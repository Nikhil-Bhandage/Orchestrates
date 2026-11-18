"""
intent_classifier.py — Deletion Intent Classifier
Milestone 2: Hybrid Intent Classification (Deterministic Rule-Based + Gemini API).

Determines whether a DeletionRequest's `request_text` actually authorizes deletion.
Per AGENTS.md §6.2 and problem_statement.md:
  - "First determine whether request_text authorizes deletion. A request for access,
     correction, export, marketing opt-out, or another non-deletion action is
     NOT_APPLICABLE, even if other fields resemble a deletion case."
  - "For NOT_APPLICABLE, use an empty JSON array ([]) because no deletion or
     deletion verification is authorized."

Architecture:
  1. Deterministic heuristic classifier:
     - Handles multilingual text (English, Portuguese, Spanish, French, Japanese, Korean, German, etc.)
     - High-precision pattern matching for non-deletion intents (access, correction, export,
       opt-out, retention instructions) vs deletion authorizations.
     - 100% deterministic, zero latency, zero API quota usage.
  2. Gemini API classifier (gemini-1.5-flash):
     - Activated when GEMINI_API_KEY is provided.
     - Batched requests (up to 20 per call) to respect free-tier rate limits (15 RPM).
     - Strict JSON array schema output with temperature=0 for reproducibility.
     - Exponential backoff retry logic on 429/503 errors.
     - Built-in token usage tracking for code/evaluation/usage_report.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional
import sys as _sys
from pathlib import Path as _Path
if str(_Path(__file__).resolve().parent) not in _sys.path:
    _sys.path.insert(0, str(_Path(__file__).resolve().parent))

# Configure logger
logger = logging.getLogger("intent_classifier")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class IntentClassificationResult:
    """Classification outcome for a single deletion request."""
    case_id: str
    intent: str  # "DELETION_REQUEST" | "NOT_APPLICABLE"
    confidence: float
    method: str  # "deterministic" | "gemini_llm"
    reasoning_note: str

    @property
    def is_deletion_authorized(self) -> bool:
        return self.intent == "DELETION_REQUEST"


@dataclass
class LLMUsageStats:
    """Accumulated LLM token usage and call statistics."""
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error_count: int = 0
    total_time_seconds: float = 0.0

    @property
    def estimated_cost_usd(self) -> float:
        # Free-tier usage costs $0.00
        return 0.0


# ---------------------------------------------------------------------------
# Deterministic Heuristic Classifier
# ---------------------------------------------------------------------------

# Multilingual keywords indicating explicit non-deletion intents
NON_DELETION_PATTERNS = [
    # Explicit instructions to keep or not delete
    r"\bkeep\s+(?:the|my|this)\s+(?:account|profile|records?)\b",
    r"\bleave\s+(?:the|my|this)\s+(?:account|profile|records?|purchase|order)\b",
    r"\bdo\s+not\s+(?:delete|close|erase|remove)\b",
    r"\bdon'?t\s+(?:delete|close|erase|remove)\b",
    r"\bnot\s+asking\s+for\s+deletion\b",
    r"\bnot\s+a\s+request\s+to\s+erase\b",
    r"\bleave\s+the\s+account\s+active\b",
    r"\bcontinue\s+using\s+(?:the\s+service|the\s+account|my\s+account)\b",
    r"\bwithout\s+removing\s+(?:any|my)\b",
    
    # Subject Access Requests (SAR / Access / Info only)
    r"\bdownload\s+my\s+account\s+information\b",
    r"\bcopy\s+of\s+last\s+year'?s?\s+invoices\b",
    r"\bcopy\s+of\s+the\s+information\s+held\b",
    r"\bportable\s+format\b",
    r"\bwhat\s+personal\s+information\s+you\s+hold\b",
    r"\binformation\s+request\b",
    r"\bsend\s+me\s+a\s+copy\b",

    # Rectification / Correction only
    r"\bmobile\s+number.*(?:is\s+out\s+of\s+date|replace\s+it)\b",
    r"\bsurname\s+is\s+misspelled\b",
    r"\bcorrect\s+it\s+without\s+removing\b",
    r"\bchange\s+the\s+email\s+address\b",
    r"\bupdate\s+my\s+(?:address|phone|email|name|profile)\b",

    # Marketing opt-out only
    r"\bstop\s+the\s+promotional\s+emails?\b",
    r"\bmarketing\s+lists?\s+only\b",
    r"\bunsubscribe\s+from\s+marketing\b",
    r"\bopt-?out\s+of\s+marketing\b",

    # Account recovery / login issue only
    r"\bcan'?t\s+access\s+my\s+profile\b",
    r"\bresetting\s+the\s+login\b",
    r"\bpassword\s+reset\b",
]

# Multilingual keywords confirming deletion authorization
DELETION_PATTERNS = [
    # English inflections and phrases
    r"\bdelet(?:e|ed|ing|ion|ions)\b",
    r"\beras(?:e|ed|ing|ure|ures)\b",
    r"\bremov(?:e|ed|ing|al|als)\b",
    r"\bclos(?:e|ed|ing)\b",
    r"\b(?:account|profile)\s+(?:page\s+)?is\s+gone\b",
    r"\bcannot\s+identify\s+me\b",
    r"\bleft\s+behind\b",
    r"\bpurge\b",
    r"\bforget\s+me\b",
    r"\bright\s+to\s+be\s+forgotten\b",

    # Portuguese
    r"\bexclus[aã]o(?:\s+permanente)?\b",
    r"\bexcluir\b",
    r"\bapagar\b",

    # Spanish
    r"\beliminaci[oó]n(?:\s+permanente)?\b",
    r"\beliminar\b",
    r"\bborrar\b",

    # French
    r"\bsuppression(?:\s+d[eé]finitive)?\b",
    r"\bsupprimer\b",
    r"\beffacer\b",
    r"\beffacement\b",

    # German
    r"\bl[oö]sch(?:ung|en)?\b",

    # Italian
    r"\bcancell(?:azione|are)\b",

    # Japanese
    r"削除",
    r"完全な削除",
    r"消去",

    # Korean
    r"영구\s*삭제",
    r"삭제",
]

_COMPILED_NON_DELETION = [re.compile(p, re.IGNORECASE) for p in NON_DELETION_PATTERNS]
_COMPILED_DELETION = [re.compile(p, re.IGNORECASE) for p in DELETION_PATTERNS]


def classify_deterministic(case_id: str, request_text: str) -> IntentClassificationResult:
    """
    Evaluates request_text with compiled regex patterns to identify
    whether deletion is authorized (DELETION_REQUEST) or not (NOT_APPLICABLE).
    """
    if not request_text or not request_text.strip():
        return IntentClassificationResult(
            case_id=case_id,
            intent="NOT_APPLICABLE",
            confidence=0.99,
            method="deterministic",
            reasoning_note="Empty or whitespace-only request_text does not authorize deletion."
        )

    text = request_text.strip()

    # Check for non-deletion triggers first
    non_del_matches = [p.pattern for p in _COMPILED_NON_DELETION if p.search(text)]
    del_matches = [p.pattern for p in _COMPILED_DELETION if p.search(text)]

    if non_del_matches:
        # Non-deletion trigger found (e.g. "keep account", "misspelled", "marketing only")
        reason = f"Non-deletion intent detected ({len(non_del_matches)} signal(s)): {non_del_matches[0]}"
        return IntentClassificationResult(
            case_id=case_id,
            intent="NOT_APPLICABLE",
            confidence=0.98,
            method="deterministic",
            reasoning_note=reason
        )

    if del_matches:
        # Clear deletion authorization found
        reason = f"Deletion authorization confirmed ({len(del_matches)} signal(s)): {del_matches[0]}"
        return IntentClassificationResult(
            case_id=case_id,
            intent="DELETION_REQUEST",
            confidence=0.98,
            method="deterministic",
            reasoning_note=reason
        )

    # If neither pattern matched definitively, check default English vocabulary
    lower = text.lower()
    if any(w in lower for w in ["close", "cancel my account", "terminate account"]):
        return IntentClassificationResult(
            case_id=case_id,
            intent="DELETION_REQUEST",
            confidence=0.85,
            method="deterministic",
            reasoning_note="General account closure language detected."
        )

    # Ambiguous or unclassified case: default to NOT_APPLICABLE with lower confidence
    return IntentClassificationResult(
        case_id=case_id,
        intent="NOT_APPLICABLE",
        confidence=0.60,
        method="deterministic",
        reasoning_note="No explicit deletion authorization keywords found in request_text."
    )


# ---------------------------------------------------------------------------
# Gemini API Classifier (Batch mode)
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """You are a privacy compliance auditor assessing data subject requests.
For each request below, determine whether the user is authorizing the permanent DELETION of their account/personal data, or if this request is NOT_APPLICABLE for deletion.

