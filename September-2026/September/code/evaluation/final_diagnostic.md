# Final 250-request diagnostic

- Requests: 250
- Validation failures: 0
- No-feasible-candidate requests: 82

## Aggregate distributions

```json
{
  "request_count": 250,
  "affordability_statuses": {
    "affordable_later": 41,
    "affordable_now": 62,
    "affordable_with_plan": 65,
    "not_affordable": 82
  },
  "payment_methods": {
    "full_payment": 63,
    "installments": 54,
    "not_recommended": 82,
    "partial_payment": 10,
    "wait": 41
  },
  "spending_change_usage": {
    "requests_with_changes": 9,
    "by_selected_method": {
      "full_payment": 1,
      "installments": 5,
      "wait": 3
    },
    "actions": {
      "reduce_to:event_14534:3280": 1,
      "reduce_to:event_16352:46.4": 1,
      "reduce_to:event_17160:660": 1,
      "reduce_to:event_17233:623.7": 1,
      "stop:event_10912": 1,
      "stop:event_12572": 1,
      "stop:event_13140": 1,
      "stop:event_17159": 1,
      "stop:event_2412": 1,
      "stop:event_5101": 1,
      "stop:event_5471": 1
    }
  },
  "validation_failures": {},
  "validation_failure_count": 0,
  "unresolved_fields": {},
  "requests_with_no_feasible_candidate": 82,
  "candidate_rejection_counts_for_no_feasible": {
    "deadline_missed": 327,
    "payment_preference_conflict": 309,
    "simulation_infeasible": 231,
    "wait_requires_full_payment_preference": 8
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
| request_26 | full_payment | affordable_now | 15656000 | 2025-08-03:15656000 | 2025-08-03 | 30979709.69 | valid | sufficient_balance |
| request_27 | full_payment | affordable_with_plan | 6186.04 | 2026-07-05:6670 | 2026-07-05 | 21220.54 | valid | spending_change_required |
| request_28 | wait | affordable_later | 314.04 | 2024-08-13:1302.4 | 2024-08-13 | 1307.04 | valid | waiting_for_income, minimum_balance_constraint |
| request_29 | not_recommended | not_affordable | 32600.95 | none | — | 60900.95 | valid | not_affordable, no_feasible_candidate |
| request_30 | not_recommended | not_affordable | 416.16 | none | — | 1316.16 | valid | not_affordable, no_feasible_candidate |
| request_31 | wait | affordable_later | 3104409.61 | 2024-09-14:18164000 | 2024-09-14 | 19693309.61 | valid | waiting_for_income, minimum_balance_constraint |
| request_32 | not_recommended | not_affordable | 0 | none | — | -3746.19 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_33 | wait | affordable_later | 48207.35 | 2026-02-13:118000 | 2026-02-13 | 135835.51 | valid | waiting_for_income, minimum_balance_constraint |
| request_34 | full_payment | affordable_now | 129400 | 2024-12-04:129400 | 2024-12-04 | 155500.11 | valid | sufficient_balance |
| request_35 | not_recommended | not_affordable | 38099.29 | none | — | 144499.29 | valid | not_affordable, no_feasible_candidate |
| request_36 | wait | affordable_later | 772.85 | 2026-08-14:3954 | 2026-08-14 | 3062.73 | valid | waiting_for_income, minimum_balance_constraint |
| request_37 | not_recommended | not_affordable | 3975769.45 | none | — | 21031969.45 | valid | not_affordable, no_feasible_candidate |
| request_38 | wait | affordable_later | 261.06 | 2025-09-13:971.3 | 2025-09-13 | 661.06 | valid | waiting_for_income, minimum_balance_constraint |
| request_39 | wait | affordable_later | 149577.38 | 2026-04-14:208600 | 2026-04-14 | 362977.38 | valid | waiting_for_income, minimum_balance_constraint |
| request_40 | not_recommended | not_affordable | 0 | none | — | -122.67 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_41 | wait | affordable_later | 11474344.39 | 2025-11-14:38760000 | 2025-11-14 | 36840944.39 | valid | waiting_for_income, minimum_balance_constraint |
| request_42 | full_payment | affordable_now | 52100 | 2026-01-05:52100 | 2026-01-05 | 172711.64 | valid | sufficient_balance |
| request_43 | wait | affordable_later | 9802940.49 | 2024-11-12:43339000 | 2024-11-12 | 31200940.49 | valid | waiting_for_income, minimum_balance_constraint |
| request_44 | not_recommended | not_affordable | 0 | none | — | -12455.46 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_45 | wait | affordable_later | 5087536.44 | 2026-08-14:21983000 | 2026-08-14 | 16237336.44 | valid | waiting_for_income, minimum_balance_constraint |
| request_46 | partial_payment | affordable_with_plan | 33398.92 | 2024-12-03:33398.92|2024-12-15:16051.08 | 2024-12-15 | 84000 | valid | minimum_balance_constraint, deadline_constraint |
| request_47 | not_recommended | not_affordable | 9999760.35 | none | — | 40048760.35 | valid | not_affordable, no_feasible_candidate |
| request_48 | full_payment | affordable_now | 45700 | 2026-07-25:45700 | 2026-07-25 | 92046.56 | valid | sufficient_balance |
| request_49 | installments | affordable_with_plan | 11443610.95 | 2024-03-18:11902106.67|2024-04-18:11902106.67|2024-05-19:11902106.67 | 2024-05-19 | 20813667.13 | valid | installment_preferred |
| request_50 | full_payment | affordable_now | 43900 | 2025-08-06:43900 | 2025-08-06 | 155506.44 | valid | sufficient_balance |
| request_51 | not_recommended | not_affordable | 2131140.2 | none | — | 9942140.2 | valid | not_affordable, no_feasible_candidate |
| request_52 | wait | affordable_later | 26530 | 2024-06-16:28870 | 2024-06-16 | 68030 | valid | waiting_for_income, minimum_balance_constraint |
| request_53 | installments | affordable_with_plan | 607.86 | 2025-11-21:589.06|2025-12-19:589.06|2026-01-16:589.06 | 2026-01-16 | 2707.86 | valid | installment_preferred |
| request_54 | not_recommended | not_affordable | 6319.09 | none | — | 43319.09 | valid | not_affordable, no_feasible_candidate |
| request_55 | installments | affordable_with_plan | 132540.36 | 2026-06-11:75781.33|2026-07-12:75781.33|2026-08-12:75781.33 | 2026-08-12 | 137510.66 | valid | installment_preferred, spending_change_required |
| request_56 | partial_payment | affordable_with_plan | 760.27 | 2025-02-03:760.27|2025-02-14:121.29 | 2025-02-14 | 2100 | valid | minimum_balance_constraint, deadline_constraint |
| request_57 | wait | affordable_later | 12349.83 | 2026-06-13:61446 | 2026-06-13 | 55049.83 | valid | waiting_for_income, minimum_balance_constraint |
| request_58 | full_payment | affordable_now | 16226000 | 2024-12-07:16226000 | 2024-12-07 | 21679995.98 | valid | sufficient_balance |
| request_59 | installments | affordable_with_plan | 140600 | 2025-05-07:48741.33|2025-06-04:48741.33|2025-07-02:48741.33 | 2025-07-02 | 140037.46 | valid | installment_preferred, spending_change_required |
| request_60 | wait | affordable_later | 186.69 | 2026-01-14:199.89 | 2026-01-14 | 542.26 | valid | waiting_for_income, minimum_balance_constraint |
| request_61 | installments | affordable_with_plan | 29062 | 2024-03-17:10074.83|2024-04-17:10074.83|2024-05-18:10074.83 | 2024-05-18 | 61356.09 | valid | installment_preferred |
| request_62 | full_payment | affordable_now | 404.23 | 2025-08-05:404.23 | 2025-08-05 | 3701.36 | valid | sufficient_balance |
| request_63 | partial_payment | affordable_with_plan | 48485.36 | 2026-07-07:48485.36|2026-08-14:295414.64 | 2026-08-14 | 153500 | valid | minimum_balance_constraint, deadline_constraint |
| request_64 | not_recommended | not_affordable | 0 | none | — | 2294.07 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_65 | not_recommended | not_affordable | 8359.38 | none | — | 23859.38 | valid | not_affordable, no_feasible_candidate |
| request_66 | full_payment | affordable_now | 22200 | 2026-04-03:22200 | 2026-04-03 | 236444.34 | valid | sufficient_balance |
| request_67 | wait | affordable_later | 518.02 | 2024-09-14:2094 | 2024-09-14 | 1653.7 | valid | waiting_for_income, minimum_balance_constraint |
| request_68 | not_recommended | not_affordable | 182.42 | none | — | 1682.42 | valid | not_affordable, no_feasible_candidate |
| request_69 | full_payment | affordable_now | 529.1 | 2026-01-04:529.1 | 2026-01-04 | 739.19 | valid | sufficient_balance |
| request_70 | wait | affordable_later | 59952.21 | 2025-01-16:243900 | 2025-01-16 | 138036.63 | valid | waiting_for_income, minimum_balance_constraint |
| request_71 | not_recommended | not_affordable | 1361456.19 | none | — | 10246256.19 | valid | not_affordable, no_feasible_candidate |
| request_72 | not_recommended | not_affordable | 0 | none | — | 11656.89 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_73 | full_payment | affordable_now | 71400 | 2023-01-20:71400 | 2023-01-20 | 108739.25 | valid | sufficient_balance |
| request_74 | full_payment | affordable_now | 5010 | 2025-08-04:5010 | 2025-08-04 | 29976.48 | valid | sufficient_balance |
| request_75 | installments | affordable_with_plan | 28270 | 2026-04-09:9800.27|2026-05-09:9800.27|2026-06-08:9800.27 | 2026-06-08 | 48839.5 | valid | installment_preferred |
| request_76 | not_recommended | not_affordable | 867.25 | none | — | 2667.25 | valid | not_affordable, no_feasible_candidate |
| request_77 | full_payment | affordable_now | 60700 | 2025-11-05:60700 | 2025-11-05 | 82429.28 | valid | sufficient_balance |
| request_78 | full_payment | affordable_now | 50200 | 2025-10-02:50200 | 2025-10-02 | 57875.83 | valid | sufficient_balance |
| request_79 | partial_payment | affordable_with_plan | 796.65 | 2024-09-04:796.65|2024-09-15:1354.95 | 2024-09-15 | 1000 | valid | minimum_balance_constraint, deadline_constraint |
| request_80 | not_recommended | not_affordable | 119792.02 | none | — | 241092.02 | valid | not_affordable, no_feasible_candidate |
| request_81 | full_payment | affordable_now | 2076 | 2026-07-03:2076 | 2026-07-03 | 1786.2 | valid | sufficient_balance |
| request_82 | not_recommended | not_affordable | 336.7 | none | — | 1436.7 | valid | not_affordable, no_feasible_candidate |
| request_83 | not_recommended | not_affordable | 9821.04 | none | — | 47621.04 | valid | not_affordable, no_feasible_candidate |
| request_84 | wait | affordable_later | 29077.51 | 2026-05-14:95400 | 2026-05-14 | 114807.49 | valid | waiting_for_income, minimum_balance_constraint |
| request_85 | not_recommended | not_affordable | 419632.8 | none | — | 6815932.8 | valid | not_affordable, no_feasible_candidate |
| request_86 | not_recommended | not_affordable | 0 | none | — | 30815.49 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_87 | not_recommended | not_affordable | 0 | none | — | 114187.53 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_88 | installments | affordable_with_plan | 11959.79 | 2024-06-14:9045.23|2024-07-15:9045.23|2024-08-15:9045.23 | 2024-08-15 | 37759.79 | valid | installment_preferred |
| request_89 | installments | affordable_with_plan | 9613266.35 | 2025-11-18:4768746.67|2025-12-16:4768746.67|2026-01-13:4768746.67 | 2026-01-13 | 22147966.35 | valid | installment_preferred |
| request_90 | full_payment | affordable_now | 2560 | 2026-07-06:2560 | 2026-07-06 | 24086.83 | valid | sufficient_balance |
| request_91 | wait | affordable_later | 320.74 | 2024-11-13:1927.2 | 2024-11-13 | 2321.81 | valid | waiting_for_income, minimum_balance_constraint |
| request_92 | full_payment | affordable_now | 34034 | 2025-02-05:34034 | 2025-02-05 | 35593.52 | valid | sufficient_balance |
| request_93 | full_payment | affordable_now | 1729.2 | 2026-04-07:1729.2 | 2026-04-07 | 1982.33 | valid | sufficient_balance |
| request_94 | full_payment | affordable_now | 572 | 2024-12-04:572 | 2024-12-04 | 927.72 | valid | sufficient_balance |
| request_95 | not_recommended | not_affordable | 0 | none | — | 78405.58 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_96 | not_recommended | not_affordable | 33049.14 | none | — | 89549.14 | valid | not_affordable, no_feasible_candidate |
| request_97 | installments | affordable_with_plan | 2910.52 | 2024-03-19:8145.28|2024-04-19:8145.28|2024-05-20:8145.28 | 2024-05-20 | 32610.52 | valid | installment_preferred |
| request_98 | wait | affordable_later | 11097.99 | 2025-09-13:27148 | 2025-09-13 | 41097.99 | valid | waiting_for_income, minimum_balance_constraint |
| request_99 | full_payment | affordable_now | 18062 | 2026-07-04:18062 | 2026-07-04 | 52882.67 | valid | sufficient_balance |
| request_100 | installments | affordable_with_plan | 26546.03 | 2024-06-13:12866.19|2024-07-14:12866.19|2024-08-14:12866.19 | 2024-08-14 | 46179.84 | valid | installment_preferred |
| request_101 | full_payment | affordable_now | 143500 | 2025-11-03:143500 | 2025-11-03 | 237881.44 | valid | sufficient_balance |
| request_102 | installments | affordable_with_plan | 1716 | 2026-04-05:594.88|2026-05-05:594.88|2026-06-04:594.88 | 2026-06-04 | 1113.69 | valid | installment_preferred |
| request_103 | not_recommended | not_affordable | 11424.7 | none | — | 136924.7 | valid | not_affordable, no_feasible_candidate |
| request_104 | full_payment | affordable_now | 17204 | 2025-02-04:17204 | 2025-02-04 | 29969.23 | valid | sufficient_balance |
| request_105 | full_payment | affordable_now | 53500 | 2026-06-08:53500 | 2026-06-08 | 83387.83 | valid | sufficient_balance |
| request_106 | wait | affordable_later | 538.44 | 2025-01-16:2207.7 | 2025-01-16 | 1434.22 | valid | waiting_for_income, minimum_balance_constraint |
| request_107 | not_recommended | not_affordable | 827.49 | none | — | 2427.49 | valid | not_affordable, no_feasible_candidate |
| request_108 | not_recommended | not_affordable | 4736.92 | none | — | 28836.92 | valid | not_affordable, no_feasible_candidate |
| request_109 | installments | affordable_with_plan | 781.58 | 2024-03-18:645.98|2024-04-18:645.98|2024-05-19:645.98 | 2024-05-19 | 2481.58 | valid | installment_preferred |
| request_110 | not_recommended | not_affordable | 19462.35 | none | — | 30662.35 | valid | not_affordable, no_feasible_candidate |
| request_111 | not_recommended | not_affordable | 14422453.85 | none | — | 37445253.85 | valid | not_affordable, no_feasible_candidate |
| request_112 | not_recommended | not_affordable | 0 | none | — | 146.78 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_113 | full_payment | affordable_now | 36500 | 2026-09-04:36500 | 2026-09-04 | 82992.93 | valid | sufficient_balance |
| request_114 | full_payment | affordable_now | 65300 | 2026-01-04:65300 | 2026-01-04 | 119100.21 | valid | sufficient_balance |
| request_115 | wait | affordable_later | 16371.71 | 2024-10-14:80500 | 2024-10-14 | 39631.81 | valid | waiting_for_income, minimum_balance_constraint |
| request_116 | not_recommended | not_affordable | 20310.02 | none | — | 100610.02 | valid | not_affordable, no_feasible_candidate |
| request_117 | full_payment | affordable_now | 880 | 2026-07-05:880 | 2026-07-05 | 1047.81 | valid | sufficient_balance |
| request_118 | installments | affordable_with_plan | 633.29 | 2024-12-07:255.87|2025-01-07:255.87|2025-02-07:255.87 | 2025-02-07 | 611.73 | valid | installment_preferred, spending_change_required |
| request_119 | not_recommended | not_affordable | 70634.69 | none | — | 221834.69 | valid | not_affordable, no_feasible_candidate |
| request_120 | full_payment | affordable_now | 7714000 | 2026-04-06:7714000 | 2026-04-06 | 20665694.06 | valid | sufficient_balance |
| request_121 | full_payment | affordable_now | 633.6 | 2024-03-03:633.6 | 2024-03-03 | 962.45 | valid | sufficient_balance |
| request_122 | installments | affordable_with_plan | 20558000 | 2025-08-05:7126773.33|2025-09-02:7126773.33|2025-09-30:7126773.33 | 2025-09-30 | 34455980.16 | valid | installment_preferred |
| request_123 | not_recommended | not_affordable | 0 | none | — | 17168199.65 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_124 | installments | affordable_with_plan | 1480.83 | 2024-06-11:1076.12|2024-07-12:1076.12|2024-08-12:1076.12 | 2024-08-12 | 2004.71 | valid | installment_preferred |
| request_125 | full_payment | affordable_now | 6468 | 2025-11-06:6468 | 2025-11-06 | 13098.56 | valid | sufficient_balance |
| request_126 | not_recommended | not_affordable | 0 | none | — | 124932.64 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_127 | not_recommended | not_affordable | 0 | none | — | 5472.08 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_128 | full_payment | affordable_now | 25168 | 2025-02-07:25168 | 2025-02-07 | 49583.21 | valid | sufficient_balance |
| request_129 | not_recommended | not_affordable | 102.49 | none | — | 902.49 | valid | not_affordable, no_feasible_candidate |
| request_130 | not_recommended | not_affordable | 369.08 | none | — | 1769.08 | valid | not_affordable, no_feasible_candidate |
| request_131 | not_recommended | not_affordable | 261.36 | none | — | 1361.36 | valid | not_affordable, no_feasible_candidate |
| request_132 | full_payment | affordable_now | 379.86 | 2026-01-05:379.86 | 2026-01-05 | 1126.94 | valid | sufficient_balance |
| request_133 | not_recommended | not_affordable | 1257596.49 | none | — | 11243796.49 | valid | not_affordable, no_feasible_candidate |
| request_134 | wait | affordable_later | 6195440.75 | 2025-08-14:21831000 | 2025-08-14 | 22097940.75 | valid | waiting_for_income, minimum_balance_constraint |
| request_135 | full_payment | affordable_now | 304.8 | 2026-07-06:304.8 | 2026-07-06 | 526.53 | valid | sufficient_balance |
| request_136 | full_payment | affordable_now | 560.4 | 2024-06-03:560.4 | 2024-06-03 | 1139.18 | valid | sufficient_balance |
| request_137 | wait | affordable_later | 27318.92 | 2026-01-13:80100 | 2026-01-13 | 72592.06 | valid | waiting_for_income, minimum_balance_constraint, spending_change_required |
| request_138 | partial_payment | affordable_with_plan | 1022.04 | 2026-04-07:1022.04|2026-04-14:234.9 | 2026-04-14 | 2300 | valid | minimum_balance_constraint, deadline_constraint |
| request_139 | installments | affordable_with_plan | 1792.23 | 2024-09-07:802.88|2024-10-08:802.88|2024-11-08:802.88 | 2024-11-08 | 2489.35 | valid | installment_preferred |
| request_140 | not_recommended | not_affordable | 0 | none | — | 1549.24 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_141 | not_recommended | not_affordable | 31138.77 | none | — | 98438.77 | valid | not_affordable, no_feasible_candidate |
| request_142 | full_payment | affordable_now | 1263.6 | 2024-12-05:1263.6 | 2024-12-05 | 1923.4 | valid | sufficient_balance |
| request_143 | wait | affordable_later | 3327.96 | 2025-06-16:12584 | 2025-06-16 | 11498.48 | valid | waiting_for_income, minimum_balance_constraint, spending_change_required |
| request_144 | not_recommended | not_affordable | 0 | none | — | 376.57 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_145 | not_recommended | not_affordable | 27052.46 | none | — | 182452.46 | valid | not_affordable, no_feasible_candidate |
| request_146 | wait | affordable_later | 26160.38 | 2025-10-13:449400 | 2025-10-13 | 134760.38 | valid | waiting_for_income, minimum_balance_constraint |
| request_147 | not_recommended | not_affordable | 0 | none | — | 855.53 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_148 | installments | affordable_with_plan | 8038.8 | 2024-06-14:7710.56|2024-07-15:7710.56|2024-08-15:7710.56 | 2024-08-15 | 28038.8 | valid | installment_preferred |
| request_149 | installments | affordable_with_plan | 22823.29 | 2025-11-18:12706.03|2025-12-16:12706.03|2026-01-13:12706.03 | 2026-01-13 | 64923.29 | valid | installment_preferred |
| request_150 | installments | affordable_with_plan | 362.87 | 2026-01-06:171.98|2026-02-05:171.98|2026-03-07:171.98 | 2026-03-07 | 803.56 | valid | installment_preferred |
| request_151 | full_payment | affordable_now | 26999000 | 2024-09-03:26999000 | 2024-09-03 | 35347819.45 | valid | sufficient_balance |
| request_152 | installments | affordable_with_plan | 13185.27 | 2025-02-12:4812.43|2025-03-12:4812.43|2025-04-09:4812.43 | 2025-04-09 | 19478.18 | valid | installment_preferred |
| request_153 | not_recommended | not_affordable | 220 | none | — | 1620 | valid | not_affordable, no_feasible_candidate |
| request_154 | installments | affordable_with_plan | 1625.8 | 2024-12-04:563.61|2025-01-04:563.61|2025-02-04:563.61 | 2025-02-04 | 3098.79 | valid | installment_preferred |
| request_155 | full_payment | affordable_now | 112500 | 2025-05-06:112500 | 2025-05-06 | 79672.19 | valid | sufficient_balance |
| request_156 | wait | affordable_later | 9933.65 | 2026-06-13:43076 | 2026-06-13 | 36833.65 | valid | waiting_for_income, minimum_balance_constraint |
| request_157 | not_recommended | not_affordable | 5120935.81 | none | — | 20835035.81 | valid | not_affordable, no_feasible_candidate |
| request_158 | installments | affordable_with_plan | 242600 | 2025-08-07:84101.33|2025-09-04:84101.33|2025-10-02:84101.33 | 2025-10-02 | 138767.09 | valid | installment_preferred, spending_change_required |
| request_159 | not_recommended | not_affordable | 11556.06 | none | — | 20256.06 | valid | not_affordable, no_feasible_candidate |
| request_160 | installments | affordable_with_plan | 643.61 | 2024-06-13:432.05|2024-07-14:432.05|2024-08-14:432.05 | 2024-08-14 | 1411.56 | valid | installment_preferred |
| request_161 | not_recommended | not_affordable | 0 | none | — | 10543911.76 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_162 | not_recommended | not_affordable | 4404851.23 | none | — | 28565951.23 | valid | not_affordable, no_feasible_candidate |
| request_163 | installments | affordable_with_plan | 10805711.73 | 2024-09-10:6692053.33|2024-10-11:6692053.33|2024-11-11:6692053.33 | 2024-11-11 | 27876845.62 | valid | installment_preferred |
| request_164 | installments | affordable_with_plan | 27018000 | 2025-02-11:9366240|2025-03-11:9366240|2025-04-08:9366240 | 2025-04-08 | 52848767.88 | valid | installment_preferred |
| request_165 | full_payment | affordable_now | 80600 | 2026-04-06:80600 | 2026-04-06 | 97715.68 | valid | sufficient_balance |
| request_166 | installments | affordable_with_plan | 2907.6 | 2024-12-03:1007.97|2025-01-03:1007.97|2025-02-03:1007.97 | 2025-02-03 | 2470.98 | valid | installment_preferred |
| request_167 | not_recommended | not_affordable | 6674.78 | none | — | 37874.78 | valid | not_affordable, no_feasible_candidate |
| request_168 | partial_payment | affordable_with_plan | 38294.16 | 2026-01-07:38294.16|2026-01-14:11085.84 | 2026-01-14 | 114400 | valid | minimum_balance_constraint, deadline_constraint |
| request_169 | full_payment | affordable_now | 41976 | 2024-03-04:41976 | 2024-03-04 | 27247.5 | valid | sufficient_balance |
| request_170 | installments | affordable_with_plan | 31310765.13 | 2025-08-06:12804480|2025-09-03:12804480|2025-10-01:12804480 | 2025-10-01 | 36371275.49 | valid | installment_preferred |
| request_171 | not_recommended | not_affordable | 87.26 | none | — | 587.26 | valid | not_affordable, no_feasible_candidate |
| request_172 | installments | affordable_with_plan | 10200 | 2024-06-05:5304|2024-07-03:5304 | 2024-07-03 | 31133.98 | valid | installment_preferred |
| request_173 | installments | affordable_with_plan | 71958.49 | 2025-11-21:39173.33|2025-12-19:39173.33|2026-01-16:39173.33 | 2026-01-16 | 150609.17 | valid | installment_preferred |
| request_174 | installments | affordable_with_plan | 1146.2 | 2026-04-04:397.35|2026-05-04:397.35|2026-06-03:397.35 | 2026-06-03 | 883.71 | valid | installment_preferred |
| request_175 | full_payment | affordable_now | 2346.3 | 2024-09-06:2346.3 | 2024-09-06 | 1966.53 | valid | sufficient_balance |
| request_176 | not_recommended | not_affordable | 409.9 | none | — | 1009.9 | valid | not_affordable, no_feasible_candidate |
| request_177 | full_payment | affordable_now | 1017.6 | 2026-01-05:1017.6 | 2026-01-05 | 1618.81 | valid | sufficient_balance |
| request_178 | installments | affordable_with_plan | 2938.1 | 2024-12-07:1018.54|2025-01-07:1018.54|2025-02-07:1018.54 | 2025-02-07 | 1534.68 | valid | installment_preferred, spending_change_required |
| request_179 | not_recommended | not_affordable | 8092257.18 | none | — | 49523057.18 | valid | not_affordable, no_feasible_candidate |
| request_180 | not_recommended | not_affordable | 37838.8 | none | — | 75138.8 | valid | not_affordable, no_feasible_candidate |
| request_181 | not_recommended | not_affordable | 310.18 | none | — | 2310.18 | valid | not_affordable, no_feasible_candidate |
| request_182 | full_payment | affordable_now | 65714 | 2025-08-05:65714 | 2025-08-05 | 45696.29 | valid | sufficient_balance |
| request_183 | installments | affordable_with_plan | 24279648.97 | 2026-04-10:9313546.67|2026-05-10:9313546.67|2026-06-09:9313546.67 | 2026-06-09 | 22692418.8 | valid | installment_preferred |
| request_184 | not_recommended | not_affordable | 15825.25 | none | — | 126625.25 | valid | not_affordable, no_feasible_candidate |
| request_185 | wait | affordable_later | 470.2 | 2025-12-14:1257.3 | 2025-12-14 | 1540.9 | valid | waiting_for_income, minimum_balance_constraint |
| request_186 | wait | affordable_later | 13307.65 | 2026-01-14:26554 | 2026-01-14 | 23598.4 | valid | waiting_for_income, minimum_balance_constraint, spending_change_required |
| request_187 | wait | affordable_later | 44971.01 | 2024-10-13:187500 | 2024-10-13 | 161643.03 | valid | waiting_for_income, minimum_balance_constraint |
| request_188 | not_recommended | not_affordable | 258.33 | none | — | 1158.33 | valid | not_affordable, no_feasible_candidate |
| request_189 | full_payment | affordable_now | 488.4 | 2026-07-04:488.4 | 2026-07-04 | 509.95 | valid | sufficient_balance |
| request_190 | wait | affordable_later | 488.07 | 2024-12-15:2557.5 | 2024-12-15 | 2088.07 | valid | waiting_for_income, minimum_balance_constraint |
| request_191 | full_payment | affordable_now | 664.4 | 2025-05-03:664.4 | 2025-05-03 | 669.73 | valid | sufficient_balance |
| request_192 | not_recommended | not_affordable | 225.43 | none | — | 1225.43 | valid | not_affordable, no_feasible_candidate |
| request_193 | installments | affordable_with_plan | 133.35 | 2024-03-21:420.23|2024-04-21:420.23|2024-05-22:420.23 | 2024-05-22 | 1133.35 | valid | installment_preferred |
| request_194 | not_recommended | not_affordable | 0 | none | — | 45448.17 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_195 | installments | affordable_with_plan | 1074.03 | 2026-01-09:405.74|2026-02-08:405.74|2026-03-10:405.74 | 2026-03-10 | 1121.22 | valid | installment_preferred |
| request_196 | full_payment | affordable_now | 762.3 | 2024-06-03:762.3 | 2024-06-03 | 693.86 | valid | sufficient_balance |
| request_197 | not_recommended | not_affordable | 8831311.78 | none | — | 35077211.78 | valid | not_affordable, no_feasible_candidate |
| request_198 | full_payment | affordable_now | 185800 | 2026-07-07:185800 | 2026-07-07 | 175909.41 | valid | sufficient_balance |
| request_199 | installments | affordable_with_plan | 23674000 | 2024-09-07:8206986.67|2024-10-08:8206986.67|2024-11-08:8206986.67 | 2024-11-08 | 133162866.57 | valid | installment_preferred |
| request_200 | full_payment | affordable_now | 21717000 | 2025-02-06:21717000 | 2025-02-06 | 26510224.62 | valid | sufficient_balance |
| request_201 | full_payment | affordable_now | 23997000 | 2026-04-03:23997000 | 2026-04-03 | 50895016.8 | valid | sufficient_balance |
| request_202 | full_payment | affordable_now | 123900 | 2024-12-05:123900 | 2024-12-05 | 169039.01 | valid | sufficient_balance |
| request_203 | not_recommended | not_affordable | 1017.81 | none | — | 2417.81 | valid | not_affordable, no_feasible_candidate |
| request_204 | not_recommended | not_affordable | 0 | none | — | -162.18 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_205 | full_payment | affordable_now | 10621000 | 2024-03-06:10621000 | 2024-03-06 | 16000780.14 | valid | sufficient_balance |
| request_206 | installments | affordable_with_plan | 1404.7 | 2025-08-03:486.96|2025-08-31:486.96|2025-09-28:486.96 | 2025-09-28 | 1188.58 | valid | installment_preferred |
| request_207 | wait | affordable_later | 6737.41 | 2026-07-15:11830 | 2026-07-15 | 20337.41 | valid | waiting_for_income, minimum_balance_constraint |
| request_208 | wait | affordable_later | 3420221.72 | 2024-06-14:4413000 | 2024-06-14 | 13186313.35 | valid | waiting_for_income, minimum_balance_constraint |
| request_209 | not_recommended | not_affordable | 2204.53 | none | — | 20604.53 | valid | not_affordable, no_feasible_candidate |
| request_210 | partial_payment | affordable_with_plan | 948.61 | 2026-04-06:948.61|2026-04-14:411.41 | 2026-04-14 | 2000 | valid | minimum_balance_constraint, deadline_constraint |
| request_211 | wait | affordable_later | 247.48 | 2024-09-14:1788.6 | 2024-09-14 | 1747.48 | valid | waiting_for_income, minimum_balance_constraint |
| request_212 | not_recommended | not_affordable | 0 | none | — | -39143072.99 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_213 | installments | affordable_with_plan | 3362.4 | 2026-01-21:1165.63|2026-02-20:1165.63|2026-03-22:1165.63 | 2026-03-22 | 2919.23 | valid | installment_preferred |
| request_214 | installments | affordable_with_plan | 69750 | 2024-12-04:36270|2025-01-01:36270 | 2025-01-01 | 218507.16 | valid | installment_preferred |
| request_215 | installments | affordable_with_plan | 29986 | 2025-05-09:10395.15|2025-06-06:10395.15|2025-07-04:10395.15 | 2025-07-04 | 20057.81 | valid | installment_preferred |
| request_216 | wait | affordable_later | 705.78 | 2026-08-14:3332.4 | 2026-08-14 | 2505.78 | valid | waiting_for_income, minimum_balance_constraint |
| request_217 | installments | affordable_with_plan | 18800.52 | 2024-03-19:12889.07|2024-04-19:12889.07|2024-05-20:12889.07 | 2024-05-20 | 45600.52 | valid | installment_preferred |
| request_218 | installments | affordable_with_plan | 28954404.85 | 2025-08-07:21195893.33|2025-09-04:21195893.33|2025-10-02:21195893.33 | 2025-10-02 | 42235711.52 | valid | installment_preferred |
| request_219 | not_recommended | not_affordable | 0 | none | — | 1000.81 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_220 | not_recommended | not_affordable | 103.43 | none | — | 1203.43 | valid | not_affordable, no_feasible_candidate |
| request_221 | full_payment | affordable_now | 109800 | 2025-11-03:109800 | 2025-11-03 | 103112.95 | valid | sufficient_balance |
| request_222 | full_payment | affordable_now | 34078 | 2026-01-05:34078 | 2026-01-05 | 36723.65 | valid | sufficient_balance |
| request_223 | full_payment | affordable_now | 898.7 | 2024-09-07:898.7 | 2024-09-07 | 1049.95 | valid | sufficient_balance |
| request_224 | installments | affordable_with_plan | 10327000 | 2025-02-04:5370040|2025-03-04:5370040 | 2025-03-04 | 27841241.42 | valid | installment_preferred |
| request_225 | installments | affordable_with_plan | 10181867.14 | 2026-07-20:7647120|2026-08-19:7647120|2026-09-18:7647120 | 2026-09-18 | 21737081.27 | valid | installment_preferred |
| request_226 | full_payment | affordable_now | 157000 | 2024-12-03:157000 | 2024-12-03 | 245201.67 | valid | sufficient_balance |
| request_227 | not_recommended | not_affordable | 12595.85 | none | — | 75495.85 | valid | not_affordable, no_feasible_candidate |
| request_228 | not_recommended | not_affordable | 0 | none | — | -7993386.91 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_229 | installments | affordable_with_plan | 414.58 | 2024-03-18:529.29|2024-04-18:529.29|2024-05-19:529.29 | 2024-05-19 | 1167.96 | valid | installment_preferred |
| request_230 | full_payment | affordable_now | 3537.6 | 2025-08-06:3537.6 | 2025-08-06 | 3995.61 | valid | sufficient_balance |
| request_231 | installments | affordable_with_plan | 34787.96 | 2026-01-06:12378.08|2026-02-05:12378.08|2026-03-07:12378.08 | 2026-03-07 | 46709.88 | valid | installment_preferred |
| request_232 | not_recommended | not_affordable | 0 | none | — | -438.87 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_233 | not_recommended | not_affordable | 0 | none | — | -1586361.38 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_234 | wait | affordable_later | 318.97 | 2026-08-14:1213.3 | 2026-08-14 | 1018.97 | valid | waiting_for_income, minimum_balance_constraint |
| request_235 | full_payment | affordable_now | 967.2 | 2024-09-06:967.2 | 2024-09-06 | 890.67 | valid | sufficient_balance |
| request_236 | not_recommended | not_affordable | 6900019.57 | none | — | 23668619.57 | valid | not_affordable, no_feasible_candidate |
| request_237 | full_payment | affordable_now | 23826000 | 2026-04-05:23826000 | 2026-04-05 | 23629181.59 | valid | sufficient_balance |
| request_238 | installments | affordable_with_plan | 663.6 | 2024-12-07:230.05|2025-01-07:230.05|2025-02-07:230.05 | 2025-02-07 | 1434.53 | valid | installment_preferred |
| request_239 | not_recommended | not_affordable | 0 | none | — | 357.31 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_240 | not_recommended | not_affordable | 0 | none | — | 4208.74 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_241 | installments | affordable_with_plan | 21052000 | 2024-03-17:7298026.67|2024-04-17:7298026.67|2024-05-18:7298026.67 | 2024-05-18 | 35239964.77 | valid | installment_preferred |
| request_242 | not_recommended | not_affordable | 0 | none | — | 64.75 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_243 | full_payment | affordable_now | 17468 | 2026-07-07:17468 | 2026-07-07 | 24599.21 | valid | sufficient_balance |
| request_244 | not_recommended | not_affordable | 12470.58 | none | — | 58370.58 | valid | not_affordable, no_feasible_candidate |
| request_245 | wait | affordable_later | 43120.36 | 2025-12-14:128500 | 2025-12-14 | 119602.48 | valid | waiting_for_income, minimum_balance_constraint |
| request_246 | installments | affordable_with_plan | 64086 | 2026-04-03:22216.48|2026-05-03:22216.48|2026-06-02:22216.48 | 2026-06-02 | 46565.03 | valid | installment_preferred |
| request_247 | full_payment | affordable_now | 1059.3 | 2024-09-05:1059.3 | 2024-09-05 | 1395.25 | valid | sufficient_balance |
| request_248 | partial_payment | affordable_with_plan | 955.7 | 2025-02-07:955.7|2025-04-15:1009.9 | 2025-04-15 | 1300 | valid | minimum_balance_constraint, deadline_constraint |
| request_249 | wait | affordable_later | 173.22 | 2026-03-15:643.2 | 2026-03-15 | 637.66 | valid | waiting_for_income, minimum_balance_constraint |
| request_250 | not_recommended | not_affordable | 17404.9 | none | — | 52704.9 | valid | not_affordable, no_feasible_candidate |
| request_251 | not_recommended | not_affordable | 119.63 | none | — | 1419.63 | valid | not_affordable, no_feasible_candidate |
| request_252 | wait | affordable_later | 6643701.89 | 2026-08-14:28082000 | 2026-08-14 | 21795901.89 | valid | waiting_for_income, minimum_balance_constraint |
| request_253 | installments | affordable_with_plan | 1444.71 | 2024-03-21:984.6|2024-04-21:984.6|2024-05-22:984.6 | 2024-05-22 | 2618.78 | valid | installment_preferred |
| request_254 | wait | affordable_later | 1057.65 | 2025-09-13:3535.2 | 2025-09-13 | 3526.51 | valid | waiting_for_income, minimum_balance_constraint |
| request_255 | full_payment | affordable_now | 3345000 | 2026-04-06:3345000 | 2026-04-06 | 14589713.3 | valid | sufficient_balance |
| request_256 | not_recommended | not_affordable | 45481.49 | none | — | 214081.49 | valid | not_affordable, no_feasible_candidate |
| request_257 | wait | affordable_later | 593.01 | 2025-11-14:1352.4 | 2025-11-14 | 2193.01 | valid | waiting_for_income, minimum_balance_constraint |
| request_258 | full_payment | affordable_now | 1113.6 | 2026-01-07:1113.6 | 2026-01-07 | 1337.97 | valid | sufficient_balance |
| request_259 | wait | affordable_later | 482.9 | 2024-10-14:935 | 2024-10-14 | 961.3 | valid | waiting_for_income, minimum_balance_constraint |
| request_260 | partial_payment | affordable_with_plan | 9860377.76 | 2025-02-06:9860377.76|2025-03-16:42218622.24 | 2025-03-16 | 20727700 | valid | minimum_balance_constraint, deadline_constraint |
| request_261 | full_payment | affordable_now | 1830.4 | 2026-07-03:1830.4 | 2026-07-03 | 2025.03 | valid | sufficient_balance |
| request_262 | full_payment | affordable_now | 9236000 | 2024-12-05:9236000 | 2024-12-05 | 58029159.08 | valid | sufficient_balance |
| request_263 | not_recommended | not_affordable | 7523.47 | none | — | 31623.47 | valid | not_affordable, no_feasible_candidate |
| request_264 | wait | affordable_later | 22118.62 | 2026-06-13:111300 | 2026-06-13 | 81618.62 | valid | waiting_for_income, minimum_balance_constraint |
| request_265 | not_recommended | not_affordable | 0 | none | — | 183200.58 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_266 | installments | affordable_with_plan | 935 | 2025-08-03:324.13|2025-08-31:324.13|2025-09-28:324.13 | 2025-09-28 | 1151.48 | valid | installment_preferred |
| request_267 | installments | affordable_with_plan | 1732.18 | 2026-01-08:667.33|2026-02-07:667.33|2026-03-09:667.33 | 2026-03-09 | 2162.69 | valid | installment_preferred |
| request_268 | installments | affordable_with_plan | 1134.52 | 2024-06-14:841.22|2024-07-15:841.22|2024-08-15:841.22 | 2024-08-15 | 2534.52 | valid | installment_preferred |
| request_269 | not_recommended | not_affordable | 0 | none | — | 10626.41 | valid | not_affordable, no_feasible_candidate, natural_forecast_below_minimum |
| request_270 | not_recommended | not_affordable | 226.3 | none | — | 1626.3 | valid | not_affordable, no_feasible_candidate |
| request_271 | wait | affordable_later | 14333.18 | 2024-11-13:91300 | 2024-11-13 | 69769.88 | valid | waiting_for_income, minimum_balance_constraint |
| request_272 | installments | affordable_with_plan | 6714556.95 | 2025-02-12:4709466.67|2025-03-12:4709466.67|2025-04-09:4709466.67 | 2025-04-09 | 9513690.28 | valid | installment_preferred |
| request_273 | partial_payment | affordable_with_plan | 9192347.08 | 2026-04-07:9192347.08|2026-04-14:6668652.92 | 2026-04-14 | 18774600 | valid | minimum_balance_constraint, deadline_constraint |
| request_274 | installments | affordable_with_plan | 2384.12 | 2024-12-04:940.75|2025-01-04:940.75|2025-02-04:940.75 | 2025-02-04 | 3243.37 | valid | installment_preferred |
| request_275 | full_payment | affordable_now | 15884000 | 2025-05-06:15884000 | 2025-05-06 | 14349959.94 | valid | sufficient_balance |
