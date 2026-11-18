"""
test_workflow.py -- Unit and Integration Tests for LangGraph Workflow
Milestone 6: Validates multi-agent graph orchestration, state schemas,
adversarial audit invariants, bounded loops, replica conflict handling,
and benchmark evaluation on sample_output.csv.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = REPO_ROOT / "code"
DATASET_DIR = REPO_ROOT / "dataset"

if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from policy_engine import AuditStep, ResourceEvaluation
from workflow import (
    audit_node,
    audit_single_case,
    build_audit_graph,
    evidence_node,
    get_compiled_graph,
    get_global_bundle_and_index,
    identity_node,
    manager_node,
    output_node,
    policy_node,
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


class TestWorkflowStateSchema(unittest.TestCase):
    """Verifies state initialization, typed dictionary fields, and serialization."""

    def test_create_initial_state(self):
        state = create_initial_state(
            case_id="case_test",
            request_email="user@example.com",
            request_text="Please delete my account",
            requested_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime(2026, 8, 2, 10, 0, tzinfo=timezone.utc),
            audit_at=datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc),
            max_iterations=2,
        )
        self.assertEqual(state["case_id"], "case_test")
        self.assertEqual(state["request_email"], "user@example.com")
        self.assertEqual(state["identifiers"], ["user@example.com"])
        self.assertEqual(state["iteration_count"], 0)
        self.assertEqual(state["max_iterations"], 2)
        self.assertFalse(state["audit_passed"])
        self.assertEqual(state["steps_json"], "[]")

    def test_serialization_helpers(self):
        ev = ResourceEvaluation(
            resource_id="acc_1",
            system_id="account_service",
            data_category="USER_PROFILE",
            applicable_rule_id="rule_01",
            required_action="DELETE",
            observed_state="ABSENT",
            evidence_id="evidence_54",
            is_compliant=True,
            uncertainty_note="",
            conflict_details=["drift"],
        )
        d = eval_to_dict(ev)
        self.assertEqual(d["resource_id"], "acc_1")
        self.assertEqual(d["conflict_details"], ["drift"])
        ev_back = eval_from_dict(d)
        self.assertEqual(ev_back.resource_id, ev.resource_id)
        self.assertEqual(ev_back.conflict_details, ev.conflict_details)

        step = AuditStep(
            step_no=1,
            phase="FINDING",
            system_id="search_service",
            resource_id="search_01",
            operation="REPORT_REMAINING_RECORD",
            state="PRESENT",
            evidence_id="ev_01",
        )
        sd = step_to_dict(step)
        step_back = step_from_dict(sd)
        self.assertEqual(step_back.step_no, 1)
        self.assertEqual(step_back.operation, "REPORT_REMAINING_RECORD")


class TestManagerRoutingAndIntent(unittest.TestCase):
    """Verifies Manager decisions, short-circuits, and bounded iterations."""

    def test_non_deletion_short_circuit(self):
        """Access, export, and marketing requests must immediately exit as NOT_APPLICABLE."""
        non_del_texts = [
            "Please send me a full copy of all data you have collected about me.",
            "I want to export my order history to CSV for tax purposes.",
            "Please correct my misspelled last name from Smith to Smyth.",
            "Unsubscribe me from promotional marketing emails but keep my account active.",
        ]
        for text in non_del_texts:
            state = create_initial_state(
                case_id="case_na",
                request_email="user@test.com",
                request_text=text,
                requested_at=datetime.now(timezone.utc),
                reported_status="NOT_STARTED",
                reported_at=datetime.now(timezone.utc),
                audit_at=datetime.now(timezone.utc),
            )
            out_state = manager_node(state)
            self.assertEqual(out_state["deletion_status"], "NOT_APPLICABLE")
            self.assertEqual(out_state["steps_json"], "[]")
            self.assertEqual(out_state["next_node"], "output_node")
            self.assertEqual(out_state["manager_decision"]["action"], "SHORT_CIRCUIT_NOT_APPLICABLE")

    def test_iteration_limit_enforcement(self):
        """When iteration_count reaches max_iterations, Manager must force conservative termination."""
        state = create_initial_state(
            case_id="case_limit",
            request_email="user@test.com",
            request_text="Delete my account completely.",
            requested_at=datetime.now(timezone.utc),
            reported_status="COMPLETE",
            reported_at=datetime.now(timezone.utc),
            audit_at=datetime.now(timezone.utc),
            max_iterations=2,
        )
        state["intent_is_deletion"] = True
        state["iteration_count"] = 2
        state["audit_passed"] = False
        state["audit_challenges"] = [{"target_agent": "evidence", "issue": "Missing proof"}]

        out_state = manager_node(state)
        self.assertEqual(out_state["next_node"], "output_node")
        self.assertEqual(out_state["deletion_status"], "INCOMPLETE")
        self.assertEqual(out_state["manager_decision"]["action"], "FINALIZE")


class TestReplicaConflictPolicyMapping(unittest.TestCase):
    """
    Verifies that replica conflicts are resolved according to applicable policy rules
    rather than a blind assumption that primary ABSENT + replica PRESENT = DELETE_RECORD.
    """

    def test_replica_conflict_uses_applicable_policy_rule(self):
        # 1. USER_PROFILE category -> rule requires DELETE
        ev_profile = ResourceEvaluation(
            resource_id="account_101",
            system_id="account_service",
            data_category="USER_PROFILE",
            applicable_rule_id="rule_01",
            required_action="DELETE",
            observed_state="CONFLICTING",
            evidence_id="ev_replica",
            is_compliant=False,
            uncertainty_note="Replication drift",
            conflict_details=["Primary absent, replica present"],
        )
        f1, r1, v1 = policy_node({
            "evaluations": [eval_to_dict(ev_profile)],
            "unresolved_conflicts": ["Primary absent, replica present"],
            "evidence_gaps": [],
        })["steps"], [], []
        ops1 = [s["operation"] for s in f1]
        self.assertIn("REPORT_REMAINING_RECORD", ops1)
        self.assertIn("DELETE_RECORD", ops1)
        self.assertIn("VERIFY_RECORD_ABSENT", ops1)

        # 2. ACCOUNT_TOMBSTONE category -> rule requires REDACT (not DELETE!)
        ev_tombstone = ResourceEvaluation(
            resource_id="tombstone_101",
            system_id="account_service",
            data_category="ACCOUNT_TOMBSTONE",
            applicable_rule_id="rule_15",
            required_action="REDACT",
            observed_state="CONFLICTING",
            evidence_id="ev_replica",
            is_compliant=False,
            uncertainty_note="Replication drift on tombstone",
            conflict_details=["Primary redacted, replica contains PII"],
        )
        res_tomb = policy_node({
            "evaluations": [eval_to_dict(ev_tombstone)],
            "unresolved_conflicts": ["Replica contains PII"],
            "evidence_gaps": [],
        })
        ops2 = [s["operation"] for s in res_tomb["steps"]]
        self.assertIn("REPORT_EXPOSED_PII", ops2)
        self.assertIn("REDACT_RECORD", ops2)
        self.assertIn("VERIFY_RECORD_REDACTED", ops2)
        self.assertNotIn("DELETE_RECORD", ops2)

        # 3. ANALYTICS_PROFILE category -> rule requires ANONYMIZE
        ev_analytics = ResourceEvaluation(
            resource_id="analytics_101",
            system_id="analytics_platform",
            data_category="ANALYTICS_PROFILE",
            applicable_rule_id="rule_07",
            required_action="ANONYMIZE",
            observed_state="CONFLICTING",
            evidence_id="ev_replica",
            is_compliant=False,
            uncertainty_note="Replica not yet anonymized",
            conflict_details=["Replica has raw identifiers"],
        )
        res_analytics = policy_node({
            "evaluations": [eval_to_dict(ev_analytics)],
            "unresolved_conflicts": ["Replica has raw identifiers"],
            "evidence_gaps": [],
        })
        ops3 = [s["operation"] for s in res_analytics["steps"]]
        self.assertIn("REPORT_EXPOSED_PII", ops3)
        self.assertIn("ANONYMIZE_RECORD", ops3)
        self.assertIn("VERIFY_RECORD_ANONYMIZED", ops3)
        self.assertNotIn("DELETE_RECORD", ops3)


class TestAdversarialAuditAgent(unittest.TestCase):
    """Verifies independent adversarial invariant validation."""

    def test_audit_challenges_uncited_findings(self):
        state: AuditWorkflowState = {
            "case_id": "c1",
            "audit_at": "2026-09-01T12:00:00+00:00",
            "deletion_status": "INCOMPLETE",
            "steps": [
                step_to_dict(AuditStep(1, "FINDING", "account_service", "acc_1", "REPORT_REMAINING_RECORD", "PRESENT", evidence_id="")),
            ],
            "evaluations": [],
        }
        res = audit_node(state)
        self.assertFalse(res["audit_passed"])
        self.assertTrue(any("Missing required evidence_id" in c["issue"] for c in res["audit_challenges"]))

    def test_audit_challenges_post_audit_citations(self):
        state: AuditWorkflowState = {
            "case_id": "c2",
            "audit_at": "2026-08-01T12:00:00+00:00",
            "deletion_status": "COMPLETE",
            "steps": [
                # evidence_01 was captured in September 2026 (> August cutoff)
                step_to_dict(AuditStep(1, "VERIFICATION", "account_service", "acc_1", "VERIFY_RECORD_ABSENT", "ABSENT", evidence_id="evidence_01")),
            ],
            "evaluations": [],
        }
        res = audit_node(state)
        self.assertFalse(res["audit_passed"])
        self.assertTrue(any("is after audit_at" in c["issue"] for c in res["audit_challenges"]))

    def test_audit_challenges_remediation_dependency_inversion(self):
        """DISABLE_DATA_FLOW and BLOCK_RESTORE must precede record alterations."""
        state: AuditWorkflowState = {
            "case_id": "c3",
            "audit_at": "2026-10-01T12:00:00+00:00",
            "deletion_status": "INCOMPLETE",
            "steps": [
                step_to_dict(AuditStep(1, "REMEDIATION", "account_service", "acc_1", "DELETE_RECORD", "ABSENT", evidence_id="")),
                step_to_dict(AuditStep(2, "REMEDIATION", "integration_service", "flow_1", "DISABLE_DATA_FLOW", "DISABLED", evidence_id="")),
            ],
            "evaluations": [],
        }
        res = audit_node(state)
        self.assertFalse(res["audit_passed"])
        self.assertTrue(any("appeared after record changes" in c["issue"] for c in res["audit_challenges"]))

    def test_audit_challenges_tombstone_deletion(self):
        state: AuditWorkflowState = {
            "case_id": "c4",
            "audit_at": "2026-10-01T12:00:00+00:00",
            "deletion_status": "INCOMPLETE",
            "steps": [
                step_to_dict(AuditStep(1, "REMEDIATION", "identity_service", "tombstone_99", "DELETE_RECORD", "ABSENT", evidence_id="")),
            ],
            "evaluations": [],
        }
        res = audit_node(state)
        self.assertFalse(res["audit_passed"])
        self.assertTrue(any("tombstone must be REDACTED" in c["issue"] for c in res["audit_challenges"]))


class TestBenchmarkSampleCases(unittest.TestCase):
    """
    Evaluates compiled LangGraph workflow against all 32 sample cases in sample_output.csv.
    Asserts schema validity, status accuracy, and step structure without hardcoding.
    """

    @classmethod
    def setUpClass(cls):
        cls.bundle, cls.index = get_global_bundle_and_index()
        sample_out_file = DATASET_DIR / "sample_output.csv"
        cls.golden = {}
        with sample_out_file.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cls.golden[r["case_id"]] = {
                    "deletion_status": r["deletion_status"],
                    "steps": json.loads(r["steps_json"]),
                }

    def test_sample_case_outputs(self):
        total = len(self.bundle.sample_requests)
        status_matches = 0

        for req in self.bundle.sample_requests:
            cid = req.case_id
            gold = self.golden.get(cid)
            self.assertIsNotNone(gold, f"Golden output missing for {cid}")

            final_state = audit_single_case(cid, bundle=self.bundle, index=self.index)
            pred_status = final_state.get("deletion_status")
            pred_steps_json = final_state.get("steps_json", "[]")

            # 1. Schema check
            parsed = json.loads(pred_steps_json)
            self.assertIsInstance(parsed, list)
            for idx, s in enumerate(parsed, start=1):
                self.assertEqual(s["step_no"], idx)
                self.assertIn(s["phase"], ("FINDING", "REMEDIATION", "VERIFICATION"))
                self.assertTrue(bool(s["system_id"]))
                self.assertTrue(bool(s["resource_id"]))
                self.assertTrue(bool(s["operation"]))
                self.assertTrue(bool(s["state"]))
                self.assertIn("evidence_id", s)

            if pred_status == gold["deletion_status"]:
                status_matches += 1

        acc = status_matches / total
        self.assertGreaterEqual(acc, 0.70, f"Sample status accuracy {acc:.1%} below 70% baseline.")


if __name__ == "__main__":
    unittest.main()
