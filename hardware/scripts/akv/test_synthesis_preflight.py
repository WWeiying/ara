#!/usr/bin/env python3

"""Unit tests for the QBS/AKV synthesis preflight audit."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("check-synthesis-preflight.py")
SPEC = importlib.util.spec_from_file_location("check_synthesis_preflight", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SynthesisPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.filelist = self.root / "ara_soc_dc.f"
        self.sdc = self.root / "ara_soc.sdc"
        self.setup = self.root / "setup.env"
        self.sram_db = self.root / "akv.db"
        self.sram_db.write_text("db", encoding="utf-8")
        self.sdc.write_text(
            "set clk_mul 1.0\n"
            "set uncertainty_add 0\n"
            "create_clock -name clk_i -period [expr {1 * $clk_mul}] [get_ports clk_i]\n"
            "set_clock_uncertainty -setup "
            "[expr {(0.15 + $uncertainty_add) * $clk_mul}] [get_clocks clk_i]\n",
            encoding="utf-8",
        )
        self.setup.write_text(f"set akv_db {self.sram_db}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_filelist(self, *, akv_v2_define: bool = True, blackbox: bool = True) -> None:
        defines = [
            "+define+SYNTHESIS",
            "+define+TARGET_SYNTHESIS",
            "+define+TARGET_SRAM_MC",
            "+define+TARGET_SRAM_BLACKBOX",
            "+define+TARGET_TECH_CELLS_GENERIC_EXCLUDE_TC_SRAM",
            "+define+NR_LANES=4",
            "+define+VLEN=1024",
            "+define+ARA_QBS_ENABLE=1",
            "+define+ARA_AKV_ENABLE=1",
        ]
        if akv_v2_define:
            defines.append("+define+ARA_AKV_V2_ENABLE=1")
        sources = [
            *MODULE.COMMON_SOURCES[:2],
            *MODULE.QBS_SOURCES,
            *MODULE.AKV_SOURCES[:2],
            *MODULE.AKV_V2_SOURCES,
            *MODULE.AKV_SOURCES[2:],
            *MODULE.COMMON_SOURCES[2:],
        ]
        if blackbox:
            sources.append(MODULE.AKV_SRAM_BLACKBOX)
        self.filelist.write_text("\n".join([*defines, *sources]) + "\n", encoding="utf-8")

    def options(self) -> object:
        return MODULE.Options(
            filelist=self.filelist,
            sdc=self.sdc,
            setup=self.setup,
            sram_db=self.sram_db,
            require_qbs=True,
            require_akv=True,
            require_akv_v2=True,
            require_macro_sram=True,
            nr_lanes=4,
            vlen=1024,
        )

    def test_complete_qbs_akv_v2_inputs_pass(self) -> None:
        self.write_filelist()
        summary = MODULE.audit(self.options())
        self.assertEqual(summary["clock_period_ns"], 1)

    def test_stale_qbs_only_define_is_rejected(self) -> None:
        self.write_filelist(akv_v2_define=False)
        with self.assertRaisesRegex(MODULE.PreflightError, "ARA_AKV_V2_ENABLE"):
            MODULE.audit(self.options())

    def test_missing_macro_blackbox_is_rejected(self) -> None:
        self.write_filelist(blackbox=False)
        with self.assertRaisesRegex(MODULE.PreflightError, "64x256"):
            MODULE.audit(self.options())

    def test_missing_macro_selection_define_is_rejected(self) -> None:
        self.write_filelist()
        text = self.filelist.read_text().replace("+define+TARGET_SRAM_MC\n", "")
        self.filelist.write_text(text)
        with self.assertRaisesRegex(MODULE.PreflightError, "TARGET_SRAM_MC"):
            MODULE.audit(self.options())

    def test_wrong_clock_constraint_is_rejected(self) -> None:
        self.write_filelist()
        self.sdc.write_text(self.sdc.read_text().replace("clk_mul 1.0", "clk_mul 1.2"))
        with self.assertRaisesRegex(MODULE.PreflightError, "1 GHz"):
            MODULE.audit(self.options())

    def test_tcl_line_continuation_is_accepted(self) -> None:
        self.write_filelist()
        self.sdc.write_text(
            self.sdc.read_text().replace(
                "set_clock_uncertainty -setup [expr",
                "set_clock_uncertainty -setup \\\n    [expr",
            )
        )
        MODULE.audit(self.options())


if __name__ == "__main__":
    unittest.main()
