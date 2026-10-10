import copy
from pathlib import Path
import unittest

import mfpu_constants272_sourcefirst770 as b


class SourceFirstBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = b.collect()
        cls.texts = {Path(p).name: (b.ROOT/p).read_text() for p in b.SOURCE}
        cls.tree = staticmethod(b.function(b.ROOT/'verification/coverage/review_qbs_accum_config_constants767.py', 'tree'))

    def test_real_union_and_complement(self):
        c = b.contract(self.config)
        self.assertEqual(sum(len(i['targets']) for i in c['instances']), 272)
        self.assertEqual(sum(n['missing_slots'] for i in c['instances'] for n in i['targets']), 34816)
        self.assertTrue(c['protected_children'])
        self.assertTrue(any(n['portnode'] != '0' for i in c['instances'] for n in i['protected']))

    def test_negative_active_producer(self):
        self.assertEqual(b.constants(self.tree, 6, set(range(6)), 0), {6: 0})
        self.assertEqual(b.constants(self.tree, 5, set(range(5)), 0), {6: 0})
        texts = dict(self.texts)
        texts['vmfpu.sv'] = texts['vmfpu.sv'].replace('{default: DISABLED}', '{default: PARALLEL}')
        with self.assertRaises(ValueError): b.semantic_proof(texts)

    def test_negative_literal_cast(self):
        texts = dict(self.texts)
        texts['fpnew_opgroup_block.sv'] = texts['fpnew_opgroup_block.sv'].replace("TagType'(fpnew_pkg::DONT_CARE)", 'tag_i')
        with self.assertRaises(ValueError): b.semantic_proof(texts)

    def test_negative_packed_member_order(self):
        texts = dict(self.texts)
        texts['vmfpu.sv'] = texts['vmfpu.sv'].replace('elen_t operand_a;\n    strb_t flag_mask;\n    strb_t control;',
                                                                 'strb_t control;\n    strb_t flag_mask;\n    elen_t operand_a;')
        with self.assertRaises(ValueError): b.semantic_proof(texts)

    def test_negative_compiled_config(self):
        with self.assertRaises(ValueError): b.parameters({'param': 'NumIn=6,LockIn=1'}, {'LockIn': 0})
        with self.assertRaises(ValueError): b.parameters({'param': 'FpFmtMask=63'}, {'FpFmtMask': 56})

    def test_negative_port_and_flags(self):
        n = copy.deepcopy(self.config['instances'][0]['targets'][0]['attributes'])
        n['portnode'] = '3'
        with self.assertRaises(ValueError): b.target_guard(n)
        n['portnode'] = '0'; n['name'] = 'gen_arbiter.rr_q'
        with self.assertRaises(ValueError): b.target_guard(n)

    def test_negative_complement_and_promotion(self):
        c = copy.deepcopy(self.config); c['instances'][0]['protected'].pop()
        with self.assertRaises(ValueError): b.contract(c)
        c = copy.deepcopy(self.config); c['ready_for_union'] = True
        with self.assertRaises(ValueError): b.contract(c)
        c = copy.deepcopy(self.config); c['instances'][0]['targets'][0]['native_label'] = 'guessed'
        with self.assertRaises(ValueError): b.contract(c)

    def test_negative_pin(self):
        with self.assertRaises(ValueError): b.check_pins({str(b.RESULT): '0'*64})


if __name__ == '__main__': unittest.main()
