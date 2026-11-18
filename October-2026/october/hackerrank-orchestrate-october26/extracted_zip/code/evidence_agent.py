"""
evidence_agent.py -- Evidence Investigation Agent
Milestone 5: Reconstruct resource state at audit_at using the inverted evidence index,
system_activity.csv, and all available evidence (including PNG via OCR / Gemini Vision).
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
SYSTEM_ACTIVITY_CSV = DATASET_DIR / "system_activity.csv"
_OCR_CACHE_FILE = REPO_ROOT / "code" / ".ocr_cache.json"


def _load_env_file() -> None:
    if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"].strip():
        return
    for base in [Path("."), REPO_ROOT, REPO_ROOT.parent]:
        env_file = base / ".env"
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            os.environ["GEMINI_API_KEY"] = val
                            return
            except Exception:
                pass


_load_env_file()

if str(REPO_ROOT / "code") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "code"))

from data_loader import (
    DatasetBundle,
    DeletionRequest,
    DeletionRule,
    HistoricalIdentifiers,
    SystemActivity,
    get_historical_identifiers,
    load_all_datasets,
    resolve_identity,
)
from evidence_indexer import (
    EvidenceHit,
    InvertedEvidenceIndex,
    RE_EMAIL,
    RE_RESOURCE_ID,
    RE_USER_ID,
    _infer_system_id,
    get_evidence_index,
)
from policy_engine import ResourceEvaluation

logger = logging.getLogger("evidence_agent")

ALL_SYSTEMS = [
    "account_service",
    "analytics_platform",
    "backup_service",
    "export_service",
    "identity_service",
    "integration_service",
    "search_service",
    "security_service",
    "support_platform",
]

CATEGORY_SYSTEM_MAP = {
    "USER_PROFILE": "account_service",
    "ACCOUNT_TOMBSTONE": "identity_service",
    "SECONDARY_IDENTIFIER": "identity_service",
    "SEARCH_INDEX_ENTRY": "search_service",
    "CACHE_ENTRY": "account_service",
    "SUPPORT_MESSAGE": "support_platform",
    "SUPPORT_ATTACHMENT": "support_platform",
    "ANALYTICS_PROFILE": "analytics_platform",
    "PRODUCT_TELEMETRY": "analytics_platform",
    "USER_EXPORT": "export_service",
    "MARKETING_PROFILE": "integration_service",
    "INTEGRATION_DATA_FLOW": "integration_service",
    "EMAIL_DELIVERY_LOG": "integration_service",
    "SECURITY_AUDIT_LOG": "security_service",
    "LEGAL_HOLD_RECORD": "security_service",
    "BACKUP_ARCHIVE": "backup_service",
}

CATEGORY_ACTION_MAP = {
    "USER_PROFILE": "DELETE",
    "SECONDARY_IDENTIFIER": "DELETE",
    "SEARCH_INDEX_ENTRY": "DELETE",
    "CACHE_ENTRY": "DELETE",
    "SUPPORT_MESSAGE": "REDACT",
    "SUPPORT_ATTACHMENT": "DELETE",
    "ANALYTICS_PROFILE": "ANONYMIZE",
    "PRODUCT_TELEMETRY": "ANONYMIZE",
    "USER_EXPORT": "DELETE",
    "MARKETING_PROFILE": "DELETE",
    "INTEGRATION_DATA_FLOW": "DISABLE",
    "EMAIL_DELIVERY_LOG": "REDACT",
    "SECURITY_AUDIT_LOG": "RETAIN",
    "LEGAL_HOLD_RECORD": "RETAIN",
    "BACKUP_ARCHIVE": "RETAIN",
    "ACCOUNT_TOMBSTONE": "REDACT",
}

RESOURCE_PREFIX_TO_CATEGORY = {
    "account_": "USER_PROFILE",
    "tombstone_": "ACCOUNT_TOMBSTONE",
    "search_": "SEARCH_INDEX_ENTRY",
    "analytics_": "ANALYTICS_PROFILE",
    "backup_": "BACKUP_ARCHIVE",
    "export_": "USER_EXPORT",
    "support_": "SUPPORT_MESSAGE",
    "data_flow_": "INTEGRATION_DATA_FLOW",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "object_": "SUPPORT_ATTACHMENT",
    "marketing_": "MARKETING_PROFILE",
}


@dataclass
class GeminiUsage:
    """Tracks cumulative Gemini Vision API token consumption."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0
    cache_hits: int = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.total_tokens += prompt + completion
        self.call_count += 1

    def to_dict(self):
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
            "cache_hits": self.cache_hits,
        }


