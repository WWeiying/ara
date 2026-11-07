"""Exact full-GGML integration of the already measured ordered Norm helpers."""
from pathlib import Path

from audit import digest, require
from rms_norm_source import START, END, SUM, group
from rms_norm_output_source import OUTPUT

MAIN=Path('/home/wangwy/openproject/ara_dsa')
LIVE=Path('/home/wangwy/llama/llama.cpp')
OPS=Path('ggml/src/ggml-cpu/ops.cpp')
ARCH=Path('ggml/src/ggml-cpu/arch/riscv')
ORIGINAL_SHA='7e8dea5f434230002de9bc5817422ebcebda59207f7b691b385af961414a6b14'
MEMBER='ops.cpp.o'


def transform(original):
    body=group(original);operations=[]
    def change(before,after):
        nonlocal body
        require(body.count(before)==1,'Exact Norm integration anchor required')
        body=body.replace(before,after,1);operations.append(dict(before=before,after=after))
    anchor='    GGML_ASSERT(eps >= 0.0f);\n\n    // TODO: optimize\n'
    change(anchor,'    GGML_ASSERT(eps >= 0.0f);\n\n'
        '    auto rvv_rms = ggml_rvv_rms_begin(FUSE_OP == GGML_RMS_NORM_FUSE_OP_MUL, ne00, ith, nth);\n\n'
        '    // TODO: optimize\n')
    replacement='''                ggml_float sum = 0.0;
                // worth switching to explicit SIMD?
                if (!ggml_rvv_rms_sum_row(&rvv_rms, x, (size_t)ne00, &sum)) {
                    for (int64_t i00 = 0; i00 < ne00; i00++) {
                        sum += (ggml_float)(x[i00] * x[i00]);
                    }
                }
'''
    change(SUM,replacement)
    change(OUTPUT,'''                    if (!ggml_rvv_rms_output_row(&rvv_rms, y, x, w, scale, (size_t)ne00)) {
                        for (int64_t i00 = 0; i00 < ne00; i00++) {
                            y[i00] = x[i00] * scale * w[i00];
                        }
                    }
''')
    anchor='    }\n}\n\nvoid ggml_compute_forward_rms_norm(\n'
    change(anchor,'    }\n    ggml_rvv_rms_finish(&rvv_rms);\n}\n\nvoid ggml_compute_forward_rms_norm(\n')
    restored=body
    for op in reversed(operations):
        require(restored.count(op['after'])==1,'Nonreversible Norm edit')
        restored=restored.replace(op['after'],op['before'],1)
    require(restored==group(original),'Original Norm arithmetic does not restore exactly')
    result=original.replace(group(original),body,1)
    include='#include "vec.h"\n'
    require(result.count(include)==1,'Exact include anchor')
    result=result.replace(include,include+'#include "arch/riscv/rms-norm.h"\n',1)
    return result,dict(operations=operations,original_math_retained_in_fallback=True,
        original_group_reversible=True,unrelated_source_text_unchanged=True,
        default_enabled=False,selection='Per operator RV64/V/FP64, entry vstart0 and legal FRM; explicit env',
        runtime_flag='GGML_RISCV_ORDERED_RMS',trace_flag='GGML_RISCV_ORDERED_RMS_TRACE')


def header_inventory():
    result={}
    for filename,canonical in (('rms-sum.h','rms_sum.h'),('rms-output.h','rms_output.h')):
        source=MAIN/'software/rvv/experimental/ordered_rms_norm'/canonical
        live=LIVE/ARCH/filename
        require(live.read_bytes()==source.read_bytes(),'Backend helper differs from measured canonical body')
        result[str(live)]=digest(source)
    result[str(LIVE/ARCH/'rms-norm.h')]=digest(LIVE/ARCH/'rms-norm.h')
    return result
