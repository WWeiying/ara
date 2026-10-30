#!/usr/bin/env python3
"""Reversible, hash-locked printing-only successor of the sealed H/S/B main."""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINAL = HERE.parent / 'attention_threeway_main.c'
ORIGINAL_SHA256 = '1c0eb4bdaca3fc171931885392c6644920877889059c3761a7a084ba0f6b758a'
INCLUDE_ROOT = b'verification/akv/quantized_kv/'
HEADER_LINE = b'#include "verification/akv/quantized_kv/fast_hex/hex32.h"\n'
OLD_CALL = b'printf("%08x",bits(output.data[head][d]));'
NEW_CALL = b'fast_hex32(bits(output.data[head][d]));'
INCLUDES = tuple((b'#include "' + name + b'"\n',
                  b'#include "' + INCLUDE_ROOT + name + b'"\n')
                 for name in (b'threeway_strided_primitives.h', b'shared_rvv_qk.h'))
START = b'    const uint64_t start=strided_cycles();\n'
END = b'    const uint64_t elapsed=strided_cycles()-start;\n'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(data, old, new):
    if data.count(old) != 1 or new in data:
        raise ValueError('Missing, duplicate, or already replaced source fragment')
    return data.replace(old, new, 1)


def timed_region(data):
    if data.count(START) != 1 or data.count(END) != 1:
        raise ValueError('Ambiguous measurement window')
    start, end = data.index(START), data.index(END) + len(END)
    if end <= start:
        raise ValueError('Reversed measurement window')
    return data[start:end]


def render(original):
    if digest(original) != ORIGINAL_SHA256:
        raise ValueError('Sealed original main identity differs')
    data = original
    for old, new in INCLUDES:
        data = replace_once(data, old, new)
    data = replace_once(data, OLD_CALL, NEW_CALL)
    data = HEADER_LINE + data
    if timed_region(data) != timed_region(original) or inverse(data) != original:
        raise ValueError('Printing successor is not exactly reversible')
    return data


def inverse(data):
    if not data.startswith(HEADER_LINE) or data.count(HEADER_LINE) != 1:
        raise ValueError('Missing or duplicate emitter include')
    data = data[len(HEADER_LINE):]
    data = replace_once(data, NEW_CALL, OLD_CALL)
    for old, new in reversed(INCLUDES):
        data = replace_once(data, new, old)
    if digest(data) != ORIGINAL_SHA256:
        raise ValueError('Inverse does not match the sealed original')
    return data


def provenance(original, rendered):
    if inverse(rendered) != original or render(original) != rendered:
        raise ValueError('Source/provenance mismatch')
    return dict(original_source=str(ORIGINAL), original_sha256=digest(original),
                generated_sha256=digest(rendered), inverse_sha256=digest(inverse(rendered)),
                timed_region_sha256=digest(timed_region(original)),
                timed_region_source_identical=True, output_call_replacements=1,
                include_path_qualifications=2, stdout_contract='unchanged eight lowercase hex characters',
                trial_order=[0, 1, 2, 2, 1, 0], output_words_per_trial=768,
                output_hex_characters=36864, machine_code_identity_claimed=False)
