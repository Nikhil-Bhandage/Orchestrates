import csv

# Load expected (from sample_requests.csv)
expected = {}
with open('dataset/sample_requests.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        expected[row['request_id']] = row

# Load our output
our_output = {}
with open('tmp_sample_output.csv', newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        our_output[row['request_id']] = row

# Compare field by field
fields = ['amount_safe_to_pay','affordability_status','recommended_payment_method','payment_plan','earliest_date_for_full_payment','spending_changes_needed']

print('=== FIELD-BY-FIELD COMPARISON ===')
exact_match = []
mismatches = {}
for rid in sorted(expected.keys()):
    exp = expected[rid]
    our = our_output.get(rid, {})
    row_mismatches = []
    for field in fields:
        ev = exp.get(field,'').strip()
        ov = our.get(field,'').strip()
        if ev != ov:
            row_mismatches.append((field, ev, ov))
    if row_mismatches:
        mismatches[rid] = row_mismatches
        print(f'\n--- {rid} (user={exp["user_id"]}, type={exp["request_type"]}, amt={exp["requested_amount"]}, date={exp["request_date"]}) ---')
        for field, ev, ov in row_mismatches:
            print(f'  {field}:')
            print(f'    EXP: {ev!r}')
            print(f'    OUR: {ov!r}')
    else:
        exact_match.append(rid)

print(f'\n=== SUMMARY ===')
print(f'Exact matches: {len(exact_match)}/25: {exact_match}')
print(f'Mismatches: {len(mismatches)}/25')

# Per-field accuracy
for field in fields:
    matches = sum(1 for rid in expected if expected[rid].get(field,'').strip() == our_output.get(rid,{}).get(field,'').strip())
    print(f'  {field}: {matches}/25')
