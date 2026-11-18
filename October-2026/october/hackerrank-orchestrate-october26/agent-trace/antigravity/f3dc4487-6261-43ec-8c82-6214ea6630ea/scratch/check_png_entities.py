import json
import re
from pathlib import Path

cache = json.loads(Path("code/.ocr_cache.json").read_text(encoding="utf-8"))

RE_USER_ID = re.compile(r'\buser_\d+\b', re.IGNORECASE)
RE_EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
RE_RES_ID = re.compile(r'\b(?:account|audit_record|analytics|support|data_flow|backup|tombstone|search|connector|export)_\d+\b', re.IGNORECASE)

manifest_files = {}
import csv
with open("dataset/evidence_files.csv", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        manifest_files[r["file_path"]] = r

import hashlib
for png_path in sorted(list(Path("dataset/evidence/images").glob("*.png"))):
    rel_path = f"evidence/images/{png_path.name}"
    sha = hashlib.sha256(png_path.read_bytes()).hexdigest()
    text = cache.get(sha, "")
    meta = manifest_files.get(rel_path, {})
    file_id = meta.get("file_id", "unknown")
    captured_at = meta.get("captured_at", "")
    
    users = set(u.lower() for u in RE_USER_ID.findall(text))
    emails = set(e.lower() for e in RE_EMAIL.findall(text))
    res = set(r.lower() for r in RE_RES_ID.findall(text))
    
    print(f"File: {file_id} ({png_path.name}) captured_at={captured_at}")
    print(f"  Users: {sorted(list(users))}")
    print(f"  Emails: {sorted(list(emails))}")
    print(f"  Resources: {sorted(list(res))}")
    # Also print any status or state mentions
    status_words = [w for w in ["deleted", "blocked", "disabled", "redacted", "anonymized", "active", "present", "healthy", "in transit", "completed"] if w in text.lower()]
    print(f"  Status words: {status_words}")
    print()
