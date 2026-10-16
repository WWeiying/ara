import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from stage_dual_repair import ADAPTER, TOP, PROJECT, CLOCK, repair, stage

ROOT = Path(__file__).resolve().parents[2]


class RepairTests(unittest.TestCase):
    def test_adapter_fix_matches_production(self):
        current = (ROOT / ADAPTER).read_text()
        old = current.replace('~invalidate & ~inval_valid_i;', '~invalidate;').replace(
            '// Invalidation owns the D-cache return slot. Backpressure AXI as well,\n'
            '    // otherwise a simultaneous read beat is accepted but never captured.',
            '// we are not ready when invalidating').replace(
            '// External invalidation can overlap speculative fetches and page walks.\n'
            '    // The shared R channel is held until this return slot is available.',
            '// External invalidation requests (from coprocessor). This is safe as\n'
            '    // there are no other transactions when a coprocessor has pending stores.')
        self.assertEqual(repair(ADAPTER, old.encode()), current.encode())
        with self.assertRaises(ValueError): repair(ADAPTER, current.encode())

    def test_clock_is_local_and_profile_scoped(self):
        top = (ROOT / TOP).read_text()
        self.assertIn('`ifdef ARA_FPGA_DDR2\n  input logic c2_sys_clk_p, c2_sys_clk_n,', top)
        self.assertIn('.dram_clk_i(c2_sys_clk), .fabric_ready_o(dram_ready[1])', top)
        self.assertIn('.dram_clk_i(sys_clk), .fabric_ready_o(dram_ready[0])', top)
        clock = (ROOT / CLOCK).read_text()
        self.assertIn('PACKAGE_PIN AW26 [get_ports c2_sys_clk_p]', clock)
        self.assertIn('PACKAGE_PIN AW27 [get_ports c2_sys_clk_n]', clock)
        self.assertIn('-period 4.000', clock)
        self.assertIn('if {$fpga_profile in {dual_ddr dual_ddr_ethernet}} {\n'
            '    add_files -fileset constrs_1 -norecurse [file join $package_root constraints ddr2_clock.xdc]',
            (ROOT / PROJECT).read_text())

    def test_stage_rejects_corrupted_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'old'; source.mkdir()
            (source/'x').write_text('changed')
            (source/'SHA256SUMS').write_text(hashlib.sha256(b'original').hexdigest()+'  x\n')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                stage(source, Path(tmp)/'new')
            self.assertFalse((Path(tmp)/'new').exists())

    def test_unrelated_sources_unchanged(self):
        self.assertEqual(repair('rtl/unrelated.sv', b'original'), b'original')

    def test_staged_inventory_is_complete(self):
        files = {
            ADAPTER: ('axi_rd_rdy        = ~invalidate;\n'
                '// we are not ready when invalidating\n'
                '// External invalidation requests (from coprocessor). This is safe as\n'
                '    // there are no other transactions when a coprocessor has pending stores.').encode(),
            TOP: ('`ifdef ARA_FPGA_DDR2\n  output logic c1_ddr4_act_n,\n'
                  '  if (1) begin : gen_ddr2\n'
                  '.dram_clk_i(sys_clk), .fabric_ready_o(dram_ready[1])').encode(),
            PROJECT: b'add_files -fileset constrs_1 -norecurse [file join $package_root constraints board.xdc]\n',
            'provenance/dual_ethernet.json': b'{}',
            'rtl/unrelated.sv': b'original',
        }
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'old'; target=Path(tmp)/'new'; source.mkdir()
            for name,data in files.items():
                path=source/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
            (source/'SHA256SUMS').write_text(''.join(
                f'{hashlib.sha256(data).hexdigest()}  {name}\n' for name,data in files.items()))
            stage(source,target)
            self.assertEqual((target/'rtl/unrelated.sv').read_bytes(),b'original')
            record=json.loads((target/'provenance/dual_inval_clock_fix.json').read_text())
            self.assertEqual(set(record['changes']),{ADAPTER,TOP,PROJECT,CLOCK})
            for line in (target/'SHA256SUMS').read_text().splitlines():
                digest,name=line.split('  ',1)
                self.assertEqual(hashlib.sha256((target/name).read_bytes()).hexdigest(),digest)
            with self.assertRaises(ValueError): stage(source,target)


if __name__ == '__main__': unittest.main()
