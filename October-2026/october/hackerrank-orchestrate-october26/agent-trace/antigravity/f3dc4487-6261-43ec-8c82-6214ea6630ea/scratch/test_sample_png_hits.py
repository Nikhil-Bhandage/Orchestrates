import csv
import json
from pathlib import Path
import sys

sys.path.insert(0, "code")
from data_loader import load_all_datasets
from evidence_indexer import get_evidence_index
from evidence_agent import _reinspect_png_hits, GeminiUsage, resolve_identity, get_historical_identifiers

bundle = load_all_datasets("dataset")
index = get_evidence_index("dataset")

usage = GeminiUsage()
print("Checking PNG matches across all 32 sample requests:")
for req in bundle.sample_requests:
    audit_at = req.audit_at
    all_identifiers = {req.email.lower()}
    res = resolve_identity(req.email, bundle)
    if res:
        all_identifiers.add(res.user_id.lower())
        hist = get_historical_identifiers(res.user_id, as_of=audit_at, bundle=bundle)
        all_identifiers.update(e.lower() for e in hist.emails)
        all_identifiers.update(p for p in hist.phones if p)
        all_identifiers.update(eh.lower() for eh in hist.email_hashes if eh)
    
    hits = _reinspect_png_hits(index, all_identifiers, audit_at, usage)
    if hits:
        print(f"Case {req.case_id} ({req.email}): {len(hits)} hits:")
        for h in hits:
            print(f"  file={h.file_id} sys={h.system_id} res={h.resource_id} ident={h.matched_identifier} state={h.parsed_state}")
