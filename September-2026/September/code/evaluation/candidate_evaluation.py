"""Evaluate candidate generation/ranking against the 25 public solved rows.

Solved rows are used only for diagnostics here, never as prediction-time rules.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from candidate_plans import CandidateEngine
from canonical_events import normalize_dataset
from data_layer import DatasetIndex

ROOT = Path(__file__).parents[2]
index = DatasetIndex.from_dataset(ROOT / "dataset")
store = normalize_dataset(index)
engine = CandidateEngine(index, store)
with (ROOT / "dataset/sample_requests.csv").open(encoding="utf-8-sig") as handle:
    samples = list(csv.DictReader(handle))


def plan_text(candidate):
    return "|".join(f"{day}:{amount}" for day, amount in candidate.payment_schedule) or "none"


rows = []
for sample in samples:
    decision = engine.decide(sample)
    candidate = decision.selected
    predicted = {
        "amount_safe_to_pay": str(candidate.amount_safe_to_pay),
        "affordability_status": decision.affordability_status,
        "recommended_payment_method": candidate.payment_method,
        "payment_plan": plan_text(candidate),
        "earliest_date_for_full_payment": decision.earliest_full_payment_date,
        "spending_changes_needed": "|".join(candidate.spending_changes) or "none",
    }
    expected = {
        key: sample[key]
        for key in predicted
    }
    mismatches = [key for key in predicted if predicted[key] != expected[key]]
    rows.append({
        "request_id": sample["request_id"],
        "expected": expected,
        "predicted": predicted,
        "mismatches": mismatches,
        "selected_rationale_codes": candidate.rationale_codes,
        "selected_option_id": candidate.option_id,
        "feasible_candidate_count": len(decision.feasible_candidates),
        "rejection_counts": decision.rejection_counts,
        "baseline_safe_amount": str(decision.baseline_safe_amount),
    })

counts = Counter(key for row in rows for key in row["mismatches"])
summary = {
    "sample_count": len(rows),
    "exact_rows": sum(not row["mismatches"] for row in rows),
    "field_match_counts": {
        key: sum(key not in row["mismatches"] for row in rows)
        for key in rows[0]["predicted"]
    },
    "mismatch_counts": dict(counts),
    "rows": rows,
}
json_path = Path(__file__).with_name("candidate_sample_mismatch.json")
json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

lines = [
    "# Candidate-plan golden-sample mismatch report",
    "",
    "This artifact evaluates the deterministic candidate engine against the 25 public solved rows. It is diagnostic only; solved labels are not used as prediction-time rules.",
    "",
    f"- Exact rows: **{summary['exact_rows']}/{summary['sample_count']}**",
    "- Field matches: " + ", ".join(f"`{key}` {value}/{summary['sample_count']}" for key, value in summary["field_match_counts"].items()),
    "- Mismatch counts: " + ", ".join(f"`{key}` {value}" for key, value in summary["mismatch_counts"].items()),
    "",
    "## Rows",
    "",
    "| Request | Expected method/status | Selected method/status | Amount safe | Earliest full date | Mismatches |",
    "|---|---|---|---:|---|---|",
]
for row in rows:
    lines.append(
        f"| {row['request_id']} | {row['expected']['recommended_payment_method']} / {row['expected']['affordability_status']} | "
        f"{row['predicted']['recommended_payment_method']} / {row['predicted']['affordability_status']} | "
        f"{row['predicted']['amount_safe_to_pay']} | {row['predicted']['earliest_date_for_full_payment'] or 'empty'} | "
        f"{', '.join(row['mismatches']) or 'none'} |"
    )
lines += [
    "",
    "## Systematic mismatch categories",
    "",
    "- **State versus plan semantics:** the engine validates the selected plan with the deterministic simulator; it does not force the prior one-time-capacity primitive to match a solved `amount_safe_to_pay` label.",
    "- **Evidence/state differences:** messages may amend existing salary/rent entries, but unsupported pending income, bonuses, refunds, prizes, and unrealized values remain excluded.",
    "- **Forecast-policy differences:** conservative recurring and essential-variable projections can change whether a public plan is feasible; these are retained as diagnostics rather than sample-specific exceptions.",
    "- **Option/preference differences:** installment offers are accepted only when their exact schedule, duration, cost, deadline, and user preference all pass hard validation.",
]
Path(__file__).with_name("candidate_sample_mismatch.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", json_path, "exact_rows=", summary["exact_rows"], "mismatches=", dict(counts))
