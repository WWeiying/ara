import unittest
from pathlib import Path
from prepare import ROOT, HERE, MODULES, engine, vlsu, once, compile_lines


class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = {k: (ROOT / p).read_text() for k, p in MODULES.items()}
        cls.changed = {k: vlsu(v) if k == "vlsu" else engine(v, k)
                       for k, v in cls.original.items()}

    def test_both_readers_removed(self):
        for kind in ("qbs", "akv"):
            text = self.changed[kind]
            self.assertNotIn("qbs_read_engine #(", text)
            self.assertNotIn("i_read_engine", text)
            self.assertIn("output reader_req_t reader_req_o", text)
            self.assertIn("input reader_rsp_t reader_rsp_i", text)
            self.assertEqual(text.count("assign reader_req_o"), 1)

    def test_explicit_tag_contract(self):
        self.assertIn("range_tag: 16'(read_range_tag)", self.changed["qbs"])
        self.assertIn("range_tag: {8'b0, read_range_tag}", self.changed["akv"])
        for kind in ("qbs", "akv"):
            for field in ("data_tag", "completion_tag", "fault_tag"):
                suffix = "[7:0]" if kind == "akv" else ""
                self.assertIn(f"{kind}_range_tag_t'(reader_rsp_i.{field}{suffix})", self.changed[kind])

    def test_context_and_commit_suffixes_exact(self):
        for kind, anchor in (("qbs", "  assign context_lookup_valid ="),
                             ("akv", "  always_comb begin\n    unique case (read_data_tag.role)")):
            before, after = self.original[kind], self.changed[kind]
            self.assertEqual(before[before.index(anchor):], after[after.index(anchor):])

    def test_vlsu_owner_mmu_cut_seed_unchanged(self):
        before, after = self.original["vlsu"], self.changed["vlsu"]
        for start, end in (
            ("  axi_cut #(", "  //  Address Generation"),
            ("  assign qbs_command_valid", "  assign qbs_physical_range_allowed"),
            ("  // QBS and VLDu share", "  qbs_engine #(")):
            self.assertEqual(before[before.index(start):before.index(end)],
                             after[after.index(start):after.index(end)])

    def test_probe_paths_not_dropped(self):
        self.assertNotIn("i_qbs_engine.i_read_engine", self.changed["vlsu"])
        before = self.original["vlsu"].count("i_qbs_engine.i_read_engine.")
        after = self.changed["vlsu"].count("i_shared_reader.i_read_engine.")
        self.assertEqual(after, before + 3)
        self.assertIn("reader_probe_burst_count_i == 0", self.changed["qbs"])
        self.assertIn("else if (!reader_probe_r_valid_i)", self.changed["qbs"])

    def test_one_instance_clock_before_gate(self):
        support = (HERE / "vlsu_shared_reader.svh").read_text()
        self.assertEqual(support.count("qbs_akv_shared_reader #("), 1)
        self.assertIn("shared_read_clk_en = qbs_clk_en || akv_clk_en", support)
        self.assertIn(".command_fire_i({akv_command_fire, qbs_command_fire})", support)
        self.assertNotIn("qbs_clk || akv_clk", support)
        self.assertNotIn("write_busy", support)

    def test_drift_anchor_rejected(self):
        with self.assertRaises(ValueError):
            once("aa", "a", "b")
        with self.assertRaises(ValueError):
            engine(self.original["qbs"].replace("  qbs_read_engine #(\n", "  changed #(\n"), "qbs")

    def test_compile_excludes_only_soc_tb_units(self):
        lines = ["+define+FOR_VERIFY", "+incdir+/private/hardware/tb",
                 "/private/hardware/src/vlsu/vlsu.sv", "/private/hardware/tb/ara_tb.sv",
                 "/private/verification/uvm/ara_cvxif_dut_bind.sv"]
        kept, omitted = compile_lines(lines, Path("/private"))
        self.assertEqual(kept, lines[:3])
        self.assertEqual(omitted, lines[3:])

    def test_successor_admission_not_fault_terminal(self):
        text = (HERE / "admission_assertions.svh").read_text()
        self.assertIn("$isunknown({qbs_active_q, akv_active_q,", text)
        self.assertIn("if (qbs_command_fire || akv_command_fire)", text)
        self.assertIn("context_write_busy === 1'b0", text)
        self.assertNotIn("if (akv_terminal)", text)
        self.assertIn('`include "admission_assertions.svh"', self.changed["vlsu"])


if __name__ == "__main__":
    unittest.main()
