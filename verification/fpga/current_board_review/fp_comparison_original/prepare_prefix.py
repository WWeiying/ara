#!/usr/bin/env python3
"""Prepare three bounded original-source prefixes; software references only."""
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'comparison_alias_original'))
import prepare19 as base
from recover import CAMP, TOOLS, CC as OLD_CC, OLD, read, save, sha

OUT = HERE / 'prepared02'
SELECTION = [
    ('alias_v8_e16m8_prefix682', 'rvv_fp_compare_unmasked_alias_v8_e16_m8', 682, 512),
    ('restart_e16m2_prefix130', 'rvv_fp_compare_restart_e16_m2', 130, 128),
    ('restart_unmasked_e16m2_prefix130', 'rvv_fp_compare_restart_unmasked_e16_m2', 130, 128),
]
FAIL = re.compile(r'RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|BOARD_\w*FAIL|BOARD_REPLAY_TRAP')


HOST = r'''
#include <stdio.h>
#include <stdlib.h>
unsigned long capacity(void){return HOST_CAP;}
long replay_write(long n,long fd,long p,long len){if(n!=64||fd!=1)abort();return fwrite((void*)p,1,len,stdout);}
static unsigned calls;
static struct fixture independent(unsigned op,unsigned a,unsigned b){
    unsigned an=(a&0x7c00)==0x7c00 && (a&1023), bn=(b&0x7c00)==0x7c00 && (b&1023);
    unsigned sn=(an && !(a&512)) || (bn && !(b&512));
    unsigned eq=a==b || ((a&0x7fff)==0 && (b&0x7fff)==0);
    unsigned ka=(a&0x8000)?(a^0xffff):(a^0x8000), kb=(b&0x8000)?(b^0xffff):(b^0x8000);
    unsigned lt=!eq && ka<kb;
    unsigned flags=(op<2?sn:an||bn)?16:0;
    unsigned bit=an||bn ? op==1 : op==0?eq:op==1?!eq:op==2?lt:op==3?lt||eq:op==4?!lt&&!eq:!lt;
    return (struct fixture){bit,flags};
}
static unsigned long emulate(unsigned op,const void*aa,const void*bb,void*oo,unsigned long vl,unsigned long cap,const void*mm,unsigned long start,unsigned long sticky){
    const word *a=aa,*b=bb;const unsigned char *m=mm;unsigned char *o=oo;
    unsigned flags=sticky;
    if(DESTINATION_KIND==1 || DESTINATION_KIND==2){const word *p=DESTINATION_KIND==1?a:b;
        for(unsigned i=0;i<cap;++i){unsigned mask=1u<<(i%8),old=(p[i/SEW]>>(i%SEW))&1;
            o[i/8]=(o[i/8]&~mask)|(old<<(i%8));}}
    for(unsigned i=0;i<cap;++i){
        if(i>=start && i<vl && (UNMASKED_COMPARISONS || ((m[i/8]>>(i%8))&1))){
            struct fixture r=independent(op<4?op:op-4,a[i],b[op<4?i:0]);
            unsigned mask=1u<<(i%8);o[i/8]=(o[i/8]&~mask)|(r.bit<<(i%8));flags|=r.flags;
        } else if(HOST_MUTATION==6 && start<vl && i>=vl)o[i/8]|=1u<<(i%8);
    }
    ++calls;
    if(calls==HOST_CALLS){
        if(HOST_MUTATION==1)o[start/8]^=1u<<(start%8);
        if(HOST_MUTATION==2)flags^=16;
        if(HOST_MUTATION==3)o[0]^=1;
        if(HOST_MUTATION==4)o[-1]^=1;
    }
    return ((unsigned long)flags<<32) | (HOST_MUTATION==5 && calls==HOST_CALLS);
}
'''


