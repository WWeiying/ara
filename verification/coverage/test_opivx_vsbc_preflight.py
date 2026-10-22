"""Small arithmetic/encoding tests and rejection tests using the actual Spike log."""
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest

import build_opivx_vsbc_preflight as p
import run_opivx_vsbc_simulation as runner


class StaticTests(unittest.TestCase):
    def test_recovery(self):
        self.assertEqual(p.expected_register(2, True)[:4], bytes([253, 255, 252, 124]))
        self.assertEqual(p.expected_register(2, True)[4:], bytes([90] * 124))

    def test_encoding(self):
        self.assertEqual((18 << 26) | (8 << 20) | (7 << 15) | (4 << 12) | 87, 0x4883c057)

    def test_widths(self):
        self.assertEqual(p.store_width(0x0002b023), 8)
        self.assertEqual(p.store_width(0xe022), 8)
        self.assertEqual(p.store_width(0x02850027), 1)

    def test_unknown_store(self):
        with self.assertRaises(ValueError):
            p.store_width(0x13)

    def test_runner_budget_and_command(self):
        command = runner.command(p.OUT / "unused-vsbc-test-output")
        self.assertEqual(command[0], str(runner.life.IMAGE))
        self.assertIn("+NO_FSDB", command)
        self.assertNotIn("dve", " ".join(command).lower())


@unittest.skipUnless(os.environ.get("VSBC_PREFLIGHT"), "Set VSBC_PREFLIGHT for actual-log rejection fixture")
class ActualFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(os.environ["VSBC_PREFLIGHT"]).absolute()
        cls.pre = json.loads((cls.out / "preflight-manifest.json").read_text())
        cls.commits = p.parse_spike_commits(cls.out / "spike.trace")
        cls.trace = (cls.out / "spike.trace").read_text()
        cls.symbols = cls.pre["symbols"]

    def validate(self, commits=None, trace=None, symbols=None):
        return p.validate(self.commits if commits is None else commits,
                          self.symbols if symbols is None else symbols,
                          self.trace if trace is None else trace)

    def test_actual_full_replay(self):
        self.assertEqual(self.validate(), self.pre["validation"])

    def test_missing_trap(self):
        with self.assertRaises(ValueError):
            self.validate(trace="")

    def test_extra_trap(self):
        with self.assertRaises(ValueError):
            self.validate(trace=self.trace + "exception trap_illegal_instruction, epc 0x80000000\n")

    def test_bad_retirement(self):
        with self.assertRaises(ValueError):
            self.validate(commits=self.commits + [replace(self.commits[-1], pc=self.symbols["gvs_bad"])])

    def test_extra_vrf_write(self):
        c = replace(self.commits[-1], vector_writes={3: 0})
        with self.assertRaises(ValueError):
            self.validate(commits=self.commits + [c])

    def test_wrong_recovery(self):
        commits = [replace(c, vector_writes={10: 0}) if c.pc == self.symbols["gvs_recovery"] else c
                   for c in self.commits]
        with self.assertRaises(ValueError):
            self.validate(commits=commits)

    def corrupt_word(self, symbol, offset, value):
        address = self.symbols[symbol] + offset
        c = replace(self.commits[-1], instruction=0x0002b023, vector_writes={},
                    memory_accesses=((address, value),))
        with self.assertRaises(ValueError):
            self.validate(commits=self.commits + [c])

    def test_vstart_not_preserved(self):
        self.corrupt_word("gvs_post", 32, 0)

    def test_handler_t2_clobbered(self):
        self.corrupt_word("gvs_post", 16, 4)

    def test_tail_changed(self):
        self.corrupt_word("gvs_dump", (3 * 18 + 2 * 18 + 16) * 8, 0)

    def test_guard_changed(self):
        self.corrupt_word("gvs_dump", 0, 0)

    def test_handler_extra_store(self):
        c = replace(self.commits[-1], pc=self.symbols["gvs_handler"] + 4,
                    instruction=0x0002b023, memory_accesses=((self.symbols["gvs_post"], 0),),
                    vector_writes={})
        with self.assertRaises(ValueError):
            self.validate(commits=self.commits + [c])

    def test_handler_protected_csr(self):
        commits = [replace(c, csr_writes={8: 0}) if c.pc == self.symbols["gvs_handler"] else c
                   for c in self.commits]
        with self.assertRaises(ValueError):
            self.validate(commits=commits)

    def test_target_drift(self):
        pre = json.loads(json.dumps(self.pre))
        pre["targets"]["branch"]["point"]["raw_index"] = 969
        with self.assertRaises(ValueError):
            runner.validate(pre)

    def test_accept_actual_runner_contract(self):
        runner.validate(self.pre)

    def test_wrong_baseline(self):
        pre = dict(self.pre, baseline_tests=718)
        with self.assertRaises(ValueError):
            runner.validate(pre)

    def test_elf_word_drift(self):
        blob = bytearray((self.out / "input.elf").read_bytes())
        pos = blob.find(bytes.fromhex("57c08348"))
        self.assertGreaterEqual(pos, 0)
        blob[pos] ^= 1
        with self.assertRaises(ValueError):
            p.verify_elf(blob, self.symbols)


if __name__ == "__main__":
    unittest.main()
