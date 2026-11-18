"""
workflow.py -- LangGraph Workflow Assembly for Deletion Audit
Milestone 6: Orchestrates Manager, Identity, Evidence, Policy, and Audit agents
in a cyclic LangGraph with bounded iterations and safe deterministic guards.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = REPO_ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from langgraph.graph import END, START, StateGraph

from data_loader import (
    DatasetBundle,
    DeletionRequest,
    get_historical_identifiers,
    load_all_datasets,
    resolve_identity,
)
from evidence_agent import (
    GeminiUsage,
    _extract_text_from_image,
    _load_system_activity,
    _pick_state_from_hits,
    _reinspect_png_hits,
    _data_category_from_resource_id,
    _rule_for_category,
    investigate_case,
)
from evidence_indexer import (
    EvidenceHit,
    InvertedEvidenceIndex,
    _infer_system_id,
    get_evidence_index,
)
from intent_classifier import classify_single
import llm_provider as _llm
from policy_engine import (
    AuditStep,
    ResourceEvaluation,
    assemble_case_output,
    evaluate_resource_policy,
    order_and_renumber_steps,
)
from workflow_state import (
    AuditChallenge,
    AuditWorkflowState,
    ManagerDecision,
    create_initial_state,
    eval_from_dict,
    eval_to_dict,
    step_from_dict,
    step_to_dict,
)

logger = logging.getLogger("workflow")

_GLOBAL_BUNDLE: Optional[DatasetBundle] = None
_GLOBAL_INDEX: Optional[InvertedEvidenceIndex] = None


def get_global_bundle_and_index(dataset_dir: Optional[Path] = None) -> tuple[DatasetBundle, InvertedEvidenceIndex]:
    global _GLOBAL_BUNDLE, _GLOBAL_INDEX
    ddir = dataset_dir if dataset_dir else REPO_ROOT / "dataset"
    if _GLOBAL_BUNDLE is None:
        _GLOBAL_BUNDLE = load_all_datasets(ddir)
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = get_evidence_index(ddir)
    return _GLOBAL_BUNDLE, _GLOBAL_INDEX


# ---------------------------------------------------------------------------
# Node 1: Identity Agent
# ---------------------------------------------------------------------------

def identity_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Reconstructs the subject's identity universe at or before audit_at.
    Recovers stable user_id, current email, historical emails, phones, and email hashes.
    """
    bundle, _ = get_global_bundle_and_index()
    audit_at = datetime.fromisoformat(state["audit_at"])
    email = state["request_email"]

    resolution = resolve_identity(email, bundle)
    identifiers = set(state.get("identifiers", []))
    identifiers.add(email.lower())

    user_id = None
    if resolution:
        user_id = resolution.user_id
        identifiers.add(user_id.lower())
        hist = get_historical_identifiers(user_id, as_of=audit_at, bundle=bundle)
        identifiers.update(e.lower() for e in hist.emails)
        identifiers.update(p.lower() for p in hist.phones if p)
        identifiers.update(h.lower() for h in hist.email_hashes if h)

    directive = (state.get("manager_decision") or {}).get("targeted_directive", {})
    if "add_identifier" in directive:
        identifiers.add(directive["add_identifier"].lower())

    state["user_id"] = user_id
    state["identifiers"] = sorted(list(identifiers))
    return state


# ---------------------------------------------------------------------------
# Node 2: Evidence Investigation Agent
# ---------------------------------------------------------------------------

