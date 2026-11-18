"""
Root cause analysis: salary recurrence for multiple users.
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
    _detect_patterns, _pattern_signature
)
from evidence_resolution import apply_evidence_to_timeline
from candidate_plans import CandidateEngine

dataset_dir = Path('tmp_sample_test')
index = DatasetIndex.from_dataset(dataset_dir)
store = normalize_dataset(index)
engine = CandidateEngine(index, store)

ZERO = Decimal('0')

print('SALARY / INCOME RECURRENCE ANALYSIS FOR FAILING REQUESTS\n')

failing_with_status_wrong = [
    ('request_01', 'user_01', '2024-03-03'),  # not_affordable vs affordable_now
    ('request_07', 'user_07', '2024-09-05'),  # not_affordable vs affordable_with_plan
    ('request_08', 'user_08', '2025-02-07'),  # not_affordable vs affordable_later
    ('request_09', 'user_09', '2026-07-04'),  # not_affordable vs affordable_now
    ('request_23', 'user_23', '2025-05-07'),  # not_affordable vs affordable_later
]

for rid, uid, rd in failing_with_status_wrong:
    print(f'\n{"="*60}')
    print(f'{rid} ({uid}) request_date={rd}')
    
    events = store.by_user.get(uid, [])
    eligible = [e for e in events if e.forecast_eligible and e.forecast_cash_effect is not None]
    
    # Income events
    income_events = [e for e in events if e.direction == 'credit' and e.category in ('salary', 'income')]
    settled_income = [e for e in income_events if e.status == 'settled']
    print(f'  Income events: {len(income_events)} ({len(settled_income)} settled)')
    for se in sorted(income_events, key=lambda e: e.effective_date):
        print(f'    {se.event_id} {se.effective_date} {se.status:<10} {se.amount:>12} {se.currency} {se.description}')
    
    # Detect patterns
    patterns = _detect_patterns(eligible)
    income_pats = [p for p in patterns if any(e.direction == 'credit' for e in [store.by_id[sid] for sid in p.source_event_ids if sid in store.by_id])]
    print(f'  Detected income patterns: {len(income_pats)}')
    for p in income_pats:
        print(f'    interval={p.interval_days} amount={p.next_amount} src_count={len(p.source_event_ids)}')
    
    # What patterns are there?
    all_pats = _detect_patterns(eligible)
    print(f'  All patterns: {len(all_pats)}')
    for p in all_pats:
        print(f'    sig={p.signature[0]}|{p.signature[3]} n={len(p.source_event_ids)} interval={p.interval_days} next_amt={p.next_amount}')
    
    # Show timeline entries - specifically income after request_date
    context = engine.evidence.context_for_request(index.requests_by_id[rid])
    base_tl = engine.catalog.get(uid)
    timeline = apply_evidence_to_timeline(base_tl, context, index.exchange_rates_by_key)
    
    print(f'  Opening balance: {timeline.policy.starting_balance}')
    print(f'  Min balance: {timeline.policy.minimum_balance}')
    
    rd_date = date.fromisoformat(rd)
    forecast_end = date.fromisoformat(timeline.forecast_end)
    
    income_after_rd = [e for e in timeline.entries if e.event.direction == 'credit' and date.fromisoformat(e.effective_date) >= rd_date]
    print(f'  Income entries after request_date: {len(income_after_rd)}')
    for e in income_after_rd:
        print(f'    {e.effective_date} {e.net_cash_flow:>12} {e.event.description} projected={e.projected}')
    
    # What's the natural balance at day 90?
    balance = timeline.policy.starting_balance
    day90 = rd_date + timedelta(days=90)
    balances_by_date = {}
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd_date and ed <= day90:
            balance += e.net_cash_flow
            balances_by_date[e.effective_date] = balance
    
    print(f'  Balance 90 days after request: {balance:.2f} (needs to stay > {timeline.policy.minimum_balance})')
    if balances_by_date:
        min_bal = min(balances_by_date.values())
        print(f'  Minimum natural balance 90 days: {min_bal:.2f}')
        # Find when minimum occurs
        min_date = min(balances_by_date, key=lambda d: balances_by_date[d])
        print(f'  Minimum occurs on: {min_date}')
