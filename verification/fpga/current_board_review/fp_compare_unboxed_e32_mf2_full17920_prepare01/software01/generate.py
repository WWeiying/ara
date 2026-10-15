#!/usr/bin/env python3
"""One exclusive FP32 source port; no compiler/reference/simulator invocation."""
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
G = ROOT.parent
BASE = G / 'fp_compare_unboxed_full17920_prepare01'
OLD = G / 'fp_compare_unboxed_prefix265_prepare01'
NAME = 'fp_compare_unboxed_e32_mf2_full17920'
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_compare_oracle.c')
BINDINGS_SHA = '1245adb28fe0c6042837573950b2c1261fb130507497932010814c4f0267bfff'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, obj):
    with path.open('x') as f:
        json.dump(obj, f, indent=2)
        f.write('\n')


def text(path, value):
    with path.open('x') as f:
        f.write(value)


def replace_once(value, old, new):
    require(value.count(old) == 1, 'Unique source boundary: ' + old[:80])
    return value.replace(old, new)


def load_base():
    spec = importlib.util.spec_from_file_location('sealed_e16_source', BASE / 'prepare_source.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pack_period(values, sew):
    require(sew == 32 and len(values) == 16, 'Only reviewed FP32 CAP16 profile')
    require(all(0 <= x < 1 << sew for x in values), 'Unsigned FP32 bit patterns')
    return [values[i] | (values[i + 1] << sew) for i in range(0, 16, 2)]


def unpack_period(words, sew):
    return [(words[i // 2] >> (sew * (i % 2))) & ((1 << sew) - 1) for i in range(16)]


def source_port(base, original):
    # The original C and all width-independent substitutions are already pinned.
    result = base.port(original)
    result = replace_once(result, 'SEW != 16', 'SEW != 32')
    result = replace_once(result, 'fp_compare_unboxed_e16_mf4_full17920_main', NAME + '_main')
    return result


def packed_core():
    result = (BASE / 'packed_core.h').read_text()
    anchor = '    SD_AT(a, 24, ar[3]); SD_AT(b, 24, br[3]);\n'
    extra = ''.join('    SD_AT(a, %d, ar[%d]); SD_AT(b, %d, br[%d]);\n' % (8*i, i, 8*i, i)
                    for i in range(4, 8))
    return replace_once(result, anchor, anchor + extra)


def helpers(base, bindings):
    blob = Path(bindings['parent']['original_elf']).read_bytes()
    old = json.loads((OLD / 'soc/elf.json').read_text())['functions']
    bound = bindings['original_helper_binding']
    result, joined = [], bytearray()
    next_pc = 0x10532
    for name in ['capacity'] + ['op_' + str(i) for i in range(10)]:
        proof = bound['helpers'][name]
        pc = int(proof['original_pc'], 16)
        require(pc == next_pc, 'Continuous original helper source order')
        raw = base.elf_bytes(blob, pc, proof['bytes'])
        require(hashlib.sha256(raw).hexdigest() == proof['sha256'], 'Exact original helper ' + name)
        codes, pos = [], 0
        for row in old[name]:
            width = len(row['insn']) // 2
            codes.append(raw[pos:pos + width][::-1].hex())
            pos += width
        require(pos == len(raw) and len(codes) == proof['instructions'], 'Complete instruction partition')
        result.append(dict(name=name, original_linux_start=pc, instructions=len(codes), codes=codes,
                           sha256=proof['sha256']))
        joined.extend(raw)
        next_pc += len(raw)
    require(next_pc == 0x107ea and len(joined) == 696, 'Original 696B helper extent')
    require(sum(r['instructions'] for r in result) == 185, '185 original static instructions')
    require(hashlib.sha256(joined).hexdigest() == bound['concatenation_sha256'], 'Whole helper identity')
    require(blob.count(joined) == 1, 'Unique original helper block, not arbitrary bytes')
    return result


def main():
    binding_path = ROOT / 'INPUT_BINDINGS.json'
    require(sha(binding_path) == BINDINGS_SHA, 'Reviewed binding identity')
    bindings = json.loads(binding_path.read_text())
    pins = dict(bindings['input_pins'])
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Pinned source drift: ' + path)
    review = ROOT / 'source_review01/review.json'
    approved = json.loads(review.read_text())
    require(approved['status'] == 'SOURCE_GENERATOR_NO_BLOCKER', 'Exact source review required')
    require(approved['generator_sha256'] == sha(Path(__file__)), 'Review binds actual generator')
    extra = [binding_path, Path(__file__), review, ROOT / 'static_review01/review.json']
    extra += [OLD / 'software' / n for n in ('runtime.c', 'startup.S', 'replay.ld')]
    pins.update({str(p): sha(p) for p in extra})
    out = HERE / 'generated01'
    out.mkdir()  # Exclusive: any prior attempt, including failure, must remain.
    save(out / 'inputs_before.json', pins)
    base = load_base()
    config = json.loads((ROOT / 'shape.json').read_text())
    sew = config['defines']['SEW']
    require(sew == 32 and config['capacity'] == 16 and config['vtype'] == 23, 'Actual reviewed shape')
    archive = Path(bindings['parent']['assembly']).parent
    fixture = (archive / 'e32/fixtures.h').read_text()
    values = [int(x, 16) for x in re.findall(r'UINT64_C\((0x[0-9a-f]+)\)', fixture)]
    literal = fixture.split('expected[6][16][16]=', 1)[1].strip().rstrip(';')
    table = ast.literal_eval(literal.replace('{', '[').replace('}', ']'))
    require(len(values) == 16 and len(table) == 6, 'Original fixture geometry')
    helper_rows = helpers(base, bindings)
    periods, records, rows = [], [], []
    for seed in range(32):
        for op in range(10):
            for vl in config['lengths']:
                row = base.source_row(table, values, seed, op, vl, 0, 0)
                ids = []
                for bank in ('a', 'b'):
                    words = pack_period(row[bank], sew)
                    require(unpack_period(words, sew) == row[bank], 'Lossless uint32 packing')
                    if words not in periods:
                        periods.append(words)
                    ids.append(periods.index(words))
                z = sum(1 << i for i, permitted in enumerate(row['allowed']) if permitted == [0])
                o = sum(1 << i for i, permitted in enumerate(row['allowed']) if permitted == [1])
                require(not z & o and max(ids) < 256, 'Record representability')
                record = z | (o << 16) | (row['flags'] << 32) | (vl << 40) | (ids[0] << 48) | (ids[1] << 56)
                records.append(record)
                for mode in range(4):
                    for sticky in range(2):
                        current = base.source_row(table, values, seed, op, vl, mode, sticky)
                        current.update(ordinal=len(rows) + 1, record_index=len(records) - 1)
                        require(current['flags'] == (((record >> 32) & 255) | sticky), 'Sticky record bits')
                        rows.append(current)
    require(len(rows) == 17920 and len(records) == 2240 and len(periods) == 48, 'Complete original geometry')
    require(rows[-1]['seed'] == 31 and rows[-1]['op'] == 9 and rows[-1]['sticky'] == 1, 'Original endpoint')
    sw = out / 'software'
    original = sw / 'original'
    original.mkdir(parents=True)
    sources = {'parent.c': SOURCE, 'scenario.S': Path(bindings['parent']['assembly']),
               'fixtures.h': archive / 'e32/fixtures.h', 'operations.h': archive / 'e32/operations.h'}
    for name, path in sources.items():
        shutil.copyfile(path, original / name)
    for name in ('runtime.c', 'startup.S', 'replay.ld'):
        shutil.copyfile(OLD / 'software' / name, sw / name)
    source = SOURCE.read_text()
    candidate = source_port(base, source)
    text(sw / 'case.c', candidate)
    text(sw / 'packed_core.h', packed_core())
    text(sw / 'source.diff', ''.join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True),
                                                        fromfile='original/parent.c', tofile='candidate/case.c')))
    header = ['/* Pinned original FP32 bit patterns and allowed sets; no selected tail outcome. */',
              '#include <stdint.h>', 'static const uint64_t input_periods[][8] __attribute__((aligned(8))) = {']
    header += ['    {' + ','.join('UINT64_C(0x%016x)' % v for v in p) + '},' for p in periods]
    header += ['};', 'static const uint64_t oracle_records[2240] __attribute__((aligned(8))) = {']
    header += ['    UINT64_C(0x%016x),' % v for v in records]
    text(sw / 'generated_tables.h', '\n'.join(header + ['};', '']))
    text(sw / 'main.c', 'extern void replay_text(const char *);\nextern int ' + NAME + '_main(void);\n'
         'int main(void) {\n unsigned long vb; __asm__ volatile("csrr %0,vlenb":"=r"(vb));\n'
         ' if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
         ' replay_text("BOARD_CASE_BEGIN ' + NAME + '\\n");\n'
         ' if(' + NAME + '_main()){replay_text("BOARD_CASE_FAIL ' + NAME + '\\n");return 1;}\n'
         ' replay_text("BOARD_CASE_PASS ' + NAME + '\\nBOARD_REPLAY_PASS\\n");return 0;\n}\n')
    save(out / 'model.json', dict(scope='GENERATED_SOURCE_MODEL_NOT_INDEPENDENT_NUMERICAL_ACCEPTANCE', rows=rows))
    save(out / 'helper_identity.json', dict(original_elf=bindings['parent']['original_elf'],
         original_sha256=bindings['parent']['sha256'], helpers=helper_rows, new_elf='NOT_COMPILED'))
    save(out / 'generation.json', dict(status='GENERATED_PENDING_INDEPENDENT_ORIGINAL_C_HOST',
         defines=config['defines'], source_calls=len(rows), periods=len(periods), records=len(records),
         input_ROM_bytes=3072, oracle_ROM_bytes=17920, fresh_stores_per_call=49,
         input_LD_per_call=16, output_LWU_per_call=1, untouched_input_BSS_bytes_per_bank=4032,
         reference=False, DUT=False, original_Linux_recompiled=False))
    require(all(sha(Path(p)) == digest for p, digest in pins.items()), 'Inputs changed during generation')
    save(out / 'inputs_after.json', pins)
    save(out / 'artifact_pins.json', {str(p): sha(p) for p in sorted(out.rglob('*')) if p.is_file()})
    print(json.dumps({'status': 'GENERATED_PENDING_INDEPENDENT_ORIGINAL_C_HOST', 'out': str(out)}), flush=True)


if __name__ == '__main__':
    main()
