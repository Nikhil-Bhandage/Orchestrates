"""Financial timelines and deterministic cash-flow simulation.

The timeline starts from the profile's supplied current balance. Historical
settled rows before the request date are retained for indexing/recurrence
inference but are never replayed into that starting balance.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from canonical_events import CanonicalEvent, CanonicalEventStore
from data_layer import DatasetIndex, Row


ZERO = Decimal("0")


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _date_text(value: date) -> str:
    return value.isoformat()


def _decimal(value: str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _pipe_set(value: str) -> FrozenSet[str]:
    return frozenset(part for part in (value or "").split("|") if part)


@dataclass(frozen=True)
class ProfilePolicy:
    user_id: str
    home_currency: str
    starting_balance: Decimal
    minimum_balance: Decimal
    protected_categories: FrozenSet[str]
    reducible_categories: FrozenSet[str]
    stoppable_categories: FrozenSet[str]
    payment_methods: FrozenSet[str]
    max_installment_months: Optional[int]

    @classmethod
    def from_row(cls, row: Row) -> "ProfilePolicy":
        max_months = row.get("max_installment_months", "").strip()
        return cls(
            user_id=row["user_id"],
            home_currency=row["home_currency"],
            starting_balance=Decimal(row["current_available_balance"]),
            minimum_balance=Decimal(row["minimum_balance_to_keep"]),
            protected_categories=_pipe_set(row["expense_categories_to_protect"]),
            reducible_categories=_pipe_set(row["expense_categories_user_is_willing_to_reduce"]),
            stoppable_categories=_pipe_set(row["expense_categories_user_is_willing_to_stop"]),
            payment_methods=_pipe_set(row["payment_methods_user_will_consider"]),
            max_installment_months=int(max_months) if max_months else None,
        )


@dataclass(frozen=True)
class RecurrencePattern:
    source_event_ids: Tuple[str, ...]
    signature: Tuple[str, ...]
    interval_days: int
    next_amount: Decimal
    next_minimum_allowed_amount: Optional[Decimal]
    kind: str = "exact"


@dataclass(frozen=True)
class TimelineEntry:
    event: CanonicalEvent
    projected: bool
    change_event_ids: Tuple[str, ...]
    projection_kind: str = "source"
    # Cash effects are expressed in the profile's home currency. The event
    # itself retains its source currency and amount for auditability.
    cash_flow: Optional[Decimal] = None

    @property
    def event_id(self) -> str:
        return self.event.event_id

    @property
    def effective_date(self) -> str:
        return self.event.effective_date

    @property
    def net_cash_flow(self) -> Decimal:
        if self.cash_flow is not None:
            return self.cash_flow
        assert self.event.forecast_cash_effect is not None
        return self.event.forecast_cash_effect


@dataclass(frozen=True)
class UserTimeline:
    user_id: str
    policy: ProfilePolicy
    anchor_date: str
    forecast_end: str
    entries: Tuple[TimelineEntry, ...]
    dates: Tuple[str, ...]
    net: Tuple[Decimal, ...]
    cumulative_net_flow: Tuple[Decimal, ...]
    suffix_min_prefix: Tuple[Decimal, ...]
    range_min_tree: Tuple[Decimal, ...]
    change_index: Mapping[str, Tuple[int, ...]]

    def __post_init__(self) -> None:
        if len(self.cumulative_net_flow) != len(self.entries) + 1:
            raise ValueError("prefix array must contain one more element than entries")
        if len(self.suffix_min_prefix) != len(self.cumulative_net_flow):
            raise ValueError("suffix minimum must match prefix length")

    def start_index(self, request_date: str) -> int:
        """First eligible natural event on or after request_date."""
        return bisect.bisect_left(self.dates, request_date)

    def after_date_index(self, event_date: str) -> int:
        """First event strictly after event_date; payment follows same-day events."""
        return bisect.bisect_right(self.dates, event_date)

    def end_index(self, start_date: str) -> int:
        end_date = _date_text(_parse_date(start_date) + timedelta(days=90))
        return bisect.bisect_right(self.dates, min(end_date, self.forecast_end))

    def natural_balance_after(self, start_index: int, event_index: int) -> Decimal:
        return self.policy.starting_balance + (
            self.cumulative_net_flow[event_index + 1]
            - self.cumulative_net_flow[start_index]
        )

    def _range_min_prefix(self, left: int, right: int) -> Decimal:
        """Inclusive RMQ over cumulative_net_flow[left:right+1]."""
        if left > right:
            raise ValueError("empty prefix range")
        size = len(self.cumulative_net_flow)
        base = (len(self.range_min_tree) + 1) // 2
        left += base
        right += base
        result: Optional[Decimal] = None
        while left <= right:
            if left & 1:
                result = self.range_min_tree[left] if result is None else min(result, self.range_min_tree[left])
                left += 1
            if not (right & 1):
                result = self.range_min_tree[right] if result is None else min(result, self.range_min_tree[right])
                right -= 1
            left //= 2
            right //= 2
        assert result is not None
        return result

    def minimum_natural_balance_after(
        self, start_index: int, payment_after_index: int, end_index: Optional[int] = None
    ) -> Decimal:
        """Minimum natural balance from immediately before payment onward."""
        end_prefix = self.end_index(self.anchor_date) if end_index is None else end_index
        if payment_after_index > end_prefix:
            payment_after_index = end_prefix
        min_prefix = (
            self.suffix_min_prefix[payment_after_index]
            if end_prefix == len(self.entries)
            else self._range_min_prefix(payment_after_index, end_prefix)
        )
        return self.policy.starting_balance + min_prefix - self.cumulative_net_flow[start_index]


@dataclass(frozen=True)
class MaxSafePaymentResult:
    max_safe_payment: Decimal
    natural_path_feasible: bool
    minimum_natural_balance_before_payment: Decimal
    minimum_natural_balance_after_payment: Decimal
    payment_after_index: int
    first_violation_date: str


@dataclass(frozen=True)
class BalanceCheckpoint:
    date: str
    kind: str
    identifier: str
    balance_before: Decimal
    cash_delta: Decimal
    balance_after: Decimal


@dataclass(frozen=True)
class SimulationResult:
    feasible: bool
    ending_balance: Decimal
    minimum_balance_seen: Decimal
    first_violation_date: str
    first_violation_reason: str
    balance_checkpoints: Tuple[BalanceCheckpoint, ...]
    total_inflow: Decimal
    total_outflow: Decimal
    total_payment: Decimal
    natural_cash_flow: Decimal
    paid_amount_matches_requested: Optional[bool]
    violations: Tuple[str, ...]


@dataclass(frozen=True)
class _Change:
    target_event_id: str
    kind: str
    amount: Optional[Decimal]


def _pattern_signature(event: CanonicalEvent) -> Tuple[str, ...]:
    return (
        event.event_type,
        event.category,
        event.description,
        event.direction,
        event.currency,
        event.flexibility,
        str(event.minimum_allowed_amount or ""),
    )


def _supported_pattern(events: Sequence[CanonicalEvent]) -> Optional[RecurrencePattern]:
    if len(events) < 3:
        return None
    ordered = sorted(events, key=lambda e: (e.effective_date, e.event_id))
    dates = [_parse_date(e.effective_date) for e in ordered]
    intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
    typical = int(round(float(median(intervals))))
    if typical <= 0 or not (6 <= typical <= 35):
        return None
    # Accept regular weekly, fortnightly, or monthly history only. A broad
    # 20% interval band avoids extrapolating irregular one-off spending.
    if any(abs(interval - typical) > max(2, round(typical * 0.20)) for interval in intervals):
        return None
    if not (
        6 <= typical <= 8
        or 13 <= typical <= 16
        or 27 <= typical <= 35
    ):
        return None
    latest = ordered[-1]
    amounts = [e.amount for e in ordered[-3:] if e.amount is not None]
    if not amounts:
        return None
    # Variable debit obligations use a recent maximum; fixed/subscription and
    # salary recurrence use the latest confirmed amount.
    if latest.direction == "debit" and latest.flexibility == "fixed" and latest.event_type == "expense":
        next_amount = max(amounts)
    else:
        next_amount = amounts[-1]
    return RecurrencePattern(
        source_event_ids=tuple(e.event_id for e in ordered),
        signature=_pattern_signature(latest),
        interval_days=typical,
        next_amount=next_amount,
        next_minimum_allowed_amount=latest.minimum_allowed_amount,
        kind="exact",
    )


def _detect_patterns(events: Sequence[CanonicalEvent]) -> List[RecurrencePattern]:
    groups: Dict[Tuple[str, ...], List[CanonicalEvent]] = {}
    for event in events:
        if (
            event.status == "settled"
            and event.amount is not None
            and event.effective_date
            and event.direction in {"debit", "credit"}
        ):
            groups.setdefault(_pattern_signature(event), []).append(event)
    patterns: List[RecurrencePattern] = []
    for group in groups.values():
        pattern = _supported_pattern(group)
        if pattern:
            patterns.append(pattern)
    return patterns


def _detect_category_patterns(
    events: Sequence[CanonicalEvent],
    policy: ProfilePolicy,
    excluded_event_ids: FrozenSet[str],
) -> List[RecurrencePattern]:
    """Detect supported cadence for essential variable spending.

    Variable essential rows intentionally have varying descriptions. They are
    forecast only when the category is protected, the rows are fixed debits,
    and at least five historical observations support a regular cadence.
    """
    groups: Dict[Tuple[str, str, str], List[CanonicalEvent]] = {}
    for event in events:
        if (
            event.event_id not in excluded_event_ids
            and event.status == "settled"
            and event.event_type == "expense"
            and event.direction == "debit"
            and event.flexibility == "fixed"
            and event.category in policy.protected_categories
            and event.amount is not None
        ):
            groups.setdefault((event.category, event.currency, event.direction), []).append(event)

    patterns: List[RecurrencePattern] = []
    for signature, group in groups.items():
        if len(group) < 5:
            continue
        ordered = sorted(group, key=lambda e: (e.effective_date, e.event_id))
        dates = [_parse_date(e.effective_date) for e in ordered]
        intervals = [(b - a).days for a, b in zip(dates, dates[1:])]
        typical = int(round(float(median(intervals))))
        if typical <= 0 or not (4 <= typical <= 35):
            continue
        if any(abs(interval - typical) > max(2, round(typical * 0.20)) for interval in intervals):
            continue
        if not (4 <= typical <= 12 or 13 <= typical <= 16 or 27 <= typical <= 35):
            continue
        amounts = [e.amount for e in ordered[-3:] if e.amount is not None]
        if not amounts:
            continue
        latest = ordered[-1]
        patterns.append(
            RecurrencePattern(
                source_event_ids=tuple(e.event_id for e in ordered),
                signature=signature,
                interval_days=typical,
                next_amount=max(amounts),
                next_minimum_allowed_amount=None,
                kind="essential_variable",
            )
        )
    return patterns


def _project_event(
    source: CanonicalEvent,
    event_id: str,
    projected_date: str,
    amount: Decimal,
    minimum_allowed_amount: Optional[Decimal],
) -> CanonicalEvent:
    signed = amount if source.direction == "credit" else -amount
    return replace(
        source,
        event_id=event_id,
        description=f"Projected recurring: {source.description}",
        amount=amount,
        event_date=projected_date,
        settlement_date=projected_date,
        effective_date=projected_date,
        status="scheduled",
        linked_event_id="",
        relationship="recurring_projection",
        amount_source="recurrence_projection",
        evidence_image_id="",
        current_cash_effect=ZERO,
        forecast_cash_effect=signed,
        forecast_eligible=True,
        reserve_pending_debit=False,
        cash_eligibility="recurring_projection",
        cash_flow_reason="Projected only from a supported repeated historical interval.",
        minimum_allowed_amount=minimum_allowed_amount,
    )


def _tree_for(values: Sequence[Decimal]) -> Tuple[Decimal, ...]:
    base = 1
    while base < len(values):
        base *= 2
    tree = [Decimal("Infinity")] * (2 * base)
    tree[base : base + len(values)] = values
    for i in range(base - 1, 0, -1):
        tree[i] = min(tree[2 * i], tree[2 * i + 1])
    return tuple(tree)


def _cash_effect_in_home_currency(
    event: CanonicalEvent,
    home_currency: str,
    exchange_rates: Mapping[Tuple[str, str, str], Row],
    allow_prior_rate: bool = False,
) -> Decimal:
    """Convert one eligible event using deterministic fixed exchange rates.

    Real source events require their exact settlement-date row. A recurrence
    projection is synthetic, so when the table has no exact projected date it
    uses the latest fixed rate on or before that date; it never calls a live
    service or fabricates a rate.
    """
    assert event.forecast_cash_effect is not None
    if event.currency == home_currency:
        return event.forecast_cash_effect
    key = (event.effective_date, event.currency, home_currency)
    rate_row = exchange_rates.get(key)
    if rate_row is None and allow_prior_rate:
        prior = [
            row for (rate_date, from_currency, to_currency), row in exchange_rates.items()
            if from_currency == event.currency
            and to_currency == home_currency
            and rate_date <= event.effective_date
        ]
        if prior:
            rate_row = max(prior, key=lambda row: row["rate_date"])
    if rate_row is None:
        raise ValueError(f"missing exchange rate for {event.event_id}: {key}")
    return event.forecast_cash_effect * Decimal(rate_row["rate"])


def build_user_timeline(
    user_id: str,
    canonical_events: Sequence[CanonicalEvent],
    profile_row: Row,
    request_dates: Sequence[str],
    horizon_days: int = 90,
    exchange_rates: Optional[Mapping[Tuple[str, str, str], Row]] = None,
) -> UserTimeline:
    if not request_dates:
        raise ValueError(f"cannot build timeline for {user_id} without request dates")
    policy = ProfilePolicy.from_row(profile_row)
    exchange_rates = exchange_rates or {}
    anchor = min(request_dates)
    forecast_end = _date_text(max(_parse_date(d) for d in request_dates) + timedelta(days=horizon_days))

    eligible = [e for e in canonical_events if e.forecast_eligible and e.forecast_cash_effect is not None]
    exact_patterns = _detect_patterns(eligible)
    exact_event_ids = frozenset(source for pattern in exact_patterns for source in pattern.source_event_ids)
    variable_patterns = _detect_category_patterns(eligible, policy, exact_event_ids)
    patterns = exact_patterns + variable_patterns
    pattern_by_source: Dict[str, RecurrencePattern] = {
        source: pattern for pattern in patterns for source in pattern.source_event_ids
    }
    entries: List[TimelineEntry] = [
        TimelineEntry(
            event=e,
            projected=False,
            change_event_ids=pattern_by_source[e.event_id].source_event_ids
            if e.event_id in pattern_by_source and e.is_flexible
            else (),
            projection_kind="source",
            cash_flow=_cash_effect_in_home_currency(e, policy.home_currency, exchange_rates),
        )
        for e in eligible
    ]

    for pattern in patterns:
        source = next(e for e in eligible if e.event_id == pattern.source_event_ids[-1])
        if pattern.kind == "exact":
            occupied = {
                (e.category, e.direction, e.effective_date)
                for e in eligible
                if _pattern_signature(e) == pattern.signature
            }
        else:
            occupied = {
                (e.category, e.direction, e.effective_date)
                for e in eligible
                if e.category == source.category
                and e.currency == source.currency
                and e.direction == source.direction
            }
        terminal_dates = [
            e.effective_date
            for e in eligible
            if e.direction == "credit"
            and e.category == source.category
            and any(term in e.description.lower() for term in ("final", "employment ended", "contract ended"))
            and e.effective_date > source.effective_date
        ]
        terminal_date = min(terminal_dates) if terminal_dates else ""
        next_day = _parse_date(source.effective_date) + timedelta(days=pattern.interval_days)
        while next_day <= _parse_date(forecast_end):
            projected_date = _date_text(next_day)
            if terminal_date and projected_date > terminal_date:
                break
            occupied_key = (source.category, source.direction, projected_date)
            if occupied_key not in occupied:
                projected = _project_event(
                    source,
                    f"forecast:{source.event_id}:{projected_date}",
                    projected_date,
                    pattern.next_amount,
                    pattern.next_minimum_allowed_amount,
                )
                entries.append(
                    TimelineEntry(
                        event=projected,
                        projected=True,
                        change_event_ids=pattern.source_event_ids if source.is_flexible and pattern.kind == "exact" else (),
                        projection_kind=pattern.kind,
                        cash_flow=_cash_effect_in_home_currency(
                            projected, policy.home_currency, exchange_rates, allow_prior_rate=True
                        ),
                    )
                )
                occupied.add(occupied_key)
            next_day += timedelta(days=pattern.interval_days)

    entries.sort(key=lambda item: (item.effective_date, item.event_id))
    dates = tuple(entry.effective_date for entry in entries)
    net = tuple(entry.net_cash_flow for entry in entries)
    prefix: List[Decimal] = [ZERO]
    for value in net:
        prefix.append(prefix[-1] + value)
    suffix: List[Decimal] = [ZERO] * len(prefix)
    suffix[-1] = prefix[-1]
    for i in range(len(prefix) - 2, -1, -1):
        suffix[i] = min(prefix[i], suffix[i + 1])

    change_index: Dict[str, List[int]] = {}
    for index, entry in enumerate(entries):
        for source_id in entry.change_event_ids:
            change_index.setdefault(source_id, []).append(index)

    return UserTimeline(
        user_id=user_id,
        policy=policy,
        anchor_date=anchor,
        forecast_end=forecast_end,
        entries=tuple(entries),
        dates=dates,
        net=net,
        cumulative_net_flow=tuple(prefix),
        suffix_min_prefix=tuple(suffix),
        range_min_tree=_tree_for(prefix),
        change_index={key: tuple(value) for key, value in change_index.items()},
    )


class TimelineCatalog:
    """Build and cache one immutable indexed timeline per user."""

    def __init__(self, timelines: Mapping[str, UserTimeline]):
        self.by_user = dict(timelines)

    @classmethod
    def from_index(cls, index: DatasetIndex, store: CanonicalEventStore, horizon_days: int = 90) -> "TimelineCatalog":
        request_dates: Dict[str, List[str]] = {}
        for request in index.requests:
            request_dates.setdefault(request["user_id"], []).append(request["request_date"])
        timelines: Dict[str, UserTimeline] = {}
        for user_id, dates in request_dates.items():
            timelines[user_id] = build_user_timeline(
                user_id,
                store.by_user.get(user_id, []),
                index.profiles_by_user[user_id],
                dates,
                horizon_days,
                index.exchange_rates_by_key,
            )
        return cls(timelines)

    def get(self, user_id: str) -> UserTimeline:
        return self.by_user[user_id]


def _parse_changes(timeline: UserTimeline, spending_changes: Optional[Sequence[str] | str]) -> Dict[str, _Change]:
    if not spending_changes or spending_changes == "none":
        return {}
    tokens = spending_changes.split("|") if isinstance(spending_changes, str) else list(spending_changes)
    if len(tokens) > 3:
        raise ValueError("at most three spending changes are allowed")
    changes: Dict[str, _Change] = {}
    for token in tokens:
        if token.startswith("stop:"):
            kind, target = "stop", token[5:]
            amount = None
        elif token.startswith("reduce_to:"):
            parts = token.split(":", 2)
            if len(parts) != 3:
                raise ValueError(f"invalid spending change: {token}")
            kind, target, raw_amount = "reduce_to", parts[1], parts[2]
            amount = Decimal(raw_amount)
        else:
            raise ValueError(f"invalid spending change: {token}")
        if not target or target in changes:
            raise ValueError(f"duplicate/blank spending change target: {token}")
        if target not in timeline.change_index:
            raise ValueError(f"spending change target is not a flexible recurring event: {target}")
        source_entry = timeline.entries[timeline.change_index[target][0]]
        event = source_entry.event
        if kind == "stop":
            if event.category not in timeline.policy.stoppable_categories:
                raise ValueError(f"category is not user-approved for stopping: {event.category}")
            if event.flexibility not in {"stoppable", "reducible_or_stoppable"}:
                raise ValueError("only stoppable flexible events may be stopped")
        else:
            if event.category not in timeline.policy.reducible_categories:
                raise ValueError(f"category is not user-approved for reduction: {event.category}")
            if event.flexibility not in {"reducible", "reducible_or_stoppable"}:
                raise ValueError("only reducible flexible events may be reduced")
            if amount is None or amount < (event.minimum_allowed_amount or ZERO) or event.amount is None or amount > event.amount:
                raise ValueError("reduction must respect the event minimum and current amount")
        changes[target] = _Change(target, kind, amount)
    return changes


def _adjusted_net(timeline: UserTimeline, changes: Mapping[str, _Change]) -> Tuple[Decimal, ...]:
    if not changes:
        return timeline.net
    adjusted = list(timeline.net)
    for target, change in changes.items():
        indexes = timeline.change_index[target]
        for index in indexes:
            event = timeline.entries[index].event
            if change.kind == "stop":
                adjusted[index] = ZERO
            else:
                assert change.amount is not None
                adjusted[index] = change.amount if event.direction == "credit" else -change.amount
    return tuple(adjusted)


def get_max_safe_one_time_payment(
    timeline: UserTimeline,
    payment_date: str,
    requested_amount: Decimal | str,
    spending_changes: Optional[Sequence[str] | str] = None,
) -> MaxSafePaymentResult:
    """Calculate the maximum safe one-time payment without amount enumeration."""
    requested = max(ZERO, _decimal(requested_amount))
    if payment_date < timeline.anchor_date:
        raise ValueError("payment date precedes the timeline anchor")
    start = timeline.start_index(payment_date)
    payment_after = timeline.after_date_index(payment_date)
    end = timeline.end_index(payment_date)
    # For the normal one-request-per-user case the cached suffix minimum is
    # directly valid. Adjusted flows use a rebuilt prefix, preserving safety.
    changes = _parse_changes(timeline, spending_changes)
    if not changes and end == len(timeline.entries):
        prefix = timeline.cumulative_net_flow
        suffix_min = timeline.suffix_min_prefix[payment_after]
        min_after = timeline.policy.starting_balance + suffix_min - prefix[start]
    else:
        flows = _adjusted_net(timeline, changes)
        running = ZERO
        min_after = timeline.policy.starting_balance
        for index in range(start, end):
            if timeline.entries[index].effective_date > payment_date:
                min_after = min(min_after, timeline.policy.starting_balance + running)
            running += flows[index]
            if index + 1 >= payment_after:
                min_after = min(min_after, timeline.policy.starting_balance + running)
        min_after = min(min_after, timeline.policy.starting_balance + running)

    min_before = timeline.policy.starting_balance
    if changes:
        flows = _adjusted_net(timeline, changes)
        running = ZERO
        for index in range(start, payment_after):
            running += flows[index]
            min_before = min(min_before, timeline.policy.starting_balance + running)
    else:
        for index in range(start, payment_after):
            min_before = min(min_before, timeline.natural_balance_after(start, index))

    natural_feasible = (
        min_before >= timeline.policy.minimum_balance
        and min_after >= timeline.policy.minimum_balance
    )
    if not natural_feasible:
        safe = ZERO
        flows = _adjusted_net(timeline, changes) if changes else timeline.net
        running = ZERO
        first_date = ""
        for index in range(start, end):
            running += flows[index]
            if timeline.policy.starting_balance + running < timeline.policy.minimum_balance:
                first_date = timeline.entries[index].effective_date
                break
    else:
        safe = min(requested, max(ZERO, min_after - timeline.policy.minimum_balance))
        first_date = ""
    return MaxSafePaymentResult(safe, natural_feasible, min_before, min_after, payment_after, first_date)


def _change_adjustment_for_entry(entry: TimelineEntry, changes: Mapping[str, _Change]) -> Optional[Decimal]:
    for source_id in entry.change_event_ids:
        change = changes.get(source_id)
        if change:
            if change.kind == "stop":
                return ZERO
            assert change.amount is not None
            return change.amount if entry.event.direction == "credit" else -change.amount
    return None


def simulate_payment_plan(
    timeline: UserTimeline,
    payment_schedule: Sequence[Tuple[str, Decimal | str]],
    spending_changes: Optional[Sequence[str] | str] = None,
    requested_amount: Decimal | str | None = None,
) -> SimulationResult:
    """Simulate natural events and payments with natural events first per date."""
    violations: List[str] = []
    checkpoints: List[BalanceCheckpoint] = []
    changes = _parse_changes(timeline, spending_changes)
    schedule = [(day, _decimal(amount)) for day, amount in payment_schedule]
    for _, amount in schedule:
        if amount < ZERO:
            violations.append("payment amounts must be non-negative")
    for previous, current in zip(schedule, schedule[1:]):
        if current[0] < previous[0]:
            violations.append("payment dates must be chronological")
    requested = _decimal(requested_amount) if requested_amount is not None else None
    total_payment = sum((amount for _, amount in schedule), ZERO)
    match = None if requested is None else total_payment == requested
    if requested is not None and not match:
        violations.append("payment schedule total does not equal requested amount")

    start_date = timeline.anchor_date
    end_date = _date_text(_parse_date(start_date) + timedelta(days=90))
    natural_end = bisect.bisect_right(timeline.dates, min(end_date, timeline.forecast_end))
    natural_index = timeline.start_index(start_date)
    payment_index = 0
    balance = timeline.policy.starting_balance
    minimum_seen = balance
    first_violation_date = ""
    first_violation_reason = ""
    total_inflow = ZERO
    total_outflow = ZERO
    natural_cash_flow = ZERO

    def record(date_text: str, kind: str, identifier: str, delta: Decimal) -> None:
        nonlocal balance, minimum_seen, first_violation_date, first_violation_reason
        before = balance
        balance += delta
        minimum_seen = min(minimum_seen, balance)
        checkpoints.append(BalanceCheckpoint(date_text, kind, identifier, before, delta, balance))
        if balance < timeline.policy.minimum_balance:
            reason = f"balance {balance} below minimum {timeline.policy.minimum_balance}"
            violations.append(f"{date_text}: {reason}")
            if not first_violation_date:
                first_violation_date = date_text
                first_violation_reason = reason

    if balance < timeline.policy.minimum_balance:
        record(start_date, "initial", "starting_balance", ZERO)

    while natural_index < natural_end or payment_index < len(schedule):
        next_natural = timeline.entries[natural_index] if natural_index < natural_end else None
        next_payment = schedule[payment_index] if payment_index < len(schedule) else None
        natural_date = next_natural.effective_date if next_natural else None
        payment_date = next_payment[0] if next_payment else None

        # Natural events win ties: all same-day obligations/inflows are applied
        # in canonical event_id order before a requested payment on that date.
        if next_natural is not None and (payment_date is None or natural_date <= payment_date):
            delta = _change_adjustment_for_entry(next_natural, changes)
            if delta is None:
                delta = next_natural.net_cash_flow
            if delta > ZERO:
                total_inflow += delta
            elif delta < ZERO:
                total_outflow += -delta
            natural_cash_flow += delta
            record(natural_date, "natural", next_natural.event_id, delta)
            natural_index += 1
        else:
            assert next_payment is not None
            if payment_date < start_date:
                violations.append(f"{payment_date}: payment precedes simulation start")
            record(payment_date, "payment", str(payment_index), -next_payment[1])
            payment_index += 1

    feasible = not violations and (match is not False)
    return SimulationResult(
        feasible=feasible,
        ending_balance=balance,
        minimum_balance_seen=minimum_seen,
        first_violation_date=first_violation_date,
        first_violation_reason=first_violation_reason,
        balance_checkpoints=tuple(checkpoints),
        total_inflow=total_inflow,
        total_outflow=total_outflow,
        total_payment=total_payment,
        natural_cash_flow=natural_cash_flow,
        paid_amount_matches_requested=match,
        violations=tuple(violations),
    )
