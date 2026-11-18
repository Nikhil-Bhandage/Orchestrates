from __future__ import annotations

import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canonical_events import NormalizationError, normalize_dataset, normalize_events
from data_layer import DatasetIndex
from image_evidence import ImageEvidenceResolver


FIELDS = {
    "event_id": "event_test",
    "user_id": "user_test",
    "event_type": "expense",
    "description": "Test event",
    "category": "shopping",
    "direction": "debit",
    "amount": "100",
    "currency": "USD",
    "event_date": "2026-01-01",
    "settlement_date": "2026-01-01",
    "status": "settled",
    "linked_event_id": "",
    "flexibility": "fixed",
    "minimum_allowed_amount": "",
}


def row(**updates):
    value = dict(FIELDS)
    value.update(updates)
    return value


class CanonicalEventTests(unittest.TestCase):
    def test_exact_duplicate_is_rejected_not_dropped(self):
        with self.assertRaises(NormalizationError):
            normalize_events([row(), copy.deepcopy(row())])

    def test_linked_events_remain_separate(self):
        parent = row(event_id="event_parent", amount="100", description="Card purchase")
        child = row(
            event_id="event_child",
            event_type="refund",
            direction="credit",
            amount="40",
            linked_event_id="event_parent",
            description="Settled card charge reversal",
        )
        store = normalize_events([parent, child])
        self.assertEqual(set(store.by_id), {"event_parent", "event_child"})
        self.assertEqual(store.by_id["event_child"].relationship, "refund_of_prior_event")
        self.assertEqual(store.by_id["event_parent"].forecast_cash_effect, Decimal("-100"))
        self.assertEqual(store.by_id["event_child"].forecast_cash_effect, Decimal("40"))

    def test_retry_after_failed_event(self):
        failed = row(event_id="event_failed", status="failed", description="Failed bill payment attempt")
        retry = row(
            event_id="event_retry",
            event_type="debt_payment",
            linked_event_id="event_failed",
            status="scheduled",
            settlement_date="2026-01-05",
            description="Scheduled bill payment retry",
        )
        store = normalize_events([failed, retry])
        self.assertFalse(store.by_id["event_failed"].forecast_eligible)
        self.assertEqual(store.by_id["event_failed"].cash_eligibility, "failed")
        self.assertTrue(store.by_id["event_retry"].forecast_eligible)
        self.assertEqual(store.by_id["event_retry"].relationship, "retry_after_failed_event")

    def test_refund_pending_vs_settled(self):
        parent = row(event_id="event_purchase")
        pending = row(
            event_id="event_pending_refund",
            event_type="refund",
            direction="credit",
            amount="25",
            status="pending",
            linked_event_id="event_purchase",
        )
        settled = row(
            event_id="event_settled_refund",
            event_type="refund",
            direction="credit",
            amount="25",
            linked_event_id="event_purchase",
        )
        store = normalize_events([parent, pending, settled])
        self.assertFalse(store.by_id["event_pending_refund"].forecast_eligible)
        self.assertEqual(store.by_id["event_pending_refund"].cash_eligibility, "pending_credit_excluded")
        self.assertTrue(store.by_id["event_settled_refund"].forecast_eligible)

    def test_cancelled_and_failed_events_are_ignored(self):
        store = normalize_events([
            row(event_id="event_cancelled", status="cancelled"),
            row(event_id="event_failed", status="failed"),
        ])
        for event in store.events:
            self.assertFalse(event.forecast_eligible)
            self.assertIsNone(event.forecast_cash_effect)

    def test_linked_possible_duplicate_pending_debit_is_excluded(self):
        parent = row(
            event_id="event_settled_parent",
            description="Card purchase",
            status="settled",
            amount="100",
            settlement_date="2026-01-01",
        )
        duplicate = row(
            event_id="event_pending_duplicate",
            description="Possible duplicate card charge",
            status="pending",
            amount="100",
            settlement_date="2026-01-02",
            linked_event_id="event_settled_parent",
        )
        store = normalize_events([parent, duplicate])
        settled = store.by_id["event_settled_parent"]
        pending = store.by_id["event_pending_duplicate"]
        self.assertEqual(settled.forecast_cash_effect, Decimal("-100"))
        self.assertTrue(settled.forecast_eligible)
        self.assertEqual(pending.relationship, "possible_duplicate_charge")
        self.assertFalse(pending.forecast_eligible)
        self.assertIsNone(pending.forecast_cash_effect)
        self.assertFalse(pending.reserve_pending_debit)
        self.assertEqual(pending.cash_eligibility, "duplicate_excluded")
        forecast_total = sum(
            event.forecast_cash_effect
            for event in store.events
            if event.forecast_eligible and event.forecast_cash_effect is not None
        )
        self.assertEqual(forecast_total, Decimal("-100"))

    def test_pending_debit_is_reserved_and_forecast(self):
        event = normalize_events([row(status="pending", amount="12.5")]).events[0]
        self.assertTrue(event.forecast_eligible)
        self.assertTrue(event.reserve_pending_debit)
        self.assertEqual(event.current_cash_effect, Decimal("0"))
        self.assertEqual(event.forecast_cash_effect, Decimal("-12.5"))
        self.assertEqual(event.cash_eligibility, "pending_debit_reserved")

    def test_pending_credit_is_not_forecast(self):
        event = normalize_events([
            row(event_type="refund", direction="credit", status="pending", amount="12.5")
        ]).events[0]
        self.assertFalse(event.forecast_eligible)
        self.assertIsNone(event.forecast_cash_effect)
        self.assertEqual(event.cash_eligibility, "pending_credit_excluded")

    def test_scheduled_salary_is_future_credit(self):
        event = normalize_events([
            row(
                event_type="income",
                category="salary",
                direction="credit",
                status="scheduled",
                amount="2500",
                settlement_date="2026-01-15",
            )
        ]).events[0]
        self.assertFalse(event.current_cash_effect)
        self.assertTrue(event.forecast_eligible)
        self.assertEqual(event.forecast_cash_effect, Decimal("2500"))
        self.assertEqual(event.effective_date, "2026-01-15")

    def test_unrealized_investment_is_non_cash(self):
        event = normalize_events([
            row(
                event_type="investment_valuation",
                category="investment",
                direction="non_cash",
                status="unrealized",
                amount="9999",
            )
        ]).events[0]
        self.assertFalse(event.forecast_eligible)
        self.assertEqual(event.cash_eligibility, "non_cash")
        self.assertIsNone(event.forecast_cash_effect)

    def test_image_backed_blank_amount_is_resolved_semantically(self):
        index = DatasetIndex.from_dataset(Path(__file__).parents[1] / "dataset")
        store = normalize_dataset(index)
        event = store.by_id["event_253"]
        self.assertEqual(event.amount, Decimal("4365000"))
        self.assertEqual(event.amount_source, "image_evidence")
        self.assertEqual(event.evidence_image_id, "image_01")
        self.assertTrue(event.forecast_eligible)
        self.assertEqual(len(store.image_evidence_by_event), 16)
        self.assertEqual(len(ImageEvidenceResolver().cache), 0)

    def test_legitimate_recurring_events_remain_distinct_and_sorted(self):
        index = DatasetIndex.from_dataset(Path(__file__).parents[1] / "dataset")
        store = normalize_dataset(index)
        recurring = [
            e for e in store.by_user["user_26"]
            if e.category == "streaming" and e.event_type == "subscription"
        ]
        self.assertEqual(len(recurring), 5)
        self.assertEqual(len({e.event_id for e in recurring}), 5)
        self.assertEqual(
            [e.effective_date for e in recurring],
            sorted(e.effective_date for e in recurring),
        )


if __name__ == "__main__":
    unittest.main()
