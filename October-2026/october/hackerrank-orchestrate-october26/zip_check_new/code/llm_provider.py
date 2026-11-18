"""
llm_provider.py — Unified LLM Provider Abstraction

Primary:   Groq (GROQ_API_KEY) — text tasks: Manager reasoning, intent classification
Secondary: Gemini (GEMINI_API_KEY) — fallback for text; always used for Vision (PNG OCR)
"""

from __future__ import annotations

import base64
import json as _json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("llm_provider")


def _load_env_file() -> None:
    need_groq = not os.environ.get("GROQ_API_KEY", "").strip()
    need_gemini = not os.environ.get("GEMINI_API_KEY", "").strip()
    if not (need_groq or need_gemini):
        return
    _repo = Path(__file__).resolve().parent.parent
    for base in [Path("."), _repo, _repo.parent]:
        env_path = base / ".env"
        if not env_path.exists():
            continue
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GROQ_API_KEY=") and need_groq:
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        os.environ["GROQ_API_KEY"] = val
                        need_groq = False
                elif line.startswith("GEMINI_API_KEY=") and need_gemini:
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        os.environ["GEMINI_API_KEY"] = val
                        need_gemini = False
        except Exception:
            pass
        if not (need_groq or need_gemini):
            break


_load_env_file()


@dataclass
class ProviderUsage:
    groq_calls: int = 0
    groq_input_tokens: int = 0
    groq_output_tokens: int = 0
    groq_errors: int = 0
    gemini_calls: int = 0
    gemini_input_tokens: int = 0
    gemini_output_tokens: int = 0
    gemini_errors: int = 0
    fallbacks_to_gemini: int = 0
    vision_calls: int = 0
    vision_errors: int = 0

    def to_dict(self) -> dict:
        return self.__dict__.copy()


_GLOBAL_USAGE = ProviderUsage()


def get_usage() -> ProviderUsage:
    return _GLOBAL_USAGE


def _is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in ("rate limit", "429", "503", "502", "timeout", "temporarily"))


