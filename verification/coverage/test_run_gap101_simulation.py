import copy
import json
import unittest
import run_gap101_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())
        self.targets = json.loads((m.PRE / "target-before.json").read_bytes())

    def test_exact_contract(self):
        m.validate(self.pre)
        m.validate_targets(self.targets)

    def test_elf_pin_not_replaceable(self):
        self.pre["pins"][str(m.PRE / "input.elf")] = "0" * 64
        with self.assertRaisesRegex(ValueError, "ELF"): m.validate(self.pre)

    def test_extra_trap_rejected(self):
        self.pre["validation"]["illegal_traps"] = 3
        with self.assertRaisesRegex(ValueError, "oracle"): m.validate(self.pre)

    def test_missing_snapshot_pin_rejected(self):
        del self.pre["pins"][str(m.PRE / "spike.trace")]
        with self.assertRaisesRegex(ValueError, "Unpinned"): m.validate(self.pre)

    def test_wrong_branch_identity_rejected(self):
        self.targets["targets"][0]["point"]["vector"] = "0"
        with self.assertRaisesRegex(ValueError, "branch identity"): m.validate_targets(self.targets)

    def test_duplicate_target_rejected(self):
        self.targets["targets"][1] = copy.deepcopy(self.targets["targets"][0])
        with self.assertRaisesRegex(ValueError, "targets"): m.validate_targets(self.targets)

    def test_expected_pin_conflict_rejected(self):
        with self.assertRaises(ValueError): m.life.merge_pins({"x": "a"}, {"x": "b"})

    def test_exact_command(self):
        output = m.life.OUT / "gap101-test-command-only"
        command = m.command(output)
        self.assertIn("+NO_FSDB", command)
        self.assertIn("+PRELOAD=" + str(m.PRE / "input.elf"), command)
        self.assertIn("+COMMIT_TRACE=" + str(output / "commit_trace.csv"), command)
        self.assertIn("+VECTOR_TRACE=" + str(output / "vector_trace.csv"), command)
        self.assertEqual(command.count("-cm_dir"), 1)
        self.assertEqual(command[command.index("-cm_dir") + 1], str(output / "code.vdb"))


if __name__ == "__main__": unittest.main()
