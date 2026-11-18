import sys
from pathlib import Path

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index

dataset_dir = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dataset_dir)
index = get_evidence_index(dataset_dir)

cases = ['case_265', 'case_267', 'case_271', 'case_416', 'case_168', 'case_288']
for cid in cases:
    hits = index.get_hits_for_case(cid, bundle)
    print(f"=== {cid} ===")
    for h in hits:
        print(f"  hit: res_id='{h.resource_id}', state={h.parsed_state}, sys={h.system_id}")
        print(f"    snippet: {h.snippet}")
