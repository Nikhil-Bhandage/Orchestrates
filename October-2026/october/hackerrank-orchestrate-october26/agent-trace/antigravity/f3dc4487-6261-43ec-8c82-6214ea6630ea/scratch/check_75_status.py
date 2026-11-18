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

all_75 = [
    # 61 INCOMPLETE
    'case_47', 'case_48', 'case_49', 'case_61', 'case_63', 'case_74', 'case_76', 'case_78', 'case_114',
    'case_118', 'case_120', 'case_168', 'case_194', 'case_197', 'case_198', 'case_200', 'case_234',
    'case_236', 'case_240', 'case_241', 'case_242', 'case_263', 'case_264', 'case_265', 'case_266',
    'case_267', 'case_268', 'case_269', 'case_270', 'case_271', 'case_272', 'case_284', 'case_287',
    'case_288', 'case_289', 'case_290', 'case_325', 'case_328', 'case_329', 'case_330', 'case_332',
    'case_373', 'case_376', 'case_377', 'case_382', 'case_413', 'case_416', 'case_417', 'case_422',
    'case_471', 'case_484', 'case_485', 'case_488', 'case_490', 'case_492', 'case_514', 'case_515',
    'case_517', 'case_519', 'case_520', 'case_521',
    # 13 COMPLETE
    'case_98', 'case_99', 'case_123', 'case_128', 'case_147', 'case_224', 'case_248', 'case_279',
    'case_350', 'case_399', 'case_447', 'case_495', 'case_531',
    # 1 VERIFICATION
    'case_167'
]

still_empty = []
for cid in all_75:
    inv = investigate_case(cid, bundle, index)
    evaluations = inv.evaluations
    evidence_gaps = inv.evidence_gaps
    conflicts = [c for e in evaluations for c in e.conflict_details]
    
    has_non_compliant = any(e.is_compliant is False for e in evaluations)
    has_unknown = any(e.observed_state in ("UNKNOWN", "CONFLICTING") for e in evaluations)
    has_gaps = len(evidence_gaps) > 0
    has_conflicts = len(conflicts) > 0

    preliminary_complete = not (has_non_compliant or has_unknown or has_gaps or has_conflicts)

    all_findings = []
    all_remediations = []
    all_verifications = []

    for ev in evaluations:
        findings, remediations, verifications = evaluate_resource_policy(
            ev, is_overall_complete=preliminary_complete
        )
        all_findings.extend(findings)
        all_remediations.extend(remediations)
        all_verifications.extend(verifications)

    if all_findings or has_non_compliant or has_unknown or has_gaps or has_conflicts:
        status = "INCOMPLETE"
        steps = all_findings + all_remediations + all_verifications
    else:
        status = "COMPLETE"
        steps = all_verifications

    if not steps:
        eval_summary = [(e.resource_id, e.observed_state, e.data_category, e.is_compliant) for e in evaluations]
        still_empty.append((cid, status, eval_summary, evidence_gaps))

print(f"Total still empty: {len(still_empty)} / {len(all_75)}")
for cid, st, evs, gaps in still_empty:
    print(f"  {cid} ({st}): evals={evs}, gaps={gaps}")
