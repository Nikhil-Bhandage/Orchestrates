"""Deterministic final output integration and validation.

This module serializes already-selected CandidateDecision objects. It never
performs arithmetic through text generation and never permits explanations to
change a decision.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Optional, Sequence

from candidate_plans import CandidateDecision, CandidateEngine, CandidatePlan
from canonical_events import normalize_dataset
from data_layer import DatasetIndex, Row
from evidence_resolution import apply_evidence_to_timeline
from financial_timeline import (
    UserTimeline,
    build_user_timeline,
    simulate_payment_plan,
)

OUTPUT_COLUMNS = (
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
)
VALID_STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
VALID_METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}
_DECIMAL_TEXT = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")


def decimal_text(value: Decimal) -> str:
    """Return a stable non-exponent decimal representation."""
    if not value.is_finite():
        raise ValueError(f"non-finite decimal: {value}")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def plan_text(candidate: CandidatePlan) -> str:
    if not candidate.payment_schedule:
        return "none"
    return "|".join(f"{day}:{decimal_text(amount)}" for day, amount in candidate.payment_schedule)


def changes_text(candidate: CandidatePlan) -> str:
    return "|".join(candidate.spending_changes) if candidate.spending_changes else "none"


@dataclass(frozen=True)
class ValidationIssue:
    request_id: str
    field: str
    code: str
    message: str


class OutputValidationError(ValueError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        self.issues = tuple(issues)
        summary = "; ".join(f"{i.request_id}:{i.field}:{i.code}" for i in self.issues[:12])
        if len(self.issues) > 12:
            summary += f"; ... ({len(self.issues)} total)"
        super().__init__(f"output validation failed: {summary}")


@dataclass(frozen=True)
class FinalRun:
    rows: tuple[Row, ...]
    diagnostics: tuple[Mapping[str, object], ...]
    summary: Mapping[str, object]


class FinalOutputPipeline:
    def __init__(self, dataset_dir: Path | str = "dataset") -> None:
        self.dataset_dir = Path(dataset_dir)
        self.index = DatasetIndex.from_dataset(self.dataset_dir)
        self.store = normalize_dataset(self.index)
        self.engine = CandidateEngine(self.index, self.store)

    def _timeline_for(self, request: Row, decision: CandidateDecision) -> UserTimeline:
        user_id = request["user_id"]
        if user_id in self.engine.catalog.by_user:
            base = self.engine.catalog.get(user_id)
        else:
            base = build_user_timeline(
                user_id,
                self.store.by_user[user_id],
                self.index.profiles_by_user[user_id],
                [request["request_date"]],
                exchange_rates=self.index.exchange_rates_by_key,
            )
        return apply_evidence_to_timeline(base, decision.context, self.index.exchange_rates_by_key)

    @staticmethod
    def _natural_minimum(timeline: UserTimeline) -> Decimal:
        start = timeline.start_index(timeline.anchor_date)
        end = timeline.end_index(timeline.anchor_date)
        balance = timeline.policy.starting_balance
        minimum = balance
        for entry in timeline.entries[start:end]:
            balance += entry.net_cash_flow
            minimum = min(minimum, balance)
        return minimum

    def _diagnostic_minimum(self, timeline: UserTimeline, candidate: CandidatePlan) -> Decimal:
        if candidate.simulation_result is not None:
            return candidate.simulation_result.minimum_balance_seen
        return self._natural_minimum(timeline)

    def _explanation(
        self,
        request: Row,
        decision: CandidateDecision,
        candidate: CandidatePlan,
        minimum_seen: Decimal,
        timeline: UserTimeline,
    ) -> str:
        currency = timeline.policy.home_currency
        requested = Decimal(request["requested_amount"])
        minimum = timeline.policy.minimum_balance
        amount = candidate.amount_safe_to_pay
        method = candidate.payment_method
        if method == "not_recommended":
            if minimum_seen < minimum:
                return (
                    f"Do not proceed: no eligible plan completes by {request['desired_completion_date']} "
                    f"while preserving the {currency} {decimal_text(minimum)} minimum; the no-plan "
                    f"90-day forecast reaches {currency} {decimal_text(minimum_seen)}. "
                    f"The request-date safe amount is {currency} {decimal_text(amount)}."
                )
            return (
                f"Do not proceed: no eligible payment plan completes by {request['desired_completion_date']} "
                f"under the user's payment preferences and 90-day safety rules. "
                f"The request-date safe amount is {currency} {decimal_text(amount)}."
            )
        if method == "full_payment":
            action = f"pay {currency} {decimal_text(requested)} on {request['request_date']}"
            if candidate.spending_changes:
                action += " after the permitted spending changes " + ", ".join(candidate.spending_changes)
            return (
                f"Recommend {action}. The validated 90-day simulation keeps the minimum balance at "
                f"{currency} {decimal_text(minimum_seen)} against the required {currency} {decimal_text(minimum)}."
            )
        if method == "partial_payment":
            first_day, first_amount = candidate.payment_schedule[0]
            second_day, second_amount = candidate.payment_schedule[1]
            return (
                f"Recommend paying {currency} {decimal_text(first_amount)} on {first_day} and "
                f"{currency} {decimal_text(second_amount)} on {second_day}; this completes the "
                f"{currency} {decimal_text(requested)} request. The validated 90-day simulation "
                f"keeps the minimum balance at {currency} {decimal_text(minimum_seen)}."
            )
        if method == "installments":
            option_id = candidate.option_id
            return (
                f"Recommend supplied installment option {option_id}: {plan_text(candidate)}. "
                f"It completes the request by {candidate.completion_date}; the validated 90-day "
                f"simulation keeps the minimum balance at {currency} {decimal_text(minimum_seen)}."
            )
        if method == "wait":
            return (
                f"Wait until {candidate.completion_date}, then pay {currency} {decimal_text(requested)} "
                f"in full. The validated 90-day simulation keeps the minimum balance at "
                f"{currency} {decimal_text(minimum_seen)} against the required {currency} {decimal_text(minimum)}."
            )
        raise ValueError(f"unsupported method for explanation: {method}")

    def _row(self, request: Row, decision: CandidateDecision) -> Row:
        candidate = decision.selected
        timeline = self._timeline_for(request, decision)
        minimum_seen = self._diagnostic_minimum(timeline, candidate)
        return {
            "request_id": request["request_id"],
            "amount_safe_to_pay": decimal_text(candidate.amount_safe_to_pay),
            "affordability_status": decision.affordability_status,
            "recommended_payment_method": candidate.payment_method,
            "payment_plan": plan_text(candidate),
            "earliest_date_for_full_payment": decision.earliest_full_payment_date,
            "spending_changes_needed": changes_text(candidate),
            "decision_explanation": self._explanation(request, decision, candidate, minimum_seen, timeline),
        }

    @staticmethod
    def _parse_decimal(value: str, field: str, issues: list[ValidationIssue], request_id: str) -> Optional[Decimal]:
        if not isinstance(value, str) or not _DECIMAL_TEXT.fullmatch(value):
            issues.append(ValidationIssue(request_id, field, "invalid_decimal", "expected a non-negative decimal string"))
            return None
        try:
            number = Decimal(value)
        except InvalidOperation:
            issues.append(ValidationIssue(request_id, field, "invalid_decimal", "could not parse decimal"))
            return None
        if not number.is_finite():
            issues.append(ValidationIssue(request_id, field, "non_finite_decimal", "decimal must be finite"))
            return None
        return number

    @staticmethod
    def _parse_plan(value: str, request_id: str, issues: list[ValidationIssue]) -> Optional[tuple[tuple[str, Decimal], ...]]:
        if value == "none":
            return ()
        if not value:
            issues.append(ValidationIssue(request_id, "payment_plan", "empty_plan", "use none or dated payments"))
            return None
        parsed: list[tuple[str, Decimal]] = []
        for part in value.split("|"):
            if part.count(":") != 1:
                issues.append(ValidationIssue(request_id, "payment_plan", "invalid_syntax", part))
                continue
            day, raw_amount = part.split(":", 1)
            try:
                parsed_day = date.fromisoformat(day)
            except ValueError:
                issues.append(ValidationIssue(request_id, "payment_plan", "invalid_date", day))
                continue
            if parsed_day.isoformat() != day:
                issues.append(ValidationIssue(request_id, "payment_plan", "non_canonical_date", day))
                continue
            amount = FinalOutputPipeline._parse_decimal(raw_amount, "payment_plan", issues, request_id)
            if amount is None:
                continue
            if amount <= 0:
                issues.append(ValidationIssue(request_id, "payment_plan", "non_positive_payment", raw_amount))
                continue
            parsed.append((day, amount))
        return tuple(parsed)

    def _validate_row(
        self,
        request: Row,
        decision: CandidateDecision,
        row: Row,
        timeline: UserTimeline,
    ) -> list[ValidationIssue]:
        request_id = request["request_id"]
        candidate = decision.selected
        issues: list[ValidationIssue] = []
        if tuple(row.keys()) != OUTPUT_COLUMNS:
            issues.append(ValidationIssue(request_id, "schema", "column_order", "output columns/order mismatch"))
        if row["request_id"] != request_id:
            issues.append(ValidationIssue(request_id, "request_id", "unknown_request_id", row["request_id"]))
        try:
            requested = Decimal(request["requested_amount"])
        except InvalidOperation:
            issues.append(ValidationIssue(request_id, "requested_amount", "invalid_input", request["requested_amount"]))
            requested = Decimal("0")
        amount = self._parse_decimal(row["amount_safe_to_pay"], "amount_safe_to_pay", issues, request_id)
        if amount is not None and not Decimal("0") <= amount <= requested:
            issues.append(ValidationIssue(request_id, "amount_safe_to_pay", "out_of_bounds", str(amount)))
        if row["affordability_status"] not in VALID_STATUSES:
            issues.append(ValidationIssue(request_id, "affordability_status", "invalid_status", row["affordability_status"]))
        if row["recommended_payment_method"] not in VALID_METHODS:
            issues.append(ValidationIssue(request_id, "recommended_payment_method", "invalid_method", row["recommended_payment_method"]))
        if row["decision_explanation"].strip() == "":
            issues.append(ValidationIssue(request_id, "decision_explanation", "empty_explanation", "explanation required"))

        parsed_plan = self._parse_plan(row["payment_plan"], request_id, issues)
        expected_plan = candidate.payment_schedule
        if parsed_plan is not None and parsed_plan != expected_plan:
            issues.append(ValidationIssue(request_id, "payment_plan", "does_not_match_selected_candidate", f"expected {expected_plan}"))
        if row["amount_safe_to_pay"] != decimal_text(candidate.amount_safe_to_pay):
            issues.append(ValidationIssue(request_id, "amount_safe_to_pay", "does_not_match_selected_candidate", decimal_text(candidate.amount_safe_to_pay)))
        if row["affordability_status"] != decision.affordability_status:
            issues.append(ValidationIssue(request_id, "affordability_status", "inconsistent_with_candidate", decision.affordability_status))
        if row["recommended_payment_method"] != candidate.payment_method:
            issues.append(ValidationIssue(request_id, "recommended_payment_method", "inconsistent_with_candidate", candidate.payment_method))
        if row["earliest_date_for_full_payment"] != decision.earliest_full_payment_date:
            issues.append(ValidationIssue(request_id, "earliest_date_for_full_payment", "inconsistent_with_state", decision.earliest_full_payment_date))
        if row["spending_changes_needed"] != changes_text(candidate):
            issues.append(ValidationIssue(request_id, "spending_changes_needed", "inconsistent_with_candidate", changes_text(candidate)))

        method = candidate.payment_method
        if method == "not_recommended":
            if parsed_plan not in (None, ()) and parsed_plan:
                issues.append(ValidationIssue(request_id, "payment_plan", "fallback_must_have_no_plan", "not_recommended requires none"))
            if row["spending_changes_needed"] != "none":
                issues.append(ValidationIssue(request_id, "spending_changes_needed", "fallback_must_have_no_changes", "not_recommended requires none"))
        else:
            if parsed_plan is None or not parsed_plan:
                issues.append(ValidationIssue(request_id, "payment_plan", "missing_plan", "recommended method requires payments"))
            else:
                if any(left > right for (left, _), (right, _) in zip(parsed_plan, parsed_plan[1:])):
                    issues.append(ValidationIssue(request_id, "payment_plan", "not_chronological", "payment dates must be chronological"))
                if any(day < request["request_date"] for day, _ in parsed_plan):
                    issues.append(ValidationIssue(request_id, "payment_plan", "before_request", "payment precedes request date"))
                if any(day > request["desired_completion_date"] for day, _ in parsed_plan):
                    issues.append(ValidationIssue(request_id, "payment_plan", "after_deadline", "payment exceeds desired completion date"))
                if any(day > timeline.forecast_end for day, _ in parsed_plan):
                    issues.append(ValidationIssue(request_id, "payment_plan", "outside_forecast", "payment exceeds 90-day forecast"))
                total = sum((value for _, value in parsed_plan), Decimal("0"))
                if method in {"full_payment", "partial_payment", "wait"} and total != requested:
                    issues.append(ValidationIssue(request_id, "payment_plan", "wrong_total", f"expected {requested}"))
                if method == "full_payment":
                    if parsed_plan != ((request["request_date"], requested),):
                        issues.append(ValidationIssue(request_id, "payment_plan", "invalid_full_payment_plan", "full payment must be one request-date payment"))
                elif method == "wait":
                    if len(parsed_plan) != 1 or parsed_plan[0][1] != requested or parsed_plan[0][0] <= request["request_date"]:
                        issues.append(ValidationIssue(request_id, "payment_plan", "invalid_wait_plan", "wait must be one later full payment"))
                elif method == "partial_payment":
                    if request["allows_partial_payment"].lower() != "true":
                        issues.append(ValidationIssue(request_id, "payment_plan", "partial_not_allowed", "request disallows partial payment"))
                    if "partial_payment" not in timeline.policy.payment_methods:
                        issues.append(ValidationIssue(request_id, "payment_plan", "partial_preference_conflict", "user does not accept partial payment"))
                    if len(parsed_plan) != 2:
                        issues.append(ValidationIssue(request_id, "payment_plan", "partial_requires_two_payments", "expected exactly two payments"))
                    elif parsed_plan[0][0] != request["request_date"] or not Decimal("0") < parsed_plan[0][1] < requested or parsed_plan[0][1] + parsed_plan[1][1] != requested:
                        issues.append(ValidationIssue(request_id, "payment_plan", "invalid_partial_split", "invalid first/remainder amounts"))
                    elif parsed_plan[1][0] != decision.earliest_full_payment_date:
                        issues.append(ValidationIssue(request_id, "payment_plan", "partial_date_not_earliest_full", decision.earliest_full_payment_date))
                elif method == "installments":
                    self._validate_installment(request, decision, parsed_plan, timeline, issues)

        # All spending changes are parsed by the same strict validator used by
        # the simulator. This verifies flexible-only targets, categories,
        # reductions, duplicate targets, and the three-change limit.
        if row["spending_changes_needed"] != "none":
            try:
                from financial_timeline import _parse_changes
                _parse_changes(timeline, row["spending_changes_needed"])
            except (ValueError, InvalidOperation) as exc:
                issues.append(ValidationIssue(request_id, "spending_changes_needed", "invalid_spending_change", str(exc)))

        simulation = candidate.simulation_result
        if method != "not_recommended":
            if simulation is None or not simulation.feasible:
                issues.append(ValidationIssue(request_id, "payment_plan", "not_90_day_safe", "selected plan is not simulator-feasible"))
            elif simulation.minimum_balance_seen < timeline.policy.minimum_balance:
                issues.append(ValidationIssue(request_id, "payment_plan", "minimum_balance_violation", str(simulation.minimum_balance_seen)))
            if simulation is not None and not simulation.paid_amount_matches_requested:
                issues.append(ValidationIssue(request_id, "payment_plan", "payment_total_mismatch", "simulator total does not match requested/option total"))
        if row["earliest_date_for_full_payment"]:
            try:
                earliest = date.fromisoformat(row["earliest_date_for_full_payment"])
                if earliest.isoformat() != row["earliest_date_for_full_payment"]:
                    issues.append(ValidationIssue(request_id, "earliest_date_for_full_payment", "non_canonical_date", row["earliest_date_for_full_payment"]))
                if earliest < date.fromisoformat(request["request_date"]) or earliest > date.fromisoformat(timeline.forecast_end):
                    issues.append(ValidationIssue(request_id, "earliest_date_for_full_payment", "date_outside_forecast", row["earliest_date_for_full_payment"]))
            except ValueError:
                issues.append(ValidationIssue(request_id, "earliest_date_for_full_payment", "invalid_date", row["earliest_date_for_full_payment"]))
        if decision.affordability_status == "affordable_now" and row["earliest_date_for_full_payment"] != request["request_date"]:
            issues.append(ValidationIssue(request_id, "earliest_date_for_full_payment", "affordable_now_date_mismatch", request["request_date"]))
        # Numeric output is in the profile home currency by dataset contract;
        # all candidates are sourced from request/options already expressed in it.
        if timeline.policy.home_currency != self.index.profiles_by_user[request["user_id"]]["home_currency"]:
            issues.append(ValidationIssue(request_id, "currency", "profile_currency_mismatch", timeline.policy.home_currency))
        return issues

    def _validate_installment(
        self,
        request: Row,
        decision: CandidateDecision,
        parsed_plan: tuple[tuple[str, Decimal], ...],
        timeline: UserTimeline,
        issues: list[ValidationIssue],
    ) -> None:
        request_id = request["request_id"]
        candidate = decision.selected
        option = self.index.payment_options_by_id.get(candidate.option_id)
        if option is None or option["request_id"] != request_id or option["payment_method"] != "installments":
            issues.append(ValidationIssue(request_id, "payment_plan", "missing_installment_option", candidate.option_id))
            return
        count = int(option["number_of_payments"])
        frequency = int(option["payment_frequency_days"])
        first = date.fromisoformat(option["first_payment_date"])
        expected = tuple(
            ((first.fromordinal(first.toordinal() + index * frequency)).isoformat(), Decimal(option["payment_amount"]))
            for index in range(count)
        )
        if parsed_plan != expected:
            issues.append(ValidationIssue(request_id, "payment_plan", "installment_schedule_mismatch", f"expected {expected}"))
        if sum((amount for _, amount in parsed_plan), Decimal("0")) != Decimal(option["total_payable_amount"]):
            issues.append(ValidationIssue(request_id, "payment_plan", "installment_total_mismatch", option["total_payable_amount"]))
        if timeline.policy.max_installment_months is not None and count > timeline.policy.max_installment_months:
            issues.append(ValidationIssue(request_id, "payment_plan", "installment_duration_exceeds_preference", str(count)))

    def build_and_validate(self) -> FinalRun:
        rows: list[Row] = []
        diagnostics: list[Mapping[str, object]] = []
        issues: list[ValidationIssue] = []
        status_counts: Counter[str] = Counter()
        method_counts: Counter[str] = Counter()
        spending_method_counts: Counter[str] = Counter()
        spending_action_counts: Counter[str] = Counter()
        spending_request_count = 0
        rejection_counts: Counter[str] = Counter()
        no_feasible = 0
        unresolved_fields: Counter[str] = Counter()

        expected_ids = [request["request_id"] for request in self.index.requests]
        if len(expected_ids) != len(set(expected_ids)):
            issues.append(ValidationIssue("<dataset>", "request_id", "duplicate_input_ids", "requests.csv contains duplicate IDs"))

        for request in self.index.requests:
            decision = self.engine.decide(request)
            candidate = decision.selected
            timeline = self._timeline_for(request, decision)
            row = self._row(request, decision)
            row_issues = self._validate_row(request, decision, row, timeline)
            issues.extend(row_issues)
            simulation = candidate.simulation_result
            minimum_seen = self._diagnostic_minimum(timeline, candidate)
            reasons = list(candidate.rationale_codes)
            if candidate.payment_method == "not_recommended":
                no_feasible += 1
                reasons.append("no_feasible_candidate")
                rejection_counts.update(decision.rejection_counts)
                if minimum_seen < timeline.policy.minimum_balance:
                    reasons.append("natural_forecast_below_minimum")
            if candidate.spending_changes:
                spending_request_count += 1
                spending_method_counts[candidate.payment_method] += 1
                spending_action_counts.update(candidate.spending_changes)
            status_counts[decision.affordability_status] += 1
            method_counts[candidate.payment_method] += 1
            if not decision.earliest_full_payment_date:
                # This is an allowed empty value, not an unresolved field.
                pass
            diagnostics.append({
                "request_id": request["request_id"],
                "selected_method": candidate.payment_method,
                "affordability_status": decision.affordability_status,
                "amount_safe_to_pay": row["amount_safe_to_pay"],
                "payment_plan": row["payment_plan"],
                "completion_date": candidate.completion_date,
                "minimum_balance_seen": decimal_text(minimum_seen),
                "validation_status": "invalid" if row_issues else "valid",
                "validation_errors": [issue.code for issue in row_issues],
                "reason_codes": list(dict.fromkeys(reasons)),
                "unresolved_fields": [],
                "home_currency": timeline.policy.home_currency,
                "currency_consistent": timeline.policy.home_currency == self.index.profiles_by_user[request["user_id"]]["home_currency"],
                "feasible_candidate_count": len(decision.feasible_candidates),
            })
            rows.append(row)

        if len(rows) != len(self.index.requests):
            issues.append(ValidationIssue("<dataset>", "row_count", "row_count_mismatch", f"{len(rows)} != {len(self.index.requests)}"))
        summary: dict[str, object] = {
            "request_count": len(rows),
            "affordability_statuses": dict(sorted(status_counts.items())),
            "payment_methods": dict(sorted(method_counts.items())),
            "spending_change_usage": {
                "requests_with_changes": spending_request_count,
                "by_selected_method": dict(sorted(spending_method_counts.items())),
                "actions": dict(sorted(spending_action_counts.items())),
            },
            "validation_failures": dict(Counter(issue.code for issue in issues)),
            "validation_failure_count": len(issues),
            "unresolved_fields": dict(sorted(unresolved_fields.items())),
            "requests_with_no_feasible_candidate": no_feasible,
            "candidate_rejection_counts_for_no_feasible": dict(sorted(rejection_counts.items())),
            "sanity_checks": {
                "all_request_ids_present_once": len(rows) == len(set(row["request_id"] for row in rows)) == len(self.index.requests),
                "all_rows_schema_valid": all(tuple(row.keys()) == OUTPUT_COLUMNS for row in rows),
                "all_rows_valid": not issues,
                "impossible_output_flags": [],
                "distribution_flags": [],
            },
        }
        if issues:
            # Diagnostics are still returned to the caller, but no output file
            # may be written when any strict validation rule fails.
            raise OutputValidationError(issues)
        return FinalRun(tuple(rows), tuple(diagnostics), summary)

    @staticmethod
    def write_csv(path: Path | str, rows: Sequence[Row]) -> None:
        destination = Path(path)
        temporary = destination.with_name(destination.name + ".tmp")
        with temporary.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(destination)

    @staticmethod
    def write_diagnostic(path: Path | str, run: FinalRun) -> None:
        destination = Path(path)
        payload = {"summary": run.summary, "requests": list(run.diagnostics)}
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        markdown = [
            "# Final 250-request diagnostic",
            "",
            f"- Requests: {run.summary['request_count']}",
            f"- Validation failures: {run.summary['validation_failure_count']}",
            f"- No-feasible-candidate requests: {run.summary['requests_with_no_feasible_candidate']}",
            "",
            "## Aggregate distributions",
            "",
            "```json",
            json.dumps(run.summary, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Requests",
            "",
            "| Request | Method | Status | Safe amount | Plan | Completion | Minimum seen | Validation | Reason codes |",
            "|---|---|---|---:|---|---|---:|---|---|",
        ]
        for item in run.diagnostics:
            markdown.append(
                f"| {item['request_id']} | {item['selected_method']} | {item['affordability_status']} | "
                f"{item['amount_safe_to_pay']} | {item['payment_plan']} | {item['completion_date'] or '—'} | "
                f"{item['minimum_balance_seen']} | {item['validation_status']} | {', '.join(item['reason_codes'])} |"
            )
        destination.with_suffix(".md").write_text("\n".join(markdown) + "\n", encoding="utf-8")


def run_final_pipeline(
    dataset_dir: Path | str = "dataset",
    output_path: Path | str = "output.csv",
    diagnostic_path: Path | str = "code/evaluation/final_diagnostic.json",
) -> FinalRun:
    pipeline = FinalOutputPipeline(dataset_dir)
    run = pipeline.build_and_validate()
    pipeline.write_diagnostic(diagnostic_path, run)
    pipeline.write_csv(output_path, run.rows)
    return run
