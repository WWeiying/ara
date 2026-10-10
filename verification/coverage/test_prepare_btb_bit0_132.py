import json
from pathlib import Path
import tempfile
import unittest
import prepare_btb_bit0_132 as p


class PartialIdentity(unittest.TestCase):
    def test_exact_132(self):
        self.assertEqual(len(p.records(p.el_text())), 132)
        self.assertEqual(len(p.NAMES), 66)
        self.assertFalse(any('.valid' in n for n in p.NAMES))

    def test_direction_pair(self):
        lines = p.el_text().splitlines()
        body = []
        for line in lines[3:]:
            body.extend(line.replace('Toggle ', 'Toggle '+d+' ', 1) for d in ('0to1', '1to0'))
        self.assertEqual(p.records('\n'.join(lines[:3]+body)), p.records(p.el_text()))
        with self.assertRaises(ValueError): p.records('\n'.join(lines[:3]+body[:-1]))

    def test_duplicate_and_mixed_rejected(self):
        text = p.el_text()
        for line in (text.splitlines()[3], text.splitlines()[3].replace('Toggle ', 'Toggle 0to1 ', 1)):
            with self.assertRaises(ValueError): p.records(text+line+'\n')

    def test_expansion_foreign_annotation_checksum(self):
        text = p.el_text()
        for old, new in [('[0] "logic', '[1] "logic'), (' [0] "logic', ' "logic'),
                         ('[0] "logic', '[0:1] "logic'), (p.SCOPE, p.SCOPE+'.foreign'),
                         (p.CHECKSUM, '0 1574888635'), (p.NOTE, 'unknown'),
                         ('btb_prediction_o[0].target_address', 'btb_prediction_o[0].valid')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                p.records(text.replace(old, new, 1))


class Overlap(unittest.TestCase):
    def block(self, scope, directive=''):
        return 'CHECKSUM: "1"\nINSTANCE: '+scope+'\n'+directive+'\n'

    def test_ancestor_and_exact_whole_rejected(self):
        for s in (p.SCOPE, p.SCOPE.rsplit('.',1)[0]):
            with self.assertRaises(ValueError): p.no_overlap(self.block(s))

    def test_field_bit_ancestor_overlap(self):
        name = sorted(p.NAMES)[0]
        for suffix in ('', ' [0]', ' [1:0]'):
            for scope, field in [(p.SCOPE, name), (p.SCOPE.rsplit('.',1)[0], 'i_btb.'+name)]:
                with self.assertRaises(ValueError):
                    p.no_overlap(self.block(scope, 'Toggle '+field+suffix+' "logic '+field+'[63:0]"'))

    def test_protected_bits_sibling_other_metric(self):
        name = sorted(p.NAMES)[0]
        p.no_overlap(self.block(p.SCOPE, 'Toggle '+name+' [63:1] "logic '+name+'[63:0]"'))
        p.no_overlap(self.block(p.SCOPE+'.sibling'))
        p.no_overlap(self.block(p.SCOPE, 'Transition state "X" -> "Y"'))


class SourceAndRealPrepare(unittest.TestCase):
    def sources(self):
        root = p.ROOT/'hardware/deps/cva6/core'
        return [(root/n).read_text() for n in ('frontend/btb.sv', 'frontend/frontend.sv',
            'branch_unit.sv', 'include/cv64a6_imafdcv_sv39_config_pkg.sv', 'cva6.sv')]

    def test_source_induction(self):
        self.assertEqual(len(p.source_proof(*self.sources())['writers']), 6)

    def test_mutated_drivers_and_config(self):
        texts = self.sources()
        changes = [(0, 'btb_q <= btb_d;', "btb_q <= btb_d; btb_q[0][0].target_address <= '1;"),
            (0, "'{default: 0}", "'{default: 1}"),
            (0, 'btb_q[index][i]', 'btb_d[index][i]'),
            (2, "target_address[0] = 1'b0", "target_address[0] = 1'b1"),
            (3, "RVZCMT: bit'(0)", "RVZCMT: bit'(1)")]
        for index, old, new in changes:
            self.assertIn(old, texts[index])
            copied = list(texts); copied[index] = copied[index].replace(old, new)
            with self.subTest(index=index, old=old), self.assertRaises(ValueError): p.source_proof(*copied)

    def test_actual_prepare_compiled_779_and_prior_EL(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'prepared'
            seal = p.prepare(out)
            self.assertEqual(seal, p.digest(out/'prepare-manifest.json'))
            inv = json.loads((out/'inventory.json').read_text())
            self.assertEqual(inv['target_serialized_count'],132)
            self.assertEqual(inv['protected_serialized_count'],8860)
            self.assertEqual(len(inv['targets']),66)
            offsets = {n['attrs']['name']:n['offset'] for n in inv['targets']}
            self.assertEqual(offsets['btb_prediction_o[0].target_address'],394)
            self.assertEqual(offsets['btb_prediction_o[1].target_address'],524)
            for q, slot, start in [('d',0,672),('d',1,2752),('q',0,4832),('q',1,6912)]:
                for row in range(16):
                    self.assertEqual(offsets[f'gen_asic_btb.btb_{q}[{row}][{slot}].target_address'],start+130*row)
            self.assertTrue({2101,2361,4831,6261,6521,8991} <=
                            set(inv['protected_residual_serialized_positions']))
            self.assertTrue(any(n['attrs']['name'].endswith('.valid') for n in inv['all_nodes']))
            self.assertEqual(len(p.records((out/'candidate.el').read_text())),132)
            manifest = json.loads((out/'prepare-manifest.json').read_text())
            self.assertFalse(manifest['EDA_run'])
            self.assertFalse(manifest['coverage_admitted'])
            for name, sha in manifest['output_pins'].items(): self.assertEqual(p.digest(name),sha)
            with self.assertRaises(FileExistsError): p.prepare(out)


if __name__ == '__main__':
    unittest.main()
