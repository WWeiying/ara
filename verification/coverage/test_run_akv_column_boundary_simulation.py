import unittest
from pathlib import Path
import run_akv_column_boundary_simulation as r


class RunnerTest(unittest.TestCase):
    def test_command(self):
        out = r.life.OUT / "test-boundary"
        command = r.command(dict(input_elf="/absolute/native.elf"), out)
        self.assertEqual(command[0], str(r.life.IMAGE))
        self.assertIn("+NO_FSDB", command)
        self.assertIn("+AKV_PERF", command)
        self.assertIn("+PRELOAD=/absolute/native.elf", command)
        self.assertIn("+COMMIT_TRACE=" + str(out / "commit_trace.csv"), command)
        self.assertNotIn("+PRELOAD=/absolute/software.elf", command)

    def test_reject_missing_contract(self):
        with self.assertRaises(ValueError):
            r.validate({}, Path("/tmp"))

    def test_reject_foreign_output(self):
        with self.assertRaises(ValueError):
            r.prepare(Path("/tmp/pre"), "a"*64, Path("/tmp/out"))

    def test_timeout_is_manifest_bound(self):
        self.assertIn('timeout=manifest["timeout_s"]', Path(r.__file__).read_text())
        self.assertNotIn("life.run(", Path(r.__file__).read_text())


if __name__ == "__main__":
    unittest.main()
