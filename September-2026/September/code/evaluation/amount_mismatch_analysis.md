# Golden amount/status/method investigation

This is a diagnostic classification of the 25 public solved rows. The classification is not used by prediction code and does not hardcode solved labels.

Detailed numeric trace:

- `amount_semantics_trace.json`
- `amount_semantics_trace.md`

The trace follows request -> evidence context -> evidence-adjusted timeline -> baseline safe-capacity primitive -> generated candidates -> selected candidate -> output amount. It also compares the benchmark schedule's first payment, total, and date against the selected schedule.

## Amount semantics established from specification and data

`README.md`, `problem_statement.md`, and `AGENTS.md` all define:

> `amount_safe_to_pay` is the largest amount safe to pay on `request_date` before optional spending changes.

The data supports this interpretation:

- It is not generally the selected plan total.
- It is not generally the first installment: installment rows 02, 07, 12, 17, and 22 have benchmark amounts different from their first installment.
- It is not generally the selected wait payment: wait rows use a smaller amount than the later full payment.
- It equals the first payment for the one partial-payment row, as required by the partial-payment rule.
- It equals the requested amount for safe immediate full-payment rows 09 and 16, and for benchmark row 01.
- Benchmark row 19 also equals its partial first payment, but that row conflicts with the maximum-safe-capacity interpretation because the reconstructed no-change state can safely cover the full requested amount.
- Not-recommended rows 05, 10, 14, 15, 20, 24, and 25 still report a nonzero amount in the public data. Therefore recommendation failure must not automatically force `amount_safe_to_pay` to zero.

The implementation now reports the baseline no-change safe amount for `not_recommended` fallback decisions. This follows the output definition and generalizes to all requests; it is not a solved-row rule.

## Row classifications

Primary category meanings:

1. Correct candidate, incorrect amount calculation
2. Wrong candidate selected
3. Wrong interpretation of `amount_safe_to_pay`
4. Forecast/state mismatch
5. Currency/evidence issue
6. Other

Rows 12 and 16 have no amount mismatch. Rows are assigned one primary category; secondary observations are shown separately.

| Request | Primary category | Evidence/state trace | Benchmark plan vs selected plan | Amount diagnosis |
|---|---:|---|---|---|
| request_01 | 4 | No relevant evidence; our 90-day path falls below minimum on 2024-05-11 after the request deadline, while the benchmark accepts the immediate plan. | Full payment vs no surviving candidate. | Benchmark amount is the requested amount; difference is forecast-policy feasibility. |
| request_02 | 1 | Payroll evidence is applied; timeline and selected installment schedule are stable. | Exact installment schedule match. | Candidate is correct; benchmark safe amount is below our baseline capacity. |
| request_03 | 2 | No relevant evidence; salary projection is 2024-11-13 in our timeline. | Wait on 2019-11-13 vs benchmark wait on 2019-11-15. | Amount is tied to the different candidate/state boundary. |
| request_04 | 2 | No relevant evidence; salary projection is 2024-06-14 in our timeline. | Wait on 2024-06-14 vs benchmark wait on 2024-06-15. | Amount is tied to the different candidate/state boundary. |
| request_05 | 4 | No evidence; natural forecast crosses minimum before the forecast end, so our safe capacity is zero. | Both are not recommended. | Benchmark reports a positive amount despite a different forecast interpretation. |
| request_06 | 2 | Payroll message is evidence; no-change plan is feasible in our 90-day simulation. | Same full-payment schedule, but benchmark requires `stop:event_476`. | Benchmark amount is below the request and its status treats the spending change as necessary. |
| request_07 | 4 | Payroll-date amendment is applied; our third-installment plan is followed by a projected minimum violation on 2024-11-11. | Benchmark installments vs no surviving candidate. | Amount and method depend on forecast horizon/event-boundary semantics. |
| request_08 | 4 (secondary 5, fixed) | Payroll amendment originally failed to update cached forecast cash effect; this was fixed. The amended salary now applies, but a later 90-day projected violation remains after the benchmark completion date. | Benchmark wait on 2025-04-15 vs no surviving candidate. | Remaining difference is horizon/forecast policy, not currency. |
| request_09 | 4 | No evidence; our path falls below minimum on 2026-09-30, after the benchmark deadline. | Benchmark full payment vs no surviving candidate. | Benchmark accepts the request amount under a shorter/equivalent forecast interpretation. |
| request_10 | 4 | Pending payout remains correctly excluded; our baseline safe capacity is high but no eligible plan survives the option/preference rules. | Both not recommended. | After fallback correction, amount is baseline capacity; remaining difference is benchmark state/forecast policy. |
| request_11 | 2 | Payroll amount evidence applies; our no-change full plan is simulator-feasible. | Same full-payment schedule, but benchmark requires `reduce_to:event_989:665950`. | Benchmark treats the change as necessary under a different projected state. |
| request_12 | — | Evidence/state and schedule agree. | Exact installment schedule match. | Amount matches exactly. |
| request_13 | 2 | No evidence; our immediate full payment is feasible. | Benchmark waits until 2024-05-15; engine selects full payment on request date. | Benchmark uses a more conservative immediate-affordability interpretation. |
| request_14 | 4 | Payroll/childcare evidence is present; our natural forecast falls below minimum before the deadline. | Both not recommended. | Benchmark positive safe amount reflects a different forecast/state policy. |
| request_15 | 4 | Confirmed first salary evidence applies; natural forecast crosses minimum before the horizon. | Both not recommended. | Benchmark positive safe amount reflects a different forecast/state policy. |
| request_16 | — | Rent amendment is applied and full payment is feasible. | Exact full-payment schedule match. | Amount matches exactly. |
| request_17 | 1 | No relevant evidence; selected installment schedule is simulator-feasible and exact. | Exact installment schedule match. | Candidate is correct; safe-capacity amount differs from benchmark. |
| request_18 | 2 | Internal-transfer evidence is correctly non-duplicating; earlier safe date is found by event-boundary search. | Wait on 2026-08-14 vs benchmark wait on 2026-09-15. | Amount is tied to the different candidate/date interpretation. |
| request_19 | 3 (secondary 2) | No evidence; baseline capacity reaches the request amount, so maximum-first-payment logic does not emit a partial split. | Benchmark partial payment vs supplied installment selected by engine. | Benchmark amount equals the partial first payment, not the reconstructed maximum immediate safe amount. |
| request_20 | 4 | Pending refund remains excluded as required; no eligible plan survives. | Both not recommended. | Benchmark positive amount differs from our forecast-derived baseline capacity. |
| request_21 | 2 | No evidence; no-change full payment is feasible in our timeline. | Same full-payment schedule, but benchmark requires two permitted changes. | Benchmark treats changes as necessary under a different projected state. |
| request_22 | 1 | Unrealized investment evidence remains non-cash; selected installment schedule is exact and feasible. | Exact installment schedule match. | Candidate is correct; safe-capacity amount differs from benchmark. |
| request_23 | 4 | Pending prize remains excluded as required; our natural forecast does not support the benchmark wait plan under the full horizon. | Benchmark wait vs no surviving candidate. | Difference is unsupported-income/forecast policy, not a currency conversion. |
| request_24 | 4 | Settled proceeds evidence is applied; no eligible plan survives the forecast. | Both not recommended. | Benchmark positive amount differs from our forecast-derived baseline capacity. |
| request_25 | 4 | No relevant evidence; IDR source and home-currency state are now calculated in home currency. | Both not recommended. | Remaining difference is forecast/state policy, not the previously fixed source-unit currency bug. |

