import copy
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import check_akv_column_boundary_offline as c


def symbols():
    return dict(boundary_snapshots=0x80010000, boundary_status=0x80018000,
        boundary_trap=0x80018100, g75_result=0x80018200, num_failed=0x80018210,
        query=0x80019000, key=0x80019100, value=0x80019200,
        descriptor=0x80019300, boundary_bad=0x80002000)


def vector_fixture():
    rows, allocations, completions, commands = [], [], [], []
    config = {k: "0" for k in c.common.VECTOR_FIELDS}
    config.update(event="config", nr_lanes="4", vlen_bits="1024")
    rows.append(config)
    seq = cycle = 0
    def group(word, use, vd, vl, phase=None, seed=False):
        nonlocal seq, cycle
        metadata = dict(config, event="alloc", cycle=str(cycle), arch_seq=str(seq), vid="0", insn="%08x" % word,
                        use_vd=str(use), vd=str(vd), eew="1", vl=str(vl), vstart="0")
        rows.append(metadata)
        allocations.append(dict(order=seq, cycle=cycle, port=0, insn=word))
        if phase is not None:
            commands.append(dict(seq=seq, phase=phase, word=word))
        if seed or phase in (1,3,4,5,6):
            for chunk in range(4):
                for lane in range(4):
                    value = 0
                    for byte in range(8):
                        slot, within = divmod(byte, 2)
                        natural = ((slot&1)<<1) | (slot>>1)
                        offset = chunk*32+(natural*4+lane)*2+within
                        half = 0x1000+64*vd+offset//2 if seed else (
                            0x343f if offset//2 == 0 else 0) if phase in (1,3) else {4:0x2400,5:0x3400,6:0x4400}[phase]+offset//2
                        value |= half.to_bytes(2, "little")[offset%2] << (8*byte)
                    cycle += 1
                    rows.append(dict(metadata, event="write", cycle=str(cycle), lane=str(lane),
                                     addr=str(vd*4+chunk), be="ff", wdata="%016x" % value))
        cycle += 1
        rows.append(dict(metadata, event="done", cycle=str(cycle)))
        completions.append(dict(order=seq, cycle=cycle, port=0, insn=word))
        cycle += 1; seq += 1
    def snapshot():
        for r in range(32): group(0x02055027 | (r<<7), 0, 0, 64)
    for r in range(32): group(0x02055007 | (r<<7), 1, r, 64, seed=True)
    for phase, word in enumerate(c.WORDS):
        use = int(phase in (1,2,3,4,5,6))
        vd = {1:8,2:8,3:8,4:10,5:12,6:14}.get(phase, 0)
        group(word, use, vd, 64 if use else 1, phase=phase)
        if phase in (1,2,3,7): snapshot()
    return rows, dict(commands=commands, uops=allocations, completions=completions)


