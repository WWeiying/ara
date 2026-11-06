import unittest

from rms_norm_source import START,END,SUM,ORDERED,group,translation_unit,shape_group


class RMSNormSourceTests(unittest.TestCase):
    def fixture(self):
        return 'unrelated\n'+START+'enum X {};\n'+SUM+'void ggml_compute_forward_rms_norm_mul_fused(\n'+END+'rest'

    def test_only_the_original_sum_changes(self):
        source=self.fixture();a=translation_unit(source);b=translation_unit(source,True)
        self.assertIn(group(source),a)
        self.assertIn(group(source).replace(SUM,ORDERED,1),b)
        self.assertNotIn(SUM,b)
        self.assertIn('candidate_rms_norm(',b)
        self.assertIn('ggml_compute_forward_rms_norm_mul_fused(&params,&norm,&dst)',b)
        self.assertIn('dst.src[0]=&norm;dst.src[1]=&w',a)

    def test_ambiguous_or_changed_reduction_rejects(self):
        source=self.fixture()
        for altered in (source+START,source.replace(END,''),source.replace(SUM,'changed'),source.replace(SUM,SUM+SUM,1)):
            with self.subTest(altered=altered),self.assertRaises(ValueError):group(altered)

    def test_original_shape_helper_is_not_reimplemented(self):
        body='bool ggml_are_same_shape(const struct ggml_tensor * t0, const struct ggml_tensor * t1) {\n  return true;\n}\n\n'
        end='bool ggml_are_same_stride(const struct ggml_tensor * t0, const struct ggml_tensor * t1) {\n'
        self.assertEqual(shape_group(body+end),'#include "ggml.h"\n'+body)
        with self.assertRaises(ValueError):shape_group(body+body+end)


if __name__=='__main__':unittest.main()
