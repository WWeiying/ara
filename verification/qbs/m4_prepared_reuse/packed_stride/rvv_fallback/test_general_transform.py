import unittest
from pathlib import Path

from general_transform import transform

LIVE = Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp')


class TransformTests(unittest.TestCase):
    def test_bounded_shared_layout(self):
        source = LIVE.read_text()
        result = transform(source)
        self.assertEqual(result.count('if constexpr (INTER_SIZE == 1 &&\n'), 2)
        self.assertEqual(result.count('ggml_qbs_strided_input::quantize<4, block, 4*bytes>'), 1)
        self.assertEqual(result.count('ggml_qbs_strided_input::quantize<1, block, bytes>'), 2)
        self.assertIn('nb10 != sizeof(float) || nb11 != size_t(ne10)*sizeof(float)', result)

    def test_other_execution_methods_unchanged(self):
        source = LIVE.read_text()
        result = transform(source)
        boundary = '    void forward_mul_mat_id'
        self.assertEqual(source[source.index(boundary):], result[result.index(boundary):])
        boundary = '    void forward_mul_mat(ggml_compute_params * params, ggml_tensor * op) {'
        self.assertEqual('#include "strided_input.h"\n' + source[:source.index(boundary)],
                         result[:result.index(boundary)])

    def test_refuses_unreviewed_shape(self):
        with self.assertRaises(ValueError):
            transform(LIVE.read_text().replace('    void forward_mul_mat_id', '    void changed_method'))


if __name__ == '__main__':
    unittest.main()
