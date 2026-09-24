import contextlib
import csv
import io
import json
from pathlib import Path, PureWindowsPath
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import host_ethernet_preflight as preflight


# Abbreviated rows from uploaded f8d60ab1, preserving Vivado's blank cells.
LICENSE_TABLE = """IP License Status Summary
| Instance Name | Target | Required License | Generated License Level | Available License Level |
+---------------+--------+------------------+-------------------------+-------------------------+
| eth_j10 | Simulation | tri_mode_eth_mac@2015.04 | Design_Linking | Design_Linking |
|         |            | eth_avb_endpoint@2015.04 | Design_Linking | Design_Linking |
|         | Synthesis  | tri_mode_eth_mac@2015.04 | Design_Linking | Design_Linking |
|         |            | eth_avb_endpoint@2015.04 | Design_Linking | Design_Linking |
"""


class EthernetPreflightTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / "evidence with spaces"

    def main(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return preflight.main(["--out", str(self.out), *args])

    def record(self):
        return json.loads((self.out / "preflight.json").read_text())

    def stage_file(self, states):
        with (self.out / "stages.tsv").open("w", newline="") as stream:
            csv.writer(stream, delimiter="\t", lineterminator="\n").writerows(states.items())

    def vivado_result(self, command, **kwargs):
        self.assertEqual(Path(kwargs["cwd"]), self.out)
        self.assertIn("-mode", command)
        self.assertIn("batch", command)
        self.assertNotIn("-nolog", command)
        self.assertEqual(command[command.index("-log") + 1], (self.out / "vivado.log").as_posix())
        for option in ("stdout", "stderr", "stdin", "capture_output", "shell", "creationflags"):
            self.assertNotIn(option, kwargs, f"Must inherit console handles, not {option}")
        self.assertEqual(command[-2:], [self.out.as_posix(), preflight.BOARD.parents[1].as_posix()])
        self.stage_file(dict.fromkeys(preflight.STAGES, "PASS"))
        (self.out / "preflight.rpt").write_text("PREFLIGHT_COMPLETE\n")
        (self.out / "vivado.log").write_text("Mock Vivado native log\n")
        for name in ("ip_status_before.rpt", "ip_status_after.rpt"):
            (self.out / name).write_text("Mock license missing/evaluation report, not an approval\n")
        return subprocess.CompletedProcess(command, 0)

    def test_bundled_board_contract_and_directions(self):
        contract = preflight.board_contract(preflight.BOARD)
        self.assertEqual(contract["reference_clock_hz"], 625000000)
        self.assertEqual(contract["pins"]["SGMII_TX_P"]["loc"], "AU21")
        self.assertEqual(contract["pins"]["SGMII_RX_P"]["loc"], "AU24")
        self.assertEqual(contract["pins"]["SGMIICLK_P"]["iostandard"], "LVDS")
        self.assertEqual(len(contract["files_sha256"]), 3)

    def test_reject_changed_contract(self):
        cases = (
            ("board.xml", ".//component[@name='part0']", "part_name", "wrong"),
            ("board.xml", ".//component[@name='phy_onboard']", "part_name", "wrong"),
            ("board.xml", ".//interface[@name='sgmii_phyclk']/parameters/parameter[@name='frequency']", "value", "125000000"),
            ("board.xml", ".//interface[@name='sgmii_lvds']//pin_map", "component_pin", "SGMII_RX_N"),
            ("part0_pins.xml", ".//pin[@name='SGMII_TX_P']", "loc", "AU24"),
            ("preset.xml", ".//user_parameter[@name='CONFIG.lvdsclkrate']", "value", "125"),
        )
        for i, (filename, xpath, attr, value) in enumerate(cases):
            with self.subTest(filename=filename, xpath=xpath):
                board = self.root / f"board{i}"
                shutil.copytree(preflight.BOARD, board)
                tree = ET.parse(board / filename)
                tree.find(xpath).set(attr, value)
                tree.write(board / filename)
                with self.assertRaises(ValueError):
                    preflight.board_contract(board)

    def test_static_only_never_invokes_vivado(self):
        with mock.patch.object(preflight.subprocess, "run") as run:
            self.assertEqual(self.main("--static-only"), 0)
        run.assert_not_called()
        record = self.record()
        self.assertEqual(record["state"], "static_board_checked_not_ip_verified")
        self.assertFalse(record["hardware_verified"])
        self.assertFalse(record["bitstream_license_verified"])
        self.assertNotIn("logging_mode", record)
        self.assertEqual(record["stages"], {})

    def test_existing_output_untouched(self):
        self.out.mkdir()
        previous = self.out / "preflight.json"
        previous.write_text("previous evidence")
        self.assertEqual(self.main("--static-only"), 1)
        self.assertEqual(previous.read_text(), "previous evidence")

    def test_success_is_not_license_or_hardware_approval(self):
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=self.vivado_result):
            self.assertEqual(self.main(), 0)
        record = self.record()
        self.assertEqual(record["state"], "ip_example_generated_needs_license_and_constraints_review")
        self.assertEqual(record["logging_mode"], "inherited_console_with_vivado_native_log")
        self.assertFalse(record["hardware_access"])
        self.assertFalse(record["hardware_verified"])
        self.assertFalse(record["bitstream_license_verified"])

    def test_windows_paths_use_forward_slashes_at_vivado_boundary(self):
        here = PureWindowsPath(r"D:\project\ara\hardware\fpga\vcu118\tests")
        board = PureWindowsPath(r"D:\project\ara\hardware\fpga\ara_dsa_vcu118\board_files\vcu118\2.4")
        with mock.patch.object(preflight, "HERE", here), \
                mock.patch.object(preflight, "BOARD", board), \
                mock.patch.object(preflight, "board_contract", return_value={}), \
                mock.patch.object(preflight, "digest", return_value="mock-digest"), \
                mock.patch.object(preflight, "find_vivado", return_value=r"D:\Xilinx\Vivado\2020.1\bin\vivado.bat"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=self.vivado_result) as run:
            self.assertEqual(self.main(), 0)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-source") + 1],
                         "D:/project/ara/hardware/fpga/vcu118/tests/host_ethernet_preflight.tcl")
        self.assertEqual(command[-1], "D:/project/ara/hardware/fpga/ara_dsa_vcu118/board_files")
        for argument in command[command.index("-source") + 1:]:
            self.assertNotIn("\\", argument)
            self.assertNotIn("{", argument)

    def test_zero_exit_without_marker_rejected(self):
        def incomplete(command, **kwargs):
            result = self.vivado_result(command, **kwargs)
            (self.out / "preflight.rpt").write_text("interrupted\n")
            return result
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=incomplete):
            self.assertEqual(self.main(), 1)
        self.assertEqual(self.record()["state"], "failed")

    def test_failed_stage_preserved_and_uploaded_even_with_zero_exit(self):
        def failure(command, **kwargs):
            result = self.vivado_result(command, **kwargs)
            self.stage_file({**dict.fromkeys(preflight.STAGES, "PASS"), "configure": "FAIL"})
            return result
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=failure), \
                mock.patch.object(preflight, "upload") as upload:
            self.assertEqual(self.main("--upload"), 1)
        upload.assert_called_once_with(self.out)
        self.assertEqual(self.record()["stages"]["configure"], "FAIL")

    def test_nonzero_exit_rejected_with_complete_reports(self):
        def failure(command, **kwargs):
            self.vivado_result(command, **kwargs)
            return subprocess.CompletedProcess(command, 1)
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=failure):
            self.assertEqual(self.main(), 1)

    def test_missing_license_report_rejected(self):
        def missing(command, **kwargs):
            result = self.vivado_result(command, **kwargs)
            (self.out / "ip_status_after.rpt").unlink()
            return result
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=missing):
            self.assertEqual(self.main(), 1)

    def test_design_linking_is_not_accepted_despite_all_stages_passing(self):
        def linking_only(command, **kwargs):
            result = self.vivado_result(command, **kwargs)
            (self.out / "ip_status_after.rpt").write_text(LICENSE_TABLE)
            return result
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=linking_only):
            self.assertEqual(self.main(), 1)
        record = self.record()
        self.assertEqual(record["stages"], dict.fromkeys(preflight.STAGES, "PASS"))
        self.assertEqual(record["state"], "failed")
        self.assertIn("Design_Linking", record["error"])
        self.assertFalse(record["bitstream_license_verified"])

    def test_example_error_and_license_blocker_both_survive_failure_upload(self):
        def observed_failure(command, **kwargs):
            self.vivado_result(command, **kwargs)
            self.stage_file({**dict.fromkeys(preflight.STAGES, "PASS"),
                             "example": "FAIL", "example_inventory": "SKIP"})
            (self.out / "ip_status_after.rpt").write_text(LICENSE_TABLE)
            (self.out / "vivado.log").write_text('can not find channel named "stdout"\n')
            return subprocess.CompletedProcess(command, 1)
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=observed_failure), \
                mock.patch.object(preflight, "upload") as upload:
            self.assertEqual(self.main("--upload"), 1)
        upload.assert_called_once_with(self.out)
        record = self.record()
        self.assertEqual(record["stages"]["example"], "FAIL")
        diagnostics = record["diagnostics"]
        self.assertTrue(diagnostics["stdout_channel_error_observed"])
        self.assertEqual(diagnostics["temac_license"]["state"], "blocked_design_linking")

    def test_bought_license_does_not_hide_example_failure(self):
        def observed_failure(command, **kwargs):
            self.vivado_result(command, **kwargs)
            self.stage_file({**dict.fromkeys(preflight.STAGES, "PASS"),
                             "example": "FAIL", "example_inventory": "SKIP"})
            (self.out / "ip_status_after.rpt").write_text(LICENSE_TABLE.replace("Design_Linking", "Bought"))
            (self.out / "preflight.rpt").write_text('can not find channel named "stdout"\nPREFLIGHT_COMPLETE\n')
            return subprocess.CompletedProcess(command, 1)
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=observed_failure):
            self.assertEqual(self.main(), 1)
        record = self.record()
        self.assertEqual(record["state"], "failed")
        self.assertTrue(record["diagnostics"]["stdout_channel_error_observed"])
        self.assertEqual(record["diagnostics"]["temac_license"]["state"], "full_reported_not_bitstream_verified")

    def test_stdout_error_cannot_be_accepted_despite_success_stages(self):
        def suppressed_error(command, **kwargs):
            result = self.vivado_result(command, **kwargs)
            (self.out / "vivado.log").write_text('can not find channel named "stdout"\n')
            return result
        with mock.patch.object(preflight, "find_vivado", return_value="vivado"), \
                mock.patch.object(preflight.subprocess, "run", side_effect=suppressed_error):
            self.assertEqual(self.main(), 1)
        self.assertIn("stdout channel error", self.record()["error"])

    def test_license_table_continuation_and_disabled_avb(self):
        assessment = preflight.assess_mac_license(LICENSE_TABLE.replace("\n", "\r\n"))
        self.assertEqual(assessment["state"], "blocked_design_linking")
        self.assertEqual(len(assessment["synthesis_rows"]), 1)
        self.assertEqual(assessment["synthesis_rows"][0]["required"], "tri_mode_eth_mac@2015.04")
        # Leave AVB at Design_Linking, but provide a full TEMAC license.
        full = LICENSE_TABLE.replace("tri_mode_eth_mac@2015.04 | Design_Linking | Design_Linking",
                                     "tri_mode_eth_mac@2015.04 | Full | Full")
        self.assertEqual(preflight.assess_mac_license(full)["state"], "full_reported_not_bitstream_verified")
        self.assertFalse(preflight.assess_mac_license(full)["bitstream_verified"])
        for generated, available in (("Bought", "Bought"), ("Purchased", "Purchased"),
                                     ("Bought", "Full"), ("Full", "Bought")):
            with self.subTest(generated=generated, available=available):
                table = full.replace("| Full | Full", f"| {generated} | {available}")
                assessment = preflight.assess_mac_license(table)
                self.assertEqual(assessment["state"], "full_reported_not_bitstream_verified")
                self.assertEqual(assessment["synthesis_rows"][0]["generated"], generated)
                self.assertEqual(assessment["synthesis_rows"][0]["available"], available)
                self.assertFalse(assessment["bitstream_verified"])
        stale = full.replace("tri_mode_eth_mac@2015.04 | Full | Full",
                             "tri_mode_eth_mac@2015.04 | Design_Linking | Full")
        self.assertEqual(preflight.assess_mac_license(stale)["state"], "blocked_design_linking")
        evaluation = full.replace("| Full | Full", "| Hardware_Evaluation | Hardware_Evaluation")
        self.assertEqual(preflight.assess_mac_license(evaluation)["state"],
                         "evaluation_reported_not_bitstream_verified")

    def test_license_unknown_or_unrelated_report_never_approves_hardware(self):
        for content in ("", "unrecognized table", "Design_Linking in prose",
                        LICENSE_TABLE.replace("Synthesis", "Simulation"),
                        LICENSE_TABLE.replace("eth_j10", "another_ip"),
                        LICENSE_TABLE.replace("Design_Linking", "Unrecognized_Level")):
            with self.subTest(content=content):
                assessment = preflight.assess_mac_license(content)
                self.assertEqual(assessment["state"], "unverified")
                self.assertFalse(assessment["bitstream_verified"])
        self.out.mkdir()
        diagnostics = preflight.diagnose_reports(self.out)
        self.assertEqual(diagnostics["temac_license"]["state"], "unverified")
        self.assertFalse(diagnostics["stdout_channel_error_observed"])

    def test_tool_missing_leaves_failure_report(self):
        with mock.patch.object(preflight, "find_vivado", side_effect=ValueError("not installed")):
            self.assertEqual(self.main(), 1)
        self.assertIn("not installed", self.record()["error"])

    def test_stages_reject_duplicates_and_unknown_states(self):
        self.out.mkdir()
        for content in ("version\tPASS\nversion\tPASS\n", "version\tOK\n", "made_up\tPASS\n"):
            (self.out / "stages.tsv").write_text(content)
            with self.assertRaises(ValueError):
                preflight.read_stages(self.out)

    def test_upload_whitelist_excludes_ip_and_license_files(self):
        import host_axi_upload
        self.out.mkdir()
        for name in (*preflight.UPLOAD_FILES, "secret.lic", "vendor.v", "design.bit", "project.xpr"):
            (self.out / name).write_text("test")
        with mock.patch.object(host_axi_upload, "git", return_value="mock-origin"), \
                mock.patch.object(host_axi_upload, "package") as package, \
                mock.patch.object(host_axi_upload, "publish", return_value="commit") as publish, \
                mock.patch.object(preflight.tempfile, "mkdtemp", return_value=str(self.root / "bundle")), \
                contextlib.redirect_stdout(io.StringIO()):
            preflight.upload(self.out)
        files = package.call_args.args[0]
        self.assertEqual({name for _, name in files}, set(preflight.UPLOAD_FILES))
        self.assertTrue(publish.call_args.args[2].startswith("fpga-evidence/ethernet-"))
        self.assertEqual(publish.call_args.kwargs["message"], "Collect VCU118 Ethernet IP preflight")

    @unittest.skipUnless(shutil.which("tclsh"), "tclsh not installed")
    def test_tcl_preflight_scenarios(self):
        self.assertEqual(self.main("--static-only"), 0)
        result = subprocess.run(["tclsh", str(preflight.HERE / "test_host_ethernet_preflight.tcl"), str(self.out)],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: Ethernet preflight", result.stderr)

    @unittest.skipUnless(shutil.which("tclsh"), "tclsh not installed")
    def test_tcl_real_stdout_loss_is_recorded_and_rejected(self):
        self.assertEqual(self.main("--static-only"), 0)
        for mode in ("stdout_before_example", "stdout_closed_in_example",
                     "stdout_closed_on_success", "stdout_chan_closed_in_example"):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    ["tclsh", str(preflight.HERE / "test_host_ethernet_preflight.tcl"), str(self.out), mode],
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS: Ethernet preflight", result.stderr)


if __name__ == "__main__":
    unittest.main()
