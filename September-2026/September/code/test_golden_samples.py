"""Determinism and contract regression checks for every solved sample.

This intentionally tests state reconstruction, evidence resolution, and plan
field invariants only. It does not train on or copy solved labels into the
prediction pipeline.
"""

import csv
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canonical_events import normalize_dataset
from data_layer import DatasetIndex
from evidence_resolution import EvidenceResolver, apply_evidence_to_timeline
from financial_timeline import build_user_timeline, get_max_safe_one_time_payment

ROOT = Path(__file__).parent.parent


class GoldenSampleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DatasetIndex.from_dataset(ROOT / "dataset")
        cls.store = normalize_dataset(cls.index)
        cls.resolver = EvidenceResolver(cls.index, cls.store)
        with (ROOT / "dataset/sample_requests.csv").open(encoding="utf-8-sig") as handle:
            cls.samples = list(csv.DictReader(handle))

    def _state_signature(self, sample):
        user = sample["user_id"]
        timeline = build_user_timeline(
            user,
            self.store.by_user[user],
            self.index.profiles_by_user[user],
            [sample["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        context = self.resolver.context_for_request(sample)
        timeline = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        result = get_max_safe_one_time_payment(timeline, sample["request_date"], sample["requested_amount"])
        return (
            result.max_safe_payment,
            result.natural_path_feasible,
            result.minimum_natural_balance_before_payment,
            result.minimum_natural_balance_after_payment,
            tuple((entry.event_id, entry.effective_date, entry.net_cash_flow) for entry in timeline.entries),
        )

    def test_all_25_solved_samples_are_deterministic(self):
        self.assertEqual(len(self.samples), 25)
        for sample in self.samples:
            self.assertEqual(self._state_signature(sample), self._state_signature(sample))
            amount = Decimal(sample["amount_safe_to_pay"])
            requested = Decimal(sample["requested_amount"])
            self.assertGreaterEqual(amount, Decimal("0"))
            self.assertLessEqual(amount, requested)
            self.assertIn(sample["affordability_status"], {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"})
            self.assertIn(sample["recommended_payment_method"], {"full_payment", "partial_payment", "installments", "wait", "not_recommended"})

    def test_sample_partial_plans_balance(self):
        for sample in self.samples:
            if sample["recommended_payment_method"] != "partial_payment":
                continue
            parts = sample["payment_plan"].split("|")
            self.assertEqual(len(parts), 2)
            paid = sum((Decimal(part.split(":", 1)[1]) for part in parts), Decimal("0"))
            self.assertEqual(paid, Decimal(sample["requested_amount"]))


if __name__ == "__main__":
    unittest.main()