Guidelines:
1. "DELETION_REQUEST": The user explicitly or implicitly requests account deletion, profile erasure, removal of personal data, account closure, or right to be forgotten. This applies across English, French, Spanish, Portuguese, German, Italian, Japanese, Korean, etc.
2. "NOT_APPLICABLE": The user is requesting something other than deletion, including:
   - Data access / Subject Access Request (e.g. asking what data is held, downloading data, requesting invoice copies)
   - Data correction / rectification (e.g. fixing misspelled surname, updating phone number, changing email)
   - Marketing opt-out only (e.g. unsubscribing from newsletters while keeping the account)
   - Account recovery / login help (e.g. password reset while keeping the account)
   - Any message stating "do not delete", "keep my account", "not asking for deletion", or "leave the account active"

Requests to classify:
{batch_json}

Respond ONLY with a valid JSON array of objects. Do not include markdown code block backticks if possible, or use standard ```json.
Each object must have the following exact schema:
[
  {{
    "case_id": "case_xx",
    "intent": "DELETION_REQUEST" or "NOT_APPLICABLE",
    "confidence": 0.0 to 1.0,
    "reasoning_note": "Brief explanation"
  }}
]
"""


def _build_batch_prompt(cases: list[dict[str, str]]) -> str:
    """Builds the LLM prompt for a batch of cases."""
    batch_json = json.dumps(cases, indent=2, ensure_ascii=False)
    return PROMPT_TEMPLATE.format(batch_json=batch_json)


def _call_gemini_batch(
    cases: list[dict[str, str]],
    api_key: str,
    model_name: str = "gemini-3.8-flash",
    max_retries: int = 3,
    stats: Optional[LLMUsageStats] = None,
) -> list[IntentClassificationResult]:
    """
    Calls Gemini API to classify a batch of cases (up to 20).
    Retries on rate-limit (429) or transient errors (503).
    """
    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google-generativeai is not installed; falling back to deterministic classification.")
        return [classify_deterministic(c["case_id"], c["request_text"]) for c in cases]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
    )

    prompt = _build_batch_prompt(cases)
    
    last_err = None
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            response = model.generate_content(prompt)
            duration = time.time() - start_time

            # Update usage stats
            if stats is not None:
                stats.call_count += 1
                stats.total_time_seconds += duration
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    stats.input_tokens += getattr(usage, "prompt_token_count", 0)
                    stats.output_tokens += getattr(usage, "candidates_token_count", 0)

            raw_text = response.text.strip()
            # Strip markdown block wrappers if present
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            parsed = json.loads(raw_text)
            results = []
            for item in parsed:
                results.append(
                    IntentClassificationResult(
                        case_id=str(item["case_id"]),
                        intent=str(item["intent"]),
                        confidence=float(item.get("confidence", 0.95)),
                        method="gemini_llm",
                        reasoning_note=str(item.get("reasoning_note", "Classified via Gemini LLM")),
                    )
                )
            return results

        except Exception as e:
            last_err = e
            if stats is not None:
                stats.error_count += 1
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "resource exhausted" in err_str:
                wait_time = (2 ** attempt) * 4
                logger.warning("Rate limit encountered in Gemini batch. Waiting %ds (attempt %d/%d)...", wait_time, attempt + 1, max_retries)
                time.sleep(wait_time)
            elif "503" in err_str or "unavailable" in err_str:
                wait_time = 2 * (attempt + 1)
                logger.warning("Service unavailable (503). Retrying in %ds...", wait_time)
                time.sleep(wait_time)
            else:
                logger.error("Gemini batch call failed: %s", e)
                break

    logger.warning("Gemini API call failed after retries (%s). Falling back to deterministic classifier.", last_err)
    return [classify_deterministic(c["case_id"], c["request_text"]) for c in cases]


# ---------------------------------------------------------------------------
# Public Orchestration Functions
# ---------------------------------------------------------------------------

def classify_single(
    case_id: str,
    request_text: str,
    api_key: Optional[str] = None,
    use_llm: bool = False,
    stats: Optional[LLMUsageStats] = None,
) -> IntentClassificationResult:
    """
    Classifies a single request's intent.
    Uses deterministic classification by default or LLM (Groq->Gemini) if requested.
    """
    if use_llm:
        try:
            import llm_provider
            batch_cases = [{"case_id": case_id, "request_text": request_text}]
            results = llm_provider.call_intent_batch(batch_cases)
            if results:
                r = results[0]
                return IntentClassificationResult(
                    case_id=r.get("case_id", case_id),
                    intent=r.get("intent", "NOT_APPLICABLE"),
                    confidence=float(r.get("confidence", 0.8)),
                    method="llm",
                    reasoning_note=r.get("reasoning_note", ""),
                )
        except Exception as exc:
            logger.warning("LLM intent classification failed for %s: %s. Using deterministic.", case_id, type(exc).__name__)

    # Fallback: also check Gemini directly if api_key provided
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    if use_llm and api_key:
        batch_cases = [{"case_id": case_id, "request_text": request_text}]
        results = _call_gemini_batch(batch_cases, api_key=api_key, stats=stats)
        if results:
            return results[0]

    return classify_deterministic(case_id, request_text)


def classify_intents(
    requests: Iterable[Any],
    api_key: Optional[str] = None,
    batch_size: int = 20,
    force_llm: bool = False,
) -> tuple[dict[str, IntentClassificationResult], LLMUsageStats]:
    """
    Classifies a collection of DeletionRequest objects or dicts with case_id & request_text.
    
    Strategy:
      - If force_llm is False (default): Uses high-speed deterministic heuristic.
        If a case has low confidence (< 0.90) and api_key is available, LLM resolves ambiguity.
      - If force_llm is True and api_key is available: batches all requests to Gemini API (20 per call).
      - Returns (dict[case_id -> IntentClassificationResult], LLMUsageStats).
    """
    api_key = api_key or os.environ.get("GEMINI_API_KEY")
    stats = LLMUsageStats()
    results: dict[str, IntentClassificationResult] = {}

    req_list = []
    for r in requests:
        cid = getattr(r, "case_id", None) or r["case_id"]
        txt = getattr(r, "request_text", None) or r["request_text"]
        req_list.append({"case_id": cid, "request_text": txt})

    if not req_list:
        return results, stats

    if force_llm and api_key:
        # Full LLM batch processing
        for i in range(0, len(req_list), batch_size):
            chunk = req_list[i:i + batch_size]
            batch_results = _call_gemini_batch(chunk, api_key=api_key, stats=stats)
            for res in batch_results:
                results[res.case_id] = res
            # Respect 15 RPM free tier rate limit: wait 4 seconds between 20-case batches
            if i + batch_size < len(req_list):
                time.sleep(4.0)
        return results, stats

    # Fast deterministic classification first
    ambiguous_cases: list[dict[str, str]] = []
    for c in req_list:
        res = classify_deterministic(c["case_id"], c["request_text"])
        results[c["case_id"]] = res
        if res.confidence < 0.90:
            ambiguous_cases.append(c)

    # If ambiguous cases exist, resolve them via Groq->Gemini
    if ambiguous_cases:
        logger.info("Resolving %d ambiguous case(s) with LLM (Groq->Gemini)...", len(ambiguous_cases))
        try:
            import llm_provider
            for i in range(0, len(ambiguous_cases), batch_size):
                chunk = ambiguous_cases[i:i + batch_size]
                batch_results = llm_provider.call_intent_batch(chunk)
                if batch_results:
                    for r in batch_results:
                        results[r["case_id"]] = IntentClassificationResult(
                            case_id=r.get("case_id", ""),
                            intent=r.get("intent", "NOT_APPLICABLE"),
                            confidence=float(r.get("confidence", 0.8)),
                            method="llm",
                            reasoning_note=r.get("reasoning_note", ""),
                        )
        except Exception as exc:
            logger.warning("LLM ambiguous resolution failed: %s. Keeping deterministic results.", type(exc).__name__)

    return results, stats
