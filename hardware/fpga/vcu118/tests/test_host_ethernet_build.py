import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

import host_ethernet_build as build


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="eth_build_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def completed(self):
        (self.root / "build_stages.tsv").write_text("".join(n + "\tPASS\n" for n in build.STAGES))
        (self.root / "ip_status.rpt").write_text(
            "| Instance Name | Target | Required License | Generated License Level | Available License Level |\n"
            "| eth_j10 | Synthesis | tri_mode_eth_mac@2015.04 | Bought | Bought |\n")
        for name in ("eth_diag.bit", "eth_diag.ltx", "eth_diag_routed.dcp"):
            (self.root / name).write_bytes(b"mock artifact, not hardware evidence")

    def test_complete_is_not_hardware_or_programming_pass(self):
        self.completed()
        result = build.classify(self.root, 0)
        self.assertEqual(result["state"], "built_needs_manual_review_and_board_test")
        self.assertTrue(result["full_license_bitstream_generated"])
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["programming_approved"])

    def test_missing_artifact_and_nonzero_exit_fail(self):
        self.completed()
        self.assertFalse(build.classify(self.root, 1)["bitstream_generated"])
        (self.root / "eth_diag.ltx").unlink()
        self.assertFalse(build.classify(self.root, 0)["bitstream_generated"])

    def test_license_unknown_or_linking_never_full_pass(self):
        self.completed()
        for license in ("", "Design_Linking", "Hardware_Evaluation"):
            with self.subTest(license=license):
                (self.root / "ip_status.rpt").write_text(
                    "| Instance Name | Target | Required License | Generated License Level | Available License Level |\n"
                    f"| eth_j10 | Synthesis | tri_mode_eth_mac@2015.04 | {license} | {license} |\n")
                self.assertFalse(build.classify(self.root, 0)["full_license_bitstream_generated"])

    def test_stage_order_duplicate_and_missing_rejected(self):
        for text in ("ip\tPASS\n", "project\tPASS\nproject\tPASS\n", "project\tBOGUS\n"):
            (self.root / "build_stages.tsv").write_text(text)
            with self.assertRaises(ValueError):
                build.read_stages(self.root)
        (self.root / "build_stages.tsv").write_text("project\tPASS\nip\tFAIL\n")
        self.assertFalse(build.classify(self.root, 0)["bitstream_generated"])

    def test_source_copy_checks_hashes_before_and_after(self):
        source = self.root / "source.v"
        source.write_bytes(b"reviewed source\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        with mock.patch.object(build, "collect", return_value=([(source, "example/imports/test.v")], {"board": {}})), \
                mock.patch.object(build, "VENDOR", {"test.v": digest}):
            build.prepare(self.root, self.root)
            self.assertEqual((self.root / "vendor/test.v").read_bytes(), source.read_bytes())
            source.write_bytes(b"modified source\n")
            with self.assertRaisesRegex(ValueError, "Unreviewed"):
                build.prepare(self.root, self.root)

    def test_existing_directory_is_not_touched_or_uploaded(self):
        with mock.patch.object(build, "upload") as upload:
            code = build.main(["--out", str(self.root), "--upload"])
        self.assertEqual(code, 1)
        self.assertEqual(list(self.root.iterdir()), [])
        upload.assert_not_called()

    def test_console_inherited_and_no_board_actions(self):
        out = self.root / "new"
        with mock.patch.object(build, "prepare", return_value={}), \
                mock.patch.object(build.preflight, "find_vivado", return_value="vivado.bat"), \
                mock.patch.object(build.subprocess, "run", return_value=mock.Mock(returncode=1)) as run:
            self.assertEqual(build.main(["--out", str(out), str(self.root)]), 1)
        command = run.call_args.args[0]
        self.assertIn("-log", command)
        self.assertNotIn("stdout", run.call_args.kwargs)
        self.assertNotIn("stderr", run.call_args.kwargs)
        self.assertNotIn("shell", run.call_args.kwargs)
        script = (build.SOURCE / "build.tcl").read_text()
        self.assertNotIn("program_hw_devices", script)
        self.assertNotIn("open_hw_target", script)
        self.assertNotIn("SEVERITY Warning", script)
        self.assertNotIn("open_example_project", script)

    def test_tcl_build_gates(self):
        tcl = shutil.which("tclsh")
        if not tcl:
            self.skipTest("tclsh required for build API/control-flow regression")
        for case in ("success", "version_fail", "config_fail", "license_fail", "synth_fail", "pin_fail", "route_fail",
                     "drc_fail", "timing_fail", "clock_fail"):
            with self.subTest(case=case):
                output = self.root / case
                result = subprocess.run([tcl, str(build.HERE / "test_host_ethernet_build.tcl"), str(output), case],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertIn("PASS " + case, result.stdout)

    def test_snapshot_is_independent(self):
        source, board, fingerprints = build.snapshot_sources(self.root)
        self.assertEqual(build.preflight.board_contract(board / "vcu118/2.4"),
                         build.preflight.board_contract(build.preflight.BOARD))
        self.assertEqual((source / "build.tcl").read_bytes(), (build.SOURCE / "build.tcl").read_bytes())
        self.assertIn("ethernet/rtl/eth_diag_top.sv", fingerprints)

    def test_upload_excludes_generated_products(self):
        import host_axi_upload
        for name in ("build.json", "eth_diag.bit", "eth_diag_routed.dcp", "secret.lic", "protected.v"):
            (self.root / name).write_text("test fixture")
        log = self.root / "project/eth_diag.runs/ip_synth_1/runme.log"
        log.parent.mkdir(parents=True)
        log.write_text("test synthesis log")
        bundle = self.root / "bundle"
        bundle.mkdir()
        with mock.patch.object(build.tempfile, "mkdtemp", return_value=str(bundle)), \
                mock.patch.object(host_axi_upload, "git", return_value=str(self.root)), \
                mock.patch.object(host_axi_upload, "publish", return_value="test-commit") as publish:
            build.upload(self.root)
        publish.assert_called_once()
        with zipfile.ZipFile(bundle / "evidence.zip") as archive:
            self.assertEqual(set(archive.namelist()),
                             {"build.json", "run_logs/eth_diag.runs/ip_synth_1/runme.log"})

    def test_reviewed_archive_can_prepare_without_vivado(self):
        from check_ethernet_example_ctrl import EVIDENCE_COMMIT, verify_bundle
        raw = subprocess.run(["git", "show", EVIDENCE_COMMIT + ":evidence.zip"], cwd=build.HERE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if raw.returncode:
            self.skipTest("Fetch the reviewed evidence branch to run the real-source integration test")
        manifest = json.loads(subprocess.check_output(
            ["git", "show", EVIDENCE_COMMIT + ":manifest.json"], cwd=build.HERE, timeout=30))
        files = verify_bundle(raw.stdout, manifest)
        review = json.loads(files["review.json"])
        source = self.root / "preflight"
        source.mkdir()
        for name, row in review["selected"].items():
            path = source / row["source_relative"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(files[name])
        output = self.root / "prepared"
        self.assertEqual(build.main([str(source), "--prepare-only", "--out", str(output)]), 0)
        record = json.loads((output / "build.json").read_text())
        self.assertEqual(record["state"], "inputs_prepared_not_built")
        self.assertEqual({p.name for p in (output / "vendor").iterdir()}, set(build.VENDOR))


if __name__ == "__main__":
    unittest.main()
