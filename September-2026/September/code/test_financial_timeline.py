from __future__ import annotations

import random
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canonical_events import normalize_events
from data_layer import DatasetIndex
from financial_timeline import (
    TimelineCatalog,
    build_user_timeline,
    get_max_safe_one_time_payment,
    simulate_payment_plan,
)


PROFILE = {
    "user_id": "user_test",
    "home_currency": "USD",
    "current_available_balance": "100",
    "minimum_balance_to_keep": "20",
    "financial_priorities": "emergency_savings",
    "expense_categories_to_protect": "rent|utilities",
    "expense_categories_user_is_willing_to_reduce": "dining|streaming",
    "expense_categories_user_is_willing_to_stop": "streaming",
    "payment_methods_user_will_consider": "full_payment|partial_payment|installments",
    "max_installment_months": "6",
}


def raw(event_id, **updates):
    value = {
        "event_id": event_id,
        "user_id": "user_test",
        "event_type": "expense",
        "description": event_id,
        "category": "shopping",
        "direction": "debit",
        "amount": "10",
        "currency": "USD",
        "event_date": "2026-01-05",
        "settlement_date": "2026-01-05",
        "status": "settled",
        "linked_event_id": "",
        "flexibility": "fixed",
        "minimum_allowed_amount": "",
    }
    value.update(updates)
    return value


def timeline(rows, request_date="2026-01-01", profile=None):
    store = normalize_events(rows)
    return build_user_timeline(
        "user_test",
        store.by_user.get("user_test", []),
        profile or PROFILE,
        [request_date],
    )


