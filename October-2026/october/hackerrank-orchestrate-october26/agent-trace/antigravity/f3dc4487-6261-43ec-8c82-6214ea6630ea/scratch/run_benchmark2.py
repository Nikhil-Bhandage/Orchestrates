"""32-case benchmark with provider usage reporting."""
import sys, time
sys.path.insert(0, "code")

import llm_provider
from main import evaluate_sample_benchmark

t0 = time.time()
report = evaluate_sample_benchmark()
elapsed = time.time() - t0
u = llm_provider.get_usage()

total = report["total_cases"]
status_ok = report["status_matches"]
schema_ok = report["schema_valid_count"]

print()
print("=" * 60)
print("BENCHMARK RESULTS -- 32 Sample Cases")
print("=" * 60)
print(f"Status accuracy:   {status_ok}/{total}  ({status_ok/total*100:.1f}%)")
print(f"Schema valid:      {schema_ok}/{total}  ({schema_ok/total*100:.1f}%)")
print()
print("LLM Provider Usage:")
print(f"  Groq calls:      {u.groq_calls}  (input={u.groq_input_tokens} out={u.groq_output_tokens} tok, errors={u.groq_errors})")
print(f"  Gemini calls:    {u.gemini_calls}  (input={u.gemini_input_tokens} out={u.gemini_output_tokens} tok, errors={u.gemini_errors})")
print(f"  Groq->Gemini fb: {u.fallbacks_to_gemini}")
print(f"  Vision calls:    {u.vision_calls}  (errors={u.vision_errors})")
print(f"  Elapsed:         {elapsed:.1f}s")
print()

mismatches = [c for c in report["case_details"] if not c.get("status_match", True)]
if mismatches:
    print("STATUS MISMATCHES:")
    for m in mismatches:
        print(f"  {m['case_id']:>10}: expected={m.get('exp_status','?'):<12}  got={m.get('pred_status','?')}")
else:
    print("All 32 cases correct -- no mismatches.")
