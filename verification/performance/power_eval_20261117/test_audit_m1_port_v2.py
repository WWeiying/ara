import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit_v2', Path(__file__).with_name('audit_m1_port_v2.py'))
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


class Tests(unittest.TestCase):
    def rows(self):
        live = dict(top_committing_pcs=[('0x80001e3e', 60), ('0x800022f4', 15)])
        old = json.loads(json.dumps(live))
        return live, copy.deepcopy(old), old

    def test_representation_only(self):
        result = a.compare_representation(*self.rows())
        self.assertFalse(result['raw_python_equality'])
        self.assertTrue(result['exact_ordered_PC_and_counts_equal'])

    def test_count_mutation(self):
        live, persisted, old = self.rows()
        persisted['top_committing_pcs'][0][1] += 1
        with self.assertRaises(ValueError):
            a.compare_representation(live, persisted, old)

    def test_pc_mutation(self):
        live, persisted, old = self.rows()
        persisted['top_committing_pcs'][0][0] = '0x800022f8'
        with self.assertRaises(ValueError):
            a.compare_representation(live, persisted, old)

    def test_order_not_relaxed(self):
        live, persisted, old = self.rows()
        persisted['top_committing_pcs'].reverse()
        with self.assertRaises(ValueError):
            a.compare_representation(live, persisted, old)

    def test_bad_count_type(self):
        with self.assertRaises(ValueError):
            a.top_pairs([['0x80001e3e', True]])

    def test_projection_preserves_interval_semantics_and_both_ack_bits(self):
        # Port1 has a different PC, but both reviewed readers intentionally observe only pc_o[port0].
        header = '''$timescale 100fs $end
$scope module ara_tb $end
$scope module dut $end
$scope module i_ara_soc $end
$var wire 1 a clk_i $end
$var wire 1 b rst_ni $end
$scope module i_system $end
$scope module i_ariane $end
$scope module commit_stage_i $end
$var wire 64 c pc_o $end
$var wire 2 d commit_ack_o $end
$var wire 64 h unused_port1_pc $end
$upscope $end
$upscope $end
$scope module i_ara $end
$scope module i_dispatcher $end
$var wire 4 e state_q $end
$upscope $end
$scope module i_sequencer $end
$var wire 1 f state_q $end
$var wire 1 g ara_req_valid_i $end
$upscope $end
$upscope $end
$upscope $end
$upscope $end
$upscope $end
$upscope $end
$enddefinitions $end
#10000
$dumpvars
0a
1b
PC0 c
b11 d
PC1 h
b0000 e
0f
1g
$end
#15000
1a
#17000
b1 h
#20000
0a
COMPANION c
#25000
1a
#30000
0a
b00 d
'''
        header = header.replace('PC0', 'b' + format(0x80001e3e, '064b')).replace(
            'PC1', 'b' + format(0x800022f8, '064b')).replace('COMPANION', 'b' + format(0x800022f4, '064b'))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            raw = root / 'raw.vcd'
            raw.write_text(header)
            dc = a.w.load(Path(a.__file__).with_name('dc_power.py'), 'fixture_original_dc')
            original = dc.scan_activity_vcd(raw, 2, 10000, 30000, '0x800022f8')
            projected = a.projected_scan(raw, dc, root)
            for key in ('signals', 'retire_samples', 'top_committing_pcs', 'clock_edges', 'initial_value_records', 'initial_unknown_value_records'):
                self.assertEqual(original[key], projected[key])
            self.assertEqual(projected['retire_samples'], 5)
            self.assertNotIn('0x800022f8', dict(projected['top_committing_pcs']))
            self.assertEqual(projected['vcd_sha256'], a.b.sha(raw))
            self.assertNotIn('b1 h', (root / 'observed-controls.vcd').read_text())
            self.assertIn('#17000', (root / 'observed-controls.vcd').read_text())


if __name__ == '__main__':
    unittest.main()
