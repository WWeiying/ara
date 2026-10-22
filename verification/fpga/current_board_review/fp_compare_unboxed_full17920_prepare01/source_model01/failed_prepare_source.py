#!/usr/bin/env python3
"""Source/model only. No subprocess, compiler, reference or simulator invocation."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import time

HERE = Path(__file__).resolve().parent
G = HERE.parent
OLD = G / 'fp_compare_unboxed_prefix265_prepare01'
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_additions46/binaries/rvv_fp_compare_unboxed_unmasked_e16_mf4')
LENGTHS = (0, 1, 2, 3, 8, 15, 16)
EXPECTED = {
    'parent.c': '03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad',
    'scenario.S': '33abaa5c662a3780ac82ea631fec6909a035ccbb6b9d656896ce0cb356808bbe',
    'fixtures.h': '5664c1a4546bb402fe64ef190ca8e4910efa21fc35daea5229a187377eba7cb1',
    'operations.h': 'cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def classify(op, a, b):
    """Integer FP16 comparison, independent of fixture bit/flag table."""
    def nan(x):
        return (x & 0x7c00) == 0x7c00 and (x & 1023) != 0
    any_nan = nan(a) or nan(b)
    snan = (nan(a) and not (a & 512)) or (nan(b) and not (b & 512))
    equal = a == b or ((a & 32767) == 0 and (b & 32767) == 0)
    ka = a ^ (65535 if a & 32768 else 32768)
    kb = b ^ (65535 if b & 32768 else 32768)
    less = not equal and ka < kb
    value = op == 1 if any_nan else (
        equal, not equal, less, less or equal, not less and not equal, not less)[op]
    return [int(value), 16 * int(bool(snan if op < 2 else any_nan))]


def source_row(fixtures, inputs, seed, op, vl, mode, sticky):
    """Literal source oracle branches for the pinned defines, not packed masks."""
    a, b, allowed = [], [], []
    flags = sticky
    for i in range(16):
        ai = (i + seed + 7 * (seed // 16)) % 16
        bi = (i * 3 + seed * 5 + seed // 16) % 16 if op < 4 else seed % 16
        a.append(inputs[ai]); b.append(inputs[bi])
        wanted, nv = fixtures[op if op < 4 else op - 4][ai][bi if op < 4 else 14]
        old = (0x5b >> (i % 8)) & 1
        if i < vl:
            flags |= nv
            permitted = {wanted}
        elif 0 >= vl:
            permitted = {old}
        else:
            permitted = {old, 1, wanted}
        allowed.append(sorted(permitted))
    return dict(seed=seed, op=op, vl=vl, mode=mode, sticky=sticky, vstart=0,
                a=a, b=b, mask_byte=(255, 170, 36, 0)[mode], allowed=allowed,
                flags=flags, raw_scalar=b[0] if op >= 4 else None)


def original_errors(row, actual, status):
    errors = int((status & 0xffffffff) != 0)
    for i, allowed in enumerate(row['allowed']):
        errors += ((actual >> (8 + i)) & 1) not in allowed
    errors += (status >> 32) != row['flags']
    errors += ((actual & 255) != 91 or (actual >> 24) != 91)
    return errors


def packed_errors(row, record, actual, status):
    value = (actual >> 8) & 65535
    bad = (value & (record & 65535)) | ((~value & 65535) & ((record >> 16) & 65535))
    return (bad.bit_count() + int((status & 0xffffffff) != 0)
            + int((status >> 32) != row['flags'])
            + int((actual & 255) != 91 or (actual >> 24) != 91))


def elf_bytes(blob, address, length):
    require(blob[:6] == b'\x7fELF\x02\x01', 'ELF64 little endian')
    phoff = struct.unpack_from('<Q', blob, 32)[0]
    entsize, count = struct.unpack_from('<HH', blob, 54)
    for i in range(count):
        kind, _, off, va, _, filesz, _, _ = struct.unpack_from('<IIQQQQQQ', blob, phoff + i * entsize)
        if kind == 1 and va <= address and address + length <= va + filesz:
            return blob[off + address - va:off + address - va + length]
    raise ValueError('Unmapped original helper bytes')


def helper_proof():
    specs = [json.loads((OLD / backend / 'elf.json').read_text()) for backend in ('soc', 'spike')]
    blob = ARCHIVE.read_bytes()
    names = ['capacity'] + ['op_' + str(i) for i in range(10)]
    starts = [0x10540 + 64 * i for i in range(4)] + [0x10640 + 72 * i for i in range(6)]
    report = []
    for name in names:
        codes = [r['insn'] for r in specs[0]['functions'][name]]
        require(codes == [r['insn'] for r in specs[1]['functions'][name]], 'Old backend helper bytes')
        if name == 'capacity':
            require(codes == ['52fd', '00e2f557', '8082'], 'Actual capacity e16 mf4')
        else:
            pc = starts[int(name[3:])]
            for code in codes:
                raw = int(code, 16).to_bytes(len(code) // 2, 'little')
                require(elf_bytes(blob, pc, len(raw)) == raw, 'Original helper ' + name)
                pc += len(raw)
        report.append(dict(name=name, instructions=len(codes), codes=codes,
                           original_linux_start=None if name == 'capacity' else starts[int(name[3:])]))
    require(sum(x['instructions'] for x in report) == 185, '185 actual helper encodings')
    require([x['instructions'] for x in report] == [3] + [17] * 4 + [19] * 6, 'Helper lengths')
    # Capacity relocates; confirm its exact six bytes occur in the original ELF.
    capbytes = b''.join(int(c, 16).to_bytes(len(c) // 2, 'little') for c in report[0]['codes'])
    require(blob.count(capbytes) == 1, 'Unique original capacity bytes')
    return report


def port(source):
    def replace_once(old, new):
        nonlocal source
        require(source.count(old) == 1, 'Port boundary: ' + old[:70])
        source = source.replace(old, new)
    replace_once('static word a[1024],b[1024];', 'static word a[1024] __attribute__((aligned(8)));\nstatic word b[1024] __attribute__((aligned(8)));')
    replace_once('static uint8_t mask[128],output[130];', 'static uint8_t mask[128] __attribute__((aligned(8)));\nstatic uint8_t output[130] __attribute__((aligned(8)));\n#include "packed_core.h"\n#include "generated_tables.h"')
    start = source.index('static long syscall3(')
    end = source.index('static void text(', start)
    source = source[:start] + 'extern long replay_write(long,long,long,long);\n#define syscall3 replay_write\n' + source[end:]
    start = source.index('static unsigned bit(')
    end = source.index('void probe_main(', start)
    source = source[:start] + source[end:]
    replace_once('void probe_main(void)', 'int fp_compare_unboxed_e16_mf4_full17920_main(void)')
    replace_once('if(!cap || cap>1024){text("RVV_FP_COMPARE_CAPACITY_FAIL\\n");syscall3(94,2,0,0);for(;;){}}', 'if(cap!=16){text("RVV_FP_COMPARE_CAPACITY_FAIL\\n");return 2;}')
    replace_once('unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap},bytes=(cap+7)/8;', 'unsigned lengths[]={0,1,2,3,cap/2,cap-1,cap};')
    start = source.index('        for(unsigned i=0;i<128;++i)')
    end = source.index('        if(RESTART_COMPARISONS &&', start)
    source = source[:start] + '''        uint64_t record=oracle_records[(seed*10+op)*7+l];
        uint64_t maskword=(uint64_t)(mode==0 ? 255:mode==1 ? 0xaa:mode==2 ? 0x24:0)*UINT64_C(0x0101010101010101);
        ALL_16_SD(mask,maskword);
        fresh_inputs(a,b,input_periods[(record>>48)&255],input_periods[record>>56]);
        ALL_16_SD(output,UINT64_C(0x5b5b5b5b5b5b5b5b));
        SH_AT(output,128,0x5b5b);
''' + source[end:]
    start = source.index('        if((uint32_t)status)')
    end = source.index('        if(errors!=prior', start)
    source = source[:start] + '''        flags|=(unsigned)((record>>32)&255);
        errors+=packed_errors(result_and_guards(output),status,record,flags);
''' + source[end:]
    replace_once('    syscall3(94,errors ? 1:0,0,0);for(;;){}', '    return errors ? 1:0;')
    source = source[:source.index('__asm__(".global _start')]
    source = '''/* Full original source-derived port. Compile admission is separate. */
#if SEW != 16 || UNMASKED_COMPARISONS != 1 || UNBOXED_COMPARISONS != 1 || RESTART_COMPARISONS != 0 || DESTINATION_KIND != 0
#error Wrong original source configuration
#endif
''' + source
    return source


def main():
    began = time.monotonic()
    out = HERE / 'source_model01'
    require(not out.exists(), 'Fresh output required; no automatic retry/overwrite')
    inputs_to_pin = [HERE / 'prepare_source.py', HERE / 'packed_core.h', ARCHIVE,
                     OLD / 'software/original_rebuilt.elf', OLD / 'source_elf_proof.json',
                     G / 'fp_compare_unboxed_full17920_source_review01/REVIEW.md',
                     G / 'fp_compare_unboxed_full17920_source_review01/REVIEW.json']
    inputs_to_pin += [OLD / 'software/original' / n for n in EXPECTED]
    inputs_to_pin += [OLD / 'software' / n for n in ('runtime.c', 'startup.S', 'replay.ld')]
    inputs_to_pin += [OLD / backend / 'elf.json' for backend in ('soc', 'spike')]
    before = {str(p): sha(p) for p in inputs_to_pin}
    for name, digest in EXPECTED.items():
        require(before[str(OLD / 'software/original' / name)] == digest, 'Original identity ' + name)
    require(before[str(ARCHIVE)] == '404b2c0bb8f9224dc5e281ad1ef83faee238dec1989b26b36d7dbc12e4c3b152', 'Original ELF identity')
    require(before[str(ARCHIVE)] == before[str(OLD / 'software/original_rebuilt.elf')], 'Old byte-identical reconstruction')
    out.mkdir(); save(out / 'inputs_before.json', before)
    fixture_text = (OLD / 'software/original/fixtures.h').read_text()
    input_values = [int(x, 16) for x in re.findall(r'UINT64_C\((0x[0-9a-f]+)\)', fixture_text)]
    fixture_literal = fixture_text.split('expected[6][16][16]=', 1)[1].strip().rstrip(';')
    fixtures = ast.literal_eval(fixture_literal.replace('{', '[').replace('}', ']'))
    require(len(input_values) == 16 and len(fixtures) == 6, 'Original fixture dimensions')
    for op in range(6):
        for i in range(16):
            for j in range(16):
                require(classify(op, input_values[i], input_values[j]) == fixtures[op][i][j], 'Independent fixture classification')
    helpers = helper_proof()
    periods, records, rows = [], [], []
    for seed in range(32):
        for op in range(10):
            for vl in LENGTHS:
                row = source_row(fixtures, input_values, seed, op, vl, 0, 0)
                ids = []
                for words in (row['a'], row['b']):
                    packed = [sum(words[k+j] << (16*j) for j in range(4)) for k in range(0, 16, 4)]
                    if packed not in periods:
                        periods.append(packed)
                    ids.append(periods.index(packed))
                z = sum(1 << i for i, values in enumerate(row['allowed']) if values == [0])
                o = sum(1 << i for i, values in enumerate(row['allowed']) if values == [1])
                require(not z & o, 'Contradictory allow masks')
                record = z | (o << 16) | (row['flags'] << 32) | (vl << 40) | (ids[0] << 48) | (ids[1] << 56)
                records.append(record)
                for values, shift in ((row['a'], 48), (row['b'], 56)):
                    period = periods[(record >> shift) & 255]
                    decoded = [(period[i // 4] >> (16 * (i % 4))) & 65535 for i in range(16)]
                    require(decoded == values, 'Packed input word little-endian identity')
                require((record >> 40) & 255 == vl, 'Packed original VL')
                for mode in range(4):
                    for sticky in range(2):
                        current = source_row(fixtures, input_values, seed, op, vl, mode, sticky)
                        current.update(ordinal=len(rows)+1, record_index=len(records)-1)
                        require(current['flags'] == ((record >> 32) & 255) | sticky, 'Sticky fixture flags')
                        for i in range(16):
                            cmp = classify(op if op < 4 else op - 4, current['a'][i], current['b'][i] if op < 4 else 0x7e00)
                            old = (0x5b >> (i % 8)) & 1
                            independent = {cmp[0]} if i < vl else {old} if vl == 0 else {old, 1, cmp[0]}
                            require(set(current['allowed'][i]) == independent, 'Independent allowed set')
                            for bit in (0, 1):
                                packed_invalid = bool(((bit << i) & z) or (((1-bit) << i) & o))
                                require(packed_invalid == (bit not in independent), 'All bit possibilities/error weights')
                        # Both extreme legal tail selections; flags/guards/CSR all checked.
                        for choose in (min, max):
                            bits = sum(choose(a) << i for i, a in enumerate(current['allowed']))
                            actual = 91 | (bits << 8) | (91 << 24)
                            status = current['flags'] << 32
                            require(original_errors(current, actual, status) == packed_errors(current, record, actual, status) == 0, 'Full positive oracle')
                        rows.append(current)
    require(len(rows) == 17920 and len(records) == 2240 and len(periods) <= 48, 'Full shape')
    require(rows[-1]['seed'] == 31 and rows[-1]['op'] == 9 and rows[-1]['vl'] == 16 and rows[-1]['sticky'] == 1, 'Original endpoint')
    negatives = {}
    def negative(label, row, bits_xor=0, guards=(91, 91), status_xor=0, expected=1):
        rec = records[row['record_index']]
        bits = sum(min(a) << i for i, a in enumerate(row['allowed'])) ^ bits_xor
        actual = guards[0] | (bits << 8) | (guards[1] << 24)
        status = (row['flags'] << 32) ^ status_xor
        a, b = original_errors(row, actual, status), packed_errors(row, rec, actual, status)
        require(a == b == expected, 'Negative ' + label)
        negatives[label] = dict(source_errors=a, packed_errors=b, ordinal=row['ordinal'])
    vl0 = rows[0]
    active = next(r for r in rows if r['vl'] == 16)
    tail = next(r for r in rows if r['vl'] > 0 and any(i >= r['vl'] and a == [1] for i, a in enumerate(r['allowed'])))
    ti = next(i for i, a in enumerate(tail['allowed']) if i >= tail['vl'] and a == [1])
    negative('VL0_preserve', vl0, bits_xor=1)
    negative('active', active, bits_xor=1)
    negative('tail_disallowed_zero', tail, bits_xor=1 << ti)
    negative('guard0', active, guards=(90, 91))
    negative('guard3', active, guards=(91, 90))
    negative('both_guards_one_error', active, guards=(90, 90))
    negative('two_bits_two_errors', active, bits_xor=3, expected=2)
    negative('vstart', active, status_xor=1)
    nv = next(r for r in rows if r['flags'] & 16)
    negative('missing_NV', nv, status_xor=16 << 32)
    negative('VL0_spurious_NV', vl0, status_xor=16 << 32)
    sticky = next(r for r in rows if r['sticky'] == 1)
    negative('missing_sticky', sticky, status_xor=1 << 32)
    # Model the original short circuit: only failing calls increment details.
    detail_count, printed = 0, []
    for ordinal, error in enumerate([0, 1] * 21, 1):
        if error:
            old_detail = detail_count; detail_count += 1
            if old_detail < 20:
                printed.append(ordinal)
    require(detail_count == 21 and printed == list(range(2, 41, 2)), 'Original details20/21')
    raw_by_seed = [next(r['raw_scalar'] for r in rows if r['seed'] == seed and r['op'] == 4) for seed in range(32)]
    require([i for i, v in enumerate(raw_by_seed) if v == 0] == [0, 16], 'Raw scalar zero seeds')
    require(all(v < 65536 for v in raw_by_seed), 'Raw fmv.d.x upper48 zero, not NaN boxed')
    scalar_negatives = []
    for seed, value in enumerate(raw_by_seed):
        if value:
            require(value != 0 and value != (value | 0xffffffffffff0000), 'Nonzero raw seed counterexample')
            scalar_negatives.append(dict(seed=seed, required=value, wrong_zero=0,
                                         wrong_boxed=value | 0xffffffffffff0000))
    fresh = {name: [byte for off, width in writes for byte in range(off, off+width)] for name, writes in {
        'a': [(x, 8) for x in range(0, 32, 8)], 'b': [(x, 8) for x in range(0, 32, 8)],
        'mask': [(x, 8) for x in range(0, 128, 8)], 'output': [(x, 8) for x in range(0, 128, 8)] + [(128, 2)]}.items()}
    for name, size in (('a', 32), ('b', 32), ('mask', 128), ('output', 130)):
        require(fresh[name] == list(range(size)), 'Exact fresh scalar coverage ' + name)
    sw = out / 'software'; sw.mkdir(); original = sw / 'original'; original.mkdir()
    for name in EXPECTED:
        shutil.copyfile(OLD / 'software/original' / name, original / name)
    for name in ('runtime.c', 'startup.S', 'replay.ld'):
        shutil.copyfile(OLD / 'software' / name, sw / name)
    shutil.copyfile(HERE / 'packed_core.h', sw / 'packed_core.h')
    source = (original / 'parent.c').read_text()
    candidate = port(source)
    (sw / 'case.c').write_text(candidate)
    (sw / 'source.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True), fromfile='original/parent.c', tofile='candidate/case.c')))
    header = ['/* Generated solely from pinned original fixtures; no chosen tail outcome. */', '#include <stdint.h>', 'static const uint64_t input_periods[][4] __attribute__((aligned(8))) = {']
    header += ['    {' + ','.join('UINT64_C(0x%016x)' % x for x in r) + '},' for r in periods]
    header += ['};', 'static const uint64_t oracle_records[2240] __attribute__((aligned(8))) = {']
    header += ['    UINT64_C(0x%016x),' % r for r in records]
    header += ['};', '']
    (sw / 'generated_tables.h').write_text('\n'.join(header))
    name = 'fp_compare_unboxed_e16_mf4_full17920'
    (sw / 'main.c').write_text('extern void replay_text(const char *);\nextern int ' + name + '_main(void);\nint main(void) {\n unsigned long vb; __asm__ volatile("csrr %0,vlenb":"=r"(vb));\n if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n replay_text("BOARD_CASE_BEGIN ' + name + '\\n");\n if(' + name + '_main()){replay_text("BOARD_CASE_FAIL ' + name + '\\n");return 1;}\n replay_text("BOARD_CASE_PASS ' + name + '\\nBOARD_REPLAY_PASS\\n");return 0;\n}\n')
    # No compile invocation: this is a proposed command configuration, not its result.
    save(out / 'compile_proposal.json', dict(status='NOT_AUTHORIZED_NOT_RUN', note='Proposed configuration only; no compiler invoked', exact_defines=dict(SEW=16, UNMASKED_COMPARISONS=1, UNBOXED_COMPARISONS=1, RESTART_COMPARISONS=0, DESTINATION_KIND=0), isa='rv64gcv_zfh_zvfh_zvl1024b', required_flags=['-Os', '-mabi=lp64d', '-ffreestanding', '-fno-builtin', '-fno-tree-vectorize', '-fno-tree-slp-vectorize'], backends=['soc', 'spike'], gate='Independent source/model review, then explicit dualcompile/CFG authorization'))
    save(out / 'model.json', dict(scope='SOURCE_MODEL_ONLY_NOT_REFERENCE_OR_DUT', rows=rows))
    save(out / 'helper_identity.json', dict(original_elf=str(ARCHIVE), original_sha256=sha(ARCHIVE), prior_actual_helpers=helpers, new_elf='NOT_COMPILED', copied_s_sha256=sha(original/'scenario.S')))
    save(out / 'model_checks.json', dict(status='PASS_PYTHON_SOURCE_MODEL_NOT_C_HOST', fixture_pairs=1536, complete_calls=17920,
         bit_membership_checks=17920*16*2, extreme_positive_calls=17920*2, targeted_negatives=negatives,
         details=dict(failing_calls=21, printed=printed, suppressed_failure_ordinal=42), raw_scalar_by_seed=raw_by_seed,
         raw_scalar_counterexamples=scalar_negatives,
         fresh_offsets=fresh, original_upper_input_BSS_bytes_per_array=2016))
    after = {str(p): sha(p) for p in inputs_to_pin}
    require(before == after, 'Input drift')
    save(out / 'inputs_after.json', after)
    report = dict(status='SOURCE_MODEL_PREPARED_PENDING_INDEPENDENT_REVIEW_NOT_COMPILED', calls=17920,
                  result_bits=286720, guards=35840, flags=17920, vstarts=17920, capacity=16, vtype=14,
                  vf_calls=10752, vv_calls=7168, vl0_calls=2560, dynamic_helper_instructions=326144,
                  capacity_instructions=3, static_helper_encodings=185, fresh_stores_per_call=41,
                  fresh_scalar_stores=734720, input_periods=len(periods), input_ROM_bytes=len(periods)*32,
                  records=len(records), oracle_ROM_bytes=len(records)*8, new_elf=None, compile=False,
                  reference=False, DUT=False, inputs_unchanged=True, model_elapsed_s=time.monotonic()-began)
    save(out / 'report.json', report)
    save(out / 'artifact_pins.json', {str(p): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps(report))


if __name__ == '__main__':
    main()
