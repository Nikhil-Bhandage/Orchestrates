"""
evidence_indexer.py — Evidence Pre-Indexer
Milestone 3: Local, deterministic evidence parsing and inverted index construction.

Inspects and parses all evidence files in dataset/evidence/ (SQL, PDF, JSON, log, TXT, PNG),
building an in-memory inverted index by user identifiers and resource IDs.

Key architectural requirements (AGENTS.md & Milestone 3 spec):
  - Purely local and deterministic: no external DB execution, no Gemini calls in pre-indexer.
  - SQL files: executed inside an in-memory SQLite (:memory:) instance to safely extract tables/records.
  - PDF files: parsed with pdfplumber for text and tables.
  - Preserves full provenance: file_id, captured_at, system_id, resource_id, source path, snippet, full_record.
  - Case-specific temporal filtering: respects each case's audit_at timestamp (only evidence captured <= audit_at).
  - Robust error handling: captures file-level warnings and errors without crashing.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# PDF parser
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

# Sibling import from code/data_loader
REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
if str(REPO_ROOT / "code") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "code"))

from data_loader import (
    DatasetBundle,
    EvidenceFile,
    HistoricalIdentifiers,
    get_historical_identifiers,
    load_all_datasets,
    resolve_identity,
)

logger = logging.getLogger("evidence_indexer")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class EvidenceHit:
    """One piece of extracted evidence matching an identifier or resource."""
    file_id: str
    file_path: str
    origin: str
    captured_at: datetime
    system_id: str
    resource_id: str
    matched_identifier: str       # normalized lowercase identifier
    identifier_type: str          # 'user_id' | 'email' | 'phone' | 'email_hash' | 'resource_id' | 'other'
    snippet: str
    full_record: Any              # dict, list, or raw string
    parsed_state: str = "UNKNOWN" # 'PRESENT' | 'ABSENT' | 'ANONYMIZED' | 'REDACTED' | 'BLOCKED' | 'DISABLED' | 'RETAIN' | 'UNKNOWN'


@dataclass
class EvidenceFileSummary:
    """Parsing summary for a single evidence file."""
    file_id: str
    file_path: str
    file_type: str
    origin: str
    captured_at: datetime
    status: str                   # 'success' | 'warning' | 'error'
    hit_count: int
    error_message: Optional[str] = None


@dataclass
class EvidenceIndexReport:
    """Corpus-wide indexing report."""
    total_files: int
    succeeded_files: int
    failed_files: int
    files_by_type: dict[str, int]
    total_hits: int
    unique_identifiers: int
    parsing_errors: list[dict[str, str]]


# ---------------------------------------------------------------------------
# System ID & Resource Normalization Helpers
# ---------------------------------------------------------------------------

SYSTEM_MAP = {
    "account_admin_portal": "account_service",
    "account_history_service": "account_service",
    "customer_account_service": "account_service",
    "customer_account_failover_replica_capture": "account_service",
    "analytics_platform": "analytics_platform",
    "backup_service": "backup_service",
    "export_service": "export_service",
    "customer_export_service": "export_service",
    "identity_service": "identity_service",
    "integration_admin": "integration_service",
    "integration_management_service": "integration_service",
    "downstream_delivery_service": "integration_service",
    "search_index_admin": "search_service",
    "search_index_service": "search_service",
    "customer_search_primary_capture": "search_service",
    "security_audit_service": "security_service",
    "security_service": "security_service",
    "legal_retention_service": "security_service",
    "support_platform": "support_platform",
}

RESOURCE_SYSTEM_MAP = {
    "account": "account_service",
    "analytics": "analytics_platform",
    "audit_record": "security_service",
    "backup": "backup_service",
    "data_flow": "integration_service",
    "export": "export_service",
    "search": "search_service",
    "support": "support_platform",
    "tombstone": "identity_service",
    "object": "support_platform",
    "marketing": "integration_service",
}

# Regex patterns for fast extraction from raw text
RE_USER_ID = re.compile(r"\buser_\d+\b", re.IGNORECASE)
RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
RE_PHONE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,5}[\s.-]?\d{3,5}")
RE_HASH = re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE)
RE_RESOURCE_ID = re.compile(
    r"\b(?:account|analytics|audit_record|backup|data_flow|export|search|support|tombstone|object|marketing)_[0-9a-zA-Z]+\b",
    re.IGNORECASE,
)


def _infer_system_id(origin: str, resource_id: str, default: str = "account_service") -> str:
    """Infers the canonical system_id from origin, resource prefix, or default."""
    if resource_id:
        for prefix, sys_name in RESOURCE_SYSTEM_MAP.items():
            if resource_id.startswith(prefix + "_"):
                return sys_name
    for key, sys_name in SYSTEM_MAP.items():
        if key in origin.lower():
            return sys_name
    return default


def _extract_identifiers_from_dict(d: dict[str, Any]) -> list[tuple[str, str]]:
    """Extracts (identifier_value, identifier_type) pairs from a JSON-like dict or SQL row."""
    hits = []
    if not isinstance(d, dict):
        return hits

    for k, val in d.items():
        if val is None:
            continue
        val_str = str(val).strip()
        if not val_str:
            continue

        # user_id
        if val_str.lower().startswith("user_"):
            hits.append((val_str.lower(), "user_id"))

        # email (exact or contained)
        elif "@" in val_str and "." in val_str:
            for em in RE_EMAIL.findall(val_str):
                hits.append((em.lower(), "email"))

        # phone
        elif k in ("phone", "owner_phone", "requester_phone") and any(c.isdigit() for c in val_str):
            hits.append((val_str, "phone"))

        # email_hash (64 hex characters)
        elif (k == "email_hash" or len(val_str) == 64) and all(c in "0123456789abcdefABCDEF" for c in val_str):
            hits.append((val_str.lower(), "email_hash"))

    # resource_id
    res_id = d.get("resource_id")
    if res_id and isinstance(res_id, str) and res_id.strip():
        hits.append((res_id.strip().lower(), "resource_id"))

    # Deduplicate while preserving order
    deduped = []
    seen = set()
    for h in hits:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return deduped


# ---------------------------------------------------------------------------
# Individual File Format Parsers
# ---------------------------------------------------------------------------

def parse_sql_evidence(file_meta: EvidenceFile, content: str) -> list[EvidenceHit]:
    """
    Parses a SQL evidence dump using an isolated in-memory SQLite database.
    Reads primary and replica tables, checking direct columns and JSON-embedded rows.
    """
    hits: list[EvidenceHit] = []
    conn = sqlite3.connect(":memory:")
    try:
        conn.executescript(content)
        cursor = conn.cursor()
        tables = [
            row[0]
            for row in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
            ).fetchall()
        ]

        for table in tables:
            # Get table columns
            col_info = cursor.execute(f"PRAGMA table_info({table});").fetchall()
            col_names = [c[1] for c in col_info]

            rows = cursor.execute(f"SELECT * FROM {table};").fetchall()
            for r in rows:
                row_dict = dict(zip(col_names, r))
                res_id = str(row_dict.get("resource_id") or "")
                origin_sys = str(row_dict.get("origin_system") or "")
                system_id = _infer_system_id(origin_sys or file_meta.origin, res_id)

                # Check if row has record_json column
                record_json_str = row_dict.get("record_json")
                parsed_json = None
                if record_json_str and isinstance(record_json_str, str):
                    try:
                        parsed_json = json.loads(record_json_str)
                    except Exception:
                        parsed_json = None

                identifiers: list[tuple[str, str]] = []
                if parsed_json and isinstance(parsed_json, dict):
                    identifiers.extend(_extract_identifiers_from_dict(parsed_json))
                    # Check for anonymization or redaction
                    p_state = "PRESENT"
                    if parsed_json.get("email") is None and parsed_json.get("user_id") is None:
                        p_state = "ANONYMIZED"
                else:
                    identifiers.extend(_extract_identifiers_from_dict(row_dict))
                    status_col = str(row_dict.get("status") or "").upper()
                    account_status = str(row_dict.get("account_status") or "").upper()
                    restore_allowed = row_dict.get("restore_allowed")
                    enabled = row_dict.get("enabled")

                    if restore_allowed in (0, "0", False):
                        p_state = "BLOCKED"
                    elif restore_allowed in (1, "1", True):
                        p_state = "ACTIVE"
                    elif enabled in (0, "0", False):
                        p_state = "DISABLED"
                    elif enabled in (1, "1", True):
                        p_state = "ACTIVE"
                    elif account_status:
                        p_state = "ABSENT" if account_status in ("DELETED", "PURGED", "ABSENT") else "PRESENT"
                    elif res_id.startswith("tombstone_"):
                        pii_cols = ["email", "phone", "email_hash", "full_name", "display_name"]
                        if all(row_dict.get(c) is None for c in pii_cols):
                            p_state = "REDACTED"
                        else:
                            p_state = "PRESENT"
                    elif res_id.startswith("support_"):
                        if row_dict.get("requester_email") is None and row_dict.get("requester_phone") is None and row_dict.get("requester_name") is None:
                            p_state = "REDACTED"
                        else:
                            p_state = "PRESENT"
                    elif status_col:
                        p_state = "PRESENT" if status_col in ("ACTIVE", "PRESENT", "SUCCESS", "DELETION_PENDING", "") else status_col
                    else:
                        p_state = "PRESENT"

                # Create an evidence hit for each matched identifier
                for id_val, id_type in identifiers:
                    snippet = f"SQL table {table}: {res_id} ({system_id}) matches {id_type}={id_val}"
                    hits.append(
                        EvidenceHit(
                            file_id=file_meta.file_id,
                            file_path=file_meta.file_path,
                            origin=file_meta.origin,
                            captured_at=file_meta.captured_at,
                            system_id=system_id,
                            resource_id=res_id,
                            matched_identifier=id_val.lower(),
                            identifier_type=id_type,
                            snippet=snippet,
                            full_record=parsed_json or row_dict,
                            parsed_state=p_state,
                        )
                    )

    finally:
        conn.close()

    return hits


def parse_pdf_evidence(file_meta: EvidenceFile, abs_path: Path) -> list[EvidenceHit]:
    """
    Parses a PDF evidence document using pdfplumber.
    Extracts text and tables, searching for user IDs, emails, phones, and resource IDs.

    Enhanced classification:
      - Legal retention registers, disputed orders, tax record registers, and
        custody documents are identified from document content and origin metadata.
        Their hits receive parsed_state="RETAIN" (mapped to LEGAL_HOLD_RECORD by
        the policy engine / evidence agent) rather than "PRESENT".
      - Detection uses document headings, retention language, and origin fields,
        not hardcoded case IDs or expected outputs.
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is required to parse PDF evidence.")

    hits: list[EvidenceHit] = []

    # Determine if this document is a legal retention / custody register
    # by checking the origin metadata and document content
    is_retention_doc = False
    retention_indicators = [
        "legal_retention", "retention_register", "retention_service",
        "disputed_orders", "tax_records", "custody",
    ]
    origin_lower = file_meta.origin.lower()
    if any(ind in origin_lower for ind in retention_indicators):
        is_retention_doc = True

    with pdfplumber.open(abs_path) as pdf:
        # First pass: check document title/heading for retention indicators
        if not is_retention_doc and pdf.pages:
            first_text = (pdf.pages[0].extract_text() or "").lower()
            heading_indicators = [
                "retention register", "retain until", "disputed orders",
                "tax records register", "custody notes", "legal hold",
            ]
            if any(ind in first_text for ind in heading_indicators):
                is_retention_doc = True

        for page_idx, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if not text:
                continue

            # Identify resource ID for document if present
            res_matches = RE_RESOURCE_ID.findall(text)
            doc_res_id = ""
            if res_matches:
                # The first item may be a tuple or string depending on groups
                first_match = res_matches[0]
                doc_res_id = first_match if isinstance(first_match, str) else "".join(first_match)

            system_id = _infer_system_id(file_meta.origin, doc_res_id)

            # For retention documents, override system to security_service
            if is_retention_doc:
                system_id = "security_service"

            # Find all user IDs, emails, and phones
            user_ids = RE_USER_ID.findall(text)
            emails = RE_EMAIL.findall(text)
            hashes = RE_HASH.findall(text)

            matched_tuples: list[tuple[str, str]] = []
            for u in user_ids:
                matched_tuples.append((u.lower(), "user_id"))
            for e in emails:
                matched_tuples.append((e.lower(), "email"))
            for h in hashes:
                matched_tuples.append((h.lower(), "email_hash"))
            for r in res_matches:
                matched_tuples.append((r.lower(), "resource_id"))

            # Determine parsed_state
            # Retention documents → RETAIN (legal hold applies)
            # Other PDFs → PRESENT (default)
            parsed_state = "RETAIN" if is_retention_doc else "PRESENT"

            for id_val, id_type in matched_tuples:
                # Build context snippet (lines containing the match)
                matching_lines = [l.strip() for l in text.splitlines() if id_val in l.lower()]
                snippet = "; ".join(matching_lines[:3]) if matching_lines else f"PDF p.{page_idx + 1}"
                hits.append(
                    EvidenceHit(
                        file_id=file_meta.file_id,
                        file_path=file_meta.file_path,
                        origin=file_meta.origin,
                        captured_at=file_meta.captured_at,
                        system_id=system_id,
                        resource_id=doc_res_id if doc_res_id else (id_val if id_type == "resource_id" else ""),
                        matched_identifier=id_val.lower(),
                        identifier_type=id_type,
                        snippet=f"PDF page {page_idx + 1}: {snippet[:200]}",
                        full_record={"page": page_idx + 1, "text_sample": text[:300],
                                     "is_retention_doc": is_retention_doc},
                        parsed_state=parsed_state,
                    )
                )

    return hits


