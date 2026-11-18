"""Indexed, lossless loader for the Buy or Wait dataset.

This module intentionally does not decide which financial events affect cash.
It preserves source rows and relationship identifiers so later normalization can
apply the challenge's status, linkage, currency, and evidence rules explicitly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple


REQUIRED_COLUMNS: Mapping[str, Tuple[str, ...]] = {
    "financial_profiles.csv": (
        "user_id",
        "home_currency",
        "current_available_balance",
        "minimum_balance_to_keep",
        "financial_priorities",
        "expense_categories_to_protect",
        "expense_categories_user_is_willing_to_reduce",
        "expense_categories_user_is_willing_to_stop",
        "payment_methods_user_will_consider",
        "max_installment_months",
    ),
    "financial_events.csv": (
        "event_id",
        "user_id",
        "event_type",
        "description",
        "category",
        "direction",
        "amount",
        "currency",
        "event_date",
        "settlement_date",
        "status",
        "linked_event_id",
        "flexibility",
        "minimum_allowed_amount",
    ),
    "requests.csv": (
        "request_id",
        "user_id",
        "request_date",
        "request_type",
        "requested_amount",
        "desired_completion_date",
        "allows_partial_payment",
        "request_text",
    ),
    "request_payment_options.csv": (
        "payment_option_id",
        "request_id",
        "payment_method",
        "payment_amount",
        "number_of_payments",
        "first_payment_date",
        "payment_frequency_days",
        "financing_fee",
        "total_payable_amount",
    ),
    "exchange_rates.csv": (
        "rate_date",
        "from_currency",
        "to_currency",
        "rate",
    ),
    "messages.csv": (
        "message_id",
        "user_id",
        "request_id",
        "related_event_id",
        "sent_at",
        "source_type",
        "message_text",
    ),
    "images.csv": (
        "image_id",
        "user_id",
        "request_id",
        "related_event_id",
    ),
}


Row = Dict[str, str]


def _read_csv(path: Path, expected_columns: Sequence[str]) -> List[Row]:
    """Read a UTF-8 CSV and reject schema drift early."""
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        actual = tuple(reader.fieldnames or ())
        expected = tuple(expected_columns)
        if actual != expected:
            raise ValueError(
                f"{path.name}: expected columns {expected}, got {actual}"
            )
        return [dict(row) for row in reader]


def _index_unique(rows: Sequence[Row], key: str, label: str) -> Dict[str, Row]:
    index: Dict[str, Row] = {}
    for row in rows:
        value = row.get(key, "")
        if not value:
            raise ValueError(f"{label}: blank {key}")
        if value in index:
            raise ValueError(f"{label}: duplicate {key}={value}")
        index[value] = row
    return index


def _group(rows: Sequence[Row], key: str) -> Dict[str, List[Row]]:
    grouped: Dict[str, List[Row]] = {}
    for row in rows:
        value = row.get(key, "")
        if value:
            grouped.setdefault(value, []).append(row)
    return grouped


def _sort_event_rows(rows: List[Row]) -> None:
    # ISO-8601 dates sort lexicographically. The event_id tie-breaker keeps the
    # ordering deterministic without imposing financial semantics here.
    rows.sort(key=lambda row: (row.get("event_date", ""), row.get("event_id", "")))


@dataclass(frozen=True)
class DatasetIndex:
    """All direct lookups needed by later financial-state components.

    Rows remain ordinary dictionaries to keep the loader lossless and avoid
    prematurely coercing blank amounts or dates. Evidence indexes point back to
    messages/images; they never create synthetic financial events.
    """

    profiles: List[Row]
    events: List[Row]
    requests: List[Row]
    payment_options: List[Row]
    exchange_rates: List[Row]
    messages: List[Row]
    images: List[Row]

    profiles_by_user: Mapping[str, Row]
    events_by_id: Mapping[str, Row]
    requests_by_id: Mapping[str, Row]
    payment_options_by_id: Mapping[str, Row]
    messages_by_id: Mapping[str, Row]
    images_by_id: Mapping[str, Row]

    events_by_user: Mapping[str, List[Row]]
    requests_by_user: Mapping[str, List[Row]]
    options_by_request: Mapping[str, List[Row]]
    messages_by_user: Mapping[str, List[Row]]
    messages_by_request: Mapping[str, List[Row]]
    messages_by_event: Mapping[str, List[Row]]
    images_by_user: Mapping[str, List[Row]]
    images_by_request: Mapping[str, List[Row]]
    images_by_event: Mapping[str, List[Row]]
    events_by_linked_event: Mapping[str, List[Row]]
    exchange_rates_by_key: Mapping[Tuple[str, str, str], Row]

    @classmethod
    def from_dataset(cls, dataset_dir: Path | str = "dataset") -> "DatasetIndex":
        root = Path(dataset_dir)
        loaded = {
            name: _read_csv(root / name, columns)
            for name, columns in REQUIRED_COLUMNS.items()
        }

        profiles = loaded["financial_profiles.csv"]
        events = loaded["financial_events.csv"]
        requests = loaded["requests.csv"]
        payment_options = loaded["request_payment_options.csv"]
        exchange_rates = loaded["exchange_rates.csv"]
        messages = loaded["messages.csv"]
        images = loaded["images.csv"]

        profiles_by_user = _index_unique(profiles, "user_id", "profiles")
        events_by_id = _index_unique(events, "event_id", "events")
        requests_by_id = _index_unique(requests, "request_id", "requests")
        payment_options_by_id = _index_unique(
            payment_options, "payment_option_id", "payment options"
        )
        messages_by_id = _index_unique(messages, "message_id", "messages")
        images_by_id = _index_unique(images, "image_id", "images")

        events_by_user = _group(events, "user_id")
        requests_by_user = _group(requests, "user_id")
        options_by_request = _group(payment_options, "request_id")
        messages_by_user = _group(messages, "user_id")
        messages_by_request = _group(messages, "request_id")
        messages_by_event = _group(messages, "related_event_id")
        images_by_user = _group(images, "user_id")
        images_by_request = _group(images, "request_id")
        images_by_event = _group(images, "related_event_id")
        events_by_linked_event = _group(events, "linked_event_id")

        for rows in events_by_user.values():
            _sort_event_rows(rows)
        for rows in requests_by_user.values():
            rows.sort(key=lambda row: (row.get("request_date", ""), row["request_id"]))
        for rows in messages_by_user.values():
            rows.sort(key=lambda row: (row.get("sent_at", ""), row["message_id"]))

        exchange_rates_by_key: Dict[Tuple[str, str, str], Row] = {}
        for row in exchange_rates:
            key = (row["rate_date"], row["from_currency"], row["to_currency"])
            if key in exchange_rates_by_key:
                raise ValueError(f"exchange rates: duplicate key={key}")
            exchange_rates_by_key[key] = row

        return cls(
            profiles=profiles,
            events=events,
            requests=requests,
            payment_options=payment_options,
            exchange_rates=exchange_rates,
            messages=messages,
            images=images,
            profiles_by_user=profiles_by_user,
            events_by_id=events_by_id,
            requests_by_id=requests_by_id,
            payment_options_by_id=payment_options_by_id,
            messages_by_id=messages_by_id,
            images_by_id=images_by_id,
            events_by_user=events_by_user,
            requests_by_user=requests_by_user,
            options_by_request=options_by_request,
            messages_by_user=messages_by_user,
            messages_by_request=messages_by_request,
            messages_by_event=messages_by_event,
            images_by_user=images_by_user,
            images_by_request=images_by_request,
            images_by_event=images_by_event,
            events_by_linked_event=events_by_linked_event,
            exchange_rates_by_key=exchange_rates_by_key,
        )

    def evidence_for_event(self, event_id: str) -> Tuple[List[Row], List[Row]]:
        """Return messages and images attached to one event, without cash effects."""
        return (
            list(self.messages_by_event.get(event_id, [])),
            list(self.images_by_event.get(event_id, [])),
        )
