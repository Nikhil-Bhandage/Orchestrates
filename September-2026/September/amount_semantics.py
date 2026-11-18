"""
Analysis of amount_safe_to_pay semantics and specific discrepancies.
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
print('AMOUNT_SAFE_TO_PAY SEMANTICS ANALYSIS')
print('Spec says: "largest amount user can safely pay on request_date BEFORE')
print('optional spending changes, while covering protected expenses and')
print('maintaining their minimum balance"')
print('='*70)

# Key cases where our amount is too HIGH
# This means we are computing a higher "safe amount" than what the benchmark expects
# Possible causes:
# 1. We're including income that the benchmark treats as uncertain
# 2. The benchmark uses a different computation window (just deadline, not 90 days)
# 3. The benchmark includes events we are not including

print('\n--- request_20: EXP=5400 OUR=23818.52 ---')
req20 = index.requests_by_id['request_20']
uid20 = 'user_20'
ctx20 = engine.evidence.context_for_request(req20)
tl20 = apply_evidence_to_timeline(engine.catalog.get(uid20), ctx20, index.exchange_rates_by_key)
requested20 = Decimal(req20['requested_amount'])

print(f'  Opening balance: {tl20.policy.starting_balance}')
print(f'  Min balance: {tl20.policy.minimum_balance}')
print(f'  Expected amount_safe: 5400')
print(f'  Our amount_safe: 23818.52 (= {tl20.policy.starting_balance} - {tl20.policy.minimum_balance} + surplus)')
print(f'  Diff: {tl20.policy.starting_balance - tl20.policy.minimum_balance} = {102609.05 - 64500}')
print(f'  Our min_after: 88318.52 (= min_bal + 23818.52)')

rd20 = req20['request_date']
dl20 = req20['desired_completion_date']
print(f'  deadline: {dl20}  horizon: +90 days = {(date.fromisoformat(rd20) + timedelta(days=90)).isoformat()}')

print()
print('  Timeline entries after request_date:')
rd20_d = date.fromisoformat(rd20)
balance = tl20.policy.starting_balance
for i, e in enumerate(tl20.entries):
    ed = date.fromisoformat(e.effective_date)
    if ed >= rd20_d and i < 35:
        balance += e.net_cash_flow
        print(f'    [{i}] {e.effective_date} cf={e.net_cash_flow:>12} bal={balance:>12} {e.event.description[:50]}')

# The issue: are there events we should see before the request_date affecting the opening balance?
print()
print('  Events BEFORE request_date:')
for e in tl20.entries:
    ed = date.fromisoformat(e.effective_date)
    if ed < rd20_d and ed >= rd20_d - timedelta(days=30):
        print(f'    {e.effective_date} cf={e.net_cash_flow:>12} {e.event.description[:60]} status={e.event.status}')

# Check all raw events for this user
print()
print('  ALL financial events for user_20:')
user20_events = sorted([e for e in index.events if e['user_id'] == 'user_20'], key=lambda e: e['event_date'])
for ev in user20_events:
    print(f'    {ev["event_id"]} {ev["event_date"]} {ev["status"]:<10} {ev["amount"]:>12} {ev["currency"]} {ev["description"][:60]}')

print()
print('='*70)
print('request_25: EXP=1425000 OUR=3838582.88')
print('='*70)

req25 = index.requests_by_id['request_25']
uid25 = 'user_25'
ctx25 = engine.evidence.context_for_request(req25)
tl25 = apply_evidence_to_timeline(engine.catalog.get(uid25), ctx25, index.exchange_rates_by_key)

print(f'  Opening balance: {tl25.policy.starting_balance}')
print(f'  Min balance: {tl25.policy.minimum_balance}')
print(f'  request_date: {req25["request_date"]}  deadline: {req25["desired_completion_date"]}')

rd25 = req25['request_date']
rd25_d = date.fromisoformat(rd25)
print()
print('  Events around request_date:')
balance = tl25.policy.starting_balance
for i, e in enumerate(tl25.entries):
    ed = date.fromisoformat(e.effective_date)
    if ed >= rd25_d - timedelta(days=10) and ed <= rd25_d + timedelta(days=40):
        balance += e.net_cash_flow
        print(f'  {e.effective_date} cf={e.net_cash_flow:>15} bal={balance:>15} {e.event.description[:50]} status={e.event.status}')

print()
print('  Raw events (ALL):')
user25_events = sorted([e for e in index.events if e['user_id'] == 'user_25'], key=lambda e: e['event_date'])
for ev in user25_events:
    print(f'  {ev["event_id"]} {ev["event_date"]} {ev["status"]:<10} {ev["amount"]:>15} {ev["currency"]} {ev["description"][:60]}')
