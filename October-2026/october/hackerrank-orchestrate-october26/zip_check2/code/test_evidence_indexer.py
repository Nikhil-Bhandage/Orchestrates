"""
test_evidence_indexer.py — Comprehensive unit tests for Milestone 3 Evidence Pre-Indexer.
Tests corpus-wide parsing, SQL in-memory execution, pdfplumber extraction, JSON/log/TXT
parsers, inverted index lookups, and per-case audit_at temporal boundary filtering.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"

# Ensure code/ is on sys.path for sibling imports
sys.path.insert(0, str(REPO_ROOT / "code"))

from data_loader import EvidenceFile, load_all_datasets
from evidence_indexer import (
    EvidenceHit,
    InvertedEvidenceIndex,
    get_evidence_index,
    parse_json_evidence,
    parse_log_evidence,
    parse_pdf_evidence,
    parse_sql_evidence,
    parse_txt_evidence,
)


class TestEvidenceCorpusParsing(unittest.TestCase):
    """Verifies that all 94 evidence files in dataset/evidence/ parse cleanly."""

    @classmethod
    def setUpClass(cls):
        cls.indexer = InvertedEvidenceIndex(DATASET_DIR)
        cls.report = cls.indexer.build_index()

    def test_all_manifest_files_accounted_for(self):
        self.assertEqual(self.report.total_files, 94)
        self.assertEqual(self.report.succeeded_files, 94)
        self.assertEqual(self.report.failed_files, 0)
        self.assertEqual(len(self.report.parsing_errors), 0)

    def test_file_type_counts(self):
        expected_types = {"sql": 24, "pdf": 4, "json": 28, "log": 26, "txt": 1, "png": 11}
        self.assertEqual(self.report.files_by_type, expected_types)

    def test_total_hits_and_unique_identifiers(self):
        self.assertGreater(self.report.total_hits, 4000)
        self.assertGreater(self.report.unique_identifiers, 2000)


class TestSQLParser(unittest.TestCase):
    """Tests SQL parser using in-memory SQLite isolation."""

    def test_parse_customer_accounts_failover_replica(self):
        ef = EvidenceFile(
            file_id="evidence_54",
            file_path="evidence/databases/customer_accounts_failover_replica_20260902.sql",
            origin="customer_account_failover_replica_capture",
            captured_at=datetime(2026, 9, 2, 23, 0, 0, tzinfo=timezone.utc),
        )
        sql_path = DATASET_DIR / ef.file_path
        self.assertTrue(sql_path.exists())
        hits = parse_sql_evidence(ef, sql_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)

        # Check for account_005 / user_05 in failover replica
        user_05_hits = [h for h in hits if h.matched_identifier == "user_05"]
        self.assertGreater(len(user_05_hits), 0)
        hit = user_05_hits[0]
        self.assertEqual(hit.file_id, "evidence_54")
        self.assertEqual(hit.system_id, "account_service")
        self.assertEqual(hit.resource_id, "account_005")
        self.assertEqual(hit.identifier_type, "user_id")

    def test_parse_read_replica_json_records(self):
        ef = EvidenceFile(
            file_id="evidence_05",
            file_path="evidence/databases/customer_data_read_replica_20260921.sql",
            origin="customer_data_read_replica_capture",
            captured_at=datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc),
        )
        sql_path = DATASET_DIR / ef.file_path
        hits = parse_sql_evidence(ef, sql_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)
        # Check security audit records in evidence_05
        audit_hits = [h for h in hits if "audit_record" in h.resource_id]
        self.assertGreater(len(audit_hits), 0)
        self.assertEqual(audit_hits[0].system_id, "security_service")


class TestPDFParser(unittest.TestCase):
    """Tests pdfplumber document extraction."""

    def test_parse_account_history_report(self):
        ef = EvidenceFile(
            file_id="evidence_18",
            file_path="evidence/documents/account_history_report_20260718.pdf",
            origin="account_history_service",
            captured_at=datetime(2026, 7, 18, 11, 0, 0, tzinfo=timezone.utc),
        )
        pdf_path = DATASET_DIR / ef.file_path
        hits = parse_pdf_evidence(ef, pdf_path)
        self.assertGreater(len(hits), 0)

        # Ingrid Dahl / user_18
        user_hits = [h for h in hits if h.matched_identifier == "user_18"]
        email_hits = [h for h in hits if h.matched_identifier == "ingrid.dahl@outlook.com"]
        self.assertGreater(len(user_hits), 0)
        self.assertGreater(len(email_hits), 0)
        self.assertEqual(user_hits[0].system_id, "account_service")

    def test_parse_delivery_correction_attachment(self):
        ef = EvidenceFile(
            file_id="evidence_58",
            file_path="evidence/documents/delivery_correction_attachment.pdf",
            origin="support_platform",
            captured_at=datetime(2026, 9, 12, 7, 30, 0, tzinfo=timezone.utc),
        )
        pdf_path = DATASET_DIR / ef.file_path
        hits = parse_pdf_evidence(ef, pdf_path)
        self.assertGreater(len(hits), 0)
        support_hits = [h for h in hits if "support_001" in h.matched_identifier or "support_001" in h.resource_id]
        self.assertGreater(len(support_hits), 0)


class TestJSONParser(unittest.TestCase):
    """Tests JSON records, snapshots, and service resource exports."""

    def test_parse_service_resource_export(self):
        ef = EvidenceFile(
            file_id="evidence_92",
            file_path="evidence/records/service_resource_export_20260915_114455.json",
            origin="service_resource_export",
            captured_at=datetime(2026, 9, 15, 11, 44, 55, tzinfo=timezone.utc),
        )
        json_path = DATASET_DIR / ef.file_path
        hits = parse_json_evidence(ef, json_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)

        # Check absent status code 404 profile lookup
        absent_hits = [h for h in hits if h.parsed_state == "ABSENT"]
        present_hits = [h for h in hits if h.parsed_state == "PRESENT"]
        self.assertGreater(len(absent_hits), 0)
        self.assertGreater(len(present_hits), 0)

    def test_parse_customer_export_jobs(self):
        ef = EvidenceFile(
            file_id="evidence_59",
            file_path="evidence/records/customer_export_jobs_20260914.json",
            origin="export_service",
            captured_at=datetime(2026, 9, 14, 15, 40, 0, tzinfo=timezone.utc),
        )
        json_path = DATASET_DIR / ef.file_path
        hits = parse_json_evidence(ef, json_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)
        export_hits = [h for h in hits if h.resource_id == "export_001"]
        self.assertGreater(len(export_hits), 0)
        self.assertEqual(export_hits[0].system_id, "export_service")


class TestLogParser(unittest.TestCase):
    """Tests log evidence parsing across different logging formats."""

    def test_parse_resource_lookup_trace(self):
        ef = EvidenceFile(
            file_id="evidence_94",
            file_path="evidence/logs/resource_lookup_trace_20260926_103856.log",
            origin="service_readback_logs",
            captured_at=datetime(2026, 9, 26, 10, 38, 56, tzinfo=timezone.utc),
        )
        log_path = DATASET_DIR / ef.file_path
        hits = parse_log_evidence(ef, log_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)

        # Check l.fontaine46@yahoo.com lookup
        fontaine_hits = [h for h in hits if h.matched_identifier == "l.fontaine46@yahoo.com"]
        self.assertGreater(len(fontaine_hits), 0)
        self.assertEqual(fontaine_hits[0].resource_id, "account_7566")
        self.assertEqual(fontaine_hits[0].parsed_state, "ABSENT")


class TestTXTHandoverParser(unittest.TestCase):
    """Tests pipe-delimited shift handover parsing."""

    def test_parse_customer_account_handover(self):
        ef = EvidenceFile(
            file_id="evidence_03",
            file_path="evidence/records/customer_account_handover_20261001.txt",
            origin="customer_account_service",
            captured_at=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        txt_path = DATASET_DIR / ef.file_path
        hits = parse_txt_evidence(ef, txt_path.read_text(encoding="utf-8"))
        self.assertGreater(len(hits), 0)

        # Check NOT_FOUND state
        not_found_hits = [h for h in hits if h.parsed_state == "ABSENT"]
        self.assertGreater(len(not_found_hits), 0)
        self.assertEqual(not_found_hits[0].system_id, "account_service")


class TestTemporalBoundaryFiltering(unittest.TestCase):
    """Tests case-specific audit_at cutoff boundaries."""

    def setUp(self):
        self.indexer = InvertedEvidenceIndex(DATASET_DIR)
        self.indexer.index.clear()

        # Create synthetic hits across 3 timestamps
        self.t1 = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.t2 = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.t3 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)

        hit1 = EvidenceHit(
            file_id="ev_1", file_path="p1", origin="orig", captured_at=self.t1,
            system_id="account_service", resource_id="res_1", matched_identifier="user_999",
            identifier_type="user_id", snippet="s1", full_record={}, parsed_state="PRESENT"
        )
        hit2 = EvidenceHit(
            file_id="ev_2", file_path="p2", origin="orig", captured_at=self.t2,
            system_id="account_service", resource_id="res_2", matched_identifier="user_999",
            identifier_type="user_id", snippet="s2", full_record={}, parsed_state="PRESENT"
        )
        hit3 = EvidenceHit(
            file_id="ev_3", file_path="p3", origin="orig", captured_at=self.t3,
            system_id="account_service", resource_id="res_3", matched_identifier="user_999",
            identifier_type="user_id", snippet="s3", full_record={}, parsed_state="PRESENT"
        )

        self.indexer.index["user_999"] = [hit1, hit2, hit3]
        self.indexer._is_indexed = True

    def test_exact_boundary_included(self):
        # Exact match on t2 must include t1 and t2 (<= not <)
        hits = self.indexer.get_hits_for_identifiers(["user_999"], audit_at=self.t2)
        self.assertEqual(len(hits), 2)
        self.assertEqual([h.file_id for h in hits], ["ev_1", "ev_2"])

    def test_cutoff_excludes_future_evidence(self):
        # Cutoff at t1 must only return hit1
        hits = self.indexer.get_hits_for_identifiers(["user_999"], audit_at=self.t1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].file_id, "ev_1")

    def test_no_cutoff_returns_all(self):
        hits = self.indexer.get_hits_for_identifiers(["user_999"], audit_at=None)
        self.assertEqual(len(hits), 3)


class TestRobustnessAndEdgeCases(unittest.TestCase):
    """Tests empty strings, malformed files, and missing resources."""

    def test_empty_sql_content(self):
        ef = EvidenceFile(
            file_id="ev_empty", file_path="empty.sql", origin="orig",
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        hits = parse_sql_evidence(ef, "")
        self.assertEqual(hits, [])

    def test_empty_json_content(self):
        ef = EvidenceFile(
            file_id="ev_empty", file_path="empty.json", origin="orig",
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        hits = parse_json_evidence(ef, "{}")
        self.assertEqual(hits, [])

    def test_empty_log_content(self):
        ef = EvidenceFile(
            file_id="ev_empty", file_path="empty.log", origin="orig",
            captured_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        hits = parse_log_evidence(ef, "")
        self.assertEqual(hits, [])

    def test_unknown_identifier_lookup(self):
        index = get_evidence_index(DATASET_DIR)
        hits = index.get_hits_for_identifiers(["nonexistent_user_id_12345"])
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
