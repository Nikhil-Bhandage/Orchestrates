import sys, csv, json
from pathlib import Path

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import InvertedEvidenceIndex
from workflow import audit_single_case
from main import validate_output_file

dd = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dd)
index = InvertedEvidenceIndex(dataset_dir=dd)
index.build_index()

# 1. Test case_363 and case_369
updated_cases = {}
for cid in ["case_363", "case_369"]:
    res = audit_single_case(cid, bundle=bundle, index=index)
    updated_cases[cid] = (res["deletion_status"], res["steps_json"])
    print(f"{cid}: status={res['deletion_status']}, steps_len={len(res['steps'])}, steps={res['steps_json']}")

# 2. Update output.csv in place for just these 2 rows
out_files = [
    Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/output.csv"),
    Path("g:/coding/HackerRank-Orchestrate/october/output.csv")
]

for p in out_files:
    if not p.exists():
        continue
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        if r["case_id"] in updated_cases:
            st, sj = updated_cases[r["case_id"]]
            r["deletion_status"] = st
            r["steps_json"] = sj
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        writer.writerows(rows)
    val = validate_output_file(p)
    print(f"Validated {p.name}: is_valid={val['is_valid']}, valid_rows={val['valid_rows']}/{val['total_rows']}, errors={len(val['errors'])}")
