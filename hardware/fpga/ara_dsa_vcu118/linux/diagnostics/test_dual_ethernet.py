import sys
from pathlib import Path
import unittest
import subprocess
import tempfile
from unittest.mock import patch
from decimal import Decimal as D

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "vcu118/ethernet"))
import check_dual_synthesis as gate
from stage_dual_ethernet import transform, WRAPPER


class DualTests(unittest.TestCase):
    def test_c2_review_is_fail_closed(self):
        prefix='gen_ddr2.i_dram_wrapper_c2/gen_channel_c2.i_dram/inst/'
        keys={('Intra Clock Table',('mmcm_clkout0',),'WHS(ns)'):(D('-.402'),D(581)),
              ('Inter Clock Table',('mmcm_clkout0','mmcm_clkout6'),'WHS(ns)'):(D('-.173'),D(1))}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'review_complete.txt').write_text('complete')
            clocks='clock\tsource\n'+''.join(f'{c}\t{prefix}mmcm/{c}\n' for c in ('mmcm_clkout0','mmcm_clkout6'))
            (root/'clocks.tsv').write_text(clocks)
            rows='from\tto\tslack\tsource\tdestination\n'
            rows+=''.join(f'mmcm_clkout0\tmmcm_clkout0\t-.402\t{prefix}s/C\t{prefix}d{i}/D\n' for i in range(581))
            rows+=f'mmcm_clkout0\tmmcm_clkout6\t-.173\t{prefix}s/C\t{prefix}cross/D\n'
            (root/'paths.tsv').write_text(rows)
            with patch.object(gate,'clock_violations',return_value=keys):
                self.assertEqual(len(gate.reviewed_c2(root,'current')),2)
                for bad in (rows.replace(prefix+'d0/D','core/unsafe/D'),
                            rows.replace('-.402','-.450'),
                            rows.replace(prefix+'d1/D',prefix+'d0/D'),
                            rows.rsplit('\n',2)[0]+'\n'):
                    (root/'paths.tsv').write_text(bad)
                    with self.assertRaises(ValueError): gate.reviewed_c2(root,'current')
                (root/'paths.tsv').write_text(rows)
                (root/'clocks.tsv').write_text(clocks.replace(prefix,'wrong/'))
                with self.assertRaises(ValueError): gate.reviewed_c2(root,'current')
                (root/'clocks.tsv').write_text(clocks)
                (root/'review_complete.txt').unlink()
                with self.assertRaises(ValueError): gate.reviewed_c2(root,'current')

    def test_config_runtime(self):
        text = transform("scripts/config.tcl", (HERE.parents[1] / "scripts/config.tcl").read_bytes()).decode()
        for profile, expected in [("dual_ddr_ethernet", "ARA_FPGA_HOST ARA_FPGA_DDR2 ARA_FPGA_ETHERNET"),
                                  ("host_ethernet", "ARA_FPGA_HOST ARA_FPGA_ETHERNET"),
                                  ("dual_ddr", "ARA_FPGA_HOST ARA_FPGA_DDR2")]:
            script = f"set ::env(ARA_FPGA_PROFILE) {profile}\n" + text + "\nputs $profile_defines\nputs $profile_ips\n"
            result = subprocess.run(["tclsh"], input=script, text=True, capture_output=True, check=True)
            self.assertFalse(result.stderr)
            self.assertEqual(result.stdout.splitlines()[0], expected)
            ips = result.stdout.splitlines()[1].split()
            self.assertEqual("ddr4_c2" in ips, "DDR2" in expected)
            self.assertEqual("eth_control" in ips, "ETHERNET" in expected)

    def test_profile(self):
        text = transform("scripts/config.tcl", (HERE.parents[1] / "scripts/config.tcl").read_bytes()).decode()
        self.assertIn("$fpga_profile in {dual_ddr dual_ddr_ethernet}", text)
        self.assertIn("$fpga_profile in {host_ethernet dual_ddr_ethernet}", text)
        self.assertIn("set run_jobs 1", text)

    def test_single_loader(self):
        data = (HERE.parents[1] / WRAPPER).read_bytes()
        text = transform(WRAPPER, data).decode()
        self.assertIn("if (Channel == 0) begin : gen_ethernet", text)
        self.assertEqual(text.count(") i_eth_loader ("), 1)
        self.assertIn("end else begin : gen_no_ethernet", text)
        with self.assertRaises(ValueError):
            transform(WRAPPER, text.encode())

    def test_profile_bit_checks(self):
        text = transform("scripts/write_profile_bit.tcl", (HERE.parents[1] / "scripts/write_profile_bit.tcl").read_bytes()).decode()
        self.assertIn("dual_ddr dual_ddr_ethernet", text)
        self.assertIn("host_ethernet dual_ddr_ethernet", text)
        self.assertIn("gen_ethernet.i_eth_loader", text)

    def test_normalization_is_narrow(self):
        self.assertEqual(gate.canonical("pll_clk[0]_1"), "pll_clk[0]")
        self.assertEqual(gate.canonical("unsafe_logic_1"), "unsafe_logic_1")

    def test_gate_failures(self):
        key = ("Intra Clock Table", ("pll_clk[0]",), "WPWS(ns)")
        old = {key: (D("-.029"), D(4))}
        new_key = (key[0], ("pll_clk[0]_1",), key[2])
        values = [D(x) for x in [1,0,0,100, 1,0,0,100, "-.029","-.232",8,100]]
        with patch.object(gate, "summary", return_value=values), patch.object(gate, "clock_violations", side_effect=[old, {key: old[key], new_key: old[key]}]):
            self.assertTrue(gate.check("new", "old")["passed"])
        for bad in [(-0.03,4),(-0.029,9)]:
            with patch.object(gate, "summary", return_value=values), patch.object(gate, "clock_violations", side_effect=[old,{new_key: (D(str(bad[0])),D(bad[1]))}]):
                with self.assertRaises(ValueError): gate.check("new", "old")
        values[0]=D(-1)
        with patch.object(gate, "summary", return_value=values):
            with self.assertRaises(ValueError): gate.check("new", "old")


if __name__ == "__main__":
    unittest.main()
