import copy
import json
from pathlib import Path
import unittest
import targeted_toggle_evidence_v2 as t


class ActualBinding(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / 'out'
        c = json.loads((root / 'final-raw740-dve-prepared-agent-20261007-01/config.json').read_bytes())
        db = Path(c['input_ledger'][0]) / 'snps/coverage/db'
        self.design, self.info, self.shape = [t.xml(db / p) for p in
            ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml')]
        self.scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher'

    def test_actual_definition_without_tglinst(self):
        checks, defs = t.definitions(self.design, self.info, self.shape, [self.scope])
        self.assertEqual(checks[self.scope], '851086890')
        self.assertIn('FPUSupport=56', defs[self.scope]['shape'])
        self.assertNotIn('<tglinst', defs[self.scope]['shape'])

    def test_wrong_module_checksum_and_ambiguity_rejected(self):
        for field, value in (('name', 'foreign'), ('chksum', '0')):
            shape = copy.deepcopy(self.shape)
            node = next(n for n in shape.findall('tgldef') if n.get('chksum') == '851086890')
            node.set(field, value)
            with self.assertRaises(ValueError):
                t.definitions(self.design, self.info, shape, [self.scope])
        shape = copy.deepcopy(self.shape)
        shape.append(copy.deepcopy(next(n for n in shape.findall('tgldef') if n.get('chksum') == '851086890')))
        with self.assertRaises(ValueError):
            t.definitions(self.design, self.info, shape, [self.scope])


if __name__ == '__main__':
    unittest.main()
