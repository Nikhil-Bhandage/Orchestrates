import csv, json
from pathlib import Path

p = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/output.csv")
cases_to_check = ["case_167", "case_98", "case_47", "case_61"]

with p.open(newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["case_id"] in cases_to_check:
            print("=" * 60)
            print(f"CASE: {row['case_id']} | STATUS: {row['deletion_status']}")
            print(f"STEPS_JSON: {row['steps_json']}")