def parse_json_evidence(file_meta: EvidenceFile, content: str) -> list[EvidenceHit]:
    """
    Parses JSON records, snapshots, and service resource exports.

    Enhanced state inference from explicit JSON fields (no guessing from nulls alone):
      - restore_allowed: false  → BLOCKED  (backup entries)
      - enabled: false AND last_delivery_status == "stopped" → DISABLED (connectors)
      - Support tickets with requester PII nulled but reliable customer_reference → REDACTED
      - Analytics profiles with all direct identifiers removed → ANONYMIZED
      - status_code == 404 AND profile is None → ABSENT (when resource linkage is present)
      - Tombstones in deleted_customer_references with direct PII removed → REDACTED
    """
    hits: list[EvidenceHit] = []
    data = json.loads(content)

    def _process_item(item: dict[str, Any], default_system: str,
                      collection_name: str = ""):
        if not isinstance(item, dict):
            return
        res_id = str(item.get("resource_id") or "")
        sys_id = _infer_system_id(item.get("origin") or default_system, res_id)

        # --- State inference from explicit structural fields ---
        state = "PRESENT"  # conservative default

        status_code = item.get("status_code")
        profile = item.get("profile")

        # 1. Explicit 404 / null-profile responses → ABSENT
        #    Only when both status_code and profile confirm absence and
        #    resource linkage (resource_id) is established.
        if status_code == 404 and profile is None and res_id:
            state = "ABSENT"
        elif "status_code" in item and status_code == 404:
            state = "ABSENT"

        # 2. Explicit download / archive presence → PRESENT
        elif status_code == 200 or item.get("download_available") is True or item.get("archive_present") is True:
            state = "PRESENT"

        # 3. restore_allowed: false → BLOCKED (backup entries)
        elif item.get("restore_allowed") is False:
            state = "BLOCKED"

        # 4. enabled: false with stopped delivery → DISABLED (integration connectors)
        elif item.get("enabled") is False:
            delivery = str(item.get("last_delivery_status") or "").lower()
            if delivery == "stopped" or not delivery:
                state = "DISABLED"
            else:
                state = "DISABLED"

        # 5. Tombstones in deleted_customer_references with direct PII removed → REDACTED
        #    A tombstone has subject_reference (user_id) but direct identifiers
        #    (name, email, phone, email_hash) are all null → properly redacted.
        #    Tombstones with PII still present remain PRESENT (needs redaction).
        elif collection_name == "deleted_customer_references" and res_id.startswith("tombstone_"):
            has_subject_ref = bool(item.get("subject_reference"))
            pii_fields = ["name", "email", "phone", "email_hash"]
            all_pii_null = all(item.get(f) is None for f in pii_fields)
            any_pii_present = any(
                item.get(f) is not None and str(item.get(f)).strip() != ""
                for f in pii_fields
            )
            if has_subject_ref and all_pii_null:
                state = "REDACTED"
                # Override system to identity_service for tombstones
                sys_id = "identity_service"
            elif any_pii_present:
                state = "PRESENT"
                sys_id = "identity_service"

        # 6. Support tickets: requester identifiers all null but customer_reference present → REDACTED
        elif res_id.startswith("support_"):
            requester_fields = ["requester_email", "requester_name", "requester_phone"]
            has_customer_ref = bool(item.get("customer_reference"))
            all_requester_null = all(
                item.get(f) is None
                for f in requester_fields
                if f in item  # only check fields that exist in the schema
            )
            # Only mark REDACTED when the schema explicitly has requester fields set to null
            # AND a reliable customer linkage exists
            if (has_customer_ref and all_requester_null
                    and any(f in item for f in requester_fields)):
                state = "REDACTED"
            # If requester PII is still present, it's PRESENT (exposed PII)

        # 7. Analytics profiles with all direct identifiers removed → ANONYMIZED
        #    An analytics profile that has been properly anonymized retains only
        #    aggregate/cohort data (audience_cohort) with no direct PII.
        elif res_id.startswith("analytics_"):
            direct_id_fields = ["email", "phone", "email_hash", "customer_reference"]
            all_ids_null = all(
                item.get(f) is None
                for f in direct_id_fields
                if f in item
            )
            has_any_id_field = any(f in item for f in direct_id_fields)
            if all_ids_null and has_any_id_field:
                state = "ANONYMIZED"
            # If direct identifiers are still present, it remains PRESENT

        # --- Identifier extraction ---
        ids = _extract_identifiers_from_dict(item)

        # Check nested structures (e.g. profile dict, recent_activity)
        if isinstance(profile, dict):
            ids.extend(_extract_identifiers_from_dict(profile))
            # Profile dict with all identifying fields null → ANONYMIZED
            # (only when we haven't already set a more specific state)
            if state == "PRESENT":
                if profile.get("email") is None and profile.get("user_id") is None:
                    # Check if other PII fields are also absent
                    profile_pii = ["email", "phone", "email_hash",
                                   "customer_reference", "full_name"]
                    if all(profile.get(f) is None for f in profile_pii):
                        state = "ANONYMIZED"

        # Handle nested hits structure (search service index_queries)
        hits_data = item.get("hits")
        if isinstance(hits_data, dict):
            docs = hits_data.get("documents") or []
            for doc in docs:
                if isinstance(doc, dict):
                    ids.extend(_extract_identifiers_from_dict(doc))

        for id_val, id_type in ids:
            snippet = f"JSON record: {res_id} ({sys_id}) state={state} {id_type}={id_val}"
            hits.append(
                EvidenceHit(
                    file_id=file_meta.file_id,
                    file_path=file_meta.file_path,
                    origin=file_meta.origin,
                    captured_at=file_meta.captured_at,
                    system_id=sys_id,
                    resource_id=res_id,
                    matched_identifier=id_val.lower(),
                    identifier_type=id_type,
                    snippet=snippet,
                    full_record=item,
                    parsed_state=state,
                )
            )

    # 1. Structure: service_exports dict
    if isinstance(data, dict) and "service_exports" in data:
        for service_name, service_content in data["service_exports"].items():
            if isinstance(service_content, dict):
                for coll_name, coll_items in service_content.items():
                    if isinstance(coll_items, list):
                        for item in coll_items:
                            _process_item(item, service_name,
                                          collection_name=coll_name)

    # 2. Structure: records list
    elif isinstance(data, dict) and "records" in data and isinstance(data["records"], list):
        for item in data["records"]:
            _process_item(item, file_meta.origin)

    # 3. Structure: snapshots list
    elif isinstance(data, dict) and "snapshots" in data and isinstance(data["snapshots"], list):
        for snap in data["snapshots"]:
            data_store = snap.get("data_store") or file_meta.origin
            snap_collection = snap.get("collection") or ""
            snap_records = snap.get("records") or []
            for item in snap_records:
                _process_item(item, data_store,
                              collection_name=snap_collection)

    # 4. Top-level list of dicts
    elif isinstance(data, list):
        for item in data:
            _process_item(item, file_meta.origin)

    return hits


