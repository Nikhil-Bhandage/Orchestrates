"""
test_intent_classifier.py — Test suite for Milestone 2 Deletion Intent Classifier.
Validates deterministic classification, multilingual detection, batching logic,
and Gemini API integration (skipped if GEMINI_API_KEY is not set).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"

# Ensure code/ is on sys.path for sibling imports
sys.path.insert(0, str(REPO_ROOT / "code"))

from data_loader import load_all_datasets
from intent_classifier import (
    IntentClassificationResult,
    LLMUsageStats,
    _build_batch_prompt,
    classify_deterministic,
    classify_intents,
    classify_single,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"


class TestSampleCasesClassification(unittest.TestCase):
    """Verifies that all 32 sample cases in sample_deletion_requests.csv classify as DELETION_REQUEST."""

    @classmethod
    def setUpClass(cls):
        bundle = load_all_datasets(DATASET_DIR)
        cls.samples = bundle.sample_requests

    def test_all_sample_cases_are_deletion_requests(self):
        self.assertEqual(len(self.samples), 32)
        for s in self.samples:
            result = classify_deterministic(s.case_id, s.request_text)
            self.assertEqual(
                result.intent,
                "DELETION_REQUEST",
                f"Sample {s.case_id} failed to classify as DELETION_REQUEST: '{s.request_text}'",
            )
            self.assertGreaterEqual(result.confidence, 0.80)
            self.assertTrue(result.is_deletion_authorized)


class TestNonDeletionCases(unittest.TestCase):
    """Verifies that known non-deletion requests (cases 533-542) classify as NOT_APPLICABLE."""

    @classmethod
    def setUpClass(cls):
        bundle = load_all_datasets(DATASET_DIR)
        cls.eval_requests = {r.case_id: r for r in bundle.deletion_requests}

    def test_known_non_deletion_cases(self):
        non_del_ids = [f"case_{i}" for i in range(533, 543)]
        for cid in non_del_ids:
            self.assertIn(cid, self.eval_requests, f"{cid} missing from evaluation set")
            req = self.eval_requests[cid]
            result = classify_deterministic(req.case_id, req.request_text)
            self.assertEqual(
                result.intent,
                "NOT_APPLICABLE",
                f"{cid} failed to classify as NOT_APPLICABLE: '{req.request_text}'",
            )
            self.assertFalse(result.is_deletion_authorized)
            self.assertIn("Non-deletion intent detected", result.reasoning_note)


class TestMultilingualClassification(unittest.TestCase):
    """Tests multilingual detection across various languages."""

    def test_french_deletion(self):
        text = "Je demande la suppression définitive du compte associé à cette adresse e-mail."
        result = classify_deterministic("case_fr", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_spanish_deletion(self):
        text = "Solicito la eliminación permanente de la cuenta asociada a este correo."
        result = classify_deterministic("case_es", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_portuguese_deletion(self):
        text = "Solicito a exclusão permanente da conta associada a este e-mail."
        result = classify_deterministic("case_pt", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_japanese_deletion(self):
        text = "このメールアドレスに関連するアカウントの完全な削除を依頼します。"
        result = classify_deterministic("case_ja", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_korean_deletion(self):
        text = "이 이메일 주소에 연결된 계정의 영구 삭제를 요청합니다."
        result = classify_deterministic("case_ko", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_german_deletion(self):
        text = "Bitte um vollständige Löschung meines Benutzerkontos und aller Daten."
        result = classify_deterministic("case_de", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")

    def test_italian_deletion(self):
        text = "Richiedo la cancellazione definitiva del mio account e dei dati associati."
        result = classify_deterministic("case_it", text)
        self.assertEqual(result.intent, "DELETION_REQUEST")


class TestSyntheticEdgeCases(unittest.TestCase):
    """Tests edge cases: empty strings, SAR requests, rectification, opt-outs."""

    def test_empty_request(self):
        res = classify_deterministic("empty_1", "")
        self.assertEqual(res.intent, "NOT_APPLICABLE")

    def test_whitespace_request(self):
        res = classify_deterministic("ws_1", "   \t\n  ")
        self.assertEqual(res.intent, "NOT_APPLICABLE")

    def test_subject_access_request(self):
        text = "I would like to download my account information in a portable format. Please keep the account active."
        res = classify_deterministic("sar_1", text)
        self.assertEqual(res.intent, "NOT_APPLICABLE")

    def test_data_rectification(self):
        text = "My phone number is out of date. Please replace it with 555-0199 and do not delete my account."
        res = classify_deterministic("rect_1", text)
        self.assertEqual(res.intent, "NOT_APPLICABLE")

    def test_marketing_opt_out(self):
        text = "Please stop the promotional emails. I still need the account, so I am not asking for deletion."
        res = classify_deterministic("opt_1", text)
        self.assertEqual(res.intent, "NOT_APPLICABLE")

    def test_login_help(self):
        text = "I can't access my profile and need help resetting the login. Do not close the account."
        res = classify_deterministic("login_1", text)
        self.assertEqual(res.intent, "NOT_APPLICABLE")


class TestBatchingAndPromptConstruction(unittest.TestCase):
    """Tests batch JSON building and schema compliance."""

    def test_prompt_formatting(self):
        cases = [
            {"case_id": "c1", "request_text": "Please delete my account."},
            {"case_id": "c2", "request_text": "Keep my account active."},
        ]
        prompt = _build_batch_prompt(cases)
        self.assertIn('"case_id": "c1"', prompt)
        self.assertIn('"case_id": "c2"', prompt)
        self.assertIn("DELETION_REQUEST", prompt)
        self.assertIn("NOT_APPLICABLE", prompt)


class TestClassifyIntentsOrchestrator(unittest.TestCase):
    """Tests the high-level classify_intents interface on collections."""

    @classmethod
    def setUpClass(cls):
        bundle = load_all_datasets(DATASET_DIR)
        cls.samples = bundle.sample_requests

    def test_classify_all_samples_batch(self):
        results, stats = classify_intents(self.samples)
        self.assertEqual(len(results), 32)
        for s in self.samples:
            self.assertIn(s.case_id, results)
            self.assertEqual(results[s.case_id].intent, "DELETION_REQUEST")

    def test_classify_single_wrapper(self):
        res = classify_single("c_test", "Please delete my account immediately.")
        self.assertEqual(res.intent, "DELETION_REQUEST")


class TestGeminiLiveAPI(unittest.TestCase):
    """Optional live test with Gemini API if GEMINI_API_KEY is configured in environment."""

    def setUp(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            self.skipTest("GEMINI_API_KEY environment variable not set; skipping live LLM test.")

    def test_live_batch_classification(self):
        test_cases = [
            {"case_id": "c_del", "request_text": "Please permanently remove my account and personal details."},
            {"case_id": "c_keep", "request_text": "Please send me a copy of my invoices. Do not delete my account."},
        ]
        results, stats = classify_intents(test_cases, api_key=self.api_key, force_llm=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(results["c_del"].intent, "DELETION_REQUEST")
        self.assertEqual(results["c_keep"].intent, "NOT_APPLICABLE")
        self.assertGreater(stats.call_count, 0)
        self.assertGreater(stats.input_tokens, 0)


if __name__ == "__main__":
    unittest.main()