## Status and method mismatch relationship

The nine status mismatches are requests 01, 06, 07, 08, 09, 11, 13, 21, and 23. The seven method mismatches are requests 01, 07, 08, 09, 13, 19, and 23.

Shared root causes:

- Requests 01, 07, 08, 09, and 23 are primarily feasibility/date-boundary differences. The benchmark plan completes by its deadline, while our strict simulator checks the remaining 90-day forecast and rejects a later minimum-balance violation.
- Requests 06, 11, and 21 have the same method but differ on whether optional spending changes are considered necessary. This is a forecast-policy/state difference, not a method-preference error.
- Request 13 is an immediate-versus-wait interpretation difference: our full payment is feasible; the benchmark chooses to wait despite the same available payment method.
- Request 19 is a plan-selection/amount-semantic conflict: the benchmark chooses partial payment even though the reconstructed immediate safe capacity reaches the full request; the supplied installment has a higher total cost and should lose under the documented ranking hierarchy.

## Fixes and before/after counts

### Fix 1: amended payroll cash effect

In `evidence_resolution.py`, payroll evidence now updates both:

```text
CanonicalEvent.amount
CanonicalEvent.forecast_cash_effect
TimelineEntry.cash_flow
```

Previously only `amount` changed, leaving the cached cash flow stale. This is a general evidence-state correctness fix. A regression test uses request 08 and verifies EUR 1,422.85 propagates into the projected cash flow.

### Fix 2: amount on fallback decisions

In `candidate_plans.py`, `not_recommended` now reports:

```text
amount_safe_to_pay = baseline_safe_amount
```

instead of zero. This follows the independent output definition of amount safety and applies to every request.

### Public golden counts

| Metric | Before | After |
|---|---:|---:|
| Exact rows | 2/25 | 2/25 |
| Amount matches | 2/25 | 2/25 |
| Status matches | 16/25 | 16/25 |
| Method matches | 18/25 | 18/25 |
| Payment-plan matches | 13/25 | 13/25 |
| Earliest-date matches | 8/25 | 8/25 |
| Spending-change matches | 22/25 | 22/25 |

The public counts do not improve because the remaining mismatches are dominated by the benchmark’s forecast horizon/state policy. The fixes nevertheless generalize: amended payroll cash effects are now correct for all evidence-adjusted timelines, and fallback rows preserve their independently computed safe amount on the full evaluation set.

No `output.csv` or natural-language explanation layer was generated.
