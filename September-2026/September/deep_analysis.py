"""Deep analysis of key sample requests"""
import sys, json, csv
from pathlib import Path
from decimal import Decimal
from datetime import date
sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from financial_timeline import build_user_timeline, get_max_safe_one_time_payment, simulate_payment_plan

dataset_dir = Path('tmp_sample_test')
index = DatasetIndex.from_dataset(dataset_dir)

def analyze_user(user_id, request_id, request_date_str, requested_amount):
    print(f'\n{"="*70}')
    print(f'USER: {user_id}  REQUEST: {request_id}  DATE: {request_date_str}  AMT: {requested_amount}')
    print(f'{"="*70}')
    
    prof_rows = [r for r in index.tables['financial_profiles.csv'] if r['user_id'] == user_id]
    if not prof_rows:
        print('NO PROFILE FOUND')
        return
    p = prof_rows[0]
    print(f'Profile: currency={p["home_currency"]}, min_bal={p["minimum_balance_to_keep"]}')
    print(f'  Adjustable: {p.get("adjustable_spending_categories","")}')
    print(f'  Payment methods: {p["payment_methods_user_will_consider"]}')
    
    # Build timeline
    request_date = date.fromisoformat(request_date_str)
    timeline = build_user_timeline(user_id, request_date, index)
    
    from decimal import Decimal
    min_bal = Decimal(p['minimum_balance_to_keep'])
    
    print(f'\nTimeline opening balance: {timeline.opening_balance}')
    print(f'Min balance: {min_bal}')
    
    # Get max safe payment
    result = get_max_safe_one_time_payment(timeline, min_bal, request_date, request_date + __import__('datetime').timedelta(days=90))
    print(f'\nMax safe payment on request_date: {result.max_amount}')
    print(f'Earliest date for full amt ({requested_amount}): {result.earliest_full_payment_date}')
    
    # Show timeline entries around request date
    print('\nTimeline entries (first 15):')
    for i, entry in enumerate(timeline.entries[:15]):
        print(f'  {entry.entry_date} {entry.amount:>15} {entry.event_type:<25} {entry.description[:50]}')
    
    # Show balance at request date
    bal = timeline.opening_balance
    for entry in timeline.entries:
        if entry.entry_date <= request_date:
            bal += entry.amount
    print(f'\nBalance at request_date {request_date_str}: {bal}')
    print(f'Amount safe to pay (bal - min): {bal - min_bal}')

# Key problematic cases
analyze_user('user_01', 'request_01', '2024-03-03', Decimal('25256'))
