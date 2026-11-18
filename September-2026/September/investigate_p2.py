"""
P2 Investigation: amount_safe_to_pay = 0 when natural path infeasible.
READ-ONLY. No source modifications.

Investigates requests 05, 14, 15 in detail.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    build_user_timeline, simulate_payment_plan, get_max_safe_one_time_payment,
    UserTimeline, ZERO
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

def investigate_p2(rid):
    req = index.requests_by_id[rid]
    exp = expected[rid]
    uid = req['user_id']
    profile = index.profiles_by_user[uid]
    
    ctx = engine.evidence.context_for_request(req)
    timeline = apply_evidence_to_timeline(engine.catalog.get(uid), ctx, index.exchange_rates_by_key)
    
    requested = Decimal(req['requested_amount'])
    request_date = req['request_date']
    rd = date.fromisoformat(request_date)
    exp_amount = Decimal(exp['amount_safe_to_pay'])
    
    print(f'\n{"="*70}')
    print(f'P2 INVESTIGATION: {rid} ({uid})')
    print(f'{"="*70}')
    
    # Q1: Opening balance
    opening = timeline.policy.starting_balance
    minimum = timeline.policy.minimum_balance
    print(f'\n1. Opening balance (from profile.current_available_balance): {opening}')
    print(f'2. Minimum required balance:                                  {minimum}')
    print(f'   Naive headroom (opening - minimum):                        {opening - minimum}')
    
    # Q3: List every cash flow on/after request_date chronologically
    print(f'\n3. Cash flows on request_date {request_date} and subsequent days:')
    print(f'   (All entries including same-day outflows before any payment)')
    
    balance = opening
    same_day_outflows = Decimal('0')
    same_day_inflows = Decimal('0')
    first_natural_min = opening   # min balance seen across natural path
    min_date = ''
    
    print(f'   {"DATE":<12} {"DELTA":>14}  {"BALANCE":>14}  DESCRIPTION')
    print(f'   {"-"*12}  {"-"*14}  {"-"*14}  {"-"*50}')
    
    # Show first 25 entries starting from request_date
    count = 0
    for entry in timeline.entries:
        ed = date.fromisoformat(entry.effective_date)
        if ed >= rd:
            cf = entry.net_cash_flow
            balance += cf
            first_natural_min = min(first_natural_min, balance)
            if balance == first_natural_min:
                min_date = entry.effective_date
            if ed == rd:
                if cf < ZERO:
                    same_day_outflows += cf  # already negative
                else:
                    same_day_inflows += cf
            marker = ' <-- MIN' if balance == first_natural_min else ''
            print(f'   {entry.effective_date:<12}  {cf:>14}  {balance:>14}  {entry.event.description[:50]}{marker}')
            count += 1
            if count >= 30:
                print(f'   ... (truncated at 30 entries)')
                break
    
    print(f'\n   Same-day outflows on request_date: {same_day_outflows} (negative)')
    print(f'   Same-day inflows  on request_date: {same_day_inflows}')
    print(f'   Minimum natural balance seen:       {first_natural_min} on {min_date}')
    
    # Q4: Derive the spec-compliant safe amount
    # Spec: "amount_safe_to_pay is the amount safe on request_date before optional spending changes"
    # Current implementation: returns 0 when natural_path_feasible = False
    # natural_path_feasible = (min_before >= min) AND (min_after >= min)
    # min_before = min balance seen from anchor to payment (on request_date)
    # min_after = min balance seen from after payment to end of forecast
    
    baseline = get_max_safe_one_time_payment(timeline, request_date, requested)
    print(f'\n4. Current implementation:')
    print(f'   get_max_safe_one_time_payment result:')
    print(f'     max_safe_payment:  {baseline.max_safe_payment}')
    print(f'     natural_feasible:  {baseline.natural_path_feasible}')
    print(f'     min_before:        {baseline.minimum_natural_balance_before_payment}')
    print(f'     min_after:         {baseline.minimum_natural_balance_after_payment}')
    print(f'     first_violation:   {baseline.first_violation_date}')
    print(f'   => Returns 0 because natural_path_feasible=False')
    
    # Q5: Alternative calculation: point-in-time on request_date
    # What is the balance JUST BEFORE any same-day outflows on request_date?
    # = opening balance (since same-day events haven't fired yet)
    # Safe amount ON request_date = opening - minimum = maximum you can spend without touching minimum
    # BUT outflows that fire same-day (before the payment, since natural events win ties)
    # reduce effective capacity.
    
    # The simulator applies: same-day natural events first, then payment.
    # So on request_date: balance after same-day naturals = opening + same_day_outflows + same_day_inflows
    # Then payment fires.
    # For the payment to be safe: balance_after_naturals - payment >= minimum
    # => payment <= balance_after_naturals - minimum
    
    balance_after_same_day = opening + same_day_outflows + same_day_inflows
    point_in_time_safe = max(ZERO, balance_after_same_day - minimum)
    
    print(f'\n5. Spec-derived point-in-time safe amount:')
    print(f'   balance_after_same_day_naturals = {opening} + ({same_day_outflows}) + {same_day_inflows} = {balance_after_same_day}')
    print(f'   point_in_time_safe = max(0, {balance_after_same_day} - {minimum}) = {point_in_time_safe}')
    print(f'   Expected (public):  {exp_amount}')
    print(f'   Match: {abs(point_in_time_safe - exp_amount) < Decimal("0.01")}')
    
    # Alternative: min_before_payment only (ignoring min_after)
    min_before_only_safe = max(ZERO, baseline.minimum_natural_balance_before_payment - minimum)
    print(f'\n   Alternative (min_before only, ignoring min_after):')
    print(f'   max(0, min_before - minimum) = max(0, {baseline.minimum_natural_balance_before_payment} - {minimum}) = {min_before_only_safe}')
    print(f'   Match: {abs(min_before_only_safe - exp_amount) < Decimal("0.01")}')
    
    # Q6: Can expected be derived exactly?
    print(f'\n6. Expected = {exp_amount}. Derivation check:')
    # Try: expected = opening - minimum - sum(absolute same-day outflows)
    abs_outflows = -same_day_outflows  # make positive
    formula_a = max(ZERO, opening - minimum - abs_outflows)
    print(f'   Formula A: opening({opening}) - min({minimum}) - same_day_outflows({abs_outflows}) = {formula_a}. Match: {abs(formula_a - exp_amount) < Decimal("0.01")}')
    
    # Try: min_before_payment - minimum
    formula_b = max(ZERO, baseline.minimum_natural_balance_before_payment - minimum)
    print(f'   Formula B: min_before({baseline.minimum_natural_balance_before_payment}) - min({minimum}) = {formula_b}. Match: {abs(formula_b - exp_amount) < Decimal("0.01")}')
    
    # Try: balance after applying ALL events up to (but not including) the first event AFTER request_date
    # i.e., balance at END of request_date (after all same-day events)
    formula_c = max(ZERO, balance_after_same_day - minimum)
    print(f'   Formula C: (bal_after_all_sameday) - min = {balance_after_same_day} - {minimum} = {formula_c}. Match: {abs(formula_c - exp_amount) < Decimal("0.01")}')
    
    # Q7: Would changing amount_safe_to_pay affect feasibility/recommendation?
    print(f'\n7. Would fixing amount_safe_to_pay affect candidacy or recommendation?')
    decision = engine.decide(req)
    candidate = decision.selected
    print(f'   Current decision: method={candidate.payment_method} status={decision.affordability_status}')
    print(f'   Feasible candidates: {len(decision.feasible_candidates)}')
    # amount_safe_to_pay in not_recommended case is set to baseline_safe
    # Changing the baseline_safe formula would only change the output amount_safe_to_pay field
    # The candidate selection logic uses simulation_result.feasible for determining candidates,
    # not amount_safe_to_pay. So changing the formula would only affect the output field.
    print(f'   Since all candidates are rejected (0 feasible), changing amount_safe_to_pay')
    print(f'   ONLY changes the output field. It does NOT affect method or status selection.')

for rid in ['request_05', 'request_14', 'request_15']:
    investigate_p2(rid)
