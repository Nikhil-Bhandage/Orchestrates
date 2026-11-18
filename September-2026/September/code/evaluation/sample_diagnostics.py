import sys, csv, json
from pathlib import Path
from decimal import Decimal
from collections import defaultdict, Counter
sys.path.insert(0, str(Path(__file__).parents[1]))
from data_layer import DatasetIndex
from canonical_events import normalize_dataset
from financial_timeline import build_user_timeline, get_max_safe_one_time_payment
from evidence_resolution import EvidenceResolver, apply_evidence_to_timeline

ROOT = Path(__file__).parents[2]
index = DatasetIndex.from_dataset(ROOT / "dataset")
store = normalize_dataset(index)
profiles = index.profiles_by_user
evidence_resolver = EvidenceResolver(index, store)
samples = list(csv.DictReader((ROOT / "dataset/sample_requests.csv").open(encoding="utf-8-sig")))


def dec(value):
    return Decimal(str(value))


def suspected_causes(sample, future, messages, images, calculated):
    result = []
    if any(any(term in m["message_text"].lower() for term in ("salary", "payroll", "income")) for m in messages):
        result.append("message_payroll_or_income_evidence_not_in_canonical_timeline")
    if any(entry.projection_kind == "essential_variable" for entry in future):
        result.append("protected_category_variable_forecast")
    if any(
        entry.projection_kind == "exact"
        and entry.event.category in {"rent", "utilities", "insurance", "education", "healthcare", "family_support", "debt_repayment"}
        for entry in future
    ):
        result.append("recurring_obligation_projection")
    if images:
        result.append("image_evidence_relevance_check")
    expected = dec(sample["amount_safe_to_pay"])
    if calculated < expected:
        result.append("current_timeline_is_more_conservative_than_sample")
    elif calculated > expected:
        result.append("current_timeline_has_less_future_pressure_than_sample")
    return result or ["no_obvious_evidence_cause"]


