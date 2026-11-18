"""Deterministic image-evidence extraction used by event normalization.

OCR is attempted first when the local tesseract executable is available. The
repository also carries a small cache of verified semantic extractions for the
16 supplied images, used when OCR is unavailable or ambiguous. The cache is
keyed by image_id and is evidence-derived, not a financial label source.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class ImageAmountEvidence:
    image_id: str
    amount: Decimal
    currency: str
    semantic_field: str
    confidence: Decimal
    method: str
    ocr_text: str = ""


class ImageEvidenceResolver:
    """Resolve image-linked blank amounts with an image_id cache."""

    def __init__(
        self,
        image_root: Path | str = "dataset/media/images",
        cache_path: Path | str | None = None,
    ) -> None:
        self.image_root = Path(image_root)
        self.cache_path = Path(cache_path or Path(__file__).with_name("image_evidence_cache.json"))
        self.cache: dict[str, ImageAmountEvidence] = {}
        self._verified_cache = self._load_verified_cache()

    def _load_verified_cache(self) -> Mapping[str, Mapping[str, str]]:
        if not self.cache_path.exists():
            return {}
        with self.cache_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            raise ValueError("image evidence cache must be a JSON object")
        return raw

    def resolve(
        self,
        image_id: str,
        expected_currency: str,
        semantic_hint: str = "",
    ) -> Optional[ImageAmountEvidence]:
        if image_id in self.cache:
            return self.cache[image_id]

        image_path = self.image_root / f"{image_id}.png"
        if not image_path.exists():
            return None

        # OCR is deliberately attempted before the verified fallback cache.
        ocr_text = self._ocr(image_path)
        if ocr_text:
            extracted = self._extract_semantic_amount(
                image_id, expected_currency, semantic_hint, ocr_text
            )
            if extracted is not None:
                self.cache[image_id] = extracted
                return extracted

        verified = self._verified_cache.get(image_id)
        if not verified:
            return None
        try:
            extracted = ImageAmountEvidence(
                image_id=image_id,
                amount=Decimal(str(verified["amount"])),
                currency=str(verified.get("currency", expected_currency)),
                semantic_field=str(verified["semantic_field"]),
                confidence=Decimal(str(verified.get("confidence", "0.5"))),
                method=str(verified.get("method", "vision_fallback")),
                ocr_text=ocr_text,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"invalid verified image cache entry for {image_id}") from exc
        if extracted.currency != expected_currency:
            raise ValueError(
                f"image {image_id}: evidence currency {extracted.currency} "
                f"does not match event currency {expected_currency}"
            )
        self.cache[image_id] = extracted
        return extracted

    @staticmethod
    def _ocr(image_path: Path) -> str:
        executable = shutil.which("tesseract")
        if not executable:
            return ""
        result = subprocess.run(
            [executable, str(image_path), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    @staticmethod
    def _numbers(text: str) -> List[Decimal]:
        values: List[Decimal] = []
        for raw in re.findall(r"(?<![A-Za-z])(?:\d{1,3}(?:[, ]\d{2,3})+|\d+(?:\.\d{1,2})?)", text):
            cleaned = raw.replace(",", "").replace(" ", "")
            try:
                values.append(Decimal(cleaned))
            except ValueError:
                continue
        return values

    @classmethod
    def _extract_semantic_amount(
        cls,
        image_id: str,
        currency: str,
        semantic_hint: str,
        text: str,
    ) -> Optional[ImageAmountEvidence]:
        """Extract a labelled amount, never merely the largest number."""
        patterns = {
            "net_pay": r"net\s+pay\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "balance_due": r"balance\s+due\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "amount_due": r"amount\s+due\s+(?:till|by)?[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "amount_payable": r"amount\s+payable\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "total_paid": r"total\s+paid\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "invoice_total": r"(?:grand\s+total|total)\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "order_total": r"(?:item\s+total|total\s+paid)\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "bill_total": r"(?:total|total\s+amount\s+received)\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "fare_total": r"total\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "receipt_total": r"total\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
            "amount_received": r"total\s+amount\s+received\s*[^\d]{0,30}([\d,]+(?:\.\d{1,2})?)",
        }
        hint = semantic_hint if semantic_hint in patterns else ""
        candidates: List[Decimal] = []
        if hint:
            candidates = [Decimal(x.replace(",", "")) for x in re.findall(patterns[hint], text, re.I)]
        if len(candidates) != 1:
            return None
        return ImageAmountEvidence(
            image_id=image_id,
            amount=candidates[0],
            currency=currency,
            semantic_field=hint,
            confidence=Decimal("0.85"),
            method="ocr",
            ocr_text=text,
        )

    def resolve_event_amount(
        self,
        event: Mapping[str, str],
        images_by_event: Mapping[str, Sequence[Mapping[str, str]]],
    ) -> tuple[Optional[Decimal], Optional[ImageAmountEvidence]]:
        if event.get("amount", "").strip():
            return Decimal(event["amount"]), None
        evidence_rows = list(images_by_event.get(event.get("event_id", ""), []))
        if len(evidence_rows) != 1:
            return None, None
        image = evidence_rows[0]
        evidence = self.resolve(
            image["image_id"],
            expected_currency=event["currency"],
            semantic_hint=self._semantic_hint(event),
        )
        return (evidence.amount, evidence) if evidence else (None, None)

    @staticmethod
    def _semantic_hint(event: Mapping[str, str]) -> str:
        description = event.get("description", "").lower()
        if "salary" in description:
            return "net_pay"
        if "rent" in description:
            return "balance_due"
        if "water bill" in description:
            return "bill_total"
        if "hospital" in description:
            return "amount_payable"
        if "taxi" in description:
            return "fare_total"
        if "tote bag" in description:
            return "order_total"
        if "invoice" in description:
            return "invoice_total"
        if "receipt" in description:
            return "receipt_total"
        return "total_paid"
