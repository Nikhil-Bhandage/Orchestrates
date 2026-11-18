# Candidate-plan golden-sample mismatch report

This artifact evaluates the deterministic candidate engine against the 25 public solved rows. It is diagnostic only; solved labels are not used as prediction-time rules.

- Exact rows: **2/25**
- Field matches: `amount_safe_to_pay` 2/25, `affordability_status` 16/25, `recommended_payment_method` 18/25, `payment_plan` 13/25, `earliest_date_for_full_payment` 8/25, `spending_changes_needed` 22/25
- Mismatch counts: `amount_safe_to_pay` 23, `affordability_status` 9, `recommended_payment_method` 7, `payment_plan` 12, `earliest_date_for_full_payment` 17, `spending_changes_needed` 3

## Rows

| Request | Expected method/status | Selected method/status | Amount safe | Earliest full date | Mismatches |
|---|---|---|---:|---|---|
| request_01 | full_payment / affordable_now | not_recommended / not_affordable | 17896.72 | empty | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_02 | installments / affordable_with_plan | installments / affordable_with_plan | 19808677.60 | 2025-09-13 | amount_safe_to_pay, earliest_date_for_full_payment |
| request_03 | wait / affordable_later | wait / affordable_later | 1043755.81 | 2019-11-13 | amount_safe_to_pay, payment_plan, earliest_date_for_full_payment |
| request_04 | wait / affordable_later | wait / affordable_later | 11986593.66 | 2024-06-14 | amount_safe_to_pay, payment_plan, earliest_date_for_full_payment |
| request_05 | not_recommended / not_affordable | not_recommended / not_affordable | 0 | empty | amount_safe_to_pay |
| request_06 | full_payment / affordable_with_plan | full_payment / affordable_now | 620.4 | 2026-01-03 | amount_safe_to_pay, affordability_status, payment_plan, earliest_date_for_full_payment, spending_changes_needed |
| request_07 | installments / affordable_with_plan | not_recommended / not_affordable | 101903.15 | empty | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_08 | wait / affordable_later | not_recommended / not_affordable | 303.90 | empty | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_09 | full_payment / affordable_now | not_recommended / not_affordable | 162.72 | empty | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_10 | not_recommended / not_affordable | not_recommended / not_affordable | 266700 | 2024-12-06 | amount_safe_to_pay, earliest_date_for_full_payment |
| request_11 | full_payment / affordable_with_plan | full_payment / affordable_now | 13110000 | 2025-05-03 | amount_safe_to_pay, affordability_status, earliest_date_for_full_payment, spending_changes_needed |
| request_12 | installments / affordable_with_plan | installments / affordable_with_plan | 65164 | 2026-04-05 | none |
| request_13 | wait / affordable_later | full_payment / affordable_now | 941.6 | 2024-03-07 | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_14 | not_recommended / not_affordable | not_recommended / not_affordable | 0 | empty | amount_safe_to_pay |
| request_15 | not_recommended / not_affordable | not_recommended / not_affordable | 0 | empty | amount_safe_to_pay |
| request_16 | full_payment / affordable_now | full_payment / affordable_now | 122500 | 2023-08-12 | none |
| request_17 | installments / affordable_with_plan | installments / affordable_with_plan | 274600 | 2026-03-01 | amount_safe_to_pay, earliest_date_for_full_payment |
| request_18 | wait / affordable_later | wait / affordable_later | 662.19 | 2026-08-14 | amount_safe_to_pay, payment_plan, earliest_date_for_full_payment |
| request_19 | partial_payment / affordable_with_plan | installments / affordable_with_plan | 39660 | 2024-09-04 | amount_safe_to_pay, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_20 | not_recommended / not_affordable | not_recommended / not_affordable | 23818.52 | empty | amount_safe_to_pay |
| request_21 | full_payment / affordable_with_plan | full_payment / affordable_now | 1574.4 | 2026-04-03 | amount_safe_to_pay, affordability_status, payment_plan, earliest_date_for_full_payment, spending_changes_needed |
| request_22 | installments / affordable_with_plan | installments / affordable_with_plan | 503.12 | 2025-01-16 | amount_safe_to_pay, earliest_date_for_full_payment |
| request_23 | wait / affordable_later | not_recommended / not_affordable | 8263.15 | empty | amount_safe_to_pay, affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment |
| request_24 | not_recommended / not_affordable | not_recommended / not_affordable | 15056.98 | empty | amount_safe_to_pay |
| request_25 | not_recommended / not_affordable | not_recommended / not_affordable | 3838582.88 | empty | amount_safe_to_pay |

## Systematic mismatch categories

- **State versus plan semantics:** the engine validates the selected plan with the deterministic simulator; it does not force the prior one-time-capacity primitive to match a solved `amount_safe_to_pay` label.
- **Evidence/state differences:** messages may amend existing salary/rent entries, but unsupported pending income, bonuses, refunds, prizes, and unrealized values remain excluded.
- **Forecast-policy differences:** conservative recurring and essential-variable projections can change whether a public plan is feasible; these are retained as diagnostics rather than sample-specific exceptions.
- **Option/preference differences:** installment offers are accepted only when their exact schedule, duration, cost, deadline, and user preference all pass hard validation.
