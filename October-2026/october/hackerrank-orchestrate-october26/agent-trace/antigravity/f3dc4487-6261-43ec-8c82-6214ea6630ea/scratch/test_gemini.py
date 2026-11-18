import os
from pathlib import Path

# Look for .env in repo root or parent
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

print("Key present:", bool(os.environ.get("GEMINI_API_KEY")))

import google.generativeai as genai
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
models = [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
print("Supported models count:", len(models))
print("Sample models:", [m for m in models if "flash" in m or "pro" in m][:5])
