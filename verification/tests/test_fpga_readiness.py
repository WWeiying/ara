"""Offline preflight fixtures only: never inspect /dev, /sys, SDKs or boards."""

import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fpga import readiness


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dev = self.root / "host/dev"
        self.sys = self.root / "host/sys"
        self.sdk = self.root / "host/sdk"
        self.bin = self.root / "host/bin"
        for path in (self.dev, self.sys / "bus/usb/devices", self.sys / "class/tty", self.bin):
            path.mkdir(parents=True)

    def put(self, name, data=b"payload"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def audit(self, **kwargs):
        return readiness.audit(self.root, dev=self.dev, sysfs=self.sys,
                               search_path=str(self.bin), sdk=self.sdk, **kwargs)

    def test_missing_is_not_unknown_or_pass(self):
        result = self.audit()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["ready_for_signoff"])
        self.assertTrue(all(b["status"] == "missing" for b in result["blockers"]))
        self.assertEqual(result["linux_images"]["Image"]["status"], "missing")
        self.assertEqual(result["board"]["programmed_bitstream"], "unknown")
        self.assertEqual(result["llama_cpp"]["executable"]["status"], "unknown")

    def test_marker_and_completed_audit_are_not_bitstreams(self):
        prefix = readiness.EXPORT.as_posix()
        self.put(f"{prefix}/output/COMPLETE", b"PASS")
        self.put(f"{prefix}/reports/completed_audit.json",
                 b'{"AutomatedChecksPassed": true, "BitstreamGenerated": false}')
        self.put(f"{prefix}/linux/artifacts/console.log", b"OpenSBI\nLinux version\nPASS")
        result = self.audit()
        self.assertEqual(result["build_inventory"]["artifacts"], [])
        self.assertIn("local_bitstream", [b["id"] for b in result["blockers"]])

    def test_all_files_available_is_still_not_signoff(self):
        prefix = readiness.EXPORT.as_posix()
        bit = self.put(f"{prefix}/output/ara.bit", b"not even a valid bitstream")
        self.put(f"{prefix}/manifest.json", b'{"revisions": {"ara": {"commit": "not attested"}}}')
        self.put(f"{prefix}/SHA256SUMS", b"not a valid checksum list")
        for name in ("fw_jump.elf", "Image", "ara_vcu118.dtb", "initramfs.cpio", "SHA256SUMS"):
            self.put(f"{prefix}/linux/artifacts/{name}")
        result = self.audit()
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertFalse(result["ready_for_signoff"])
        found = result["build_inventory"]["artifacts"][0]
        self.assertEqual(found["sha256"], hashlib.sha256(bit.read_bytes()).hexdigest())
        self.assertTrue(result["unknowns"])

    def test_export_revision_is_content_not_acceptance(self):
        value = {"revisions": {"ara": {"commit": "a" * 40}}, "flow_status": "COMPLETE"}
        manifest = self.put(str(readiness.EXPORT / "manifest.json"), json.dumps(value).encode())
        record = self.audit()["export"]["manifest"]
        self.assertEqual(record["content"], value)
        self.assertEqual(record["sha256"], hashlib.sha256(manifest.read_bytes()).hexdigest())

    def test_bad_manifest_and_empty_payload_unknown(self):
        self.put(str(readiness.EXPORT / "manifest.json"), b"{broken")
        empty = self.put("empty.bit", b"")
        self.assertEqual(self.audit()["export"]["manifest"]["status"], "unknown")
        self.assertEqual(readiness.artifact(self.root, empty)["status"], "unknown")

    def test_regular_artifact_hash_and_bounds(self):
        path = self.put("payload.elf", b"real file bytes")
        result = readiness.artifact(self.root, path)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["size_bytes"], 15)
        with patch.object(readiness, "MAX_FILE_BYTES", 2):
            self.assertEqual(readiness.artifact(self.root, path)["status"], "unknown")

    def test_file_replaced_while_inspecting_is_unknown(self):
        path = self.put("changing.bit", b"old")
        original = readiness.regular_open

        @contextlib.contextmanager
        def changing(root, name):
            with original(root, name) as stream:
                yield stream
            replacement = self.put("replacement.bit", b"new")
            replacement.replace(path)

        with patch.object(readiness, "regular_open", changing):
            result = readiness.artifact(self.root, path)
        self.assertEqual(result["status"], "unknown")
        self.assertNotIn("sha256", result)

    def test_known_artifact_problems_require_exact_identity(self):
        original = readiness.artifact
        hashes = {"initramfs.cpio": "e98ae673a251ee2ddf362fb3f18fd2ac12b7625c7087d2af2842857230b6106a",
                  "rv64uv-ara-vfredmax_boundary": "98a007e64cb2187bc077b6798a0cc583b6340acf309fb90f451fcd9c400648a5"}
        self.put(str(readiness.EXPORT / "linux/artifacts/initramfs.cpio"))
        self.put("apps/bin/rv64uv-ara-vfredmax_boundary")
        self.assertNotIn("historical_initramfs", [b["id"] for b in self.audit()["blockers"]])

        def identity_fixture(root, path):
            record = original(root, path)
            if path.name in hashes:
                record["sha256"] = hashes[path.name]
            return record

        with patch.object(readiness, "artifact", identity_fixture):
            result = self.audit()
        ids = [b["id"] for b in result["blockers"]]
        self.assertIn("historical_initramfs", ids)
        self.assertIn("verification_elf_runtime", ids)

    def test_fifo_not_opened(self):
        path = self.root / "fifo.bit"
        os.mkfifo(path)
        with patch.object(readiness.os, "open", side_effect=AssertionError("must not open FIFO")):
            self.assertEqual(readiness.artifact(self.root, path)["status"], "unknown")

    def test_symlink_files_and_directories_not_followed(self):
        actual = self.put("outside/payload.bit")
        folder = self.root / "hardware/fpga"
        folder.mkdir(parents=True)
        (folder / "linked.bit").symlink_to(actual)
        (folder / "external").symlink_to(actual.parent, target_is_directory=True)
        result = self.audit()["build_inventory"]
        self.assertEqual(len(result["artifacts"]), 1)
        self.assertEqual(result["artifacts"][0]["status"], "unknown")
        self.assertIn(str(folder / "external"), result["skipped_directories"])

    def test_out_of_tree_input_not_read(self):
        self.assertEqual(readiness.artifact(self.root, self.root.parent / "elsewhere.bit")["status"], "unknown")

    def test_scan_bound_is_unknown_not_missing(self):
        self.put("hardware/fpga/one.txt")
        with patch.object(readiness, "MAX_ENTRIES", 0):
            result = self.audit()
        self.assertTrue(result["build_inventory"]["errors"])
        self.assertEqual(next(b for b in result["blockers"] if b["id"] == "local_bitstream")["status"], "unknown")

    def test_permission_error_not_missing(self):
        with patch.object(readiness.Path, "iterdir", side_effect=PermissionError("fixture denied")):
            _, record = readiness.directory_entries(self.dev)
        self.assertEqual(record["status"], "unknown")

    def test_uart_only_metadata_usb_only_allowlisted_attributes(self):
        # FIFO stands in for a device: opening it would hang. The scan must not.
        os.mkfifo(self.dev / "ttyUSB0")
        serial = self.dev / "serial/by-id"
        serial.mkdir(parents=True)
        (serial / "CP2105_Enhanced").symlink_to("../../ttyUSB0")
        usb = self.sys / "devices/usb1/1-2"
        usb.mkdir(parents=True)
        (self.sys / "bus/usb/devices/1-2").symlink_to(usb)
        for name, value in {"idVendor": "10c4", "idProduct": "ea70", "product": "CP2105"}.items():
            (usb / name).write_text(value)
        os.mkfifo(usb / "descriptors")
        result = self.audit()["board"]
        self.assertEqual(len(result["uart_nodes"]), 2)
        self.assertEqual(result["usb_devices"][0]["hint"], "Silicon Labs UART candidate")
        self.assertEqual(result["board_identity"], "unknown")
        self.assertEqual(result["jtag_connectivity"], "unknown")

    def test_absent_sysfs_not_evidence_of_absent_board(self):
        result = readiness.board_hints(self.root / "no-dev", self.root / "no-sys")
        self.assertEqual(result["usb_listing"]["status"], "missing")
        self.assertEqual(result["board_identity"], "unknown")

    def test_tools_are_metadata_only_and_directory_is_not_a_tool(self):
        executable = self.put("host/bin/vivado", b"#!/bin/sh\nexit 99\n")
        executable.chmod(0o755)
        (self.bin / "hw_server").mkdir()
        (self.bin / "openocd").symlink_to(self.bin / "hw_server", target_is_directory=True)
        result = self.audit()["tools"]["path_tools"]
        self.assertEqual(result["vivado"]["status"], "available")
        self.assertEqual(result["vivado"]["version"], "unknown")
        self.assertEqual(result["hw_server"]["status"], "missing")
        self.assertEqual(result["openocd"]["status"], "missing")

    def test_custom_runtime_gates_independent_of_linux_markers(self):
        self.put(str(readiness.EXPORT / "linux/artifacts/console.log"),
                 b"[LINUX_RVV] PASS signal_return\n"
                 b"[LINUX_CUSTOM_CAPS] QBS UNAVAILABLE signal=SIGILL\n"
                 b"[LINUX_CUSTOM_CAPS] AKV UNAVAILABLE signal=SIGILL\n"
                 b"CUSTOM_COMPUTE=NOT_VALIDATED\n")
        gates = self.audit()["verification_gates"]
        self.assertEqual(set(gates), {"linux_rvv_userspace", "custom_query", "qbs_akv_compute",
                                      "shared_ddr_mmu_cache", "hidden_context_isolation"})
        self.assertTrue(all(gate["status"] == "unknown" for gate in gates.values()))
        self.assertIn("OS task/address-space ownership", gates["hidden_context_isolation"]["requires"])

    def cli(self, output):
        with patch.dict(os.environ, {"PATH": str(self.bin)}), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return readiness.main(["--root", str(self.root), "--output", str(output),
                                   "--dev-root", str(self.dev), "--sys-root", str(self.sys),
                                   "--sdk", str(self.sdk)])

    def test_cli_writes_json_exclusively_and_exits_nonzero(self):
        output = self.root / "verification/fpga/reports/inventory.json"
        self.assertEqual(self.cli(output), 1)
        before = output.read_bytes()
        self.assertFalse(json.loads(before)["ready_for_signoff"])
        self.assertEqual(self.cli(output), 2)
        self.assertEqual(output.read_bytes(), before)

    def test_cli_rejects_outside_scope_and_symlink_parent(self):
        self.assertEqual(self.cli(self.root / "hardware/report.json"), 2)
        allowed = self.root / "verification/fpga"
        allowed.mkdir(parents=True)
        (allowed / "linked").symlink_to(self.bin, target_is_directory=True)
        self.assertEqual(self.cli(allowed / "linked/report.json"), 2)
        self.assertFalse((self.bin / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
