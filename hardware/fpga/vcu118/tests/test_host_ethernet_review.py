import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import host_ethernet_review as review


XCI = '''<?xml version="1.0"?>
<spirit:design xmlns:spirit="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009">
  <spirit:componentInstances><spirit:componentInstance>
    <spirit:componentRef spirit:vendor="xilinx.com" spirit:library="ip" spirit:name="axi_ethernet" spirit:version="7.2"/>
    <spirit:configurableElementValues>
      <spirit:configurableElementValue spirit:referenceId="PARAM_VALUE.PHY_TYPE">SGMII</spirit:configurableElementValue>
      <spirit:configurableElementValue spirit:referenceId="MODELPARAM_VALUE.C_LVDS_CLK_FREQ">625</spirit:configurableElementValue>
    </spirit:configurableElementValues>
  </spirit:componentInstance></spirit:componentInstances>
</spirit:design>
'''


class EthernetReviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "preflight with spaces"
        self.source.mkdir()
        self.example = self.source / "example/eth_j10_ex"
        self.original = "D:/fpga_runs/ara_eth_fixture"
        self.record = {
            "state": review.PREFLIGHT_STATE, "vivado_exit_code": 0,
            "stages": dict.fromkeys(review.preflight.STAGES, "PASS"),
            "requested_config": review.preflight.CONFIG,
            "board": review.preflight.board_contract(review.preflight.BOARD),
            "command": ["vivado.bat", "-tclargs", self.original, "D:/board_files"],
            "tools_sha256": {"fixture": "fixture"},
        }
        for name in review.preflight.UPLOAD_FILES:
            (self.source / name).write_text("fixture\n", encoding="utf-8")
        self.write_record()
        (self.source / "stages.tsv").write_text("".join(f"{key}\tPASS\r\n" for key in review.preflight.STAGES))
        (self.source / "ip_status_after.rpt").write_text(
            "| Instance Name | Target | Required License | Generated License Level | Available License Level |\n"
            "| eth_j10 | Synthesis | tri_mode_eth_mac@2015.04 | Bought | Bought |\n")
        self.entries = []
        for name in review.IMPORTS:
            self.add_file("Verilog", "imports/" + name, "// generated example fixture\nmodule fixture; endmodule\n")
        for name in review.IMPORT_XDC:
            self.add_file("XDC", "imports/" + name, "# XDC fixture; never executed\n")
        self.add_file("XDC", str(review.IP_ROOT / "eth_j10_board.xdc"), "# board scope\n")
        self.add_file("XDC", str(review.IP_ROOT / "synth/eth_j10_ooc.xdc"), "# OOC scope\n")
        self.add_file("IP", str(review.IP_ROOT / "eth_j10.xci"), XCI)
        self.add_file("IP", str(review.IP_ROOT / "bd_0/ip/ip_1/bd_1234_pcs_pma_0.xci"), XCI.replace("axi_ethernet", "gig_ethernet_pcs_pma"))
        self.add_file("Verilog", str(review.IP_ROOT / "hdl/vendor_rfs.v"), "`pragma protect begin_protected\nsecret\n")
        self.add_file("Verilog", "imports/eth_j10_demo_tb.v", "// simulation only, not selected\n")
        self.add_file("Verilog Template", str(review.IP_ROOT / "eth_j10.veo"), "// instantiation template\n")
        self.add_file("Unknown", "private.lic", "INCREMENT secret xilinxd 9999 permanent\n")
        self.add_file("Unknown", "design.bit", "binary excluded\n")
        (self.example / "eth_j10_ex.xpr").write_text(
            '<Project><Configuration><Option Name="Part" Val="xcvu9p-flga2104-2L-e"/>'
            '<Option Name="Unrelated" Val="skip summary"/></Configuration></Project>')
        self.write_report()
        self.bundle = self.root / "review bundle"
        self.bundle.mkdir()

    def add_file(self, kind, relative, content):
        path = self.example / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.entries.append(f"EXAMPLE_FILE {kind} {self.original}/example/eth_j10_ex/{relative}")

    def write_record(self):
        (self.source / "preflight.json").write_text(json.dumps(self.record), encoding="utf-8-sig")

    def write_report(self):
        xdc_count = sum(line.startswith("EXAMPLE_FILE XDC ") for line in self.entries)
        (self.source / "preflight.rpt").write_text(
            "EXAMPLE_PROJECT eth_j10_ex\r\n" + "\r\n".join(self.entries) +
            f"\r\nEXAMPLE_FILES={len(self.entries)} XDC_FILES={xdc_count}\r\nPREFLIGHT_COMPLETE\r\n",
            encoding="utf-8")

    def snapshot(self):
        return {str(path.relative_to(self.source)): path.read_bytes()
                for path in self.source.rglob("*") if path.is_file()}

    def run_main(self, *args):
        output = io.StringIO()
        with mock.patch.object(review.tempfile, "mkdtemp", return_value=str(self.bundle)), \
                mock.patch.object(review.evidence, "git", return_value="fixture-repo"), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = review.main([str(self.source), *args])
        return code, output.getvalue()

    def test_relocated_windows_inventory_and_exact_allowlist(self):
        before = self.snapshot()
        files, result = review.collect(self.source)
        members = {name for _, name in files}
        self.assertEqual(result["counts"], {"example_hdl": 17, "xdc": 4, "ip_config": 2})
        self.assertIn("example/imports/eth_j10_example.v", members)
        self.assertIn("example/eth_j10_ex.xpr", members)
        for forbidden in ("vendor_rfs.v", "demo_tb.v", ".lic", ".bit", ".veo"):
            self.assertFalse(any(forbidden in name for name in members))
        self.assertEqual(result["license_report"]["state"], "full_reported_not_bitstream_verified")
        self.assertEqual(result["project_options"], [{"Name": "Part", "Val": "xcvu9p-flga2104-2L-e"}])
        self.assertFalse(result["build_ready"])
        self.assertFalse(result["hardware_verified"])
        self.assertEqual(before, self.snapshot())

    def test_windows_backslashes_and_drive_case(self):
        self.entries = [line.replace("D:/", "d:/").replace("/", "\\") for line in self.entries]
        self.write_report()
        _, result = review.collect(self.source)
        self.assertEqual(result["counts"]["example_hdl"], 17)

    def test_posix_inventory(self):
        self.record["command"][-2] = "/tmp/preflight"
        self.write_record()
        self.entries = [line.replace(self.original, "/tmp/preflight") for line in self.entries]
        self.write_report()
        review.collect(self.source)

    def test_ip_xact_parameter_extraction_and_unknown_schema(self):
        config = review.config_summary(XCI)
        self.assertTrue(config["recognized"])
        self.assertEqual(config["parameters"]["PARAM_VALUE.PHY_TYPE"], "SGMII")
        self.assertEqual(config["components"][0]["version"], "7.2")
        self.assertFalse(review.config_summary("<unknown/>")["recognized"])
        with self.assertRaises(ValueError):
            review.config_summary(XCI.replace("MODELPARAM_VALUE.C_LVDS_CLK_FREQ", "PARAM_VALUE.PHY_TYPE"))
        with self.assertRaises(ValueError):
            review.config_summary('<!DOCTYPE x [<!ENTITY e "text">]><x/>')

    def test_failed_or_different_preflight_rejected(self):
        for key, value in (("state", "failed"), ("vivado_exit_code", 1),
                           ("stages", {}), ("requested_config", {}), ("board", {})):
            with self.subTest(key=key):
                original = self.record[key]
                self.record[key] = value
                self.write_record()
                with self.assertRaises(ValueError):
                    review.collect(self.source)
                self.record[key] = original
                self.write_record()

    def test_missing_file_or_required_inventory_entry_rejected(self):
        path = self.example / "imports/eth_j10_clocks_resets.v"
        path.unlink()
        with self.assertRaises(OSError):
            review.collect(self.source)
        self.entries = [line for line in self.entries if "eth_j10_clocks_resets.v" not in line]
        self.write_report()
        with self.assertRaisesRegex(ValueError, "Required integration files"):
            review.collect(self.source)

    def test_external_path_and_traversal_rejected(self):
        original = list(self.entries)
        for path in ("D:/private/eth_j10_example.v",
                     self.original + "/example/eth_j10_ex/imports/../private.v"):
            with self.subTest(path=path):
                self.entries = ["EXAMPLE_FILE Verilog " + path] + original[1:]
                self.write_report()
                with self.assertRaises(ValueError):
                    review.collect(self.source)

    def test_symlink_file_and_parent_rejected(self):
        path = self.example / "imports/eth_j10_example.v"
        path.unlink()
        target = self.root / "private.v"
        target.write_text("private")
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "linked input"):
            review.collect(self.source)
        path.unlink()
        path.write_text("restored fixture")
        imports = self.example / "imports"
        imports.rename(self.root / "moved imports")
        imports.symlink_to(self.root / "moved imports", target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "linked input"):
            review.collect(self.source)

    def test_duplicate_inventory_or_wrong_xdc_count_rejected(self):
        self.entries.append(self.entries[0])
        self.write_report()
        with self.assertRaisesRegex(ValueError, "Duplicate inventory"):
            review.collect(self.source)
        self.entries.pop()
        self.write_report()
        report = self.source / "preflight.rpt"
        report.write_text(report.read_text().replace("XDC_FILES=4", "XDC_FILES=999"))
        with self.assertRaisesRegex(ValueError, "counts disagree"):
            review.collect(self.source)

    def test_partial_completion_or_stage_mismatch_rejected(self):
        report = self.source / "preflight.rpt"
        report.write_text(report.read_text().replace("PREFLIGHT_COMPLETE", "INTERRUPTED"))
        with self.assertRaisesRegex(ValueError, "completion marker"):
            review.collect(self.source)
        self.write_report()
        (self.source / "stages.tsv").write_text("console\tFAIL\n")
        with self.assertRaisesRegex(ValueError, "Stage file differs"):
            review.collect(self.source)

    def test_protected_or_binary_content_under_allowed_name_rejected(self):
        path = self.example / "imports/eth_j10_example.v"
        for content in (b'`pragma protect begin_protected\nsecret',
                        b'INCREMENT secret xilinxd 9999 permanent',
                        b'-----BEGIN RSA PRIVATE KEY-----', b'\x00binary', b''):
            with self.subTest(content=content):
                path.write_bytes(content)
                with self.assertRaises(ValueError):
                    review.collect(self.source)

    def test_size_and_count_limits(self):
        for name, limit in (("MAX_FILE_BYTES", 2), ("MAX_TOTAL_BYTES", 2), ("MAX_FILES", 1)):
            with self.subTest(name=name), mock.patch.object(review, name, limit):
                with self.assertRaises(ValueError):
                    review.collect(self.source)

    def test_default_packages_locally_without_publish_or_vivado(self):
        before = self.snapshot()
        with mock.patch.object(review.evidence, "publish") as publish, \
                mock.patch.object(review.preflight.subprocess, "run", side_effect=AssertionError("No tools expected")):
            code, output = self.run_main()
        self.assertEqual(code, 0, output)
        publish.assert_not_called()
        self.assertIn("PACKAGED_ONLY", output)
        self.assertEqual(before, self.snapshot())
        manifest = json.loads((self.bundle / "manifest.json").read_text())
        with zipfile.ZipFile(self.bundle / "evidence.zip") as archive:
            result = json.loads(archive.read("review.json"))
            self.assertFalse(result["build_ready"])
            for entry in manifest["files"]:
                self.assertEqual(hashlib.sha256(archive.read(entry["path"])).hexdigest(), entry["sha256"])

    def test_explicit_example_upload_and_failure_preserve_bundle(self):
        with mock.patch.object(review.evidence, "publish", return_value="evidence-commit") as publish:
            code, output = self.run_main("--upload-example")
        self.assertEqual(code, 0, output)
        self.assertIn("UPLOADED_COMMIT evidence-commit", output)
        self.assertTrue(publish.call_args.args[2].startswith("fpga-evidence/ethernet-review-"))
        with mock.patch.object(review.evidence, "publish", side_effect=RuntimeError("push failed")):
            code, output = self.run_main("--upload-example")
        self.assertEqual(code, 1)
        self.assertIn("Local bundle retained", output)
        self.assertNotIn("UPLOADED_COMMIT", output)

    def test_changed_source_during_packaging_never_published(self):
        package = review.evidence.package

        def changed(files, output, metadata):
            (self.example / "imports/eth_j10_example.v").write_text("changed after inspection")
            package(files, output, metadata)

        with mock.patch.object(review.evidence, "package", side_effect=changed), \
                mock.patch.object(review.evidence, "publish") as publish:
            code, output = self.run_main("--upload-example")
        self.assertEqual(code, 1)
        self.assertIn("Source changed", output)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
