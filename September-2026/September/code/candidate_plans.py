"""Candidate generation, hard validation, and deterministic plan ranking.

This layer does not alter the financial simulator. It treats the simulator as a
feasibility oracle and keeps all recommendation choices deterministic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from itertools import combinations
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from canonical_events import CanonicalEventStore
from data_layer import DatasetIndex, Row
from evidence_resolution import EvidenceResolver, RequestContext, apply_evidence_to_timeline
from financial_timeline import (
    MaxSafePaymentResult,
    SimulationResult,
    TimelineCatalog,
    TimelineEntry,
    UserTimeline,
    build_user_timeline,
    get_max_safe_one_time_payment,
    simulate_payment_plan,
)

ZERO = Decimal("0")
METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}


@dataclass(frozen=True)
class CandidatePlan:
    request_id: str
    payment_method: str
    payment_schedule: Tuple[Tuple[str, Decimal], ...]
    total_payment: Decimal
    amount_safe_to_pay: Decimal
    completion_date: str
    spending_changes: Tuple[str, ...]
    total_payment_cost: Decimal
    rationale_codes: Tuple[str, ...]
    metadata: Mapping[str, str]
    simulation_result: Optional[SimulationResult] = None

    @property
    def option_id(self) -> str:
        return self.metadata.get("payment_option_id", "")

    @property
    def payment_count(self) -> int:
        return len(self.payment_schedule)

    @property
    def start_date(self) -> str:
        return self.payment_schedule[0][0] if self.payment_schedule else "9999-12-31"


@dataclass(frozen=True)
class CandidateDecision:
    request_id: str
    selected: CandidatePlan
    feasible_candidates: Tuple[CandidatePlan, ...]
    rejection_counts: Mapping[str, int]
    baseline_safe_amount: Decimal
    earliest_full_payment_date: str
    context: RequestContext

    @property
    def affordability_status(self) -> str:
        candidate = self.selected
        if candidate.payment_method == "not_recommended":
            return "not_affordable"
        if candidate.payment_method == "wait":
            return "affordable_later"
        if candidate.payment_method == "full_payment" and candidate.start_date == candidate.metadata.get("request_date", "") and not candidate.spending_changes:
            return "affordable_now"
        return "affordable_with_plan"


@dataclass(frozen=True)
class _Action:
    target_event_id: str
    token: str
    category: str


class CandidateEngine:
    """Build and rank plans for one request at a time."""

    def __init__(
        self,
        index: DatasetIndex,
        store: CanonicalEventStore,
        catalog: Optional[TimelineCatalog] = None,
    ) -> None:
        self.index = index
        self.store = store
        self.catalog = catalog or TimelineCatalog.from_index(index, store)
        self.evidence = EvidenceResolver(index, store)

    def decide(self, request: Row) -> CandidateDecision:
        context = self.evidence.context_for_request(request)
        if request["user_id"] in self.catalog.by_user:
            base_timeline = self.catalog.get(request["user_id"])
        else:
            base_timeline = build_user_timeline(
                request["user_id"],
                self.store.by_user[request["user_id"]],
                self.index.profiles_by_user[request["user_id"]],
                [request["request_date"]],
                exchange_rates=self.index.exchange_rates_by_key,
            )
        timeline = apply_evidence_to_timeline(base_timeline, context, self.index.exchange_rates_by_key)
        requested = Decimal(request["requested_amount"])
        request_date = request["request_date"]
        deadline = request["desired_completion_date"]
        baseline_result = get_max_safe_one_time_payment(timeline, request_date, requested)
        baseline_safe = baseline_result.max_safe_payment
        earliest = self._earliest_full_payment(timeline, request, None)
        feasible: list[CandidatePlan] = []
        rejections: Counter[str] = Counter()

        def add(candidate: Optional[CandidatePlan]) -> None:
            if candidate is None:
                return
            reason = self._hard_rejection(candidate, timeline, request)
            if reason:
                rejections[reason] += 1
            elif not any(self._same_candidate(candidate, existing) for existing in feasible):
                feasible.append(candidate)

        changesets = self._change_sets(timeline)
        for changes in changesets:
            add(self._full_payment_candidate(timeline, request, changes, baseline_safe))
            for option in self.index.options_by_request.get(request["request_id"], []):
                if option["payment_method"] == "installments":
                    add(self._installment_candidate(timeline, request, option, changes, baseline_safe))
            add(self._partial_candidate(timeline, request, changes))

        # Preserve the no-change wait candidate, then consider only genuinely
        # deferred waits that use an otherwise valid spending-change set.
        wait_date = self._earliest_full_payment(timeline, request, None)
        if wait_date:
            add(self._wait_candidate(timeline, request, wait_date, baseline_safe))
        for changes in changesets:
            if not changes:
                continue
            wait_date = self._earliest_full_payment(timeline, request, changes)
            if wait_date and wait_date > request_date:
                add(self._wait_candidate(timeline, request, wait_date, baseline_safe, changes))

        if feasible:
            selected = min(feasible, key=self._ranking_key)
        else:
            selected = CandidatePlan(
                request_id=request["request_id"],
                payment_method="not_recommended",
                payment_schedule=(),
                total_payment=ZERO,
                # amount_safe_to_pay is a state field, not a recommendation
                # field. It remains the no-change safe amount even when no
                # eligible full plan survives the hard constraints.
                amount_safe_to_pay=baseline_safe,
                completion_date="",
                spending_changes=(),
                total_payment_cost=ZERO,
                rationale_codes=("not_affordable",),
                metadata={"request_date": request_date},
                simulation_result=None,
            )
        return CandidateDecision(
            request_id=request["request_id"],
            selected=selected,
            feasible_candidates=tuple(sorted(feasible, key=self._ranking_key)),
            rejection_counts=dict(rejections),
            baseline_safe_amount=baseline_safe,
            earliest_full_payment_date=earliest,
            context=context,
        )

    def _full_payment_candidate(
        self,
        timeline: UserTimeline,
        request: Row,
        changes: Tuple[str, ...],
        baseline_safe: Decimal,
    ) -> Optional[CandidatePlan]:
        request_id = request["request_id"]
        request_date = request["request_date"]
        option = next(
            (
                row for row in self.index.options_by_request.get(request_id, [])
                if row["payment_method"] == "full_payment"
                and Decimal(row["payment_amount"]) == Decimal(request["requested_amount"])
                and row["first_payment_date"] == request_date
            ),
            None,
        )
        if option is None:
            return None
        requested = Decimal(request["requested_amount"])
        simulation = simulate_payment_plan(
            timeline,
            [(request_date, requested)],
            spending_changes=changes or None,
            requested_amount=requested,
        )
        return CandidatePlan(
            request_id=request_id,
            payment_method="full_payment",
            payment_schedule=((request_date, requested),),
            total_payment=requested,
            amount_safe_to_pay=requested if not changes else baseline_safe,
            completion_date=request_date,
            spending_changes=changes,
            total_payment_cost=requested,
            rationale_codes=("sufficient_balance",) if not changes else ("spending_change_required",),
            metadata={"payment_option_id": option["payment_option_id"], "request_date": request_date},
            simulation_result=simulation,
        )

    def _installment_candidate(
        self,
        timeline: UserTimeline,
        request: Row,
        option: Row,
        changes: Tuple[str, ...],
        baseline_safe: Decimal,
    ) -> Optional[CandidatePlan]:
        requested = Decimal(request["requested_amount"])
        count = int(option["number_of_payments"])
        frequency = int(option["payment_frequency_days"])
        first = date.fromisoformat(option["first_payment_date"])
        schedule = tuple(
            (
                (first + timedelta(days=index * frequency)).isoformat(),
                Decimal(option["payment_amount"]),
            )
            for index in range(count)
        )
        total_cost = Decimal(option["total_payable_amount"])
        simulation = simulate_payment_plan(
            timeline,
            schedule,
            spending_changes=changes or None,
            requested_amount=total_cost,
        )
        return CandidatePlan(
            request_id=request["request_id"],
            payment_method="installments",
            payment_schedule=schedule,
            total_payment=total_cost,
            amount_safe_to_pay=baseline_safe,
            completion_date=schedule[-1][0],
            spending_changes=changes,
            total_payment_cost=total_cost,
            rationale_codes=("installment_preferred",) if not changes else ("installment_preferred", "spending_change_required"),
            metadata={
                "payment_option_id": option["payment_option_id"],
                "request_date": request["request_date"],
                "requested_amount": str(requested),
                "option_total_payable": option["total_payable_amount"],
                "option_payment_amount": option["payment_amount"],
                "option_number_of_payments": option["number_of_payments"],
                "option_first_payment_date": option["first_payment_date"],
                "option_frequency_days": option["payment_frequency_days"],
            },
            simulation_result=simulation,
        )

    def _partial_candidate(
        self,
        timeline: UserTimeline,
        request: Row,
        changes: Tuple[str, ...],
    ) -> Optional[CandidatePlan]:
        if request["allows_partial_payment"].lower() != "true":
            return None
        if "partial_payment" not in timeline.policy.payment_methods:
            return None
        requested = Decimal(request["requested_amount"])
        deadline = request["desired_completion_date"]
        best: Optional[CandidatePlan] = None
        for second_date in self._payment_dates(timeline, request):
            if second_date <= request["request_date"] or second_date > deadline:
                continue
            first_amount = self._maximum_first_payment(timeline, request["request_date"], second_date, requested, changes)
            if first_amount <= ZERO or first_amount >= requested:
                continue
            remainder = requested - first_amount
            schedule = ((request["request_date"], first_amount), (second_date, remainder))
            simulation = simulate_payment_plan(
                timeline,
                schedule,
                spending_changes=changes or None,
                requested_amount=requested,
            )
            candidate = CandidatePlan(
                request_id=request["request_id"],
                payment_method="partial_payment",
                payment_schedule=schedule,
                total_payment=requested,
                amount_safe_to_pay=first_amount,
                completion_date=second_date,
                spending_changes=changes,
                total_payment_cost=requested,
                rationale_codes=("minimum_balance_constraint", "deadline_constraint") if not changes else ("minimum_balance_constraint", "spending_change_required"),
                metadata={"request_date": request["request_date"]},
                simulation_result=simulation,
            )
            if simulation.feasible and (best is None or self._partial_key(candidate) < self._partial_key(best)):
                best = candidate
        return best

    def _wait_candidate(
        self,
        timeline: UserTimeline,
        request: Row,
        wait_date: str,
        baseline_safe: Decimal,
        changes: Tuple[str, ...] = (),
    ) -> CandidatePlan:
        requested = Decimal(request["requested_amount"])
        simulation = simulate_payment_plan(
            timeline,
            [(wait_date, requested)],
            spending_changes=changes or None,
            requested_amount=requested,
        )
        rationale_codes = ("waiting_for_income", "minimum_balance_constraint")
        if changes:
            rationale_codes += ("spending_change_required",)
        return CandidatePlan(
            request_id=request["request_id"],
            payment_method="wait",
            payment_schedule=((wait_date, requested),),
            total_payment=requested,
            amount_safe_to_pay=baseline_safe,
            completion_date=wait_date,
            spending_changes=changes,
            total_payment_cost=requested,
            rationale_codes=rationale_codes,
            metadata={"request_date": request["request_date"]},
            simulation_result=simulation,
        )

    def _earliest_full_payment(
        self,
        timeline: UserTimeline,
        request: Row,
        changes: Optional[Tuple[str, ...]],
    ) -> str:
        requested = Decimal(request["requested_amount"])
        deadline = request["desired_completion_date"]
        for day in self._payment_dates(timeline, request):
            if day > deadline:
                break
            result = simulate_payment_plan(
                timeline,
                [(day, requested)],
                spending_changes=changes or None,
                requested_amount=requested,
            )
            if result.feasible:
                return day
        return ""

    def _payment_dates(self, timeline: UserTimeline, request: Row) -> Tuple[str, ...]:
        start = date.fromisoformat(request["request_date"])
        horizon_end = date.fromisoformat(timeline.forecast_end)
        deadline = date.fromisoformat(request["desired_completion_date"])
        end = min(horizon_end, deadline)
        dates = {start.isoformat(), end.isoformat()}
        for entry in timeline.entries:
            event_day = date.fromisoformat(entry.effective_date)
            if start <= event_day <= end:
                dates.add(event_day.isoformat())
                next_day = event_day + timedelta(days=1)
                if next_day <= end:
                    dates.add(next_day.isoformat())
        return tuple(sorted(dates))

    def _maximum_first_payment(
        self,
        timeline: UserTimeline,
        request_date: str,
        second_date: str,
        requested: Decimal,
        changes: Tuple[str, ...],
    ) -> Decimal:
        # Before the second payment, increasing the first payment by x lowers
        # every intervening balance by x. Therefore the exact maximum x is the
        # minimum natural/adjusted balance before the second payment minus the
        # user's minimum, capped by the requested amount.
        from financial_timeline import _adjusted_net

        flows = timeline.net
        if changes:
            from financial_timeline import _parse_changes, _adjusted_net
            parsed = _parse_changes(timeline, changes)
            flows = _adjusted_net(timeline, parsed)
        start = timeline.start_index(request_date)
        second_after = timeline.after_date_index(second_date)
        minimum = timeline.policy.starting_balance
        running = ZERO
        for index in range(start, second_after):
            running += flows[index]
            minimum = min(minimum, timeline.policy.starting_balance + running)
        maximum = min(requested, max(ZERO, minimum - timeline.policy.minimum_balance))
        if maximum <= ZERO:
            return ZERO
        # The total requested payment after the second date is independent of
        # how the amount is split. If even a zero first payment cannot complete
        # safely, no partial split is feasible; this avoids accepting a
        # prefix-only capacity that ignores the final-payment boundary.
        zero_first = simulate_payment_plan(
            timeline,
            [(request_date, ZERO), (second_date, requested)],
            spending_changes=changes or None,
            requested_amount=requested,
        )
        if not zero_first.feasible:
            return ZERO
        maximum_result = simulate_payment_plan(
            timeline,
            [(request_date, maximum), (second_date, requested - maximum)],
            spending_changes=changes or None,
            requested_amount=requested,
        )
        if maximum_result.feasible:
            return maximum
        # Decimal amounts are not unit-enumerated. This defensive binary search
        # is over the mathematically monotone prefix capacity only and is used
        # when a simulator boundary differs from the closed-form minimum.
        low, high = ZERO, maximum
        for _ in range(80):
            middle = (low + high) / Decimal("2")
            result = simulate_payment_plan(
                timeline,
                [(request_date, middle), (second_date, requested - middle)],
                spending_changes=changes or None,
                requested_amount=requested,
            )
            if result.feasible:
                low = middle
            else:
                high = middle
        return low

    def _change_sets(self, timeline: UserTimeline) -> Tuple[Tuple[str, ...], ...]:
        actions_by_target: dict[str, list[_Action]] = {}
        grouped: dict[Tuple[int, ...], list[str]] = {}
        for target, indexes in timeline.change_index.items():
            grouped.setdefault(tuple(indexes), []).append(target)
        for indexes, targets in grouped.items():
            target = max(
                targets,
                key=lambda event_id: (timeline.entries[indexes[0]].effective_date, event_id),
            )
            event = timeline.entries[indexes[0]].event
            actions: list[_Action] = []
            if event.category in timeline.policy.stoppable_categories and event.flexibility in {"stoppable", "reducible_or_stoppable"}:
                actions.append(_Action(target, f"stop:{target}", event.category))
            if event.category in timeline.policy.reducible_categories and event.flexibility in {"reducible", "reducible_or_stoppable"}:
                minimum = event.minimum_allowed_amount or ZERO
                actions.append(_Action(target, f"reduce_to:{target}:{minimum}", event.category))
            if actions:
                actions_by_target[target] = actions
        targets = sorted(actions_by_target)
        result: list[Tuple[str, ...]] = [()]
        for count in range(1, min(3, len(targets)) + 1):
            for selected_targets in combinations(targets, count):
                for choices in self._product_actions([actions_by_target[target] for target in selected_targets]):
                    result.append(tuple(action.token for action in choices))
        return tuple(result)

    @staticmethod
    def _product_actions(groups: Sequence[Sequence[_Action]]) -> Iterable[Tuple[_Action, ...]]:
        if not groups:
            yield ()
            return
        for action in groups[0]:
            for tail in CandidateEngine._product_actions(groups[1:]):
                yield (action,) + tail

    @staticmethod
    def _same_candidate(left: CandidatePlan, right: CandidatePlan) -> bool:
        return (
            left.payment_method == right.payment_method
            and left.payment_schedule == right.payment_schedule
            and left.spending_changes == right.spending_changes
            and left.option_id == right.option_id
        )

    @staticmethod
    def _partial_key(candidate: CandidatePlan):
        return (candidate.completion_date, -candidate.amount_safe_to_pay)

    @staticmethod
    def _ranking_key(candidate: CandidatePlan):
        # The problem statement's hierarchy is intentionally represented as a
        # lexicographic tuple, not a weighted score.
        return (
            0,  # every candidate reaching this point meets the deadline
            0 if not candidate.spending_changes else 1,
            candidate.total_payment_cost,
            candidate.start_date,
            candidate.payment_count,
            candidate.option_id or "~",
            candidate.payment_method,
        )

    @staticmethod
    def _hard_rejection(candidate: CandidatePlan, timeline: UserTimeline, request: Row) -> str:
        if candidate.payment_method not in METHODS:
            return "invalid_payment_method"
        preferences = timeline.policy.payment_methods
        if candidate.payment_method in {"full_payment", "partial_payment", "installments"} and candidate.payment_method not in preferences:
            return "payment_preference_conflict"
        if candidate.payment_method == "wait" and "full_payment" not in preferences:
            return "wait_requires_full_payment_preference"
        requested = Decimal(request["requested_amount"])
        if not ZERO <= candidate.amount_safe_to_pay <= requested:
            return "amount_out_of_bounds"
        if candidate.payment_schedule:
            if any(amount < ZERO for _, amount in candidate.payment_schedule):
                return "negative_payment"
            if any(day < request["request_date"] for day, _ in candidate.payment_schedule):
                return "payment_before_request"
            if any(day > request["desired_completion_date"] for day, _ in candidate.payment_schedule):
                return "deadline_missed"
            if any(day > timeline.forecast_end for day, _ in candidate.payment_schedule):
                return "outside_forecast"
            if any(left > right for (left, _), (right, _) in zip(candidate.payment_schedule, candidate.payment_schedule[1:])):
                return "payment_dates_not_chronological"
        if candidate.payment_method in {"full_payment", "partial_payment", "wait"} and candidate.total_payment != requested:
            return "request_total_mismatch"
        if candidate.payment_method == "partial_payment":
            if request["allows_partial_payment"].lower() != "true":
                return "partial_not_allowed_by_request"
            if "partial_payment" not in preferences:
                return "partial_payment_preference_conflict"
            if len(candidate.payment_schedule) != 2:
                return "partial_requires_two_payments"
            first, second = candidate.payment_schedule
            if first[0] != request["request_date"] or not ZERO < first[1] < requested:
                return "invalid_partial_first_payment"
            if first[1] + second[1] != requested:
                return "partial_total_mismatch"
        if candidate.payment_method == "installments":
            option_id = candidate.option_id
            if not option_id:
                return "missing_installment_option"
            metadata = candidate.metadata
            if candidate.total_payment != sum((amount for _, amount in candidate.payment_schedule), ZERO):
                return "installment_total_mismatch"
            if candidate.payment_count != int(metadata["option_number_of_payments"]):
                return "installment_count_mismatch"
            if any(amount != Decimal(metadata["option_payment_amount"]) for _, amount in candidate.payment_schedule):
                return "installment_amount_mismatch"
            first_date = metadata["option_first_payment_date"]
            frequency = int(metadata["option_frequency_days"])
            expected_dates = tuple(
                (date.fromisoformat(first_date) + timedelta(days=index * frequency)).isoformat()
                for index in range(candidate.payment_count)
            )
            if tuple(day for day, _ in candidate.payment_schedule) != expected_dates:
                return "installment_schedule_mismatch"
            if candidate.total_payment != Decimal(metadata["option_total_payable"]):
                return "installment_option_cost_mismatch"
            max_months = timeline.policy.max_installment_months
            if max_months is not None and candidate.payment_count > max_months:
                return "installment_duration_exceeds_preference"
        if candidate.spending_changes and len(candidate.spending_changes) > 3:
            return "too_many_spending_changes"
        simulation = candidate.simulation_result
        if simulation is None or not simulation.feasible:
            return "simulation_infeasible"
        return ""


def run_candidate_engine(index: DatasetIndex, store: CanonicalEventStore) -> Mapping[str, CandidateDecision]:
    engine = CandidateEngine(index, store)
    return {request["request_id"]: engine.decide(request) for request in index.requests}
