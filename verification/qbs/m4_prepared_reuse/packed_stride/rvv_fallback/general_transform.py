"""Successor address repair for the shared RVV/QBS one-byte interleave path.

Produces source text only. It never installs into a live runtime or changes
the frozen QBS-only repair used by earlier acceptance runs.
"""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent


def transform(source):
    parent = HERE.parent
    sys.path.insert(0, str(parent))
    spec = importlib.util.spec_from_file_location('accepted_qbs_stride_repair', parent / 'repair.py')
    repair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repair)
    result = repair.transform(source)
    before = 'if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {'
    after = ('if constexpr (INTER_SIZE == 1 &&\n'
             '                              (PARAM_TYPE == GGML_TYPE_Q8_K || PARAM_TYPE == GGML_TYPE_Q8_0)) {')
    start = result.index('    void forward_mul_mat(ggml_compute_params * params, ggml_tensor * op) {')
    end = result.index('    void forward_mul_mat_id', start)
    body = result[start:end]
    if body.count(before) != 2:
        raise ValueError('Expected exactly the reviewed group and tail gather guards')
    return result[:start] + body.replace(before, after) + result[end:]
