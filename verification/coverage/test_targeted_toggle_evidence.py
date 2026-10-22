import gzip
import json
from pathlib import Path
import tempfile
import unittest

import targeted_toggle_evidence as tool


class ToggleEvidence(unittest.TestCase):
    def test_direction_not_inferred_and_left_to_right_gain(self):
        old = {'s': dict(width=4, checksum='7', bits='0x4')}
        single = {'s': dict(width=4, checksum='7', bits='0x9')}
        self.assertEqual(tool.gains(old, tool.union(old, single)), {'s': [0, 3]})

    def test_width_checksum_scope_and_loss_rejected(self):
        old = {'s': dict(width=4, checksum='7', bits='0x4')}
        for new in ({}, {'s': dict(width=5, checksum='7', bits='0x4')},
                    {'s': dict(width=4, checksum='8', bits='0x4')}):
            with self.assertRaises(ValueError):
                tool.union(old, new)
        with self.assertRaises(ValueError):
            tool.gains(old, {'s': dict(width=4, checksum='7', bits='0x0')})

    def test_gzip_binary_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'data.xml'
            for contents in ('<instance_data name="s" value="01X" chksum="7"/>',
                             '<instance_data name="s" value="01" chksum="7"/>' * 2):
                p.write_bytes(gzip.compress(('<covdata>' + contents + '</covdata>').encode()))
                with self.assertRaises(ValueError):
                    tool.rows(p, ['s'])

    def test_missing_scope_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'data.xml'
            p.write_bytes(gzip.compress(b'<covdata/>'))
            with self.assertRaises(ValueError):
                tool.rows(p, ['s'])

    def test_actual_old_image_compressed_fixture(self):
        root = Path(__file__).resolve().parents[1] / 'out'
        c = json.loads((root / 'final-raw740-dve-prepared-agent-20261007-01/config.json').read_bytes())
        scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'
        path = next((Path(c['input_ledger'][1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        rows, sha = tool.rows(path, [scope])
        self.assertEqual(sha, c['pins'][str(path)])
        self.assertGreater(rows[scope]['width'], 0)
        self.assertLessEqual(int(rows[scope]['bits'], 16).bit_length(), rows[scope]['width'])

    def test_foreign_config_seal_rejected_before_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'config.json'
            p.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'seal differs'):
                tool.collect(p, '0' * 64, ['s'])


if __name__ == '__main__':
    unittest.main()
