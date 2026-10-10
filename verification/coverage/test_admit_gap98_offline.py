import json
from pathlib import Path
import unittest

import admit_gap98_offline as m


def row(insn=0x13, **kw):
    r = {key: 0 for key in m.common.COMMIT_FIELDS}
    r.update(event="retire", insn=insn, pc=0x80002000)
    r.update(kw)
    return r


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        pre = json.loads((m.runner.PRE / "preflight-manifest.json").read_bytes())
        self.meta = dict(entry=0x80000000, symbols=pre["main_case"]["symbols"])
        self.rows = []
        for flags in [0, 3, 3, 3] * 2:
            self.rows.extend((row((9 << 20) | (10 << 15) | (7 << 12) | (11 << 7) | 0x57, rd=11, rd_wdata=128),
                              row(0x82821857), row((1 << 20) | (2 << 12) | (11 << 7) | 0x73, rd=11, rd_wdata=flags),
                              row((8 << 20) | (2 << 12) | (11 << 7) | 0x73, rd=11)))
        s = self.meta["symbols"]
        for addr, data, size in ((s["g75_result"], 3112, 4), (s["g75_result"] + 4, 0, 4),
                                 (s["num_failed"], 0, 4),
                                 *((s["g75_trap"] + off, 0, 8) for off in (0, 8, 16)), (s["tohost"], 1, 8)):
            self.rows.append(row(mem_addr=addr, mem_wdata=data, mem_wmask=((1 << size) - 1) << (addr & 7)))
        for order, r in enumerate(self.rows):
            r.update(order=order, cycle=order)

    def test_architecture_exact(self):
        self.assertEqual(m.architecture(self.rows, self.meta)["checks"], 3112)

    def test_wrong_flags(self):
        self.rows[2]["rd_wdata"] = 3
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_wrong_vl(self):
        self.rows[0]["rd_wdata"] = 64
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_missing_retirement(self):
        with self.assertRaises(ValueError):
            m.architecture(self.rows[1:], self.meta)

    def test_failed_signature(self):
        self.rows[32]["mem_wdata"] = 3111
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_duplicate_tohost(self):
        self.rows.append(dict(self.rows[-1], order=len(self.rows)))
        with self.assertRaises(ValueError):
            m.architecture(self.rows, self.meta)

    def test_actual_elf(self):
        pre = json.loads((m.runner.PRE / "preflight-manifest.json").read_bytes())
        self.assertEqual(m.elf_metadata(Path(pre["main_case"]["input_elf"]).read_bytes(), self.meta["symbols"]), self.meta)

    def test_wrong_elf_symbols(self):
        pre = json.loads((m.runner.PRE / "preflight-manifest.json").read_bytes())
        bad = dict(self.meta["symbols"], tohost=0)
        with self.assertRaises(ValueError):
            m.elf_metadata(Path(pre["main_case"]["input_elf"]).read_bytes(), bad)

    def vector(self):
        result = dict(status="PASS", nr_lanes=4, vlen_bits=1024, vector_destination_requests=24,
                      prefix_vector_destination_requests=24, compared_instructions=24, compared_bytes=6144,
                      skipped_unknown_bytes=0, non_bit_exact_instructions=0, unobservable_instructions=0,
                      incomplete_requests=[], unretired_requests=[], trapped_requests=[],
                      first_mismatch=None, stopped_at_spike_index=None)
        result["instructions"] = [dict(status="PASS", compared_bytes=256, skipped_unknown_bytes=0,
                                        unknown_write_bytes=0, mismatch_count=0, first_mismatch=None) for _ in range(24)]
        return result

    def test_vector_exact(self):
        m.validate_vector(self.vector())

    def test_vector_negative(self):
        for key, value in (("status", "PREFIX"), ("compared_bytes", 6143), ("skipped_unknown_bytes", 1),
                           ("non_bit_exact_instructions", 1), ("unretired_requests", [1]),
                           ("vector_destination_requests", 25)):
            result = self.vector()
            result[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.validate_vector(result)

    def test_unknown_write(self):
        result = self.vector()
        result["instructions"][0]["unknown_write_bytes"] = 1
        with self.assertRaises(ValueError):
            m.validate_vector(result)

    def test_vector_memory_is_accelerator(self):
        self.assertTrue(m.is_accelerator(0x02055407))
        self.assertTrue(m.is_accelerator(0x02055827))
        self.assertFalse(m.is_accelerator(0x00052507))

    def test_handshake_and_orphan(self):
        insn = 0x02055407
        rows = [row(insn, event="arch_start", cycle=0, order=0), row(insn, event="cvx_req", cycle=1),
                row(0, event="cvx_resp", cycle=2), row(insn, cycle=3)]
        self.assertEqual(m.handshakes(rows)["requests"], 1)
        with self.assertRaises(ValueError):
            m.handshakes(rows[1:])

    def test_pin_conflict_atomic(self):
        book = m.common.PinBook()
        book.merge({"/test": "0" * 64})
        with self.assertRaises(ValueError):
            book.merge({"/new": "1" * 64, "/test": "2" * 64})
        self.assertEqual(book.pins, {"/test": "0" * 64})

    def test_scalar_prefix_rejected(self):
        result = dict(status="PREFIX", ara_trap_events=0, matched_instructions=1,
                      ara_committed_instructions=1, ara_retired_instructions=1,
                      skipped_unobservable_register_values=0, stopped_at_unobservable=None, mismatch=None)
        with self.assertRaises(ValueError):
            m.common.validate_scalar(result, 1)

    def test_target_population_and_hits(self):
        targets, metrics = [], {}
        for i in range(8):
            scope = "scope%d" % i
            targets.append(dict(scope=scope, width=143, checksum="839910393",
                                missing_points=[dict(raw_index=56 + r) for r in range(16 if i < 7 else 13)]))
            metrics[scope] = dict(width=143, checksum="839910393", bits="0")
        before = dict(metrics=dict(branch=metrics))
        sample = dict(metrics=dict(branch={s: dict(r, bits=hex(1 << (142 - 56))) for s, r in metrics.items()}))
        result = m.target_hits(before, sample, dict(rows=targets))
        self.assertEqual(result["hit_targets"], 8)
        self.assertEqual(result["intended_targets"], 125)
        metrics["scope0"]["bits"] = hex(1 << (142 - 56))
        with self.assertRaises(ValueError):
            m.target_hits(before, sample, dict(rows=targets))

    def test_target_shape_drift(self):
        before = dict(metrics=dict(branch={"scope": dict(width=143, checksum="a", bits="0")}))
        sample = dict(metrics=dict(branch={"scope": dict(width=143, checksum="b", bits="0")}))
        targets = dict(rows=[dict(scope="scope", width=143, checksum="a", missing_points=[])])
        with self.assertRaises(ValueError):
            m.target_hits(before, sample, targets)


if __name__ == "__main__":
    unittest.main()
