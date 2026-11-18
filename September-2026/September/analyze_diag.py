import json, csv

with open('tmp_sample_diagnostic.json', encoding='utf-8') as f:
    diag = json.load(f)

requests = diag.get('requests', [])
by_id = {r['request_id']: r for r in requests}

# Load expected
expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

# load our output
our_output = {}
with open('tmp_sample_output.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        our_output[row['request_id']] = row

# Focus on specific requests with major issues
focus_ids = ['request_01', 'request_07', 'request_08', 'request_09', 
             'request_10', 'request_13', 'request_23', 'request_06', 
             'request_11', 'request_21']

for rid in focus_ids:
    d = by_id.get(rid, {})
    exp = expected.get(rid, {})
    our = our_output.get(rid, {})
    print(f'\n=== {rid} ===')
    print(f'  EXP status: {exp.get("affordability_status","")}  method: {exp.get("recommended_payment_method","")}')
    print(f'  OUR status: {d.get("affordability_status","")}  method: {d.get("selected_method","")}')
    print(f'  EXP amount_safe: {exp.get("amount_safe_to_pay","")}')
    print(f'  OUR amount_safe: {d.get("amount_safe_to_pay","")}')
    print(f'  OUR min_balance_seen: {d.get("minimum_balance_seen","")}')
    print(f'  OUR feasible_candidates: {d.get("feasible_candidate_count",0)}')
    print(f'  OUR reason_codes: {d.get("reason_codes",[])}')
    print(f'  EXP earliest: {exp.get("earliest_date_for_full_payment","")}')
    print(f'  OUR earliest: {our.get("earliest_date_for_full_payment","")}')
    print(f'  EXP spending: {exp.get("spending_changes_needed","")}')
    print(f'  OUR spending: {our.get("spending_changes_needed","")}')
