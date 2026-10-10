"""Finite software-only FCLASS/DIV/SQRT matrix; exact gold and raw783 targets."""
import argparse
from collections import defaultdict
from fractions import Fraction
from functools import lru_cache
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import preflight_c910_float_edge776 as previous
import audit_remaining_toggle776 as coverage

base, life, require, build, old = previous.base, previous.life, previous.require, previous.build, previous.old
ROOT, OUT = life.ROOT, life.OUT
APP = ROOT / 'apps/riscv-tests/isa/rv64uv/fclass_divsqrt_matrix783.c'
BASE = OUT / 'qbs-k2-pending-offline-admitted783-agent-20261008-01'
BASE_SHA = '8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
GUARD = previous.GUARD
SYMBOLS = ('tohost', 'num_failed', 'g75_result', 'trap_fail', 'matrix_checks',
    'matrix_a', 'matrix_b', 'matrix_dst', 'matrix_ledger', 'matrix_fcsr_restore') + tuple(
    'matrix_' + op + str(w) for w in (16, 32, 64)
    for op in ('load_a', 'load_b', 'class', 'div', 'sqrt', 'store')) + tuple(
    'matrix_initial_v' + str(v) for v in (8, 16, 24))
TARGETS = None


def encoding(width):
    require(type(width) is int and width in (16, 32, 64), 'Supported IEEE formats only')
    return {16: (10, 15), 32: (23, 127), 64: (52, 1023)}[width]


def value(bits, width):
    f, bias = encoding(width)
    require(type(bits) is int and 0 <= bits < 1 << width, 'Exact element encoding')
    sign, exp, mantissa = bits >> (width - 1), (bits >> f) & (2 * bias + 1), bits & ((1 << f) - 1)
    require(exp != 2 * bias + 1, 'Finite rational input required')
    power = (exp - bias if exp else 1 - bias) - f
    n = mantissa + ((1 << f) if exp else 0)
    return (-1 if sign else 1) * Fraction(n * (1 << max(power, 0)), 1 << max(-power, 0))


def classify(bits, width):
    f, bias = encoding(width)
    sign, exp, mantissa = bits >> (width - 1), (bits >> f) & (2 * bias + 1), bits & ((1 << f) - 1)
    if exp == 2 * bias + 1:
        index = 9 if mantissa & (1 << (f - 1)) else 8 if mantissa else 0 if sign else 7
    elif not exp:
        index = (2 if sign else 5) if mantissa else (3 if sign else 4)
    else:
        index = 1 if sign else 6
    return 1 << index


def inputs(width, phase, element):
    f, bias = encoding(width)
    require(type(phase) is int and 0 <= phase < 25 and type(element) is int and 0 <= element < 256 // width,
            'Closed phase/element domain')
    sign, inf = 1 << (width - 1), (2 * bias + 1) << f
    classes = (sign | inf, sign | (bias << f), sign | 1, sign, 0, 1, bias << f,
               inf, inf | 1, inf | (1 << (f - 1)))
    if phase < 10:
        return 'class', 0, classes[(phase + element) % 10], 0
    if phase < 20:
        rm, pass_ = divmod(phase - 10, 2)
        kind = (element + pass_) % 4
        mask = (1 << f) - 1
        mantissa = (0xaaaaaaaaaaaaaaaa & mask, 0x5555555555555555 & mask, mask, 0)[kind]
        return 'div', rm, (1 << f) | mantissa | (((element + pass_) & 1) << (width - 1)), (bias + 1 + (kind & 1)) << f
    rm = phase - 20
    return 'sqrt', rm, ((bias + 1) << f, 1, sign | (bias << f), (bias + 2) << f)[(rm + element) % 4], 0


def rounded(magnitude, width, rm, sign=False, square=False):
    """Binary search exact IEEE values; midpoint decisions use rationals only."""
    f, bias = encoding(width)
    require(type(rm) is int and rm in range(5) and type(sign) is bool and magnitude >= 0, 'Valid RM and magnitude')
    max_finite = ((2 * bias) << f) | ((1 << f) - 1)
    low, high = 0, max_finite
    while low < high:
        mid = (low + high + 1) // 2
        v = value(mid, width)
        if (v * v if square else v) <= magnitude:
            low = mid
        else:
            high = mid - 1
    v = value(low, width)
    exact = (v * v if square else v) == magnitude
    if exact:
        return low | (int(sign) << (width - 1)), 0
    require(low < max_finite, 'This finite matrix has no overflow rounding')
    midpoint = (v + value(low + 1, width)) / 2
    delta = magnitude - (midpoint * midpoint if square else midpoint)
    increment = (rm == 0 and (delta > 0 or delta == 0 and low & 1)
                 or rm == 4 and delta >= 0 or rm == 2 and sign or rm == 3 and not sign)
    result = low + int(bool(increment))
    flags = 1 | (2 if result < 1 << f else 0)
    return result | (int(sign) << (width - 1)), flags


