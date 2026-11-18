"""Independent deterministic check for the root output.csv schema and IDs."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from data_layer import DatasetIndex  # noqa: E402
from output_pipeline import OUTPUT_COLUMNS  # noqa: E402


def validate(path: Path) -> None:
    index = DatasetIndex.from_dataset(ROOT / "dataset")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTPUT_COLUMNS:
            raise ValueError(f"columns: expected {OUTPUT_COLUMNS}, got {reader.fieldnames}")
        rows = list(reader)
    expected = [row["request_id"] for row in index.requests]
    actual = [row["request_id"] for row in rows]
    if len(rows) != len(expected):
        raise ValueError(f"row count: expected {len(expected)}, got {len(rows)}")
    if actual != expected:
        raise ValueError("request IDs/order do not exactly match requests.csv")
    if any(any(value is None for value in row.values()) for row in rows):
        raise ValueError("output contains missing CSV fields")
    for row in rows:
        if not row["decision_explanation"].strip():
            raise ValueError(f"empty explanation: {row['request_id']}")
    print(f"schema valid: {path} columns={len(OUTPUT_COLUMNS)} rows={len(rows)}")


if __name__ == "__main__":
    validate(ROOT / "output.csv")