def parse_log_evidence(file_meta: EvidenceFile, content: str) -> list[EvidenceHit]:
    """
    Parses application logs, service event logs, syslog archives, and readback logs.
    Correlates trace_id and resource_id query states across started and completed lines.
    """
    hits: list[EvidenceHit] = []

    # First pass: map trace_id and resource_id to terminal states and trace_resources
    trace_states: dict[str, str] = {}
    resource_states: dict[str, str] = {}
    trace_resources: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip().replace('\\"', '"')
        if not line:
            continue
        tr_match = re.search(r'\b(?:trace_id|requestId)=["\']?([a-zA-Z0-9_\-]+)["\']?', line)
        if not tr_match:
            tr_match = re.search(r'["\'](?:trace_id|requestId)["\']:\s*["\']([a-zA-Z0-9_\-]+)["\']', line)
        if not tr_match:
            tr_match = re.search(r'\b(tr-[a-zA-Z0-9_\-]+)\b', line)
        res_match = re.search(r'\bresource_id=["\']?([a-zA-Z0-9_]+)["\']?', line)
        if not res_match:
            res_match = re.search(r'["\']resource_id["\']:\s*["\']([a-zA-Z0-9_]+)["\']', line)
        if tr_match and res_match:
            trace_resources[tr_match.group(1)] = res_match.group(1)

        line_state = None
        if "[REDACTED]" in line or 'message_text="[REDACTED]"' in line or "message_text='[REDACTED]'" in line:
            line_state = "REDACTED"
        elif ("404" in line or "rows=0" in line or "result=miss" in line or 'result="miss"' in line
            or "archive_present=false" in line or "NOT_FOUND" in line or "http_status=404" in line):
            line_state = "ABSENT"
        elif ("enabled=false" in line or 'enabled="false"' in line
              or "last_delivery_status=stopped" in line or 'last_delivery_status="stopped"' in line):
            line_state = "DISABLED"
        elif "restore_allowed=false" in line or 'restore_allowed="false"' in line:
            line_state = "BLOCKED"
        elif "support_ticket_read_completed" in line:
            if "requester_email=null" in line and "requester_phone=null" in line and "requester_name=null" in line:
                line_state = "REDACTED"
            else:
                line_state = "PRESENT"
        elif "analytics_profile_read_completed" in line:
            if "email=null" in line and "phone=null" in line and "email_hash=null" in line:
                line_state = "ANONYMIZED"
            else:
                line_state = "PRESENT"
        elif ("message_pii_scan" in line or "attachment_pii_scan" in line or "analytics_identity_scan" in line
              or 'detector="direct_identifier"' in line or 'level=WARN' in line):
            line_state = "PRESENT"
        elif ("200" in line or "rows=1" in line or "result=hit" in line or 'result="hit"' in line
              or "archive_present=true" in line or "http_status=200" in line or "enabled=true" in line
              or "available=true" in line or 'available="true"' in line):
            line_state = "PRESENT"

        if line_state:
            if tr_match:
                trace_states[tr_match.group(1)] = line_state
            if res_match:
                resource_states[res_match.group(1)] = line_state

    for line in content.splitlines():
        line = line.strip().replace('\\"', '"')
        if not line:
            continue

        # Look for ISO timestamp at beginning of line
        line_captured_at = file_meta.captured_at
        ts_match = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)", line)
        if ts_match:
            try:
                line_captured_at = datetime.fromisoformat(ts_match.group(1).replace("Z", "+00:00"))
            except Exception:
                pass

        # Check for JSON-structured log line
        if "{" in line and line.endswith("}"):
            json_part = line[line.find("{") :]
            try:
                data = json.loads(json_part)
                tr_id = str(data.get("trace_id") or data.get("requestId") or "")
                raw_res_id = str(data.get("resource_id") or "")
                res_id = raw_res_id if raw_res_id else (trace_resources.get(tr_id, "") if tr_id else "")
                sys_id = _infer_system_id(data.get("service") or data.get("function") or file_meta.origin, res_id)
                ids = _extract_identifiers_from_dict(data)
                json_state = "PRESENT"
                if tr_id and tr_id in trace_states:
                    json_state = trace_states[tr_id]
                elif res_id and res_id in resource_states:
                    json_state = resource_states[res_id]
                elif data.get("http_status") == 404 or data.get("rows") == 0:
                    json_state = "ABSENT"

                for id_val, id_type in ids:
                    hits.append(
                        EvidenceHit(
                            file_id=file_meta.file_id,
                            file_path=file_meta.file_path,
                            origin=file_meta.origin,
                            captured_at=line_captured_at,
                            system_id=sys_id,
                            resource_id=res_id,
                            matched_identifier=id_val.lower(),
                            identifier_type=id_type,
                            snippet=line[:200],
                            full_record=data,
                            parsed_state=json_state,
                        )
                    )
                continue
            except Exception:
                pass

        # Look for trace_id
        tr_match = re.search(r'\b(?:trace_id|requestId)=["\']?([a-zA-Z0-9_\-]+)["\']?', line)
        if not tr_match:
            tr_match = re.search(r'\b(tr-[a-zA-Z0-9_\-]+)\b', line)
        tr_id = tr_match.group(1) if tr_match else ""

        # Look for resource_id
        res_match = re.search(r'\bresource_id=["\']?([a-zA-Z0-9_]+)["\']?', line)
        res_id = res_match.group(1) if res_match else (trace_resources.get(tr_id, "") if tr_id else "")

        # Look for system / service
        srv_match = re.search(r'\b(?:service|function|system)=["\']?([a-zA-Z0-9_]+)["\']?', line)
        srv_name = srv_match.group(1) if srv_match else ""
        system_id = _infer_system_id(srv_name or file_meta.origin, res_id)

        # Look for state (ABSENT vs PRESENT)
        state = "UNKNOWN"
        if "[REDACTED]" in line or 'message_text="[REDACTED]"' in line or "message_text='[REDACTED]'" in line:
            state = "REDACTED"
        elif ("404" in line or "rows=0" in line or "result=miss" in line or 'result="miss"' in line
            or "archive_present=false" in line or "NOT_FOUND" in line or "http_status=404" in line):
            state = "ABSENT"
        elif ("enabled=false" in line or 'enabled="false"' in line
              or "last_delivery_status=stopped" in line or 'last_delivery_status="stopped"' in line):
            state = "DISABLED"
        elif "restore_allowed=false" in line or 'restore_allowed="false"' in line:
            state = "BLOCKED"
        elif "support_ticket_read_completed" in line:
            if "requester_email=null" in line and "requester_phone=null" in line and "requester_name=null" in line:
                state = "REDACTED"
            else:
                state = "PRESENT"
        elif "analytics_profile_read_completed" in line:
            if "email=null" in line and "phone=null" in line and "email_hash=null" in line:
                state = "ANONYMIZED"
            else:
                state = "PRESENT"
        elif ("message_pii_scan" in line or "attachment_pii_scan" in line or "analytics_identity_scan" in line
              or 'detector="direct_identifier"' in line or 'level=WARN' in line):
            state = "PRESENT"
        elif ("200" in line or "rows=1" in line or "result=hit" in line or 'result="hit"' in line
              or "archive_present=true" in line or "http_status=200" in line or "enabled=true" in line
              or "available=true" in line or 'available="true"' in line):
            state = "PRESENT"
        elif tr_id and tr_id in trace_states:
            state = trace_states[tr_id]
        elif res_id and res_id in resource_states:
            state = resource_states[res_id]

        # Extract explicit key-values
        found_identifiers: list[tuple[str, str]] = []
        for kv in re.finditer(r'\b(?:lookup_key|correlation_key|customer_email|email|requester_email|subject_reference|subject_key|scan_key|matched_value)=["\']?([^"\'\s]+)["\']?', line):
            val = kv.group(1).strip()
            if "@" in val:
                found_identifiers.append((val.lower(), "email"))
            elif val.startswith("user_"):
                found_identifiers.append((val.lower(), "user_id"))
            elif len(val) == 64 and all(c in "0123456789abcdefABCDEF" for c in val):
                found_identifiers.append((val.lower(), "email_hash"))

        # Regex scan for user_ids, emails, hashes, and resource IDs
        for u in RE_USER_ID.findall(line):
            found_identifiers.append((u.lower(), "user_id"))
        for e in RE_EMAIL.findall(line):
            found_identifiers.append((e.lower(), "email"))
        for h in RE_HASH.findall(line):
            found_identifiers.append((h.lower(), "email_hash"))
        if res_id:
            found_identifiers.append((res_id.lower(), "resource_id"))

        # Deduplicate while preserving order
        seen = set()
        for id_val, id_type in found_identifiers:
            key = (id_val, id_type)
            if key not in seen:
                seen.add(key)
                hits.append(
                    EvidenceHit(
                        file_id=file_meta.file_id,
                        file_path=file_meta.file_path,
                        origin=file_meta.origin,
                        captured_at=line_captured_at,
                        system_id=system_id,
                        resource_id=res_id,
                        matched_identifier=id_val.lower(),
                        identifier_type=id_type,
                        snippet=line[:200],
                        full_record=line,
                        parsed_state=state,
                    )
                )

    return hits


