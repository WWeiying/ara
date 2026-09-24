#!/usr/bin/env python3
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "software"))
import host_burst_read_map as probe


class Memory:
    def __init__(self, mode="normal"):
        self.mode = mode
        self.calls = 0

    def exchange(self, operations):
        self.calls += 1
        result = []
        for op in operations:
            if op.bus != "M" or op.kind != "READ" or op.data:
                raise AssertionError("Probe must be memory-read-only")
            if not any(base <= op.address and op.address + 8*op.beats <= base + 256
                       for base in (0xffff0000, 0x1401ff00)):
                raise AssertionError("Read outside probe window")
            op.wire()
            if self.mode == "failure" and op.beats > 1:
                raise RuntimeError("mock transport failure")
            stride = 72 if self.mode == "stride72" else 8
            words = [(op.address + stride*i).to_bytes(8, "little") for i in range(op.beats)]
            if op.burst == "FIXED":
                words = [op.address.to_bytes(8, "little")] * op.beats
            if self.mode == "line_advance" and op.burst == "INCR":
                words = [((op.address & ~63) + 64*i + ((op.address + 8*i) & 63)).to_bytes(8, "little")
                         for i in range(op.beats)]
            if self.mode == "duplicate":
                words = [b"\x55" * 8] * op.beats
            if self.mode == "stale" and op.beats > 1:
                words[1] = b"\xaa" * 8
            if self.mode == "changed" and self.calls == 9:
                words[0] = b"\x66" * 8
            result.append(b"".join(words))
        return result


class ProbeTests(unittest.TestCase):
    def run_map(self, mode):
        report = {"regions": []}
        probe.collect(Memory(mode), report)
        self.assertEqual(len(report["regions"]), 2)
        self.assertTrue(all(len(r["rows"]) == 7 for r in report["regions"]))
        return report["regions"]

    def test_correct_mapping(self):
        for region in self.run_map("normal"):
            self.assertTrue(region["stable"])
            for row in region["rows"]:
                base = int(row["address"], 16)
                self.assertEqual(row["matches"], [[hex(base + 8*i)] for i in range(row["beats"])])

    def test_stride72_mapping(self):
        for region in self.run_map("stride72"):
            self.assertTrue(region["stable"])
            for row in region["rows"]:
                base = int(row["address"], 16)
                self.assertEqual(row["matches"], [[hex(base + 72*i)] for i in range(row["beats"])])

    def test_reported_board_pattern_is_not_constant_stride(self):
        expected = ((0, 0x48), (8, 0x50), (0x38, 0x40), (0x40, 0x88),
                    (0, 0x48, 0x90), (0x38, 0x40, 0x88), (0, 0x48))
        for region in self.run_map("line_advance"):
            self.assertTrue(region["stable"])
            base = int(region["base"], 16)
            for row, offsets in zip(region["rows"], expected):
                self.assertEqual(row["matches"], [[hex(base + offset)] for offset in offsets])
            self.assertNotEqual(region["rows"][2]["matches"][1], [hex(base + 0x38 + 72)])

    def test_fixed_probe_keeps_address_constant(self):
        report = {"regions": []}
        probe.collect(Memory("line_advance"), report, fixed_probe=True)
        for region in report["regions"]:
            self.assertTrue(region["stable"])
            self.assertEqual(len(region["fixed_rows"]), 2)
            for row in region["fixed_rows"]:
                self.assertEqual(row["matches"], [[row["address"]]] * row["beats"])

    def test_no_false_attribution_for_stale_data(self):
        for region in self.run_map("stale"):
            self.assertTrue(all(row["matches"][1] == [] for row in region["rows"]))

    def test_duplicate_data_remains_ambiguous(self):
        for region in self.run_map("duplicate"):
            self.assertTrue(all(len(row["matches"][1]) == 32 for row in region["rows"]))

    def test_changing_memory_marked_unstable(self):
        regions = self.run_map("changed")
        self.assertFalse(regions[0]["stable"])

    def test_partial_failure_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "probe"
            memory = Memory("failure")
            with patch.object(probe, "VivadoTransport") as transport, \
                 patch.object(probe, "identity", return_value={"caps": 1}), \
                 patch.object(probe, "read_debug", return_value=[7]), \
                 contextlib.redirect_stdout(io.StringIO()):
                transport.return_value.__enter__.return_value = memory
                with self.assertRaisesRegex(RuntimeError, "mock transport"):
                    probe.main("dummy.ltx", output)
            report = json.loads((output / "map.json").read_text())
            self.assertFalse(report["memory_writes"])
            self.assertEqual(len(report["regions"][0]["before"]), 32)
            self.assertIsNone(report["regions"][0]["stable"])
            self.assertIn("error", report)


class CliTests(unittest.TestCase):
    def test_auto_output_is_unique_and_not_precreated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            probes = root / "matching.ltx"
            probes.touch()
            with patch.object(probe.Path, "cwd", return_value=root), \
                 patch.object(probe, "main") as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.cli([str(probes)]), 0)
                self.assertEqual(probe.cli([str(probes)]), 0)
            outputs = [call.args[1] for call in run.call_args_list]
            self.assertNotEqual(*outputs)
            for output in outputs:
                self.assertFalse(output.exists())
                self.assertEqual(output.parent.parent, root / "burst_maps")

    def test_explicit_output_and_vivado(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes = Path(tmp) / "matching.ltx"
            probes.touch()
            output = Path(tmp) / "evidence"
            with patch.object(probe, "main") as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.cli([str(probes), str(output), "--vivado", "vivado.bat"]), 0)
            run.assert_called_once_with(probes.resolve(), output.resolve(),
                                        vivado="vivado.bat", fixed_probe=False)

    def test_fixed_probe_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes = Path(tmp) / "matching.ltx"
            probes.touch()
            output = Path(tmp) / "evidence"
            with patch.object(probe, "main") as run, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe.cli([str(probes), str(output), "--fixed-probe"]), 0)
            run.assert_called_once_with(probes.resolve(), output.resolve(),
                                        vivado="vivado", fixed_probe=True)

    def test_missing_probes_does_not_connect(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(probe, "main") as run, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                probe.cli([str(Path(tmp) / "missing.ltx")])
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_failure_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            probes = Path(tmp) / "matching.ltx"
            probes.touch()
            with patch.object(probe, "main", side_effect=RuntimeError("mock failure")), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(probe.cli([str(probes), str(Path(tmp) / "out")]), 1)


if __name__ == "__main__":
    unittest.main()