def main():
    OUT.mkdir(exist_ok=False)
    prepared = OUT / 'prepared'
    prepared.mkdir()
    recovered = HERE / 'provenance01/fp_compare_oracle_3652.c'
    assert sha(recovered) == OLD
    pins = dict(read(HERE / 'provenance01/pins.json'))
    def pin(p):
        pins[str(p)] = sha(p)
    for p in (Path(__file__), HERE / 'recover.py', recovered, Path(base.__file__),
              base.CC.resolve(), base.SPIKE, Path('/usr/bin/gcc').resolve()):
        pin(p)
    for n in ('startup.S','runtime.c','replay.ld'):
        pin(base.BASE / n)
        shutil.copyfile(base.BASE / n, prepared / n)
    rows = read(HERE / 'provenance01/parents.json')
    entries, provenance, host_results = [], [], []
    hostdir = OUT / 'host'
    hostdir.mkdir()
    for name,parent,limit,cap in SELECTION:
        row = next(r for r in rows if r['name']==parent)
        assert row['source_c_sha256']==OLD
        case = prepared / name
        original = case / 'original'
        original.mkdir(parents=True)
        shutil.copyfile(recovered, original / 'parent.c')
        shutil.copyfile(row['assembly'], original / 'scenario.S')
        for n in ('operations.h','fixtures.h'):
            shutil.copyfile(Path(row['manifest']).parent / 'e16' / n, original / n)
        source = recovered.read_text()
        # Stop only after the selected call's entire original oracle has run.
        point = '        ++cases;\n    }\n'
        assert source.count(point)==1
        prefix = source.replace(point, f'        ++cases;\n        if(cases=={limit})goto prefix_done;\n    }}\nprefix_done:\n')
        (original / 'prefix.c').write_text(prefix)
        port = base.adapt(prefix,name)
        oracle = source[source.index('        if((uint32_t)status)'):source.index('        ++cases;')]
        assert oracle in port
        (case / 'case.c').write_text(port)
        for label,a,b in [('prefix',source,prefix),('wrapper',prefix,port)]:
            (case / (label+'.diff')).write_text(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile=label+'_before',tofile=label+'_after')))
        defs = ['-D'+k+'='+str(v) for k,v in row['defines'].items()]
        # Verify the other selected original parents too, not just source hashes.
        rebuilt = case / 'original_rebuilt.elf'
        base.command([OLD_CC,'-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding',
            '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
            '-msmall-data-limit=0','-Wl,--build-id=none','-Wl,-s','-Wall','-Wextra','-Werror',*defs,
            '-I'+str(original),original / 'parent.c',original / 'scenario.S','-o',rebuilt],case / 'original_rebuild.log')
        assert sha(rebuilt)==row['sha256']
        tuples = []
        for seed in range(32):
            for op in range(10):
                for vl in (0,1,2,3,cap//2,cap-1,cap):
                    for mode in range(4):
                        for sticky in range(2):
                            for start in ((1,vl//2,vl,cap-1) if row['defines']['RESTART_COMPARISONS'] else (0,)):
                                tuples.append(dict(seed=seed,op=op,vl=vl,mask=mode,sticky=sticky,vstart=start))
        save(case / 'call_sequence.json',tuples[:limit])
        provenance.append(dict(id=name,parent=row,limit=limit,capacity=cap,first=tuples[0],last=tuples[limit-1],
            original_rebuild_byte_identical=True,oracle_sha256=__import__('hashlib').sha256(oracle.encode()).hexdigest(),
            scope='Original call prefix with full per-call oracle, not full parent and not Linux execution'))
        entries.append(dict(id=name,defines=[d[2:] for d in defs],assembly='scenario.S',include_combined=False))
        for mutation in ([0,1,2,3,4,5,6] if name=='restart_e16m2_prefix130' else [0]):
            hp = hostdir / f'{name}_mutation{mutation}.c'
            hp.write_text(port+'\n'+HOST+'\n'+'\n'.join(
                f'unsigned long op_{i}(const void*a,const void*b,void*o,unsigned long vl,unsigned long cap,const void*m,unsigned long start,unsigned long flags){{return emulate({i},a,b,o,vl,cap,m,start,flags);}}' for i in range(10))+
                f'\nint main(void){{for(unsigned op=0;op<6;++op)for(unsigned a=0;a<16;++a)for(unsigned b=0;b<16;++b){{struct fixture r=independent(op,inputs[a],inputs[b]);if(r.bit!=expected[op][a][b].bit || r.flags!=expected[op][a][b].flags)abort();}}return {name}_main();}}\n')
            exe = hp.with_suffix('')
            base.command(['/usr/bin/gcc','-O2',*defs,f'-DHOST_CAP={cap}',f'-DHOST_CALLS={limit}',f'-DHOST_MUTATION={mutation}',
                '-I'+str(original),hp,'-o',exe],exe.with_suffix('.compile.log'))
            result = subprocess.run([exe],capture_output=True,text=True,timeout=10)
            log = exe.with_suffix('.log'); log.write_text(result.stdout+result.stderr)
            positive = mutation in (0,6)
            assert (result.returncode==0 and f'cases={limit} errors=0' in result.stdout and not FAIL.search(result.stdout)) if positive else (result.returncode==1 and 'RVV_FP_COMPARE_FAIL' in result.stdout)
            host_results.append(dict(id=name,mutation=mutation,status='PASS' if positive else 'EXPECTED_REJECTION',log_sha256=sha(log)))
    save(OUT / 'host.json',dict(status='PASS_3_PREFIXES_5_NEGATIVE_1_AGNOSTIC_CONTROL',results=host_results,
        limitation='Independent integer FP16 classifier checks all1536 archived fixture entries and emulates operations; not RTL proof'))
    # Static equivalence to the existing 50-call derivative; do not execute it again.
    oldprefix = CAMP / 'rvv_compare_alias_prefix01/rvv_prefix_fp_compare_unmasked_alias_v8_e16_m8/scenario.c'
    pin(oldprefix)
    modern = (TOOLS / 'fp_compare_oracle.c').read_text()
    oldtext = oldprefix.read_text()
    rawstart = oldtext.index('        if(seed==0 && op==0 && l==6 && mode==0 && sticky==1) {')
    rawend = oldtext.index('        if((uint32_t)status)',rawstart)
    stripped = oldtext[:rawstart] + oldtext[rawend:]
    stripped = stripped.replace('        if(seed==0 && op==0 && l==6 && mode==0 && sticky==1)goto prefix_done;\n','').replace('prefix_done:\n','')
    assert stripped==modern
    cmd=read(HERE/'provenance01/original_rebuild.command.json')
    cmd[cmd.index(str(recovered))]=str(TOOLS/'fp_compare_oracle.c')
    cmd[-1]=str(OUT/'current_c_parent_rebuilt.elf')
    base.command(cmd,OUT/'current_c_parent_rebuild.log')
    assert sha(Path(cmd[-1]))==sha(HERE/'provenance01/original_rebuilt.elf')
    save(OUT / 'old_prefix_equivalence.json',dict(original_c_sha256=OLD,existing_prefix=str(oldprefix),
        current_c_sha256=sha(TOOLS / 'fp_compare_oracle.c'),optimized_parent_elf_byte_identical=True,
        parent_elf_sha256=sha(Path(cmd[-1])),
        existing_prefix_changes='Only raw output logging and stop after call50; current and recovered original C build the identical original parent ELF',
        old_prefix_rerun=False,new_context='Continue identical original sequence through call682, first retained later op2/seed1/VL1 flag failures'))
    save(prepared / 'provenance.json',dict(schema_version=1,cases=entries,records=provenance,
        files={str(p.relative_to(prepared)):sha(p) for p in prepared.rglob('*') if p.is_file()}))
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-mcmodel=medany','-ffreestanding','-fno-builtin','-fno-stack-protector',
        '-fno-tree-vectorize','-fno-tree-slp-vectorize','-msmall-data-limit=0','-ffunction-sections','-fdata-sections',
        '-Wall','-Wextra','-Werror','-nostdlib','-static','-Wl,--build-id=none','-Wl,--gc-sections','-T',prepared/'replay.ld']
    references, maps = [], {}
    for backend in ('spike','soc'):
        dest = OUT / backend; dest.mkdir()
        programs = {}
        for entry, record in zip(entries,provenance):
            name=entry['id']; case=prepared/name
            main=dest/(name+'_main.c')
            main.write_text('extern void replay_text(const char*);\nextern int '+name+'_main(void);\n'
                'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));if(vb!=128){replay_text("BOARD_REPLAY_VLEN_FAIL\\n");return 90;}\n'
                f'if({name}_main()){{replay_text("BOARD_CASE_FAIL {name}\\n");return 1;}}replay_text("BOARD_CASE_PASS {name}\\nBOARD_REPLAY_PASS\\n");return 0;}}\n')
            elf=dest/(name+'.elf')
            defs=['-D'+d for d in entry['defines']]+(['-DSPIKE_REFERENCE=1'] if backend=='spike' else [])
            base.command([base.CC,*flags,*defs,'-I'+str(case/'original'),case/'case.c',case/'original/scenario.S',main,
                prepared/'startup.S',prepared/'runtime.c','-lgcc','-o',elf],dest/(name+'.compile.log'))
            dis=elf.with_suffix('.dis')
            base.command([base.CC.with_name(base.CC.name.removesuffix('gcc')+'objdump'),'-d',elf],dis)
            nm=subprocess.check_output([base.CC.with_name(base.CC.name.removesuffix('gcc')+'nm'),elf],text=True)
            syms={n:a for a,_,n in (l.split() for l in nm.splitlines())}
            save(dest/(name+'.symbols.json'),syms)
            targets=re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(vmf[^\n]+)',dis.read_text(),re.M)
            assert len(targets)==10
            maps.setdefault(name,{})[backend]=dict(elf_sha256=sha(elf),targets=targets,disassembly_sha256=sha(dis))
            markers=[f'RVV_FP_COMPARE_PASS sew=16 cases={record["limit"]} errors=0',f'BOARD_CASE_PASS {name}','BOARD_REPLAY_PASS']
            programs[name]=dict(path=str(elf),sha256=sha(elf),cases=[name],pass_markers=markers)
            if backend=='spike':
                debug=dest/(name+'.cmd')
                debug.write_text('until pc 0 '+targets[0][0]+'\npc 0\ninsn 0\nreg 0 vl\nreg 0 vstart\nuntil pc 0 '+syms['replay_exit']+'\nreg 0 a0\nstr '+syms['replay_log']+'\nrs\n')
                log=dest/(name+'.spike.log')
                base.command([base.SPIKE,'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvfh_zvl1024b','-m2',elf],log,120)
                text=log.read_text(); values=re.findall(r'^0x([0-9a-f]+)$',text,re.M)
                assert len(values)==4 and [int(v,16) for v in values[1:]]==[0,record['first']['vstart'],0]
                assert not FAIL.search(text) and all(m in text for m in markers)
                references.append(dict(id=name,status='PASS',calls=record['limit'],log_sha256=sha(log),first_target_pc=targets[0][0],last_tuple=record['last']))
        save(dest/'programs.json',dict(schema_version=1,programs=programs,prepared=str(prepared),
            provenance_sha256=sha(prepared/'provenance.json'),backend='spike-htif' if backend=='spike' else 'vcs-soc'))
    assert all(sha(Path(p))==h for p,h in pins.items())
    save(OUT/'pins.json',pins)
    save(OUT/'address_map.json',maps)
    save(OUT/'reference.json',dict(status='PASS_3_BOUNDED_ORIGINAL_PREFIXES_NOT_DUT',results=references,pins_unchanged=True))
    print('HOST_AND_SPIKE_PASS_3_PREFIXES_NOT_DUT')


if __name__=='__main__':
    main()
