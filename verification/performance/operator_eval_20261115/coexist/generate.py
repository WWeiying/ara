"""Deterministic small firmware fixtures and instruction kernels, not execution."""
import json
from contract import require,save,fnv


def fixture(output,rows,kind):
    payload=bytearray();assembly=['.section .rodata.coexist,"a",@progbits','.balign 64',
        '.global co_data_guard_before','co_data_guard_before:','.fill 64,1,0xa5',
        '.global co_data_begin','co_data_begin:']
    declarations=[];entries=[]
    def blob(label,raw):
        padding=-len(payload)%64;payload.extend(bytes(padding));offset=len(payload);payload.extend(raw)
        assembly.extend(['.balign 64','.global '+label,label+':',
                         '.incbin '+json.dumps(str(output/'fixture.bin'))+','+str(offset)+','+str(len(raw))])
        declarations.append('extern const unsigned char '+label+'[];')
    for i,row in enumerate(rows):
        for role in ('a','b','seed','gold'):
            if role not in row: continue
            width=row['sew'] if role in ('a','b') else row['width']
            raw=b''.join(v.to_bytes(width//8,'little') for v in row[role])
            blob('co_%d_%s'%(i,role),raw)
        row['bytes']=len(row['gold'])*row['width']//8
        require(row['bytes']<=256,'Oversized small coexist fixture')
        raw=b''.join(x.to_bytes(row['width']//8,'little') for x in row['gold'])
        row['output_hash']=fnv(raw+b'\xa5'*(256-len(raw)))
        row['id']=i
        function='co_kernel_%d'%i if kind!='handoff' else row['function']
        declarations.append('void %s(unsigned char *, uint64_t *);'%function)
        row.setdefault('expected_vl',row.get('vl',0))
        row.setdefault('expected_vtype',((row.get('sew',8).bit_length()-4)<<3))
        row.setdefault('expected_vcsr',5)
        entries.append('  {%s, co_%d_gold, %d, %d, %d, %d, %d, UINT64_C(0x%x)},'%
            (function,i,row['bytes'],row['initial_fcsr'],row['expected_fcsr'],
             row['expected_vl'],row['expected_vtype'],row['output_hash']))
    blob('co_mask',bytes([0xaa,0xaa]))
    assembly.extend(['.global co_data_end','co_data_end:','.global co_data_guard_after',
                     'co_data_guard_after:','.fill 64,1,0xa5','.section .note.GNU-stack,"",@progbits'])
    (output/'fixture.bin').write_bytes(payload)
    (output/'data.S').write_text('\n'.join(assembly)+'\n')
    header=['#ifndef CO_FIXTURE_H','#define CO_FIXTURE_H',*declarations,
        'typedef void (*co_kernel_t)(unsigned char *, uint64_t *);',
        'typedef struct { co_kernel_t kernel; const unsigned char *gold; unsigned bytes;',
        '  unsigned initial_fcsr, fcsr, vl, vtype; uint64_t hash; } co_case_t;',
        '#define CO_CASES %d'%len(rows),'#define CO_CHAIN %d'%(kind=='handoff'),
        '#define CO_KIND '+json.dumps(kind),'#define CO_DATA_BYTES %d'%len(payload),
        '#define CO_DATA_HASH UINT64_C(0x%x)'%fnv(payload),
        'static const co_case_t co_cases[CO_CASES] = {',*entries,'};','#endif']
    (output/'fixture.h').write_text('\n'.join(header)+'\n')
    save(output/'fixture.json',dict(kind=kind,cases=rows,data_bytes=len(payload),data_hash=fnv(payload),
        numerical_contract='Every output byte and inactive byte checked on target outside ROI; independent gold',
        rejected=['SEW64 widening to128 exceeds ELEN64; never generated']))


def kernels(output,rows):
    code=['.text','.option push','.option norvc','.option norelax']
    for i,r in enumerate(rows):
        sew,width=r['sew'],r['width'];emul=2 if width>sew else 1
        label='co_kernel_%d'%i
        code.extend(['.p2align 2','.global '+label,'.type '+label+',@function',label+':',
            'li t0,16',f'vsetvli t1,t0,e{width},m{emul},tu,mu',f'la t4,co_{i}_seed',
            f'vle{width}.v v24,(t4)',f'vsetvli t1,t0,e{sew},m1,tu,mu',
            f'la t4,co_{i}_a',f'la t5,co_{i}_b',f'vle{sew}.v v8,(t4)',
            f'vle{sew}.v v16,(t5)','la t4,co_mask','vlm.v v0,(t4)',
            'li t0,%d'%r['vl'],f'vsetvli t1,t0,e{sew},m1,tu,mu',
            'sd t1,0(a1)','csrr t1,vtype','sd t1,8(a1)',
            'li t0,%d'%r['restart'],'csrw vstart,t0',
            '.global co_test_%d'%i,'.type co_test_%d,@function'%i,'co_test_%d:'%i,
            r['op']+'.vv v24,v8,v16'+(',v0.t' if r['masked'] else ''),
            '.size co_test_%d,4'%i,'csrr t1,vstart','sd t1,16(a1)',
            'li t0,16',f'vsetvli zero,t0,e{width},m{emul},tu,mu',
            f'vse{width}.v v24,(a0)','ret','.size '+label+',.-'+label])
    code.extend(['.option pop','.section .note.GNU-stack,"",@progbits'])
    (output/'kernels.S').write_text('\n'.join(code)+'\n')
