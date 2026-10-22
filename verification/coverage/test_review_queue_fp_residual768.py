"""Actual frozen source and deliberate nonzero writer/parameter/EL mutations."""
import unittest
import xml.etree.ElementTree as ET
import review_queue_fp_residual768 as m


class Proof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue=(m.ROOT/'hardware/src/lane/operand_queue.sv').read_text()
        cls.stage=(m.ROOT/'hardware/src/lane/operand_queues_stage.sv').read_text()

    def test_actual_source_and_complete_writer_table(self):
        r=m.source_contract(self.queue,self.stage)
        self.assertEqual(len(r['abstract_writer_table']),16)
        self.assertFalse(any(v['global_fp8_nonzero_writer'] for v in r['abstract_writer_table']))
        for v in r['abstract_writer_table']:
            if not v['support']:
                self.assertFalse(v['global_fp16_nonzero_writer'] or v['global_fp32_nonzero_writer'])
        self.assertTrue(any(v['global_fp16_nonzero_writer'] for v in r['abstract_writer_table']))
        self.assertTrue(any(v['global_fp32_nonzero_writer'] for v in r['abstract_writer_table']))

    def test_global_fp8_nonzero_or_partial_override(self):
        for assignment in ("fp8[0] = '1;",'fp8[0].m = ibuf_operand[1:0];','fp8[0].m += 1;',
                           'fp8[0].m[1] = ibuf_operand[0];','fp16[0].m[2:0] = 3;','fp32.m[0] <= 1;'):
            with self.subTest(assignment=assignment),self.assertRaises(ValueError):
                m.source_contract(self.queue.replace('end : type_conversion',assignment+' end : type_conversion'),self.stage)

    def test_default_zero_removed(self):
        with self.assertRaises(ValueError):m.source_contract(self.queue.replace("fp8[i]  = '0","fp8[i]  = '1"),self.stage)

    def test_gate_disabled_or_nonzero_global_writer(self):
        for before,after in (('if (FPUSupport != FPUSupportNone)','if (1)'),
                             ('fp32 = ibuf_operand[8*select +: 32]','fp32 = operand_i')):
            with self.assertRaises(ValueError):m.source_contract(self.queue.replace(before,after),self.stage)

    def test_local_shadow_removed(self):
        with self.assertRaises(ValueError):m.source_contract(self.queue.replace('automatic fp8_t fp8 =','fp8[0] ='),self.stage)

    def test_alu_parameter_enabled(self):
        with self.assertRaises(ValueError):m.source_contract(self.queue,self.stage.replace('FPUSupportNone','FPUSupport',1))

    def test_missing_or_duplicate_producer(self):
        with self.assertRaises(ValueError):m.source_contract(self.queue,self.stage.replace('i_operand_queue_alu_a (','i_operand_queue_alu_b (',1))

    def test_EL_difference_bracket_names_partial_and_directions(self):
        text='INSTANCE: a\nToggle fp8[0].m "logic fp8[0].m[1:0]"\nToggle 0to1 fp32.m [3] "logic fp32.m[22:0]"\n'
        self.assertEqual(m.covered_fields(text,{'a'}),{('a','fp8[0].m'),('a','fp32.m')})
        self.assertEqual(m.covered_fields(text,{'b'}),set())
        with self.assertRaises(ValueError):m.covered_fields('INSTANCE: a\nToggle ??? invalid',{'a'})

    def test_effective_formats_and_control_never_selected(self):
        self.assertEqual(m.candidate_names('mfpu_a'),m.FP8)
        for name in ('fp16[0].m','fp32.m','fp8_m_lzc[0]','conv_operand','cmd.conv','cmd.eew','ntr.w64','operand_valid_o'):
            self.assertNotIn(name,m.candidate_names('mfpu_a'))
        self.assertEqual(len(m.candidate_names('alu_a')),21)

    def test_typed_width_kind_port_and_excluded_corruptions(self):
        node=ET.fromstring('<vectornode name="fp8[0].e" left="4" right="0" portnode="0" excluded="0"/>')
        self.assertEqual(m.typed_width('fp8[0].e',node),5)
        for key,value in (('left','3'),('right','1'),('portnode','1'),('excluded','1'),('name','fp16[0].e')):
            bad=ET.fromstring(ET.tostring(node));bad.set(key,value)
            with self.assertRaises(ValueError):m.typed_width('fp8[0].e',bad)
        node.tag='node'
        with self.assertRaises(ValueError):m.typed_width('fp8[0].e',node)


if __name__=='__main__':unittest.main()
