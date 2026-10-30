"""Fail-closed production delta checks without editing the runtime."""
import unittest

from stage import LIVE, PUBLIC, REPAIR, files, transform


class StageTests(unittest.TestCase):
    def test_exact_kernel_sources(self):
        result = {str(k): v for k, v in files().items()}
        self.assertEqual(len(result), 4)
        self.assertEqual(result['arch/riscv/q8_K-m4-packed.h'], (PUBLIC / 'q8_K-m4-packed.h').read_text())
        self.assertEqual(result['arch/riscv/qbs-strided-input.h'], (REPAIR / 'strided_input.h').read_text())

    def test_one_selector_both_paths_and_identity(self):
        result = {str(k): v for k, v in files().items()}
        for name in ('repack.cpp', 'arch/riscv/q8_K-prepared-reuse.h'):
            self.assertEqual(result[name].count('ggml_riscv_q8_K_m4_packed::selected_quantize('), 1)
            self.assertNotIn('ggml_riscv_q8_K_m4::quantize', result[name])
        cache = result['arch/riscv/q8_K-prepared-reuse.h']
        self.assertIn('identity.producer_tag=ggml_riscv_q8_K_m4_packed::producer_tag();', cache)
        self.assertIn('if(vector && policy.fill)', cache)
        self.assertIn('if((before>>5)!=0 || start) return false;', cache)

    def test_unchanged_existing_trace_records(self):
        result = {str(k): v for k, v in files().items()}
        for name in ('repack.cpp', 'arch/riscv/q8_K-prepared-reuse.h'):
            original = (LIVE / name).read_text()
            for line in original.splitlines():
                if 'GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=' in line or 'GGML_RISCV_QBS_M4_CACHE epoch=' in line:
                    self.assertIn(line, result[name])

    def test_nonreviewed_source_fails(self):
        source = (LIVE / 'repack.cpp').read_text()
        cache = (PUBLIC / 'q8_K-prepared-reuse.h').read_text()
        with self.assertRaises(ValueError):
            transform(source.replace('vector_used = ggml_riscv_q8_K_m4::quantize(', 'vector_used = changed('), cache)
        with self.assertRaises(ValueError):
            transform(source, cache.replace('identity.producer_tag=1;', 'identity.producer_tag=3;'))

    def test_not_idempotent_on_already_patched_source(self):
        modified = transform((LIVE / 'repack.cpp').read_text(), (PUBLIC / 'q8_K-prepared-reuse.h').read_text())
        with self.assertRaises(ValueError):
            transform(*modified)


if __name__ == '__main__':
    unittest.main()