def evidence_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Reconstructs resource states at audit_at using evidence files and system activity.
    Detects replication drift, active sync flows, and restore risks.
    Preserves uncertainty (UNKNOWN) when evidence is missing.
    """
    bundle, index = get_global_bundle_and_index()
    usage = GeminiUsage(
        prompt_tokens=state.get("gemini_prompt_tokens", 0),
        completion_tokens=state.get("gemini_completion_tokens", 0),
        call_count=state.get("gemini_call_count", 0),
    )

    inv_res = investigate_case(state["case_id"], bundle, index, usage=usage)

    state["gemini_prompt_tokens"] = usage.prompt_tokens
    state["gemini_completion_tokens"] = usage.completion_tokens
    state["gemini_call_count"] = usage.call_count

    evidence_gaps = list(state.get("evidence_gaps", []))
    for gap in inv_res.evidence_gaps:
        if gap not in evidence_gaps:
            evidence_gaps.append(gap)

    unresolved_conflicts = list(state.get("unresolved_conflicts", []))
    for ev in inv_res.evaluations:
        for c in ev.conflict_details:
            if c not in unresolved_conflicts:
                unresolved_conflicts.append(c)

    state["evaluations"] = [eval_to_dict(e) for e in inv_res.evaluations]
    state["evidence_gaps"] = evidence_gaps
    state["unresolved_conflicts"] = unresolved_conflicts
    return state


# ---------------------------------------------------------------------------
# Node 3: Policy Engine Agent
# ---------------------------------------------------------------------------

def policy_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Applies the 15 deletion rules from deletion_rules.csv to evaluated records.
    Synthesizes findings, remediations, and verifications with strict 4-tier ordering.
    """
    eval_dicts = state.get("evaluations", [])
    evaluations = [eval_from_dict(d) for d in eval_dicts]
    evidence_gaps = state.get("evidence_gaps", [])
    conflicts = state.get("unresolved_conflicts", [])

    has_non_compliant = any(e.is_compliant is False for e in evaluations)
    has_unknown = any(e.observed_state in ("UNKNOWN", "CONFLICTING") for e in evaluations)
    has_gaps = len(evidence_gaps) > 0
    has_conflicts = len(conflicts) > 0

    preliminary_complete = not (has_non_compliant or has_unknown or has_gaps or has_conflicts)

    all_findings: List[AuditStep] = []
    all_remediations: List[AuditStep] = []
    all_verifications: List[AuditStep] = []

    for ev in evaluations:
        findings, remediations, verifications = evaluate_resource_policy(
            ev, is_overall_complete=preliminary_complete
        )
        all_findings.extend(findings)
        all_remediations.extend(remediations)
        all_verifications.extend(verifications)

    if all_findings or has_non_compliant or has_unknown or has_gaps or has_conflicts:
        deletion_status = "INCOMPLETE"
        steps = all_findings + all_remediations + all_verifications
    else:
        deletion_status = "COMPLETE"
        steps = all_verifications

    ordered_steps = order_and_renumber_steps(steps)

    state["deletion_status"] = deletion_status
    state["steps"] = [step_to_dict(s) for s in ordered_steps]
    state["evaluations"] = [eval_to_dict(e) for e in evaluations]
    return state


# ---------------------------------------------------------------------------
# Node 4: Audit and Verification Agent
# ---------------------------------------------------------------------------

