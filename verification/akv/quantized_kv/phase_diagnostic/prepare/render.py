"""Exact reversible three-call diagnostic transform, never a performance gate."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
BASE = ROOT / 'verification/out/q4-untimed-verify-fixed-layout-20261025-01'
SOURCE = BASE / 'attention_threeway_untimed.c'
SOURCE_SHA = 'd609762ba1857f4b797cf08e00cd4e9975f14920306cb3abc004b1ec0f9eac6c'
TIMED_SHA = '88e43efe2b0cbd5f184b6f3fdd1693a063b3fb39fd1e03ff64d79bc3c63f1064'
PREFIX = b'QUANT_DIAG_HSB_'
START = b'    const uint64_t start=strided_cycles();\n'
END = b'    const uint64_t elapsed=strided_cycles()-start;\n'
EDITS = (
    (b'THREEWAY_TRIALS = 6', b'THREEWAY_TRIALS = 3'),
    (b'/* Each mode appears at mirror positions, without comparisons across ELFs. */',
     b'/* Diagnostic: only first H/S/B entries execute; unused mirror entries are not repeats. */'),
    (b'kv_head=0 trials=6 scale=', b'kv_head=0 trials=3 scale='),
    (b'SUITE_PASS trials=6 outputs=768 rvv_exact=1 repeats_exact=1',
     b'SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0'),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def timed(data):
    if data.count(START) != 1 or data.count(END) != 1:
        raise ValueError('Ambiguous timer boundary')
    lo, hi = data.index(START), data.index(END) + len(END)
    if hi <= lo:
        raise ValueError('Reversed timer boundary')
    return data[lo:hi]


def replace_one(data, old, new):
    if data.count(old) != 1:
        raise ValueError('Missing or duplicate exact edit')
    return data.replace(old, new, 1)


def inverse(data):
    if data.count(PREFIX) != 4 or b'QUANT_THREEWAY_' in data:
        raise ValueError('Wrong diagnostic protocol')
    data = data.replace(PREFIX, b'QUANT_THREEWAY_')
    for old, new in reversed(EDITS):
        data = replace_one(data, new, old)
    if digest(data) != SOURCE_SHA:
        raise ValueError('Inverse differs from accepted source')
    return data


def render(data):
    if digest(data) != SOURCE_SHA:
        raise ValueError('Accepted source identity changed')
    source = data
    for old, new in EDITS:
        data = replace_one(data, old, new)
    if data.count(b'QUANT_THREEWAY_') != 4:
        raise ValueError('Wrong original protocol count')
    data = data.replace(b'QUANT_THREEWAY_', PREFIX)
    if inverse(data) != source or timed(data) != timed(source) or digest(timed(data)) != TIMED_SHA:
        raise ValueError('Source/timed-region preservation failed')
    return data


def provenance(data):
    source = inverse(data)
    if render(source) != data:
        raise ValueError('Not the exact successor')
    return dict(original_sha256=SOURCE_SHA, generated_sha256=digest(data),
                timed_region_sha256=digest(timed(data)), inverse_sha256=digest(source),
                trial_order=[0, 1, 2], trials=3, outputs_per_trial=768, total_outputs=2304,
                expected_qbs_commands=8, repeated_trials=0, diagnostic_only=True,
                numerical_guard_csr_checks_preserved=True,
                retained_repeat_branch='Dormant: each mode visited once; never claimed as tested',
                timed_source_identical=True, timed_machine_identity=False,
                accepted_six_call_evidence_replaced=False, execution='NOT_RUN')
