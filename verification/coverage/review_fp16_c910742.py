"""Independent existing FP16 RTZ divide evidence for eight additional C910 arithmetic scopes."""
import argparse
import bisect
import csv
from fractions import Fraction
import json
from pathlib import Path
import re

from elftools.elf.elffile import ELFFile
import c910_srt_datapath_native as previous
import targeted_toggle_evidence_v2 as t
from review_dwc_internal_error742 import BASE, BASE_SHA, BUILD, DB

life, require = previous.life, previous.require
ROOT, OUT = life.ROOT, life.OUT
RUN = OUT / 'repaired-aligned-600-20260930-01/results/c0279-extra-rvv-vfdiv-46c98dbd428e'
CASE = RUN / 'tests/rvv_vfdiv'
ELF_SHA = 'de0b74076f105ab79cb3a66b2624f9bfc102043e47f080fdbb77d94eb89e6e84'
REFERENCE = OUT / 'c910-srt-native1264-recovery-agent-20261007-01'
REFERENCE_SHA = '5fa9180cf70f658fbf355e7510a8d9c99af0240f6be22084139791f47fddbf38'
SOURCE = ROOT / 'apps/riscv-tests/isa/rv64uv/vfdiv.c'
PCS = [0x8000023e, 0x80000acc, 0x80001254, 0x800019aa]


def half_value(word):
    exponent, mantissa = (word >> 10) & 31, word & 1023
    require(exponent != 31, 'Nonfinite input outside reviewed contract')
    value = Fraction(mantissa + (1024 if exponent else 0), 1024) * Fraction(2) ** (exponent - 15 if exponent else -14)
    return -value if word & 0x8000 else value


POSITIVE_HALF = [half_value(w) for w in range(0x7c00)]


def div_rtz(a, b):
    require(half_value(b) != 0, 'Zero divisor outside reviewed contract')
    quotient = half_value(a) / half_value(b)
    require(abs(quotient) <= POSITIVE_HALF[-1], 'Overflow outside reviewed contract')
    magnitude = bisect.bisect_right(POSITIVE_HALF, abs(quotient)) - 1
    return magnitude | ((a ^ b) & 0x8000)


