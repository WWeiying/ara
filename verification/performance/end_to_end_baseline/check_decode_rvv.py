"""Validate complete RVV output/state records; ISA-model cycles are not timing."""
import math
import re
import struct

from audit import require
from check_projection_native import checksum

SCOPE = ('RVV_DECODE_SCOPE m=1 n=128 parts=7 stages=4 trials=1 full_k=1 full_n=0 full_ggml=0 '
         'q4_layout=r32 q6_layout=row_major atol=2e-3 rtol=2e-3 '
         'reference=existing_expected independent_rvv_oracle=0')
K = (2048, 2048, 2048, 2048, 2048, 6144, 2048)
PROFILE = (1, 2, 1, 1, 1, 2, 2)
STAGE = (0, 0, 0, 1, 1, 2, 3)


def fields(line, tag):
    require(line.startswith(tag+' '), 'Wrong numeric record prefix')
    words = line[len(tag)+1:].split()
    require(words and all(re.fullmatch(r'[a-z][a-z0-9_]*=[0-9]+', w) for w in words), 'Malformed numeric record')
    pairs = [word.split('=') for word in words]
    require(len({key for key,value in pairs}) == len(pairs), 'Duplicate numeric record field')
    result = {key:int(value) for key,value in pairs}
    require(all(0 <= v < 1 << 64 for v in result.values()), 'Record integer outside architectural width')
    return result


def f32(value): return struct.unpack('<f', struct.pack('<f', value))[0]
def bits(value): return struct.unpack('<I', struct.pack('<f', value))[0]
def number(value): return struct.unpack('<f', struct.pack('<I', value))[0]


def differences(actual, expected):
    require(len(actual) == len(expected) == 128, 'Full output row required')
    max_abs, max_rel, ulp, changed, mismatches = 0.0, 0.0, 0, 0, 0
    for a, b in zip(actual, expected):
        require(0 <= a < 1 << 32 and 0 <= b < 1 << 32, 'Float word outside 32 bits')
        x, y = number(a), number(b)
        require(math.isfinite(x) and math.isfinite(y), 'Nonfinite reference/output')
        absolute = abs(f32(x-y)); magnitude = abs(y)
        relative = f32(absolute / max(magnitude, f32(1e-12)))
        bound = f32(f32(2e-3) + f32(f32(2e-3)*magnitude))
        mismatches += absolute > bound
        order = lambda word: (~word & 0xffffffff) if word & 0x80000000 else word | 0x80000000
        distance = 0 if x == y == 0 else abs(order(a)-order(b))
        ulp = max(ulp, distance); changed += a != b
        max_abs, max_rel = max(max_abs, absolute), max(max_rel, relative)
    return dict(bit_differences=changed, max_abs_bits=bits(max_abs), max_rel_bits=bits(max_rel),
                max_ulp=ulp, mismatches=mismatches)


def check(text, golden, packed, *, isa_model=False):
    require(len(golden) == 7 and all(len(row) == 512 for row in golden) and
            list(map(len, packed)) == [2336, 2336, 7008, 2336], 'RVV oracle geometry')
    lines = text.replace('\r', '').splitlines()
    require(lines.count(SCOPE) == 1 and not re.search(
        r'RVV_DECODE_FAIL|Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@|mcause_val', text, re.M), 'Scope or execution failure')
    def rows(tag): return [fields(line, tag) for line in lines if line.startswith(tag+' ')]
    prep, parts, output, total = [rows(tag) for tag in
        ('RVV_DECODE_PREP', 'RVV_DECODE_PART', 'RVV_DECODE_OUTPUT', 'RVV_DECODE_RESULT')]
    require(tuple(map(len, (prep, parts, output, total))) == (4, 7, 896, 1), 'Missing/extra RVV work')
    for s,row in enumerate(prep):
        expected = dict(stage=s, k=6144 if s == 2 else 2048, before_fcsr=8 if s == 0 else 9,
            fcsr=9, before_vcsr=5 if s == 0 else 3, vcsr=3, before_vstart=0, vstart=0,
            checksum=checksum(packed[s]), payload_errors=0, guard_errors=0, state_errors=0)
        require(set(row) == set(expected) | {'cycles'} and row['cycles'] > 0 and
                all(row[key] == value for key,value in expected.items()), 'Preparation payload/state mismatch')
    require([(r['part'],r['idx']) for r in output] == [(p,i) for p in range(7) for i in range(128)] and
            all(set(r) == {'part','idx','bits'} for r in output), 'Output word order/identity mismatch')
    payloads, metrics = [], []
    for p,row in enumerate(parts):
        words = [r['bits'] for r in output[p*128:p*128+128]]
        diff = differences(words, struct.unpack('<128I', golden[p])); metrics.append(diff)
        payload = struct.pack('<128I', *words); payloads.append(payload.hex())
        expected = dict(part=p, profile=PROFILE[p], k=K[p], stage=STAGE[p], calls=1 if PROFILE[p] == 1 else 128,
            before_fcsr=9, fcsr=9, before_vcsr=3, vcsr=3, before_vstart=0, vstart=0,
            checksum=checksum(payload), guard_errors=0, state_errors=0, errors=0, **diff)
        require(diff['mismatches'] == 0 and set(row) == set(expected) | {'dispatch','execution'} and
                all(row[key] == value for key,value in expected.items()) and
                row['dispatch'] > 0 and row['execution'] > 0, 'RVV output/numerical/state mismatch')
    row = total[0]
    expected = dict(preparation=sum(p['cycles'] for p in prep), dispatch=sum(p['dispatch'] for p in parts),
        execution=sum(p['execution'] for p in parts), parts=7, outputs=896, q4_calls=4, q6_calls=384, errors=0)
    require(set(row) == set(expected) | {'region'} and all(row[k] == v for k,v in expected.items()) and
            row['region'] >= row['preparation']+row['dispatch']+row['execution'], 'RVV interval/work accounting')
    if isa_model:
        terminal = rows('SPIKE_SOC_EXIT')
        require(len(terminal) == 1 and set(terminal[0]) == {'status','uart_bytes'} and
                terminal[0]['status'] == 0 and terminal[0]['uart_bytes'] > 0, 'Independent model did not exit cleanly')
    return dict(outputs_hex=payloads, differences_from_qbs_reference=metrics,
                preparation_state=[{k:v for k,v in r.items() if k != 'cycles'} for r in prep],
                part_state=[{k:v for k,v in r.items() if k not in ('dispatch','execution')} for r in parts],
                outputs=896, q4_calls=4, q6_calls=384, real_decode_inputs=True,
                performance_measured=False if isa_model else None,
                source='Exact-ELF Spike execution' if isa_model else 'RVV RTL output records',
                cycle_fields_ignored_for_performance=isa_model,
                numerical_policy='QBS reference tolerance screen; exact emitted RVV words retained for ISA comparison')


def compare_isa(rtl, isa):
    for key in ('outputs_hex', 'preparation_state', 'part_state', 'outputs', 'q4_calls', 'q6_calls'):
        require(rtl[key] == isa[key], 'RVV differs from independent ISA model: '+key)
    return dict(bitwise_outputs=896, state_records=11, timing_compared=False)
