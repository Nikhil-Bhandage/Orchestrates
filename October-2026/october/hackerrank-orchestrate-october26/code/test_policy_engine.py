"""
test_policy_engine.py — Comprehensive unit tests for Milestone 4 Policy Engine.
Validates all 15 deletion rules from dataset/deletion_rules.csv, step ordering against
sample_output.csv, evidence_id attribution rules, uncertainty/conflict separation,
and output contract schemas per AGENTS.md §6.3–§6.6.
"""

from __future__ import annotations

import csv
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"

# Ensure code/ is on sys.path for sibling imports
sys.path.insert(0, str(REPO_ROOT / "code"))

from data_loader import load_all_datasets
from policy_engine import (
    OP_ORDER,
    OP_REQUIRED_STATE,
    PHASE_ORDER,
    AuditStep,
    PolicyEvaluationResult,
    ResourceEvaluation,
    assemble_case_output,
    evaluate_resource_policy,
    order_and_renumber_steps,
    step_sort_key,
)


class TestAll15RulesInDataset(unittest.TestCase):
    """Verifies that all 15 rules in deletion_rules.csv are loaded and mapped correctly."""

    @classmethod
    def setUpClass(cls):
        bundle = load_all_datasets(DATASET_DIR)
        cls.rules = {r.rule_id: r for r in bundle.deletion_rules}

    def test_all_15_rules_present(self):
        self.assertEqual(len(self.rules), 15)
        for i in range(1, 16):
            rule_id = f"rule_{i:02d}"
            self.assertIn(rule_id, self.rules, f"Missing {rule_id} from dataset")

    def test_rule_01_user_profile_delete(self):
        r = self.rules["rule_01"]
        self.assertEqual(r.data_category, "USER_PROFILE")
        self.assertEqual(r.required_action, "DELETE")
        ev = ResourceEvaluation(
            resource_id="account_001", system_id="account_service", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_01"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].operation, "REPORT_REMAINING_RECORD")
        self.assertEqual(rem[0].operation, "DELETE_RECORD")
        self.assertEqual(ver[0].operation, "VERIFY_RECORD_ABSENT")

    def test_rule_02_secondary_identifier_delete(self):
        r = self.rules["rule_02"]
        self.assertEqual(r.data_category, "SECONDARY_IDENTIFIER")
        self.assertEqual(r.required_action, "DELETE")

    def test_rule_03_search_index_delete(self):
        r = self.rules["rule_03"]
        self.assertEqual(r.data_category, "SEARCH_INDEX_ENTRY")
        self.assertEqual(r.required_action, "DELETE")
        ev = ResourceEvaluation(
            resource_id="search_101", system_id="search_service", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_57"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(f[0].operation, "REPORT_REMAINING_RECORD")
        self.assertEqual(rem[0].operation, "DELETE_RECORD")

    def test_rule_05_support_message_redact(self):
        r = self.rules["rule_05"]
        self.assertEqual(r.data_category, "SUPPORT_MESSAGE")
        self.assertEqual(r.required_action, "REDACT")
        ev = ResourceEvaluation(
            resource_id="support_5569", system_id="support_platform", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_94"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(f[0].operation, "REPORT_EXPOSED_PII")
        self.assertEqual(rem[0].operation, "REDACT_RECORD")
        self.assertEqual(ver[0].operation, "VERIFY_RECORD_REDACTED")

    def test_rule_07_analytics_profile_anonymize(self):
        r = self.rules["rule_07"]
        self.assertEqual(r.data_category, "ANALYTICS_PROFILE")
        self.assertEqual(r.required_action, "ANONYMIZE")
        ev = ResourceEvaluation(
            resource_id="analytics_037", system_id="analytics_platform", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_94"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(f[0].operation, "REPORT_EXPOSED_PII")
        self.assertEqual(rem[0].operation, "ANONYMIZE_RECORD")
        self.assertEqual(ver[0].operation, "VERIFY_RECORD_ANONYMIZED")

    def test_rule_12_security_audit_log_retain(self):
        r = self.rules["rule_12"]
        self.assertEqual(r.data_category, "SECURITY_AUDIT_LOG")
        self.assertEqual(r.required_action, "RETAIN")
        ev = ResourceEvaluation(
            resource_id="audit_record_2016", system_id="security_service", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_94"
        )
        f, rem, ver = evaluate_resource_policy(ev, is_overall_complete=True)
        self.assertEqual(len(f), 0)
        self.assertEqual(len(rem), 0)
        self.assertEqual(len(ver), 1)
        self.assertEqual(ver[0].operation, "VERIFY_RECORD_PRESENT")
        self.assertEqual(ver[0].evidence_id, "evidence_94")

    def test_rule_14_backup_archive_block_restore(self):
        r = self.rules["rule_14"]
        self.assertEqual(r.data_category, "BACKUP_ARCHIVE")
        self.assertEqual(r.required_action, "RETAIN")
        ev = ResourceEvaluation(
            resource_id="backup_7809", system_id="backup_service", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="ACTIVE",
            evidence_id="evidence_94"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(f[0].operation, "REPORT_RESTORE_RISK")
        self.assertEqual(rem[0].operation, "BLOCK_RESTORE")
        self.assertEqual(ver[0].operation, "VERIFY_RESTORE_BLOCKED")

    def test_rule_15_account_tombstone_redact(self):
        r = self.rules["rule_15"]
        self.assertEqual(r.data_category, "ACCOUNT_TOMBSTONE")
        self.assertEqual(r.required_action, "REDACT")
        ev = ResourceEvaluation(
            resource_id="tombstone_9178", system_id="identity_service", data_category=r.data_category,
            applicable_rule_id=r.rule_id, required_action=r.required_action, observed_state="PRESENT",
            evidence_id="evidence_51"
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertEqual(f[0].operation, "REPORT_EXPOSED_PII")
        self.assertEqual(rem[0].operation, "REDACT_RECORD")
        self.assertEqual(ver[0].operation, "VERIFY_RECORD_REDACTED")


class TestStepOrderingMatchesSampleOutput(unittest.TestCase):
    """Verifies that the step_sort_key produces identical order to all 32 cases in sample_output.csv."""

    @classmethod
    def setUpClass(cls):
        with open(DATASET_DIR / "sample_output.csv", encoding="utf-8") as f:
            cls.sample_rows = list(csv.DictReader(f))

    def test_perfect_ordering_match_across_all_32_samples(self):
        self.assertEqual(len(self.sample_rows), 32)
        for row in self.sample_rows:
            raw_steps = json.loads(row["steps_json"])
            audit_steps = [
                AuditStep(
                    step_no=s["step_no"],
                    phase=s["phase"],
                    system_id=s["system_id"],
                    resource_id=s["resource_id"],
                    operation=s["operation"],
                    state=s["state"],
                    evidence_id=s.get("evidence_id", ""),
                )
                for s in raw_steps
            ]
            renumbered = order_and_renumber_steps(audit_steps)
            for idx, (expected, actual) in enumerate(zip(raw_steps, renumbered)):
                self.assertEqual(
                    expected["phase"], actual.phase,
                    f"{row['case_id']} step {idx+1}: phase mismatch"
                )
                self.assertEqual(
                    expected["operation"], actual.operation,
                    f"{row['case_id']} step {idx+1}: op mismatch"
                )
                self.assertEqual(
                    expected["system_id"], actual.system_id,
                    f"{row['case_id']} step {idx+1}: system mismatch"
                )
                self.assertEqual(
                    expected["resource_id"], actual.resource_id,
                    f"{row['case_id']} step {idx+1}: resource mismatch"
                )
                self.assertEqual(actual.step_no, idx + 1)


class TestRemediationDependencies(unittest.TestCase):
    """Verifies dependency rules: data flows and restore blocks must precede record changes."""

    def test_remediation_dependency_sorting(self):
        steps = [
            AuditStep(0, "REMEDIATION", "account_service", "account_01", "DELETE_RECORD", "ABSENT"),
            AuditStep(0, "REMEDIATION", "support_platform", "support_01", "REDACT_RECORD", "REDACTED"),
            AuditStep(0, "REMEDIATION", "integration_service", "data_flow_01", "DISABLE_DATA_FLOW", "DISABLED"),
            AuditStep(0, "REMEDIATION", "backup_service", "backup_01", "BLOCK_RESTORE", "BLOCKED"),
            AuditStep(0, "REMEDIATION", "analytics_platform", "analytics_01", "ANONYMIZE_RECORD", "ANONYMIZED"),
        ]
        sorted_steps = order_and_renumber_steps(steps)
        ops = [s.operation for s in sorted_steps]
        self.assertEqual(
            ops,
            [
                "DISABLE_DATA_FLOW",
                "BLOCK_RESTORE",
                "DELETE_RECORD",
                "REDACT_RECORD",
                "ANONYMIZE_RECORD",
            ]
        )


class TestEvidenceIdAttributionRules(unittest.TestCase):
    """Tests compliance with AGENTS.md §6.6 evidence_id rules."""

    def test_incomplete_case_strips_remediation_and_verification_evidence_ids(self):
        steps = [
            AuditStep(0, "FINDING", "account_service", "account_01", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_01"),
            AuditStep(0, "REMEDIATION", "account_service", "account_01", "DELETE_RECORD", "ABSENT", "evidence_01"),
            AuditStep(0, "VERIFICATION", "account_service", "account_01", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_01"),
        ]
        result = assemble_case_output("case_test", "INCOMPLETE", steps)
        for s in result.steps:
            if s.phase == "FINDING":
                self.assertEqual(s.evidence_id, "evidence_01")
            elif s.phase == "REMEDIATION":
                self.assertEqual(s.evidence_id, "")
            elif s.phase == "VERIFICATION":
                self.assertEqual(s.evidence_id, "")

    def test_not_applicable_case_empty_steps(self):
        result = assemble_case_output("case_na", "NOT_APPLICABLE", [])
        self.assertEqual(result.deletion_status, "NOT_APPLICABLE")
        self.assertEqual(result.steps_json, "[]")
        self.assertEqual(len(result.steps), 0)


class TestUncertaintyAndConflictHandling(unittest.TestCase):
    """Verifies that missing or conflicting evidence is NOT treated as proof of deletion."""

    def test_unknown_state_preserves_uncertainty(self):
        ev = ResourceEvaluation(
            resource_id="account_999", system_id="account_service", data_category="USER_PROFILE",
            applicable_rule_id="rule_01", required_action="DELETE", observed_state="UNKNOWN",
            evidence_id=""
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertFalse(ev.is_compliant)
        self.assertIsNotNone(ev.uncertainty_note)
        self.assertIn("cannot confirm absence", ev.uncertainty_note)

    def test_conflicting_state_triggers_findings(self):
        ev = ResourceEvaluation(
            resource_id="account_888", system_id="account_service", data_category="USER_PROFILE",
            applicable_rule_id="rule_01", required_action="DELETE", observed_state="CONFLICTING",
            evidence_id="evidence_54", conflict_details=["Primary shows ABSENT, but Replica shows PRESENT"]
        )
        f, rem, ver = evaluate_resource_policy(ev)
        self.assertFalse(ev.is_compliant)
        self.assertEqual(len(f), 1)
        self.assertEqual(f[0].operation, "REPORT_REMAINING_RECORD")


class TestAllowedOperationsAndStates(unittest.TestCase):
    """Verifies all operations map strictly to their allowed states in AGENTS.md §6.4."""

    def test_all_15_operations_valid(self):
        self.assertEqual(len(OP_REQUIRED_STATE), 15)
        self.assertEqual(OP_REQUIRED_STATE["REPORT_REMAINING_RECORD"], "PRESENT")
        self.assertEqual(OP_REQUIRED_STATE["REPORT_EXPOSED_PII"], "PRESENT")
        self.assertEqual(OP_REQUIRED_STATE["REPORT_ACTIVE_DATA_FLOW"], "ACTIVE")
        self.assertEqual(OP_REQUIRED_STATE["REPORT_RESTORE_RISK"], "ACTIVE")
        self.assertEqual(OP_REQUIRED_STATE["DISABLE_DATA_FLOW"], "DISABLED")
        self.assertEqual(OP_REQUIRED_STATE["BLOCK_RESTORE"], "BLOCKED")
        self.assertEqual(OP_REQUIRED_STATE["DELETE_RECORD"], "ABSENT")
        self.assertEqual(OP_REQUIRED_STATE["REDACT_RECORD"], "REDACTED")
        self.assertEqual(OP_REQUIRED_STATE["ANONYMIZE_RECORD"], "ANONYMIZED")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_RECORD_ABSENT"], "ABSENT")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_RECORD_PRESENT"], "PRESENT")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_RECORD_REDACTED"], "REDACTED")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_RECORD_ANONYMIZED"], "ANONYMIZED")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_DATA_FLOW_DISABLED"], "DISABLED")
        self.assertEqual(OP_REQUIRED_STATE["VERIFY_RESTORE_BLOCKED"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
