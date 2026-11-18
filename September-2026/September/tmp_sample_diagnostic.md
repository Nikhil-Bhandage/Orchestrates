# Final 250-request diagnostic

- Requests: 25
- Validation failures: 0
- No-feasible-candidate requests: 12

## Aggregate distributions

```json
{
  "request_count": 25,
  "affordability_statuses": {
    "affordable_later": 3,
    "affordable_now": 5,
    "affordable_with_plan": 5,
    "not_affordable": 12
  },
  "payment_methods": {
    "full_payment": 5,
    "installments": 5,
    "not_recommended": 12,
    "wait": 3
  },
  "spending_change_usage": {
    "requests_with_changes": 0,
    "by_selected_method": {},
    "actions": {}
  },
  "validation_failures": {},
  "validation_failure_count": 0,
  "unresolved_fields": {},
  "requests_with_no_feasible_candidate": 12,
  "candidate_rejection_counts_for_no_feasible": {
    "deadline_missed": 41,
    "payment_preference_conflict": 82,
    "simulation_infeasible": 22,
    "wait_requires_full_payment_preference": 1
  },
  "sanity_checks": {
    "all_request_ids_present_once": true,
    "all_rows_schema_valid": true,
    "all_rows_valid": true,
    "impossible_output_flags": [],
    "distribution_flags": []
  }
}
```

## Requests

| Request | Method | Status | Safe amount | Plan | Completion | Minimum seen | Validation | Reason codes |
|---|---|---|---:|---|---|---:|---|---|
| request_01 | not_recommended | not_affordable | 17896.72 | none | — | 35896.72 | valid | not_affordable, no_feasible_candidate |
| request_02 | installments | affordable_with_plan | 19808677.6 | 2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67 | 2025-10-07 | 33014170.93 | valid | installment_preferred |
| request_03 | wait | affordable_later | 1043755.81 | 2019-11-13:5491000 | 2019-11-13 | 3712455.81 | valid | waiting_for_income, minimum_balance_constraint |
| request_04 | wait | affordable_later | 11986593.66 | 2024-06-14:12693000 | 2024-06-14 | 35657199.24 | valid | waiting_for_income, minimum_balance_constraint |
| request_05 | not_recommended | not_affordable | 0 | none | — | 10921.32 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_06 | full_payment | affordable_now | 620.4 | 2026-01-03:620.4 | 2026-01-03 | 1074.44 | valid | sufficient_balance |
| request_07 | not_recommended | not_affordable | 101903.15 | none | — | 194903.15 | valid | not_affordable, no_feasible_candidate |
| request_08 | not_recommended | not_affordable | 303.9 | none | — | 1103.9 | valid | not_affordable, no_feasible_candidate |
| request_09 | not_recommended | not_affordable | 162.72 | none | — | 762.72 | valid | not_affordable, no_feasible_candidate |
| request_10 | not_recommended | not_affordable | 266700 | none | — | 570892.88 | valid | not_affordable, no_feasible_candidate |
| request_11 | full_payment | affordable_now | 13110000 | 2025-05-03:13110000 | 2025-05-03 | 36912241.52 | valid | sufficient_balance |
| request_12 | installments | affordable_with_plan | 65164 | 2026-04-19:22590.19|2026-05-20:22590.19|2026-06-20:22590.19 | 2026-06-20 | 47085.08 | valid | installment_preferred |
| request_13 | full_payment | affordable_now | 941.6 | 2024-03-07:941.6 | 2024-03-07 | 1639.56 | valid | sufficient_balance |
| request_14 | not_recommended | not_affordable | 0 | none | — | 649.51 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_15 | not_recommended | not_affordable | 0 | none | — | 608.22 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_16 | full_payment | affordable_now | 122500 | 2023-08-12:122500 | 2023-08-12 | 129684.24 | valid | sufficient_balance |
| request_17 | installments | affordable_with_plan | 274600 | 2026-03-01:95194.67|2026-03-31:95194.67|2026-04-30:95194.67 | 2026-04-30 | 349423.38 | valid | installment_preferred |
| request_18 | wait | affordable_later | 662.19 | 2026-08-14:3246.1 | 2026-08-14 | 2062.19 | valid | waiting_for_income, minimum_balance_constraint |
| request_19 | installments | affordable_with_plan | 39660 | 2024-09-04:20623.2|2024-10-02:20623.2 | 2024-10-02 | 141607.09 | valid | installment_preferred |
| request_20 | not_recommended | not_affordable | 23818.52 | none | — | 88318.52 | valid | not_affordable, no_feasible_candidate |
| request_21 | full_payment | affordable_now | 1574.4 | 2026-04-03:1574.4 | 2026-04-03 | 1877.94 | valid | sufficient_balance |
| request_22 | installments | affordable_with_plan | 503.12 | 2024-12-08:253.59|2025-01-05:253.59|2025-02-02:253.59 | 2025-02-02 | 685.55 | valid | installment_preferred |
| request_23 | not_recommended | not_affordable | 8263.15 | none | — | 35263.15 | valid | not_affordable, no_feasible_candidate |
| request_24 | not_recommended | not_affordable | 15056.98 | none | — | 66056.98 | valid | not_affordable, no_feasible_candidate |
| request_25 | not_recommended | not_affordable | 3838582.88 | none | — | 27217682.88 | valid | not_affordable, no_feasible_candidate |
