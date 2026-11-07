"""One exact output-loop edit on the already checked ordered-sum candidate."""
from audit import require
from rms_norm_source import translation_unit

OUTPUT = '''                    for (int64_t i00 = 0; i00 < ne00; i00++) {
                        y[i00] = x[i00] * scale * w[i00];
                    }
'''
VECTOR_OUTPUT = '''                    if (!ggml_rvv_fused_rms_output(y, x, w, scale, (size_t)ne00)) {
                        for (int64_t i00 = 0; i00 < ne00; i00++) {
                            y[i00] = x[i00] * scale * w[i00];
                        }
                    }
'''


def candidate(source, prefix='candidate'):
    text = translation_unit(source, True, prefix)
    require(text.count(OUTPUT) == 1 and text.count('#include "rms_sum.h"\n') == 1,
            'Fused output source changed')
    return text.replace(OUTPUT, VECTOR_OUTPUT, 1).replace(
        '#include "rms_sum.h"\n', '#include "rms_sum.h"\n#include "rms_output.h"\n', 1)


def caller(completed):
    anchor = 'int main() {\n'
    require(completed.count(anchor) == 1 and completed.count('timing=call_and_csr_completion') == 1,
            'Completed caller changed')
    return completed.replace(anchor, 'extern "C" unsigned rms_output_checks();\n'+anchor+
                             '    if (rms_output_checks()) return 1;\n', 1)
