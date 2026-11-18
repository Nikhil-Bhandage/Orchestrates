"""
P2 exhaustive derivation: try every possible formula to match expected values.
READ-ONLY.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta
from itertools import combinations

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    simulate_payment_plan, get_max_safe_one_time_payment, ZERO
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

def exhaustive_match(rid):
    req = index.requests_by_id[rid]
    exp = expected[rid]
    uid = req['user_id']
    
    ctx = engine.evidence.context_for_request(req)
    timeline = apply_evidence_to_timeline(engine.catalog.get(uid), ctx, index.exchange_rates_by_key)
    
    requested = Decimal(req['requested_amount'])
    request_date = req['request_date']
    dl = req['desired_completion_date']
    exp_amount = Decimal(exp['amount_safe_to_pay'])
    
    opening = timeline.policy.starting_balance
    minimum = timeline.policy.minimum_balance
    baseline = get_max_safe_one_time_payment(timeline, request_date, requested)
    
    rd = date.fromisoformat(request_date)
    dl_date = date.fromisoformat(dl)
    day90 = rd + timedelta(days=90)
    
    print(f"\n{'='*65}")
    print(f"{rid}: expected amount_safe={exp_amount}")
    print(f"  opening={opening}  minimum={minimum}  requested={requested}")
    print(f"  request_date={request_date}  deadline={dl}  day90={day90.isoformat()}")
    
    # Collect all timeline entries after request_date with running balance
    entries_after = []
    balance = opening
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd:
            balance += e.net_cash_flow
            entries_after.append({
                'date': e.effective_date,
                'cf': e.net_cash_flow,
                'balance': balance,
                'desc': e.event.description[:40],
                'event_id': e.event.event_id,
            })
    
    # Try many formulas
    candidates = {}
    
    # F1: min balance to deadline - minimum
    min_to_dl = opening
    b = opening
    for en in entries_after:
        if en['date'] <= dl:
            b = en['balance']
            min_to_dl = min(min_to_dl, b)
    candidates['F1:min_to_deadline-min'] = max(ZERO, min_to_dl - minimum)
    
    # F2: min balance to first_violation - 1 day - minimum
    fv = baseline.first_violation_date
    if fv:
        fv_date = date.fromisoformat(fv)
        min_to_fv_minus1 = opening
        b = opening
        for en in entries_after:
            if en['date'] < fv:
                min_to_fv_minus1 = min(min_to_fv_minus1, en['balance'])
        candidates['F2:min_before_violation-min'] = max(ZERO, min_to_fv_minus1 - minimum)
    
    # F3: opening - minimum (simple headroom)
    candidates['F3:opening-minimum'] = max(ZERO, opening - minimum)
    
    # F4: min_before_payment (from baseline) - minimum
    candidates['F4:min_before_payment-min'] = max(ZERO, baseline.minimum_natural_balance_before_payment - minimum)
    
    # F5: min_after (from baseline, post-payment window) - minimum
    candidates['F5:min_after-min'] = max(ZERO, baseline.minimum_natural_balance_after_payment - minimum)
    
    # F6: balance after same-day events on request_date - minimum
    b = opening
    for en in entries_after:
        if en['date'] == request_date:
            b = en['balance']
        elif en['date'] > request_date:
            break
    candidates['F6:bal_after_sameday-min'] = max(ZERO, b - minimum)
    
    # F7: min to min(deadline, day90) - minimum  
    cutoff = min(dl_date, day90)
    min_to_cutoff = opening
    for en in entries_after:
        if en['date'] <= cutoff.isoformat():
            min_to_cutoff = min(min_to_cutoff, en['balance'])
    candidates['F7:min_to_min(dl,d90)-min'] = max(ZERO, min_to_cutoff - minimum)
    
    # F8: min to JUST deadline - minimum, clamped to requested
    candidates['F8:min_to_dl-min,capped_req'] = min(requested, max(ZERO, min_to_dl - minimum))
    
    # F9: Simulate exp_amount and check minimum_balance_seen - minimum
    sim_exp = simulate_payment_plan(timeline, [(request_date, exp_amount)], requested_amount=None)
    candidates['F9:sim(exp_amount).min_seen-min'] = max(ZERO, sim_exp.minimum_balance_seen - minimum)
    
    # F10: What is the max payment such that balance at deadline stays >= minimum?
    # Binary search
    lo, hi = ZERO, min(requested, opening - minimum)
    for _ in range(60):
        mid = (lo + hi) / Decimal('2')
        sim_mid = simulate_payment_plan(timeline, [(request_date, mid)], requested_amount=None)
        # Check if balance at each checkpoint up to deadline is >= minimum
        ok = all(
            cp.balance_after >= minimum
            for cp in sim_mid.balance_checkpoints
            if cp.date <= dl
        )
        if ok:
            lo = mid
        else:
            hi = mid
    candidates['F10:binary_search(deadline_bounded)'] = lo.quantize(Decimal('0.01'))
    
    # F11: Binary search - 90 day feasible maximum (should give 0 when nat_path infeasible)
    lo2, hi2 = ZERO, min(requested, opening - minimum)
    for _ in range(60):
        mid2 = (lo2 + hi2) / Decimal('2')
        sim_mid2 = simulate_payment_plan(timeline, [(request_date, mid2)], requested_amount=None)
        if sim_mid2.feasible or (not sim_mid2.violations or all('total' in v for v in sim_mid2.violations)):
            lo2 = mid2
        else:
            hi2 = mid2
    candidates['F11:binary_search(90day_feasible)'] = lo2.quantize(Decimal('0.01'))
    
    # F12: min balance from request_date to desired_completion_date, NO INCOME counted
    # (only expenses)
    b = opening
    min_no_income = opening
    for en in entries_after:
        if en['date'] <= dl and en['cf'] < ZERO:
            b += en['cf']
            min_no_income = min(min_no_income, b)
    candidates['F12:min_expenses_only_to_dl-min'] = max(ZERO, min_no_income - minimum)
    
    print(f"  Trying {len(candidates)} formulas against expected={exp_amount}:")
    any_match = False
    for fname, val in sorted(candidates.items()):
        match = abs(val - exp_amount) < Decimal('0.02')
        marker = ' *** MATCH ***' if match else ''
        print(f"  {fname:<45} = {val:>12}{marker}")
        if match:
            any_match = True
    
    if not any_match:
        print(f"\n  NO FORMULA MATCHED. Trying to reverse-engineer from {exp_amount}:")
        # What value V gives: opening - V = minimum + some_expense?
        # opening - exp_amount - minimum = ??
        remainder = opening - exp_amount - minimum
        print(f"  opening({opening}) - exp_amount({exp_amount}) - minimum({minimum}) = {remainder}")
        # Does remainder correspond to any event?
        for en in entries_after:
            if abs(abs(en['cf']) - abs(remainder)) < Decimal('0.02'):
                print(f"  -> Matches cash flow of entry: {en['date']} {en['cf']} {en['desc']}")
        # Check sum of expenses on certain days
        b = opening
        for en in entries_after:
            if en['date'] <= dl:
                old_b = b
                b = en['balance']
                safe_here = max(ZERO, b - minimum)
                if abs(safe_here - exp_amount) < Decimal('1.00'):
                    print(f"  -> Balance after {en['date']} {en['desc']}: safe={safe_here} (delta from exp: {safe_here - exp_amount})")
    
    print()

for rid in ['request_05', 'request_14', 'request_15']:
    exhaustive_match(rid)
