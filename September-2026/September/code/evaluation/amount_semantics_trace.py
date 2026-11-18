"""Trace public amount_safe_to_pay semantics through state and selected plans."""
from __future__ import annotations
import csv, json, sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from candidate_plans import CandidateEngine
from canonical_events import normalize_dataset
from data_layer import DatasetIndex
from evidence_resolution import apply_evidence_to_timeline
from financial_timeline import build_user_timeline, get_max_safe_one_time_payment

ROOT = Path(__file__).parents[2]
index = DatasetIndex.from_dataset(ROOT / "dataset")
store = normalize_dataset(index)
engine = CandidateEngine(index, store)
with (ROOT / "dataset/sample_requests.csv").open(encoding="utf-8-sig") as handle:
    samples = list(csv.DictReader(handle))

def dec(x): return Decimal(str(x))
def parse_plan(text):
    if not text or text == "none": return []
    return [(part.split(":", 1)[0], Decimal(part.split(":", 1)[1])) for part in text.split("|")]

def selected_plan_text(c):
    return "|".join(f"{d}:{a}" for d,a in c.payment_schedule) or "none"

rows=[]
for sample in samples:
    user=sample["user_id"]
    context=engine.evidence.context_for_request(sample)
    if user in engine.catalog.by_user:
        base=engine.catalog.get(user)
    else:
        base=build_user_timeline(user,store.by_user[user],index.profiles_by_user[user],[sample["request_date"]],exchange_rates=index.exchange_rates_by_key)
    timeline=apply_evidence_to_timeline(base,context,index.exchange_rates_by_key)
    raw=get_max_safe_one_time_payment(timeline,sample["request_date"],sample["requested_amount"])
    decision=engine.decide(sample)
    selected=decision.selected
    benchmark_schedule=parse_plan(sample["payment_plan"])
    benchmark_first=benchmark_schedule[0][1] if benchmark_schedule else Decimal("0")
    benchmark_total=sum((amount for _,amount in benchmark_schedule),Decimal("0"))
    same_day_balance=timeline.policy.starting_balance
    start=timeline.start_index(sample["request_date"])
    after=timeline.after_date_index(sample["request_date"])
    for i in range(start,after): same_day_balance += timeline.entries[i].net_cash_flow
    row={
        "request_id":sample["request_id"],
        "request_type":sample["request_type"],
        "requested_amount":sample["requested_amount"],
        "expected_method":sample["recommended_payment_method"],
        "selected_method":selected.payment_method,
        "expected_status":sample["affordability_status"],
        "selected_status":decision.affordability_status,
        "expected_amount":sample["amount_safe_to_pay"],
        "selected_amount":str(selected.amount_safe_to_pay),
        "baseline_safe":str(decision.baseline_safe_amount),
        "raw_natural_feasible":raw.natural_path_feasible,
        "raw_min_after":str(raw.minimum_natural_balance_after_payment),
        "raw_first_violation":raw.first_violation_date,
        "starting_balance":str(timeline.policy.starting_balance),
        "minimum_balance":str(timeline.policy.minimum_balance),
        "same_day_balance_before_request_payment":str(same_day_balance),
        "headroom_before_request_payment":str(same_day_balance-timeline.policy.minimum_balance),
        "expected_plan":sample["payment_plan"],
        "expected_plan_first_amount":str(benchmark_first),
        "expected_plan_total":str(benchmark_total),
        "expected_plan_last_date":benchmark_schedule[-1][0] if benchmark_schedule else "",
        "selected_plan":selected_plan_text(selected),
        "selected_plan_first_amount":str(selected.payment_schedule[0][1]) if selected.payment_schedule else "",
        "selected_plan_total":str(selected.total_payment),
        "selected_plan_last_date":selected.completion_date,
        "selected_changes":"|".join(selected.spending_changes) or "none",
        "selected_feasible":selected.simulation_result.feasible if selected.simulation_result else False,
        "selected_minimum_seen":str(selected.simulation_result.minimum_balance_seen) if selected.simulation_result else "",
        "evidence_facts":[f.fact_type for f in context.resolved_facts],
        "foreign_event_present":any(e.event.currency != timeline.policy.home_currency for e in timeline.entries),
    }
    # Deterministic preliminary classification. This is deliberately based on
    # trace evidence and is reviewed in the generated markdown, not used by
    # prediction code.
    expected_amount=dec(sample["amount_safe_to_pay"])
    if expected_amount == benchmark_first and sample["recommended_payment_method"] == "partial_payment":
        category="selected_partial_first_payment_semantics"
    elif expected_amount == dec(sample["requested_amount"]) and sample["recommended_payment_method"] == "full_payment":
        category="full_payment_amount_equals_request"
    elif sample["recommended_payment_method"] in {"installments","wait"} or sample["recommended_payment_method"] == "not_recommended":
        category="immediate_safe_capacity_semantics_or_state_mismatch"
    elif sample["recommended_payment_method"] == "full_payment" and expected_amount < dec(sample["requested_amount"]):
        category="safe_capacity_before_spending_changes_or_state_mismatch"
    else:
        category="other"
    row["preliminary_category"]=category
    rows.append(row)

summary={
    "rows":rows,
    "category_counts":dict(Counter(row["preliminary_category"] for row in rows)),
    "expected_amount_equals_plan_first":sum(dec(row["expected_amount"])==dec(row["expected_plan_first_amount"]) for row in rows),
    "expected_amount_equals_requested":sum(dec(row["expected_amount"])==dec(row["requested_amount"]) for row in rows),
    "expected_amount_equals_selected_first":sum(row["expected_amount"]==row["selected_plan_first_amount"] for row in rows),
    "expected_amount_equals_baseline":sum(dec(row["expected_amount"])==dec(row["baseline_safe"]) for row in rows),
}
Path(__file__).with_name("amount_semantics_trace.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
lines=["# Amount-safe-to-pay semantic trace","","This traces each solved row from evidence and timeline state through candidate selection. It is diagnostic only.","",f"- Expected amount equals benchmark first payment: {summary['expected_amount_equals_plan_first']}/25",f"- Expected amount equals requested amount: {summary['expected_amount_equals_requested']}/25",f"- Expected amount equals selected plan first payment: {summary['expected_amount_equals_selected_first']}/25",f"- Expected amount equals current baseline primitive: {summary['expected_amount_equals_baseline']}/25",f"- Preliminary categories: {summary['category_counts']}","","| Request | Expected amount | Benchmark method/first | Selected method/first | Baseline safe | Headroom | Expected plan | Selected plan | Preliminary category |","|---|---:|---|---|---:|---:|---|---|---|"]
for r in rows:
 lines.append(f"| {r['request_id']} | {r['expected_amount']} | {r['expected_method']} / {r['expected_plan_first_amount']} | {r['selected_method']} / {r['selected_plan_first_amount'] or '-'} | {r['baseline_safe']} | {r['headroom_before_request_payment']} | {r['expected_plan']} | {r['selected_plan']} | {r['preliminary_category']} |")
Path(__file__).with_name("amount_semantics_trace.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
print(json.dumps({k:v for k,v in summary.items() if k!="rows"},indent=2))
