import sys
sys.path.insert(0, 'code')
import evidence_agent

# Let's fix the mappings in memory and test
evidence_agent.CATEGORY_SYSTEM_MAP["ACCOUNT_TOMBSTONE"] = "identity_service"
evidence_agent.CATEGORY_SYSTEM_MAP["INTEGRATION_DATA_FLOW"] = "integration_service"
evidence_agent.CATEGORY_ACTION_MAP["INTEGRATION_DATA_FLOW"] = "DISABLE"
evidence_agent.RESOURCE_PREFIX_TO_CATEGORY["data_flow_"] = "INTEGRATION_DATA_FLOW"

# Also in _infer_system_id
old_infer = evidence_agent._infer_system_id
def patched_infer(source_or_target, resource_id=""):
    rid = (resource_id or "").lower()
    if rid.startswith("tombstone_"):
        return "identity_service"
    if rid.startswith("data_flow_"):
        return "integration_service"
    return old_infer(source_or_target, resource_id)
evidence_agent._infer_system_id = patched_infer

from workflow import audit_single_case

for cid in ['case_21', 'case_26', 'case_27', 'case_28', 'case_31']:
    st = audit_single_case(cid)
    print(f"{cid}: status={st['deletion_status']}, steps={len(st['steps'])}")
    for s in st['steps']:
        print(f"  {s['phase']} {s['system_id']} {s['resource_id']} {s['operation']} {s['state']} ev={s['evidence_id']}")