class FinancialTimelineTests(unittest.TestCase):
    def test_historical_settled_event_is_not_replayed(self):
        tl = timeline([raw("past", event_date="2025-12-01", settlement_date="2025-12-01", amount="90")])
        result = simulate_payment_plan(tl, [])
        self.assertTrue(result.feasible)
        self.assertEqual(result.ending_balance, Decimal("100"))
        self.assertEqual(result.natural_cash_flow, Decimal("0"))

    def test_future_settled_event_is_applied(self):
        tl = timeline([raw("future", amount="15", event_date="2026-01-05", settlement_date="2026-01-05")])
        result = simulate_payment_plan(tl, [])
        self.assertEqual(result.ending_balance, Decimal("85"))
        self.assertEqual(result.total_outflow, Decimal("15"))

    def test_pending_debit_is_deducted_exactly_once(self):
        tl = timeline([raw("pending", status="pending", amount="30", event_date="2026-01-03", settlement_date="2026-01-04")])
        result = simulate_payment_plan(tl, [])
        self.assertEqual(result.ending_balance, Decimal("70"))
        self.assertEqual(result.total_outflow, Decimal("30"))
        safe = get_max_safe_one_time_payment(tl, "2026-01-01", "100")
        self.assertEqual(safe.max_safe_payment, Decimal("50"))

    def test_pending_credit_is_excluded(self):
        tl = timeline([raw("refund", event_type="refund", direction="credit", status="pending", amount="50")])
        result = simulate_payment_plan(tl, [])
        self.assertEqual(result.ending_balance, Decimal("100"))
        self.assertEqual(result.total_inflow, Decimal("0"))

    def test_scheduled_salary_arrives_only_on_settlement_date(self):
        tl = timeline([raw("salary", event_type="income", category="salary", direction="credit", status="scheduled", amount="40", event_date="2026-01-03", settlement_date="2026-01-10")])
        before = simulate_payment_plan(tl, [("2026-01-05", "1")])
        self.assertEqual(before.balance_checkpoints[0].balance_after, Decimal("99"))
        after = simulate_payment_plan(tl, [("2026-01-10", "1")])
        self.assertEqual(after.balance_checkpoints[0].kind, "natural")
        self.assertEqual(after.balance_checkpoints[0].balance_after, Decimal("140"))

    def test_failed_event_has_no_cash_effect(self):
        tl = timeline([raw("failed", status="failed", amount="80")])
        self.assertEqual(simulate_payment_plan(tl, []).ending_balance, Decimal("100"))

    def test_cancelled_event_has_no_cash_effect(self):
        tl = timeline([raw("cancelled", status="cancelled", amount="80")])
        self.assertEqual(simulate_payment_plan(tl, []).ending_balance, Decimal("100"))

    def test_unrealized_investment_has_no_cash_effect(self):
        tl = timeline([raw("valuation", event_type="investment_valuation", category="investment", direction="non_cash", status="unrealized", amount="1000")])
        self.assertEqual(simulate_payment_plan(tl, []).ending_balance, Decimal("100"))

    def test_minimum_balance_violation_is_reported(self):
        tl = timeline([raw("large", amount="81")])
        result = simulate_payment_plan(tl, [])
        self.assertFalse(result.feasible)
        self.assertEqual(result.first_violation_date, "2026-01-05")
        self.assertIn("below minimum", result.first_violation_reason)
        direct = get_max_safe_one_time_payment(tl, "2026-01-01", "10")
        self.assertFalse(direct.natural_path_feasible)
        self.assertEqual(direct.first_violation_date, "2026-01-05")

    def test_payment_at_maximum_safe_amount(self):
        tl = timeline([raw("outflow", amount="10")])
        safe = get_max_safe_one_time_payment(tl, "2026-01-01", "100")
        self.assertEqual(safe.max_safe_payment, Decimal("70"))
        self.assertTrue(simulate_payment_plan(tl, [("2026-01-01", "70")]).feasible)

    def test_payment_one_unit_above_safe_amount(self):
        tl = timeline([raw("outflow", amount="10")])
        result = simulate_payment_plan(tl, [("2026-01-01", "71")])
        self.assertFalse(result.feasible)

    def test_payment_on_same_date_as_salary_salary_is_first(self):
        tl = timeline([raw("salary", event_type="income", category="salary", direction="credit", status="scheduled", amount="30", event_date="2026-01-02", settlement_date="2026-01-02")], request_date="2026-01-02")
        result = simulate_payment_plan(tl, [("2026-01-02", "60")])
        self.assertTrue(result.feasible)
        self.assertEqual([c.kind for c in result.balance_checkpoints], ["natural", "payment"])
        self.assertEqual(result.ending_balance, Decimal("70"))

    def test_multiple_same_date_events_have_deterministic_event_id_order(self):
        tl = timeline([
            raw("event_a", amount="81", event_date="2026-01-02", settlement_date="2026-01-02"),
            raw("event_b", event_type="income", category="salary", direction="credit", amount="30", event_date="2026-01-02", settlement_date="2026-01-02"),
        ], request_date="2026-01-02")
        result = simulate_payment_plan(tl, [])
        self.assertEqual([c.identifier for c in result.balance_checkpoints], ["event_a", "event_b"])
        self.assertFalse(result.feasible)

    def test_multiple_installments_and_exact_total(self):
        tl = timeline([])
        result = simulate_payment_plan(
            tl,
            [("2026-01-01", "10"), ("2026-01-10", "20"), ("2026-02-01", "30")],
            requested_amount="60",
        )
        self.assertTrue(result.feasible)
        self.assertEqual(result.total_payment, Decimal("60"))
        self.assertTrue(result.paid_amount_matches_requested)

    def test_installment_plan_wrong_total_is_invalid(self):
        tl = timeline([])
        result = simulate_payment_plan(tl, [("2026-01-01", "20")], requested_amount="21")
        self.assertFalse(result.feasible)
        self.assertFalse(result.paid_amount_matches_requested)

    def test_payment_dates_must_be_chronological(self):
        tl = timeline([])
        result = simulate_payment_plan(tl, [("2026-02-01", "10"), ("2026-01-01", "10")])
        self.assertFalse(result.feasible)
        self.assertIn("chronological", " ".join(result.violations))

    def test_distinct_exact_recurrences_do_not_suppress_each_other(self):
        rows = [
            raw("a1", description="Stream A", event_date="2025-12-01", settlement_date="2025-12-01"),
            raw("a2", description="Stream A", event_date="2025-12-15", settlement_date="2025-12-15"),
            raw("a3", description="Stream A", event_date="2025-12-29", settlement_date="2025-12-29"),
            raw("b1", description="Stream B", event_date="2025-12-15", settlement_date="2025-12-15"),
            raw("b2", description="Stream B", event_date="2025-12-29", settlement_date="2025-12-29"),
            raw("b3", description="Stream B", event_date="2026-01-12", settlement_date="2026-01-12"),
        ]
        tl = timeline(rows)
        self.assertIn("forecast:a3:2026-01-12", {entry.event_id for entry in tl.entries})
        self.assertIn("b3", {entry.event_id for entry in tl.entries})

    def test_flexible_expense_stop_applies_to_projected_instances(self):
        rows = [
            raw("stream_1", event_type="subscription", category="streaming", description="Streaming", amount="10", flexibility="stoppable", event_date="2025-11-01", settlement_date="2025-11-01"),
            raw("stream_2", event_type="subscription", category="streaming", description="Streaming", amount="10", flexibility="stoppable", event_date="2025-12-01", settlement_date="2025-12-01"),
            raw("stream_3", event_type="subscription", category="streaming", description="Streaming", amount="10", flexibility="stoppable", event_date="2026-01-01", settlement_date="2026-01-01"),
        ]
        tl = timeline(rows)
        result = simulate_payment_plan(tl, [], spending_changes="stop:stream_3")
        self.assertEqual(result.total_outflow, Decimal("0"))

    def test_flexible_expense_reduction_respects_minimum(self):
        rows = [
            raw("dining_1", category="dining", description="Dining", amount="30", flexibility="reducible", minimum_allowed_amount="15", event_date="2025-11-01", settlement_date="2025-11-01"),
            raw("dining_2", category="dining", description="Dining", amount="30", flexibility="reducible", minimum_allowed_amount="15", event_date="2025-12-01", settlement_date="2025-12-01"),
            raw("dining_3", category="dining", description="Dining", amount="30", flexibility="reducible", minimum_allowed_amount="15", event_date="2026-01-01", settlement_date="2026-01-01"),
        ]
        tl = timeline(rows)
        result = simulate_payment_plan(tl, [], spending_changes="reduce_to:dining_3:15")
        self.assertEqual(result.total_outflow, Decimal("60"))

    def test_protected_expense_cannot_be_reduced(self):
        rows = [
            raw("rent_1", category="rent", description="Rent", amount="30", flexibility="reducible", minimum_allowed_amount="10", event_date="2025-11-01", settlement_date="2025-11-01"),
            raw("rent_2", category="rent", description="Rent", amount="30", flexibility="reducible", minimum_allowed_amount="10", event_date="2025-12-01", settlement_date="2025-12-01"),
            raw("rent_3", category="rent", description="Rent", amount="30", flexibility="reducible", minimum_allowed_amount="10", event_date="2026-01-01", settlement_date="2026-01-01"),
        ]
        tl = timeline(rows)
        with self.assertRaises(ValueError):
            simulate_payment_plan(tl, [], spending_changes="reduce_to:rent_3:10")

    def test_request_date_between_events_uses_binary_boundary(self):
        tl = timeline([
            raw("before", amount="20", event_date="2025-12-31", settlement_date="2025-12-31"),
            raw("after", amount="10", event_date="2026-01-05", settlement_date="2026-01-05"),
        ])
        self.assertEqual(tl.start_index("2026-01-01"), 1)
        self.assertEqual(simulate_payment_plan(tl, []).ending_balance, Decimal("90"))

    def test_request_date_exactly_on_event_includes_event(self):
        tl = timeline([raw("same", amount="10")])
        self.assertEqual(tl.start_index("2026-01-05"), 0)
        self.assertEqual(simulate_payment_plan(tl, []).ending_balance, Decimal("90"))

    def test_suffix_minimum_calculation(self):
        tl = timeline([
            raw("one", amount="5", event_date="2026-01-02", settlement_date="2026-01-02"),
            raw("two", amount="20", event_date="2026-01-03", settlement_date="2026-01-03"),
        ], request_date="2026-01-01")
        start = tl.start_index("2026-01-01")
        self.assertEqual(tl.minimum_natural_balance_after(start, tl.after_date_index("2026-01-01")), Decimal("75"))

    def test_catalog_reuses_same_user_timeline(self):
        index = DatasetIndex.from_dataset(Path(__file__).parents[1] / "dataset")
        from canonical_events import normalize_dataset
        catalog = TimelineCatalog.from_index(index, normalize_dataset(index))
        self.assertIs(catalog.get("user_26"), catalog.get("user_26"))

    def test_optimized_one_time_amount_matches_bruteforce_randomized(self):
        random.seed(19)
        for trial in range(30):
            rows = []
            for i in range(random.randint(0, 7)):
                day = 2 + random.randint(0, 20)
                direction = "credit" if random.random() < 0.3 else "debit"
                rows.append(raw(
                    f"amount_{trial}_{i}",
                    description=f"amount-unique-{trial}-{i}",
                    direction=direction,
                    event_type="income" if direction == "credit" else "expense",
                    category="salary" if direction == "credit" else "shopping",
                    amount=str(random.randint(1, 20)),
                    event_date=f"2026-01-{day:02d}",
                    settlement_date=f"2026-01-{day:02d}",
                ))
            tl = timeline(rows)
            optimized = get_max_safe_one_time_payment(tl, "2026-01-01", "80").max_safe_payment
            brute = Decimal("0")
            for amount in range(81):
                result = simulate_payment_plan(tl, [("2026-01-01", str(amount))])
                if result.feasible:
                    brute = Decimal(amount)
            self.assertEqual(optimized, brute)

    def test_optimized_simulation_matches_bruteforce_randomized(self):
        random.seed(7)
        for trial in range(50):
            rows = []
            for i in range(random.randint(0, 8)):
                day = 2 + random.randint(0, 20)
                direction = "credit" if random.random() < 0.35 else "debit"
                rows.append(raw(
                    f"random_{trial}_{i}",
                    description=f"unique-{trial}-{i}",
                    direction=direction,
                    event_type="income" if direction == "credit" else "expense",
                    category="salary" if direction == "credit" else "shopping",
                    amount=str(random.randint(1, 30)),
                    event_date=f"2026-01-{day:02d}",
                    settlement_date=f"2026-01-{day:02d}",
                ))
            tl = timeline(rows)
            schedule = [(f"2026-01-{day:02d}", str(amount)) for day, amount in sorted(
                [(random.randint(1, 20), random.randint(0, 15)) for _ in range(random.randint(0, 3))]
            )]
            optimized = simulate_payment_plan(tl, schedule)
            balance = Decimal("100")
            minimum = Decimal("20")
            checkpoints = []
            i = tl.start_index("2026-01-01")
            natural_end = tl.end_index("2026-01-01")
            payments = list(schedule)
            p = 0
            while i < natural_end or p < len(payments):
                if i < natural_end and (p == len(payments) or tl.entries[i].effective_date <= payments[p][0]):
                    balance += tl.entries[i].net_cash_flow
                    checkpoints.append(balance)
                    i += 1
                else:
                    balance -= Decimal(payments[p][1])
                    checkpoints.append(balance)
                    p += 1
            self.assertEqual(optimized.ending_balance, balance)
            self.assertEqual(optimized.minimum_balance_seen, min([Decimal("100")] + checkpoints))
            self.assertEqual(optimized.feasible, all(value >= minimum for value in checkpoints))


if __name__ == "__main__":
    unittest.main()
