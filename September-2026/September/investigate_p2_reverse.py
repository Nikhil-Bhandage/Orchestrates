"""
P2 reverse-engineering: exhaustive scan of all timeline-derivable values.
READ-ONLY.
"""
import sys, csv
from pathlib import Path
from decimal import Decimal
from datetime import date, timedelta

sys.path.insert(0, 'code')

from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import simulate_payment_plan, get_max_safe_one_time_payment, ZERO
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

def reverse_engineer(rid):
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
    
    rd = date.fromisoformat(request_date)
    dl_date = date.fromisoformat(dl)
    
    print(f"\n{'='*65}")
    print(f"{rid} (uid={uid})")
    print(f"  request_date={request_date}  deadline={dl}")
    print(f"  opening={opening}  minimum={minimum}  requested={requested}")
    print(f"  expected amount_safe={exp_amount}")

    # Collect full timeline with running balance
    bal = opening
    entries = []
    for e in timeline.entries:
        ed = date.fromisoformat(e.effective_date)
        if ed >= rd:
            bal += e.net_cash_flow
            entries.append({
                'date': e.effective_date,
                'date_obj': ed,
                'cf': e.net_cash_flow,
                'balance': bal,
                'desc': e.event.description[:50],
            })
    
    # Show first entries to request_date + 5 days
    print(f"\n  Timeline entries [request_date, request_date+5days]:")
    for en in entries:
        if en['date_obj'] <= rd + timedelta(days=5):
            print(f"    {en['date']}  cf={en['cf']:>12}  bal={en['balance']:>12}  {en['desc']}")
    
    # Show entries around deadline
    print(f"\n  Timeline entries around deadline {dl}:")
    for en in entries:
        if dl_date - timedelta(days=3) <= en['date_obj'] <= dl_date + timedelta(days=3):
            safe_here = max(ZERO, en['balance'] - minimum)
            match = abs(safe_here - exp_amount) < Decimal('0.05')
            print(f"    {en['date']}  cf={en['cf']:>12}  bal={en['balance']:>12}  safe_here={safe_here}{'  <-- MATCH' if match else ''}")
    
    # Try: Simulate paying exp_amount on each date before deadline
    # and find which date/scenario gives feasible=True
    print(f"\n  Searching: which payment date makes pay=exp_amount feasible?")
    for test_date in [request_date, dl]:
        sim = simulate_payment_plan(timeline, [(test_date, exp_amount)], requested_amount=None)
        min_seen = sim.minimum_balance_seen
        viols = [v for v in sim.violations if 'total' not in v]
        print(f"  pay={exp_amount} on {test_date}: feasible={sim.feasible} min_seen={min_seen} violations={viols[:2]}")
    
    # Special check: what is 597.74 for request_14?
    # opening=3931.74, min=2200
    # 3931.74 - 597.74 = 3334 ... rent? 
    # 1134 = opening - exp - min ... what event costs 1134?
    print(f"\n  Reverse-engineering remainder={opening - exp_amount - minimum}:")
    remainder = opening - exp_amount - minimum
    # Check all events with amounts near remainder
    for en in entries:
        if abs(abs(en['cf']) - abs(remainder)) < Decimal('0.02'):
            print(f"  -> EXACT cash flow match: {en['date']} {en['cf']} {en['desc']}")
    
    # Check profile events (raw)
    user_events = [e for e in index.events if e['user_id'] == uid]
    print(f"\n  Raw events for {uid} at/around request_date:")
    for ev in sorted(user_events, key=lambda e: e['event_date']):
        evd = date.fromisoformat(ev['event_date'])
        if rd - timedelta(days=5) <= evd <= rd + timedelta(days=5):
            print(f"    {ev['event_id']} {ev['event_date']} {ev['status']:<10} {ev.get('amount',''):>12} {ev['currency']} {ev['description'][:50]}")
    
    # Check if there are any pending events on request_date
    pending_on_rd = [e for e in user_events
                     if e['status'] in ('pending', 'scheduled')
                     and date.fromisoformat(e['settlement_date'] or e['event_date']) >= rd]
    print(f"\n  Pending/scheduled events >= request_date:")
    for ev in sorted(pending_on_rd, key=lambda e: e.get('settlement_date') or e['event_date']):
        sd = ev.get('settlement_date') or ev['event_date']
        sd_d = date.fromisoformat(sd)
        if sd_d <= rd + timedelta(days=30):
            print(f"    {ev['event_id']} {sd} {ev['status']:<10} {ev.get('amount',''):>12} {ev['currency']} {ev['description'][:50]}")
    
    # CRITICAL: Check what the CandidateEngine actually produces
    decision = engine.decide(req)
    selected = decision.selected
    print(f"\n  CandidateEngine decision:")
    print(f"    status={decision.affordability_status} method={selected.payment_method}")
    print(f"    amount_safe={selected.amount_safe_to_pay}")
    print(f"    baseline_safe={decision.baseline_safe}")
    print(f"    earliest_full={selected.earliest_date_for_full_payment}")
    print(f"    spending_changes={selected.spending_changes_needed}")

for rid in ['request_05', 'request_14', 'request_15']:
    reverse_engineer(rid)
