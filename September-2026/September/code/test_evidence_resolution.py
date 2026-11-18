import csv
import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from canonical_events import normalize_dataset
from data_layer import DatasetIndex
from evidence_resolution import EvidenceResolver, _facts_from_message, apply_evidence_to_timeline
from financial_timeline import build_user_timeline


ROOT = Path(__file__).parent.parent


class EvidenceResolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = DatasetIndex.from_dataset(ROOT / "dataset")
        cls.store = normalize_dataset(cls.index)
        cls.resolver = EvidenceResolver(cls.index, cls.store)
        with (ROOT / "dataset/sample_requests.csv").open(encoding="utf-8-sig") as handle:
            cls.samples = {row["request_id"]: row for row in csv.DictReader(handle)}

    def test_all_sample_contexts_are_indexed_and_lossless(self):
        for request_id, request in self.samples.items():
            context = self.resolver.context_for_request(request)
            self.assertEqual(context.request["request_id"], request_id)
            self.assertEqual(len(context.event_ids), len(set(context.event_ids)))
            self.assertTrue(all(message["user_id"] == request["user_id"] for message in context.messages))

    def test_image_cache_is_reused_for_all_image_linked_sample_events(self):
        contexts = [self.resolver.context_for_request(request) for request in self.samples.values()]
        sample_evidence_ids = {
            event_id
            for context in contexts
            for event_id in context.image_evidence
        }
        self.assertEqual(sample_evidence_ids, {"event_253", "event_1442", "event_1545", "event_1700", "event_1786"})
        all_evidence_ids = set(self.store.image_evidence_by_event)
        self.assertEqual(len(all_evidence_ids), 16)
        self.assertTrue(all(evidence.amount > 0 for evidence in self.store.image_evidence_by_event.values()))

    def test_english_regular_salary_and_one_time_arrears_keep_regular_amount(self):
        message = {
            "message_id": "message_test_english_arrears",
            "source_type": "employer",
            "message_text": (
                "Your regular salary for the next payroll is EUR 1452. "
                "The same payroll includes a one-time arrears adjustment of EUR 653.40."
            ),
            "sent_at": "2024-06-01T09:30:00Z",
        }
        facts = _facts_from_message(message)
        self.assertEqual(
            [(fact.fact_type, fact.value, fact.currency) for fact in facts],
            [("payroll_amount", "1452", "EUR")],
        )

    def test_indonesian_regular_salary_and_one_time_arrears_keep_regular_amount(self):
        message = {
            "message_id": "message_test_indonesian_arrears",
            "source_type": "employer",
            "message_text": (
                "Gaji rutin Anda untuk penggajian berikutnya adalah IDR 21090000. "
                "Penggajian yang sama mencakup penyesuaian tunggakan satu kali sebesar IDR 9490500."
            ),
            "sent_at": "2024-03-01T09:30:00Z",
        }
        facts = _facts_from_message(message)
        self.assertEqual(
            [(fact.fact_type, fact.value, fact.currency) for fact in facts],
            [("payroll_amount", "21090000", "IDR")],
        )

    def test_regular_salary_remains_selected_recurring_payroll_amount(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_28")
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        salary = [
            entry for entry in adjusted.entries
            if entry.event.category == "salary" and entry.effective_date >= request["request_date"]
        ]
        self.assertTrue(salary)
        self.assertTrue(all(entry.event.amount == Decimal("1452") for entry in salary))
        self.assertNotIn(Decimal("653.40"), {entry.event.amount for entry in salary})

    def test_settled_arrears_event_is_counted_exactly_once(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_28")
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        arrears = [entry for entry in timeline.entries if entry.event_id == "event_2508"]
        self.assertEqual(len(arrears), 1)
        self.assertEqual(arrears[0].event.amount, Decimal("653.4"))
        self.assertEqual(arrears[0].cash_flow, Decimal("653.4"))
        adjusted_arrears = [entry for entry in apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key).entries if entry.event_id == "event_2508"]
        self.assertEqual(len(adjusted_arrears), 1)
        self.assertEqual(adjusted_arrears[0].cash_flow, Decimal("653.4"))

    def test_one_time_arrears_cannot_overwrite_recurring_salary(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_163")
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        future_salary = [
            entry for entry in adjusted.entries
            if entry.event.category == "salary" and entry.effective_date >= request["request_date"]
        ]
        self.assertTrue(future_salary)
        self.assertTrue(all(entry.event.amount == Decimal("30400000") for entry in future_salary))
        self.assertNotIn(Decimal("13680000"), {entry.event.amount for entry in future_salary})

    def test_untrusted_claims_do_not_become_cash_facts(self):
        for request_id in ("request_10", "request_20", "request_22", "request_23", "request_24"):
            context = self.resolver.context_for_request(self.samples[request_id])
            self.assertFalse(any(fact.fact_type == "payroll_amount" for fact in context.resolved_facts))
        self.assertIn("payout_pending", {fact.fact_type for fact in self.resolver.context_for_request(self.samples["request_10"]).resolved_facts})
        self.assertIn("investment_unrealized", {fact.fact_type for fact in self.resolver.context_for_request(self.samples["request_22"]).resolved_facts})

    def test_payroll_amendment_is_a_fact_not_a_new_event(self):
        request = self.samples["request_02"]
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        self.assertEqual(len(timeline.entries), len(adjusted.entries))
        self.assertEqual(
            {entry.event_id for entry in timeline.entries},
            {entry.event_id for entry in adjusted.entries},
        )
        self.assertIn("payroll_amount", {fact.fact_type for fact in context.resolved_facts})

    def test_payroll_amendment_updates_projected_cash_effect(self):
        request = self.samples["request_08"]
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        amended = [
            entry for entry in adjusted.entries
            if entry.event.category == "salary" and entry.effective_date >= request["request_date"]
        ]
        self.assertTrue(amended)
        self.assertEqual(amended[0].event.amount, Decimal("1422.85"))
        self.assertEqual(amended[0].cash_flow, Decimal("1422.85"))
        self.assertEqual(amended[0].event.forecast_cash_effect, Decimal("1422.85"))

    def test_confirmed_salary_evidence_materializes_missing_future_salary(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_32")
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        self.assertFalse([
            entry for entry in timeline.entries
            if entry.event.category == "salary" and entry.effective_date >= request["request_date"]
        ])
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        confirmed = [
            entry for entry in adjusted.entries
            if entry.projection_kind == "evidence_confirmed"
        ]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].effective_date, "2025-02-15")
        self.assertEqual(confirmed[0].event.amount, Decimal("54120"))
        self.assertEqual(confirmed[0].cash_flow, Decimal("54120"))

    def test_remaining_salary_termination_preserves_primary_stream(self):
        request = next(row for row in self.index.requests if row["request_id"] == "request_42")
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        future = [
            entry for entry in adjusted.entries
            if entry.event.category == "salary" and entry.effective_date >= request["request_date"]
        ]
        primary = [entry for entry in future if "primary household salary" in entry.event.description.lower()]
        secondary = [entry for entry in future if "second household income" in entry.event.description.lower()]
        self.assertTrue(primary)
        self.assertTrue(secondary)
        self.assertTrue(all(entry.event.amount == Decimal("148000") for entry in primary))
        self.assertTrue(all(entry.cash_flow == Decimal("148000") for entry in primary))
        self.assertTrue(all(entry.cash_flow == Decimal("0") for entry in secondary))

    def test_payroll_date_replacement_materializes_missing_future_salary(self):
        request = self.samples["request_07"]
        context = self.resolver.context_for_request(request)
        timeline = build_user_timeline(
            request["user_id"],
            self.store.by_user[request["user_id"]],
            self.index.profiles_by_user[request["user_id"]],
            [request["request_date"]],
            exchange_rates=self.index.exchange_rates_by_key,
        )
        adjusted = apply_evidence_to_timeline(timeline, context, self.index.exchange_rates_by_key)
        confirmed = [
            entry for entry in adjusted.entries
            if entry.projection_kind == "evidence_confirmed"
        ]
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].effective_date, "2024-09-23")
        self.assertEqual(confirmed[0].event.amount, Decimal("149000"))
        self.assertEqual(confirmed[0].cash_flow, Decimal("149000"))

    def test_actual_request_context_uses_dataset_request_index(self):
        request_id = self.index.requests[0]["request_id"]
        context = self.resolver.context(request_id)
        self.assertEqual(context.request["request_id"], request_id)


if __name__ == "__main__":
    unittest.main()
