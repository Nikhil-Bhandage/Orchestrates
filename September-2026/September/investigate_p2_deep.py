"""
P2 deep dive: Exact derivation of expected amount_safe_to_pay.
READ-ONLY.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    simulate_payment_plan, get_max_safe_one_time_payment, ZERO, UserTimeline
)
from evidence_resolution import apply_evidence_to_timeline
from candidate_plans import CandidateEngine

dataset_dir = Path('tmp_sample_test')
index = DatasetIndex.from_dataset(dataset_dir)
store = normalize_dataset(index)
engine = CandidateEngine(index, store)

expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

# KEY INSIGHT TO INVESTIGATE:
# For request_05: 
#   natural_feasible=False (violation at 2026-02-03, which is BEYOND deadline 2026-01-12)
#   min_after = 10921.32 (not 0, because the floor is 90 days out)
#   request_date=2025-11-06, deadline=2026-01-12, 90_days=2026-02-04
#   The violation is at 2026-02-03 which is within the 90-day window
# For request_14:
#   natural_feasible=False (violation at 2025-10-05)
#   request_date=2025-08-09, deadline=2025-10-04, 90_days=2025-11-07
#   The violation is at 2025-10-05 which is within 90-day window (but AFTER deadline!)
# For request_15:
#   natural_feasible=False (violation at 2026-03-08)
#   request_date=2026-01-06, deadline=2026-02-01, 90_days=2026-04-06
#   Violation at 2026-03-08 within 90-day window but AFTER deadline

print("="*70)
print("P2 DEEP DIVE: EXACT EXPECTED VALUE DERIVATION")
print("="*70)

cases = [
    ('request_05', 'user_05', '2025-11-06', '2026-01-12'),
    ('request_14', 'user_14', '2025-08-09', '2025-10-04'),
    ('request_15', 'user_15', '2026-01-06', '2026-02-01'),
]

for rid, uid, rd_str, dl_str in cases:
    req = index.requests_by_id[rid]
    exp = expected[rid]
    exp_amount = Decimal(exp['amount_safe_to_pay'])
    
    ctx = engine.evidence.context_for_request(req)
    timeline = apply_evidence_to_timeline(engine.catalog.get(uid), ctx, index.exchange_rates_by_key)
    
    requested = Decimal(req['requested_amount'])
    opening = timeline.policy.starting_balance
    minimum = timeline.policy.minimum_balance
    
    rd = date.fromisoformat(rd_str)
    dl = date.fromisoformat(dl_str)
    day90 = rd + timedelta(days=90)
    
    baseline = get_max_safe_one_time_payment(timeline, rd_str, requested)
    
    print(f"\n{'='*60}")
    print(f"{rid}: request_date={rd_str} deadline={dl_str} day90={day90.isoformat()}")
    print(f"  opening={opening} minimum={minimum} first_violation={baseline.first_violation_date}")
    print(f"  natural_feasible={baseline.natural_path_feasible}")
    print(f"  Expected amount_safe={exp_amount}")
    
    # Compute the natural balance trajectory up to different horizons
    # Hypothesis 1: Use only up to DEADLINE
    bal = opening
    min_to_deadline = opening
    min_to_deadline_date = rd_str
    print(f"\n  Natural balance from {rd_str} to deadline {dl_str}:")
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd and ed <= dl:
            bal += e.net_cash_flow
            if bal < min_to_deadline:
                min_to_deadline = bal
                min_to_deadline_date = e.effective_date
    
    safe_to_deadline = max(ZERO, min_to_deadline - minimum)
    print(f"  min_balance_to_deadline = {min_to_deadline} on {min_to_deadline_date}")
    print(f"  safe_by_deadline = max(0, {min_to_deadline} - {minimum}) = {safe_to_deadline}")
    print(f"  Match expected ({exp_amount}): {abs(safe_to_deadline - exp_amount) < Decimal('0.01')}")
    
    # Hypothesis 2: Use deadline-bounded simulation
    # Simulate paying exp_amount on request_date and check only up to deadline
    # But simulation always runs 90 days...
    # Instead, check: what is max(0, min_to_deadline) - minimum - exp_amount?
    # If exp_amount = safe_to_deadline, then this is zero.
    
    # Hypothesis 3: Is it the min_before_payment (anchor → payment date)?
    safe_before_only = max(ZERO, baseline.minimum_natural_balance_before_payment - minimum)
    print(f"\n  safe_min_before_only = max(0, {baseline.minimum_natural_balance_before_payment} - {minimum}) = {safe_before_only}")
    print(f"  Match expected: {abs(safe_before_only - exp_amount) < Decimal('0.01')}")
    
    # Let's check if paying exp_amount on request_date is feasible within deadline
    sim_exp = simulate_payment_plan(timeline, [(rd_str, exp_amount)], requested_amount=requested)
    print(f"\n  simulate_payment_plan with pay=exp_amount={exp_amount} on {rd_str}:")
    print(f"  feasible={sim_exp.feasible} min_seen={sim_exp.minimum_balance_seen}")
    print(f"  violations={sim_exp.violations[:3]}")
    
    # Also simulate with our computed safe amount to see what happens
    our_safe = baseline.max_safe_payment  # = 0
    
    # Let's also check: what happens if we use the min_after as the safe amount 
    # i.e., max(0, min_after - min) where min_after is the post-payment minimum?
    # For not_natural_feasible: min_after = 10921.32 (request_05)
    # max(0, 10921.32 - 13100) = 0 → doesn't give 737
    
    # Try: the safe amount is the minimum balance achievable before first_violation
    # = minimum balance seen BEFORE the first violation - minimum_balance
    # Scan entries and find balance just before first_violation
    print(f"\n  Searching for derivation of expected={exp_amount}...")
    
    # Try: natural balance up to JUST BEFORE the first sub-minimum event
    first_viol = date.fromisoformat(baseline.first_violation_date)
    bal = opening
    min_up_to_viol = opening
    last_ok_balance = opening
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd and ed < first_viol:
            bal += e.net_cash_flow
            if bal < min_up_to_viol:
                min_up_to_viol = bal
        elif ed == first_viol:
            # Balance just before this event
            last_ok_balance = bal
            break
    
    safe_up_to_viol = max(ZERO, last_ok_balance - minimum)
    print(f"  Balance just before first violation ({baseline.first_violation_date}): {last_ok_balance}")
    print(f"  safe = max(0, {last_ok_balance} - {minimum}) = {safe_up_to_viol}")
    print(f"  Match expected: {abs(safe_up_to_viol - exp_amount) < Decimal('0.01')}")
    
    # Try: the minimum balance in the window [request_date, min(deadline, first_violation - 1 day)]
    cutoff = min(dl, first_viol - timedelta(days=1))
    bal = opening
    min_to_cutoff = opening
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd and ed <= cutoff:
            bal += e.net_cash_flow
            min_to_cutoff = min(min_to_cutoff, bal)
    
    safe_to_cutoff = max(ZERO, min_to_cutoff - minimum)
    print(f"\n  Window [request_date, min(deadline={dl_str}, first_violation-1={baseline.first_violation_date})]:")
    print(f"  cutoff = {cutoff.isoformat()}")
    print(f"  min_in_window = {min_to_cutoff}")
    print(f"  safe = max(0, {min_to_cutoff} - {minimum}) = {safe_to_cutoff}")
    print(f"  Match expected: {abs(safe_to_cutoff - exp_amount) < Decimal('0.01')}")