class CollectorTest(unittest.TestCase):
    def commands(self):
        return [dict(word=w, fault=int(i == 2)) for i, w in enumerate(c.WORDS)]

    def test_expected_eight_outcomes(self):
        c.command_faults(self.commands())

    def test_reject_other_fault(self):
        records = self.commands(); records[3]["fault"] = 1
        with self.assertRaises(ValueError): c.command_faults(records)

    def test_reject_swallowed_expected_fault(self):
        records = self.commands(); records[2]["fault"] = 0
        with self.assertRaises(ValueError): c.command_faults(records)

    def test_reject_missing_release(self):
        with self.assertRaises(ValueError): c.command_faults(self.commands()[:-1])

    def test_reject_wrong_row_destination(self):
        records = self.commands(); records[5]["word"] ^= 128
        with self.assertRaises(ValueError): c.command_faults(records)

    def test_independent_full_vrf_and_trap(self):
        syms = symbols(); wanted = c.expected_memory(syms)
        def read(name, length):
            return bytes(wanted[syms[name]+i] for i in range(length))
        self.assertEqual(read("boundary_trap", 32), struct.pack("<4Q", 1, 2, syms["boundary_bad"], 0))
        snapshots = struct.unpack("<8192H", read("boundary_snapshots", 16384))
        self.assertEqual(snapshots[:2048], snapshots[2048:4096])
        self.assertEqual(snapshots[:2048], snapshots[4096:6144])
        self.assertEqual(snapshots[6144+10*64:6144+11*64], tuple(range(0x2400, 0x2440)))
        self.assertEqual(snapshots[6144+12*64:6144+13*64], tuple(range(0x3400, 0x3440)))
        self.assertEqual(snapshots[6144+14*64:6144+15*64], tuple(range(0x4400, 0x4440)))
        self.assertEqual(read("g75_result", 8), struct.pack("<2I", 8396, 0))

    def test_descriptor_independent_layout(self):
        s = symbols(); memory = c.expected_memory(s)
        data = bytes(memory[s["descriptor"]+i] for i in range(64))
        self.assertEqual(struct.unpack("<4B2H4I5Q", data),
            (1,1,1,0,64,1,128,128,128,0,s["query"],s["key"],s["value"],0,0))

    def test_rvfi_unshifted_bytes(self):
        self.assertEqual(c.legacy.scalar_store_bytes(0x102, 0x343f, 0x0c), [(0x102,0x3f),(0x103,0x34)])
        with self.assertRaises(ValueError): c.legacy.scalar_store_bytes(0x102, 0, 0x03)

    def test_reject_unknown_commit_event(self):
        record = {key: "0" for key in c.common.COMMIT_FIELDS}
        record["event"] = "unknown"
        with patch.object(c.common, "read_csv", return_value=[record]):
            with self.assertRaises(ValueError): c.commit_rows(Path("unused"))

    def test_reject_partial_retirement(self):
        record = {key: "0" for key in c.common.COMMIT_FIELDS}
        record.update(event="retire", order="1")
        with patch.object(c.common, "read_csv", return_value=[record]):
            with self.assertRaises(ValueError): c.commit_rows(Path("unused"))

    def test_reject_native_reset(self):
        record = {k:"0" for k in c.common.VECTOR_FIELDS}
        record.update(event="config", nr_lanes="4", vlen_bits="1024")
        reset = dict(record, event="reset")
        with patch.object(c.common, "read_csv", return_value=[record, reset]):
            with self.assertRaises(ValueError): c.vector_audit(Path("unused"), {})

    def test_reject_noncompletion_stdout(self):
        for text in ("", "Core Test *** SUCCESS ***\n"*2, "Error: real failure\n"):
            with self.assertRaises(ValueError): c.stdout_audit(text)

    def test_does_not_execute_reference_or_sim(self):
        source = Path(c.__file__).read_text()
        self.assertNotIn("subprocess.run", source)
        self.assertNotIn("compare_commit_prefix(", source)
        self.assertIn("full_scalar_differential_qualified=False", source)

    def test_full_native_vector_positive(self):
        rows, arch = vector_fixture()
        with patch.object(c.common, "read_csv", return_value=rows):
            result = c.vector_audit(Path("unused"), arch)
        self.assertEqual(result["custom_destination_bytes"], 640)
        self.assertEqual(result["rejected_write_bytes"], 0)

    def test_reject_bad_column_write_even_with_reserved_vd(self):
        rows, arch = vector_fixture()
        seq = arch["commands"][2]["seq"]
        index = next(i for i, r in enumerate(rows) if r["event"] == "done" and int(r["arch_seq"]) == seq)
        rows.insert(index, dict(rows[index], event="write", addr="32", be="01", wdata="0"))
        with patch.object(c.common, "read_csv", return_value=rows):
            with self.assertRaises(ValueError): c.vector_audit(Path("unused"), arch)

    def test_reject_wrong_guard_seed(self):
        rows, arch = vector_fixture()
        index = next(i for i, r in enumerate(rows) if r["event"] == "write" and r["vd"] == "31")
        rows[index]["wdata"] = "%016x" % (int(rows[index]["wdata"], 16)^1)
        with patch.object(c.common, "read_csv", return_value=rows):
            with self.assertRaises(ValueError): c.vector_audit(Path("unused"), arch)

    def test_reject_partial_recovery_vrf(self):
        rows, arch = vector_fixture()
        seq = arch["commands"][3]["seq"]
        index = next(i for i, r in enumerate(rows) if r["event"] == "write" and int(r["arch_seq"]) == seq)
        rows[index]["be"] = "fe"
        with patch.object(c.common, "read_csv", return_value=rows):
            with self.assertRaises(ValueError): c.vector_audit(Path("unused"), arch)

    def test_reject_missing_backend_done(self):
        rows, arch = vector_fixture(); rows.pop()
        with patch.object(c.common, "read_csv", return_value=rows):
            with self.assertRaises(ValueError): c.vector_audit(Path("unused"), arch)


if __name__ == "__main__":
    unittest.main()
