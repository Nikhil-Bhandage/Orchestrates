import sys
from pathlib import Path

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index
from workflow import audit_single_case
from main import validate_output_file
import csv

dataset_dir = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dataset_dir)
index = get_evidence_index(dataset_dir)

all_75 = [
    'case_47', 'case_48', 'case_49', 'case_61', 'case_63', 'case_74', 'case_76', 'case_78', 'case_114',
    'case_118', 'case_120', 'case_167', 'case_168', 'case_194', 'case_197', 'case_198', 'case_200', 'case_234',
    'case_236', 'case_240', 'case_241', 'case_242', 'case_263', 'case_264', 'case_265', 'case_266',
    'case_267', 'case_268', 'case_269', 'case_270', 'case_271', 'case_272', 'case_284', 'case_287',
    'case_288', 'case_289', 'case_290', 'case_325', 'case_328', 'case_329', 'case_330', 'case_332',
    'case_373', 'case_376', 'case_377', 'case_382', 'case_413', 'case_416', 'case_417', 'case_422',
    'case_471', 'case_484', 'case_485', 'case_488', 'case_490', 'case_492', 'case_514', 'case_515',
    'case_517', 'case_519', 'case_520', 'case_521',
    'case_98', 'case_99', 'case_123', 'case_128', 'case_147', 'case_224', 'case_248', 'case_279',
    'case_350', 'case_399', 'case_447', 'case_495', 'case_531'
]

print(f"Testing workflow on all {len(all_75)} previously failing cases...")
rows = []
for cid in all_75:
    res = audit_single_case(cid, bundle=bundle, index=index)
    rows.append({
        "case_id": res["case_id"],
        "deletion_status": res["deletion_status"],
        "steps_json": res["steps_json"]
    })

# Validate the generated rows using the validator rules
test_csv = Path("C:/Users/Nikhil/.gemini/antigravity-ide/brain/f3dc4487-6261-43ec-8c82-6214ea6630ea/scratch/test_75.csv")
with test_csv.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
    writer.writeheader()
    writer.writerows(rows)

print("Rows generated. Validating individual rows...")
import json
for r in rows:
    cid = r["case_id"]
    st = r["deletion_status"]
    steps = json.loads(r["steps_json"])
    if st == "NOT_APPLICABLE" and steps != []:
        print(f"ERROR {cid}: NA with non-empty steps")
    elif st in ("COMPLETE", "INCOMPLETE") and len(steps) == 0:
        print(f"ERROR {cid}: {st} with empty steps")
    for s in steps:
        if st == "COMPLETE":
            if s["phase"] != "VERIFICATION" or not s["evidence_id"]:
                print(f"ERROR {cid}: COMPLETE step invalid: {s}")
        elif st == "INCOMPLETE":
            if s["phase"] == "FINDING" and not s["evidence_id"]:
                print(f"ERROR {cid}: FINDING without evidence_id: {s}")
            elif s["phase"] in ("REMEDIATION", "VERIFICATION") and s["evidence_id"] != "":
                print(f"ERROR {cid}: {s['phase']} with non-empty evidence_id: {s}")

print("Validation of 75 cases complete! If no ERROR printed above, all 75 pass cleanly!")
