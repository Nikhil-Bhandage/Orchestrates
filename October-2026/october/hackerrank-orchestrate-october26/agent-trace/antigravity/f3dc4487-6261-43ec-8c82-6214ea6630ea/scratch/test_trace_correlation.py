import sys, re
from pathlib import Path

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index, EvidenceHit, _infer_system_id, _extract_identifiers_from_dict

# Let's inspect the logs for Group A cases
dataset_dir = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dataset_dir)

group_a = ['case_265', 'case_267', 'case_271', 'case_272', 'case_416', 'case_417', 'case_517', 'case_519', 'case_521']

for cid in group_a:
    req = next(r for r in bundle.deletion_requests if r.case_id == cid)
    user_id = bundle.current_email_index.get(req.email.lower()) or bundle.historical_email_index.get(req.email.lower())
    print(f"\n=== {cid} ({req.email}, {user_id}) ===")
    
    # Let's search all log files in dataset/evidence/logs for any lines mentioning email or user_id
    for log_path in dataset_dir.glob("evidence/logs/*.log"):
        text = log_path.read_text(encoding="utf-8")
        if req.email.lower() in text.lower() or (user_id and user_id.lower() in text.lower()):
            for line in text.splitlines():
                if req.email.lower() in line.lower() or (user_id and user_id.lower() in line.lower()):
                    tr_m = re.search(r'\b(?:trace_id|requestId)=["\']?([a-zA-Z0-9_\-]+)["\']?', line)
                    tr_id = tr_m.group(1) if tr_m else "NO_TR"
                    print(f"  [{log_path.name}] tr={tr_id}: {line.strip()[:140]}")
                    
                    # If tr_id found, print other lines with that tr_id!
                    if tr_id != "NO_TR":
                        for l2 in text.splitlines():
                            if tr_id in l2 and l2.strip() != line.strip():
                                print(f"     -> related: {l2.strip()[:140]}")
