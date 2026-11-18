"""
Targeted forensic analysis per request - READ ONLY.
"""
import sys, json, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    build_user_timeline, get_max_safe_one_time_payment, simulate_payment_plan,
    TimelineCatalog
)
from evidence_resolution import EvidenceResolver, apply_evidence_to_timeline
from candidate_plans import CandidateEngine

dataset_dir = Path('tmp_sample_test')
index = DatasetIndex.from_dataset(dataset_dir)
store = normalize_dataset(index)
engine = CandidateEngine(index, store)

# Load expected answers
expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

ZERO = Decimal('0')

def analyze_request(rid):
    req = index.requests_by_id[rid]
    exp = expected[rid]
    user_id = req['user_id']
    profile = index.profiles_by_user[user_id]
    
    print(f'\n{"="*70}')
    print(f'REQUEST: {rid}  USER: {user_id}  TYPE: {req["request_type"]}')
    print(f'  Amount: {req["requested_amount"]}  Date: {req["request_date"]}  Deadline: {req["desired_completion_date"]}')
    print(f'  Currency: {profile["home_currency"]}  Min balance: {profile["minimum_balance_to_keep"]}')
    print(f'  Starting balance: {profile["current_available_balance"]}')
    print(f'  Payment methods: {profile["payment_methods_user_will_consider"]}')
    print(f'  Allows partial: {req["allows_partial_payment"]}')
    
    print(f'\n  EXPECTED: status={exp["affordability_status"]} method={exp["recommended_payment_method"]}')
    print(f'    amount_safe={exp["amount_safe_to_pay"]}  earliest={exp["earliest_date_for_full_payment"]}')
    print(f'    spending={exp["spending_changes_needed"]}  plan={exp["payment_plan"]}')
    
    decision = engine.decide(req)
    candidate = decision.selected
    context = decision.context
    base_tl = engine.catalog.get(user_id)
    timeline = apply_evidence_to_timeline(base_tl, context, index.exchange_rates_by_key)
    
    print(f'\n  OUR: status={decision.affordability_status} method={candidate.payment_method}')
    print(f'    amount_safe={candidate.amount_safe_to_pay}  earliest={decision.earliest_full_payment_date}')
    print(f'    spending={candidate.spending_changes}  plan={candidate.payment_schedule}')
    print(f'    feasible_count={len(decision.feasible_candidates)}  rejections={dict(decision.rejection_counts)}')
    
    # Baseline
    requested = Decimal(req['requested_amount'])
    request_date = req['request_date']
    baseline = get_max_safe_one_time_payment(timeline, request_date, requested)
    print(f'\n  Baseline: max_safe={baseline.max_safe_payment} natural_feasible={baseline.natural_path_feasible}')
    print(f'  Min before payment: {baseline.minimum_natural_balance_before_payment}')
    print(f'  Min after payment: {baseline.minimum_natural_balance_after_payment}')
    print(f'  Opening balance: {timeline.policy.starting_balance}')
    print(f'  Min balance: {timeline.policy.minimum_balance}')
    
    # Show timeline entries around request date
    request_d = date.fromisoformat(request_date)
    print(f'\n  Timeline entries (around request_date +-5 days, first 25):')
    count = 0
    for i, entry in enumerate(timeline.entries):
        entry_d = date.fromisoformat(entry.effective_date)
        if entry_d >= request_d - timedelta(days=5):
            print(f'    [{i}] {entry.effective_date} cf={entry.net_cash_flow:>12} {entry.event.event_type:<20} {entry.event.description[:60]} status={entry.event.status}')
            count += 1
            if count >= 25:
                break
    
    # Check if full payment candidate would pass
    options = index.options_by_request.get(rid, [])
    full_pay_options = [o for o in options if o['payment_method'] == 'full_payment']
    if full_pay_options:
        o = full_pay_options[0]
        print(f'\n  Testing full_payment option: first={o["first_payment_date"]} amt={o["payment_amount"]} total={o["total_payable_amount"]}')
        # Does first_payment_date match request_date?
        print(f'  first_payment_date == request_date? {o["first_payment_date"] == request_date}')
        sim = simulate_payment_plan(timeline, [(request_date, requested)], requested_amount=requested)
        print(f'  Direct simulate result: feasible={sim.feasible}')
        print(f'  Violations: {sim.violations[:5]}')
        print(f'  Min seen: {sim.minimum_balance_seen}')
    
    return decision

# Group A: Status completely wrong
for rid in ['request_01', 'request_07', 'request_08', 'request_09', 'request_23']:
    analyze_request(rid)