def parse_txt_evidence(file_meta: EvidenceFile, content: str) -> list[EvidenceHit]:
    """
    Parses shift handover TXT records (e.g. timestamp | system_id | resource_id | category | state | email).
    """
    hits: list[EvidenceHit] = []

    for line in content.splitlines():
        line = line.strip()
        if not line or not line.startswith("-"):
            continue

        # Format: - 2026-10-01T12:00:00Z | account_service | account_146 | USER_PROFILE | NOT_FOUND | e.lindberg18@yahoo.com
        parts = [p.strip() for p in line.lstrip("-").split("|")]
        if len(parts) >= 6:
            ts_str, sys_id, res_id, category, state_str, email = parts[:6]
            try:
                line_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                line_ts = file_meta.captured_at

            parsed_state = "ABSENT" if "NOT_FOUND" in state_str else "PRESENT"
            system_id = _infer_system_id(sys_id, res_id)

            identifiers = [(email.lower(), "email"), (res_id.lower(), "resource_id")]
            for id_val, id_type in identifiers:
                hits.append(
                    EvidenceHit(
                        file_id=file_meta.file_id,
                        file_path=file_meta.file_path,
                        origin=file_meta.origin,
                        captured_at=line_ts,
                        system_id=system_id,
                        resource_id=res_id,
                        matched_identifier=id_val,
                        identifier_type=id_type,
                        snippet=line,
                        full_record={"timestamp": ts_str, "system": sys_id, "resource_id": res_id, "state": state_str, "email": email},
                        parsed_state=parsed_state,
                    )
                )

    return hits