def patterns(source):
    result = []
    for number in range(1, 5):
        body = source.split('void TEST_CASE%d(void) {' % number, 1)[1].split('};', 1)[0]
        def args(pattern):
            m = re.search(pattern, body, re.S)
            require(m is not None, 'Missing exact FP16 operand/reference')
            return [int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', m.group(1))]
        a = args(r'VLOAD_16\(v2,(.*?)\);')
        b = args(r'VLOAD_16\(v3,(.*?)\);') if number <= 2 else args(r'BOX_HALF_IN_DOUBLE\(dscalar_16,(.*?)\);') * 16
        gold = args(r'VCMP_U16\(\d+, v1,(.*?)\);')
        require(len(a) == len(b) == len(gold) == 16, 'Not exact16 half elements')
        expected = [div_rtz(x, y) if number % 2 or i % 2 else 0 for i, (x, y) in enumerate(zip(a, b))]
        require(expected == gold, 'Independent RTZ oracle differs from reference')
        result.append(dict(case=number, a=a, b=b, expected=expected, masked=number % 2 == 0))
    return result


def shuffle_map(text):
    body = text.split('      4: unique case (ew)', 1)[1].split('rvv_pkg::EW16: begin', 1)[1].split('end', 1)[0]
    mapping = {int(a): int(b) for a, b in re.findall(r'idx\[(\d+)\]\s*=\s*(\d+)', body)}
    require(set(mapping) == set(mapping.values()) == set(range(32)), 'Not exact frozen EW16 shuffle')
    result = []
    for element in range(16):
        lo, hi = mapping[2 * element], mapping[2 * element + 1]
        require(hi == lo + 1 and lo % 2 == 0, 'Broken halfword lane mapping')
        result.append(dict(element=element, lane=lo // 8, subslot=(lo % 8) // 2))
    require({(r['lane'], r['subslot']) for r in result} == {(l, s) for l in range(4) for s in range(4)},
            'First16 do not exercise all physical/simd lanes')
    return result


def load_segments(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        require(elf['e_machine'] == 'EM_RISCV', 'Not RISC-V ELF')
        return [(s['p_vaddr'], s.data()) for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']


def trace_evidence(rows, segments, cases):
    retired = [r for r in rows if r['event'] == 'retire']
    require(retired and all(r['trap'] == '0' for r in retired), 'Trap in existing FP16 trace')
    regs = [0] * 32; frm = None; vl = vtype = None
    arithmetic, stores = [], []
    for index, row in enumerate(retired):
        pc, insn = int(row['pc'], 16), int(row['insn'], 16)
        width = 4 if insn & 3 == 3 else 2
        contents = [data[pc - address:pc - address + width] for address, data in segments
                    if address <= pc and pc + width <= address + len(data)]
        require(len(contents) == 1 and int.from_bytes(contents[0], 'little') == insn,
                'Retired instruction not bound to actual ELF')
        if insn & 127 == 0x73 and (insn >> 20) == 2:
            require((insn >> 12) & 7 == 1, 'Unreviewed frm access')
            frm = regs[(insn >> 15) & 31]
        if insn & 127 == 0x57 and (insn >> 12) & 7 == 7:
            vtype = (insn >> 20) & 0x7ff; vl = int(row['rd_wdata'], 16)
        if pc in PCS:
            require(frm == 1 and vl == 16 and ((vtype >> 3) & 7) == 1 and (vtype & 7) in (0, 2),
                    'Not actual RTZ/VL16/SEW16')
            require(insn in (0x822190d7, 0x802190d7, 0x8227d0d7, 0x8027d0d7), 'Wrong FP16 arithmetic instruction')
            arithmetic.append(dict(pc=hex(pc), instruction=hex(insn), order=int(row['order']),
                                   cycle=int(row['cycle']), row_index=index, frm=frm, vl=vl, vtype=vtype))
        if insn & 127 == 0x27 and (insn >> 12) & 7 == 5 and (insn >> 7) & 31 == 1:
            stores.append(dict(row_index=index, pc=hex(pc), address=regs[(insn >> 15) & 31], vl=vl, vtype=vtype))
        rd = int(row['rd'])
        if rd: regs[rd] = int(row['rd_wdata'], 16)
    require([int(r['pc'], 16) for r in arithmetic] == PCS, 'Missing/duplicate/reordered FP16 arithmetic')
    result = []
    for a, case in zip(arithmetic, cases):
        following = next((s for s in stores if s['row_index'] > a['row_index']), None)
        require(following and following['vl'] == 16, 'Missing full FP16 result store')
        address = following['address']; seen = {}
        for row in retired[following['row_index'] + 1:]:
            insn = int(row['insn'], 16)
            # Stop at the next architectural vector configuration, never borrow later output.
            if insn & 127 == 0x57 and (insn >> 12) & 7 == 7: break
            mem = int(row['mem_addr'], 16)
            if address <= mem < address + 32 and insn & 127 == 3 and (insn >> 12) & 7 == 5:
                require(mem % 2 == 0 and mem not in seen, 'Duplicate/unaligned readback')
                require(int(row['mem_rmask'], 16) == (3 << (mem % 8)), 'Incomplete halfword observation')
                seen[mem] = dict(pc=row['pc'], cycle=int(row['cycle']), value=int(row['rd_wdata'], 16))
        require(set(seen) == set(range(address, address + 32, 2)), 'Missing complete FP16 readback')
        actual = [seen[address + 2 * i]['value'] for i in range(16)]
        require(actual == case['expected'], 'Actual FP16 readback differs from independent oracle')
        result.append(dict(**a, destination_store=following, observed_halfwords=actual,
                           readback=[seen[address + 2 * i] for i in range(16)], independently_compared_bytes=32))
    return dict(retired_instruction_ELF_checks=len(retired), actual_fp16_requests=result,
                observed_halfwords=64, independently_compared_bytes=128, skipped_unknown=0,
                whole_ISA=False, native_vector_trace=False, fflags_verified=False)


def collect():
    old = life.read_bound(previous.REVIEW, previous.REVIEW_SHA)
    reference = life.read_bound(REFERENCE / 'capture-result.json', REFERENCE_SHA)
    life.check(reference['pins'])
    require(reference['objects'] == 1264 and reference['semantic_reload'] and reference['finalreset'],
            'Prior native1264 not qualified')
    config = json.loads((REFERENCE / 'config.json').read_bytes())
    require(len(config['instances']) == 8, 'Prior eight-instance map differs')
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SHA)
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    vdb = CASE / 'work/code.vdb'
    require(len(ledger) == len(set(ledger)) == 743 and ledger.count(str(vdb)) == 1, 'C0279 not exact742 member')
    inputs = json.loads((CASE / 'inputs.json').read_bytes())
    require(life.digest(CASE / 'input.elf') == inputs['binary']['sha256'] == ELF_SHA,
            'Actual ELF drift')
    command = json.loads((CASE / 'command.json').read_bytes())['command']
    require(command[0] == inputs['simv']['path'] and '+PRELOAD=' + str(CASE / 'input.elf') in command,
            'Original image/ELF command differs')
    life.check(inputs['simv']['image_sha256'])
    cases = patterns(SOURCE.read_text())
    segments = load_segments(CASE / 'input.elf')
    for case in cases:
        for values in ([case['a'], case['b']] if case['case'] <= 2 else [case['a']]):
            packed = b''.join(x.to_bytes(2, 'little') for x in values)
            require(any(packed in data for _, data in segments), 'Source operand table absent from actual ELF')
    with (CASE / 'commit_trace.csv').open() as stream: rows = list(csv.DictReader(stream))
    actual = trace_evidence(rows, segments, cases)
    mapping = shuffle_map((ROOT / 'hardware/include/ara_pkg.sv').read_text())
    added = []
    for i in config['instances']:
        if i['simd_subslot'] != 0: continue
        for slot in (2, 3):
            scope = i['scope'].replace('.gen_num_lanes[0].active_lane', '.gen_num_lanes[%d].active_lane' % slot)
            added.append(dict(i, scope=scope, simd_subslot=slot))
    scopes = [i['scope'] for i in added]
    shape_paths = [DB / 'design/verilog.design.xml', DB / 'shape/tgl.verilog.info.xml', DB / 'shape/tgl.verilog.shape.xml']
    checksums, definitions = t.definitions(*(t.xml(p) for p in shape_paths), scopes)
    for i in added:
        require(checksums[i['scope']] == old['toggle_checksum'], 'Additional Toggle checksum differs')
        require(definitions[i['scope']]['shape'] == definitions[scopes[0]]['shape'], 'Additional compiled shape differs')
    pins = {str(previous.REVIEW): previous.REVIEW_SHA, str(REFERENCE / 'capture-result.json'): REFERENCE_SHA,
            str(BASE / 'admission-manifest.json'): BASE_SHA, str(BASE / 'combined-inputs.txt'): manifest['output_pins'][str(BASE / 'combined-inputs.txt')]}
    pins = life.merge_pins(pins, reference['pins'])
    pins = life.merge_pins(pins, inputs['simv']['image_sha256'])
    build = json.loads((BUILD / 'build-source-pins.json').read_bytes())
    sources = [old['source']['path'], 'hardware/deps/fpnew/src/fpnew_pkg.sv',
               'hardware/deps/fpnew/src/fpnew_opgroup_multifmt_slice.sv',
               'hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv', 'hardware/include/ara_pkg.sv']
    for relative in sources:
        p = ROOT / relative
        require(life.digest(p) == build[str(p)], 'Frozen source chain drift')
        pins = life.merge_pins(pins, {str(p): build[str(p)]})
    for p in [SOURCE, CASE / 'input.elf', CASE / 'inputs.json', CASE / 'command.json', CASE / 'commit_trace.csv',
              RUN / 'independent_audit.json', RUN / 'summary.json', BUILD / 'build-source-pins.json',
              *shape_paths, Path(__file__).resolve(), Path(__file__).with_name('test_review_fp16_c910742.py')]:
        pins = life.merge_pins(pins, {str(p): life.digest(p)})
    for p in vdb.rglob('*'):
        if p.is_file(): pins = life.merge_pins(pins, {str(p): life.digest(p)})
    life.check(pins)
    return dict(status='FP16_C910_ADDITIONAL8_SOURCE_AND_OBSERVED_RTZ_DIV_PASS_NATIVE_PENDING', baseline=742,
        prior_native_seal=REFERENCE_SHA, actual_ELF_sha256=ELF_SHA, original_command=command,
        oracle='Exact Fraction quotient, finite binary16 RTZ floor; no DUT-derived golden',
        actual_evidence=actual, source_patterns=cases, lane_subslot_mapping=mapping,
        instances=added, target_signal_objects=1264, logical_target_bits=77472,
        two_direction_capacity=154944, protected_objects=416, protects=old['scope_limits']['protected_outside'],
        source_chain=['VL16/SEW16 retired vfdiv -> four physical lanes shuffled from actual ara_pkg EW16 table',
            'get_lane_formats: width/fp_width > subslot; e16 supplies subslots2/3',
            'multifmt local_operands = operands >> LANE*fp_width; THMULTI maps FP16 to0010',
            'unchanged C910 radix16 internal arithmetic158; all52 local non-target objects retained'],
        scope_limit='Finite RTZ FP16 DIV integration reuse only; not FP16 sqrt, all rounding/specials, fullISA or fflags proof',
        native_qualified=False, EDA_launched=False, RTL_modified=False, exclusions_applied=False, pins=pins)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True, type=Path)
    a = p.parse_args(); require(not a.output.exists(), 'Fresh review required')
    result = collect(); life.save(a.output, result)
    print(json.dumps(dict(output=str(a.output), seal=life.digest(a.output), targets=1264,
                         halfwords=result['actual_evidence']['observed_halfwords'], native='PENDING')))
