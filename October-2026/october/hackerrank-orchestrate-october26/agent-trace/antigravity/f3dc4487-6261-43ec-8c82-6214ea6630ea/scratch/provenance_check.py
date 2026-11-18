import csv
import json

sample_reqs = list(csv.DictReader(open('dataset/sample_deletion_requests.csv', encoding='utf-8')))
sample_outs = {r['case_id']: json.loads(r['steps_json']) for r in csv.DictReader(open('dataset/sample_output.csv', encoding='utf-8'))}

# Check for each sample case: where do its expected resources appear in evidence and system_activity?
activities = list(csv.DictReader(open('dataset/system_activity.csv', encoding='utf-8')))

for req in sample_reqs[:10]:
    cid = req['case_id']
    steps = sample_outs.get(cid, [])
    print(f"Case {cid} ({req['email']}):")
    for s in steps:
        res_id = s['resource_id']
        ev_id = s['evidence_id']
        # search in system activity
        acts = [a for a in activities if a['resource_id'] == res_id]
        act_summary = [f"{a['activity_id']}:{a['event_type']}:{a['details']}" for a in acts]
        print(f"  Step res={res_id} op={s['operation']} ev={ev_id} | acts={len(acts)}: {act_summary[:2]}")
