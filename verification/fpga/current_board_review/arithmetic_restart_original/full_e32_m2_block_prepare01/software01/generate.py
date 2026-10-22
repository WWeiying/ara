#!/usr/bin/env python3
"""Generate one reviewable e32/m2 candidate. No compiler or reference executor."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
A = HERE.parents[1]
OLD = A / 'full_e32_m1_packed_prepare01/software01'
CANDIDATE = A / 'full_e32_m2_scalar_candidate01'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def emit(path, value):
    with Path(path).open('x') as stream:
        stream.write(value)

def save(path, value):
    emit(path, json.dumps(value, indent=2) + '\n')

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

def replace(text, old, new, count=1):
    require(text.count(old) == count, 'Exact source replacement: ' + old)
    return text.replace(old, new)

def main():
    require(sha(CANDIDATE/'CANDIDATE.json') == '635f20f10c2d16db43ce57e12b7f1b6a8ffc32bdb3d1a3f62320f1a50b61829d', 'Sealed candidate identity')
    prior = load('m1_compile_source', OLD/'prepare.py')
    base = prior.base
    text = (OLD.parent/'model.py').read_text()
    text = text.replace('e32/m1', 'e32/m2').replace('e32_m1', 'e32_m2')
    text = text.replace('HERE.parent/', 'HERE.parents[1]/')
    for old, new in [('CAP=32', 'CAP=64'), ('PHYSICAL_BYTES=128', 'PHYSICAL_BYTES=256'),
                     ('OUTPUT_BYTES=136', 'OUTPUT_BYTES=264'), ('EXPECTED_WORDS=17', 'EXPECTED_WORDS=33'),
                     ('Exact136 bytes/17words', 'Exact264 bytes/33words'),
                     ("r['mask'][4:]==[0]*124", "r['mask'][8:]==[0]*120"),
                     ('actualvlm4', 'actualvlm8'),
                     ('0c11f7a2d6bcf0fa0ee27e5f4eb3f9d1fc567d29ad638c5e2c9675d0dc2785e4', '978310da20bf437709dae962164491c1f1e8bea6acb9b62ba7a0dbe01c621c3c'),
                     ('834ea0fdd38dfc9f948477f7daf8de462fcbe00d4983e71302846703982055f3', 'f5a921e6cbb233c4e22f5431cfa198da50e8910d2644c66dd444b908cedebf07')]:
        require(old in text, 'Model replacement ' + old)
        text = text.replace(old, new)
    emit(HERE/'model.py', text)
    model = load('e32m2_full_model', HERE/'model.py')
    seeds, rows = model.generate()
    save(HERE/'sequence.json', rows)
    save(HERE/'seed_inputs.json', seeds)
    blocks, by_value, ids = [], {}, []
    for row in rows:
        raw = b''.join(w.to_bytes(8, 'little') for w in row['words'])
        require(len(raw) == 264, 'Exact output bytes')
        rowids = []
        for offset in range(0, 264, 64):
            block = raw[offset:offset+64].ljust(64, b'\0')
            if block not in by_value:
                by_value[block] = len(blocks)
                blocks.append(block)
            rowids.append(by_value[block])
        require(len(rowids) == 5, 'Five blocks without call deduplication')
        require(b''.join(blocks[i] for i in rowids)[:264] == raw, 'All264 bytes exact')
        require(blocks[rowids[-1]][8:] == bytes(56), 'ROM-only padding')
        ids.append(rowids)
    require(len(blocks) < 65536, 'uint16 block IDs')
    def words(values):
        return '{' + ','.join(f'UINT64_C(0x{x:016x})' for x in values) + '}'
    expected = '#include <stdint.h>\nstatic const uint64_t expected_blocks[][8]={\n'
    expected += ',\n'.join(words([int.from_bytes(b[i:i+8], 'little') for i in range(0,64,8)]) for b in blocks) + '\n};\n'
    expected += 'static const uint16_t expected_ids[5985][5]={\n' + ',\n'.join('{' + ','.join(map(str, r)) + '}' for r in ids) + '\n};\n'
    emit(HERE/'expected.h', expected)
    emit(HERE/'host_expected.h', 'static const uint64_t expected_words[5985][33]={\n' + ',\n'.join(words(r['words']) for r in rows) + '\n};\n')
    fixture = 'struct fixture_row {unsigned seed,op,vl,mode,start,si;};\nstatic const struct fixture_row fixture_rows[5985]={\n'
    fixture += ',\n'.join('{' + ','.join(str(r[k]) for k in ('seed','op','vl','mode','start','si')) + '}' for r in rows) + '\n};\n'
    for bank in ('a','b'):
        fixture += f'static const unsigned fixture_{bank}[3][64]={{\n' + ',\n'.join('{' + ','.join(f'{x}u' for x in s[bank]) + '}' for s in seeds) + '\n};\n'
    emit(HERE/'host_fixture.h', fixture)
    packed = '''#include <stdint.h>
static uint64_t raw_word32(const void *p,unsigned offset) {
    uint64_t value; __builtin_memcpy(&value,(const unsigned char *)p+offset,8); return value;
}
static void initialize_output(void *p) {
    const uint64_t value=UINT64_C(0x0000005b0000005b);
'''
    packed += ''.join(f'    __builtin_memcpy((unsigned char *)p+{i},&value,8);\n' for i in range(0,264,8)) + '}\n'
    packed += 'static unsigned packed_mismatch(const void *p,uint64_t ordinal) {\n'
    for block in range(5):
        packed += f'    const uint64_t *b{block}=expected_blocks[expected_ids[ordinal][{block}]];\n'
        packed += ''.join(f'    if(raw_word32(p,{block*64+i*8})!=b{block}[{i}])return 1;\n' for i in range(8 if block<4 else 1))
    packed += '    return 0;\n}\n'
    emit(HERE/'packed.h', packed)
    original = base.old.runtime_adapt((A/'recovery22/reconstructed_oracle.c').read_text())
    candidate = base.old.runtime_adapt((CANDIDATE/'candidate_original.c').read_text())
    candidate = replace(candidate, 'static word a[1024], b[1024], out[1026];',
        'static word a[1024], b[1024];\nstatic word out[1026] __attribute__((aligned(8)));\n#include "expected.h"\n#include "packed.h"')
    candidate = replace(candidate, 'for(unsigned i=0;i<cap+2;++i)out[i]=sentinel;', 'initialize_output(out);')
    start = candidate.index('                    unsigned packed=0;')
    end = candidate.index('                    ++checks;', start)
    fallback = candidate[start:end]
    require(fallback in original, 'Exact original fallback')
    candidate = candidate[:start] + '                    if(packed_mismatch(out,checks)) {\n' + fallback + '                    } else elements+=cap;\n' + candidate[end:]
    emit(HERE/'case.c', candidate)
    emit(HERE/'original_case.c', original)
    shutil.copyfile(CANDIDATE/'scalar_setup.h', HERE/'scalar_setup.h')
    archive = HERE/'original'
    archive.mkdir()
    for src, name in [(base.ARCH/'rvv_matrix_e32_m2.S','scenario.S'),(base.ARCH/'e32/operations.h','operations.h')]:
        shutil.copyfile(src, archive/name)
    host = '#include <stdint.h>\n' + (OLD/'host.c').read_text()
    # Dimension changes only; uint32 shifts stay32, all original mutation types stay.
    for old,new in [('fp_writes[2][32]','fp_writes[2][64]'),('index<32','index<64'),
                    ('return 32;','return 64;'),('cap==32','cap==64'),('i<32','i<64'),
                    ('i=32;i<1024','i=64;i<1024'),('i*8+bit<32','i*8+bit<64'),
                    ('i<34','i<66'),('i=34;i<1026','i=66;i<1026'),('[calls][16]','[calls][32]'),
                    ('pos=33','pos=65'),('pos=32','pos=64'),('raw[138]','raw[266]'),
                    ('raw[137]','raw[265]'),('136','264'),('191520','383040'),('120960','241920')]:
        require(old in host, 'Host dimension replacement ' + old)
        host = host.replace(old,new)
    host = host.replace('#include "host_fixture.h"', '#include "host_fixture.h"\n#include "host_expected.h"')
    host = host.replace('static void fp_store(unsigned bank, unsigned index, unsigned value);',
        'static void fp_store(unsigned bank, unsigned index, unsigned value);\nstatic void mask_event(unsigned kind,unsigned index,const uint8_t *p);\nstatic unsigned fp_order,mask_events,total_mask_clear,total_mask_bits;')
    host = host.replace('    ++fp_writes[bank][index];', '    need(fp_order==2*index+bank,"FP ordered a[i],b[i] on every call");\n    ++fp_order;\n    ++fp_writes[bank][index];')
    marker='long replay_write(long n,long fd,long p,long count) {'
    hooks='''static void mask_event(unsigned kind,unsigned index,const uint8_t *p) {
    need(calls<5985,"mask event beyond scope");
    const struct fixture_row *r=&fixture_rows[calls];
    need(r->si==0,"mask event outside group initialization");
    if(mask_events<16) {
        need(kind==0 && index==8*mask_events,"mask sixteen exact ordered clears before bitsets");
        for(unsigned j=0;j<8;++j)need(p[index+j]==0,"actual cleared bytes");
        ++total_mask_clear;
    } else {
        unsigned ordinal=mask_events-16,seen=0,wanted=64;
        for(unsigned i=0;i<64;++i)if(selected(r->mode,i)){if(seen++==ordinal){wanted=i;break;}}
        need(kind==1 && index==wanted,"original selected bitset order/freshness");
        for(unsigned byte=0;byte<128;++byte) {
            unsigned v=0;
            for(unsigned bit=0;bit<8;++bit)if(byte*8+bit<=index && selected(r->mode,byte*8+bit))v|=1u<<bit;
            need(p[byte]==v,"actual cumulative mask RMW value");
        }
        ++total_mask_bits;
    }
    ++mask_events;
}
'''
    host = replace(host, marker, hooks+marker)
    host = replace(host, '    if(op>=25)++fp_calls;', '''    need(fp_order==(op>=25?128u:0u),"full128 fresh FP stores");fp_order=0;
    unsigned selected_count=r->mode==0?64:r->mode==1?32:9;
    need(mask_events==(r->si==0?16+selected_count:0),"all mask writes before first group call");mask_events=0;
    if(op>=25)++fp_calls;''')
    host = replace(host, '    int rc=arithmetic_main();', '    int rc=arithmetic_main();\n    need(total_mask_clear==35280 && total_mask_bits==77175,"complete original mask event counts");')
    # The original footprint tests retain their protected page and every-byte checks.
    emit(HERE/'host.c',host)
    scope=dict(calls=5985,ops=35,cap=64,SEW=32,physical_groups=2,output_bytes=264,
        output_words=33,output_reads=197505,results=383040,guards=11970,FP_calls=1890,
        FP_SW=241920,mask_SD=35280,mask_SB=77175,physical_mask_bytes=128,vlm_bytes=8,
        helpers=77805,static_helper_instructions=458,blocks=len(blocks),ROM_bytes=len(blocks)*64+59850,
        source_C_binary_equivalent_reconstruction=True,fflags_oracle=False,reference=False,DUT=False)
    save(HERE/'scope.json',scope)
    pins={str(p):sha(p) for p in [*map(Path,model.SOURCE_PINS),CANDIDATE/'CANDIDATE.json',
        CANDIDATE/'candidate_original.c',CANDIDATE/'scalar_setup.h',OLD/'host.c',OLD/'prepare.py',
        A/'full_e32_m1_packed_prepare01/model.py']}
    pins.update({str(p):sha(p) for p in HERE.rglob('*') if p.is_file()})
    save(HERE/'source_manifest.json',dict(status='GENERATED_PENDING_INTEGRATED_SOURCE_REVIEW',pins=pins,scope=scope))
    print(json.dumps(scope),flush=True)

if __name__=='__main__':
    main()
