import os
import base64
import json
import hashlib
from pathlib import Path

# Load API key
for base in [Path("."), Path("..")]:
    env_file = base / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
                os.environ["GEMINI_API_KEY"] = key
                break
        if "GEMINI_API_KEY" in os.environ:
            break

import google.generativeai as genai
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-3.8-flash")

cache_file = Path("code/.ocr_cache.json")
cache = {}
if cache_file.exists():
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        cache = {}

images_dir = Path("dataset/evidence/images")
pngs = sorted(list(images_dir.glob("*.png")))
print(f"Found {len(pngs)} PNG files.")

for png in pngs:
    sha = hashlib.sha256(png.read_bytes()).hexdigest()
    if sha in cache and cache[sha]:
        print(f"[CACHED] {png.name}")
        continue
    
    print(f"[CALLING GEMINI] {png.name}...")
    img_bytes = png.read_bytes()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    prompt = (
        "You are an expert OCR and auditing system. "
        "Extract ALL text from this image exactly as shown, preserving layout, tables, column headers, rows, labels, status values, IDs, timestamps, and keys. "
        "Do not invent facts or hallucinate text."
    )
    try:
        resp = model.generate_content([
            {"role": "user", "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ]},
        ])
        text = resp.text.strip() if resp.text else ""
        cache[sha] = text
        print(f"-> Extracted {len(text)} chars from {png.name}")
    except Exception as e:
        print(f"-> ERROR on {png.name}: {e}")

# Save cache with valid text
valid_cache = {k: v for k, v in cache.items() if v}
cache_file.write_text(json.dumps(valid_cache, indent=2), encoding="utf-8")
print(f"Saved {len(valid_cache)} cached entries to {cache_file}.")
