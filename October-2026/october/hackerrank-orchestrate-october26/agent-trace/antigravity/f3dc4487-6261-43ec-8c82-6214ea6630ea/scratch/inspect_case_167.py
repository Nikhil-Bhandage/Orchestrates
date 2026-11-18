import sys
from pathlib import Path

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index
from evidence_agent import investigate_case
from policy_engine import evaluate_resource_policy, order_and_renumber_steps

dataset_dir = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dataset_dir)
index = get_evidence_index(dataset_dir)

cid = "case_167"
req = next((r for r in bundle.deletion_requests if r.case_id == cid), None)
print(f"Request: {req}")

inv_res = investigate_case(cid, bundle, index)
print(f"Evidence gaps: {inv_res.evidence_gaps}")
print(f"Evaluations count: {len(inv_res.evaluations)}")
for ev in inv_res.evaluations:
    print(f"  eval: res={ev.resource_id}, sys={ev.system_id}, cat={ev.data_category}, state={ev.observed_state}, compliant={ev.is_compliant}, ev_id={ev.evidence_id}")

evaluations = inv_res.evaluations
has_non_compliant = any(e.is_compliant is False for e in evaluations)
has_unknown = any(e.observed_state in ("UNKNOWN", "CONFLICTING") for e in evaluations)
has_gaps = len(inv_res.evidence_gaps) > 0
has_conflicts = any(len(e.conflict_details) > 0 for e in evaluations)

print(f"has_non_compliant={has_non_compliant}, has_unknown={has_unknown}, has_gaps={has_gaps}, has_conflicts={has_conflicts}")