def gold(width, phase, element):
    role, rm, a, b = inputs(width, phase, element)
    if role == 'class':
        return classify(a, width), 0
    if role == 'sqrt':
        if a >> (width - 1):
            f, bias = encoding(width)
            return ((2 * bias + 1) << f) | (1 << (f - 1)), 16
        return rounded(value(a, width), width, rm, square=True)
    result = value(a, width) / value(b, width)
    return rounded(abs(result), width, rm, result < 0)


@lru_cache(maxsize=75)
def images(width, phase):
    aa, bb, dst, flags = bytearray(), bytearray(), bytearray(), 0
    for e in range(256 // width):
        role, rm, a, b = inputs(width, phase, e)
        result, ff = gold(width, phase, e)
        aa.extend(a.to_bytes(width // 8, 'little')); bb.extend(b.to_bytes(width // 8, 'little'))
        dst.extend(result.to_bytes(width // 8, 'little')); flags |= ff
    return bytes(aa), bytes(bb), bytes(dst), flags


def parameters(text):
    result = {k: int(v) for k, v in re.findall(r'\b(\w+)=(-?\d+)(?=,|\s|\))', text)}
    return result


def dynamic_class_bits(params):
    require(params.get('OpGroup') == 2 and params.get('FpFormat') in (0, 1, 2)
            and params.get('EnableVectors') == params.get('TrueSIMDClass') == 1
            and params.get('Width') == 64 and params.get('SIMD_WIDTH') in (16, 32, 64)
            and params.get('NUM_LANES') * params['SIMD_WIDTH'] == 64, 'Exact active vector CLASS family')
    return {lane * params['SIMD_WIDTH'] + b for lane in range(params['NUM_LANES']) for b in range(10)}


def target_evidence():
    t = coverage.t
    pins = {}
    def bound(path, expected):
        require(t.digest(path) == expected, 'Static input drift: ' + str(path))
        pins[str(path)] = expected
        return path.read_bytes()
    m = json.loads(bound(BASE / 'admission-manifest.json', BASE_SHA))
    ledger = BASE / 'combined-inputs.txt'
    lines = bound(ledger, m['output_pins'][str(ledger)]).decode().splitlines()
    require(m['coverage_admitted'] is True and len(lines) == len(set(lines)) == 784, 'Exact formal783')
    cache = json.loads(bound(coverage.CACHE, coverage.CACHE_SHA))
    prefix = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(lines[:742] == bound(prefix, cache['input_pins'][str(prefix)]).decode().splitlines(), 'Frozen741 prefix')
    scopes = [s for s in cache['instances'] if '.i_ara.' in s and 'qbs' not in s and
              ('gen_operation_groups[2]' in s and s.endswith('i_fmt_slice')
               or s.endswith('x_ct_vfdsu_pack'))]
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for db in lines[742:]:
        files = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Exact native suffix owner')
        rows, sha = t.rows(files[0], scopes)
        require(sha == m['input_pins'][str(files[0])], 'Native783 suffix hash')
        pins[str(files[0])] = sha; union = t.union(union, rows)
    db = Path(lines[0]) / 'snps/coverage/db'
    for rel in ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml', 'shape/tgl.verilog.shape.xml'):
        bound(db / rel, m['input_pins'][str(db / rel)])
    shape = t.xml(db / 'shape/tgl.verilog.shape.xml')
    policy = OUT / 'current-population781-plus9700-prepared-agent-20261008-01'
    config = json.loads((policy / 'config.json').read_bytes())
    # This sealed exact EL inventory is only subtracted; no new policy is applied.
    pins[str(policy / 'config.json')] = t.digest(policy / 'config.json')
    el, whole = coverage.el_fields(bound(policy / 'combined.el', config['pins'][str(policy / 'combined.el')]).decode())
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    book = json.loads(bound(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    pkg = [p for p in book if Path(p).name == 'ara_pkg.sv']
    require(len(pkg) == 1, 'Unique frozen shuffle source')
    shuffle = bound(Path(pkg[0]), book[pkg[0]]).decode()
    targets, holds = [], []
    for scope, row in union.items():
        family = 'fpnew_opgroup_fmt_slice' if scope.endswith('i_fmt_slice') else 'ct_vfdsu_pack'
        defs = [d for d in shape.findall('tgldef') if d.get('chksum') == row['checksum'] and d.get('name').split(' (')[0] == family]
        require(len(defs) == 1, 'Exact checksum/family shape')
        params = parameters(defs[0].get('name'))
        if family == 'fpnew_opgroup_fmt_slice':
            if params.get('FpFormat') not in (0, 1, 2): continue
            allowed = dynamic_class_bits(params)
        offset = 0
        for n in defs[0].find('tglshape'):
            if n.tag == 'arrays': continue
            require(n.tag in ('node', 'vectornode'), 'Known binary typed node')
            lo, hi = int(n.get('right', '0')), int(n.get('left', '0'))
            width = 1 if n.tag == 'node' else abs(hi - lo) + 1
            name = n.get('name'); start = offset; offset += 2 * width
            if family == 'fpnew_opgroup_fmt_slice':
                if name not in ('slice_class_result', 'slice_vec_class_result'): continue
                bits = allowed
                predicate = 'CLASSIFY, vectorial, active FP16/32/64; each physical subslot sees all10 classes'
            else:
                ranges = {'ex4_denorm_frac': (64, 0, 52), 'ex4_single_denorm_frac': (32, 29, 23),
                          'ex4_half_denorm_frac': (16, 42, 10)}
                if name not in ranges: continue
                fmt, shift, size = ranges[name]
                slot = int(re.search(r'gen_num_lanes\[(\d+)\]', scope)[1])
                if slot >= 64 // fmt: continue
                lane = int(re.search(r'gen_lanes\[(\d+)\]', scope)[1])
                e = physical_element(fmt, lane, slot, shuffle)
                vals = [(int.from_bytes(images(fmt, phase)[2][e * (fmt // 8):(e + 1) * (fmt // 8)], 'little') & ((1 << encoding(fmt)[0]) - 1))
                        for phase in range(10, 20)]
                varying = {b for b in range(size) if {v >> b & 1 for v in vals} == {0, 1}}
                bits = {shift + b for b in varying}
                predicate = 'Active FP%d DIV, finite minnormal+dense mantissa /2,/4; dynamic fraction only' % fmt
            require(lo == 0 and bits <= set(range(width)), 'Exact ascending serialized bit layout')
            entries = el.get((scope, name), [])
            require(not any(b == 'MDA_HOLD' for _, b, _ in entries), 'No inferred MDA exclusion map')
            removed, ambiguous = coverage.excluded_bits(entries, set(range(width)))
            require(not ambiguous, 'Unbound directional EL ownership')
            if scope in whole: continue
            missing = [start + 2 * b + d for b in sorted(bits - removed) for d in (0, 1)
                       if not (int(row['bits'], 16) >> (row['width'] - 1 - start - 2 * b - d)) & 1]
            if missing:
                targets.append(dict(scope=scope, checksum=row['checksum'], signal=name, width=width,
                    raw_offset=start, logical_dynamic_bits=sorted(bits - removed), missing_coordinates=missing,
                    predicate=predicate, parameters=params, expected_direction_labels_bound=False))
        require(offset == row['width'], 'Complete binary shape layout')
    life.check(pins)
    return dict(population=783, baseline_seal=BASE_SHA, input_pins=pins, targets=targets,
        target_missing_slots=sum(len(t['missing_coordinates']) for t in targets),
        class_padding_excluded_from_targets=True, predicted_not_measured=True, official_percentage=None,
        no_EDA=True, no_EL=True, holds=holds)


def physical_element(width, lane, slot, text):
    require(width in (16, 32, 64) and lane in range(4) and slot in range(64 // width), 'Physical owner bounds')
    section = text.split('      4: unique case (ew)', 1)[1].split('          default:', 1)[0]
    block = section.split('rvv_pkg::EW%d: begin' % width, 1)[1].split('return idx', 1)[0]
    pairs = re.findall(r'idx\[(\d+)\]\s*=\s*(\d+)\s*;', block)
    table = {int(a): int(b) for a, b in pairs}
    require(len(pairs) == len(table) == 32 and set(table) == set(table.values()) == set(range(32)), 'Exact frozen shuffle permutation')
    owners = [e for e in range(256 // width) if all(table[e * (width // 8) + b] == lane * 8 + slot * (width // 8) + b for b in range(width // 8))]
    require(len(owners) == 1, 'Unique contiguous physical element')
    return owners[0]


def source_pins():
    global TARGETS
    TARGETS = target_evidence()
    book = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    require(life.digest(book) == '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b', 'Frozen source authority')
    original = json.loads(book.read_bytes())
    pins = dict(TARGETS['input_pins'], **{str(book): life.digest(book)})
    names = ('fpnew_pkg.sv', 'fpnew_noncomp.sv', 'fpnew_opgroup_fmt_slice.sv', 'fpnew_divsqrt_th_64_multi.sv',
             'ct_vfdsu_prepare.v', 'ct_vfdsu_round.v', 'ct_vfdsu_pack.v', 'ara_pkg.sv')
    for name in names:
        matches = [Path(p) for p in original if Path(p).name == name]
        require(len(matches) == 1, 'Unique frozen source ' + name)
        pins[str(matches[0])] = original[str(matches[0])]
    for p in (APP, Path(__file__), Path(__file__).with_name('test_preflight_fclass_divsqrt783.py')):
        pins[str(p.resolve())] = life.digest(p)
    life.check(pins)
    return pins


def linked(disassembly):
    instructions = re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8}|[0-9a-f]{4})\s+([\w.]+)', disassembly, re.M)
    vector = [(int(pc, 16), int(bits, 16), op) for pc, bits, op in instructions if op.startswith('v')]
    expected = ['vsetvli'] * 4 + ['vmv.v.i'] * 3 + [f'vle{w}.v' for w in (16, 32, 64) for _ in range(2)]
    expected += [f'vse{w}.v' for w in (16, 32, 64)] + ['vfclass.v', 'vfdiv.vv', 'vfsqrt.v'] * 3
    require(sorted(x[2] for x in vector) == sorted(expected), 'Exact25 explicit RVV instructions')
    for pc, insn, op in vector:
        if op in ('vfclass.v', 'vfsqrt.v'):
            require(insn & 127 == 0x57 and insn >> 26 == 0x13 and insn >> 12 & 7 == 1
                    and insn >> 20 & 31 == 8 and insn >> 15 & 31 == (16 if op == 'vfclass.v' else 0)
                    and insn >> 7 & 31 == 24 and insn >> 25 & 1 == 1, 'Independent unary RVV opcode')
        if op == 'vfdiv.vv':
            require(insn & 127 == 0x57 and insn >> 26 == 0x20 and insn >> 12 & 7 == 1
                    and insn >> 20 & 31 == 8 and insn >> 15 & 31 == 16 and insn >> 7 & 31 == 24
                    and insn >> 25 & 1 == 1, 'Independent DIV opcode')
    return [dict(pc=pc, opcode=hex(insn), mnemonic=op) for pc, insn, op in vector]


def validate(path, symbols):
    commits = build.parse_spike_commits(path)
    require('exception ' not in path.read_text() and not any(c.pc == symbols['trap_fail'] for c in commits), 'No trap')
    mapped = {symbols['matrix_' + op + str(w)]: (op, w) for w in (16, 32, 64)
              for op in ('load_a', 'load_b', 'class', 'div', 'sqrt', 'store')}
    init = {symbols['matrix_initial_v' + str(v)]: v for v in (8, 16, 24)}
    writers, memory, stores, init_seen = [], {}, {}, []
    saved_fcsr = None
    for c in commits:
        if c.pc in init:
            v = init[c.pc]
            require(c.vector_vl == 1024 and c.vector_vstart == 0 and c.vector_writes == {r: 0 for r in range(v, v + 8)}, 'Full initialized groups')
            init_seen.append(v)
        elif c.vector_writes:
            require(c.pc in mapped and mapped[c.pc][0] in ('load_a', 'load_b', 'class', 'div', 'sqrt'), 'No implicit vector writer')
            writers.append(c)
        if c.instruction & 127 == 0x73 and c.instruction >> 20 == 3 and c.instruction >> 12 & 7 == 2 and c.instruction >> 15 & 31 == 0:
            if saved_fcsr is None: saved_fcsr = next(iter(c.gpr_writes.values()))
        for address, data in c.memory_accesses:
            if data is None: continue
            dec = old.rvc.decode(c.instruction)
            if dec:
                require(dec['kind'] == 'write', 'Compressed writer role'); size = dec['size']
            elif c.instruction & 127 == 0x23:
                size = 1 << (c.instruction >> 12 & 7); require(size <= 8, 'Scalar store width')
            else:
                require(c.pc in mapped and mapped[c.pc][0] == 'store' and c.instruction & 127 == 0x27, 'Exact vector store owner')
                size = mapped[c.pc][1] // 8
                for b in range(size):
                    require(address + b not in stores, 'No duplicate vector-store byte')
                    stores[address + b] = data >> (8 * b) & 255
            for b in range(size): memory[address + b] = data >> (8 * b) & 255
    require(init_seen == [8, 16, 24] and len(writers) == 225 and len(stores) == 2400 and saved_fcsr is not None, 'Complete initialized writer/store population')
    def observed(address, size):
        require(all(address + b in memory for b in range(size)), 'Missing memory evidence')
        return bytes(memory[address + b] for b in range(size))
    guards = GUARD.to_bytes(8, 'little') * 2
    for p in range(75):
        w, phase = 16 << (p // 25), p % 25
        aa, bb, out, flags = images(w, phase)
        role, rm, _, _ = inputs(w, phase, 0)
        for name, image in (('matrix_a', aa), ('matrix_b', bb), ('matrix_dst', out)):
            require(observed(symbols[name] + p * 64, 64) == guards + image + guards, 'Every source/result/guard byte')
        ledger = [256 // w, 256 // w, 11 + (p // 25) * 8, 0, 0, (rm << 5) | flags]
        actual = [int.from_bytes(observed(symbols['matrix_ledger'] + p * 48 + i * 8, 8), 'little') for i in range(6)]
        require(actual == ledger, 'Exact RM/flags/VL/vtype/vstart/vcsr')
        for j, opname, reg, image in ((0, 'load_a', 8, aa), (1, 'load_b', 16, bb), (2, role, 24, out)):
            c = writers[3 * p + j]
            require(mapped[c.pc] == (opname, w) and c.vector_vl == 256 // w and c.vector_vstart == 0
                    and c.vector_writes == {reg: int.from_bytes(image, 'little')}, 'Full defined active result and untouched first-register tail')
        address = symbols['matrix_dst'] + p * 64 + 16
        require(bytes(stores[address + b] for b in range(32)) == out, 'Exact vector-store footprint')
    restore = [int.from_bytes(observed(symbols['matrix_fcsr_restore'] + 8 * i, 8), 'little') for i in range(2)]
    require(restore == [saved_fcsr, saved_fcsr], 'Actual initial/restored FCSR')
    require([int.from_bytes(observed(symbols[k] + offset, size), 'little') for k, offset, size in
        (('g75_result', 0, 4), ('g75_result', 4, 4), ('num_failed', 0, 4), ('matrix_checks', 0, 4), ('tohost', 0, 8))]
        == [2251, 0, 0, 2251, 1], 'Strict successful2251-check terminal')
    return dict(checks=2251, cases=75, FCLASS=30, DIV=30, SQRT=15, CSR_values=452,
        defined_vector_writer_bytes=7200, initialization_bytes=3072, result_store_bytes=2400,
        source_result_guard_bytes=14400, retirements=len(commits), no_skip=True)


def prepare(out):
    def save(path, result):
        if path.name == 'preflight.json':
            target_path, gold_path = out / 'dynamic-targets783.json', out / 'independent-gold.json'
            life.save(target_path, TARGETS)
            life.save(gold_path, [dict(width=w, phase=p, role=inputs(w, p, 0)[0], rm=inputs(w, p, 0)[1],
                input_a=images(w, p)[0].hex(), input_b=images(w, p)[1].hex(), result=images(w, p)[2].hex(),
                flags=images(w, p)[3]) for w in (16, 32, 64) for p in range(25)])
            result = dict(result, status='FINITE_FCLASS_DIVSQRT783_HOST_SPIKE_PASS_NOT_DUT',
                baseline=str(BASE), baseline_seal=BASE_SHA, population=783, target='Dynamic CLASS low10 and dense denormal fraction only',
                target_serialized_slots=TARGETS['target_missing_slots'], measured_gain=None, official_percentage=None,
                VCS_budget_plan_seconds=600, VCS_started=False, coverage_admitted=False,
                input_pins=life.merge_pins(result['input_pins'], {str(p): life.digest(p) for p in (target_path, gold_path)}))
        return life.save(path, result)
    proxy = SimpleNamespace(**vars(life)); proxy.save = save
    namespace = dict(base.prepare.__globals__, APP=APP, SYMBOLS=SYMBOLS, source_pins=source_pins,
                     linked=linked, validate=validate, life=proxy)
    return FunctionType(base.prepare.__code__, namespace)(out, None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(); cli.add_argument('--output', type=Path, required=True)
    out = cli.parse_args().output.resolve()
    try: prepare(out)
    except Exception as error:
        if out.exists(): life.save(out / 'failure.json', dict(error=str(error), VCS_started=False, no_retry=True))
        raise