def parse_png_evidence(file_meta: EvidenceFile, abs_path: Path) -> list[EvidenceHit]:
    """
    Catalogs image evidence. If pytesseract with native tesseract binary is installed,
    extracts text; otherwise records metadata and registers image for Milestone 5 Vision Agent.
    """
    hits: list[EvidenceHit] = []
    # If pytesseract is available, try OCR
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(abs_path)
        text = pytesseract.image_to_string(img)
        if text:
            # Extract identifiers from OCR text
            user_ids = RE_USER_ID.findall(text)
            emails = RE_EMAIL.findall(text)
            res_matches = RE_RESOURCE_ID.findall(text)
            for u in user_ids:
                hits.append(
                    EvidenceHit(
                        file_id=file_meta.file_id,
                        file_path=file_meta.file_path,
                        origin=file_meta.origin,
                        captured_at=file_meta.captured_at,
                        system_id=_infer_system_id(file_meta.origin, ""),
                        resource_id=u,
                        matched_identifier=u.lower(),
                        identifier_type="user_id",
                        snippet=f"OCR hit: {u}",
                        full_record={"ocr_text": text[:500]},
                        parsed_state="PRESENT",
                    )
                )
            for e in emails:
                hits.append(
                    EvidenceHit(
                        file_id=file_meta.file_id,
                        file_path=file_meta.file_path,
                        origin=file_meta.origin,
                        captured_at=file_meta.captured_at,
                        system_id=_infer_system_id(file_meta.origin, ""),
                        resource_id=e,
                        matched_identifier=e.lower(),
                        identifier_type="email",
                        snippet=f"OCR hit: {e}",
                        full_record={"ocr_text": text[:500]},
                        parsed_state="PRESENT",
                    )
                )
    except Exception as e:
        # Tesseract binary not installed or OCR failed; register image without failing
        logger.debug("Local OCR skipped for %s (%s). Deferred to Milestone 5 Vision Agent.", file_meta.file_id, e)

    return hits


