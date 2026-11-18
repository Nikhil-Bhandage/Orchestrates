import json

d = json.load(open("dataset/evidence/records/service_resource_export_20260915_114455.json"))
for item in d["service_exports"]["analytics_platform"]["profiles"]:
    has_email = bool(item.get("email"))
    has_ref = bool(item.get("customer_reference"))
    has_hash = bool(item.get("email_hash"))
    has_phone = bool(item.get("phone"))
    cohort = item.get("audience_cohort", "")
    rid = item.get("resource_id", "")
    pii = "HAS_PII" if (has_email or has_ref or has_hash or has_phone) else "NO_PII"
    print(f"{rid}: {pii} email={item.get('email')} ref={item.get('customer_reference')} cohort={cohort}")
