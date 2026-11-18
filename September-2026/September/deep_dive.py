"""
Deep dive into specific root causes.
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
    build_user_timeline, simulate_payment_plan, get_max_safe_one_time_payment
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

print('\n' + '='*70)
print('DEEP DIVE 1: request_01 - Why simulation fails 90 days out')
print('='*70)
req = index.requests_by_id['request_01']
user_id = req['user_id']
decision = engine.decide(req)
context = decision.context
base_tl = engine.catalog.get(user_id)
timeline = apply_evidence_to_timeline(base_tl, context, index.exchange_rates_by_key)
requested = Decimal(req['requested_amount'])

# Run the simulation and show violation details
sim = simulate_payment_plan(timeline, [('2024-03-03', requested)], requested_amount=requested)
print(f'Feasible: {sim.feasible}')
print(f'Violations: {sim.violations}')
print(f'Min seen: {sim.minimum_balance_seen}')
print(f'Min balance: {timeline.policy.minimum_balance}')
print()
# Show the balance trajectory around the violation
print('Balance trajectory (all checkpoints):')
for cp in sim.balance_checkpoints:
    marker = ' *** VIOLATION ***' if cp.balance_after < timeline.policy.minimum_balance else ''
    print(f'  {cp.date} {cp.kind:<10} {cp.identifier[:30]:<30} delta={cp.cash_delta:>12} bal_after={cp.balance_after:>12}{marker}')

print('\n' + '='*70)
print('DEEP DIVE 2: request_01 - Is there a missing future salary event?')
print('='*70)
print('All income entries in timeline:')
for entry in timeline.entries:
    if entry.event.direction == 'credit':
        print(f'  {entry.effective_date} {entry.net_cash_flow:>12} {entry.event.description} status={entry.event.status} projected={entry.projected}')
print()
# What does the benchmark expect? It says bal keeps 18000 over 90 days after paying 25256
# Starting: 58481.1, pay: 25256, remaining: 33225.1
# The violation is at 2024-05-11 (day 69 after March 03)
# Without any future salary, the money runs out
# Benchmark says this is FINE - means the benchmark expects a salary to appear
# Let's check if there should be a salary in mid-April or so
print('All events for user_01 (financial_events.csv):')
user_events = [e for e in index.events if e['user_id'] == 'user_01']
for ev in sorted(user_events, key=lambda e: e['event_date']):
    if ev['event_type'] in ('income', 'salary') or ev['category'] == 'salary':
        print(f"  {ev['event_id']} {ev['event_date']} {ev['settlement_date']} {ev['status']} {ev['amount']} {ev['currency']} {ev['description']}")
print()

# Show ALL financial events in timeline for this user
print('All canonical events in store:')
for ce in store.by_user.get(user_id, []):
    if ce.direction == 'credit':
        print(f'  {ce.event_id} {ce.effective_date} {ce.amount} {ce.currency} {ce.direction} cat={ce.category} status={ce.status} cash_effect={ce.forecast_cash_effect} eligible={ce.forecast_eligible}')

print('\n' + '='*70)
print('DEEP DIVE 3: request_05, 14, 15 - natural_path_feasible=True but baseline_safe=0')
print('These are cases where our amount_safe_to_pay is UNDER the expected')
print('='*70)
for rid in ['request_05', 'request_14', 'request_15']:
    req2 = index.requests_by_id[rid]
    uid2 = req2['user_id']
    decision2 = engine.decide(req2)
    ctx2 = decision2.context
    tl2 = apply_evidence_to_timeline(engine.catalog.get(uid2), ctx2, index.exchange_rates_by_key)
    requested2 = Decimal(req2['requested_amount'])
    
    baseline2 = get_max_safe_one_time_payment(tl2, req2['request_date'], requested2)
    print(f'\n{rid}: max_safe={baseline2.max_safe_payment} natural_feasible={baseline2.natural_path_feasible}')
    print(f'  min_before={baseline2.minimum_natural_balance_before_payment}')
    print(f'  min_after={baseline2.minimum_natural_balance_after_payment}')
    print(f'  opening={tl2.policy.starting_balance} min_required={tl2.policy.minimum_balance}')
    exp2 = expected[rid]
    print(f'  EXP amount={exp2["amount_safe_to_pay"]}')
    
    # Show entries around request date
    rd = date.fromisoformat(req2['request_date'])
    print(f'  Timeline entries (around request_date):')
    for i, entry in enumerate(tl2.entries):
        ed = date.fromisoformat(entry.effective_date)
        if ed >= rd - timedelta(days=3) and ed <= rd + timedelta(days=10):
            print(f'    {entry.effective_date} cf={entry.net_cash_flow:>12} {entry.event.description[:60]}')
