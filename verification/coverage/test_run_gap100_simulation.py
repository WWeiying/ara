import json
import unittest
from pathlib import Path

import run_gap100_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())

    def test_actual_preflight(self):
        m.validate(self.pre)

    def test_wrong_baseline(self):
        self.pre["baseline_tests"] = 707
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_no_fake_scalar_qualification(self):
        for obj in (self.pre, self.pre["spike_validation"]):
            obj['scalar_comparison_qualified'] = True
            with self.assertRaises(ValueError):
                m.validate(self.pre)
            obj['scalar_comparison_qualified'] = False

    def test_wrong_elf(self):
        self.pre["pins"][self.pre["input_elf"]] = "0" * 64
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_wrong_trap_or_vector_population(self):
        for field in ('expected_traps', 'vector_destination_instructions', 'legal_hpm_reads'):
            original = self.pre['spike_validation'][field]
            self.pre['spike_validation'][field] = original + 1
            with self.assertRaises(ValueError):
                m.validate(self.pre)
            self.pre['spike_validation'][field] = original

    def test_unpinned_trace(self):
        del self.pre["pins"][self.pre["input_spike_trace"]]
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_actual_targets_and_reject_duplicate_hit_scope(self):
        file = m.PRE / 'target-before.json'
        actual = json.loads(file.read_bytes())
        m.validate_targets(actual)
        for kind in ('duplicate', 'hit', 'scope'):
            changed = json.loads(file.read_bytes())
            if kind == 'duplicate':
                changed['targets'][-1] = changed['targets'][0]
            elif kind == 'hit':
                changed['targets'][0]['hit_before'] = True
            else:
                changed['targets'][0]['scope'] += '.other'
            with self.assertRaises(ValueError):
                m.validate_targets(changed)

    def test_exact_command(self):
        out = Path('/tmp/gap100-independent')
        cmd = m.command(out)
        self.assertEqual(cmd[0], str(m.life.IMAGE))
        self.assertIn('+COMMIT_TOHOST=80001000', cmd)
        self.assertIn('+PRELOAD=' + str(m.PRE / 'input.elf'), cmd)
        self.assertIn(str(out / 'code.vdb'), cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertEqual(cmd.count('-cm'), 1)

    def test_fresh_output(self):
        with self.assertRaises(ValueError):
            m.prepare(m.PRE)


if __name__ == '__main__':
    unittest.main()
