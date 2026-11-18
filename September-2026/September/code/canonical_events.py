"""Canonical financial events and explicit cash-flow eligibility.

The normalizer is intentionally independent of balance calculations. Every raw
row becomes at most one CanonicalEvent keyed by event_id; linked events remain
separate rows and are classified for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from data_layer import DatasetIndex, Row
from image_evidence import ImageAmountEvidence, ImageEvidenceResolver


class NormalizationError(ValueError):
    """Raised when the source violates an identity or relationship invariant."""


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str
    amount: Optional[Decimal]
    currency: str
    event_date: str
    settlement_date: str
    effective_date: str
    status: str
    linked_event_id: str
    flexibility: str
    minimum_allowed_amount: Optional[Decimal]
    relationship: str
    amount_source: str
    evidence_image_id: str

    # Explicit cash-flow interpretation. A zero current effect means that the
    # profile's current_available_balance should not be replayed from this row.
    current_cash_effect: Decimal
    forecast_cash_effect: Optional[Decimal]
    forecast_eligible: bool
    reserve_pending_debit: bool
    cash_eligibility: str
    cash_flow_reason: str

    @property
    def is_flexible(self) -> bool:
        return self.flexibility in {"reducible", "stoppable", "reducible_or_stoppable"}


def _decimal_or_none(value: str) -> Optional[Decimal]:
    value = (value or "").strip()
    return Decimal(value) if value else None


def _signed_amount(direction: str, amount: Decimal) -> Decimal:
    if direction == "debit":
        return -amount
    if direction == "credit":
        return amount
    return Decimal("0")


def _relationship(row: Row, parent: Optional[Row]) -> str:
    if not row.get("linked_event_id"):
        return "independent"
    if parent is None:
        return "missing_parent"
    description = row.get("description", "").lower()
    if parent.get("status") == "failed" and row.get("event_type") == "debt_payment":
        return "retry_after_failed_event"
    if row.get("event_type") == "refund":
        return "refund_of_prior_event"
    if row.get("event_type") == "investment_valuation":
        return "unrealized_valuation_of_prior_investment"
    if row.get("event_type") == "investment_sale":
        return "settled_sale_of_prior_investment"
    if "duplicate" in description:
        return "possible_duplicate_charge"
    if parent.get("status") == "cancelled":
        return "replacement_after_cancellation"
    if "amend" in description or "replace" in description:
        return "amendment_of_prior_event"
    return "linked_event_unclassified"


def _eligibility(
    row: Row,
    amount: Optional[Decimal],
) -> Tuple[Decimal, Optional[Decimal], bool, bool, str, str]:
    """Return current effect, forecast effect, flags, and explicit reason.

    Current effects represent already-realized ledger cash; they are not added
    to the profile's supplied current balance. Forecast effects are the only
    effects a future timeline may apply after filtering by date.
    """
    status = row["status"]
    direction = row["direction"]
    if amount is None:
        return (
            Decimal("0"),
            None,
            False,
            False,
            "unresolved_amount",
            "Blank amount has no usable linked image extraction; never treated as zero.",
        )

    if direction == "non_cash" or status == "unrealized" or row["event_type"] == "investment_valuation":
        return (
            Decimal("0"),
            None,
            False,
            False,
            "non_cash",
            "Unrealized/non_cash investment value is not available cash.",
        )
    if status in {"failed", "cancelled"}:
        return (
            Decimal("0"),
            None,
            False,
            False,
            status,
            f"{status.capitalize()} event has no cash effect.",
        )

    signed = _signed_amount(direction, amount)
    if status == "settled":
        return (
            signed,
            signed,
            True,
            False,
            "settled_cash",
            "Settled debit/credit is realized cash and is eligible when its effective date is forecasted.",
        )
    if status == "pending" and direction == "debit":
        return (
            Decimal("0"),
            signed,
            True,
            True,
            "pending_debit_reserved",
            "Pending debit is reserved and applied as a forecast outflow; it is not replayed into current balance.",
        )
    if status == "pending" and direction == "credit":
        return (
            Decimal("0"),
            None,
            False,
            False,
            "pending_credit_excluded",
            "Pending credit/refund is excluded until it is settled.",
        )
    if status == "scheduled":
        return (
            Decimal("0"),
            signed,
            True,
            False,
            "scheduled_cash",
            "Scheduled cash is forecast on its settlement date; confirmed salary is not counted earlier.",
        )

    return (
        Decimal("0"),
        None,
        False,
        False,
        "unsupported_state",
        f"Status {status!r} has no supported cash-flow rule.",
    )


def normalize_event(
    row: Row,
    events_by_id: Mapping[str, Row],
    resolver: ImageEvidenceResolver,
    images_by_event: Mapping[str, Sequence[Mapping[str, str]]],
) -> CanonicalEvent:
    event_id = row.get("event_id", "")
    if not event_id:
        raise NormalizationError("event row has blank event_id")
    parent_id = row.get("linked_event_id", "")
    parent = events_by_id.get(parent_id) if parent_id else None
    if parent_id and parent is None:
        raise NormalizationError(f"{event_id}: linked parent {parent_id} does not exist")

    amount, evidence = resolver.resolve_event_amount(row, images_by_event)
    current_effect, forecast_effect, forecast_eligible, reserve, eligibility, reason = _eligibility(row, amount)
    effective_date = row.get("settlement_date", "") or row.get("event_date", "")
    if row.get("amount", "").strip():
        amount_source = "source_row"
    elif evidence:
        amount_source = "image_evidence"
    else:
        amount_source = "unresolved_image"
    image_id = evidence.image_id if evidence else ""

    return CanonicalEvent(
        event_id=event_id,
        user_id=row["user_id"],
        event_type=row["event_type"],
        description=row["description"],
        category=row["category"],
        direction=row["direction"],
        amount=amount,
        currency=row["currency"],
        event_date=row["event_date"],
        settlement_date=row["settlement_date"],
        effective_date=effective_date,
        status=row["status"],
        linked_event_id=parent_id,
        flexibility=row["flexibility"],
        minimum_allowed_amount=_decimal_or_none(row["minimum_allowed_amount"]),
        relationship=_relationship(row, parent),
        amount_source=amount_source,
        evidence_image_id=image_id,
        current_cash_effect=current_effect,
        forecast_cash_effect=forecast_effect,
        forecast_eligible=forecast_eligible,
        reserve_pending_debit=reserve,
        cash_eligibility=eligibility,
        cash_flow_reason=reason,
    )


@dataclass(frozen=True)
class CanonicalEventStore:
    by_id: Mapping[str, CanonicalEvent]
    by_user: Mapping[str, List[CanonicalEvent]]
    by_linked_event: Mapping[str, List[CanonicalEvent]]
    image_evidence_by_event: Mapping[str, ImageAmountEvidence]

    @property
    def events(self) -> List[CanonicalEvent]:
        return list(self.by_id.values())


def normalize_events(
    rows: Sequence[Row],
    images_by_event: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
    resolver: ImageEvidenceResolver | None = None,
) -> CanonicalEventStore:
    """Normalize each unique event_id exactly once and sort by user/date."""
    images_by_event = images_by_event or {}
    resolver = resolver or ImageEvidenceResolver()
    events_by_id: Dict[str, Row] = {}
    for row in rows:
        event_id = row.get("event_id", "")
        if event_id in events_by_id:
            raise NormalizationError(f"duplicate event_id={event_id}; refusing to drop duplicate rows")
        events_by_id[event_id] = row

    canonical: Dict[str, CanonicalEvent] = {}
    evidence_by_event: Dict[str, ImageAmountEvidence] = {}
    for row in rows:
        event = normalize_event(row, events_by_id, resolver, images_by_event)
        canonical[event.event_id] = event
        if event.evidence_image_id:
            evidence = resolver.cache[event.evidence_image_id]
            evidence_by_event[event.event_id] = evidence

    for event_id, event in list(canonical.items()):
        parent = canonical.get(event.linked_event_id) if event.linked_event_id else None
        if (
            event.relationship == "possible_duplicate_charge"
            and event.status == "pending"
            and event.direction == "debit"
            and parent is not None
            and parent.status == "settled"
            and parent.direction == "debit"
            and event.amount is not None
            and parent.amount is not None
            and event.amount == parent.amount
            and event.currency == parent.currency
        ):
            canonical[event_id] = replace(
                event,
                forecast_cash_effect=None,
                forecast_eligible=False,
                reserve_pending_debit=False,
                cash_eligibility="duplicate_excluded",
                cash_flow_reason=(
                    "Pending debit is an identified duplicate of an already-settled "
                    "same-amount debit; the settled parent is the sole cash flow."
                ),
            )

    by_user: Dict[str, List[CanonicalEvent]] = {}
    by_linked_event: Dict[str, List[CanonicalEvent]] = {}
    for event in canonical.values():
        by_user.setdefault(event.user_id, []).append(event)
        if event.linked_event_id:
            by_linked_event.setdefault(event.linked_event_id, []).append(event)
    for user_events in by_user.values():
        user_events.sort(key=lambda e: (e.effective_date, e.event_id))
    for linked_events in by_linked_event.values():
        linked_events.sort(key=lambda e: (e.effective_date, e.event_id))

    return CanonicalEventStore(
        by_id=canonical,
        by_user=by_user,
        by_linked_event=by_linked_event,
        image_evidence_by_event=evidence_by_event,
    )


def normalize_dataset(index: DatasetIndex, resolver: ImageEvidenceResolver | None = None) -> CanonicalEventStore:
    return normalize_events(index.events, index.images_by_event, resolver)