def call_text(
    prompt: str,
    *,
    model_groq: str = "openai/gpt-oss-120b",
    model_gemini: str = "gemini-1.5-flash",
    max_tokens: int = 512,
    temperature: float = 0.0,
    max_retries: int = 2,
    usage: Optional[ProviderUsage] = None,
) -> tuple[str, str]:
    """Try Groq first, then Gemini. Returns (text, provider). Raises RuntimeError if both fail."""
    u = usage or _GLOBAL_USAGE
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if groq_key:
        for attempt in range(max_retries + 1):
            try:
                from groq import Groq
                client = Groq(api_key=groq_key)
                resp = client.chat.completions.create(
                    model=model_groq,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = resp.choices[0].message.content or ""
                u.groq_calls += 1
                if hasattr(resp, "usage") and resp.usage:
                    u.groq_input_tokens += getattr(resp.usage, "prompt_tokens", 0)
                    u.groq_output_tokens += getattr(resp.usage, "completion_tokens", 0)
                return text, "groq"
            except Exception as exc:
                u.groq_errors += 1
                if _is_retryable(exc) and attempt < max_retries:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning("Groq text call failed (%s). Falling back to Gemini.", type(exc).__name__)
                    break
        u.fallbacks_to_gemini += 1

    if gemini_key:
        for attempt in range(max_retries + 1):
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(model_gemini)
                resp = model.generate_content(prompt)
                text = resp.text.strip() if resp.text else ""
                u.gemini_calls += 1
                pu = getattr(resp, "usage_metadata", None)
                if pu:
                    u.gemini_input_tokens += getattr(pu, "prompt_token_count", 0)
                    u.gemini_output_tokens += getattr(pu, "candidates_token_count", 0)
                return text, "gemini"
            except Exception as exc:
                u.gemini_errors += 1
                if _is_retryable(exc) and attempt < max_retries:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning("Gemini text call failed (%s).", type(exc).__name__)
                    break

    raise RuntimeError("Both Groq and Gemini text providers failed.")


def call_vision(
    image_path: Path,
    prompt: str,
    *,
    model_gemini: str = "gemini-1.5-flash",
    max_retries: int = 1,
    usage: Optional[ProviderUsage] = None,
) -> tuple[str, str]:
    """Vision OCR via Gemini only (Groq has no image support). Returns (text, method)."""
    u = usage or _GLOBAL_USAGE
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        return "", "no_key"

    u.vision_calls += 1
    b64 = base64.b64encode(image_path.read_bytes()).decode("utf-8")

    for attempt in range(max_retries + 1):
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(model_gemini)
            response = model.generate_content([
                {"role": "user", "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]},
            ])
            text = response.text.strip() if response.text else ""
            u.gemini_calls += 1
            pu = getattr(response, "usage_metadata", None)
            if pu:
                u.gemini_input_tokens += getattr(pu, "prompt_token_count", 0)
                u.gemini_output_tokens += getattr(pu, "candidates_token_count", 0)
            return text, "gemini_vision"
        except Exception as exc:
            u.vision_errors += 1
            if _is_retryable(exc) and attempt < max_retries:
                time.sleep(2 ** attempt)
            else:
                logger.warning("Gemini Vision failed for %s (%s).", image_path.name, type(exc).__name__)
                break

    return "", "vision_failed"


_INTENT_PROMPT = """You are a privacy compliance auditor assessing data subject requests.
For each request, determine if the user authorizes permanent DELETION or if NOT_APPLICABLE.

"DELETION_REQUEST": explicit/implicit account deletion, erasure, closure, right-to-be-forgotten (all languages).
"NOT_APPLICABLE": access, correction, opt-out, recovery, or "do not delete" / "keep account".

Requests:
{batch_json}

Respond ONLY with a JSON array:
[{{"case_id":"case_xx","intent":"DELETION_REQUEST","confidence":0.95,"reasoning_note":"brief"}}]"""


def call_intent_batch(
    cases: list[dict],
    *,
    usage: Optional[ProviderUsage] = None,
) -> list[dict] | None:
    """Classify intent batch via Groq→Gemini. Returns list of result dicts or None."""
    u = usage or _GLOBAL_USAGE
    prompt = _INTENT_PROMPT.format(batch_json=_json.dumps(cases, indent=2, ensure_ascii=False))

    def _parse(text: str) -> list | None:
        text = text.strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.strip().lstrip("json").strip()
                if part.startswith("["):
                    text = part
                    break
        try:
            result = _json.loads(text)
            return result if isinstance(result, list) else None
        except Exception:
            return None

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            from groq import Groq
            client = Groq(api_key=groq_key)
            resp = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content or ""
            u.groq_calls += 1
            if hasattr(resp, "usage") and resp.usage:
                u.groq_input_tokens += getattr(resp.usage, "prompt_tokens", 0)
                u.groq_output_tokens += getattr(resp.usage, "completion_tokens", 0)
            parsed = _parse(text)
            if parsed is not None:
                return parsed
        except Exception as exc:
            u.groq_errors += 1
            u.fallbacks_to_gemini += 1
            logger.warning("Groq intent batch failed (%s). Falling back to Gemini.", type(exc).__name__)

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                "gemini-1.5-flash",
                generation_config={"temperature": 0.0, "response_mime_type": "application/json"}
            )
            resp = model.generate_content(prompt)
            text = resp.text.strip() if resp.text else ""
            u.gemini_calls += 1
            pu = getattr(resp, "usage_metadata", None)
            if pu:
                u.gemini_input_tokens += getattr(pu, "prompt_token_count", 0)
                u.gemini_output_tokens += getattr(pu, "candidates_token_count", 0)
            parsed = _parse(text)
            if parsed is not None:
                return parsed
        except Exception as exc:
            u.gemini_errors += 1
            logger.warning("Gemini intent batch also failed (%s).", type(exc).__name__)

    return None
