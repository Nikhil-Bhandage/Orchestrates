import os
import base64
from pathlib import Path

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

sample_png = Path("dataset/evidence/images/customer_export_console_20260618.png")
if sample_png.exists():
    img_bytes = sample_png.read_bytes()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    
    for model_name in ["gemini-3.8-flash", "models/gemini-3.8-flash", "gemini-flash-latest"]:
        try:
            print(f"Testing model: {model_name}...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content([
                {"role": "user", "parts": [
                    {"text": "Extract all visible text from this image. Output only the text."},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]},
            ])
            print(f"SUCCESS with {model_name}!")
            print("Extracted text preview:\n", response.text[:400])
            break
        except Exception as e:
            print(f"FAILED with {model_name}: {e}")
