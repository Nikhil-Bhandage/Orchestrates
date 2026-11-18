# Candidate plan generation and ranking report

This stage implements candidate generation, deterministic hard filtering, and personalized ranking. It does not generate `output.csv` or natural-language explanations.

## Files changed

- `code/candidate_plans.py`
- `code/test_candidate_plans.py`
- `code/evaluation/candidate_evaluation.py`
- `code/evaluation/candidate_sample_mismatch.json`
- `code/evaluation/candidate_sample_mismatch.md`
- `code/evaluation/candidate_plan_report.md`

The existing simulator and evidence/state modules were not otherwise optimized or rewritten.

## Candidate types

`CandidatePlan` contains:

- payment method
- exact payment schedule
- total payment and total payment cost
- amount safe to pay
- completion date
- spending changes
- rationale codes and option metadata
- simulator result

Generated candidates are:

- immediate full payment using the supplied full-payment option
- exact supplied installment options
- two-payment partial plans derived from balance safety
- wait plans using the earliest safe one-time payment date
- the above immediate plans with up to three permitted flexible recurring-spending changes
- an explicit `not_recommended` fallback when no candidate survives

No arbitrary installment schedule or unsupported financial event is generated.

## Hard constraints

Candidates are rejected before ranking when they violate any of the following:

- payment-method preference or wait/full-payment preference
- payment date ordering, request-date lower bound, forecast horizon, or deadline
- simulator minimum-balance feasibility
- exact total payment requirements
- exact supplied installment option amount, count, cadence, first date, and total payable cost
- maximum installment months
- partial-payment permission, preference, two-payment shape, positive partial amount, and exact total
- amount-safe bounds
- maximum three spending changes and simulator-validated flexible/protected/minimum rules

The existing `simulate_payment_plan()` is the final deterministic feasibility oracle.

## Ranking hierarchy

Feasible candidates use this lexicographic ranking tuple:

1. Complete by the deadline — all candidates reaching ranking already pass this hard constraint.
2. No spending changes.
3. Lowest total payment cost.
4. Earliest first payment date.
5. Fewest payments.
6. Lowest supplied `payment_option_id`.
7. Payment method name as a deterministic final tie-breaker.

User preferences are applied as eligibility constraints before ranking, so generic ranking cannot override explicit restrictions.

## Data structures and complexity

- Request and option lookup uses existing hash indexes.
- Equivalent recurring-change source IDs are grouped by their affected timeline indexes; only one representative target per equivalent recurrence is generated.
- Spending-change combinations are limited to three targets and generated with combinations/product choices.
- Wait feasibility is checked chronologically at request/date/event-boundary candidates. No binary search is used because future credits/debits can make affordability non-monotonic.
- Partial first-payment capacity is derived from the minimum prefix balance before the second payment. A defensive binary search is used only over that monotone split-capacity predicate if the simulator boundary disagrees with the closed form.
- For a timeline with `n` entries, a candidate simulation is O(n + p) using the existing natural-event/payment sweep. Candidate count is O(options × change-combinations + date-boundaries); equivalent recurrence grouping keeps practical change enumeration bounded.
- Full evaluation run: 250 requests, 665 feasible candidates retained, 2.66 feasible candidates per request on average, maximum 37, and 2,737 rejected attempts.

## Full evaluation candidate distribution

- `not_recommended`: 100
- `full_payment`: 57
- `installments`: 50
- `wait`: 36
- `partial_payment`: 7

Statuses:

- `not_affordable`: 100
- `affordable_now`: 56
- `affordable_with_plan`: 58
- `affordable_later`: 36

Most common hard rejection causes:

- payment preference conflict: 1,370
- deadline missed: 841
- simulator infeasible: 467
- wait without full-payment preference: 59

## Golden sample results

`candidate_sample_mismatch.md` and `.json` contain the complete 25-row comparison.

- Exact rows: 2/25
- Affordability-status matches: 16/25
- Recommended-method matches: 18/25
- Amount-safe matches: 2/25
- Payment-plan matches: 13/25
- Earliest-date matches: 8/25
- Spending-change matches: 22/25

The mismatches are systematic rather than sample-specific hardcoding opportunities:

- The selected plan is simulator-feasible and does not force the prior one-time-capacity primitive to match the solved amount field.
- Some public rows encode different forecast/state assumptions, especially conservative variable spending and evidence-derived future state.
- Some rows select wait or spending changes even where the current reconstructed state permits an immediate plan; those are preserved as benchmark diagnostics, not overridden by labels.
- Installment rows are accepted only when the exact supplied schedule and user preference pass hard validation.

## Amount-safe semantics used here

The engine keeps `amount_safe_to_pay` bounded and plan-aware:

- immediate full payment without changes: requested amount
- immediate full payment requiring changes: baseline no-change safe capacity
- partial payment: derived first payment amount
- installments and wait: baseline no-change safe capacity on the request date, because the output field still describes immediate capacity even when the selected plan starts later
- not recommended: the baseline no-change safe capacity, because amount safety is independent of whether an eligible recommendation survives

This is intentionally documented as an ambiguity boundary. The public solved rows sometimes report an amount that differs from both the selected plan's first payment and the current one-time-capacity primitive; this stage does not add sample-specific exceptions. The fallback now preserves the baseline state amount rather than replacing it with zero.

## Validation

```text
python3 -m py_compile code/*.py code/evaluation/*.py
python3 code/test_canonical_events.py
python3 code/test_financial_timeline.py
python3 code/test_evidence_resolution.py
python3 code/test_golden_samples.py
python3 code/test_candidate_plans.py
python3 code/evaluation/candidate_evaluation.py
```

All commands pass. Final output generation and explanation generation are intentionally deferred to the next stage.
