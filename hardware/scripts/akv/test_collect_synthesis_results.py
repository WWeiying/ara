#!/usr/bin/env python3

"""Tests for strict synthesis evidence collection."""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("collect-synthesis-results.py")
SPEC = importlib.util.spec_from_file_location("collect_synthesis_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CollectSynthesisResultsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.include = self.root / "include"
        self.include.mkdir()
        self.header = self.include / "types.svh"
        self.header.write_text("typedef logic bit_t;\n", encoding="utf-8")
        self.source = self.root / "source.sv"
        self.source.write_text("module source; endmodule\n", encoding="utf-8")
        self.filelist = self.root / "files.f"
        self.filelist.write_text(
            f"+incdir+{self.include}\n{self.source}\n", encoding="utf-8"
        )
        self.input_sdc = self.root / "input.sdc"
        self.input_sdc.write_text("create_clock -period 1.0 clk_i\n", encoding="utf-8")
        self.flow = self.root / "flow.tcl"
        self.std_db = self.root / "tcbn28hpcplus_tt.db"
        self.sram_db = self.root / "ts1n28hpcpuhdsvtb64x256_tt.db"
        self.std_db.write_text("std db\n", encoding="utf-8")
        self.sram_db.write_text("sram db\n", encoding="utf-8")
        self.flow.write_text(
            f"set std_library {self.std_db}\n"
            f"set context_sram_library {self.sram_db}\n"
            "compile_ultra\n",
            encoding="utf-8",
        )
        self.summary_rpt = self.root / "physical_summary.rpt"
        self.area_rpt = self.root / "area.rpt"
        self.timing = self.root / "timing.rpt"
        self.netlist = self.root / "design.v"
        self.output = self.root / "synthesis_summary.json"
        self.generated = (
            self.summary_rpt,
            self.area_rpt,
            self.timing,
            self.netlist,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def write_standalone_reports(self) -> None:
        self.summary_rpt.write_text(
            "scope=akv_engine_standalone\n"
            "clock_period_ns=1.0\n"
            "clock_uncertainty_ns=0.15\n"
            "akv_sram_macro_count=20\n"
            "akv_v1_sram_macro_count=4\n"
            "akv_v2_sram_macro_count=16\n"
            "physical_sram_capacity_bits=327680\n"
            "design_total_area_um2=1000.0\n"
            "design_macro_area_um2=600.0\n"
            "design_logic_area_um2=400.0\n"
            "worst_setup_slack_ns=-0.1\n"
            "worst_reg_to_reg_setup_slack_ns=0.02\n",
            encoding="utf-8",
        )
        self.area_rpt.write_text(
            "Total cell area: 1000.000000\n"
            "Macro/Black Box area: 600.000000\n",
            encoding="utf-8",
        )
        self.timing.write_text("timing\n", encoding="utf-8")
        self.netlist.write_text("module design; endmodule\n", encoding="utf-8")

    def spec(self) -> object:
        return MODULE.CollectionSpec(
            mode="standalone",
            root=self.root,
            filelist=self.filelist,
            input_sdc=self.input_sdc,
            summary_rpt=self.summary_rpt,
            area_rpt=self.area_rpt,
            generated_artifacts=self.generated,
            source_inputs=(self.input_sdc, self.flow),
            output=self.output,
        )

    def mark_fresh(self) -> None:
        inputs = (
            self.filelist,
            self.header,
            self.source,
            self.input_sdc,
            self.flow,
            self.std_db,
            self.sram_db,
        )
        for path in inputs:
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        for path in self.generated:
            os.utime(path, ns=(2_000_000_000, 2_000_000_000))

    def test_collect_and_revalidate_complete_standalone_evidence(self) -> None:
        self.write_standalone_reports()
        self.mark_fresh()
        with mock.patch.object(MODULE.subprocess, "check_output", return_value="deadbeef\n"):
            summary = MODULE.collect(self.spec())
        self.assertEqual(summary["metrics"]["akv_sram_macro_count"], 20)
        MODULE.validate_summary(self.output, "standalone", self.root)

    def test_source_change_invalidates_collected_evidence(self) -> None:
        self.write_standalone_reports()
        self.mark_fresh()
        with mock.patch.object(MODULE.subprocess, "check_output", return_value="deadbeef\n"):
            MODULE.collect(self.spec())
        self.source.write_text("module source; logic changed; endmodule\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.CollectionError, "current RTL"):
            MODULE.validate_summary(self.output, "standalone", self.root)

    def test_old_reports_are_rejected_after_filelist_regeneration(self) -> None:
        self.write_standalone_reports()
        self.mark_fresh()
        os.utime(self.filelist, ns=(2_000_000_000, 2_000_000_000))
        for path in self.generated:
            os.utime(path, ns=(1_000_000_000, 1_000_000_000))
        with self.assertRaisesRegex(MODULE.CollectionError, "predate"):
            MODULE.collect(self.spec())

    def test_old_reports_are_rejected_after_rtl_changes_before_collection(self) -> None:
        self.write_standalone_reports()
        self.mark_fresh()
        os.utime(self.source, ns=(3_000_000_000, 3_000_000_000))
        with self.assertRaisesRegex(MODULE.CollectionError, "predate"):
            MODULE.collect(self.spec())

    def test_wrong_macro_partition_is_rejected(self) -> None:
        self.write_standalone_reports()
        self.summary_rpt.write_text(
            self.summary_rpt.read_text().replace(
                "akv_v2_sram_macro_count=16", "akv_v2_sram_macro_count=15"
            )
        )
        with self.assertRaisesRegex(MODULE.CollectionError, "SRAM organization"):
            MODULE.validate_metrics(
                "standalone", MODULE.read_key_values(self.summary_rpt), self.area_rpt
            )

    def test_integrated_area_uses_reported_total_and_all_macros(self) -> None:
        self.area_rpt.write_text(
            "Total cell area: 2000.000000\n"
            "Macro/Black Box area: 1500.000000\n",
            encoding="utf-8",
        )
        values = {
            "scope": "ara_soc_integrated",
            "clock_period_ns": "1.0",
            "clock_uncertainty_ns": "0.15",
            "akv_sram_macro_count": "20",
            "akv_v1_sram_macro_count": "4",
            "akv_v2_sram_macro_count": "16",
            "physical_sram_capacity_bits": "327680",
            "design_total_area_um2": "2000.0",
            "worst_setup_slack_ns": "-0.2",
            "worst_reg_to_reg_setup_slack_ns": "-0.1",
        }
        metrics = MODULE.validate_metrics("integrated", values, self.area_rpt)
        self.assertEqual(metrics["design_macro_area_um2"], 1500.0)
        self.assertEqual(metrics["design_logic_area_um2"], 500.0)


if __name__ == "__main__":
    unittest.main()
