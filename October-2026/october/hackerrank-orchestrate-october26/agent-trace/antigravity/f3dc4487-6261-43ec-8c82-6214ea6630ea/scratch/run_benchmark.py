"""Run 32-case benchmark and report results."""
import sys
import os
import time

sys.path.insert(0, 'code')

# Track Vision API calls and cache hits by wrapping the function
import evidence_agent as ea

_orig_extract = ea._extract_text_from_image
_api_calls = 0
_cache_hits = 0
_quota_errors = 0

def tracked_extract(path, file_id="", usage=None):
    global _api_calls, _cache_hits, _quota_errors
    # Check cache
    if hasattr(ea, '_ocr_cache') and path in ea._ocr_cache:
        cached = ea._ocr_cache[path]
        if cached:
            _cache_hits += 1
            return cached, "cache"
    result, method = _orig_extract(path, file_id, usage)
    if method and "gemini" in method.lower():
        _api_calls += 1
    if method and "quota" in method.lower():
        _quota_errors += 1
    return result, method

ea._extract_text_from_image = tracked_extract

from main import evaluate_sample_benchmark

t0 = time.time()
report = evaluate_sample_benchmark()
elapsed = time.time() - t0

total = report["total_cases"]
status_ok = report["status_matches"]
schema_ok = report["schema_valid_count"]

print("=" * 60)
print("BENCHMARK RESULTS — 32 Sample Cases")
print("=" * 60)
print(f"Status accuracy:   {status_ok}/{total}  ({status_ok/total*100:.1f}%)")
print(f"Schema valid:      {schema_ok}/{total}  ({schema_ok/total*100:.1f}%)")
print(f"Gemini API calls:  {_api_calls}  (Vision OCR, new calls)")
print(f"OCR cache hits:    {_cache_hits}  (reused results)")
print(f"Quota errors:      {_quota_errors}")
print(f"Elapsed:           {elapsed:.2f}s")
print()

mismatches = [c for c in report["case_details"] if not c.get("status_match", True)]
if mismatches:
    print("STATUS MISMATCHES:")
    for m in mismatches:
        pred = m.get("pred_status", "?")
        exp = m.get("exp_status", "?")
        err = m.get("error", "")
        print(f"  {m['case_id']:>10}: expected={exp:<12}  got={pred}  {err}")
else:
    print("✓ All 32 cases correct — no mismatches.")

schema_fail = [c for c in report["case_details"] if not c.get("schema_valid", True)]
if schema_fail:
    print("\nSCHEMA FAILURES:")
    for f in schema_fail:
        print(f"  {f['case_id']:>10}: {f.get('error', 'schema error')}")

print()
