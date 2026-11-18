"""
Comprehensive forensic analysis of all 23 failing sample requests.
READ-ONLY: No modifications made.
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

expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

ZERO = Decimal('0')

# All 23 mismatching requests
failing_rids = [
    'request_01', 'request_02', 'request_03', 'request_04', 'request_05',
    'request_06', 'request_07', 'request_08', 'request_09', 'request_10',
    'request_11', 'request_13', 'request_14', 'request_15',
    'request_17', 'request_18', 'request_19', 'request_20', 'request_21',
    'request_22', 'request_23', 'request_24', 'request_25'
]

for rid in failing_rids:
    req = index.requests_by_id[rid]
    exp = expected[rid]
    user_id = req['user_id']
    profile = index.profiles_by_user[user_id]
    
    decision = engine.decide(req)
    candidate = decision.selected
    context = decision.context
    base_tl = engine.catalog.get(user_id)
    timeline = apply_evidence_to_timeline(base_tl, context, index.exchange_rates_by_key)
    
    requested = Decimal(req['requested_amount'])
    request_date = req['request_date']
    deadline = req['desired_completion_date']
    
    baseline = get_max_safe_one_time_payment(timeline, request_date, requested)
    
    exp_amount = Decimal(exp['amount_safe_to_pay'])
    our_amount = candidate.amount_safe_to_pay
    exp_status = exp['affordability_status']
    our_status = decision.affordability_status
    
    # Test all dates for full payment
    dates_tested = []
    for d in engine._payment_dates(timeline, req):
        if d <= deadline:
            sim = simulate_payment_plan(timeline, [(d, requested)], requested_amount=requested)
            dates_tested.append((d, sim.feasible, sim.minimum_balance_seen))
    
    feasible_dates = [(d, minbal) for d, f, minbal in dates_tested if f]
    earliest_feasible = feasible_dates[0][0] if feasible_dates else ''
    
    print(f'\n{"="*70}')
    print(f'{rid} ({user_id}, {profile["home_currency"]}): {req["request_type"]} amt={req["requested_amount"]} date={request_date} deadline={deadline}')
    print(f'  EXP: status={exp_status} method={exp["recommended_payment_method"]} amount={exp_amount} earliest={exp["earliest_date_for_full_payment"]} spending={exp["spending_changes_needed"]}')
    print(f'  OUR: status={our_status} method={candidate.payment_method} amount={our_amount} earliest={decision.earliest_full_payment_date} spending={candidate.spending_changes}')
    print(f'  bal={timeline.policy.starting_balance} min={timeline.policy.minimum_balance}')
    print(f'  baseline_safe={baseline.max_safe_payment} min_after={baseline.minimum_natural_balance_after_payment}')
    print(f'  Our earliest by simulation: {earliest_feasible}')
    print(f'  Expected earliest: {exp["earliest_date_for_full_payment"]}')
    print(f'  Dates tested feasible: {feasible_dates[:5]}')
    
    # Categorize the bug
    bugs = []
    
    # A) Status wrong
    if exp_status != our_status:
        bugs.append(f'STATUS WRONG: exp={exp_status} our={our_status}')
    
    # B) Amount wrong - too high
    if abs(our_amount - exp_amount) > Decimal('0.01'):
        direction = 'OVER' if our_amount > exp_amount else 'UNDER'
        bugs.append(f'AMOUNT {direction} by {abs(our_amount - exp_amount):.2f}')
    
    # C) Earliest date wrong  
    exp_earliest = exp['earliest_date_for_full_payment']
    our_earliest = decision.earliest_full_payment_date
    if exp_earliest != our_earliest:
        bugs.append(f'EARLIEST WRONG: exp={exp_earliest} our={our_earliest} sim_found={earliest_feasible}')
    
    # D) Spending changes wrong
    exp_spending = exp['spending_changes_needed']
    our_spending = '|'.join(candidate.spending_changes) if candidate.spending_changes else 'none'
    if exp_spending != our_spending:
        bugs.append(f'SPENDING WRONG: exp={exp_spending} our={our_spending}')
    
    print(f'  BUGS: {bugs}')
    print(f'  rejections={dict(decision.rejection_counts)}')
