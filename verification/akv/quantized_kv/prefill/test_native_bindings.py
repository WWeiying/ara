"""Prevent the standalone full-call probes from silently using scalar V decode."""
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


class BindingsTest(unittest.TestCase):
    def test_shared_decoder_in_all_native_drivers(self):
        for name in ('native_main.c','native_full_main.c','native_strided_main.c',
                     'native_planned_main.c','native_aligned_main.c','native_selector_main.c',
                     'native_decode_profile.c'):
            text=(HERE/name).read_text()
            with self.subTest(name=name):
                self.assertNotIn('dequantize_row_q8_0',text)
                self.assertIn('prefill_native_decode',text)
        helper=(HERE/'native_main.c').read_text()
        self.assertIn('#include "software/akv/experimental/quantized_kv/q8_0_value.h"',helper)
        self.assertIn('akv_quant_q8_0_value(source,out,(size_t)n);',helper)

    def test_actual_backend_uses_same_decoder(self):
        frontend=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp').read_text()
        self.assertIn('#include "q8_0_value.h"',frontend)
        self.assertIn('akv_quant_q8_0_value(source, output, static_cast<size_t>(elements));',frontend)
        self.assertNotIn('dequantize_row_q8_0',frontend)
        self.assertEqual(frontend.count('bindings.decode = decode_value;'),2)


if __name__=='__main__':unittest.main()
