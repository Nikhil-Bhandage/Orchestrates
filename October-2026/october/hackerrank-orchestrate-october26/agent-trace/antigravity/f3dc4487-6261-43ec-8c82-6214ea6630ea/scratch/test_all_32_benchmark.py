import sys
import re
sys.path.insert(0, 'code')
import evidence_agent
import evidence_indexer

evidence_agent.CATEGORY_SYSTEM_MAP["ACCOUNT_TOMBSTONE"] = "identity_service"
evidence_agent.CATEGORY_SYSTEM_MAP["INTEGRATION_DATA_FLOW"] = "integration_service"
evidence_agent.CATEGORY_ACTION_MAP["INTEGRATION_DATA_FLOW"] = "DISABLE"
evidence_agent.RESOURCE_PREFIX_TO_CATEGORY["data_flow_"] = "INTEGRATION_DATA_FLOW"

old_agent_infer = evidence_agent._infer_system_id
def patched_infer(source_or_target, resource_id=""):
    rid = (resource_id or "").lower()
    if rid.startswith("tombstone_"):
        return "identity_service"
    if rid.startswith("data_flow_"):
        return "integration_service"
    return old_agent_infer(source_or_target, resource_id)

evidence_agent._infer_system_id = patched_infer
evidence_indexer._infer_system_id = patched_infer

# Patch parse_pdf_evidence
old_parse_pdf = evidence_indexer.parse_pdf_evidence
def patched_parse_pdf(file_meta, abs_path):
    hits = old_parse_pdf(file_meta, abs_path)
    for h in hits:
        if h.identifier_type == "user_id" and h.resource_id == h.matched_identifier:
            h.resource_id = ""
    return hits
evidence_indexer.parse_pdf_evidence = patched_parse_pdf

# Patch parse_log_evidence to extract sha256 hashes
old_parse_log = evidence_indexer.parse_log_evidence
def patched_parse_log(file_meta, content):
    hits = old_parse_log(file_meta, content)
    for line in content.splitlines():
        for h in evidence_indexer.RE_HASH.findall(line):
            res_match = re.search(r'\bresource_id=["\']?([a-zA-Z0-9_]+)["\']?', line)
            res_id = res_match.group(1) if res_match else ""
            srv_match = re.search(r'\b(?:service|function|system)=["\']?([a-zA-Z0-9_]+)["\']?', line)
            srv_name = srv_match.group(1) if srv_match else ""
            system_id = evidence_indexer._infer_system_id(srv_name or file_meta.origin, res_id)
            state = "PRESENT" if "200" in line or "rows=1" in line else "UNKNOWN"
            hits.append(evidence_indexer.EvidenceHit(
                file_id=file_meta.file_id,
                file_path=file_meta.file_path,
                origin=file_meta.origin,
                captured_at=file_meta.captured_at,
                system_id=system_id,
                resource_id=res_id,
                matched_identifier=h.lower(),
                identifier_type="email_hash",
                snippet=line[:200],
                full_record={"log_line": line[:300]},
                parsed_state=state,
            ))
    return hits
evidence_indexer.parse_log_evidence = patched_parse_log

# Rebuild index
from evidence_indexer import get_evidence_index
index = get_evidence_index("dataset")
index.build_index(force_reindex=True)

from main import evaluate_sample_benchmark
report = evaluate_sample_benchmark()
for c in report['case_details']:
    if not c['status_match']:
        print('Mismatch:', c)
