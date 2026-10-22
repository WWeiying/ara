"""Runner preflight checks that never invoke a compiler or simulator."""

import subprocess
import tempfile
import unittest
from pathlib import Path


RUNNER = Path(__file__).resolve().parents[1] / "uvm/divsqrt_multifmt_status_run.sh"


class DivsqrtMultifmtStatusRunnerTests(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(RUNNER)], capture_output=True,
                                text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_arguments_fail_before_launch(self):
        result = subprocess.run(["bash", str(RUNNER)], capture_output=True,
                                text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage:", result.stderr)

    def test_historical_bug_mode_rejected_before_output_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            filelist = root / "sources.f"
            filelist.touch()
            output = root / "output"
            result = subprocess.run(
                ["bash", str(RUNNER), str(output), str(filelist), "+EXPECT_OLD_BUG"],
                capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("not a signoff pass mode", result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
