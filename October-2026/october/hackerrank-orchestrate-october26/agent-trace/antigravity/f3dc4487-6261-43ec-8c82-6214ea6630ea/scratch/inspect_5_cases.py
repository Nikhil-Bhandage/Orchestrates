import csv
import json
import re
from pathlib import Path

sample_reqs = {}
with open("dataset/sample_deletion_requests.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        sample_reqs[r["case_id"]] = r

sample_outs = {}
with open("dataset/sample_output.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        sample_outs[r["case_id"]] = {
            "status": r["deletion_status"],
            "steps": json.loads(r["steps_json"]),
        }

cache = json.loads(Path("code/.ocr_cache.json").read_text(encoding="utf-8"))

target_cases = ["case_21", "case_26", "case_27", "case_28", "case_31"]

for cid in target_cases:
    print("=" * 60)
    print(f"CASE: {cid}")
    req = sample_reqs[cid]
    out = sample_outs[cid]
    print(f"Email: {req['email']}, Audit At: {req['audit_at']}")
    print(f"Expected Status: {out['status']}")
    print(f"Expected Steps ({len(out['steps'])}):")
    for s in out["steps"]:
        print(f"  Step {s['step_no']}: phase={s['phase']} sys={s['system_id']} res={s['resource_id']} op={s['operation']} state={s['state']} ev={s['evidence_id']}")
    
    # Check which cached OCR texts mention this email or user
    matched_images = []
    for sha, text in cache.items():
        if req["email"].lower() in text.lower():
            matched_images.append((sha[:10], "email match"))
    print(f"Matching images by email: {matched_images}")
