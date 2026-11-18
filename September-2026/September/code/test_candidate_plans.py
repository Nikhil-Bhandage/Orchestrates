import csv
import random
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from candidate_plans import CandidateEngine
from canonical_events import normalize_events
from data_layer import DatasetIndex
from financial_timeline import build_user_timeline, simulate_payment_plan

ROOT = Path(__file__).parent.parent


def event_row(event_id, day, amount, direction="debit"):
    return {
        "event_id": event_id,
        "user_id": "synthetic",
        "event_type": "expense" if direction == "debit" else "income",
        "description": event_id,
        "category": "shopping" if direction == "debit" else "salary",
        "direction": direction,
        "amount": str(amount),
        "currency": "USD",
        "event_date": f"2026-01-{day:02d}",
        "settlement_date": f"2026-01-{day:02d}",
        "status": "settled",
        "linked_event_id": "",
        "flexibility": "fixed",
        "minimum_allowed_amount": "",
    }


def profile_row():
    return {
        "user_id": "synthetic",
        "home_currency": "USD",
        "current_available_balance": "100",
        "minimum_balance_to_keep": "20",
        "financial_priorities": "savings",
        "expense_categories_to_protect": "rent|groceries",
        "expense_categories_user_is_willing_to_reduce": "dining",
        "expense_categories_user_is_willing_to_stop": "streaming",
        "payment_methods_user_will_consider": "full_payment|partial_payment|installments",
        "max_installment_months": "6",
    }


class CandidatePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DatasetIndex.from_dataset(ROOT / "dataset")
        cls.store = __import__("canonical_events", fromlist=["normalize_dataset"]).normalize_dataset(cls.index)
        cls.engine = CandidateEngine(cls.index, cls.store)

    def test_every_evaluation_selection_is_hard_feasible_or_explicit_fallback(self):
        decisions = [self.engine.decide(row) for row in self.index.requests]
        self.assertEqual(len(decisions), 250)
        for decision in decisions:
            selected = decision.selected
            if selected.payment_method == "not_recommended":
                self.assertIsNone(selected.simulation_result)
                self.assertEqual(selected.amount_safe_to_pay, decision.baseline_safe_amount)
                continue
            self.assertIsNotNone(selected.simulation_result)
            self.assertTrue(selected.simulation_result.feasible, decision.request_id)
            self.assertTrue(Decimal("0") <= selected.amount_safe_to_pay <= Decimal(selected.metadata.get("requested_amount", "Infinity")) if selected.metadata.get("requested_amount") else True)
            for candidate in decision.feasible_candidates:
                self.assertIsNotNone(candidate.simulation_result)
                self.assertTrue(candidate.simulation_result.feasible, candidate)

    def test_installment_candidates_match_their_supplied_option_metadata(self):
        for request in self.index.requests:
            decision = self.engine.decide(request)
            for candidate in decision.feasible_candidates:
                if candidate.payment_method != "installments":
                    continue
                self.assertEqual(candidate.payment_count, int(candidate.metadata["option_number_of_payments"]))
                self.assertEqual(candidate.total_payment, Decimal(candidate.metadata["option_total_payable"]))
                self.assertEqual(
                    sum((amount for _, amount in candidate.payment_schedule), Decimal("0")),
                    candidate.total_payment,
                )

    def test_earliest_safe_date_remains_deadline_bounded(self):
        salary_store = normalize_events([event_row("salary", 20, 100, direction="credit")])
        salary_timeline = build_user_timeline(
            "synthetic",
            salary_store.by_user["synthetic"],
            profile_row(),
            ["2026-01-01"],
        )
        helper = object.__new__(CandidateEngine)
        before_deadline = {
            "request_id": "synthetic_earliest_before",
            "request_date": "2026-01-01",
            "desired_completion_date": "2026-01-30",
            "requested_amount": "100",
        }
        self.assertEqual(
            helper._earliest_full_payment(salary_timeline, before_deadline, None),
            "2026-01-20",
        )
        after_deadline = dict(before_deadline, desired_completion_date="2026-01-10")
        self.assertEqual(
            helper._earliest_full_payment(salary_timeline, after_deadline, None),
            "",
        )
        never_safe_store = normalize_events([])
        never_safe_timeline = build_user_timeline(
            "synthetic",
            never_safe_store.by_user.get("synthetic", []),
            profile_row(),
            ["2026-01-01"],
        )
        self.assertEqual(
            helper._earliest_full_payment(never_safe_timeline, after_deadline, None),
            "",
        )

    def test_wait_with_one_spending_change_for_audited_requests(self):
        expected = {
            "request_137": ("2026-01-13", ("stop:event_12572",)),
            "request_143": ("2025-06-16", ("stop:event_13140",)),
        }
        for request_id, (wait_date, changes) in expected.items():
            request = next(row for row in self.index.requests if row["request_id"] == request_id)
            decision = self.engine.decide(request)
            self.assertEqual(decision.selected.payment_method, "wait")
            self.assertEqual(decision.selected.payment_schedule[0][0], wait_date)
            self.assertEqual(decision.selected.spending_changes, changes)
            self.assertGreater(wait_date, request["request_date"])

    def test_wait_with_three_spending_changes_for_request_186(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_186")
        decision = self.engine.decide(request)
        self.assertEqual(decision.selected.payment_method, "wait")
        self.assertEqual(decision.selected.payment_schedule, (("2026-01-14", Decimal("26554")),))
        self.assertEqual(
            decision.selected.spending_changes,
            (
                "stop:event_17159",
                "reduce_to:event_17160:660",
                "reduce_to:event_17233:623.7",
            ),
        )
        self.assertGreater(decision.selected.payment_schedule[0][0], request["request_date"])

    def test_no_change_wait_remains_preferred_over_change_based_wait(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_33")
        decision = self.engine.decide(request)
        self.assertEqual(decision.selected.payment_method, "wait")
        self.assertEqual(decision.selected.spending_changes, ())
        self.assertTrue(
            any(
                candidate.payment_method == "wait" and candidate.spending_changes
                for candidate in decision.feasible_candidates
            )
        )

    def test_same_day_payment_is_not_added_as_change_based_wait(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_27")
        decision = self.engine.decide(request)
        self.assertNotEqual(decision.selected.payment_method, "wait")
        self.assertFalse(
            any(
                candidate.payment_method == "wait"
                and candidate.spending_changes
                and candidate.payment_schedule[0][0] == request["request_date"]
                for candidate in decision.feasible_candidates
            )
        )

    def test_partial_capacity_matches_integer_bruteforce_reference(self):
        random.seed(31)
        helper = object.__new__(CandidateEngine)
        for trial in range(40):
            rows = []
            for index in range(random.randint(1, 5)):
                day = random.randint(2, 18)
                direction = "credit" if random.random() < 0.25 else "debit"
                rows.append(event_row(f"event_{trial}_{index}", day, random.randint(1, 35), direction))
            store = normalize_events(rows)
            timeline = build_user_timeline(
                "synthetic",
                store.by_user["synthetic"],
                profile_row(),
                ["2026-01-01"],
            )
            request = {
                "request_id": f"synthetic_{trial}",
                "request_date": "2026-01-01",
                "desired_completion_date": "2026-01-25",
                "requested_amount": "70",
            }
            optimized = helper._maximum_first_payment(
                timeline,
                request["request_date"],
                "2026-01-20",
                Decimal("70"),
                (),
            )
            brute = Decimal("0")
            for first in range(71):
                result = simulate_payment_plan(
                    timeline,
                    [("2026-01-01", str(first)), ("2026-01-20", str(70 - first))],
                    requested_amount="70",
                )
                if result.feasible:
                    brute = Decimal(first)
            self.assertEqual(optimized, brute, trial)


if __name__ == "__main__":
    unittest.main()
