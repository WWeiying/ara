"""Independent FP16 software oracle/negative gates; no simulator or admission."""
from dataclasses import replace
from fractions import Fraction
import unittest

import build_gap98_preflight as build


class Preflight98Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = build.OUT / "gap98-spike-first-diagnostic-706-20261006-01"
        cls.main_dir = directory / build.NAME
        cls.inf_dir = directory / "inf-flags-spike-only"
        cls.symbols = {key: build._elf_symbol(cls.main_dir / "input.elf", build.LLVM / "llvm-readelf", key)
                       for key in ("tohost", "g75_result", "g75_trap", "num_failed", "trap_fail")}
        cls.commits = build.parse_spike_commits(cls.main_dir / "spike.trace")
        cls.inf_symbols = {key: build._elf_symbol(cls.inf_dir / "input.elf", build.LLVM / "llvm-readelf", key)
                           for key in cls.symbols}
        cls.inf_commits = build.parse_spike_commits(cls.inf_dir / "spike.trace")

    def test_actual_main_signature_and_exact_oracle(self):
        result = build.validate_spike(self.commits, self.symbols)
        self.assertEqual(result["checks"], 3112)
        self.assertEqual(result["destination_instructions"], 24)
        self.assertEqual(result["destination_bytes"], 6144)
        self.assertEqual(result["exact_division_flags"], [0, 3, 3, 3] * 2)

    def test_pure_infinity_flags_are_independently_observable(self):
        result = build.validate_spike(self.inf_commits, self.inf_symbols, True)
        self.assertEqual(result["checks"], 774)
        self.assertEqual(result["exact_division_flags"], [0, 0])
        self.assertEqual(result["destination_instructions"], 6)
        with self.assertRaises(ValueError):
            build.validate_spike(self.commits, self.symbols, True)

    def test_rne_tie_even_and_signed_zero(self):
        unit = Fraction(1, 1 << 24)
        for sign in (0, 1):
            for exponent in range(5, 32):
                bits, flags = build.oracle(exponent, sign)
                expected = 1 << (15 - exponent) if exponent <= 15 else 0
                self.assertEqual(bits, (sign << 15) | expected)
                self.assertEqual(flags, 3 if 16 <= exponent <= 30 else 0)
                if exponent < 31:
                    exact = unit * Fraction(2) ** (15 - exponent)
                    self.assertEqual(expected * unit == exact, flags == 0)
        self.assertEqual(build.oracle(16, 0), (0, 3))
        self.assertEqual(build.oracle(31, 1), (0x8000, 0))

    def test_pattern_repeats_all_exponents_at_all_sixteen_positions(self):
        for position in range(16):
            seen = {build.exponent_at(batch, i) for batch in range(4)
                    for i in range(position, 128, 16)}
            self.assertEqual(seen, set(range(5, 32)))
        with self.assertRaises(ValueError):
            build.exponent_at(4, 0)

    def test_wrong_vector_result_flags_or_count_rejected(self):
        index = next(i for i, c in enumerate(self.commits) if c.instruction == 0x82821857)
        real = self.commits[index]
        wrong_data = dict(real.vector_writes)
        wrong_data[16] ^= 1
        for changed in (replace(real, vector_writes=wrong_data),
                        replace(real, csr_writes={**real.csr_writes, 1: 3}),
                        replace(real, vector_vl=127)):
            commits = list(self.commits)
            commits[index] = changed
            with self.assertRaises(ValueError):
                build.validate_spike(commits, self.symbols)
        with self.assertRaises(ValueError):
            build.validate_spike(self.commits[:index] + self.commits[index + 1:], self.symbols)

    def test_infinity_wrong_flags_cannot_hide_in_mixed_batch(self):
        index = next(i for i, c in enumerate(self.inf_commits) if c.instruction == 0x82821857)
        commits = list(self.inf_commits)
        commits[index] = replace(commits[index], csr_writes={**commits[index].csr_writes, 1: 3})
        with self.assertRaises(ValueError):
            build.validate_spike(commits, self.inf_symbols, True)

    def test_complete_signature_and_tohost_required(self):
        index = next(i for i, c in reversed(list(enumerate(self.commits)))
                     if any(a == self.symbols["g75_result"] and v is not None for a, v in c.memory_accesses))
        commits = list(self.commits)
        real = commits[index]
        commits[index] = replace(real, memory_accesses=tuple((a, v ^ 1 if v is not None else v)
                                                           for a, v in real.memory_accesses))
        with self.assertRaises(ValueError):
            build.validate_spike(commits, self.symbols)
        terminal = next(c for c in self.commits if (self.symbols["tohost"], 1) in c.memory_accesses)
        with self.assertRaises(ValueError):
            build.validate_spike([terminal] + self.commits, self.symbols)

    def test_exact_explicit_band_and_defaults_not_targets(self):
        record = dict(width=143, checksum="839910393", bits="0x0")
        mapped = [dict(raw_index=82 - v, vector=str(v), line="178", native_id="7") for v in range(55)]
        result = build.table_targets(record, mapped)
        self.assertEqual(len(result["missing_points"]), 27)
        self.assertEqual(len(result["outside_band_points"]), 28)
        self.assertTrue(all(p["decision"] == "NOT_A_GAP98_TARGET_NOT_WAIVED" for p in result["outside_band_points"]))
        record["bits"] = hex(1 << (142 - 56))
        self.assertEqual(len(build.table_targets(record, mapped)["missing_points"]), 26)
        with self.assertRaises(ValueError):
            build.table_targets(dict(record, checksum="other"), mapped)
        bad = [dict(p) for p in mapped]
        bad[0]["vector"] = "53"
        with self.assertRaises(ValueError):
            build.table_targets(record, bad)


if __name__ == "__main__":
    unittest.main()
