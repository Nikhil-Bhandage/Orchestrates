import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from output_pipeline import OUTPUT_COLUMNS, FinalOutputPipeline

ROOT = Path(__file__).parent.parent


class FinalOutputPipelineTests(unittest.TestCase):
    def test_full_dataset_builds_with_strict_validation(self):
        run = FinalOutputPipeline(ROOT / "dataset").build_and_validate()
        self.assertEqual(len(run.rows), 250)
        self.assertEqual(run.summary["validation_failure_count"], 0)
        self.assertEqual(run.summary["sanity_checks"]["all_rows_valid"], True)
        self.assertTrue(all(tuple(row.keys()) == OUTPUT_COLUMNS for row in run.rows))
        self.assertEqual(len({row["request_id"] for row in run.rows}), 250)

    def test_explanation_is_present_and_serialized_from_decision(self):
        run = FinalOutputPipeline(ROOT / "dataset").build_and_validate()
        for row in run.rows:
            self.assertTrue(row["decision_explanation"])
            self.assertTrue("minimum" in row["decision_explanation"] or "eligible" in row["decision_explanation"])


if __name__ == "__main__":
    unittest.main()