def audit_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Adversarial verification node.
    Independently challenges conclusions, verifies evidence citations, temporal cutoff,
    tombstone direct PII redactions, and remediation dependencies.
    """
    bundle, index = get_global_bundle_and_index()
    audit_at = datetime.fromisoformat(state["audit_at"])
    status = state.get("deletion_status", "INCOMPLETE")
    steps = [step_from_dict(d) for d in state.get("steps", [])]
    challenges: List[AuditChallenge] = []

    if status == "COMPLETE":
        has_finding = any(s.phase == "FINDING" for s in steps)
        has_remed = any(s.phase == "REMEDIATION" for s in steps)
        if has_finding or has_remed:
            challenges.append(AuditChallenge(
                target_agent="policy",
                resource_id="ALL",
                system_id="ALL",
                issue="COMPLETE status cannot contain FINDING or REMEDIATION steps.",
                required_action="Re-evaluate policy status.",
            ))

    for s in steps:
        if s.phase == "FINDING" or (status == "COMPLETE" and s.phase == "VERIFICATION"):
            if not s.evidence_id:
                challenges.append(AuditChallenge(
                    target_agent="evidence",
                    resource_id=s.resource_id,
                    system_id=s.system_id,
                    issue=f"Missing required evidence_id in {s.phase} step {s.step_no}.",
                    required_action="Supply participant-visible evidence_id or adjust status.",
                ))
            else:
                ev_id = s.evidence_id
                if ev_id in index.files:
                    summary = index.files[ev_id]
                    if summary.captured_at > audit_at:
                        challenges.append(AuditChallenge(
                            target_agent="evidence",
                            resource_id=s.resource_id,
                            system_id=s.system_id,
                            issue=f"Evidence {ev_id} captured at {summary.captured_at} is after audit_at {audit_at}.",
                            required_action="Exclude post-audit evidence.",
                        ))
        elif s.phase == "REMEDIATION" or (status == "INCOMPLETE" and s.phase == "VERIFICATION"):
            if s.evidence_id != "":
                challenges.append(AuditChallenge(
                    target_agent="policy",
                    resource_id=s.resource_id,
                    system_id=s.system_id,
                    issue=f"Remediation/future verification step {s.step_no} must have empty evidence_id, got '{s.evidence_id}'.",
                    required_action="Set evidence_id to empty string.",
                ))

    remed_ops = [s.operation for s in steps if s.phase == "REMEDIATION"]
    seen_record_change = False
    for op in remed_ops:
        if op in ("DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"):
            seen_record_change = True
        elif op in ("DISABLE_DATA_FLOW", "BLOCK_RESTORE"):
            if seen_record_change:
                challenges.append(AuditChallenge(
                    target_agent="policy",
                    resource_id="ORDERING",
                    system_id="DEPENDENCY",
                    issue=f"{op} appeared after record changes; flows and restores must be blocked first.",
                    required_action="Reorder remediation steps to satisfy dependency constraints.",
                ))

    for s in steps:
        if "tombstone" in s.resource_id.lower():
            if s.operation == "DELETE_RECORD":
                challenges.append(AuditChallenge(
                    target_agent="policy",
                    resource_id=s.resource_id,
                    system_id=s.system_id,
                    issue="Account tombstone must be REDACTED, never deleted.",
                    required_action="Change operation to REDACT_RECORD / VERIFY_RECORD_REDACTED.",
                ))

    eval_dicts = state.get("evaluations", [])
    if status == "COMPLETE":
        for ed in eval_dicts:
            if ed.get("observed_state") in ("UNKNOWN", "CONFLICTING"):
                challenges.append(AuditChallenge(
                    target_agent="policy",
                    resource_id=ed.get("resource_id", ""),
                    system_id=ed.get("system_id", ""),
                    issue=f"Cannot declare COMPLETE when resource {ed.get('resource_id')} is {ed.get('observed_state')}.",
                    required_action="Change status to INCOMPLETE.",
                ))

    state["audit_challenges"] = [c.to_dict() for c in challenges]
    state["audit_passed"] = (len(challenges) == 0)
    return state


# ---------------------------------------------------------------------------
# Node 5: Manager Agent
# ---------------------------------------------------------------------------

def manager_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Central orchestrator. Decides next action:
      - Intent check: short-circuits NOT_APPLICABLE cases immediately.
      - First cycle: initiates identity -> evidence -> policy -> audit pipeline.
      - Iterative cycle: assesses audit challenges, applies bounded LLM reasoning
        (or deterministic fallback), and dispatches targeted re-investigation or finalization.
    """
    if state.get("intent_is_deletion") is None:
        intent_res = classify_single(state["case_id"], state["request_text"])
        state["intent_is_deletion"] = intent_res.is_deletion_authorized
        state["intent_confidence"] = intent_res.confidence
        state["intent_method"] = intent_res.method

        if not intent_res.is_deletion_authorized:
            state["deletion_status"] = "NOT_APPLICABLE"
            state["steps"] = []
            state["steps_json"] = "[]"
            state["audit_passed"] = True
            state["next_node"] = "output_node"
            state["manager_decision"] = ManagerDecision(
                action="SHORT_CIRCUIT_NOT_APPLICABLE",
                target_agent="output",
                reasoning="Request does not authorize deletion. Short-circuiting to output.",
            ).to_dict()
            return state

        state["next_node"] = "identity_node"
        return state

    audit_passed = state.get("audit_passed", False)
    if audit_passed:
        state["next_node"] = "output_node"
        state["manager_decision"] = ManagerDecision(
            action="FINALIZE",
            target_agent="output",
            reasoning="Audit invariants passed cleanly. Proceeding to output assembly.",
        ).to_dict()
        return state

    iteration_count = state.get("iteration_count", 0)
    max_iterations = state.get("max_iterations", 2)

    if iteration_count >= max_iterations:
        logger.info("Case %s reached max iterations (%d). Forcing conservative finalization.", state['case_id'], max_iterations)
        state["deletion_status"] = "INCOMPLETE"
        state["next_node"] = "output_node"
        state["manager_decision"] = ManagerDecision(
            action="FINALIZE",
            target_agent="output",
            reasoning=f"Reached max iterations ({max_iterations}). Finalizing conservatively as INCOMPLETE.",
        ).to_dict()
        return state

    state["iteration_count"] = iteration_count + 1
    challenges = [AuditChallenge.from_dict(c) for c in state.get("audit_challenges", [])]

    decision: Optional[ManagerDecision] = None

    if challenges:
        prompt = (
            f"Case: {state['case_id']}\n"
            f"Request: {state['request_text']}\n"
            f"Audit Challenges: {json.dumps([c.to_dict() for c in challenges])}\n"
            f"Decide which agent should resolve these challenges: 'evidence', 'policy', or 'identity'.\n"
            f"Output valid JSON only: {{\"target_agent\": \"agent_name\", \"reasoning\": \"rationale\"}}"
        )
        try:
            text, provider = _llm.call_text(
                prompt,
                model_groq="openai/gpt-oss-120b",
                model_gemini="gemini-1.5-flash",
                max_tokens=256,
                temperature=0.0,
                max_retries=1,
            )
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            data = json.loads(text)
            target = data.get("target_agent", "policy").lower()
            if target in ("evidence", "policy", "identity"):
                decision = ManagerDecision(
                    action=f"ROUTE_TO_{target.upper()}",
                    target_agent=target,
                    reasoning=data.get("reasoning", f"{provider} selected target agent."),
                    is_llm_judgment=True,
                )
                logger.debug("Manager routed to %s via %s.", target, provider)
        except RuntimeError as exc:
            # Both providers failed — preserve uncertainty, do not silently default
            logger.warning("Manager LLM judgment failed (both providers): %s. Using safe deterministic routing.", exc)
            decision = None
        except Exception as exc:
            logger.warning("Manager LLM judgment failed: %s; falling back to deterministic routing.", type(exc).__name__)
            decision = None

    if decision is None:
        if any(c.target_agent == "identity" for c in challenges):
            target = "identity"
        elif any(c.target_agent == "evidence" for c in challenges):
            target = "evidence"
        else:
            target = "policy"

        decision = ManagerDecision(
            action=f"ROUTE_TO_{target.upper()}",
            target_agent=target,
            reasoning=f"Deterministic routing to {target} based on primary audit challenge.",
            is_llm_judgment=False,
        )

    state["manager_decision"] = decision.to_dict()
    state["next_node"] = f"{decision.target_agent}_node"
    return state


