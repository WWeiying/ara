import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.probes import REQUIRED_PAYLOAD, ProbeError, check_probe_capture, parse_probe
from ara_verify.plan import audit_run


def fixture(kind="mmu"):
    text = (
        f"# CVA6_STATE_PREREQ version=1 kind={kind} instance=tb.probe max_rows=8192\n"
        "# sample=pre_edge input_skew=1step edge_time_unit=ns cycle_origin=first_posedge\n"
        "cycle=0 epoch=0 edge_time_ns=5.000 row=0 rst_n=0 activity=0 gap=0 req=x\n"
        "cycle=2 epoch=1 edge_time_ns=25.000 row=1 rst_n=1 activity=1 gap=1 req=1\n"
        "cycle=3 epoch=1 edge_time_ns=35.000 row=2 rst_n=1 activity=0 gap=0 req=0\n"
        "# END sim_final=1 rows=3 limit=8192 truncated=0 dropped=0 sampled_edges=9 activity_edges=1 epoch=1\n"
    )
    extra = "".join(f" {key}={1 if key in ('schema', 'issue_ports') else 0}"
                    for key in sorted(REQUIRED_PAYLOAD[kind] - {"req"}))
    return "\n".join(line + extra if line.startswith("cycle=") else line for line in text.splitlines()) + "\n"


