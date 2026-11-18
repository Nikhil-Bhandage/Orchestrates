from pathlib import Path
import sys
from collections import Counter

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from main import validate_output_file

candidates = [
    Path("g:/coding/HackerRank-Orchestrate/october/output.csv"),
    Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/output.csv"),
    Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset/output.csv")
]

for p in candidates:
    if p.exists():
        print(f"=== Validating {p} (size={p.stat().st_size}) ===")
        res = validate_output_file(p)
        print(f"Valid: {res['is_valid']}, Total rows: {res['total_rows']}, Valid rows: {res['valid_rows']}, Errors: {len(res['errors'])}")
        print(f"Status counts: {res['status_counts']}")
        
        err_by_type = {}
        for err_str in res["errors"]:
            if ": " in err_str:
                cid, msg = err_str.split(": ", 1)
            else:
                cid, msg = "GLOBAL", err_str
            
            # Group by message
            for m in msg.split("; "):
                err_by_type.setdefault(m, []).append(cid)
        
        print("\nError Breakdown:")
        for err_type, cases in sorted(err_by_type.items(), key=lambda x: len(x[1]), reverse=True):
            print(f"  [{len(cases)} cases] {err_type}")
            print(f"    Cases ({len(cases)}): {cases}")
