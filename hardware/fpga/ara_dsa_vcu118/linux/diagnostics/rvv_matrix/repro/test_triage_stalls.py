import unittest
from triage_stalls import classify


class ClassificationTests(unittest.TestCase):
    def classify(self, asm, output='', name='case', pc=0x10000):
        return classify(name, [dict(pc=pc, asm=asm)], output)

    def test_slide_is_not_individual_case_proof(self):
        self.assertEqual(self.classify('vfslide1up.vf v24,v8,ft0,v0.t'),
                         ('slide_mask_stream', 'rtl_mechanism_confirmed_case_link_candidate'))

    def test_boundary_is_measured(self):
        self.assertEqual(self.classify('vmacc.vv v24,v8,v16,v0.t',
                         'RVV_TRIAL seed=0 vl=512 mask=0 vstart=256'),
                         ('packed_mask_restart_boundary', 'static_candidate'))

    def test_no_boundary_not_assumed(self):
        self.assertEqual(self.classify('vmacc.vv v24,v8,v16,v0.t')[0], 'unresolved')

    def test_merge_without_trial_is_qualified(self):
        self.assertEqual(self.classify('vmerge.vim v24,v8,15,v0')[1],
                         'opcode_family_candidate_no_trial')

    def test_gather_keeps_alternative(self):
        self.assertEqual(self.classify('vrgatherei16.vv v24,v8,v16,v0.t')[0],
                         'gather_operand_stream')

    def test_extension(self):
        self.assertEqual(self.classify('vzext.vf2 v24,v25,v0.t')[0],
                         'extension_overlap_dependency')

    def test_mask_logic_not_predication(self):
        self.assertEqual(self.classify('vmand.mm v8,v8,v16')[0], 'mask_logic_source_stream')

    def test_kernel_not_userspace_opcode(self):
        self.assertEqual(self.classify('kernel PC', pc=0xffffffff80013a18),
                         ('kernel_vector_state_wait', 'boundary_only'))

    def test_segment_not_setup_exception(self):
        self.assertEqual(self.classify('vlseg3e64.v v24,(a5),v0.t')[0],
                         'segment_request_completion')


if __name__ == '__main__':
    unittest.main()
