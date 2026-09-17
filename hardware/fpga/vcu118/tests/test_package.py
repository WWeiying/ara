#!/usr/bin/env python3
"""Offline package and UART protocol checks, without FPGA/Vivado emulation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
ROOT = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location("uart_load", ROOT / "software/uart_load.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.reply = bytearray()
        self.pending = None
        self.memory = {}
        self.executed = False
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def reset_input_buffer(self): self.reply.clear()
    def read(self, size):
        data = bytes(self.reply[:size])
        del self.reply[:size]
        return data
    def write(self, data):
        if self.pending:
            addr, length = self.pending
            if len(data) != length: raise AssertionError("Bad payload size")
            for i, byte in enumerate(data): self.memory[addr + i] = byte
            self.pending = None
            self.reply.extend(loader.EOT)
        elif data == loader.ACK:
            self.reply.extend(loader.ACK)
        elif data[0] in (0x11, 0x12):
            addr, length = struct.unpack("<QQ", data[1:])
            self.reply.extend(loader.ACK)
            if data[0] == 0x12:
                self.pending = addr, length
            else:
                self.reply.extend(self.memory[addr + i] for i in range(length))
                self.reply.extend(loader.EOT)
        elif data[0] == 0x13:
            entry, = struct.unpack("<Q", data[1:])
            if entry not in self.memory: raise AssertionError("Unloaded entry")
            self.executed = True
            self.reply.extend(loader.ACK + b"SMOKE PASS: mocked protocol only\r\n")
        else: raise AssertionError("Unknown command")
        return len(data)


class PackageTests(unittest.TestCase):
    def test_manifest_paths(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        files = manifest["files"]
        self.assertEqual(len(files), len(set(files)))
        for name in files + manifest["include_dirs"]:
            self.assertFalse(Path(name).is_absolute())
            self.assertNotIn("..", Path(name).parts)
            self.assertTrue((ROOT / name).exists(), name)
        self.assertEqual(manifest["defines"]["ARA_QBS_ENABLE"], 1)
        self.assertEqual(manifest["defines"]["ARA_AKV_V2_ENABLE"], 1)
        self.assertNotIn("TARGET_SRAM_MC", manifest["defines"])
        self.assertEqual(sum(name.endswith("axi_inval_filter.sv") for name in files), 1)
        self.assertTrue(any(name.endswith("tc_sram_xilinx.sv") for name in files))
        self.assertFalse(any(name.endswith("/rtl/tc_sram.sv") for name in files))

    def test_no_links_or_windows_collisions(self):
        names = set()
        reserved = {"con", "prn", "aux", "nul"} | {f"{p}{i}" for p in ("com", "lpt") for i in range(1, 10)}
        for path in ROOT.rglob("*"):
            self.assertFalse(path.is_symlink(), str(path))
            rel = path.relative_to(ROOT).as_posix().casefold()
            self.assertNotIn(rel, names)
            names.add(rel)
            self.assertNotIn(path.name.split(".")[0].casefold(), reserved)
            self.assertFalse(any(c in path.name for c in '<>:"|?*'))

    def test_qbs_payload_sram_sources(self):
        files = json.loads((ROOT / "manifest.json").read_text())["files"]
        base = "rtl/ara/hardware/src/vlsu/qbs/"
        for name in ("qbs_payload_buffer.sv", "qbs_payload_sram.sv"):
            self.assertEqual(files.count(base + name), 1, name)
        self.assertLess(files.index(base + "qbs_payload_sram.sv"),
                        files.index(base + "qbs_block_adapter.sv"))

    def test_board_xml(self):
        base = ROOT / "board_files/vcu118/2.4"
        for name in ("board.xml", "part0_pins.xml", "preset.xml"):
            ET.parse(base / name)
        self.assertIn("xcvu9p", (base / "board.xml").read_text())
        self.assertIn("ddr4_sdram_c1_062", (base / "board.xml").read_text())

    def test_checksums(self):
        for row in (ROOT / "SHA256SUMS").read_text().splitlines():
            digest, name = row.split("  ", 1)
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)

    def test_git_snapshot_policy(self):
        self.assertIn("* -text", (ROOT / ".gitattributes").read_text())
        ignore = (ROOT / ".gitignore").read_text().splitlines()
        for pattern in ("!*", "/build/", "/reports/", "/output/", "/.fpga_sync_backups/", "*.zip"):
            self.assertIn(pattern, ignore)

    def test_managed_run_scripts_match_templates(self):
        templates = Path(__file__).resolve().parents[1] / "scripts"
        for name in ("run.ps1", "run.tcl", "run_support.tcl", "common.tcl",
                     "constraint_checks.tcl",
                     "create_project.tcl", "impl.tcl", "check_fifo.ps1", "check_fifo.tcl",
                     "fifo_probe.sv", "synth_pre.tcl"):
            self.assertEqual((ROOT / "scripts" / name).read_bytes(),
                             (templates / name).read_bytes(), name)
        self.assertEqual((ROOT / "constraints/cdc.xdc").read_bytes(),
                         (templates.parent / "constraints/cdc.xdc").read_bytes())

    def test_jtag_and_uart_constraint_contract(self):
        timing = (ROOT / "constraints/timing.xdc").read_text()
        commands = "\n".join(line for line in timing.splitlines()
                             if not line.lstrip().startswith("#"))
        self.assertNotIn("set_clock_groups", commands)
        self.assertNotIn("create_clock", commands)
        self.assertNotIn("CLOCK_DEDICATED_ROUTE", commands)
        self.assertNotIn("-from [get_ports uart_rx_i]", commands)
        board = (ROOT / "rtl/board/ara_dsa_vcu118.sv").read_text()
        self.assertIn('(* CLOCK_BUFFER_TYPE = "NONE" *) input logic jtag_tck_i', board)
        self.assertIn('.jtag_trst_ni(1\'b1)', board)
        # Retain the generic CDC source for other users, but no instance may
        # survive in the sampled FPGA TAP, which shares the DM clock.
        dmi = (ROOT / "rtl/riscv-dbg/src/dmi_cdc.sv").read_text()
        self.assertIn("cdc_2phase_clearable #(.T(dm::dmi_req_t))", dmi)
        self.assertIn("cdc_2phase_clearable #(.T(dm::dmi_resp_t))", dmi)
        jtag = (ROOT / "rtl/riscv-dbg/src/dmi_jtag.sv").read_text()
        tap = (ROOT / "rtl/riscv-dbg/src/dmi_jtag_tap.sv").read_text()
        self.assertNotIn("dmi_cdc i_dmi_cdc", jtag)
        self.assertNotIn("posedge tck", jtag + tap)
        self.assertNotIn("i_dft_tck_mux", tap)
        self.assertIn("else if (fpga_fall_i)", tap)
        self.assertIn("assign dmi_req_valid_o = dmi_req_valid & ~dmi_clear & dmi_rst_no;", jtag)

    def test_generated_files_ignored(self):
        ignored = (
            "build/project/rtl/generated.v", "reports/synth/utilization.rpt",
            "output/board.bit", ".fpga_sync_backups/snapshot/rtl/core.sv",
            "gui/project.runs/synth_1/netlist.v", "gui/project.cache/ip/data",
            "gui/project.sim/sim_1/generated.sv", "gui/project.gen/ip/generated.v",
            "gui/project.hw/hw_1/state", "gui/project.ip_user_files/ip/model.v",
            "gui/ip_user_files/ip/model.v", "gui/.Xil/state", "gui/.cache/state",
            "gui/xsim.dir/top/xsim.exe", "gui/vivado.log", "gui/vivado.jou",
            "gui/vivado.str", "gui/vivado_1.backup.jou", "gui/top.vds",
            "gui/vivado.pb", "gui/top.dcp", "gui/top.bit", "gui/top.ltx",
            "gui/top.xpr", "gui/top.wdb", "gui/top.wcfg", "gui/top.vcd",
            "gui/top.fst", "gui/top.fsdb", "gui/flash.bin", "gui/flash.mcs",
            "gui/flash.prm", "gui/timing.rpt", "backup.zip", "backup.7z",
            "backup.tar.gz", "gui/Thumbs.db", "gui/Desktop.ini",
        )
        visible = (
            "rtl/cheshire/hw/cheshire_soc.sv", "rtl/cva6/core/debug/new.sv",
            "rtl/board/new.v", "scripts/new.tcl", "constraints/new.xdc",
            "ip/new.xci", "ip/init.coe", "ip/init.mem", "software/smoke.elf",
            "software/smoke.dump", "manifest.json", "SHA256SUMS",
        )
        # A fresh repo tests untracked inputs, independent of the real Git index.
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", directory], check=True)
            (repo / ".gitignore").write_text((ROOT / ".gitignore").read_text())
            for paths, expected in ((ignored, 0), (visible, 1)):
                for name in paths:
                    with self.subTest(path=name):
                        result = subprocess.run(
                            ["git", "check-ignore", "-q", "--", name], cwd=repo)
                        self.assertEqual(result.returncode, expected)

    def test_elf(self):
        entry, segments = loader.load_segments(ROOT / "software/smoke.elf")
        self.assertEqual(entry, 0x80000000)
        self.assertTrue(segments)
        self.assertLess(sum(len(data) for _, data, _ in segments), 128 * 1024)

    def test_protocol_mock(self):
        port = FakeSerial()
        argv = ["uart_load.py", "--port", "MOCK", "--elf", str(ROOT / "software/smoke.elf"), "--seconds", "0.01"]
        with patch.object(sys, "argv", argv), patch.object(loader.serial, "Serial", return_value=port):
            loader.main()
        self.assertTrue(port.executed)

    def test_protocol_rejects_bad_ack(self):
        port = FakeSerial()
        port.reply = bytearray(b"x")
        with self.assertRaises(RuntimeError): loader.expect(port, loader.ACK)


unittest.main()
