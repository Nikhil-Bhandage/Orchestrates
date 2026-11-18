"""
main.py -- CLI Entry Point for Deletion Audit Agent
Milestone 6: Supports single case execution, sample set benchmark evaluation,
and production full dataset evaluation writing to output.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = REPO_ROOT / "code"
DATASET_DIR = REPO_ROOT / "dataset"
OUTPUT_CSV = REPO_ROOT / "output.csv"

if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from data_loader import load_all_datasets
from workflow import audit_single_case, get_global_bundle_and_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")


def evaluate_sample_benchmark() -> Dict[str, Any]:
    """
    Runs the LangGraph workflow on all 32 sample cases and compares predictions
    with dataset/sample_output.csv.
    Reports:
      - Status accuracy
      - Schema validity
      - Resource coverage differences
      - Operation mismatches
      - Evidence citation differences
      - Remediation ordering errors
    """
    bundle, index = get_global_bundle_and_index()
    sample_out_file = DATASET_DIR / "sample_output.csv"

    if not sample_out_file.exists():
        raise FileNotFoundError(f"Sample output file not found at {sample_out_file}")

    expected_map: Dict[str, Dict[str, Any]] = {}
    with sample_out_file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            expected_map[r["case_id"]] = {
                "deletion_status": r["deletion_status"],
                "steps_json": r["steps_json"],
                "steps": json.loads(r["steps_json"]),
            }

    results = []
    status_matches = 0
    schema_valid_count = 0
    total = len(bundle.sample_requests)

    logger.info("Starting benchmark evaluation across %d sample cases...", total)
    start_time = time.time()

    for req in bundle.sample_requests:
        cid = req.case_id
        exp = expected_map.get(cid)
        if not exp:
            continue

        try:
            state = audit_single_case(cid, bundle=bundle, index=index)
            pred_status = state.get("deletion_status", "UNKNOWN")
            pred_steps_json = state.get("steps_json", "[]")

            # Validate schema
            try:
                parsed_steps = json.loads(pred_steps_json)
                schema_valid = isinstance(parsed_steps, list)
                for s in parsed_steps:
                    assert "step_no" in s and "phase" in s and "system_id" in s
                    assert "resource_id" in s and "operation" in s and "state" in s
                    assert "evidence_id" in s
            except Exception:
                schema_valid = False

            if schema_valid:
                schema_valid_count += 1

            status_ok = (pred_status == exp["deletion_status"])
            if status_ok:
                status_matches += 1

            # Semantic comparison on steps
            exp_steps = exp["steps"]
            exp_resources = {(s["system_id"], s["resource_id"]) for s in exp_steps}
            pred_resources = {(s["system_id"], s["resource_id"]) for s in parsed_steps} if schema_valid else set()

            exp_ops = [s["operation"] for s in exp_steps]
            pred_ops = [s["operation"] for s in parsed_steps] if schema_valid else []

            results.append({
                "case_id": cid,
                "status_match": status_ok,
                "pred_status": pred_status,
                "exp_status": exp["deletion_status"],
                "schema_valid": schema_valid,
                "exp_step_count": len(exp_steps),
                "pred_step_count": len(parsed_steps) if schema_valid else 0,
                "missing_resources": list(exp_resources - pred_resources),
                "extra_resources": list(pred_resources - exp_resources),
                "ops_match": (exp_ops == pred_ops),
            })
        except Exception as exc:
            logger.error("Sample case %s failed with exception: %s", cid, exc, exc_info=True)
            results.append({
                "case_id": cid,
                "status_match": False,
                "pred_status": "ERROR",
                "exp_status": exp["deletion_status"],
                "schema_valid": False,
                "error": str(exc),
            })

    elapsed = time.time() - start_time
    status_acc = status_matches / total if total else 0.0
    schema_acc = schema_valid_count / total if total else 0.0

    import llm_provider
    from evidence_agent import get_gemini_usage
    provider_usage = llm_provider.get_usage()
    ocr_usage = get_gemini_usage()

    mismatches = [r for r in results if not r["status_match"]]

    report = {
        "total_cases": total,
        "status_matches": status_matches,
        "status_accuracy": status_acc,
        "schema_valid_count": schema_valid_count,
        "schema_accuracy": schema_acc,
        "elapsed_seconds": round(elapsed, 2),
        "mismatches": mismatches,
        "provider_usage": provider_usage.to_dict(),
        "ocr_usage": ocr_usage.to_dict(),
        "case_details": results,
    }

    print("\n" + "=" * 60)
    print("SAMPLE BENCHMARK EVALUATION SUMMARY (32 Cases)")
    print("=" * 60)
    print(f"Total Cases:         {total}")
    print(f"Status Accuracy:     {status_acc:.1%} ({status_matches}/{total})")
    print(f"Schema Accuracy:     {schema_acc:.1%} ({schema_valid_count}/{total})")
    print(f"Elapsed Time:        {elapsed:.2f}s")
    print("-" * 60)
    print("LLM Provider Stats:")
    print(f"  Groq Calls:        {provider_usage.groq_calls} (Errors: {provider_usage.groq_errors})")
    print(f"  Gemini Text Calls: {provider_usage.gemini_calls} (Errors: {provider_usage.gemini_errors})")
    print(f"  Gemini Vision:     {provider_usage.vision_calls} (Errors: {provider_usage.vision_errors})")
    print(f"  Fallbacks:         {provider_usage.fallbacks_to_gemini}")
    print(f"  OCR Cache Hits:    {ocr_usage.cache_hits}")
    print("-" * 60)
    if mismatches:
        print(f"Remaining Mismatches ({len(mismatches)}):")
        for m in mismatches:
            print(f"  - {m['case_id']}: predicted={m['pred_status']}, expected={m['exp_status']}")
    else:
        print("Remaining Mismatches: 0 (All 32 sample cases match ground truth!)")
    print("=" * 60 + "\n")

    return report


def validate_output_file(output_path: Path) -> Dict[str, Any]:
    """
    Validates output.csv against all AGENTS.md §6.3–§6.6 requirements:
      - Exactly 518 rows
      - Ordered case_33 to case_550
      - Allowed statuses (COMPLETE, INCOMPLETE, NOT_APPLICABLE)
      - NOT_APPLICABLE -> steps_json == '[]'
      - COMPLETE -> only VERIFICATION steps citing non-empty evidence_id
      - INCOMPLETE -> FINDING (evidence_id != '') -> REMEDIATION (evidence_id == '') -> VERIFICATION (evidence_id == '')
      - Remediation ordering (data flow / restore block before mutations)
      - Exact 7 fields per step object
    """
    if not output_path.exists():
        raise FileNotFoundError(f"Output file {output_path} does not exist.")

    with output_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ["case_id", "deletion_status", "steps_json"]:
            raise ValueError(f"Invalid CSV header: {reader.fieldnames}")
        rows = list(reader)

    total_rows = len(rows)
    errors = []
    status_counts = {"COMPLETE": 0, "INCOMPLETE": 0, "NOT_APPLICABLE": 0}
    valid_rows = 0

    expected_ids = [f"case_{i}" for i in range(33, 551)]
    actual_ids = [r["case_id"] for r in rows]
    if actual_ids != expected_ids:
        errors.append(f"Case ID sequence mismatch! First actual: {actual_ids[:3]}, expected: {expected_ids[:3]}. Count: {len(actual_ids)} vs {len(expected_ids)}")

    allowed_statuses = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
    allowed_finding_ops = {
        "REPORT_REMAINING_RECORD": "PRESENT",
        "REPORT_EXPOSED_PII": "PRESENT",
        "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
        "REPORT_RESTORE_RISK": "ACTIVE",
    }
    allowed_remediation_ops = {
        "DISABLE_DATA_FLOW": "DISABLED",
        "BLOCK_RESTORE": "BLOCKED",
        "DELETE_RECORD": "ABSENT",
        "REDACT_RECORD": "REDACTED",
        "ANONYMIZE_RECORD": "ANONYMIZED",
    }
    allowed_verification_ops = {
        "VERIFY_RECORD_ABSENT": "ABSENT",
        "VERIFY_RECORD_PRESENT": "PRESENT",
        "VERIFY_RECORD_REDACTED": "REDACTED",
        "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
        "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
        "VERIFY_RESTORE_BLOCKED": "BLOCKED",
    }
    phase_order = {"FINDING": 1, "REMEDIATION": 2, "VERIFICATION": 3}
    required_step_fields = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}

    for row in rows:
        cid = row.get("case_id", "")
        status = row.get("deletion_status", "")
        steps_json = row.get("steps_json", "")

        row_errors = []
        if status not in allowed_statuses:
            row_errors.append(f"Invalid status: {status}")
        else:
            status_counts[status] += 1

        try:
            steps = json.loads(steps_json)
            if not isinstance(steps, list):
                row_errors.append("steps_json is not a JSON array")
                steps = []
        except Exception as exc:
            row_errors.append(f"JSON parse error: {exc}")
            steps = []

        if status == "NOT_APPLICABLE":
            if steps_json != "[]":
                row_errors.append(f"NOT_APPLICABLE must have steps_json='[]', got '{steps_json}'")
        else:
            if not steps:
                row_errors.append(f"{status} case must have non-empty steps")

            last_phase_val = 0
            has_seen_mutation = False
            for step_idx, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    row_errors.append(f"Step {step_idx} is not a dict")
                    continue
                missing_fields = required_step_fields - set(step.keys())
                if missing_fields:
                    row_errors.append(f"Step {step_idx} missing fields: {missing_fields}")
                extra_fields = set(step.keys()) - required_step_fields
                if extra_fields:
                    row_errors.append(f"Step {step_idx} extra fields: {extra_fields}")

                s_no = step.get("step_no")
                if s_no != step_idx:
                    row_errors.append(f"Step {step_idx} step_no is {s_no}, expected {step_idx}")

                phase = step.get("phase", "")
                op = step.get("operation", "")
                st = step.get("state", "")
                ev_id = step.get("evidence_id", "")

                if phase not in phase_order:
                    row_errors.append(f"Invalid phase: {phase}")
                else:
                    pv = phase_order[phase]
                    if pv < last_phase_val:
                        row_errors.append(f"Phase inversion: {phase} after phase value {last_phase_val}")
                    last_phase_val = pv

                if status == "COMPLETE":
                    if phase != "VERIFICATION":
                        row_errors.append(f"COMPLETE case has non-verification step ({phase})")
                    if op not in allowed_verification_ops or allowed_verification_ops[op] != st:
                        row_errors.append(f"Invalid COMPLETE verification op/state: {op}/{st}")
                    if not ev_id:
                        row_errors.append("COMPLETE verification step missing evidence_id")
                elif status == "INCOMPLETE":
                    if phase == "FINDING":
                        if op not in allowed_finding_ops or allowed_finding_ops[op] != st:
                            row_errors.append(f"Invalid FINDING op/state: {op}/{st}")
                        if not ev_id:
                            row_errors.append("FINDING step missing evidence_id")
                    elif phase == "REMEDIATION":
                        if op not in allowed_remediation_ops or allowed_remediation_ops[op] != st:
                            row_errors.append(f"Invalid REMEDIATION op/state: {op}/{st}")
                        if ev_id != "":
                            row_errors.append(f"REMEDIATION step has non-empty evidence_id: '{ev_id}'")
                        if op in ("DISABLE_DATA_FLOW", "BLOCK_RESTORE"):
                            if has_seen_mutation:
                                row_errors.append(f"Remediation ordering error: {op} appeared after mutation")
                        elif op in ("DELETE_RECORD", "REDACT_RECORD", "ANONYMIZE_RECORD"):
                            has_seen_mutation = True
                    elif phase == "VERIFICATION":
                        if op not in allowed_verification_ops or allowed_verification_ops[op] != st:
                            row_errors.append(f"Invalid VERIFICATION op/state: {op}/{st}")
                        if ev_id != "":
                            row_errors.append(f"Post-remediation VERIFICATION step has non-empty evidence_id: '{ev_id}'")

        if row_errors:
            errors.append(f"{cid}: {'; '.join(row_errors)}")
        else:
            valid_rows += 1

    return {
        "total_rows": total_rows,
        "valid_rows": valid_rows,
        "status_counts": status_counts,
        "errors": errors,
        "is_valid": len(errors) == 0 and total_rows == 518,
    }


def run_full_evaluation(output_path: Path = OUTPUT_CSV) -> Dict[str, Any]:
    """
    Executes LangGraph workflow across all 518 evaluation cases and writes output.csv.
    """
    bundle, index = get_global_bundle_and_index()
    total = len(bundle.deletion_requests)
    logger.info("Executing full evaluation over %d cases...", total)
    start_time = time.time()

    rows = []
    unresolved_cases = []

    for idx, req in enumerate(bundle.deletion_requests, start=1):
        try:
            state = audit_single_case(req.case_id, bundle=bundle, index=index)
            status = state.get("deletion_status", "INCOMPLETE")
            steps_json = state.get("steps_json", "[]")
            rows.append({
                "case_id": req.case_id,
                "deletion_status": status,
                "steps_json": steps_json,
            })
            if status == "INCOMPLETE" and state.get("has_uncertainty", False):
                unresolved_cases.append(req.case_id)
        except Exception as exc:
            logger.error("Case %s evaluation failed: %s", req.case_id, exc)
            rows.append({
                "case_id": req.case_id,
                "deletion_status": "INCOMPLETE",
                "steps_json": "[]",
            })
            unresolved_cases.append(req.case_id)

        if idx % 50 == 0 or idx == total:
            logger.info("Progress: %d / %d cases completed (%.1fs elapsed).", idx, total, time.time() - start_time)

    # Sort rows numerically by integer case number: case_33 .. case_550
    rows.sort(key=lambda r: int(r["case_id"].replace("case_", "")))

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "deletion_status", "steps_json"])
        writer.writeheader()
        writer.writerows(rows)

    elapsed = time.time() - start_time
    logger.info("Wrote %d evaluation rows to %s in %.2fs", len(rows), output_path, elapsed)

    # Validate generated output.csv
    validation = validate_output_file(output_path)

    import llm_provider
    from evidence_agent import get_gemini_usage
    provider_usage = llm_provider.get_usage()
    ocr_usage = get_gemini_usage()

    print("\n" + "=" * 65)
    print("MILESTONE 7: FULL 518-CASE EVALUATION SUMMARY")
    print("=" * 65)
    print(f"Total Cases Evaluated:   {total}")
    print(f"Output Rows Written:     {len(rows)} (at {output_path})")
    print(f"Schema Validity:         {validation['valid_rows']}/{total} ({validation['valid_rows']/total:.1%})")
    print(f"Validation Errors:       {len(validation['errors'])}")
    print(f"Elapsed Time:            {elapsed:.2f}s ({elapsed/total*1000:.1f}ms/case)")
    print("-" * 65)
    print("Status Distribution:")
    for st, count in validation["status_counts"].items():
        print(f"  {st:<16}: {count:>4} ({count/total:.1%})")
    print("-" * 65)
    print("LLM Provider Execution Stats:")
    print(f"  Groq Calls (Primary):  {provider_usage.groq_calls} (Errors: {provider_usage.groq_errors})")
    print(f"  Gemini Text Calls:     {provider_usage.gemini_calls} (Errors: {provider_usage.gemini_errors})")
    print(f"  Gemini Vision Calls:   {provider_usage.vision_calls} (Errors: {provider_usage.vision_errors})")
    print(f"  Fallbacks to Gemini:   {provider_usage.fallbacks_to_gemini}")
    print(f"  OCR Cache Hits:        {ocr_usage.cache_hits}")
    print(f"  Unresolved Cases:      {len(unresolved_cases)}")
    print("=" * 65 + "\n")

    return {
        "total": total,
        "output_path": str(output_path),
        "validation": validation,
        "elapsed_seconds": round(elapsed, 2),
        "provider_usage": provider_usage.to_dict(),
        "ocr_usage": ocr_usage.to_dict(),
        "unresolved_cases_count": len(unresolved_cases),
    }


def main():
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists -- Deletion Audit Agent")
    parser.add_argument("--case", type=str, help="Audit a specific case_id")
    parser.add_argument("--samples", action="store_true", help="Run 32-case sample benchmark and compare with sample_output.csv")
    parser.add_argument("--eval", action="store_true", help="Run all 518 evaluation cases and generate output.csv")
    parser.add_argument("--output", type=str, default=str(OUTPUT_CSV), help="Output CSV path")

    args = parser.parse_args()

    if args.case:
        state = audit_single_case(args.case)
        print(json.dumps({
            "case_id": state["case_id"],
            "deletion_status": state["deletion_status"],
            "steps_json": state["steps_json"],
            "iterations": state.get("iteration_count", 0),
            "audit_passed": state.get("audit_passed", False),
        }, indent=2))
    elif args.samples:
        evaluate_sample_benchmark()
    elif args.eval:
        run_full_evaluation(Path(args.output))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