class ProbeTests(unittest.TestCase):
    def test_complete_capture_includes_gaps_and_reset(self):
        result = parse_probe(fixture(), "mmu")
        self.assertEqual(3, result["rows"])
        self.assertEqual(9, result["sampled_edges"])

    def test_all_schemas_require_their_declared_signals(self):
        for kind, signals in REQUIRED_PAYLOAD.items():
            with self.subTest(kind=kind):
                self.assertEqual(3, parse_probe(fixture(kind), kind)["rows"])
                for signal in signals - {"req"}:
                    with self.subTest(signal=signal):
                        with self.assertRaises(ProbeError):
                            value = 1 if signal in ("schema", "issue_ports") else 0
                            parse_probe(fixture(kind).replace(f" {signal}={value}", ""), kind)

    def test_trap_schema_and_second_issue_port(self):
        for kind in ("trap_decode", "trap_ctrl"):
            with self.assertRaises(ProbeError):
                parse_probe(fixture(kind).replace(" schema=1", " schema=2"), kind)
        for ports in (0, 2, 3):
            with self.assertRaises(ProbeError):
                parse_probe(fixture("trap_decode").replace(" issue_ports=1", f" issue_ports={ports}"), "trap_decode")
        second = "".join(f" p1_{key[3:]}=0" for key in sorted(REQUIRED_PAYLOAD["trap_decode"]) if key.startswith("p0_"))
        text = "\n".join(line + second if line.startswith("cycle=") else line
                         for line in fixture("trap_decode").replace(" issue_ports=1", " issue_ports=2").splitlines())
        self.assertEqual(3, parse_probe(text, "trap_decode")["rows"])

    def test_bad_capture_matrix(self):
        original = fixture()
        mutations = [
            original.split("# END")[0], original + original.splitlines()[-1] + "\n",
            original + original.splitlines()[2] + "\n",
            original.replace("version=1", "version=2"), original.replace("kind=mmu", "kind=csr"),
            original.replace("input_skew=1step", "input_skew=0"),
            original.replace("row=1", "row=0"), original.replace("gap=1", "gap=0"),
            original.replace("activity=1", "activity=x"), original.replace("epoch=1", "epoch=-1"),
            original.replace("epoch=1 edge_time_ns=35", "epoch=0 edge_time_ns=35"),
            original.replace("25.000", "4.000"), original.replace("25.000", "nan"),
            original.replace("truncated=0", "truncated=1"), original.replace("dropped=0", "dropped=1"),
            original.replace("rows=3", "rows=2"), original.replace("limit=8192", "limit=8"),
            original.replace("sampled_edges=9", "sampled_edges=3"),
            original.replace("activity_edges=1", "activity_edges=2"),
            original.replace("sim_final=1", "sim_final=0"),
            original.replace(" req=1", " req=1 req=0"),
            original.replace("# END", "# TRUNCATED reason=limit\n# END"),
            original.replace(" va=0", ""),
        ]
        for text in mutations:
            with self.subTest(text=text):
                with self.assertRaises(ProbeError):
                    parse_probe(text, "mmu")

    def test_row_at_exact_bound_is_not_automatically_truncated(self):
        text = fixture().replace("8192", "3").replace("# END", "# LIMIT_REACHED cycle=3 rows=3\n# END")
        self.assertEqual(3, parse_probe(text, "mmu")["rows"])

    def test_files_missing_duplicate_and_wrong_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual("FAIL", check_probe_capture(root, ["mmu"])["status"])
            (root / "state_prereq.mmu.log").write_text(fixture())
            self.assertEqual("PASS", check_probe_capture(root, ["mmu"])["status"])
            (root / "state_prereq.mmu.log.1").write_text(fixture())
            self.assertEqual("FAIL", check_probe_capture(root, ["mmu"])["status"])
            (root / "state_prereq.mmu.log.1").unlink()
            (root / "state_prereq.csr.log").write_text(fixture("csr").replace("sampled_edges=9", "sampled_edges=10"))
            self.assertEqual("FAIL", check_probe_capture(root, ["mmu", "csr"])["status"])
            self.assertEqual("FAIL", check_probe_capture(root, ["mmu", "mmu"])["status"])
            self.assertEqual("FAIL", check_probe_capture(root, ["../mmu"])["status"])

    def test_cross_kind_same_cycle_requires_same_time_and_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "state_prereq.mmu.log").write_text(fixture())
            other = root / "state_prereq.csr.log"
            other.write_text(fixture("csr"))
            self.assertEqual("PASS", check_probe_capture(root, ["mmu", "csr"])["status"])
            for text in (fixture("csr").replace("25.000", "45.000").replace("35.000", "65.000"),
                         fixture("csr").replace("rst_n=1", "rst_n=0")):
                other.write_text(text)
                result = check_probe_capture(root, ["mmu", "csr"])
                self.assertEqual("FAIL", result["status"])
                self.assertIn("conflicting time/reset/epoch", str(result))

    def test_audit_rechecks_content_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "tests/case"
            work = artifact / "work"
            work.mkdir(parents=True)
            (root / "run.json").write_text(json.dumps({"status": "COMPLETE", "invocation": ["verify"],
                "git": {"commit": "abc"}, "probe_kinds": ["mmu"]}))
            (root / "summary.json").write_text(json.dumps([{"name": "case", "status": "PASS", "artifact_dir": str(artifact)}]))
            (artifact / "command.json").write_text("{}")
            log = work / "state_prereq.mmu.log"
            log.write_text(fixture())
            (artifact / "probe_capture.json").write_text(json.dumps(check_probe_capture(work, ["mmu"])))
            self.assertEqual("PASS", audit_run(root)["status"])
            log.write_text(fixture().replace("req=1", "req=0"))
            result = audit_run(root)
            self.assertEqual("FAIL", result["status"])
            self.assertIn("probe capture evidence missing or changed", str(result))

    def test_runner_rejects_missing_requested_probes(self):
        from ara_verify.runner import RegressionRunner, RunOptions
        from ara_verify.model import TestCase
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binary = root / "case.elf"
            binary.write_bytes(b"ELF")
            simv = root / "simv"
            simv.write_bytes(b"SIMV")
            options = RunOptions(root, root / "out", "default", 1, 1, False, False, True,
                                 simv, False, 20, probe_kinds=("mmu",))
            test = TestCase("case", "rvv", "case", binary, "case", 20)
            runner = RegressionRunner(options, [test], ["verify"])
            def run(command, cwd, log, *args):
                log.write_text("Core Test *** SUCCESS *** (tohost = 0)\n")
                return 0, 0.1, False, False
            with patch("ara_verify.runner._run_monitored", side_effect=run):
                result = runner._run_test(test, simv)
            self.assertEqual("FAIL", result.status)
            self.assertIn("probe capture", result.reason)


if __name__ == "__main__":
    unittest.main()
