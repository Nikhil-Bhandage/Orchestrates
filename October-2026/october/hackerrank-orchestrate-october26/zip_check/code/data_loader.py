"""
data_loader.py — Dataset Loader + Identity Resolver
Milestone 1: Pure Python, standard-library only, no LLM calls.

Loads all participant-facing dataset files into memory and provides:
  - load_all_datasets(dataset_dir)  → DatasetBundle
  - resolve_identity(email, bundle) → IdentityResolution | None
  - get_historical_identifiers(user_id, as_of, bundle) → HistoricalIdentifiers
  - get_evidence_files_at_or_before(audit_at, bundle) → list[EvidenceFile]

Design notes:
  - All email lookups are case-insensitive (requests may supply uppercase email).
  - Historical emails come from user_audit_log.csv (field_name == 'email').
  - Evidence temporal filtering enforces the audit_at cutoff from AGENTS.md §6.2.
  - All datetime values are UTC-aware.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model types
# ---------------------------------------------------------------------------

@dataclass
class UserIdentity:
    """Current identity snapshot from user_identities.csv."""
    user_id: str
    name: str
    email: str        # stored lowercase-normalized
    phone: str
    email_hash: str
    updated_at: datetime


@dataclass
class AuditEntry:
    """One field-change record from user_audit_log.csv."""
    audit_id: str
    user_id: str
    event_time: datetime
    field_name: str   # 'email', 'phone', 'email_hash', etc.
    old_value: str
    new_value: str


@dataclass
class DeletionRequest:
    """One case from deletion_requests.csv or sample_deletion_requests.csv."""
    case_id: str
    email: str          # as supplied; may be uppercase or a historical address
    requested_at: datetime
    reported_status: str  # COMPLETE | PARTIALLY_COMPLETE | NOT_STARTED
    reported_at: datetime
    audit_at: datetime
    request_text: str


@dataclass
class SystemActivity:
    """One row from system_activity.csv."""
    activity_id: str
    event_time: datetime
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


@dataclass
class DeletionRule:
    """One row from deletion_rules.csv."""
    rule_id: str
    data_category: str
    condition: str
    required_action: str  # DELETE | REDACT | ANONYMIZE | RETAIN


@dataclass
class EvidenceFile:
    """One row from evidence_files.csv."""
    file_id: str
    file_path: str   # relative to dataset/ directory
    origin: str
    captured_at: datetime


@dataclass
class IdentityResolution:
    """Result of resolve_identity()."""
    user_id: str
    match_type: str            # 'current_email' | 'historical_email'
    matched_value: str         # normalized email value that matched
    current_identity: UserIdentity


@dataclass
class HistoricalIdentifiers:
    """
    All identifier values ever associated with a user up to a given timestamp.

    Includes current values plus all old/new values from audit_log entries
    at or before as_of. Use this to match identifiers in older evidence files
    and activity logs, where the user may appear under a previous email/phone.
    """
    user_id: str
    as_of: datetime
    emails: set       # normalized lowercase; type hint avoids py3.8 set[str] compat
    phones: set
    email_hashes: set
    current_email: str
    current_phone: str
    current_email_hash: str


@dataclass
class DatasetBundle:
    """All loaded dataset files held in memory, with pre-built indexes."""
    # --- identity ---
    identities: dict              # user_id (str) → UserIdentity
    audit_log: list               # all AuditEntry, sorted by event_time
    audit_log_by_user: dict       # user_id (str) → list[AuditEntry] sorted by event_time

    # --- email resolution indexes ---
    current_email_index: dict     # normalized_email (str) → user_id (str)
    historical_email_index: dict  # normalized_old_email (str) → list[str] (user_ids)

    # --- requests ---
    deletion_requests: list       # list[DeletionRequest]  (518 evaluation cases)
    sample_requests: list         # list[DeletionRequest]  (32 sample cases)

    # --- activity ---
    system_activity: list              # list[SystemActivity]
    activity_by_resource: dict         # resource_id (str) → list[SystemActivity]
    activity_by_event_type: dict       # event_type (str) → list[SystemActivity]

    # --- policy ---
    deletion_rules: list          # list[DeletionRule]
    rules_by_category: dict       # data_category (str) → DeletionRule

    # --- evidence ---
    evidence_files: dict          # file_id (str) → EvidenceFile


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize_email(email: str) -> str:
    """Lowercase and strip whitespace from an email address."""
    return email.strip().lower()


def _parse_dt(value: str) -> datetime:
    """
    Parse an ISO-8601 timestamp (with or without trailing 'Z') into a
    UTC-aware datetime. Raises ValueError on unrecognised formats.
    """
    value = value.strip()
    # Replace trailing Z with +00:00 for Python 3.7+ fromisoformat compatibility
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC (defensive fallback)
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Individual file loaders
# ---------------------------------------------------------------------------

def _load_user_identities(
    path: Path,
) -> tuple:
    """
    Load user_identities.csv.

    Returns:
        (identities, current_email_index)
        identities: dict[str, UserIdentity]  (user_id → UserIdentity)
        current_email_index: dict[str, str]  (normalized_email → user_id)
    """
    identities: dict = {}
    current_email_index: dict = {}

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row["user_id"].strip()
            norm_email = _normalize_email(row["email"])
            identity = UserIdentity(
                user_id=uid,
                name=row["name"].strip(),
                email=norm_email,
                phone=row["phone"].strip(),
                email_hash=row["email_hash"].strip(),
                updated_at=_parse_dt(row["updated_at"]),
            )
            identities[uid] = identity
            current_email_index[norm_email] = uid

    return identities, current_email_index


def _load_audit_log(
    path: Path,
) -> tuple:
    """
    Load user_audit_log.csv.

    Returns:
        (audit_log, audit_log_by_user, historical_email_index)
        audit_log: list[AuditEntry] sorted by event_time
        audit_log_by_user: dict[str, list[AuditEntry]] user_id → sorted entries
        historical_email_index: dict[str, list[str]]  old_email → [user_ids]
    """
    entries: list = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entry = AuditEntry(
                audit_id=row["audit_id"].strip(),
                user_id=row["user_id"].strip(),
                event_time=_parse_dt(row["event_time"]),
                field_name=row["field_name"].strip(),
                old_value=row["old_value"].strip(),
                new_value=row["new_value"].strip(),
            )
            entries.append(entry)

    entries.sort(key=lambda e: e.event_time)

    by_user: dict = {}
    hist_email_idx: dict = {}

    for entry in entries:
        by_user.setdefault(entry.user_id, []).append(entry)

        if entry.field_name == "email":
            # Index old_value so requests using the former email can be resolved
            norm_old = _normalize_email(entry.old_value)
            hist_email_idx.setdefault(norm_old, []).append(entry.user_id)

    return entries, by_user, hist_email_idx


def _load_deletion_requests(path: Path) -> list:
    """
    Load deletion_requests.csv or sample_deletion_requests.csv.
    Both share the same column schema.

    Returns list[DeletionRequest].
    """
    requests: list = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            requests.append(DeletionRequest(
                case_id=row["case_id"].strip(),
                email=row["email"].strip(),   # preserve original case; normalize at lookup time
                requested_at=_parse_dt(row["requested_at"]),
                reported_status=row["reported_status"].strip(),
                reported_at=_parse_dt(row["reported_at"]),
                audit_at=_parse_dt(row["audit_at"]),
                request_text=row["request_text"].strip(),
            ))

    return requests


def _load_system_activity(path: Path) -> tuple:
    """
    Load system_activity.csv.

    Returns:
        (activities, activity_by_resource, activity_by_event_type)
        activities: list[SystemActivity] (all rows, unsorted)
        activity_by_resource: dict[str, list[SystemActivity]]
        activity_by_event_type: dict[str, list[SystemActivity]]
    """
    activities: list = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            act = SystemActivity(
                activity_id=row["activity_id"].strip(),
                event_time=_parse_dt(row["event_time"]),
                event_type=row["event_type"].strip(),
                source_system=row["source_system"].strip(),
                target_system=row["target_system"].strip(),
                resource_id=row["resource_id"].strip(),
                reported_result=row["reported_result"].strip(),
                details=row["details"].strip(),
            )
            activities.append(act)

    by_resource: dict = {}
    by_event_type: dict = {}

    for act in activities:
        by_resource.setdefault(act.resource_id, []).append(act)
        by_event_type.setdefault(act.event_type, []).append(act)

    return activities, by_resource, by_event_type


def _load_deletion_rules(path: Path) -> tuple:
    """
    Load deletion_rules.csv.

    Returns:
        (rules, rules_by_category)
        rules: list[DeletionRule]
        rules_by_category: dict[str, DeletionRule]  data_category → rule
    """
    rules: list = []

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rule = DeletionRule(
                rule_id=row["rule_id"].strip(),
                data_category=row["data_category"].strip(),
                condition=row["condition"].strip(),
                required_action=row["required_action"].strip(),
            )
            rules.append(rule)

    by_category: dict = {r.data_category: r for r in rules}
    return rules, by_category


def _load_evidence_files(path: Path) -> dict:
    """
    Load evidence_files.csv.

    Returns dict[str, EvidenceFile]  (file_id → EvidenceFile).
    """
    evidence: dict = {}

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fid = row["file_id"].strip()
            evidence[fid] = EvidenceFile(
                file_id=fid,
                file_path=row["file_path"].strip(),
                origin=row["origin"].strip(),
                captured_at=_parse_dt(row["captured_at"]),
            )

    return evidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_all_datasets(dataset_dir) -> DatasetBundle:
    """
    Load all participant-facing dataset files from dataset_dir into memory.

    Args:
        dataset_dir: path to the 'dataset/' directory (str or Path).

    Returns:
        DatasetBundle with all data and pre-built lookup indexes.

    Raises:
        FileNotFoundError if any required file is missing.
        ValueError if any timestamp or required field cannot be parsed.
    """
    dataset_dir = Path(dataset_dir)

    identities, current_email_index = _load_user_identities(
        dataset_dir / "user_identities.csv"
    )
    audit_log, audit_log_by_user, historical_email_index = _load_audit_log(
        dataset_dir / "user_audit_log.csv"
    )
    deletion_requests = _load_deletion_requests(
        dataset_dir / "deletion_requests.csv"
    )
    sample_requests = _load_deletion_requests(
        dataset_dir / "sample_deletion_requests.csv"
    )
    system_activity, activity_by_resource, activity_by_event_type = _load_system_activity(
        dataset_dir / "system_activity.csv"
    )
    deletion_rules, rules_by_category = _load_deletion_rules(
        dataset_dir / "deletion_rules.csv"
    )
    evidence_files = _load_evidence_files(
        dataset_dir / "evidence_files.csv"
    )

    return DatasetBundle(
        identities=identities,
        audit_log=audit_log,
        audit_log_by_user=audit_log_by_user,
        current_email_index=current_email_index,
        historical_email_index=historical_email_index,
        deletion_requests=deletion_requests,
        sample_requests=sample_requests,
        system_activity=system_activity,
        activity_by_resource=activity_by_resource,
        activity_by_event_type=activity_by_event_type,
        deletion_rules=deletion_rules,
        rules_by_category=rules_by_category,
        evidence_files=evidence_files,
    )


def resolve_identity(
    email: str,
    bundle: DatasetBundle,
) -> Optional[IdentityResolution]:
    """
    Resolve a supplied email address to a user_id.

    Resolution order:
      1. Current email index (case-insensitive).
      2. Historical email index — old_value entries from user_audit_log where
         field_name == 'email'.

    Args:
        email:  The email address as supplied (may be uppercase or historical).
        bundle: DatasetBundle from load_all_datasets().

    Returns:
        IdentityResolution on success, None if no match found.
    """
    norm = _normalize_email(email)

    # --- 1. Current email ---
    if norm in bundle.current_email_index:
        uid = bundle.current_email_index[norm]
        return IdentityResolution(
            user_id=uid,
            match_type="current_email",
            matched_value=norm,
            current_identity=bundle.identities[uid],
        )

    # --- 2. Historical email ---
    if norm in bundle.historical_email_index:
        user_ids = bundle.historical_email_index[norm]
        # In well-formed synthetic data, each historical email maps to at most one user.
        # Take the first match; callers can inspect match_type for ambiguity handling.
        uid = user_ids[0]
        return IdentityResolution(
            user_id=uid,
            match_type="historical_email",
            matched_value=norm,
            current_identity=bundle.identities[uid],
        )

    return None


def get_historical_identifiers(
    user_id: str,
    as_of: datetime,
    bundle: DatasetBundle,
) -> HistoricalIdentifiers:
    """
    Return all identifier values (emails, phones, email_hashes) that were ever
    associated with user_id up to and including as_of.

    Both old_value and new_value are collected for each audit_log entry at or
    before as_of, because both values were valid identifiers during the period
    before vs. after the change event.

    Args:
        user_id: The stable internal identifier.
        as_of:   Temporal cutoff (typically the case's audit_at).
        bundle:  DatasetBundle from load_all_datasets().

    Returns:
        HistoricalIdentifiers with sets of all ever-used values.

    Raises:
        ValueError if user_id is not found in the identity snapshot.
    """
    identity = bundle.identities.get(user_id)
    if identity is None:
        raise ValueError(f"Unknown user_id: {user_id!r}")

    emails: set = {identity.email}
    phones: set = {identity.phone}
    email_hashes: set = {identity.email_hash}

    for entry in bundle.audit_log_by_user.get(user_id, []):
        if entry.event_time > as_of:
            continue  # only include changes that had occurred by as_of

        if entry.field_name == "email":
            emails.add(_normalize_email(entry.old_value))
            emails.add(_normalize_email(entry.new_value))
        elif entry.field_name == "phone":
            phones.add(entry.old_value.strip())
            phones.add(entry.new_value.strip())
        elif entry.field_name == "email_hash":
            email_hashes.add(entry.old_value.strip())
            email_hashes.add(entry.new_value.strip())

    return HistoricalIdentifiers(
        user_id=user_id,
        as_of=as_of,
        emails=emails,
        phones=phones,
        email_hashes=email_hashes,
        current_email=identity.email,
        current_phone=identity.phone,
        current_email_hash=identity.email_hash,
    )


def get_evidence_files_at_or_before(
    audit_at: datetime,
    bundle: DatasetBundle,
) -> list:
    """
    Return only evidence files whose captured_at timestamp is at or before
    audit_at. Enforces the temporal evidence cutoff required by AGENTS.md §6.2:
    'Use only information available at or before audit_at when deciding the case.'

    Args:
        audit_at: The case's audit cutoff timestamp.
        bundle:   DatasetBundle from load_all_datasets().

    Returns:
        list[EvidenceFile] filtered to those available at audit_at.
    """
    return [
        ef for ef in bundle.evidence_files.values()
        if ef.captured_at <= audit_at
    ]