_GEMINI_USAGE = GeminiUsage()


def get_gemini_usage() -> GeminiUsage:
    return _GEMINI_USAGE


_ocr_cache = {}
_ocr_cache_loaded = False


def _load_ocr_cache() -> None:
    global _ocr_cache, _ocr_cache_loaded
    if _ocr_cache_loaded:
        return
    if _OCR_CACHE_FILE.exists():
        try:
            _ocr_cache = json.loads(_OCR_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _ocr_cache = {}
    _ocr_cache_loaded = True


def _save_ocr_cache() -> None:
    try:
        _OCR_CACHE_FILE.write_text(json.dumps(_ocr_cache, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not save OCR cache: %s", exc)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _extract_text_from_image(abs_path, file_id, usage):
    """
    Extracts text from a PNG image.
    Strategy: cache check -> local OCR -> llm_provider.call_vision (Gemini) -> gap note.
    Returns (text, method).
    """
    _load_ocr_cache()
    sha = _file_sha256(abs_path)
    if sha in _ocr_cache and _ocr_cache[sha]:
        if hasattr(usage, "cache_hits"):
            usage.cache_hits += 1
        return _ocr_cache[sha], "cache"

    ocr_text = ""
    ocr_succeeded = False
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(abs_path)
        ocr_text = pytesseract.image_to_string(img).strip()
        ocr_succeeded = True
    except Exception as ocr_err:
        logger.debug("Local OCR unavailable for %s: %s", file_id, ocr_err)

    if ocr_succeeded and ocr_text:
        _ocr_cache[sha] = ocr_text
        _save_ocr_cache()
        return ocr_text, "ocr"

    # Use llm_provider for Vision (Gemini only — Groq has no image support)
    try:
        import llm_provider
        from pathlib import Path as _Path
        prompt = (
            "You are an expert OCR and auditing system. "
            "Extract ALL text from this image exactly as shown, preserving layout, tables, "
            "column headers, rows, labels, status values, IDs, timestamps, and keys. "
            "Do not invent facts or hallucinate text."
        )
        vision_text, method = llm_provider.call_vision(
            _Path(abs_path),
            prompt,
            model_gemini="gemini-1.5-flash",
            max_retries=1,
        )
        if vision_text:
            # Track usage in GeminiUsage for backward-compatible reporting
            usage.add(150, 100)  # estimated tokens
            _ocr_cache[sha] = vision_text
            _save_ocr_cache()
            return vision_text, method
        logger.debug("Vision returned empty result for %s (%s).", file_id, method)
    except Exception as exc:
        logger.warning("Vision extraction failed for %s: %s.", file_id, type(exc).__name__)

    return "", "empty_ocr"


def _load_system_activity(audit_at=None):
    rows = []
    if not SYSTEM_ACTIVITY_CSV.exists():
        logger.warning("system_activity.csv not found at %s", SYSTEM_ACTIVITY_CSV)
        return rows
    with SYSTEM_ACTIVITY_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                event_time = datetime.fromisoformat(row["event_time"].replace("Z", "+00:00"))
            except Exception:
                continue
            if audit_at is not None and event_time > audit_at:
                continue
            rows.append(SystemActivity(
                activity_id=row.get("activity_id", ""),
                event_time=event_time,
                event_type=row.get("event_type", ""),
                source_system=row.get("source_system", ""),
                target_system=row.get("target_system", ""),
                resource_id=row.get("resource_id", ""),
                reported_result=row.get("reported_result", ""),
                details=row.get("details", ""),
            ))
    return rows


def _activity_mentions_identifiers(activity, identifiers):
    haystack = (activity.resource_id + " " + activity.details).lower()
    for ident in identifiers:
        if ident.lower() in haystack:
            return True
    return False


def _pick_state_from_hits(hits, resource_id, system_id):
    """
    Synthesizes observed state for a (system_id, resource_id) pair from evidence hits.
    Detects replication drift and returns (state, evidence_ids, conflict_details).
    """
    relevant = [
        h for h in hits
        if h.resource_id.lower() == resource_id.lower() or h.system_id == system_id
    ]
    if not relevant:
        return "UNKNOWN", [], []

    relevant.sort(key=lambda h: h.captured_at, reverse=True)

    _REPLICA_KEYWORDS = ("replica", "regional", "reporting", "failover", "secondary")
    primary_hits = [h for h in relevant if not any(kw in h.origin.lower() for kw in _REPLICA_KEYWORDS)]
    replica_hits = [h for h in relevant if any(kw in h.origin.lower() for kw in _REPLICA_KEYWORDS)]

    state_priority = {
        "ABSENT": 5, "ANONYMIZED": 4, "REDACTED": 3,
        "DISABLED": 3, "BLOCKED": 3, "RETAIN": 3,
        "PRESENT": 2, "ACTIVE": 2, "UNKNOWN": 1,
    }

    def _best_state(hit_list):
        if not hit_list:
            return "UNKNOWN"
        best = "UNKNOWN"
        for h in hit_list:
            s = h.parsed_state.upper()
            if state_priority.get(s, 0) > state_priority.get(best, 0):
                best = s
        return best

    primary_state = _best_state(primary_hits)
    replica_state = _best_state(replica_hits) if replica_hits else primary_state

    evidence_ids = list({h.file_id for h in relevant})
    conflict_details = []

    if (replica_hits and primary_state != "UNKNOWN" and replica_state != "UNKNOWN"
            and primary_state != replica_state):
        conflict_msg = (
            f"Replication drift on {system_id}/{resource_id}: "
            f"primary={primary_state}, replica={replica_state} "
            f"(files: {[h.file_id for h in replica_hits[:3]]})"
        )
        conflict_details.append(conflict_msg)
        return "CONFLICTING", evidence_ids, conflict_details

    final_state = primary_state if primary_state != "UNKNOWN" else replica_state
    return final_state, evidence_ids, conflict_details


def _data_category_from_resource_id(resource_id):
    rid = resource_id.lower()
    for prefix, category in RESOURCE_PREFIX_TO_CATEGORY.items():
        if rid.startswith(prefix):
            return category
    return "USER_PROFILE"


def _rule_for_category(category, rules):
    for rule in rules:
        if rule.data_category == category:
            return rule.rule_id, rule.required_action
    action = CATEGORY_ACTION_MAP.get(category, "DELETE")
    return "", action


def _reinspect_png_hits(index, identifiers, audit_at, usage):
    """
    Re-inspects PNG files via OCR/Gemini Vision to extract additional evidence hits.
    Only processes files at or before audit_at.
    """
    additional_hits = []
    if not index._is_indexed:
        index.build_index()

    for file_id, summary in index.files.items():
        if summary.file_type != "png":
            continue
        if audit_at is not None and summary.captured_at > audit_at:
            continue

        png_path = DATASET_DIR / summary.file_path
        if not png_path.exists():
            continue

        text, method = _extract_text_from_image(png_path, file_id, usage)
        if not text:
            logger.info(
                "PNG %s could not be inspected via OCR or Gemini Vision (method=%s). Evidence gap recorded.",
                file_id, method,
            )
            continue

        found_user_ids = set(u.lower() for u in RE_USER_ID.findall(text))
        found_emails = set(e.lower() for e in RE_EMAIL.findall(text))
        found_res_ids = set(r.lower() for r in RE_RESOURCE_ID.findall(text))
        all_found = found_user_ids | found_emails | found_res_ids

        matched_identifiers = all_found & identifiers
        if not matched_identifiers:
            continue

        for ident in matched_identifiers:
            id_type = (
                "user_id" if ident.startswith("user_") else
                "email" if "@" in ident else
                "resource_id"
            )
            res_id = next((r for r in found_res_ids if r in text.lower()), ident)
            sys_id = _infer_system_id(summary.origin, res_id)
            snippet = f"PNG OCR ({method}): {ident}"
            additional_hits.append(EvidenceHit(
                file_id=file_id,
                file_path=summary.file_path,
                origin=summary.origin,
                captured_at=summary.captured_at,
                system_id=sys_id,
                resource_id=res_id,
                matched_identifier=ident,
                identifier_type=id_type,
                snippet=snippet[:200],
                full_record={"ocr_text": text[:500], "method": method},
                parsed_state="PRESENT",
            ))

    return additional_hits


@dataclass
class InvestigationResult:
    """Full output of investigate_case()."""
    case_id: str
    user_id: Optional[str]
    audit_at: datetime
    evaluations: list
    evidence_gaps: list
    image_methods: dict
    gemini_usage: GeminiUsage


def investigate_case(case_id, bundle, index, usage=None):
    """
    Investigates a single deletion case end-to-end.

    Steps:
      1. Resolve identity (current + historical) up to audit_at.
      2. Collect evidence hits from the inverted index.
      3. Re-inspect PNG files via OCR / Gemini Vision.
      4. Augment with system_activity.csv events.
      5. Synthesize resource states across all systems.
      6. Return ResourceEvaluation objects for the policy engine.

    Preserves uncertainty and contradictions; never assumes deletion from absence.
    """
    if usage is None:
        usage = GeminiUsage()

    req = next((r for r in bundle.deletion_requests if r.case_id == case_id), None)
    if req is None:
        req = next((r for r in bundle.sample_requests if r.case_id == case_id), None)
    if req is None:
        raise KeyError(f"Case {case_id} not found in bundle.")

    audit_at = req.audit_at
    evidence_gaps = []
    image_methods = {}

    resolution = resolve_identity(req.email, bundle)
    user_id = resolution.user_id if resolution else None

    all_identifiers = {req.email.lower()}
    if resolution:
        hist = get_historical_identifiers(resolution.user_id, as_of=audit_at, bundle=bundle)
        all_identifiers.add(resolution.user_id.lower())
        all_identifiers.update(e.lower() for e in hist.emails)
        all_identifiers.update(p for p in hist.phones if p)
        all_identifiers.update(eh.lower() for eh in hist.email_hashes if eh)

    all_hits = index.get_hits_for_identifiers(all_identifiers, audit_at=audit_at)

    png_hits = _reinspect_png_hits(index, all_identifiers, audit_at, usage)
    all_hits.extend(png_hits)

    for file_id, summary in index.files.items():
        if summary.file_type == "png" and (audit_at is None or summary.captured_at <= audit_at):
            png_path = DATASET_DIR / summary.file_path
            if png_path.exists():
                sha = _file_sha256(png_path)
                image_methods[file_id] = "cache_hit" if sha in _ocr_cache else "not_inspected"

    activities = _load_system_activity(audit_at=audit_at)
    relevant_activities = [
        a for a in activities
        if _activity_mentions_identifiers(a, all_identifiers)
        or any(h.resource_id and a.resource_id == h.resource_id for h in all_hits)
    ]

    resource_map = {}
    for hit in all_hits:
        key = (hit.system_id, hit.resource_id)
        resource_map.setdefault(key, []).append(hit)

    for act in relevant_activities:
        if act.resource_id:
            sys_candidate = act.target_system if act.target_system in ALL_SYSTEMS else (act.source_system if act.source_system in ALL_SYSTEMS else (act.target_system or act.source_system))
            sys_id = _infer_system_id(sys_candidate, act.resource_id)
            key = (sys_id, act.resource_id)
            if key not in resource_map:
                resource_map[key] = []

    evaluations = []
    rules = bundle.deletion_rules

    for (sys_id, res_id), hits in resource_map.items():
        if not res_id:
            continue

        data_category = _data_category_from_resource_id(res_id)
        rule_id, required_action = _rule_for_category(data_category, rules)

        if not hits:
            # Check if this resource has activity events
            matched_act = next((a for a in relevant_activities if a.resource_id == res_id and a.reported_result == "FAILED"), None)
            if not matched_act:
                matched_act = next((a for a in relevant_activities if a.resource_id == res_id), None)
            cited_ev = matched_act.activity_id if matched_act else ""

            # If deletion explicitly failed in activity, it is definitely PRESENT
            if matched_act and matched_act.reported_result == "FAILED":
                state = "PRESENT"
                ev_id = cited_ev
                is_comp = False
                note = f"Deletion of {res_id} on {sys_id} failed per activity {cited_ev}; record remains present."
            elif matched_act and matched_act.event_type in ("LINK_RESOURCE_IDENTITY", "CATALOG_ATTACHMENT", "INDEX_CATALOG") and required_action == "DELETE":
                # A catalog activity confirmed the resource belongs to the user and no deletion evidence exists before audit_at
                state = "PRESENT"
                ev_id = cited_ev
                is_comp = False
                note = f"Resource {res_id} on {sys_id} linked to user via activity {cited_ev}; remaining record not deleted."
            else:
                state = "UNKNOWN"
                ev_id = cited_ev
                is_comp = False
                note = f"Resource {res_id} referenced in activity {cited_ev} but has no evidence hit; cannot confirm state."
                evidence_gaps.append(note)

            evaluations.append(ResourceEvaluation(
                resource_id=res_id,
                system_id=sys_id,
                data_category=data_category,
                applicable_rule_id=rule_id,
                required_action=required_action,
                observed_state=state,
                evidence_id=ev_id,
                is_compliant=is_comp,
                uncertainty_note=note,
                conflict_details=[],
            ))
            continue

        state, ev_ids, conflicts = _pick_state_from_hits(hits, res_id, sys_id)
        ev_id = ev_ids[0] if ev_ids else ""

        is_compliant = None
        uncertainty_note = None

        if state == "UNKNOWN":
            is_compliant = None
            uncertainty_note = (
                f"State of {res_id} on {sys_id} is UNKNOWN; "
                "cannot determine compliance from available evidence."
            )
            evidence_gaps.append(uncertainty_note)
        elif state == "CONFLICTING":
            is_compliant = False
            uncertainty_note = (
                f"Conflicting evidence for {res_id} on {sys_id}. Manual investigation required."
            )
        else:
            compliant_states = {
                "DELETE": {"ABSENT"},
                "REDACT": {"REDACTED"},
                "ANONYMIZE": {"ANONYMIZED"},
                "RETAIN": {"PRESENT", "BLOCKED", "RETAIN"},
                "DISABLE": {"DISABLED"},
                "BLOCK": {"BLOCKED"},
            }
            required_states = compliant_states.get(required_action, set())
            is_compliant = state in required_states

        evaluations.append(ResourceEvaluation(
            resource_id=res_id,
            system_id=sys_id,
            data_category=data_category,
            applicable_rule_id=rule_id,
            required_action=required_action,
            observed_state=state,
            evidence_id=ev_id,
            is_compliant=is_compliant,
            uncertainty_note=uncertainty_note,
            conflict_details=conflicts,
        ))

    for act in relevant_activities:
        if act.event_type in (
            "SYNC_RECORD", "EXPORT_DATA", "REPLICATE_RECORD",
            "RESTORE_BACKUP", "INDEX_RECORD",
        ):
            if act.reported_result != "SUCCESS":
                continue
            res_id = act.resource_id
            if not res_id:
                continue
            data_flow_category = "MARKETING_PROFILE"
            _, df_action = _rule_for_category(data_flow_category, rules)
            sys_id = _infer_system_id(act.target_system or act.source_system, res_id)
            existing = next((e for e in evaluations if e.resource_id == res_id), None)
            if existing is None:
                evaluations.append(ResourceEvaluation(
                    resource_id=res_id,
                    system_id=sys_id,
                    data_category=data_flow_category,
                    applicable_rule_id="",
                    required_action=df_action,
                    observed_state="ACTIVE",
                    evidence_id=act.activity_id,
                    is_compliant=False,
                    uncertainty_note=(
                        f"System activity {act.activity_id} shows a successful "
                        f"{act.event_type} into {act.target_system} that may recreate user data."
                    ),
                    conflict_details=[],
                ))

    tombstone_res_ids = {e.resource_id for e in evaluations if e.data_category == "ACCOUNT_TOMBSTONE"}
    for tomb_res_id in tombstone_res_ids:
        ev = next(e for e in evaluations if e.resource_id == tomb_res_id)
        if ev.observed_state == "PRESENT":
            ev.required_action = "REDACT"

    seen = {}
    deduped = []
    for ev in evaluations:
        key = (ev.system_id, ev.resource_id)
        if key in seen:
            deduped[seen[key]] = ev
        else:
            seen[key] = len(deduped)
            deduped.append(ev)

    return InvestigationResult(
        case_id=case_id,
        user_id=user_id,
        audit_at=audit_at,
        evaluations=deduped,
        evidence_gaps=evidence_gaps,
        image_methods=image_methods,
        gemini_usage=usage,
    )


def investigate_all_cases(bundle, index, case_ids=None):
    """
    Runs investigate_case() over all (or a subset of) deletion requests.
    Uses a single shared GeminiUsage accumulator and shared OCR cache.
    Returns dict[case_id -> InvestigationResult].
    """
    shared_usage = GeminiUsage()
    results = {}

    if case_ids is None:
        targets = [r.case_id for r in bundle.deletion_requests]
    else:
        targets = case_ids

    for case_id in targets:
        try:
            result = investigate_case(case_id, bundle, index, usage=shared_usage)
            results[case_id] = result
        except Exception as exc:
            logger.error("investigate_case(%s) failed: %s", case_id, exc, exc_info=True)
            req = next((r for r in bundle.deletion_requests if r.case_id == case_id), None)
            results[case_id] = InvestigationResult(
                case_id=case_id,
                user_id=None,
                audit_at=req.audit_at if req else datetime.now(timezone.utc),
                evaluations=[],
                evidence_gaps=[f"Investigation failed with exception: {exc}"],
                image_methods={},
                gemini_usage=shared_usage,
            )

    return results


def load_agent(dataset_dir=None):
    """
    Loads the dataset bundle and builds (or reuses) the global evidence index.
    Call once at startup; reuse across all cases.
    """
    ddir = Path(dataset_dir) if dataset_dir else DATASET_DIR
    bundle = load_all_datasets(ddir)
    index = get_evidence_index(ddir)
    return bundle, index