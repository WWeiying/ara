import json
import unittest
from pathlib import Path
import run_gap99_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())

    def test_actual_preflight(self):
        m.validate(self.pre)

    def test_wrong_baseline(self):
        self.pre["baseline_tests"] = 706
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_wrong_elf(self):
        self.pre["pins"][self.pre["input_elf"]] = "0" * 64
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_wrong_vector_expectation(self):
        self.pre["spike_validation"]["vector_bytes"] = 256
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_unpinned_trace(self):
        del self.pre["pins"][self.pre["input_spike_trace"]]
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_exact_command(self):
        out = Path("/tmp/gap99-independent")
        cmd = m.command(out)
        self.assertEqual(cmd[0], str(m.life.IMAGE))
        self.assertIn("+COMMIT_TOHOST=80001000", cmd)
        self.assertIn("+PRELOAD=" + str(m.PRE / "input.elf"), cmd)
        self.assertIn(str(out / "code.vdb"), cmd)
        self.assertIn("+NO_FSDB", cmd)

    def test_fresh_output(self):
        with self.assertRaises(ValueError):
            m.prepare(m.PRE)


if __name__ == "__main__":
    unittest.main()