report = []
for sample in samples:
    user = sample["user_id"]
    request_id = sample["request_id"]
    request_date = sample["request_date"]
    timeline = build_user_timeline(
        user,
        store.by_user[user],
        profiles[user],
        [request_date],
        exchange_rates=index.exchange_rates_by_key,
    )
    raw_result = get_max_safe_one_time_payment(timeline, request_date, sample["requested_amount"])
    context = evidence_resolver.context_for_request(sample)
    adjusted_timeline = apply_evidence_to_timeline(
        timeline, context, index.exchange_rates_by_key
    )
    result = get_max_safe_one_time_payment(adjusted_timeline, request_date, sample["requested_amount"])
    left = adjusted_timeline.start_index(request_date)
    right = adjusted_timeline.end_index(request_date)
    future = list(adjusted_timeline.entries[left:right])
    messages = list(context.messages)
    images = list(context.images)
    incomes = [
        {
            "date": entry.effective_date,
            "event_id": entry.event_id,
            "category": entry.event.category,
            "description": entry.event.description,
            "amount": str(entry.event.amount),
            "currency": entry.event.currency,
            "projected": entry.projected,
            "kind": entry.projection_kind,
        }
        for entry in future if entry.net_cash_flow > 0
    ]
    expense_totals = defaultdict(Decimal)
    expense_rows = []
    for entry in future:
        if entry.net_cash_flow < 0:
            amount = -entry.net_cash_flow
            expense_totals[entry.event.category] += amount
            expense_rows.append({
                "date": entry.effective_date,
                "event_id": entry.event_id,
                "category": entry.event.category,
                "description": entry.event.description,
                "amount": str(amount),
                "projected": entry.projected,
                "kind": entry.projection_kind,
            })
    if result.natural_path_feasible and result.max_safe_payment >= dec(sample["requested_amount"]):
        implied_status = "affordable_now"
    elif result.max_safe_payment > 0:
        implied_status = "capacity_below_request"
    else:
        implied_status = "no_safe_capacity"
    report.append({
        "request_id": request_id,
        "user_id": user,
        "request_date": request_date,
        "requested_amount": sample["requested_amount"],
        "expected": {
            "amount_safe_to_pay": sample["amount_safe_to_pay"],
            "status": sample["affordability_status"],
            "method": sample["recommended_payment_method"],
            "earliest_date": sample["earliest_date_for_full_payment"],
        },
        "current": {
            "amount_safe_to_pay": str(result.max_safe_payment),
            "natural_path_feasible": result.natural_path_feasible,
            "implied_status": implied_status,
            "minimum_before": str(result.minimum_natural_balance_before_payment),
            "minimum_after": str(result.minimum_natural_balance_after_payment),
            "first_violation_date": result.first_violation_date,
            "raw_amount_before_evidence": str(raw_result.max_safe_payment),
        },
        "evidence_resolution": {
            "facts": [
                {
                    "fact_type": fact.fact_type,
                    "value": fact.value,
                    "currency": fact.currency,
                    "effective_date": fact.effective_date,
                    "source_ids": fact.source_ids,
                }
                for fact in context.resolved_facts
            ],
            "conflicts": [
                {
                    "fact_type": conflict.fact_type,
                    "candidate_count": len(conflict.candidates),
                    "selected_source_ids": conflict.selected.source_ids if conflict.selected else (),
                    "reason": conflict.reason,
                }
                for conflict in context.conflicts
            ],
            "image_event_ids": sorted(context.image_evidence),
        },
        "profile": {
            "home_currency": profiles[user]["home_currency"],
            "starting_balance": profiles[user]["current_available_balance"],
            "minimum_balance": profiles[user]["minimum_balance_to_keep"],
            "protected": profiles[user]["expense_categories_to_protect"],
            "reduce": profiles[user]["expense_categories_user_is_willing_to_reduce"],
            "stop": profiles[user]["expense_categories_user_is_willing_to_stop"],
            "payment_methods": profiles[user]["payment_methods_user_will_consider"],
        },
        "relevant_income": incomes,
        "relevant_expense_totals": {key: str(value) for key, value in sorted(expense_totals.items())},
        "relevant_expenses": expense_rows,
        "messages": [
            {
                "message_id": message["message_id"],
                "request_id": message["request_id"],
                "related_event_id": message["related_event_id"],
                "source_type": message["source_type"],
                "text": message["message_text"],
            }
            for message in messages
        ],
        "images": [
            {
                "image_id": image["image_id"],
                "request_id": image["request_id"],
                "related_event_id": image["related_event_id"],
            }
            for image in images
        ],
        "payment_options": index.options_by_request.get(request_id, []),
        "timeline_difference": {
            "future_entry_count": len(future),
            "projection_kinds": dict(Counter(entry.projection_kind for entry in future)),
            "natural_net": str(sum((entry.net_cash_flow for entry in future), Decimal(0))),
            "expected_minus_current": str(dec(sample["amount_safe_to_pay"]) - result.max_safe_payment),
            "expected_minus_raw_current": str(dec(sample["amount_safe_to_pay"]) - raw_result.max_safe_payment),
        },
        "suspected_causes": suspected_causes(sample, future, messages, images, result.max_safe_payment),
    })

output = Path(__file__).with_name("sample_diagnostic.json")
output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print("wrote", output, "rows=", len(report))
for item in report:
    if (
        Decimal(item["current"]["amount_safe_to_pay"]) != Decimal(item["expected"]["amount_safe_to_pay"])
        or item["current"]["implied_status"] != item["expected"]["status"]
    ):
        print(
            item["request_id"],
            "expected=", item["expected"]["amount_safe_to_pay"], item["expected"]["status"],
            "current=", item["current"]["amount_safe_to_pay"], item["current"]["implied_status"],
            "causes=", ",".join(item["suspected_causes"]),
        )
