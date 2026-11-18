# Repository Reconnaissance Report
## HackerRank Orchestrate October 2026 — Ghost Data Still Exists

---

## 1. Challenge Summary

Build an AI-powered **deletion-audit agent** for a fictitious commerce platform called Northstar Shop.

For each of 518 deletion requests the agent must:
1. **Determine intent** — does `request_text` actually authorize deletion? If not → `NOT_APPLICABLE`.
2. **Resolve identity** — map the supplied email to a `user_id` via current and historical identifiers.
3. **Reconstruct state at `audit_at`** — search all evidence sources; treat reported workflow statuses as claims only.
4. **Apply deletion policy** (`deletion_rules.csv`) — determines whether each record should be deleted, redacted, anonymized, retained, or tombstoned.
5. **Emit `steps_json`** — an ordered JSON array of FINDING → REMEDIATION → VERIFICATION steps, each with 7 exact fields.
6. **Set `deletion_status`** — `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.

The central challenge: deletion workflows may report "Complete" while data persists in replicas, search indexes, logs, exports, backups, analytics, and support attachments. Sync/restore processes can also recreate previously deleted data.

---

## 2. Repository Map

| Path | Purpose |
|---|---|
| [`AGENTS.md`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/AGENTS.md) | **Single source of truth** for agent behavior. Defines logging contract, project contract (§6), allowed operations, step schema, evaluation requirements, and submission artifacts. |
| [`README.md`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/README.md) | Participant-facing quick-start. Matches AGENTS.md §6. Adds packaging instructions and a pre-submission checklist. |
| [`problem_statement.md`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/problem_statement.md) | Narrative framing + condensed spec. Fully consistent with AGENTS.md. |
| [`agent_trace_instructions.md`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/agent_trace_instructions.md) | How to package and submit the Antigravity trace (`transcript.jsonl`). |
| [`CLAUDE.md`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/CLAUDE.md) | One-liner `@AGENTS.md` — redirects Claude to AGENTS.md. |
| [`code/main.py`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code/main.py) | **Empty stub** — 0 bytes. Entry point we must fill. |
| [`code/evaluation/main.py`](file:///g:/coding/HackerRank-Orchestrate/october/hackerrank-orchestrate-october26/code/evaluation/main.py) | **Empty stub** — 0 bytes. Evaluation entry point placeholder. |
| `dataset/deletion_requests.csv` | 518 evaluation cases (case_33 → case_550+). Input to our solution. |
| `dataset/sample_deletion_requests.csv` | 32 sample cases (case_01 → case_32) with known correct outputs. |
| `dataset/sample_output.csv` | **Ground-truth answers for the 32 samples**. Primary format reference. |
| `dataset/output.csv` | Blank template (header only). Final output goes to `output.csv` at **repo root**. |
| `dataset/user_identities.csv` | 851 users: `user_id, name, email, phone, email_hash, updated_at`. |
| `dataset/user_audit_log.csv` | 307 rows of identity field changes: `audit_id, user_id, event_time, field_name, old_value, new_value`. |
| `dataset/system_activity.csv` | 4012 rows: `activity_id, event_time, event_type, source_system, target_system, resource_id, reported_result, details`. |
| `dataset/deletion_rules.csv` | 15 policy rules defining required treatment per data category. |
| `dataset/evidence_files.csv` | 94 evidence files mapped by `file_id → path + origin + captured_at`. |
| `dataset/evidence/databases/` | 24 `.sql` files (SQLite-compatible snapshots: primary, read replica, reporting replica, failover replica, inventory, search). |
| `dataset/evidence/documents/` | 4 PDFs (account history, legal retention register, security retention extract, support attachment). |
| `dataset/evidence/images/` | 11 PNGs (admin console screenshots — OCR needed). |
| `dataset/evidence/logs/` | 26 log files (application traces, cloud runtime exports, service events, syslogs, resource lookup traces, notification delivery, search diagnostics, support replica). |
| `dataset/evidence/records/` | 29 structured records (JSON snapshots, export manifests, analytics reports, connector configs, handover docs, security audit ledger, service resource exports). |

---

## 3. Exact Input/Output Contract

### Input (`deletion_requests.csv`)
```
case_id, email, requested_at, reported_status, reported_at, audit_at, request_text
```
- `reported_status` values: `COMPLETE`, `PARTIALLY_COMPLETE`, `NOT_STARTED` — all are **claims only**.
- `request_text` may be in any language. Must be interpreted to determine deletion intent.
- Emails may be **uppercase** (e.g., `SIPHO.MOKOENA@GMAIL.COM`) — case-insensitive matching required.

### Output (`output.csv` at repo root)
```
case_id,deletion_status,steps_json
```
- Exactly **518 data rows** sorted by `case_id`.
- `deletion_status`: `COMPLETE`, `INCOMPLETE`, or `NOT_APPLICABLE`.
- `steps_json`: Valid JSON array. **Array order matters**; key order and whitespace do not.

### Step Schema (7 fields, all required)
```json
{
  "step_no": 1,
  "phase": "FINDING",
  "system_id": "account_service",
  "resource_id": "account_005",
  "operation": "REPORT_REMAINING_RECORD",
  "state": "PRESENT",
  "evidence_id": "evidence_01"
}
```

### Allowed Operations (confirmed from AGENTS.md §6.4 and problem_statement.md)

| Phase | Operation | State |
|---|---|---|
| FINDING | REPORT_REMAINING_RECORD | PRESENT |
| FINDING | REPORT_EXPOSED_PII | PRESENT |
| FINDING | REPORT_ACTIVE_DATA_FLOW | ACTIVE |
| FINDING | REPORT_RESTORE_RISK | ACTIVE |
| REMEDIATION | DISABLE_DATA_FLOW | DISABLED |
| REMEDIATION | BLOCK_RESTORE | BLOCKED |
| REMEDIATION | DELETE_RECORD | ABSENT |
| REMEDIATION | REDACT_RECORD | REDACTED |
| REMEDIATION | ANONYMIZE_RECORD | ANONYMIZED |
| VERIFICATION | VERIFY_RECORD_ABSENT | ABSENT |
| VERIFICATION | VERIFY_RECORD_PRESENT | PRESENT |
| VERIFICATION | VERIFY_RECORD_REDACTED | REDACTED |
| VERIFICATION | VERIFY_RECORD_ANONYMIZED | ANONYMIZED |
| VERIFICATION | VERIFY_DATA_FLOW_DISABLED | DISABLED |
| VERIFICATION | VERIFY_RESTORE_BLOCKED | BLOCKED |

### Ordering Rules (confirmed from README.md)
1. Phase order: FINDING → REMEDIATION → VERIFICATION.
2. Within phase: operation order as in the table above.
3. Then: `system_id` ascending, then `resource_id` ascending.
4. Within remediation: disable data flows and block restores **before** changing dependent records; downstream copies before source records when dependency requires it.

### Evidence ID Rules
- FINDING steps and COMPLETE-case VERIFICATION steps: **must cite** `file_id`, `activity_id`, or `audit_id`.
- Proposed REMEDIATION steps and post-remediation VERIFICATION steps (INCOMPLETE cases): `evidence_id` = `""` (empty string).

### NOT_APPLICABLE
```csv
case_000,NOT_APPLICABLE,[]
```

---

## 4. Dataset and Evidence

### Scale
| File | Rows |
|---|---|
| `deletion_requests.csv` | 518 cases (case_33–case_550+) |
| `sample_deletion_requests.csv` | 32 cases (case_01–case_32) |
| `user_identities.csv` | 851 users |
| `user_audit_log.csv` | 307 identity-change events |
| `system_activity.csv` | 4,012 activity rows |
| `evidence_files.csv` | 94 evidence files |
| Total evidence files | 94 (24 SQL + 4 PDF + 11 PNG + 26 logs + 29 JSON/txt records) |

### Identity Resolution Complexity
- `user_identities.csv` has current state. `user_audit_log.csv` tracks field changes (email, phone, etc.).
- Requests may supply an **old email** — must look up historical values.
- Some emails are uppercased in requests → case-insensitive matching required.

### Evidence Linking
- Evidence manifest (`evidence_files.csv`) does NOT map files to cases. The solution must link evidence by matching identifiers (email, user_id, email_hash, resource_id, etc.) found within file contents.
- `captured_at` timestamps are critical — evidence after `audit_at` must be excluded.
- SQL files: multiple replica types (primary, read, reporting, failover, inventory, search) — replication lag/drift is intentional and must be detected.
- Images (11 PNGs): admin console screenshots requiring OCR or vision-model extraction.
- PDFs (4): legal retention register, security retention extract, account history report, support attachment.

### Deletion Rules (15 rules confirmed)
| rule_id | Category | Condition | Action |
|---|---|---|---|
| rule_01 | USER_PROFILE | Always | DELETE |
| rule_02 | SECONDARY_IDENTIFIER | Always | DELETE |
| rule_03 | SEARCH_INDEX_ENTRY | Always | DELETE |
| rule_04 | CACHE_ENTRY | Always | DELETE |
| rule_05 | SUPPORT_MESSAGE | Shared context must be retained | REDACT |
| rule_06 | SUPPORT_ATTACHMENT | Belongs only to subject | DELETE |
| rule_07 | ANALYTICS_PROFILE | Still attributable | ANONYMIZE |
| rule_08 | PRODUCT_TELEMETRY | Still attributable | ANONYMIZE |
| rule_09 | USER_EXPORT | Always | DELETE |
| rule_10 | MARKETING_PROFILE | Always | DELETE |
| rule_11 | EMAIL_DELIVERY_LOG | Contains user email | REDACT |
| rule_12 | SECURITY_AUDIT_LOG | Within retention period | RETAIN |
| rule_13 | LEGAL_HOLD_RECORD | Active legal hold | RETAIN |
| rule_14 | BACKUP_ARCHIVE | Restore access can be blocked | RETAIN (block restore) |
| rule_15 | ACCOUNT_TOMBSTONE | Deleted account, only user_id needed | REDACT (remove name/email/phone/hash) |

### Observed System IDs in Sample Outputs
`account_service`, `search_service`, `support_platform`, `analytics_platform`, `security_service`, `export_service`, `integration_service`, `backup_service`, `identity_service`

---

## 5. Existing Implementation

### What Exists
- `code/main.py` — **empty** (0 bytes).
- `code/evaluation/main.py` — **empty** (0 bytes).
- No `requirements.txt`, no `pyproject.toml`, no dependency files of any kind.
- No tests, no evaluation scripts, no evaluation reports.
- `dataset/output.csv` — header row only (blank template).
- `.git/` — standard git repo, no branches beyond main visible.

### What Is Missing (Everything)
- All solution code.
- Dependency manifest (`requirements.txt`).
- `code/evaluation/evaluation_report.md` (required for submission).
- `code/evaluation/usage_report.md` (required for submission).
- `output.csv` at repo root (final submission artifact).
- `log.txt` (required by AGENTS.md §2).

---

## 6. Architecture Assessment

### Does the Five-Agent LangGraph Plan Fit?

**Broadly yes, with refinements needed.**

| Our Plan | Assessment |
|---|---|
| Manager Agent (intent + routing) | ✅ Needed. Must handle multilingual `request_text` → deletion/non-deletion classification. |
| Identity Agent | ✅ Needed. Must resolve historical emails via `user_audit_log`, handle uppercase/case variants. |
| Evidence Agent | ✅ Needed but complex. Must handle 94 files across 5 formats, including OCR for images and SQL execution. |
| Policy Agent | ✅ Fits. Deterministic rule application from 15 rules is a good candidate for pure Python logic. |
| Audit Agent | ✅ Valuable for checking evidence sufficiency and step completeness. |

**Recommended Adjustments:**

1. **Decouple heavy file-reading from LLM reasoning.** SQL files, JSON records, and log files should be parsed with Python tools; only the interpreted findings should be passed to the LLM. PNG/PDF files require vision model or OCR.
2. **Pre-build indexes.** Load `user_identities.csv`, `user_audit_log.csv`, `system_activity.csv`, and `evidence_files.csv` into memory-indexed structures at startup. Do not re-read CSVs per case.
3. **Filter evidence by timestamp before sending to LLM.** Only evidence captured at or before `audit_at` is valid per case.
4. **Consider batching similar cases.** 518 cases with 94 potential evidence files each could be very expensive. Cases sharing the same user_id can share identity lookups; cases near the same `audit_at` may share evidence sets.
5. **Gemini free-tier quota is a real constraint.** RPM and TPM limits may require retry logic, exponential backoff, and possibly batching multiple short prompts.
6. **OCR/vision calls.** 11 PNG screenshots require Gemini Vision or another OCR solution. Only use for cases where the relevant file's `captured_at` ≤ `audit_at`.

---

## 7. Risks and Unresolved Questions

> Items marked **⚠ NEEDS YOUR DECISION** require your input before we design those components.

### High-Priority Risks
1. **Scale vs. quota cost.** 518 cases × multiple LLM calls each = potentially thousands of calls. With Gemini free tier (15 RPM / 1M TPM for Flash), processing 518 cases naively could take hours. **⚠ Will you use a paid API tier, or do we need aggressive caching/batching for free tier?**
2. **Image evidence (11 PNGs).** Requires vision-capable model or OCR. **⚠ Should we use Gemini Vision (multimodal), a separate OCR library like pytesseract/easyocr, or skip image evidence initially?**
3. **PDF evidence (4 PDFs).** Requires PDF text extraction (e.g., `pdfplumber` or `pypdf`). Confirm approach.
4. **NOT_APPLICABLE detection.** The sample has no `NOT_APPLICABLE` cases among the 32 samples, so we have no ground-truth example to validate against. We must infer the classification boundary from request text alone. Requests for "access", "correction", "export", "marketing opt-out" → NOT_APPLICABLE.
5. **Ordering determinism.** The grader checks array order. The within-phase ordering rule (operation order → system_id → resource_id) must be implemented exactly. Observed in samples: DISABLE_DATA_FLOW before DELETE_RECORD, BLOCK_RESTORE before DELETE.
6. **Evidence linking with no manifest-to-case mapping.** The agent must scan file contents to find identifiers. With 94 files and 518 cases, brute-force is expensive. **Need a strategy**: pre-index all evidence files on startup, build inverted index of identifiers → file_ids.

### Medium-Priority Risks
7. **Temporal filtering.** Evidence captured after `audit_at` must not influence findings. The `captured_at` field in `evidence_files.csv` is the gate.
8. **Replication drift in SQL files.** A record may be absent from the primary but present in a replica (or vice versa). The audit must detect this as a remaining record or recreation risk.
9. **`reported_status` is not proof.** Many sample cases show COMPLETE status but INCOMPLETE audit result (e.g., case_05, case_06, case_12). Our logic must never trust this field.
10. **ACCOUNT_TOMBSTONE vs. DELETE distinction.** rule_15 says keep `user_id` but redact PII; rule_01 says delete USER_PROFILE. The tombstone behavior requires distinguishing "deleted account with stable internal reference retained" from "account fully deleted". Cases 31 and 32 in the sample demonstrate this.
11. **Email case sensitivity.** `deletion_requests.csv` contains uppercase emails (e.g., `SIPHO.MOKOENA@GMAIL.COM`). `user_identities.csv` stores lowercase. Must normalize before lookup.

### Low-Priority / Clarifications
12. **`system_id` naming consistency.** We must use exactly the system names that appear in evidence content (e.g., `account_service`, not `account-service`). Cross-referencing sample output is the guide.
13. **`log.txt` requirement.** AGENTS.md §2-§5 requires a `log.txt` in the repo root with session-start and per-turn entries. This is a submission artifact (`chat_transcript`). We need to maintain it.
14. **No `NOT_APPLICABLE` sample.** We cannot validate our non-deletion classifier against ground truth without creating a synthetic test case ourselves.

---

## 8. Proposed Implementation Milestones

Each milestone is independently testable and requires your explicit approval before implementation.

---

### Milestone 0: Log Initialization *(tiny, required by AGENTS.md)*
**Scope:** Create `log.txt` in the repo root with a SESSION START entry per AGENTS.md §5.1.  
**Test:** File exists, has correct format.  
**Dependency:** None.

---

### Milestone 1: Dataset Loader + Identity Resolver
**Scope:**
- Load all CSV files into structured Python objects.
- Build email → user_id index (case-insensitive, current + historical via `user_audit_log`).
- Unit test: resolve all 32 sample request emails to their user_ids; confirm no failures.

**Test:** Match all 32 sample emails to expected user_ids (verifiable against sample output resource_ids, e.g., `account_001` → `user_01`).  
**Tools used:** Python standard library (csv, json). No LLM.

---

### Milestone 2: Deletion Intent Classifier
**Scope:**
- Gemini API call: classify `request_text` as `DELETION_REQUEST` or `NOT_APPLICABLE`.
- Handle multilingual text (Japanese, French, Spanish confirmed in samples).
- Return `NOT_APPLICABLE` with `steps_json=[]` immediately for non-deletion requests.

**Test:** Run against 32 samples; all should be `DELETION_REQUEST` (none are NOT_APPLICABLE in samples). Also manually create 2-3 NOT_APPLICABLE test cases.  
**Tools used:** Gemini API (text, flash model).

---

### Milestone 3: Evidence Pre-Indexer
**Scope:**
- Parse all 94 evidence files at startup into an in-memory index: `identifier → [(file_id, captured_at, content_fragment)]`.
- Identifiers to index: user_id, email (all variants), phone, email_hash, account_*, search_*, analytics_*, support_*, export_*, backup_*, data_flow_*, tombstone_*, audit_record_*.
- SQL files: execute with SQLite in-memory, extract relevant rows.
- JSON/text/log files: parse and extract identifier-containing lines.
- PDFs: extract text with `pdfplumber` or `pypdf`.
- PNGs: defer to Milestone 5 (vision/OCR).

**Test:** For each sample case user, confirm relevant evidence files are indexed and retrievable.  
**Tools used:** Python (sqlite3, json, re, pdfplumber or pypdf). No LLM.

---

### Milestone 4: Deterministic Policy Engine
**Scope:**
- Given a list of found records + their data categories, apply `deletion_rules.csv` to produce required actions.
- Encode the 15 rules as pure Python logic (no LLM needed).
- Implement step ordering: operation order → system_id → resource_id.
- Implement remediation dependency ordering (disable/block before delete/redact; downstream before source).

**Test:** Unit tests against all 15 rules; validate step ordering against sample outputs.  
**Tools used:** Python only.

---

### Milestone 5: Evidence Agent (Core Investigation Loop)
**Scope:**
- For a given `user_id` + `audit_at`: retrieve all relevant evidence items with `captured_at ≤ audit_at`.
- Determine which records still exist (present) and which have been deleted.
- Identify active data flows and restore risks from `system_activity.csv` + evidence.
- For image evidence: call Gemini Vision or apply OCR to extract data.
- Return a structured list of findings: `[(system_id, resource_id, data_category, state, evidence_id)]`.

**Test:** Manually verify findings for 5 sample cases against sample_output.csv.  
**Tools used:** Gemini API (vision for PNGs), Python (sqlite3, log parsing, JSON parsing).

---

### Milestone 6: LangGraph Workflow Assembly
**Scope:**
- Wire Milestones 1–5 into a LangGraph graph with typed shared state.
- Nodes: Manager → Identity → Evidence → Policy → Audit → Output.
- Conditional routing: NOT_APPLICABLE short-circuits; Audit node can route back to Evidence for one correction round.
- Iteration limits and retry budgets.
- Produce `steps_json` from findings + policy decisions.

**Test:** Run against all 32 sample cases; compare `deletion_status` and `steps_json` to `sample_output.csv`.  
**Tools used:** LangGraph, Gemini API, Python.

---

### Milestone 7: Full Dataset Run + Validation
**Scope:**
- Run against all 518 cases in `deletion_requests.csv`.
- Write `output.csv` to repo root.
- Validate: 518 rows, sorted by `case_id`, valid JSON in `steps_json`, step numbering consecutive, evidence_id rules obeyed.

**Test:** Automated validator script checking all output constraints.  
**Tools used:** Python.

---

### Milestone 8: Evaluation Reports
**Scope:**
- `code/evaluation/evaluation_report.md`: case-level accuracy on 32 samples, step-level metrics, sequence accuracy, 3+ custom test cases, failures and improvements.
- `code/evaluation/usage_report.md`: model calls, input/output tokens, estimated cost for full run.

**Test:** Files exist, are non-empty, contain all required sections.  
**Dependency:** Milestone 7 must be complete.

---

### Milestone 9: Submission Packaging
**Scope:**
- `code.zip` (code + README + evaluation/ reports, no dataset, no venv).
- `output.csv` at repo root.
- Pre-submission checklist verification (from README.md).

**Test:** Unzip and confirm structure; run `python3 code/main.py` fresh.

---

*Report generated: 2026-10-25. All findings are from direct file inspection of the cloned repository. No assumptions have been made about hidden test data or organizer-only files.*