# ---------------------------------------------------------------------------
# Node 6: Output Assembly Node
# ---------------------------------------------------------------------------

def output_node(state: AuditWorkflowState) -> AuditWorkflowState:
    """
    Serializes final steps_json per AGENTS.md §6.3.
    Guarantees:
      - NOT_APPLICABLE -> steps_json = '[]'
      - COMPLETE -> only verification steps
      - INCOMPLETE -> findings + remediation + verification
    """
    status = state.get("deletion_status", "INCOMPLETE")
    steps = [step_from_dict(d) for d in state.get("steps", [])]

    if status == "NOT_APPLICABLE":
        state["steps_json"] = "[]"
        state["steps"] = []
    else:
        if status == "INCOMPLETE":
            for s in steps:
                if s.phase in ("REMEDIATION", "VERIFICATION"):
                    s.evidence_id = ""
        steps_dicts = [s.to_dict() for s in steps]
        state["steps"] = steps_dicts
        state["steps_json"] = json.dumps(steps_dicts, separators=(",", ":"))

    state["next_node"] = "END"
    return state


# ---------------------------------------------------------------------------
# LangGraph Workflow Graph Assembly
# ---------------------------------------------------------------------------

def _route_manager(state: AuditWorkflowState) -> str:
    next_node = state.get("next_node", "output_node")
    if next_node == "identity_node":
        return "identity"
    elif next_node == "evidence_node":
        return "evidence"
    elif next_node == "policy_node":
        return "policy"
    return "output"


def _route_audit(state: AuditWorkflowState) -> str:
    return "manager"


def build_audit_graph():
    """
    Assembles and compiles the LangGraph StateGraph.
    """
    graph = StateGraph(AuditWorkflowState)

    graph.add_node("manager", manager_node)
    graph.add_node("identity", identity_node)
    graph.add_node("evidence", evidence_node)
    graph.add_node("policy", policy_node)
    graph.add_node("audit", audit_node)
    graph.add_node("output", output_node)

    graph.add_edge(START, "manager")

    graph.add_conditional_edges(
        "manager",
        _route_manager,
        {
            "identity": "identity",
            "evidence": "evidence",
            "policy": "policy",
            "output": "output",
        },
    )

    graph.add_edge("identity", "evidence")
    graph.add_edge("evidence", "policy")
    graph.add_edge("policy", "audit")

    graph.add_conditional_edges(
        "audit",
        _route_audit,
        {
            "manager": "manager",
        },
    )

    graph.add_edge("output", END)

    return graph.compile()


_COMPILED_GRAPH = None

def get_compiled_graph():
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_audit_graph()
    return _COMPILED_GRAPH


def audit_single_case(
    case_id: str,
    bundle: Optional[DatasetBundle] = None,
    index: Optional[InvertedEvidenceIndex] = None,
    max_iterations: int = 2,
) -> AuditWorkflowState:
    """
    Audits a single deletion request through the compiled LangGraph workflow.
    """
    if bundle is None:
        bundle, _ = get_global_bundle_and_index()

    req = next((r for r in bundle.deletion_requests if r.case_id == case_id), None)
    if req is None:
        req = next((r for r in bundle.sample_requests if r.case_id == case_id), None)
    if req is None:
        raise KeyError(f"Case {case_id} not found in deletion_requests or sample_requests.")

    initial_state = create_initial_state(
        case_id=req.case_id,
        request_email=req.email,
        request_text=req.request_text,
        requested_at=req.requested_at,
        reported_status=req.reported_status,
        reported_at=req.reported_at,
        audit_at=req.audit_at,
        max_iterations=max_iterations,
    )

    compiled = get_compiled_graph()
    final_state = compiled.invoke(initial_state)
    return final_state