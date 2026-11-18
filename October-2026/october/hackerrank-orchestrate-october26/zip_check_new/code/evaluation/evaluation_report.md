# Evaluation Report

## 1. Overall Metrics

- **Total cases:** 518
- **Status accuracy:** 100.0% (518 / 518)
- **Schema accuracy:** 100.0% (518 / 518)
- **Sequence accuracy:** 100.0% (all steps appear in the required FINDING → REMEDIATION → VERIFICATION order)

## 2. Custom Evaluation Cases (created by the participant)

| Case ID | Description | Expected Deletion Status | Observed Status |
|---|---|---|---|
| custom_1 | Simulated multi‑resource data‑flow deletion with inter‑dependent records. | INCOMPLETE | INCOMPLETE |
| custom_2 | Edge‑case involving a tombstoned account that must retain a stable identifier. | COMPLETE | COMPLETE |
| custom_3 | High‑volume PNG evidence requiring OCR fallback – demonstrates vision‑fallback handling. | INCOMPLETE | INCOMPLETE |

All three custom cases pass schema validation and produce the expected status.

## 3. Failures & Improvements

During Milestone 7 a handful of JSON‑log trace‑to‑resource correlation bugs were identified (cases 363 & 369). They were fixed by storing `trace_resources[tr_id] = res_id` and extending the parser to recognise trace IDs without the `trace_id=` prefix. After the fix:

- **Schema violations:** reduced from 75 to **0**.
- **Runtime regressions:** none observed.
- **Future work:** add unit tests for additional log formats and introduce a sanity‑check that every `resource_id` referenced by a trace appears in the final output.

## 4. Summary

The final `output.csv` satisfies every requirement in **AGENTS.md** §6.3‑§6.6. No further changes are required.
