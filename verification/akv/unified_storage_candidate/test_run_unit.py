"""Host evidence/graph checks; these do not simulate or prove the RTL."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("unified_storage_unit", HERE / "run_unit.py")
unit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(unit)


class UnitEvidenceTests(unittest.TestCase):
    def test_exact_completion(self):
        self.assertEqual(unit.check_log("VCS simulation\n" + unit.MARKER + "\n", 0), unit.EXPECTED)

    def test_missing_duplicate_bad_count_and_bad_exit(self):
        for text, code in [("", 0), (unit.MARKER + "\n" + unit.MARKER, 0),
                           (unit.MARKER.replace("aborts=9", "aborts=8"), 0),
                           (unit.MARKER, 1), ("prefix " + unit.MARKER, 0),
                           (unit.MARKER + "\nFatal: failed", 0),
                           (unit.MARKER + "\nError-[assert]", 0)]:
            with self.subTest(text=text, code=code), self.assertRaises(ValueError):
                unit.check_log(text, code)

    def test_pin_drift_missing_and_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_bytes(b"sealed")
            identity = unit.pins([source])
            unit.verify(identity)
            source.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                unit.verify(identity)
            source.unlink()
            with self.assertRaises(FileNotFoundError):
                unit.verify(identity)
            with self.assertRaises(ValueError):
                unit.verify({})

    def test_accepted_repacker_receipt_and_mutations(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            repacker = out / "repacker.sv"
            repacker.write_bytes(b"accepted fixture")
            sources = out / "source-pins.json"
            unit.save(sources, unit.pins([repacker]))
            for name in ("compile.log", "positive.log", "simv"):
                (out / name).write_bytes(name.encode())
            evidence = unit.pins([sources, *(out / name for name in
                                            ("compile.log", "positive.log", "simv"))])
            report = {"state": "PASS", "evidence": evidence}
            with mock.patch.object(unit, "REPACKER_SHA", unit.sha(repacker)):
                unit.save(out / "result.json", report)
                self.assertIn(repacker, unit.accepted_inputs(out, repacker))
                for missing in evidence:
                    unit.save(out / "result.json", {"state": "PASS", "evidence":
                              {p: value for p, value in evidence.items() if p != missing}})
                    with self.subTest(missing=missing), self.assertRaises(ValueError):
                        unit.accepted_inputs(out, repacker)
                unit.save(out / "result.json", {**report, "state": "FAIL"})
                with self.assertRaises(ValueError):
                    unit.accepted_inputs(out, repacker)
                unit.save(out / "result.json", report)
                (out / "positive.log").write_bytes(b"drift")
                with self.assertRaises(ValueError):
                    unit.accepted_inputs(out, repacker)

    def test_review_identity_required_no_eda(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            unit.save(out / "manifest.json", {"output": str(out)})
            with mock.patch.object(unit, "run") as runner:
                with self.assertRaises(ValueError):
                    unit.execute(out, "0" * 64)
                runner.assert_not_called()

    def test_terminal_cannot_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            unit.save(out / "manifest.json", {"output": str(out)})
            for state in ("PASS", "FAIL", "TIMEOUT", "BUILDING", "RUNNING"):
                unit.save(out / "status.json", {"state": state})
                with mock.patch.object(unit, "run") as runner:
                    with self.subTest(state=state), self.assertRaises(ValueError):
                        unit.execute(out, unit.sha(out / "manifest.json"))
                    runner.assert_not_called()

    def test_real_graph_and_accepted_inputs(self):
        generic = unit.source_graph("tc")
        macro = unit.source_graph("macro")
        self.assertEqual(len(generic), 8)
        self.assertEqual(len(macro), 10)
        self.assertEqual(len([p for p in generic if p.name == "akv_v2_context.sv"]), 1)
        self.assertEqual(len([p for p in generic if p.name == "akv_legacy_repacker.sv"]), 1)
        self.assertNotIn("tc_sram.sv", [p.name for p in macro])
        self.assertEqual(sum(p.suffix == ".v" for p in macro), 3)
        self.assertEqual(unit.sha(unit.REPACKER), unit.REPACKER_SHA)
        self.assertIn(unit.REPACKER, unit.accepted_inputs())
        with self.assertRaises(ValueError):
            unit.source_graph("unknown")

    def test_expected_work_arithmetic(self):
        counts = unit.EXPECTED
        # All 24 rows, 3 streams x 3 lengths x 8 alignments, eight v2 Q, recovery.
        self.assertEqual(counts["legacy_rows"], 24 + 3 * 3 * 8 + 8 + 1)
        writes = 24 * 256 // 16 + 3 * 8 * (128 + 192 + 256) // 16 + 8 * 192 // 16
        self.assertEqual(counts["legacy_writes"], writes + 1 + 256 // 16)
        self.assertEqual(counts["direct_writes"], 2 * 64 * 256 // 16)
        self.assertEqual(counts["row_checks"], 192 + 576 + 64 + 1024 + 128 + 9 * 72 + 72)
        self.assertEqual(counts["column_checks"], 2 * 6 * 6)
        self.assertEqual(counts["q_bytes"], 64 * 256 // 8)
        self.assertEqual(counts["kv_bytes"], 8 * 128 * 256 // 8)
        self.assertIn('"' + unit.MARKER + '"', (HERE / "unified_storage_tb.sv").read_text())


if __name__ == "__main__":
    unittest.main()