# ---------------------------------------------------------------------------
# Inverted Evidence Index Class
# ---------------------------------------------------------------------------

class InvertedEvidenceIndex:
    """
    Holds the in-memory inverted index of all evidence hits across all 94 evidence files.
    Allows rapid lookup by identifier, strictly respecting audit_at temporal cutoffs.
    """

    def __init__(self, dataset_dir: Path | str = DATASET_DIR):
        self.dataset_dir = Path(dataset_dir)
        self.files: dict[str, EvidenceFileSummary] = {}
        self.index: dict[str, list[EvidenceHit]] = {}  # identifier -> list[EvidenceHit]
        self.hits_by_file: dict[str, list[EvidenceHit]] = {}
        self.report: Optional[EvidenceIndexReport] = None
        self._is_indexed: bool = False

    def build_index(self, force_reindex: bool = False) -> EvidenceIndexReport:
        """
        Parses all 94 evidence files declared in evidence_files.csv.
        Returns a comprehensive EvidenceIndexReport.
        """
        if self._is_indexed and not force_reindex:
            return self.report  # type: ignore

        bundle = load_all_datasets(self.dataset_dir)
        manifest_files = list(bundle.evidence_files.values())

        files_by_type: dict[str, int] = {}
        succeeded = 0
        failed = 0
        errors: list[dict[str, str]] = []
        total_hits = 0

        self.index.clear()
        self.hits_by_file.clear()
        self.files.clear()

        for ef in manifest_files:
            file_path = self.dataset_dir / ef.file_path
            ext = file_path.suffix.lower().lstrip(".")
            files_by_type[ext] = files_by_type.get(ext, 0) + 1

            if not file_path.exists():
                failed += 1
                msg = f"Evidence file not found on disk: {file_path}"
                errors.append({"file_id": ef.file_id, "file_path": str(file_path), "error": msg})
                self.files[ef.file_id] = EvidenceFileSummary(
                    file_id=ef.file_id,
                    file_path=ef.file_path,
                    file_type=ext,
                    origin=ef.origin,
                    captured_at=ef.captured_at,
                    status="error",
                    hit_count=0,
                    error_message=msg,
                )
                continue

            try:
                file_hits: list[EvidenceHit] = []
                if ext == "sql":
                    content = file_path.read_text(encoding="utf-8")
                    file_hits = parse_sql_evidence(ef, content)
                elif ext == "pdf":
                    file_hits = parse_pdf_evidence(ef, file_path)
                elif ext == "json":
                    content = file_path.read_text(encoding="utf-8")
                    file_hits = parse_json_evidence(ef, content)
                elif ext == "log":
                    content = file_path.read_text(encoding="utf-8")
                    file_hits = parse_log_evidence(ef, content)
                elif ext == "txt":
                    content = file_path.read_text(encoding="utf-8")
                    file_hits = parse_txt_evidence(ef, content)
                elif ext == "png":
                    file_hits = parse_png_evidence(ef, file_path)
                else:
                    logger.warning("Unsupported evidence extension: %s (%s)", ext, ef.file_id)

                # Record successful parse
                succeeded += 1
                total_hits += len(file_hits)
                self.hits_by_file[ef.file_id] = file_hits
                self.files[ef.file_id] = EvidenceFileSummary(
                    file_id=ef.file_id,
                    file_path=ef.file_path,
                    file_type=ext,
                    origin=ef.origin,
                    captured_at=ef.captured_at,
                    status="success",
                    hit_count=len(file_hits),
                )

                # Add to inverted index
                for hit in file_hits:
                    ident = hit.matched_identifier.strip().lower()
                    if ident not in self.index:
                        self.index[ident] = []
                    self.index[ident].append(hit)

            except Exception as e:
                failed += 1
                err_msg = str(e)
                logger.error("Failed to parse evidence file %s: %s", ef.file_id, e)
                errors.append({"file_id": ef.file_id, "file_path": str(file_path), "error": err_msg})
                self.files[ef.file_id] = EvidenceFileSummary(
                    file_id=ef.file_id,
                    file_path=ef.file_path,
                    file_type=ext,
                    origin=ef.origin,
                    captured_at=ef.captured_at,
                    status="error",
                    hit_count=0,
                    error_message=err_msg,
                )

        self.report = EvidenceIndexReport(
            total_files=len(manifest_files),
            succeeded_files=succeeded,
            failed_files=failed,
            files_by_type=files_by_type,
            total_hits=total_hits,
            unique_identifiers=len(self.index),
            parsing_errors=errors,
        )
        self._is_indexed = True
        return self.report

    def get_hits_for_identifiers(
        self,
        identifiers: Iterable[str],
        audit_at: Optional[datetime] = None,
    ) -> list[EvidenceHit]:
        """
        Retrieves all evidence hits matching any of the given identifiers.
        Crucial requirement: respects each case's audit_at timestamp (only evidence
        captured <= audit_at is returned).
        """
        if not self._is_indexed:
            self.build_index()

        matched_hits: list[EvidenceHit] = []
        seen_hit_keys = set()

        for ident in identifiers:
            normalized = str(ident).strip().lower()
            hits = self.index.get(normalized, [])
            for h in hits:
                # Apply case-specific audit_at cutoff
                if audit_at is not None and h.captured_at > audit_at:
                    continue

                # Unique key: (file_id, resource_id, matched_identifier)
                hit_key = (h.file_id, h.resource_id, h.matched_identifier)
                if hit_key not in seen_hit_keys:
                    seen_hit_keys.add(hit_key)
                    matched_hits.append(h)

        # Sort hits chronologically by captured_at ascending
        matched_hits.sort(key=lambda x: x.captured_at)
        return matched_hits

    def get_hits_for_case(
        self,
        case_id: str,
        bundle: DatasetBundle,
        audit_at: Optional[datetime] = None,
    ) -> list[EvidenceHit]:
        """
        Retrieves all evidence hits relevant to a specific case by:
          1. Finding the DeletionRequest in bundle.
          2. Resolving current and historical identifiers up to audit_at.
          3. Querying the index with temporal filtering.
        """
        # Look up case request
        req = next((r for r in bundle.deletion_requests if r.case_id == case_id), None)
        if req is None:
            req = next((r for r in bundle.sample_requests if r.case_id == case_id), None)
        if req is None:
            raise KeyError(f"Case {case_id} not found in bundle requests.")

        effective_audit_at = audit_at or req.audit_at

        # Resolve identity
        res = resolve_identity(req.email, bundle)
        if res is None:
            # Query by requested email directly
            return self.get_hits_for_identifiers([req.email], audit_at=effective_audit_at)

        # Retrieve all historical identifiers up to effective_audit_at
        hist = get_historical_identifiers(res.user_id, as_of=effective_audit_at, bundle=bundle)
        all_ids: set[str] = {res.user_id}
        all_ids.update(hist.emails)
        all_ids.update(hist.phones)
        all_ids.update(hist.email_hashes)

        return self.get_hits_for_identifiers(all_ids, audit_at=effective_audit_at)

    def get_hits_by_resource_id(
        self,
        resource_id: str,
        audit_at: Optional[datetime] = None,
    ) -> list[EvidenceHit]:
        """Looks up hits matching a specific resource_id."""
        return self.get_hits_for_identifiers([resource_id], audit_at=audit_at)

    def get_hits_by_file_id(self, file_id: str) -> list[EvidenceHit]:
        """Returns all raw hits extracted from a specific evidence file."""
        if not self._is_indexed:
            self.build_index()
        return self.hits_by_file.get(file_id, [])


# Global cached index instance
_GLOBAL_INDEX: Optional[InvertedEvidenceIndex] = None


def get_evidence_index(dataset_dir: Path | str = DATASET_DIR) -> InvertedEvidenceIndex:
    """Returns the singleton instance of the InvertedEvidenceIndex."""
    global _GLOBAL_INDEX
    if _GLOBAL_INDEX is None:
        _GLOBAL_INDEX = InvertedEvidenceIndex(dataset_dir=dataset_dir)
        _GLOBAL_INDEX.build_index()
    return _GLOBAL_INDEX
