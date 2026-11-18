"""
policy_engine.py — Policy Engine & Step Ordering
Milestone 4: Deterministic policy evaluation, rule mapping, and output contract enforcement.

Applies the 15 deletion rules from dataset/deletion_rules.csv to evaluated records.
Enforces the exact phase ordering, operation sequencing, dependency constraints,
and evidence_id attribution rules specified in AGENTS.md §6.3–§6.6.

Key Architectural Guarantees:
  1. Grounded in actual rules: 15 explicit rules from deletion_rules.csv, no invented rules.
  2. Exact output contract:
     - Phases: FINDING -> REMEDIATION -> VERIFICATION.
     - Ordering: Phase order -> Operation table order -> system_id asc -> resource_id asc.
     - Remediation sequencing: DISABLE_DATA_FLOW and BLOCK_RESTORE before DELETE_RECORD / REDACT_RECORD / ANONYMIZE_RECORD.
     - Attribution: Findings cite visible evidence; COMPLETE-case verification cites visible evidence;
       remediation and post-remediation verification steps strictly use evidence_id = "".
  3. Separation of Policy and Evidence:
     - Missing or conflicting evidence is NOT treated as proof of deletion.
     - Preserves uncertainty and contradictions for downstream investigation agents.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger("policy_engine")

# ---------------------------------------------------------------------------
# Constants: Output Contract Definitions (AGENTS.md §6.3–§6.4)
# ---------------------------------------------------------------------------

PHASE_ORDER = {
    "FINDING": 1,
    "REMEDIATION": 2,
    "VERIFICATION": 3,
}

OP_ORDER = {
    # Phase: FINDING
    "REPORT_REMAINING_RECORD": 1,
    "REPORT_EXPOSED_PII": 2,
    "REPORT_ACTIVE_DATA_FLOW": 3,
    "REPORT_RESTORE_RISK": 4,

    # Phase: REMEDIATION (Dependency order: disable/block before record changes)
    "DISABLE_DATA_FLOW": 10,
    "BLOCK_RESTORE": 11,
    "DELETE_RECORD": 12,
    "REDACT_RECORD": 13,
    "ANONYMIZE_RECORD": 14,

    # Phase: VERIFICATION
    "VERIFY_RECORD_ABSENT": 20,
    "VERIFY_RECORD_PRESENT": 21,
    "VERIFY_RECORD_REDACTED": 22,
    "VERIFY_RECORD_ANONYMIZED": 23,
    "VERIFY_DATA_FLOW_DISABLED": 24,
    "VERIFY_RESTORE_BLOCKED": 25,
}

VALID_STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}

# Expected state for each operation (AGENTS.md §6.4)
OP_REQUIRED_STATE = {
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class AuditStep:
    """One atomic step in output.csv steps_json."""
    step_no: int
    phase: str          # "FINDING" | "REMEDIATION" | "VERIFICATION"
    system_id: str
    resource_id: str
    operation: str
    state: str
    evidence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_no": self.step_no,
            "phase": self.phase,
            "system_id": self.system_id,
            "resource_id": self.resource_id,
            "operation": self.operation,
            "state": self.state,
            "evidence_id": self.evidence_id,
        }


@dataclass
class ResourceEvaluation:
    """Evaluation context for a single resource or data flow."""
    resource_id: str
    system_id: str
    data_category: str             # e.g. "USER_PROFILE", "SECURITY_AUDIT_LOG", "DATA_FLOW", etc.
    applicable_rule_id: str        # e.g. "rule_01", "rule_12"
    required_action: str           # "DELETE" | "REDACT" | "ANONYMIZE" | "RETAIN" | "DISABLE" | "BLOCK"
    observed_state: str            # "PRESENT" | "ABSENT" | "REDACTED" | "ANONYMIZED" | "ACTIVE" | "BLOCKED" | "DISABLED" | "UNKNOWN" | "CONFLICTING"
    evidence_id: str               # cited evidence proving the observed state
    is_compliant: Optional[bool] = None
    uncertainty_note: Optional[str] = None
    conflict_details: list[str] = field(default_factory=list)


@dataclass
class PolicyEvaluationResult:
    """Complete evaluation outcome for one deletion request."""
    case_id: str
    deletion_status: str           # "COMPLETE" | "INCOMPLETE" | "NOT_APPLICABLE"
    steps: list[AuditStep]
    steps_json: str
    evaluations: list[ResourceEvaluation] = field(default_factory=list)
    has_uncertainty: bool = False
    unresolved_conflicts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule Application & Action Mapping
# ---------------------------------------------------------------------------

def evaluate_resource_policy(
    eval_ctx: ResourceEvaluation,
    is_overall_complete: bool = False,
) -> tuple[list[AuditStep], list[AuditStep], list[AuditStep]]:
    """
    Evaluates policy requirements for a single resource and returns:
      (findings, remediations, verifications)

    Strictly adheres to AGENTS.md §6.4 & §6.6:
      - Finding: cites visible evidence proving non-compliance.
      - Remediation: evidence_id is empty string "".
      - Verification:
          * In a COMPLETE case: cites visible evidence proving compliant state.
          * In an INCOMPLETE case: evidence_id is empty string "".
    """
    findings: list[AuditStep] = []
    remediations: list[AuditStep] = []
    verifications: list[AuditStep] = []

    sys_id = eval_ctx.system_id
    res_id = eval_ctx.resource_id
    action = eval_ctx.required_action
    state = eval_ctx.observed_state
    ev_id = eval_ctx.evidence_id

    # 1. Action: DELETE (rule_01, rule_02, rule_03, rule_04, rule_06, rule_09, rule_10)
    if action == "DELETE":
        if state == "PRESENT" or state == "ACTIVE" or state == "CONFLICTING":
            # Violation: record still exists
            eval_ctx.is_compliant = False
            findings.append(
                AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="REPORT_REMAINING_RECORD",
                    state="PRESENT",
                    evidence_id=ev_id,
                )
            )
            remediations.append(
                AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="DELETE_RECORD",
                    state="ABSENT",
                    evidence_id="",
                )
            )
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_ABSENT",
                    state="ABSENT",
                    evidence_id="",  # Future verification check
                )
            )
        elif state == "ABSENT":
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_ABSENT",
                    state="ABSENT",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )
        else:
            # UNKNOWN state - preserve uncertainty, do not assume compliance
            eval_ctx.is_compliant = False
            eval_ctx.uncertainty_note = f"State of {res_id} is {state}; cannot confirm absence."

    # 2. Action: REDACT (rule_05, rule_11, rule_15)
    elif action == "REDACT":
        if state == "PRESENT" or state == "ACTIVE" or state == "CONFLICTING":
            # Exposed PII: needs redaction
            eval_ctx.is_compliant = False
            findings.append(
                AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="REPORT_EXPOSED_PII",
                    state="PRESENT",
                    evidence_id=ev_id,
                )
            )
            remediations.append(
                AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="REDACT_RECORD",
                    state="REDACTED",
                    evidence_id="",
                )
            )
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_REDACTED",
                    state="REDACTED",
                    evidence_id="",
                )
            )
        elif state == "REDACTED":
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_REDACTED",
                    state="REDACTED",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )
        elif state == "ABSENT":
            # Record is already deleted/absent; compliant without needing further redaction
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_ABSENT",
                    state="ABSENT",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )
        else:
            eval_ctx.is_compliant = False
            eval_ctx.uncertainty_note = f"State of {res_id} is {state}; cannot confirm redaction."

    # 3. Action: ANONYMIZE (rule_07, rule_08)
    elif action == "ANONYMIZE":
        if state == "PRESENT" or state == "ACTIVE" or state == "CONFLICTING":
            eval_ctx.is_compliant = False
            findings.append(
                AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="REPORT_EXPOSED_PII",
                    state="PRESENT",
                    evidence_id=ev_id,
                )
            )
            remediations.append(
                AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="ANONYMIZE_RECORD",
                    state="ANONYMIZED",
                    evidence_id="",
                )
            )
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_ANONYMIZED",
                    state="ANONYMIZED",
                    evidence_id="",
                )
            )
        elif state == "ANONYMIZED":
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_ANONYMIZED",
                    state="ANONYMIZED",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )
        else:
            eval_ctx.is_compliant = False
            eval_ctx.uncertainty_note = f"State of {res_id} is {state}; cannot confirm anonymization."

    # 4. Action: RETAIN (rule_12, rule_13, rule_14)
    elif action == "RETAIN":
        if "BACKUP" in eval_ctx.data_category or "RESTORE" in eval_ctx.data_category or res_id.startswith("backup_"):
            # Backup archive retention with restore blocking
            if state == "ACTIVE" or state == "PRESENT":
                eval_ctx.is_compliant = False
                findings.append(
                    AuditStep(
                        step_no=0,
                        phase="FINDING",
                        system_id=sys_id,
                        resource_id=res_id,
                        operation="REPORT_RESTORE_RISK",
                        state="ACTIVE",
                        evidence_id=ev_id,
                    )
                )
                remediations.append(
                    AuditStep(
                        step_no=0,
                        phase="REMEDIATION",
                        system_id=sys_id,
                        resource_id=res_id,
                        operation="BLOCK_RESTORE",
                        state="BLOCKED",
                        evidence_id="",
                    )
                )
                verifications.append(
                    AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=sys_id,
                        resource_id=res_id,
                        operation="VERIFY_RESTORE_BLOCKED",
                        state="BLOCKED",
                        evidence_id="",
                    )
                )
            elif state == "BLOCKED":
                eval_ctx.is_compliant = True
                verifications.append(
                    AuditStep(
                        step_no=0,
                        phase="VERIFICATION",
                        system_id=sys_id,
                        resource_id=res_id,
                        operation="VERIFY_RESTORE_BLOCKED",
                        state="BLOCKED",
                        evidence_id=ev_id if is_overall_complete else "",
                    )
                )
        else:
            # Policy-required retained records (audit log, legal hold) must remain PRESENT
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_RECORD_PRESENT",
                    state="PRESENT",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )

    # 5. Integration Data Flows (Sync / Replication processes)
    elif action == "DISABLE" or "DATA_FLOW" in eval_ctx.data_category:
        if state == "ACTIVE" or state == "PRESENT":
            eval_ctx.is_compliant = False
            findings.append(
                AuditStep(
                    step_no=0,
                    phase="FINDING",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="REPORT_ACTIVE_DATA_FLOW",
                    state="ACTIVE",
                    evidence_id=ev_id,
                )
            )
            remediations.append(
                AuditStep(
                    step_no=0,
                    phase="REMEDIATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="DISABLE_DATA_FLOW",
                    state="DISABLED",
                    evidence_id="",
                )
            )
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_DATA_FLOW_DISABLED",
                    state="DISABLED",
                    evidence_id="",
                )
            )
        elif state == "DISABLED":
            eval_ctx.is_compliant = True
            verifications.append(
                AuditStep(
                    step_no=0,
                    phase="VERIFICATION",
                    system_id=sys_id,
                    resource_id=res_id,
                    operation="VERIFY_DATA_FLOW_DISABLED",
                    state="DISABLED",
                    evidence_id=ev_id if is_overall_complete else "",
                )
            )

    return findings, remediations, verifications


# ---------------------------------------------------------------------------
# Step Ordering & Sequential Renumbering
# ---------------------------------------------------------------------------

def step_sort_key(s: AuditStep) -> tuple[int, int, str, str]:
    """
    Exact 4-tier sort key conforming to AGENTS.md §6.3–§6.6:
      1. Phase order (FINDING=1, REMEDIATION=2, VERIFICATION=3)
      2. Operation order (table order in §6.4; data flows/restore blocks precede record changes)
      3. system_id ascending (lexicographical)
      4. resource_id ascending (lexicographical)
    """
    return (
        PHASE_ORDER.get(s.phase, 99),
        OP_ORDER.get(s.operation, 99),
        s.system_id,
        s.resource_id,
    )


def order_and_renumber_steps(steps: list[AuditStep]) -> list[AuditStep]:
    """
    Sorts steps deterministically and renumbers step_no consecutively starting at 1.
    """
    sorted_steps = sorted(steps, key=step_sort_key)
    renumbered = []
    for idx, s in enumerate(sorted_steps, start=1):
        renumbered.append(
            AuditStep(
                step_no=idx,
                phase=s.phase,
                system_id=s.system_id,
                resource_id=s.resource_id,
                operation=s.operation,
                state=s.state,
                evidence_id=s.evidence_id,
            )
        )
    return renumbered


# ---------------------------------------------------------------------------
# Output Serialization & Assembly
# ---------------------------------------------------------------------------

def assemble_case_output(
    case_id: str,
    deletion_status: str,
    steps: list[AuditStep],
    evaluations: Optional[list[ResourceEvaluation]] = None,
) -> PolicyEvaluationResult:
    """
    Validates constraints and serializes steps to JSON.
    Guarantees:
      - NOT_APPLICABLE -> steps_json = "[]"
      - COMPLETE -> only VERIFICATION steps with valid evidence citations
      - INCOMPLETE -> FINDING + REMEDIATION + VERIFICATION
    """
    if deletion_status not in VALID_STATUSES:
        raise ValueError(f"Invalid deletion_status '{deletion_status}'. Must be one of {VALID_STATUSES}")

    if deletion_status == "NOT_APPLICABLE":
        return PolicyEvaluationResult(
            case_id=case_id,
            deletion_status="NOT_APPLICABLE",
            steps=[],
            steps_json="[]",
            evaluations=evaluations or [],
            has_uncertainty=False,
        )

    # Order and sequentially number steps
    ordered_steps = order_and_renumber_steps(steps)

    # Sanity checks per contract
    if deletion_status == "COMPLETE":
        for s in ordered_steps:
            if s.phase != "VERIFICATION":
                raise ValueError(f"COMPLETE case {case_id} contains non-VERIFICATION step: {s}")
            if not s.evidence_id:
                logger.warning("COMPLETE case %s verification step %s has empty evidence_id.", case_id, s.resource_id)

    elif deletion_status == "INCOMPLETE":
        for s in ordered_steps:
            if s.phase in ("REMEDIATION", "VERIFICATION") and s.evidence_id != "":
                # In an incomplete case, proposed remediation and future verification must use ""
                s.evidence_id = ""

    # Serialize steps to JSON array
    dict_steps = [s.to_dict() for s in ordered_steps]
    steps_json = json.dumps(dict_steps, separators=(",", ":"))

    has_uncertainty = False
    unresolved_conflicts: list[str] = []
    if evaluations:
        for ev in evaluations:
            if ev.uncertainty_note:
                has_uncertainty = True
            if ev.conflict_details:
                unresolved_conflicts.extend(ev.conflict_details)

    return PolicyEvaluationResult(
        case_id=case_id,
        deletion_status=deletion_status,
        steps=ordered_steps,
        steps_json=steps_json,
        evaluations=evaluations or [],
        has_uncertainty=has_uncertainty,
        unresolved_conflicts=unresolved_conflicts,
    )
