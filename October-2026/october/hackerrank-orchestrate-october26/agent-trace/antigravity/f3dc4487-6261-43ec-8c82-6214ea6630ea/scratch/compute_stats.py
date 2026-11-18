import csv, json, pathlib

output_path = pathlib.Path(r"g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/output.csv")
rows = 0
status_counts = {}
steps_parsed = 0
with output_path.open(newline='') as f:
    reader = csv.DictReader(f)
    for r in reader:
        rows += 1
        st = r['deletion_status']
        status_counts[st] = status_counts.get(st, 0) + 1
        try:
            json.loads(r['steps_json'])
            steps_parsed += 1
        except Exception:
            pass
print('TOTAL_ROWS', rows)
print('STATUS_COUNTS', status_counts)
print('STEPS_PARSED', steps_parsed)
