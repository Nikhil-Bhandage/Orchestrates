# Amount-safe-to-pay semantic trace

This traces each solved row from evidence and timeline state through candidate selection. It is diagnostic only.

- Expected amount equals benchmark first payment: 4/25
- Expected amount equals requested amount: 4/25
- Expected amount equals selected plan first payment: 1/25
- Expected amount equals current baseline primitive: 2/25
- Preliminary categories: {'full_payment_amount_equals_request': 3, 'immediate_safe_capacity_semantics_or_state_mismatch': 18, 'safe_capacity_before_spending_changes_or_state_mismatch': 3, 'selected_partial_first_payment_semantics': 1}

| Request | Expected amount | Benchmark method/first | Selected method/first | Baseline safe | Headroom | Expected plan | Selected plan | Preliminary category |
|---|---:|---|---|---:|---:|---|---|---|
| request_01 | 25256 | full_payment / 25256 | not_recommended / - | 17896.72 | 40481.1 | 2024-03-03:25256 | none | full_payment_amount_equals_request |
| request_02 | 17229139.2 | installments / 15952906.67 | installments / 15952906.67 | 19808677.60 | 31225489.2 | 2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67 | 2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_03 | 873000 | wait / 5491000 | wait / 5491000 | 1043755.81 | 2001600 | 2019-11-15:5491000 | 2019-11-13:5491000 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_04 | 8401800 | wait / 12693000 | wait / 12693000 | 11986593.66 | 19486481.17 | 2024-06-15:12693000 | 2024-06-14:12693000 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_05 | 737 | not_recommended / 0 | not_recommended / - | 0 | 33375.1 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_06 | 603.3 | full_payment / 620.40 | full_payment / 620.4 | 620.4 | 1109.5 | 2026-01-03:620.40 | 2026-01-03:620.4 | safe_capacity_before_spending_changes_or_state_mismatch |
| request_07 | 87170.56 | installments / 68432 | not_recommended / - | 0 | 125945.56 | 2024-09-12:68432|2024-10-10:68432|2024-11-07:68432 | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_08 | 284.57 | wait / 996.60 | not_recommended / - | 303.90 | 736.57 | 2025-04-15:996.60 | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_09 | 166.61 | full_payment / 166.61 | not_recommended / - | 162.72 | 1631.1 | 2026-07-04:166.61 | none | full_payment_amount_equals_request |
| request_10 | 12700 | not_recommended / 0 | not_recommended / - | 266700 | 524755 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_11 | 12510645 | full_payment / 13110000 | full_payment / 13110000 | 13110000 | 29391195 | 2025-05-03:13110000 | 2025-05-03:13110000 | safe_capacity_before_spending_changes_or_state_mismatch |
| request_12 | 65164 | installments / 22590.19 | installments / 22590.19 | 65164 | 149889.89 | 2026-04-19:22590.19|2026-05-20:22590.19|2026-06-20:22590.19 | 2026-04-19:22590.19|2026-05-20:22590.19|2026-06-20:22590.19 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_13 | 433.4 | wait / 941.60 | full_payment / 941.6 | 941.6 | 1489.52 | 2024-05-15:941.60 | 2024-03-07:941.6 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_14 | 597.74 | not_recommended / 0 | not_recommended / - | 0 | 1731.74 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_15 | 83.05 | not_recommended / 0 | not_recommended / - | 0 | 505.63 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_16 | 122500 | full_payment / 122500 | full_payment / 122500 | 122500 | 239970 | 2023-08-12:122500 | 2023-08-12:122500 | full_payment_amount_equals_request |
| request_17 | 243849.58 | installments / 95194.67 | installments / 95194.67 | 274600 | 384279.58 | 2026-03-01:95194.67|2026-03-31:95194.67|2026-04-30:95194.67 | 2026-03-01:95194.67|2026-03-31:95194.67|2026-04-30:95194.67 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_18 | 462 | wait / 3246.10 | wait / 3246.1 | 662.19 | 960.6 | 2026-09-15:3246.10 | 2026-08-14:3246.1 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_19 | 28820 | partial_payment / 28820 | installments / 20623.2 | 39660 | 106745 | 2024-09-04:28820|2024-09-15:10840 | 2024-09-04:20623.2|2024-10-02:20623.2 | selected_partial_first_payment_semantics |
| request_20 | 5400 | not_recommended / 0 | not_recommended / - | 23818.52 | 38109.05 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_21 | 1543.35 | full_payment / 1574.40 | full_payment / 1574.4 | 1574.4 | 2111.35 | 2026-04-03:1574.40 | 2026-04-03:1574.4 | safe_capacity_before_spending_changes_or_state_mismatch |
| request_22 | 475.46 | installments / 253.59 | installments / 253.59 | 503.12 | 632.46 | 2024-12-08:253.59|2025-01-05:253.59|2025-02-02:253.59 | 2024-12-08:253.59|2025-01-05:253.59|2025-02-02:253.59 | immediate_safe_capacity_semantics_or_state_mismatch |
| request_23 | 9152 | wait / 38016 | not_recommended / - | 8263.15 | 23279.53 | 2025-07-15:38016 | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_24 | 13420 | not_recommended / 0 | not_recommended / - | 15056.98 | 28735.74 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
| request_25 | 1425000 | not_recommended / 0 | not_recommended / - | 3838582.88 | 8683950 | none | none | immediate_safe_capacity_semantics_or_state_mismatch |
