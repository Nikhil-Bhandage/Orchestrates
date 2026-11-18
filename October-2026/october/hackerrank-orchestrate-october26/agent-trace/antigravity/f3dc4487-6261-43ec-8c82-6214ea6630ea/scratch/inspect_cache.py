import json
from pathlib import Path

cache = json.loads(Path("code/.ocr_cache.json").read_text(encoding="utf-8"))
for sha, text in cache.items():
    print("=" * 60)
    first_line = text.splitlines()[0] if text else "EMPTY"
    lines = [l for l in text.splitlines() if any(k in l.lower() for k in ["user_", "usr_", "cust_", "email", "state", "status", "active", "deleted", "blocked", "disabled", "redacted", "anonymized", "retain", "restore", "tombstone"])]
    print(f"SHA: {sha[:10]} | First line: {first_line}")
    print("Key lines matching keywords:")
    for l in lines[:10]:
        print("  ", l)
