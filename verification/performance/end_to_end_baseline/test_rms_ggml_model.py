from pathlib import Path
import unittest

from rms_ggml_model import driver, norm_work


def fixture():
    lines = ['TRACE_CONTEXT_VARIANT_BEGIN variant=0', 'TRACE_CONTEXT_VARIANT_END variant=0',
             'TRACE_CONTEXT_VARIANT_BEGIN variant=1']
    for kind in range(2):
        for step in range(2):
            totals = {128: 26880, 2048: 2202} if not step else {128: 672, 2048: 57}
            counts = {128: 56, 2048: 57}
            for width, count in counts.items():
                q, r = divmod(totals[width], count)
                for i in range(count):
                    n = q + (i < r)
                    lines.append(f'GGML_RISCV_RMS_EXEC enabled=1 fused=1 ith=0 nth=1 width={width} '
                                 f'sum_fast={n} sum_scalar=0 output_fast={n} output_scalar=0')
            lines.append(f'OUTPUT_MODEL_STEP enabled=1 kind={kind} step={step} token=1 fcsr=9 vcsr=5 outputs=151936')
    return '\n'.join(lines + ['TRACE_CONTEXT_VARIANT_END variant=1'])


class NormModel(unittest.TestCase):
    def test_full_graph_totals(self):
        result = norm_work(fixture())
        self.assertEqual((result['operators'], result['sum_rows']), (452, 59622))

    def test_nonfused_sum_does_not_claim_fused_output(self):
        text = fixture().replace('fused=1', 'fused=0').replace('output_fast=480', 'output_fast=0')
        import re
        text = re.sub(r'output_fast=\d+', 'output_fast=0', text)
        self.assertEqual(norm_work(text)['sum_rows'], 59622)

    def test_disabled_missing_extra_fallback_and_wrong_rows_rejected(self):
        text = fixture()
        for bad in (text.replace('enabled=1 fused=', 'enabled=0 fused=', 1),
                    text.replace('sum_fast=480', 'sum_fast=479', 1),
                    text.replace('nth=1', 'nth=2', 1),
                    text.replace('sum_scalar=0', 'sum_scalar=1', 1),
                    text.replace('output_fast=480', 'output_fast=479', 1),
                    text.replace('TRACE_CONTEXT_VARIANT_END variant=1', ''),
                    text.replace('GGML_RISCV_RMS_EXEC', 'GGML_RISCV_RMS_UNKNOWN', 1)):
            with self.subTest(bad=bad[:120]), self.assertRaises(ValueError):
                norm_work(bad)

    def test_driver_preserves_comparison_and_sets_both_policies(self):
        source = Path(__file__).with_name('trace_context_model_driver.cpp').read_text()
        result = driver(source)
        self.assertIn('GGML_RISCV_ORDERED_RMS_TRACE', result)
        self.assertIn('!std::memcmp(va.data(),vb.data(),na*4)', result)
        self.assertIn('performance=not_measured', result)
        for bad in ('', source + source):
            with self.assertRaises(ValueError):
                driver(bad)


if __name__ == '__main__':
    unittest.main()
