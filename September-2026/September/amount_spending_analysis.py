"""
Root cause analysis for amount_safe_to_pay discrepancies and spending changes issues.
READ-ONLY analysis.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import (
    simulate_payment_plan, get_max_safe_one_time_payment
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

ZERO = Decimal('0')

print('='*70)
print('ROOT CAUSE ANALYSIS: amount_safe_to_pay discrepancies')
print('='*70)

print('\n--- Case A: We are too OPTIMISTIC (our amount > expected) ---')
print('This means we are missing some future outflow that the benchmark includes')
print('OR the benchmark "amount_safe_to_pay" is computed differently')
print()

# Check request_09: natural balance 90 days = 762.72, min=600
# We say amount_safe = 162.72, benchmark says 166.61 (= full amount)
# But our simulation fails at day 89 (2026-09-30) when balance hits 596.11 < 600
# The benchmark says this is "affordable_now" = full amount can be paid
# Key question: is the benchmark using the REQUEST_DATE min balance, not full 90-day horizon?
print('request_09 analysis:')
req09 = index.requests_by_id['request_09']
uid09 = 'user_09'
ctx09 = engine.evidence.context_for_request(req09)
base_tl09 = engine.catalog.get(uid09)
tl09 = apply_evidence_to_timeline(base_tl09, ctx09, index.exchange_rates_by_key)
requested09 = Decimal('166.61')
sim09 = simulate_payment_plan(tl09, [('2026-07-04', requested09)], requested_amount=requested09)
print(f'  Full simulation: feasible={sim09.feasible}')
print(f'  Violations: {sim09.violations}')
print(f'  Min seen: {sim09.minimum_balance_seen}  needed: {tl09.policy.minimum_balance}')
print()

# The 90-day check is what causes the violation.
# But user_09 has freelance income that is NOT recurring (irregular).
# The natural balance at day 90 is 762.72 (from salary analysis)
# After paying 166.61 -> 596.11 which is below 600
# The benchmark says this IS affordable now.
# INSIGHT: maybe the benchmark's "next 90 days" starts from request_date+1?
# or maybe it uses desired_completion_date as the horizon, not 90 days?

# Let's check: desired_completion_date = 2026-07-23 (only 19 days from request)
print(f'  desired_completion_date: {req09["desired_completion_date"]}')
print(f'  request_date: {req09["request_date"]}')
print(f'  Days between: {(date.fromisoformat(req09["desired_completion_date"]) - date.fromisoformat(req09["request_date"])).days}')
print()

# Simulate with deadline-bounded horizon
sim09_deadline = simulate_payment_plan(tl09, [('2026-07-04', requested09)], requested_amount=requested09)
# Check balance only up to deadline
dl_date = date.fromisoformat(req09['desired_completion_date'])
print(f'  Balance at deadline ({req09["desired_completion_date"]}):')
balance = tl09.policy.starting_balance
for cp in sim09_deadline.balance_checkpoints:
    if date.fromisoformat(cp.date) <= dl_date:
        balance = cp.balance_after
print(f'    balance = {balance}')
print()

# Check all checkpoints up to deadline
print('  Checkpoints up to deadline:')
for cp in sim09_deadline.balance_checkpoints:
    cp_date = date.fromisoformat(cp.date)
    if cp_date <= dl_date:
        print(f'    {cp.date} bal={cp.balance_after:.2f}')

print()
print('  Checkpoints AFTER deadline (causing violation):')
for cp in sim09_deadline.balance_checkpoints:
    cp_date = date.fromisoformat(cp.date)
    if cp_date > dl_date:
        marker = ' *** VIOLATION ***' if cp.balance_after < tl09.policy.minimum_balance else ''
        print(f'    {cp.date} bal={cp.balance_after:.2f}{marker}')

print()
print('='*70)
print('ROOT CAUSE ANALYSIS: Spending changes not being found')  
print('='*70)
print()

# request_06: EXP spending=stop:event_476, OUR spending=none
# request_11: EXP spending=reduce_to:event_989:665950, OUR spending=none
# request_21: EXP spending=stop:event_1815|reduce_to:event_1816:23.50, OUR spending=none

for rid in ['request_06', 'request_11', 'request_21']:
    req = index.requests_by_id[rid]
    exp = expected[rid]
    uid = req['user_id']
    ctx = engine.evidence.context_for_request(req)
    base_tl = engine.catalog.get(uid)
    timeline = apply_evidence_to_timeline(base_tl, ctx, index.exchange_rates_by_key)
    
    print(f'\n--- {rid} ({uid}) ---')
    print(f'  EXP spending: {exp["spending_changes_needed"]}')
    print(f'  EXP status: {exp["affordability_status"]}')
    print(f'  EXP amount_safe: {exp["amount_safe_to_pay"]}')
    print(f'  EXP earliest: {exp["earliest_date_for_full_payment"]}')
    
    # What events are in the change_index?
    print(f'  change_index targets: {list(timeline.change_index.keys())}')
    
    # Can we find event_476, event_989, event_1815, event_1816?
    for expected_event_id in ['event_476', 'event_989', 'event_1815', 'event_1816']:
        event = store.by_id.get(expected_event_id)
        if event:
            print(f'  {expected_event_id}: type={event.event_type} cat={event.category} flex={event.flexibility} status={event.status} eligible={event.forecast_eligible}')
            # Is it in the change_index?
            in_change = expected_event_id in timeline.change_index
            print(f'    In change_index: {in_change}')
            # Is it projected?
            in_entries = [e for e in timeline.entries if e.event.event_id == expected_event_id or expected_event_id in e.change_event_ids]
            print(f'    In entries with change: {len(in_entries)} entries')
            for e in in_entries:
                print(f'      {e.effective_date} cf={e.net_cash_flow} change_ids={e.change_event_ids}')
    
    # Show changesets generated
    changesets = engine._change_sets(timeline)
    print(f'  Generated changesets: {len(changesets)}')
    for cs in changesets[:10]:
        print(f'    {cs}')
    
    # What is the full_payment simulation WITHOUT spending changes?
    requested = Decimal(req['requested_amount'])
    request_date = req['request_date']
    sim_no_changes = simulate_payment_plan(timeline, [(request_date, requested)], requested_amount=requested)
    print(f'  Full payment no-changes: feasible={sim_no_changes.feasible} min_seen={sim_no_changes.minimum_balance_seen}')
    print(f'  Policy minimum: {timeline.policy.minimum_balance}')
    print(f'  Stoppable categories: {timeline.policy.stoppable_categories}')
    print(f'  Reducible categories: {timeline.policy.reducible_categories}')
