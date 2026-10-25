#!/usr/bin/env python3
"""Hash-locked, reversible post-timing-only H/S/B verifier transform."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ORIGINAL = ROOT / ('verification/out/akv-quantkv-threeway-fasthex-q4-build-20261025-01/'
                   'source/attention_threeway_fast_hex.c')
ORIGINAL_SHA256 = '8e5d8edf7aa79ae615a9eb2f6b9cecc8f27e1fc93e827f88ca4203788c34324a'
START = b'    const uint64_t start=strided_cycles();\n'
END = b'    const uint64_t elapsed=strided_cycles()-start;\n'
CHECK_START = b'    float max_abs=0.0f,pair_max_abs=0.0f;\n'
CHECK_END = b'    if (errors) return 1;\n'

OLD_COMPARE = b'''        differences+=bits(y)!=bits(baseline[head][d]);
        if (mode!=MODE_QBS) errors+=bits(y)!=bits(baseline[head][d]);
        if (seen[mode]) errors+=bits(y)!=bits(mode_previous[mode][head][d]);
        else mode_previous[mode][head][d]=y;
'''
NEW_COMPARE = b'''        uint32_t y_word, baseline_word;
        __builtin_memcpy(&y_word, &y, sizeof(y_word));
        __builtin_memcpy(&baseline_word, &baseline[head][d], sizeof(baseline_word));
        differences+=y_word!=baseline_word;
        if (mode!=MODE_QBS) errors+=y_word!=baseline_word;
        if (seen[mode]) {
          uint32_t previous_word;
          __builtin_memcpy(&previous_word, &mode_previous[mode][head][d], sizeof(previous_word));
          errors+=y_word!=previous_word;
        } else mode_previous[mode][head][d]=y;
'''
OLD_PADDING = b'''      for (unsigned d=DIM; d<STRIDE; ++d)
        errors+=bits(output.data[head][d])!=UINT32_C(0xa5a5a5a5);
'''
NEW_PADDING = b'''      for (unsigned d=DIM; d<STRIDE; ++d) {
        uint32_t padding_word;
        __builtin_memcpy(&padding_word, &output.data[head][d], sizeof(padding_word));
        errors+=padding_word!=UINT32_C(0xa5a5a5a5);
      }
'''
OLD_SEEN = b'    ++seen[mode];\n'
NEW_SEEN = OLD_SEEN + b'''    uint32_t max_abs_word, pair_max_abs_word;
    __builtin_memcpy(&max_abs_word, &max_abs, sizeof(max_abs_word));
    __builtin_memcpy(&pair_max_abs_word, &pair_max_abs, sizeof(pair_max_abs_word));
'''
OLD_ARGS = b'        bits(max_abs),bits(pair_max_abs),differences,errors);\n'
NEW_ARGS = b'        max_abs_word,pair_max_abs_word,differences,errors);\n'
OLD_OUTPUT = b'''    for (unsigned head=0; head<HEADS; ++head)
      for (unsigned d=0; d<DIM; ++d) fast_hex32(bits(output.data[head][d]));
'''
NEW_OUTPUT = b'''    for (unsigned head=0; head<HEADS; ++head)
      for (unsigned d=0; d<DIM; ++d) {
        uint32_t output_word;
        __builtin_memcpy(&output_word, &output.data[head][d], sizeof(output_word));
        fast_hex32(output_word);
      }
'''
EDITS = ((OLD_COMPARE, NEW_COMPARE), (OLD_PADDING, NEW_PADDING),
         (OLD_SEEN, NEW_SEEN), (OLD_ARGS, NEW_ARGS), (OLD_OUTPUT, NEW_OUTPUT))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def region(data, start, end):
    if data.count(start) != 1 or data.count(end) != 1:
        raise ValueError('Missing or ambiguous source boundary')
    lo, hi = data.index(start), data.index(end) + len(end)
    if hi <= lo:
        raise ValueError('Reversed source boundary')
    return lo, hi


def check_body(data):
    lo, hi = region(data, CHECK_START, CHECK_END)
    return data[lo:hi]


def substitute(data, edits):
    for old, new in edits:
        if data.count(old) != 1:
            raise ValueError('Missing or duplicate exact replacement')
        data = data.replace(old, new, 1)
    return data


def inverse(data):
    lo, hi = region(data, CHECK_START, CHECK_END)
    body = substitute(data[lo:hi], [(new, old) for old, new in reversed(EDITS)])
    original = data[:lo] + body + data[hi:]
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError('Inverse differs from frozen fasthex main')
    return original


def render(original):
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError('Frozen fasthex main identity differs')
    lo, hi = region(original, CHECK_START, CHECK_END)
    data = original[:lo] + substitute(original[lo:hi], EDITS) + original[hi:]
    if inverse(data) != original:
        raise ValueError('Not exactly reversible')
    return data


def provenance(original, generated):
    if inverse(generated) != original or render(original) != generated:
        raise ValueError('Generated source/provenance mismatch')
    lo, hi = region(original, CHECK_START, CHECK_END)
    new_lo, new_hi = region(generated, CHECK_START, CHECK_END)
    a, b = region(original, START, END)
    if (original[:lo] != generated[:new_lo] or original[hi:] != generated[new_hi:]
            or b >= lo):
        raise ValueError('Change escaped post-timing verification')
    return dict(state='SOURCE_TRANSFORM_ONLY_NOT_BUILT',
                source_variant='UNTIMED_BUILTIN_BITCOPY_LOCAL_REUSE',
                original_sha256=digest(original), generated_sha256=digest(generated),
                inverse_sha256=digest(inverse(generated)),
                unchanged_prefix_sha256=digest(original[:lo]),
                unchanged_suffix_sha256=digest(original[hi:]),
                timed_region_sha256=digest(original[a:b]),
                prefix_including_csr_and_counter_checks_identical=True,
                new_global_arrays=False, machine_code_identity_claimed=False,
                trial_order=[0, 1, 2, 2, 1, 0], output_words_per_trial=768,
                output_hex_characters=36864, timeout_seconds=10800,
                performance_claim=False, execution='NOT_RUN')
