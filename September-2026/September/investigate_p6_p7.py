"""
P6 investigation: request_11 - why event_948 is selected instead of event_989.
P7 investigation: request_19 - why installments wins over partial_payment.
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
    simulate_payment_plan, get_max_safe_one_time_payment, ZERO, _detect_patterns, _pattern_signature
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

print("="*70)
print("P6: request_11 — spending change targets event_948 vs expected event_989")
print("="*70)

req11 = index.requests_by_id['request_11']
uid11 = 'user_11'
exp11 = expected['request_11']

ctx11 = engine.evidence.context_for_request(req11)
tl11 = apply_evidence_to_timeline(engine.catalog.get(uid11), ctx11, index.exchange_rates_by_key)

print(f"\nrequest_11: uid={uid11}")
print(f"Expected spending_changes: {exp11['spending_changes_needed']}")
print(f"Expected status: {exp11['affordability_status']}, method: {exp11['recommended_payment_method']}")
print(f"Expected amount_safe: {exp11['amount_safe_to_pay']}")
print(f"request_date: {req11['request_date']}  deadline: {req11['desired_completion_date']}")

# What is event_989?
ev989 = store.by_id.get('event_989')
print(f"\nevent_989:")
print(f"  user={ev989.user_id} cat={ev989.category} type={ev989.event_type}")
print(f"  flex={ev989.flexibility} status={ev989.status}")
print(f"  date={ev989.event_date} effective={ev989.effective_date}")
print(f"  amount={ev989.amount} min_allowed={ev989.minimum_allowed_amount}")
print(f"  desc={ev989.description}")
print(f"  forecast_eligible={ev989.forecast_eligible} cash_effect={ev989.forecast_cash_effect}")

# What is event_948?
ev948 = store.by_id.get('event_948')
print(f"\nevent_948:")
print(f"  user={ev948.user_id} cat={ev948.category} type={ev948.event_type}")
print(f"  flex={ev948.flexibility} status={ev948.status}")
print(f"  date={ev948.event_date} effective={ev948.effective_date}")
print(f"  amount={ev948.amount} min_allowed={ev948.minimum_allowed_amount}")
print(f"  desc={ev948.description}")
print(f"  forecast_eligible={ev948.forecast_eligible} cash_effect={ev948.forecast_cash_effect}")

# What is the change_index for dining?
print(f"\nchange_index contents (first 20 keys):")
for k in list(tl11.change_index.keys())[:20]:
    idxs = tl11.change_index[k]
    dates = [tl11.entries[i].effective_date for i in idxs[:3]]
    print(f"  {k} -> entry indices {idxs[:3]}, dates {dates}")

# The _change_sets logic: groups entries by their index tuple
# then picks max(targets, key=lambda t: (entries[indexes[0]].effective_date, t))
# i.e., picks the target with the LATEST first projected occurrence, breaking ties by event_id

print(f"\n_change_sets() analysis for dining entries:")
from collections import defaultdict
grouped = {}
for target, indexes in tl11.change_index.items():
    key = tuple(indexes)
    grouped.setdefault(key, []).append(target)

print(f"  Number of distinct index groups: {len(grouped)}")
for idxs_tuple, targets in sorted(grouped.items()):
    first_idx = idxs_tuple[0]
    entry = tl11.entries[first_idx]
    # Pick winner by (date, event_id) max
    winner = max(targets, key=lambda t: (tl11.entries[idxs_tuple[0]].effective_date, t))
    print(f"  group idxs={idxs_tuple[:3]} first_date={entry.effective_date} cat={entry.event.category}")
    print(f"    targets={targets}")
    print(f"    winner={winner}")

# Show all dining events for user_11
print(f"\nAll dining events for user_11 (from canonical store):")
events11 = store.by_user.get(uid11, [])
dining = sorted([e for e in events11 if e.category == 'dining'], key=lambda e: e.effective_date)
for e in dining:
    print(f"  {e.event_id} {e.effective_date} {e.status:<10} {e.amount:>15} {e.currency} flex={e.flexibility} min_allowed={e.minimum_allowed_amount} {e.description}")

print(f"\nKey question: why does the change_index have event_948 but benchmark expects event_989?")
print(f"  event_989: date={ev989.event_date} (latest settled dining event before request_date)")
print(f"  event_948: date={ev948.event_date}")
print(f"  Both are dining/reducible events. The change_index is built from PROJECTED entries.")
print(f"  Projected entries carry change_event_ids = tuple of ALL source settled events.")
print(f"  The winner is picked as max by (first_projected_date, event_id).")
print()

# Show actual projected dining entries
print("Projected dining timeline entries (change_event_ids):")
for e in tl11.entries:
    if e.projected and e.event.category == 'dining':
        print(f"  {e.effective_date} cf={e.net_cash_flow:>14} change_ids={e.change_event_ids}")
        break  # just first one

# Show what changeset is generated
changesets = engine._change_sets(tl11)
dining_changes = [cs for cs in changesets if any('event_948' in c or 'event_949' in c or 'event_989' in c for c in cs)]
print(f"\nGenerated changesets involving dining/cloud_storage:")
for cs in changesets:
    if cs:  # skip empty
        print(f"  {cs}")

print()
print("="*70)
print("P7: request_19 — why installments beats partial_payment")
print("="*70)

req19 = index.requests_by_id['request_19']
uid19 = 'user_19'
exp19 = expected['request_19']

ctx19 = engine.evidence.context_for_request(req19)
tl19 = apply_evidence_to_timeline(engine.catalog.get(uid19), ctx19, index.exchange_rates_by_key)

requested19 = Decimal(req19['requested_amount'])
rd19 = req19['request_date']
dl19 = req19['desired_completion_date']

print(f"\nrequest_19: uid={uid19}")
print(f"Expected: method={exp19['recommended_payment_method']} status={exp19['affordability_status']}")
print(f"Expected payment_plan: {exp19['payment_plan']}")
print(f"Expected amount_safe: {exp19['amount_safe_to_pay']}")
print(f"Expected earliest: {exp19['earliest_date_for_full_payment']}")
print(f"requested={requested19} request_date={rd19} deadline={dl19}")
print(f"allows_partial_payment={req19['allows_partial_payment']}")
print(f"policy payment_methods={tl19.policy.payment_methods}")
print(f"policy max_installment_months={tl19.policy.max_installment_months}")

# Get all payment options for request_19
opts19 = index.options_by_request.get('request_19', [])
print(f"\nPayment options for request_19:")
for opt in opts19:
    print(f"  option_id={opt['payment_option_id']} method={opt['payment_method']}")
    print(f"    first={opt['first_payment_date']} freq={opt['payment_frequency_days']}d count={opt['number_of_payments']}")
    print(f"    amount_per={opt['payment_amount']} total={opt['total_payable_amount']}")

# Run the full decision and show all feasible candidates
decision19 = engine.decide(req19)
print(f"\nCandidateEngine decision:")
print(f"  selected: method={decision19.selected.payment_method}")
print(f"    amount_safe={decision19.selected.amount_safe_to_pay}")
print(f"    schedule={decision19.selected.payment_schedule}")
print(f"    spending_changes={decision19.selected.spending_changes}")
print(f"    total_cost={decision19.selected.total_payment_cost}")
print(f"    ranking_key={engine._ranking_key(decision19.selected)}")
print(f"  rejections: {decision19.rejection_counts}")

print(f"\n  All feasible candidates ({len(decision19.feasible_candidates)} total):")
for i, c in enumerate(decision19.feasible_candidates):
    key = engine._ranking_key(c)
    print(f"  [{i}] method={c.payment_method} amount_safe={c.amount_safe_to_pay}")
    print(f"      schedule={c.payment_schedule}")
    print(f"      total_cost={c.total_payment_cost} spending={c.spending_changes}")
    print(f"      ranking_key={key}")

# Now check partial_payment specifically
# Is allows_partial_payment=True?
print(f"\npartial_payment eligibility check:")
print(f"  allows_partial_payment in request: {req19['allows_partial_payment']}")
print(f"  partial_payment in policy: {'partial_payment' in tl19.policy.payment_methods}")

# Run _partial_candidate manually with no changes
partial_cand = engine._partial_candidate(tl19, req19, ())
print(f"\n_partial_candidate(no changes) result: {partial_cand}")

if partial_cand is None:
    print("  -> Returns None! Investigating why...")
    print(f"  allows_partial_payment={req19['allows_partial_payment']}")
    print(f"  partial_payment in policy={('partial_payment' in tl19.policy.payment_methods)}")
    
    # Try each second_date
    print(f"\n  Payment dates tried:")
    payment_dates = engine._payment_dates(tl19, req19)
    print(f"  Total dates: {len(payment_dates)}")
    
    # Check first amount for key dates
    for sd in payment_dates[:15]:
        if sd <= rd19 or sd > dl19:
            continue
        first_amt = engine._maximum_first_payment(tl19, rd19, sd, requested19, ())
        if first_amt > ZERO:
            print(f"  second_date={sd}: first_amount={first_amt} (requested={requested19})")
            if first_amt < requested19:
                # Try the simulation
                remainder = requested19 - first_amt
                sim = simulate_payment_plan(tl19, [(rd19, first_amt), (sd, remainder)], requested_amount=requested19)
                hard_rej = engine._hard_rejection(CandidatePlan := None, tl19, req19) if False else ""
                print(f"    sim feasible={sim.feasible} min_seen={sim.minimum_balance_seen}")
                if sim.violations:
                    print(f"    violations={sim.violations[:3]}")

# Check zero_first simulation
print(f"\n  simulate zero_first for each second_date (first few):")
for sd in list(payment_dates)[:10]:
    if sd <= rd19 or sd > dl19:
        continue
    zero_sim = simulate_payment_plan(tl19, [(rd19, ZERO), (sd, requested19)], requested_amount=requested19)
    print(f"  second={sd}: zero_first feasible={zero_sim.feasible} min={zero_sim.minimum_balance_seen}")
    if not zero_sim.feasible:
        print(f"    violations={zero_sim.violations[:2]}")

# Now trace the expected partial plan from benchmark
exp_plan = exp19['payment_plan']
print(f"\nExpected payment plan: {exp_plan}")
# Parse: "2024-07-15:28820|2024-09-15:10840"
parts = exp_plan.split('|')
schedule_exp = []
for part in parts:
    d, a = part.split(':')
    schedule_exp.append((d, Decimal(a)))
print(f"Parsed: {schedule_exp}")
sim_exp_plan = simulate_payment_plan(tl19, schedule_exp, requested_amount=requested19)
print(f"Simulation of expected plan: feasible={sim_exp_plan.feasible} min_seen={sim_exp_plan.minimum_balance_seen}")
if sim_exp_plan.violations:
    print(f"violations={sim_exp_plan.violations}")
rej_exp = ""
if schedule_exp[0][0] != rd19:
    rej_exp = "first payment date mismatch"
elif schedule_exp[1][0] > dl19:
    rej_exp = "deadline missed"
print(f"Hard rejection check: first={schedule_exp[0][0]} vs request_date={rd19}, second={schedule_exp[1][0]} vs deadline={dl19}")
