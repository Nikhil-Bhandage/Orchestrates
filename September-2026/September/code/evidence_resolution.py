"""Deterministic, non-cash resolution of request-linked evidence.

Messages and images are untrusted evidence. This module extracts auditable facts
and conflict records; it never creates a transaction or counts an image/message
as cash. Existing event rows remain the sole transaction identities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Mapping, Optional, Sequence, Tuple

from canonical_events import CanonicalEventStore
from data_layer import DatasetIndex, Row
from image_evidence import ImageAmountEvidence

_CURRENCY_AMOUNT = re.compile(r"\b(IDR|EUR|USD|INR|ZAR)\s*([\d][\d,]*(?:\.\d+)?)", re.I)
_ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


@dataclass(frozen=True)
class EvidenceFact:
    fact_type: str
    value: str
    currency: str
    effective_date: str
    source_ids: Tuple[str, ...]
    source_type: str
    confidence: Decimal
    text: str
    sent_at: str = ""


@dataclass(frozen=True)
class ConflictRecord:
    fact_type: str
    candidates: Tuple[EvidenceFact, ...]
    selected: Optional[EvidenceFact]
    reason: str


@dataclass(frozen=True)
class RequestContext:
    request: Row
    profile: Row
    event_ids: Tuple[str, ...]
    messages: Tuple[Row, ...]
    images: Tuple[Row, ...]
    image_evidence: Mapping[str, ImageAmountEvidence]
    facts: Tuple[EvidenceFact, ...]
    resolved_facts: Tuple[EvidenceFact, ...]
    conflicts: Tuple[ConflictRecord, ...]

    def facts_of(self, fact_type: str) -> Tuple[EvidenceFact, ...]:
        return tuple(fact for fact in self.resolved_facts if fact.fact_type == fact_type)

    @property
    def payroll_facts(self) -> Tuple[EvidenceFact, ...]:
        return tuple(fact for fact in self.resolved_facts if fact.fact_type.startswith("payroll_"))


class EvidenceResolver:
    """Build request contexts using direct indexes and stable source ordering."""

    def __init__(self, index: DatasetIndex, store: CanonicalEventStore):
        self.index = index
        self.store = store

    def context(self, request_id: str) -> RequestContext:
        return self.context_for_request(self.index.requests_by_id[request_id])

    def context_for_request(self, request: Row) -> RequestContext:
        user_id = request["user_id"]
        profile = self.index.profiles_by_user[user_id]
        event_ids = self._related_event_ids(user_id)
        request_id = request["request_id"]
        request_date = request["request_date"]
        messages = tuple(
            message for message in self.index.messages_by_user.get(user_id, [])
            if (
                message["request_id"] == request_id
                or message["related_event_id"] in event_ids
                or (
                    not message["request_id"]
                    and not message["related_event_id"]
                    and message["sent_at"][:10] <= request_date
                )
            )
        )
        images = tuple(
            image for image in self.index.images_by_user.get(user_id, [])
            if image["request_id"] == request_id or image["related_event_id"] in event_ids
        )
        image_evidence = {
            event_id: self.store.image_evidence_by_event[event_id]
            for event_id in event_ids if event_id in self.store.image_evidence_by_event
        }
        facts = tuple(fact for message in messages for fact in _facts_from_message(message))
        resolved, conflicts = _resolve_conflicts(facts)
        return RequestContext(
            request=request,
            profile=profile,
            event_ids=tuple(sorted(event_ids)),
            messages=messages,
            images=images,
            image_evidence=image_evidence,
            facts=facts,
            resolved_facts=resolved,
            conflicts=conflicts,
        )

    def _related_event_ids(self, user_id: str) -> set[str]:
        return {event.event_id for event in self.store.by_user.get(user_id, [])}


def _facts_from_message(message: Row) -> Tuple[EvidenceFact, ...]:
    text = message["message_text"]
    lower = text.lower()
    source_type = message["source_type"]
    source_id = message["message_id"]
    dates = _ISO_DATE.findall(text)
    effective_date = dates[0] if dates else ""
    amounts = [(currency.upper(), Decimal(raw.replace(",", ""))) for currency, raw in _CURRENCY_AMOUNT.findall(text)]
    facts: list[EvidenceFact] = []
    salary_terms = ("salary", "payroll", "gaji", "net pay", "monthly pay", "payslip")
    arrears_terms = ("one-time arrears adjustment", "penyesuaian tunggakan satu kali")
    if source_type == "employer" and any(term in lower for term in salary_terms):
        # The arrears amount is a separate one-off item, not a recurring salary
        # amendment. It is already represented by its own settled event in the
        # supplied event ledger, so only the explicitly stated regular salary
        # may become a payroll_amount fact.
        if any(term in lower for term in arrears_terms) and amounts:
            amounts = amounts[:1]
        for currency, amount in amounts:
            facts.append(EvidenceFact("payroll_amount", str(amount), currency, effective_date, (source_id,), source_type, Decimal("0.90"), text, message["sent_at"]))
        if any(term in lower for term in ("ended", "no regular salary", "contract has ended", "income that has ended")):
            facts.append(_fact("payroll_terminated", "true", effective_date, message))
        if "replaces the payroll date" in lower:
            facts.append(_fact("payroll_date_replacement", "true", effective_date, message))
        if any(term in lower for term in ("pending approval", "not approved", "not been approved", "still waiting")):
            facts.append(_fact("payroll_unconfirmed_income", "true", effective_date, message))
        if "childcare" in lower and "begins" in lower:
            facts.append(_fact("payroll_new_childcare_without_amount", "true", effective_date, message))
    if "rent" in lower and "increases" in lower:
        percent = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
        if percent:
            facts.append(_fact("rent_percentage_amendment", percent.group(1), effective_date, message))
    if "matching debit and credit" in lower and "same account holder" in lower:
        facts.append(_fact("internal_transfer_confirmation", "true", effective_date, message))
    if "refund" in lower and ("not reached" in lower or "still processing" in lower):
        facts.append(_fact("refund_pending", "true", effective_date, message))
    if "no units have been sold" in lower or "no cash proceeds" in lower:
        facts.append(_fact("investment_unrealized", "true", effective_date, message))
    if "prize" in lower and ("still in payment" in lower or "not been credited" in lower):
        facts.append(_fact("prize_pending", "true", effective_date, message))
    if "prize proceeds have reached" in lower or "sale have settled" in lower:
        facts.append(_fact("settled_proceeds_confirmation", "true", effective_date, message))
    if "weekly earnings" in lower and "pending" in lower:
        facts.append(_fact("payout_pending", "true", effective_date, message))
    if "foreign-currency" in lower and "may change" in lower:
        facts.append(_fact("foreign_amount_unsettled", "true", effective_date, message))
    return tuple(facts)


def _fact(fact_type: str, value: str, effective_date: str, message: Row) -> EvidenceFact:
    return EvidenceFact(fact_type, value, "", effective_date, (message["message_id"],), message["source_type"], Decimal("0.85"), message["message_text"], message["sent_at"])


def _resolve_conflicts(facts: Sequence[EvidenceFact]) -> Tuple[Tuple[EvidenceFact, ...], Tuple[ConflictRecord, ...]]:
    grouped: dict[tuple[str, str], list[EvidenceFact]] = {}
    for fact in facts:
        grouped.setdefault((fact.fact_type, fact.currency), []).append(fact)
    selected: list[EvidenceFact] = []
    conflicts: list[ConflictRecord] = []
    for (fact_type, _), candidates in sorted(grouped.items()):
        ordered = sorted(candidates, key=_conflict_priority)
        chosen = ordered[-1]
        if len({fact.value for fact in candidates}) > 1:
            conflicts.append(ConflictRecord(
                fact_type, tuple(ordered), chosen,
                "Applied explicit amendment/cancellation/settlement precedence, then newer source evidence, then deterministic date/id tie-breaks; unconfirmed amounts are not cash.",
            ))
        selected.append(chosen)
    return tuple(selected), tuple(conflicts)


def _conflict_priority(fact: EvidenceFact):
    lower = fact.text.lower()
    explicit = int(any(term in lower for term in (
        "cancel", "cancelled", "amend", "replace", "replaces", "settled", "confirmed",
    )))
    settlement = int(any(term in lower for term in ("settled", "reached your account", "confirmed")))
    return (
        explicit,
        settlement,
        fact.sent_at or "0000-00-00T00:00:00Z",
        fact.effective_date or "0000-00-00",
        fact.source_ids,
    )


def apply_evidence_to_timeline(timeline, context: RequestContext, exchange_rates: Mapping[tuple[str, str, str], Row]):
    """Apply explicit amendments to existing entries without adding transactions."""
    from dataclasses import replace
    from financial_timeline import TimelineEntry, _cash_effect_in_home_currency, _project_event, _tree_for
    entries = list(timeline.entries)
    request_date = context.request["request_date"]
    changed = False

    def future_salary_indices():
        return [i for i, entry in enumerate(entries) if entry.effective_date >= request_date and entry.event.direction == "credit" and entry.event.category == "salary"]

    def is_primary_salary_stream(entry):
        description = entry.event.description.lower()
        return (
            any(term in description for term in ("primary", "base salary", "payroll credit"))
            and not any(term in description for term in ("second", "commission", "bonus"))
        )

    def is_remaining_salary_message(fact):
        return "remaining confirmed monthly salary" in fact.text.lower()

    for fact in context.facts_of("payroll_amount"):
        all_candidates = future_salary_indices()
        candidates = all_candidates
        if fact.effective_date:
            dated = [i for i in all_candidates if entries[i].effective_date >= fact.effective_date]
            if all_candidates:
                gap = abs((date.fromisoformat(entries[all_candidates[0]].effective_date) - date.fromisoformat(fact.effective_date)).days)
            else:
                gap = 999
            if all_candidates and gap <= 3:
                # Recurrence intervals are deliberately conservative day
                # intervals (e.g. 30 days), so a monthly payroll fact can be
                # one or two days after the synthetic date it amends.
                candidates = all_candidates
            elif dated:
                candidates = dated
            elif all_candidates:
                candidates = all_candidates[:1]
        if not candidates:
            continue
        lower = fact.text.lower()
        if is_remaining_salary_message(fact):
            primary = [i for i in candidates if is_primary_salary_stream(entries[i])]
            if primary:
                candidates = primary
        one_cycle = any(term in lower for term in ("next salary", "next payroll", "first salary", "temporary monthly pay", "reduced amount continues for the next payroll"))
        amount = Decimal(fact.value)
        for i in (candidates[:1] if one_cycle else candidates):
            event = replace(entries[i].event, amount=amount, currency=fact.currency)
            signed_amount = amount if event.direction == "credit" else -amount
            event = replace(event, forecast_cash_effect=signed_amount)
            cash_flow = _cash_effect_in_home_currency(event, timeline.policy.home_currency, exchange_rates, allow_prior_rate=True)
            entries[i] = replace(entries[i], event=event, cash_flow=cash_flow)
            changed = True

    for fact in context.facts_of("payroll_date_replacement"):
        candidates = future_salary_indices()
        if candidates and fact.effective_date:
            event = replace(entries[candidates[0]].event, event_date=fact.effective_date, settlement_date=fact.effective_date, effective_date=fact.effective_date)
            entries[candidates[0]] = replace(entries[candidates[0]], event=event)
            changed = True

    def historical_salary_template(fact):
        historical = [
            entry for entry in entries
            if entry.effective_date < request_date
            and not entry.projected
            and entry.event.direction == "credit"
            and entry.event.category == "salary"
            and entry.event.amount is not None
        ]
        if not historical:
            return None
        matching = historical
        if fact.currency:
            currency_matching = [entry for entry in historical if entry.event.currency == fact.currency]
            if currency_matching:
                matching = currency_matching
        if fact.fact_type == "payroll_amount":
            amount_matching = [entry for entry in matching if entry.event.amount == Decimal(fact.value)]
            if amount_matching:
                matching = amount_matching
        return max(matching, key=lambda entry: (entry.effective_date, entry.event_id))

    materialization_facts = list(context.facts_of("payroll_amount"))
    materialization_facts.extend(context.facts_of("payroll_date_replacement"))
    for fact in materialization_facts:
        if not fact.effective_date or fact.effective_date <= request_date:
            continue
        # Existing future salary projections are amended above, including a
        # projection that is a few days before an evidence effective date.
        # Materialize only when recurrence produced no future salary at all.
        if future_salary_indices():
            continue
        template = historical_salary_template(fact)
        if template is None:
            continue
        amount = Decimal(fact.value) if fact.fact_type == "payroll_amount" else template.event.amount
        currency = fact.currency or template.event.currency
        source_tag = "-".join(fact.source_ids)
        projected = _project_event(
            replace(template.event, currency=currency),
            f"evidence:{source_tag}:salary:{fact.effective_date}",
            fact.effective_date,
            amount,
            template.event.minimum_allowed_amount,
        )
        projected = replace(
            projected,
            description="Confirmed payroll from employer evidence",
            amount_source="message_evidence",
            relationship="evidence_amendment",
            cash_eligibility="confirmed_evidence",
            cash_flow_reason="Confirmed employer evidence supplies a future salary amount and settlement date.",
        )
        entries.append(
            TimelineEntry(
                event=projected,
                projected=True,
                change_event_ids=(),
                projection_kind="evidence_confirmed",
                cash_flow=_cash_effect_in_home_currency(
                    projected, timeline.policy.home_currency, exchange_rates, allow_prior_rate=True
                ),
            )
        )
        changed = True

    for fact in context.facts_of("payroll_terminated"):
        candidates = future_salary_indices()
        if is_remaining_salary_message(fact):
            primary = {i for i in candidates if is_primary_salary_stream(entries[i])}
            candidates = [i for i in candidates if i not in primary]
        for i in candidates:
            entries[i] = replace(entries[i], cash_flow=Decimal("0"))
            changed = True

    for fact in context.facts_of("rent_percentage_amendment"):
        factor = Decimal("1") + Decimal(fact.value) / Decimal("100")
        for i, entry in enumerate(entries):
            if entry.effective_date >= request_date and entry.event.category == "rent" and entry.event.direction == "debit" and (not fact.effective_date or entry.effective_date >= fact.effective_date):
                event = replace(entry.event, amount=entry.event.amount * factor)
                entries[i] = replace(entry, event=event, cash_flow=entry.net_cash_flow * factor)
                changed = True

    if not changed:
        return timeline
    entries.sort(key=lambda item: (item.effective_date, item.event_id))
    dates = tuple(entry.effective_date for entry in entries)
    net = tuple(entry.net_cash_flow for entry in entries)
    prefix = [Decimal("0")]
    for value in net:
        prefix.append(prefix[-1] + value)
    suffix = [Decimal("0")] * len(prefix)
    suffix[-1] = prefix[-1]
    for i in range(len(prefix) - 2, -1, -1):
        suffix[i] = min(prefix[i], suffix[i + 1])
    change_index = {}
    for i, entry in enumerate(entries):
        for source_id in entry.change_event_ids:
            change_index.setdefault(source_id, []).append(i)
    return replace(timeline, entries=tuple(entries), dates=dates, net=net, cumulative_net_flow=tuple(prefix), suffix_min_prefix=tuple(suffix), range_min_tree=_tree_for(prefix), change_index={key: tuple(value) for key, value in change_index.items()})
