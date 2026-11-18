"""Run the deterministic Buy or Wait final pipeline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from output_pipeline import OutputValidationError, run_final_pipeline  # noqa: E402


def main() -> int:
    try:
        run = run_final_pipeline(
            dataset_dir=ROOT / "dataset",
            output_path=ROOT / "output.csv",
            diagnostic_path=ROOT / "code/evaluation/final_diagnostic.json",
        )
    except OutputValidationError as exc:
        failure_path = ROOT / "code/evaluation/final_validation_failure.json"
        failure_path.write_text(
            json.dumps(
                {
                    "validation_failure_count": len(exc.issues),
                    "issues": [issue.__dict__ for issue in exc.issues],
                    "output_written": False,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(run.summary, indent=2, ensure_ascii=False))
    print(f"wrote {ROOT / 'output.csv'} rows={len(run.rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
