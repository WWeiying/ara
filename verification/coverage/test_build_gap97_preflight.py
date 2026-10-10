"""Bounded CSR/AVL oracle and fail-closed preflight tests; no EDA."""
import copy
from types import SimpleNamespace
import unittest

import build_gap97_preflight as build


def commit(pc, instruction=0x13, gprs=None, memory=()):
    return SimpleNamespace(pc=pc, instruction=instruction, gpr_writes=gprs or {},
                           memory_accesses=memory)


def fixture():
    keys = ("tohost", "g75_result", "g75_trap", "num_failed", "g97_observed", "g97_avl",
            "trap_fail", "gap97_large_avl") + tuple("gap97_probe%d" % i for i in range(10))
    symbols = {key: 0x80000000 + i * 4096 for i, key in enumerate(keys)}
    commits = [commit(0x100, gprs={1: 1})]
    for phase in range(10):
        source = 1 if phase % 5 < 4 else 2
        word = (9 if phase < 5 else 15) << 20 | source << 15
        word |= build.FUNCTIONS[phase % 5] << 12 | 2 << 7 | 0x73
        commits.append(commit(symbols["gap97_probe%d" % phase], word,
                              {2: build.phase_oracle(phase)[3]}))
    commits.append(commit(0x104, gprs={1: 1 << 20}))
    commits.append(commit(symbols["gap97_large_avl"], 1 << 15 | 7 << 12 | 2 << 7 | 0x57,
                          {2: 128}))
    writes = {symbols["tohost"]: 1, symbols["g75_result"]: 75,
              symbols["g75_result"] + 4: 0, symbols["num_failed"]: 0}
    for phase in range(10):
        for column, value in enumerate(build.phase_oracle(phase)):
            writes[symbols["g97_observed"] + phase * 56 + column * 8] = value
    for column, value in enumerate((128, 128, 0, 128, 0)):
        writes[symbols["g97_avl"] + column * 8] = value
    for offset in (0, 8, 16):
        writes[symbols["g75_trap"] + offset] = 0
    commits.append(commit(0x108, memory=tuple(writes.items())))
    return commits, symbols


class Gap97Test(unittest.TestCase):
    def test_independent_exact_oracle(self):
        expected = [(4, 0, 5), (7, 1, 6), (2, 0, 3), (5, 1, 4), (6, 0, 6),
                    (4, 4, 5), (7, 7, 6), (2, 2, 3), (5, 5, 4), (6, 6, 4)]
        for phase, (before, old, after) in enumerate(expected):
            self.assertEqual(build.phase_oracle(phase),
                             [before, before & 1, before >> 1, old, after, after & 1, after >> 1])

    def test_full_signature_and_probe_pass(self):
        result = build.validate_spike(*fixture())
        self.assertEqual(result["checks"], 75)
        self.assertEqual(result["exact_observed_bytes"], 600)

    def test_wrong_old_return_rejected(self):
        commits, symbols = fixture()
        commits[1].gpr_writes[2] = 1
        with self.assertRaises(ValueError):
            build.validate_spike(commits, symbols)

    def test_dynamic_operand_and_csr_encoding_rejected(self):
        original, symbols = fixture()
        for mutate in (lambda rows: rows[0].gpr_writes.update({1: 2}),
                       lambda rows: setattr(rows[1], "instruction", rows[1].instruction & ~(31 << 15)),
                       lambda rows: setattr(rows[1], "instruction", rows[1].instruction ^ (1 << 20)),
                       lambda rows: setattr(rows[1], "instruction", rows[1].instruction & ~(31 << 7))):
            rows = copy.deepcopy(original)
            mutate(rows)
            with self.assertRaises(ValueError):
                build.validate_spike(rows, symbols)

    def test_immediate_two_is_not_zero_or_one(self):
        rows, symbols = fixture()
        rows[10].instruction ^= 3 << 15
        with self.assertRaises(ValueError):
            build.validate_spike(rows, symbols)

    def test_avl_must_be_large_and_type_exact(self):
        original, symbols = fixture()
        for mutate in (lambda rows: rows[11].gpr_writes.update({1: 128}),
                       lambda rows: setattr(rows[12], "instruction", rows[12].instruction | (1 << 20)),
                       lambda rows: rows[12].gpr_writes.update({2: 127})):
            rows = copy.deepcopy(original)
            mutate(rows)
            with self.assertRaises(ValueError):
                build.validate_spike(rows, symbols)

    def test_missing_or_duplicate_probe_rejected(self):
        rows, symbols = fixture()
        for bad in (rows[:1] + rows[2:], rows[:2] + [rows[1]] + rows[2:]):
            with self.assertRaises(ValueError):
                build.validate_spike(bad, symbols)

    def test_every_saved_observation_required_exact(self):
        original, symbols = fixture()
        for key, offset in (("g97_observed", 9 * 56 + 6 * 8), ("g97_avl", 8),
                            ("g75_result", 0), ("g75_trap", 0), ("tohost", 0)):
            address = symbols[key] + offset
            for missing in (True, False):
                rows = copy.deepcopy(original)
                rows[-1].memory_accesses = tuple((a, v ^ 1 if a == address else v)
                    for a, v in rows[-1].memory_accesses if not (missing and a == address))
                with self.assertRaises(ValueError):
                    build.validate_spike(rows, symbols)

    def test_trap_rejected_even_with_pass_signature(self):
        rows, symbols = fixture()
        rows.insert(0, commit(symbols["trap_fail"]))
        with self.assertRaises(ValueError):
            build.validate_spike(rows, symbols)

    def test_failure_or_duplicate_tohost_cannot_be_overwritten(self):
        for earlier in (1, 3):
            rows, symbols = fixture()
            rows.insert(0, commit(0x110, memory=((symbols["tohost"], earlier),)))
            with self.assertRaises(ValueError):
                build.validate_spike(rows, symbols)

    def test_reordered_probes_rejected(self):
        rows, symbols = fixture()
        rows[1], rows[3] = rows[3], rows[1]
        with self.assertRaises(ValueError):
            build.validate_spike(rows, symbols)

    def test_target_binding_zero_identity_width_checksum(self):
        record = dict(width=1140, checksum="1370170966", bits="0x0")
        mapped = [dict(raw_index=raw, line=line, native_id=native, vector=vector)
                  for raw, (line, native, vector) in build.TARGETS.items()]
        self.assertEqual(len(build.validate_targets(record, mapped)), 6)
        for field, value in (("width", 1141), ("checksum", "other"),
                             ("bits", hex(1 << (1139 - 189)))):
            with self.assertRaises(ValueError):
                build.validate_targets(dict(record, **{field: value}), mapped)
        wrong = copy.deepcopy(mapped)
        wrong[0]["vector"] = "01"
        for bad in (wrong, mapped[1:], mapped + mapped[:1]):
            with self.assertRaises(ValueError):
                build.validate_targets(record, bad)


if __name__ == "__main__":
    unittest.main()
