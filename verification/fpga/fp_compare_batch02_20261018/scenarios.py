#!/usr/bin/env python3
"""Original FPGA FP comparison tuples with separate context-layout controls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('batch02_replay', HERE/'run.py')
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
ROOT, CAMP = base.ROOT, base.CAMP
CONFIGS = [
    ('unboxed_unmasked_alias_v16_e32_m1', 32, 'm1', 2, 1, 46, 'rvv_fp_comparisons_unboxed_v16_unmasked_01', [(27,2,6,2,1)]),
    ('unmasked_alias_v8_e32_m4', 32, 'm4', 1, 0, 45, 'rvv_fp_comparisons_unmasked_alias_v8_01', [(0,5,4,3,0)]),
    ('unmasked_alias_v16_e32_m8', 32, 'm8', 2, 0, 45, 'rvv_fp_comparisons_unmasked_alias_v16_01', [(5,3,2,1,0)]),
    ('unmasked_alias_v8_e32_mf2', 32, 'mf2', 1, 0, 45, 'rvv_fp_comparisons_unmasked_alias_v8_01', [(16,5,5,0,0)]),
    ('unboxed_unmasked_alias_v16_e16_m4', 16, 'm4', 2, 1, 46, 'rvv_fp_comparisons_unboxed_v16_unmasked_01', [(19,3,6,2,0),(21,3,6,3,1)]),
    ('unboxed_unmasked_alias_v8_e16_m4', 16, 'm4', 1, 1, 46, 'rvv_fp_comparisons_unboxed_v8_unmasked_01', [(1,2,2,1,0)]),
]
LOOPS = '''    for(unsigned seed=0;seed<32;++seed)for(unsigned op=0;op<10;++op)
    for(unsigned l=0;l<7;++l)for(unsigned mode=0;mode<4;++mode)
    for(unsigned sticky=0;sticky<2;++sticky)
    for(unsigned trial=0;trial<(RESTART_COMPARISONS ? 4U:1U);++trial) {'''


def context_assembly():
    regs = ['ra', *['a'+str(i) for i in range(8)], *['t'+str(i) for i in range(7)]]
    lines = ['.text', '.balign 4', 'context_roundtrip:', 'addi sp,sp,-176']
    lines += [f'sd {r},{8*i}(sp)' for i,r in enumerate(regs)]
    for i,csr in enumerate(['vl','vtype','vstart','vcsr','fcsr']):
        lines += [f'csrr t0,{csr}', f'sd t0,{128+8*i}(sp)']
    # Same four e8/m8 accesses as the standard Linux vector context path.
    lines += ['la t2,context_buffer', 'vsetvli t0,zero,e8,m8,ta,ma']
    for v in (0,8,16,24):
        lines += [f'vse8.v v{v},(t2)']
        if v!=24: lines += ['add t2,t2,t0']
    lines += ['la t2,context_buffer', 'vsetvli t0,zero,e8,m8,ta,ma']
    for v in (0,8,16,24):
        lines += [f'vle8.v v{v},(t2)']
        if v!=24: lines += ['add t2,t2,t0']
    lines += ['ld t0,128(sp)', 'ld t1,136(sp)', 'vsetvl zero,t0,t1',
              'ld t0,144(sp)', 'csrw vstart,t0', 'ld t0,152(sp)', 'csrw vcsr,t0',
              'ld t0,160(sp)', 'csrw fcsr,t0']
    lines += [f'ld {r},{8*i}(sp)' for i,r in enumerate(regs)]
    lines += ['addi sp,sp,176', 'ret', '.bss', '.balign 64', 'context_buffer:', '.zero 4096']
    return '\n'.join(lines)+'\n'


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    parent_source = base.SOURCE.read_text()
    flags = ['-Os','-march=rv64gcv','-mabi=lp64d','-nostdlib','-static','-ffreestanding',
             '-fno-builtin','-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',
             '-msmall-data-limit=0','-Wl,--build-id=none','-Wall','-Wextra','-Werror']
    programs, pins = {}, {}
    evidence = []
    for b in (2,4,6,7):
        path = Path(f'/home/wangwy/fpga_runs/ara_va_rvv_explore_20261018_{b:02}/summary.json')
        pins[str(path)] = base.sha(path)
        evidence += [c for c in json.loads(path.read_text())['cases'] if c['board']['status']=='failed']
    for stem,sew,lmul,destination,unboxed,release,archname,tuples in CONFIGS:
        name = 'rvv_fp_compare_'+stem
        cfg = out/name; cfg.mkdir()
        original = cfg/'original'; original.mkdir()
        arch = CAMP/archname
        record = next(c for c in evidence if c['name']==name)
        old = CAMP/f'rvv_additions{release}/binaries'/name
        assert base.sha(old)==record['sha256']
        for path,filename in [(base.SOURCE,'parent.c'), (arch/(name+'.S'),'scenario.S'),
                              (arch/f'e{sew}/fixtures.h','fixtures.h'), (arch/f'e{sew}/operations.h','operations.h')]:
            shutil.copyfile(path, original/filename); pins[str(path)]=base.sha(path)
        defs = [f'-D{x}' for x in [f'SEW={sew}','UNMASKED_COMPARISONS=1',
                'RESTART_COMPARISONS=0', f'DESTINATION_KIND={destination}',f'UNBOXED_COMPARISONS={unboxed}']]
        r = base.command([base.OLD_CC,*flags,'-Wl,-s',*defs,'-I'+str(original),original/'parent.c',
                          original/'scenario.S','-o',cfg/'original_rebuilt.elf'],cfg,'original_rebuild')
        assert r['returncode']==0
        assert base.sha(cfg/'original_rebuilt.elf')==record['sha256'], name
        oracle = parent_source[parent_source.index('        if((uint32_t)status)'):parent_source.index('        ++cases;')]
        for index,(seed,op,length,mode,sticky) in enumerate(tuples):
            for context in (0,1):
                ident = f'{stem}_t{index}_ctx{context}'
                dest = cfg/f't{index}_ctx{context}'; dest.mkdir()
                replacement = (f'    {{ unsigned seed={seed},op={op},l={length},mode={mode},sticky={sticky},trial=0;\n'
                               '        (void)trial;')
                assert parent_source.count(LOOPS)==1
                source = parent_source.replace(LOOPS,replacement)
                source = base.helper.adapt(source,ident)
                assert oracle in source
                # Error-only diagnostics preserve every original check and error count.
                source = source.replace('if(actual!=wanted.bit)++errors;',
                    'if(actual!=wanted.bit){++errors;text("FP_BIT index=");num(i);text(" expected=");num(wanted.bit);text(" actual=");num(actual);text("\\n");}')
                (dest/'case.c').write_text(source)
                (dest/'source.diff').write_text(''.join(difflib.unified_diff(parent_source.splitlines(True),source.splitlines(True))))
                assembly = (original/'scenario.S').read_text()
                if context:
                    assert assembly.count('csrw fflags,a7\n')==10
                    assembly = assembly.replace('csrw fflags,a7\n',
                        'addi sp,sp,-16\nsd ra,0(sp)\ncall context_roundtrip\n'
                        'ld ra,0(sp)\naddi sp,sp,16\ncsrw fflags,a7\n')+context_assembly()
                (dest/'scenario.S').write_text(assembly)
                for filename in ('startup.S','runtime.c','replay.ld'):
                    shutil.copyfile(base.RUNTIME/filename,dest/filename)
                    pins[str(base.RUNTIME/filename)]=base.sha(base.RUNTIME/filename)
                (dest/'main.c').write_text('extern void replay_text(const char*);\nextern int '+ident+'_main(void);\n'
                    'int main(void){unsigned long vb;__asm__ volatile("csrr %0,vlenb":"=r"(vb));'
                    'if(vb!=128){return 90;}\nreplay_text("BOARD_CASE_BEGIN '+ident+'\\n");\n'
                    'if('+ident+'_main()){return 1;}\nreplay_text("BOARD_REPLAY_PASS\\n");return 0;}\n')
                for backend in ('soc','spike'):
                    r = base.command([base.helper.CC,*flags,'-mcmodel=medany','-ffunction-sections','-fdata-sections',
                         '-Wl,--gc-sections','-T',dest/'replay.ld',*defs,
                         *(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),'-I'+str(original),
                         *[dest/n for n in ('case.c','scenario.S','main.c','startup.S','runtime.c')],
                         '-lgcc','-o',dest/(backend+'.elf')],dest,backend+'_compile')
                    assert r['returncode']==0, str(dest)
                nm = subprocess.check_output([str(base.helper.CC.with_name('riscv64-unknown-elf-nm')),'-n',dest/'spike.elf'],text=True)
                symbols={r.split()[2]:r.split()[0] for r in nm.splitlines() if len(r.split())==3}
                (dest/'spike.cmd').write_text('until pc 0 '+symbols['replay_exit']+'\nreg 0 a0\nstr '+symbols['replay_log']+'\nrs\n')
                r = base.command([base.helper.SPIKE,'-d','--debug-cmd='+str(dest/'spike.cmd'),
                                 '--isa=rv64gcv_zfh_zvfh_zvl1024b','-m2',dest/'spike.elf'],dest,'spike')
                markers=[f'RVV_FP_COMPARE_PASS sew={sew} cases=1 errors=0','BOARD_REPLAY_PASS']
                text=(dest/'spike.log').read_text()
                assert r['returncode']==0 and all(m in text for m in markers) and 'RVV_FP_COMPARE_FAIL' not in text
                programs[ident]=dict(directory=str(dest),elf_sha256=base.sha(dest/'soc.elf'),pass_markers=markers,
                                    sew=sew,lmul=lmul,context=context,tuple=[seed,op,length,mode,sticky],original=record)
    pins[str(Path(__file__))]=base.sha(Path(__file__))
    base.save(out/'prepared.json',dict(programs=programs,pins=pins,
         files={str(p):base.sha(p) for p in out.rglob('*') if p.is_file()},
         scope='7 authentic first-failure tuples; 7 separate context-layout controls. Not full sequence or Linux execution.'))
    print('PREPARED_SPIKE_14_PASS_NOT_DUT',flush=True)


def replay(out, prepared):
    out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((prepared/'prepared.json').read_text())
    for group in ('files','pins'):
        for path,digest in plan[group].items(): assert base.sha(path)==digest,path
    spec=importlib.util.spec_from_file_location('runtime',base.RUNTIME/'run.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    ledger=json.loads((base.IMAGE/'image.json').read_text())
    frozen=runtime.sealed(Path(ledger['snapshot']))
    assert base.sha(Path(ledger['snapshot'])/'snapshot.json')==ledger['snapshot_sha256']
    for path,digest in ledger['files'].items(): assert base.sha(path)==digest,path
    assert base.sha(Path(ledger['simv']).parent/'simulator.conf')==ledger['configuration_sha256']
    assert base.sha(Path(ledger['simv']).parent/'vcs_source_manifest.json')==ledger['manifest_sha256']
    records=json.loads((Path(ledger['snapshot'])/'snapshot.json').read_text())['live_source_sha256']
    for path,digest in records.items():
        if Path(path).is_relative_to(ROOT/'hardware/src') or Path(path).is_relative_to(ROOT/'hardware/deps'):
            assert base.sha(path)==digest,path
    base.save(out/'identity.json',dict(image=ledger,prepared=str(prepared),prepared_sha256=base.sha(prepared/'prepared.json')))
    results=[]
    stopped=threading.Event()
    def execute(item):
        name,entry=item
        if stopped.is_set():
            r=dict(name=name,status='CANCELLED',reason='Earlier focused test did not pass')
            print(json.dumps(r),flush=True)
            return r
        dest=out/name;dest.mkdir()
        elf=Path(entry['directory'])/'soc.elf'
        assert base.sha(elf)==entry['elf_sha256']
        r=base.command([ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
                       '+PRELOAD='+str(elf),'+TESTCASE='+name,'+NO_FSDB'],dest,'vcs',timeout=600,env=runtime.environment())
        log=(dest/'vcs.log').read_text(errors='replace')
        bad=re.findall(r'(?:RVV_FP_COMPARE_(?:FAIL|DETAIL|CAPACITY_FAIL)|FP_BIT|BOARD_REPLAY_(?:TRAP|SERVICE_FAIL)|Fatal:)[^\r\n]*',log)
        r.update(name=name,status='PASS' if r['returncode']==0 and not bad and
                 all(m in log for m in entry['pass_markers']) and 'Core Test *** SUCCESS ***' in log else 'NOT_PASS',diagnostics=bad)
        if r['status']!='PASS': stopped.set()
        base.save(dest/'result.json',r);print(json.dumps(r),flush=True)
        return r
    # Already-running cases finish; a new failure prevents further dispatch.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(execute,plan['programs'].items()): results.append(r)
    base.save(out/'results.json',dict(results=results,scope=plan['scope']))
    return int(any(r['status']!='PASS' for r in results))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','replay'])
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--prepared',type=Path)
    a=p.parse_args();out=a.out.resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    if a.command=='prepare': prepare(out)
    else:
        assert a.prepared
        raise SystemExit(replay(out,a.prepared.resolve()))
