"""Single masked source successor; source/model generation, never ISA execution."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
G = HERE.parent
OLD = G / 'fp_compare_unboxed_full17920_prepare01'
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01')
PARENT = ARCHIVE / 'rvv_additions46/binaries/rvv_fp_compare_unboxed_e16_mf4'
ASSEMBLY = ARCHIVE / 'rvv_fp_comparisons_unboxed_v24_01/rvv_fp_compare_unboxed_e16_mf4.S'
NAME = 'fp_compare_unboxed_masked_e16_mf4_full17920'
spec = importlib.util.spec_from_file_location('immutable_unmasked_source_methods', OLD/'prepare_source.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def replace(text, before, after):
    assert text.count(before) == 1, before[:90]
    return text.replace(before, after)


def row(fixtures, inputs, seed, op, vl, mode, sticky):
    result = old.source_row(fixtures, inputs, seed, op, vl, mode, sticky)
    allowed = []
    flags = sticky
    maskbyte = (255, 170, 36, 0)[mode]
    for i in range(16):
        ai = (i+seed+7*(seed//16)) % 16
        bi = (3*i+5*seed+seed//16) % 16 if op < 4 else 14
        wanted, nv = fixtures[op if op < 4 else op-4][ai][bi]
        previous = (91 >> (i % 8)) & 1
        if i < vl and (maskbyte >> (i % 8)) & 1:
            values = {wanted}
            flags |= nv
        elif vl == 0 or i < vl:
            values = {previous}
        else:
            values = {previous, 1, wanted}
        allowed.append(sorted(values))
    result.update(allowed=allowed, flags=flags)
    return result


def main():
    out = HERE / 'source'
    assert not out.exists(), 'One source generation, no overwrite/retry'
    original = OLD / 'source_model02/software/original'
    files = [Path(__file__), OLD/'prepare_source.py', OLD/'packed_core.h',
        PARENT, ASSEMBLY, G/'fp_comparison_original/provenance01/parents.json']
    files += list(original.iterdir())
    pins = {str(p): sha(p) for p in files if p.is_file()}
    assert sha(PARENT) == '82d90319cdef6cad35167ab9e5e2cccc86b90103c172b88f20b5537c23609a79'
    assert sha(original/'parent.c') == '03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad'
    text = (original/'fixtures.h').read_text()
    inputs = [int(v,16) for v in re.findall(r'UINT64_C\((0x[0-9a-f]+)\)',text)]
    fixtures = ast.literal_eval(text.split('expected[6][16][16]=')[1].strip().rstrip(';').replace('{','[').replace('}',']'))
    for op in range(6):
        for i in range(16):
            for j in range(16):
                assert old.classify(op, inputs[i], inputs[j]) == fixtures[op][i][j]
    blob = PARENT.read_bytes()
    helpers = json.loads((OLD/'source_model02/helper_identity.json').read_text())['prior_actual_helpers']
    for helper in helpers:
        codes = helper['codes'][:]
        if helper['name'] != 'capacity':
            i = int(helper['name'][3:]); target = 8 if i < 4 else 10
            codes[target] = f'{int(codes[target],16) ^ (1<<25):08x}'
            address = ([0x1054a+64*j for j in range(4)]+[0x1064a+72*j for j in range(6)])[i]
        else:
            address = 0x10542
        data = b''.join(int(c,16).to_bytes(len(c)//2,'little') for c in codes)
        assert old.elf_bytes(blob, address, len(data)) == data
        helper.update(codes=codes, original_linux_start=address)
    periods, records, rows = [], [], []
    for seed in range(32):
        for op in range(10):
            for vl in old.LENGTHS:
                for mode in range(4):
                    g = row(fixtures, inputs, seed, op, vl, mode, 0)
                    ids = []
                    for values in (g['a'],g['b']):
                        words = [sum(values[k+j] << (16*j) for j in range(4)) for k in range(0,16,4)]
                        if words not in periods:
                            periods.append(words)
                        ids.append(periods.index(words))
                    z = sum(1<<i for i,v in enumerate(g['allowed']) if v == [0])
                    o = sum(1<<i for i,v in enumerate(g['allowed']) if v == [1])
                    rec = z | (o<<16) | (g['flags']<<32) | (vl<<40) | (ids[0]<<48) | (ids[1]<<56)
                    records.append(rec)
                    for sticky in range(2):
                        current = row(fixtures, inputs, seed, op, vl, mode, sticky)
                        current.update(ordinal=len(rows)+1, record_index=len(records)-1)
                        assert current['flags'] == g['flags'] | sticky
                        for i, permitted in enumerate(current['allowed']):
                            cmp = old.classify(op if op<4 else op-4, current['a'][i], current['b'][i] if op<4 else 0x7e00)
                            previous = (91 >> (i%8)) & 1
                            active = i < vl and ((current['mask_byte'] >> (i%8)) & 1)
                            independent = {cmp[0]} if active else {previous} if vl == 0 or i < vl else {previous,1,cmp[0]}
                            assert set(permitted) == independent
                            for bit in (0,1):
                                assert bool((bit<<i)&z or (((1-bit)<<i)&o)) == (bit not in permitted)
                        for choose in (min,max):
                            bits = sum(choose(v)<<i for i,v in enumerate(current['allowed']))
                            value = 91 | (bits<<8) | (91<<24)
                            assert old.original_errors(current,value,current['flags']<<32) == old.packed_errors(current,rec,value,current['flags']<<32) == 0
                        rows.append(current)
    assert len(rows)==17920 and len(records)==8960 and len(periods)==48
    assert rows[38]['flags']==0 and rows[39]['flags']==1 and rows[-1]['flags']==1
    out.mkdir()
    shutil.copytree(original, out/'original')
    shutil.copyfile(ASSEMBLY,out/'original/scenario.S')
    for name in ('runtime.c','startup.S','replay.ld'):
        source = OLD/'source_model02/software'/name
        shutil.copyfile(source,out/name)
        pins[str(source)] = sha(source)
    shutil.copyfile(OLD/'packed_core.h',out/'packed_core.h')
    candidate = old.port((original/'parent.c').read_text())
    candidate = replace(candidate,'UNMASKED_COMPARISONS != 1','UNMASKED_COMPARISONS != 0')
    candidate = replace(candidate,'oracle_records[(seed*10+op)*7+l]','oracle_records[((seed*10+op)*7+l)*4+mode]')
    candidate = candidate.replace('fp_compare_unboxed_e16_mf4_full17920',NAME)
    (out/'case.c').write_text(candidate)
    mainc = (OLD/'source_model02/software/main.c').read_text().replace('fp_compare_unboxed_e16_mf4_full17920',NAME)
    (out/'main.c').write_text(mainc)
    header = ['#include <stdint.h>','static const uint64_t input_periods[][4] __attribute__((aligned(8))) = {']
    header += ['{'+','.join(f'UINT64_C(0x{v:016x})' for v in values)+'},' for values in periods]
    header += ['};','static const uint64_t oracle_records[8960] __attribute__((aligned(8))) = {']
    header += [f'UINT64_C(0x{v:016x}),' for v in records]+['};','']
    (out/'generated_tables.h').write_text('\n'.join(header))
    baseline = (original/'parent.c').read_text()
    begin,end = baseline.index('static long syscall3('),baseline.index('static void text(')
    baseline = baseline[:begin]+'extern long host_original_syscall3(long,long,long,long);\n#define syscall3 host_original_syscall3\n'+baseline[end:]
    baseline = baseline[:baseline.index('__asm__(".global _start')]
    baseline = replace(baseline,'void probe_main(void)','void original_probe_main(void)')
    baseline += '\nvoid *original_area(unsigned i) { return i==0?(void *)a:i==1?(void *)b:i==2?(void *)mask:(void *)output; }\n'
    (out/'original_host.c').write_text(baseline)
    save(HERE/'model.json',dict(rows=rows))
    save(HERE/'helper_identity.json',dict(helpers=helpers, parent_elf=str(PARENT),sha256=sha(PARENT)))
    assert all(sha(p)==h for p,h in pins.items())
    save(HERE/'source_status.json',dict(status='SOURCE_MODEL_ONLY_PENDING_HOST',calls=17920,
        records=8960, record_bytes=71680, periods=48, result_bits=286720, guards=35840,
        alloff_first_error_original_ordinal=39, call39_expected_flags=0, final_flags=1,
        pins=pins, original_C_host='Full original body unchanged; only Linux syscall/startup adaptation',
        no_reference=True,no_DUT=True))
    print('MASKED_SOURCE_PREPARED',len(rows),len(records),flush=True)


if __name__ == '__main__':
    main()
