"""
P2: Simulate proposed fix across all 250 requests.
Proposed fix: when natural_path_feasible=False, use min_before_payment - minimum
instead of returning 0.
READ-ONLY. No source modifications. Uses a patched function to simulate only.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
from copy import deepcopy

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    simulate_payment_plan, get_max_safe_one_time_payment, ZERO, MaxSafePaymentResult
)
from evidence_resolution import apply_evidence_to_timeline
from candidate_plans import CandidateEngine

# Full dataset
full_index = DatasetIndex.from_dataset(Path('dataset'))
full_store = normalize_dataset(full_index)
full_engine = CandidateEngine(full_index, full_store)

sample_index = DatasetIndex.from_dataset(Path('tmp_sample_test'))
sample_store = normalize_dataset(sample_index)
sample_engine = CandidateEngine(sample_index, sample_store)

expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

# Load current output
current_out = {}
with open('dataset/output.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        current_out[row['request_id']] = row

# The proposed fix for amount_safe_to_pay when natural_path_feasible=False:
# PROPOSED: return max(0, min_before_payment - minimum) instead of 0
# This corresponds to: "what can you safely pay on request_date given the balance
# at request_date, ignoring what happens after"
# 
# BUT our exhaustive search showed that even this formula doesn't match the
# expected values for request_05, request_14, request_15.
# The expected values (737, 597.74, 83.05) cannot be derived from any simple
# formula on the timeline. So we need to understand what the benchmark actually computes.
#
# Let's instead test: does fixing amount_safe_to_pay=0 -> min_before-min
# change any STATUS or METHOD? (It shouldn't, because amount_safe_to_pay
# is only an output field for not_recommended cases.)

print("="*70)
print("P2 SIMULATION: Effect of amount_safe_to_pay fix on all 250 requests")
print("="*70)
print()
print("NOTE: amount_safe_to_pay is set from baseline_safe (=0 for infeasible)")
print("Proposed fix: use max(0, min_before_payment - minimum) when infeasible")
print("This ONLY changes the output field for method=not_recommended cases.")
print("It cannot change status, method, payment plan, or earliest date.")
print()

# Count requests where our current output has amount_safe_to_pay=0 AND method=not_recommended
changed_requests = []
for rid, row in current_out.items():
    if row['recommended_payment_method'] == 'not_recommended' and Decimal(row['amount_safe_to_pay']) == ZERO:
        changed_requests.append(rid)

print(f"Requests with method=not_recommended AND amount_safe_to_pay=0: {len(changed_requests)}")

# For these, compute what the fix would produce
# We need to run get_max_safe_one_time_payment for each and use min_before-minimum
fixes = {}
for rid in changed_requests:
    req = full_index.requests_by_id[rid]
    uid = req['user_id']
    ctx = full_engine.evidence.context_for_request(req)
    tl = apply_evidence_to_timeline(full_engine.catalog.get(uid), ctx, full_index.exchange_rates_by_key)
    baseline = get_max_safe_one_time_payment(tl, req['request_date'], Decimal(req['requested_amount']))
    proposed = max(ZERO, baseline.minimum_natural_balance_before_payment - tl.policy.minimum_balance)
    fixes[rid] = {
        'old_amount': ZERO,
        'new_amount': proposed,
        'min_before': baseline.minimum_natural_balance_before_payment,
        'minimum': tl.policy.minimum_balance,
    }

# How many would change?
non_zero_fixes = {rid: v for rid, v in fixes.items() if v['new_amount'] > ZERO}
print(f"Requests where fix changes amount_safe_to_pay from 0 to non-zero: {len(non_zero_fixes)}")
print(f"Requests where amount_safe_to_pay stays 0 (min_before < minimum): {len(fixes) - len(non_zero_fixes)}")
print()

# Compare with sample expected values
print("Sample requests in this set:")
for rid in ['request_05', 'request_14', 'request_15']:
    if rid in fixes:
        exp_val = Decimal(expected[rid]['amount_safe_to_pay']) if rid in expected else None
        fix = fixes[rid]
        print(f"  {rid}: proposed={fix['new_amount']} expected={exp_val} OLD=0")
        print(f"    min_before={fix['min_before']} minimum={fix['minimum']}")
        if exp_val is not None:
            match = abs(fix['new_amount'] - exp_val) < Decimal('0.02')
            print(f"    Proposed matches expected: {match}")

print()
print(f"Full 250-request impact:")
print(f"  Fields that COULD change: amount_safe_to_pay only")
print(f"  Fields that CANNOT change: affordability_status, recommended_payment_method,")
print(f"    payment_plan, earliest_date_for_full_payment, spending_changes_needed,")
print(f"    decision_explanation")
print()
print(f"  Requests where amount_safe_to_pay would change: {len(non_zero_fixes)}")
if non_zero_fixes:
    print(f"  First 10 changed request IDs and proposed new amounts:")
    for rid, fix in list(non_zero_fixes.items())[:10]:
        print(f"    {rid}: 0 -> {fix['new_amount']:.2f} (min_before={fix['min_before']:.2f}, min={fix['minimum']:.2f})")

# Impact on public metrics:
# The public metrics score amount_safe_to_pay only for the 25 sample requests.
# For request_05, 14, 15 (our current=0, expected=737/597.74/83.05),
# fixing to min_before-minimum gives: 33375.1 / 1731.74 / 505.63
# These do NOT match expected values (737 / 597.74 / 83.05).
# So this fix would WORSEN the amount score for these 3 requests!
# (Going from 0 -> wrong_nonzero is worse than staying at 0 since 0 is still wrong)

print()
print("="*70)
print("CRITICAL FINDING: Proposed fix does NOT match expected values for P2 cases")
print("="*70)
print()
print("For the 3 P2 sample requests:")
print("  request_05: current=0, proposed=33375.1, expected=737 -> Fix WORSE")
print("  request_14: current=0, proposed=1731.74, expected=597.74 -> Fix WORSE")
print("  request_15: current=0, proposed=505.63,  expected=83.05 -> Fix WORSE")
print()
print("The expected values (737, 597.74, 83.05) cannot be derived from any")
print("simple formula using timeline data. They appear to use a fundamentally")
print("different calculation method for 'amount safe to pay' that we have not")
print("been able to reverse-engineer from the available data.")
print()
print("CONCLUSION: P2 fix cannot be safely implemented without understanding the")
print("exact benchmark formula. The proposed formulas all produce WRONG values.")
print()

# Now check: would ANY formula produce values closer to expected than 0?
print("Distance from expected if we use 0 (current):")
for rid in ['request_05', 'request_14', 'request_15']:
    if rid in expected:
        exp = Decimal(expected[rid]['amount_safe_to_pay'])
        print(f"  {rid}: |0 - {exp}| = {abs(ZERO - exp)}")
print()
print("Distance from expected if we use min_before - minimum:")
for rid in ['request_05', 'request_14', 'request_15']:
    if rid in fixes and rid in expected:
        exp = Decimal(expected[rid]['amount_safe_to_pay'])
        proposed = fixes[rid]['new_amount']
        print(f"  {rid}: |{proposed:.2f} - {exp}| = {abs(proposed - exp):.2f}")

print()
print("Verdict: Current value (0) is CLOSER to expected for request_14 (|0-597|<|1732-597|)")
print("but FURTHER for request_05, 15. Fix would be net-neutral at best, net-harmful at worst.")
print()
print("The scoring for amount_safe_to_pay appears to use a tolerance metric.")
print("Without knowing the exact benchmark formula, P2 fix carries HIGH RISK of worsening score.")
