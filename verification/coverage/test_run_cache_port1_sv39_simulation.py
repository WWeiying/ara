import copy
import json
import unittest
import run_cache_port1_sv39_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())
        self.targets = json.loads((m.PRE / "target-before.json").read_bytes())

    def test_exact_contract(self):
        m.validate(self.pre)
        m.validate_targets(self.targets)

    def test_elf_drift(self):
        self.pre["pins"][str(m.PRE / "input.elf")] = "0" * 64
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_extra_trap(self):
        self.pre["spike_validation"]["expected_S_ecalls"] = 3
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_geometry_drift(self):
        self.pre["spike_validation"]["linked_geometry"]["pairs"][0]["slots"] = [1, 2]
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_missing_config_pin(self):
        del self.pre["pins"][str(m.PRE / "cache-configuration-proof.json")]
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_duplicate_target(self):
        self.targets["targets"][1] = copy.deepcopy(self.targets["targets"][0])
        with self.assertRaises(ValueError): m.validate_targets(self.targets)

    def test_hit_target(self):
        self.targets["targets"][0]["hit_before"] = True
        with self.assertRaises(ValueError): m.validate_targets(self.targets)

    def test_no_replay_claim(self):
        self.pre["replay_observed"] = True
        with self.assertRaises(ValueError): m.validate(self.pre)

    def test_command(self):
        out = m.life.OUT / "cache-port1-command-test"
        command = m.command(out)
        self.assertIn("+NO_FSDB", command)
        self.assertIn("+COMMIT_TRACE=" + str(out / "commit_trace.csv"), command)
        self.assertIn("+VECTOR_TRACE=" + str(out / "vector_trace.csv"), command)
        self.assertEqual(command[command.index("-cm") + 1], "line+cond+fsm+tgl+branch")
        self.assertEqual(command[command.index("-cm_dir") + 1], str(out / "code.vdb"))


if __name__ == "__main__":
    unittest.main()
