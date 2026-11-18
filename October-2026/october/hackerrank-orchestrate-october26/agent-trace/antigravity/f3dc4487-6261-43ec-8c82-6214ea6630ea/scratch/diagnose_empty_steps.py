import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, "g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index
from evidence_agent import investigate_case
from policy_engine import evaluate_resource_policy

dataset_dir = Path("g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/dataset")
bundle = load_all_datasets(dataset_dir)
index = get_evidence_index(dataset_dir)

incomplete_61 = ['case_47', 'case_48', 'case_49', 'case_61', 'case_63', 'case_74', 'case_76', 'case_78', 'case_114', 'case_118', 'case_120', 'case_168', 'case_194', 'case_197', 'case_198', 'case_200', 'case_234', 'case_236', 'case_240', 'case_241', 'case_242', 'case_263', 'case_264', 'case_265', 'case_266', 'case_267', 'case_268', 'case_269', 'case_270', 'case_271', 'case_272', 'case_284', 'case_287', 'case_288', 'case_289', 'case_290', 'case_325', 'case_328', 'case_329', 'case_330', 'case_332', 'case_373', 'case_376', 'case_377', 'case_382', 'case_413', 'case_416', 'case_417', 'case_422', 'case_471', 'case_484', 'case_485', 'case_488', 'case_490', 'case_492', 'case_514', 'case_515', 'case_517', 'case_519', 'case_520', 'case_521']
complete_13 = ['case_98', 'case_99', 'case_123', 'case_128', 'case_147', 'case_224', 'case_248', 'case_279', 'case_350', 'case_399', 'case_447', 'case_495', 'case_531']

print("=== Analyzing 13 COMPLETE cases with empty steps ===")
for cid in complete_13:
    req = next((r for r in bundle.deletion_requests if r.case_id == cid), None)
    inv = investigate_case(cid, bundle, index)
    print(f"{cid}: reported={req.reported_status}, evals={len(inv.evaluations)}, gaps={len(inv.evidence_gaps)}")

print("\n=== Analyzing sample of 61 INCOMPLETE cases with empty steps ===")
for cid in incomplete_61[:10]:
    req = next((r for r in bundle.deletion_requests if r.case_id == cid), None)
    inv = investigate_case(cid, bundle, index)
    eval_states = [f"{e.resource_id}:{e.observed_state}" for e in inv.evaluations]
    print(f"{cid}: reported={req.reported_status}, evals={len(inv.evaluations)} ({eval_states}), gaps={len(inv.evidence_gaps)}")
