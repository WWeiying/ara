#!/usr/bin/env python3
"""Bounded actual adapter/cache GNU/Spike check, one fresh boot per flag case."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT=Path('/home/wangwy/openproject/ara_dsa')
HERE=ROOT/'verification/performance/optimization_enablement'
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
LLAMA=Path('/home/wangwy/llama/llama.cpp')
SDK=OUT/'stage5_libraries_prepare_20261110_01/inputs/sdk'
CXX=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-g++')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
POLICY='73a07abe4156a7bf7f6090b0249f3f1a4fde81795f9a0694d6d9409f5e1e6842'
POLICY_TEST='5e8d7e88e394ed4222d27c7e27fd7adc976dd2ec6f1a3e3d96b60cb24854fea6'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,why):
    if not ok: raise ValueError(why)
def save(p,v):
    with p.open('x') as f: json.dump(v,f,indent=2,sort_keys=True);f.write('\n')


def main():
    parser=argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();out=a.output.resolve()
    require(out.parent==OUT and out.name.startswith('enablement_software_') and not out.exists(),'Fresh signoff output required')
    out.mkdir();inputs=out/'inputs';inputs.mkdir();pins={};commands=[]
    report=dict(state='FAIL',performance_measured=False,model_executed=False,rtl_changed=False)
    def pin(p):
        p=Path(p).resolve();value=sha(p)
        require(str(p) not in pins or pins[str(p)]==value,'Pin drift: '+str(p));pins[str(p)]=value
    def verify():
        for p,h in pins.items(): require(sha(p)==h,'Pin drift: '+p)
    def run(label,argv,timeout=120):
        argv=list(map(str,argv)); tool=Path(argv[0]).resolve()
        if str(tool) not in pins: pin(tool)
        with (out/(label+'.log')).open('x') as f:
            r=subprocess.run(argv,stdout=f,stderr=subprocess.STDOUT,cwd=out,stdin=subprocess.DEVNULL,timeout=timeout)
        commands.append(dict(label=label,argv=argv,returncode=r.returncode))
        require(r.returncode==0,'Failed '+label+'; inspect original log')
        return (out/(label+'.log')).read_text()
    def copy(src,dst):
        pin(src);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);pin(dst)
    try:
        pin(Path(__file__).resolve())
        for p in (ROOT/'software/llama/accel-options.h',LLAMA/'ggml/src/ggml-cpu/arch/riscv/accel-options.h'):
            require(sha(p)==POLICY,'Policy identity');pin(p)
        require(sha(ROOT/'software/llama/test_accel_options.cpp')==POLICY_TEST,'Policy test identity')
        pin(ROOT/'software/llama/test_accel_options.cpp')
        # Snapshot just GGML source inputs; no development worktree is created.
        ggml=inputs/'ggml'
        for base in ('include','src'):
            for src in sorted((LLAMA/'ggml'/base).rglob('*')):
                if src.is_file() and src.suffix in ('.h','.hpp','.c','.cpp','.S','.inc'):
                    copy(src,ggml/src.relative_to(LLAMA/'ggml'))
        arch=ggml/'src/ggml-cpu/arch/riscv'
        copy(HERE/'software_m4preflight_target_v2.cpp',inputs/'test.cpp')
        old=ROOT/'verification/performance/next_mechanism/stage4/m4_preflight'
        for name in ('start.S','runtime.cpp','link.ld'):copy(old/name,inputs/name)
        helper=SDK/'software/qbs/experimental/m4_preflight/m4_preflight.h'
        require(sha(helper)=='71b07f59aa44bea1102674d68fbe9fbaa36fa055f078804b4ff5dd0353fe0291','SDK helper identity')
        copy(helper,inputs/'m4_preflight.h')
        real=OUT/'m4-prepared-qkv-build-20261027-02/activation_f32.bin'
        require(sha(real)=='913afc315e1a3da1191ec74fe9faab17bdf25d4c672624a2c65192438cc8beb1','Real model input identity')
        copy(real,inputs/'real.bin')
        data=inputs/'data.S'
        data.write_text('.section .rodata\n.balign 64\n.global real_input\nreal_input:\n.incbin "'+str(inputs/'real.bin')+'"\n');pin(data)
        includes=[]
        for p in (inputs,ggml/'include',ggml/'src',ggml/'src/ggml-cpu',arch,SDK/'software/qbs/include'):
            includes+=['-isystem',str(p)]
        flags=['-std=c++17','-O2','-DNDEBUG','-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
            '-mcmodel=medany','-mno-relax','-msmall-data-limit=0','-fno-fast-math','-ffp-contract=off',
            '-ffunction-sections','-fdata-sections','-fno-exceptions','-fno-rtti','-fno-threadsafe-statics',
            '-fno-stack-protector','-fno-tree-vectorize','-fno-tree-slp-vectorize',*includes]
        objects=[]
        for name,source,extra in (
            ('generic',ggml/'src/ggml-cpu/repack.cpp',['-Dggml_quantize_mat_q8_K_4x1_ara_generic=frozen_generic']),
            ('test',inputs/'test.cpp',['-DGGML_RISCV_ACCEL_AUTO=1','-DGGML_USE_RISCV_QBS_M4_PREFLIGHT','-finstrument-functions']),
            ('runtime',inputs/'runtime.cpp',['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns']),
            ('start',inputs/'start.S',[]),('data',data,[])):
            if source.suffix!='.S':
                dep=out/(name+'.d');run(name+'-deps',[CXX,*flags,*extra,'-M','-MF',dep,source])
                for p in shlex.split(dep.read_text().replace('\\\n','').split(':',1)[1]):pin(p)
            obj=out/(name+'.o');run(name+'-compile',[CXX,*flags,*extra,'-c',source,'-o',obj]);pin(obj);objects.append(obj)
        lib=Path(run('libgcc',[CXX,'-print-libgcc-file-name']).strip());pin(lib)
        for name in ('cc1plus','as','ld'):
            pin(run('tool-'+name,[CXX,'-print-prog-name='+name]).strip())
        elfs=[]
        for case in range(16):
            source=inputs/('case-'+str(case)+'.S')
            source.write_text('.section .rodata\n.balign 4\n.global test_case\ntest_case:\n.word '+str(case)+'\n');pin(source)
            obj=out/('case-'+str(case)+'.o')
            run('case-'+str(case)+'-compile',[CXX,*flags,'-c',source,'-o',obj]);pin(obj)
            elf=out/('case-'+str(case)+'.elf')
            run('case-'+str(case)+'-link',[CXX,*flags,'-nostdlib','-static',*objects,obj,
                '-Wl,--gc-sections','-Wl,--build-id=none','-T',inputs/'link.ld',lib,'-o',elf]);pin(elf)
            names=run('case-'+str(case)+'-symbols',[CXX.with_name('riscv64-unknown-elf-nm'),'-n',elf])
            def symbol(name):
                rows=re.findall(r'^([0-9a-f]+) \w '+name+'$',names,re.M)
                require(len(rows)==1,'Missing symbol '+name);return rows[0]
            cmd=out/('case-'+str(case)+'.cmd')
            cmd.write_text('until pc 0 '+symbol('test_exit')+'\nreg 0 a0\nstr '+symbol('test_log')+'\nrs\n');pin(cmd)
            elfs.append((case,elf,cmd))
        pin(SPIKE);save(out/'source-pins.json',pins);verify()
        cases=[]
        for case,elf,cmd in elfs:
            text=run('case-'+str(case)+'-spike',[SPIKE,'-d','--debug-cmd='+str(cmd),
                '--isa=rv64gcv_zfh_zvfh_zvl1024b','-m2',elf],timeout=90)
            marker='M4_PREFLIGHT_VSTART_ABORT_PASS' if case==11 else 'M4_PREFLIGHT_TARGET_PASS case='+str(case)+' '
            require(text.count(marker)==1 and 'FAIL' not in text and 'TRAP' not in text and
                    len(re.findall(r'^0x0000000000000000$',text,re.M))==1,'Target rejection/failure: '+str(case))
            if case==0:
                require(text.count('M4_PREFLIGHT_INVALIDATION_PASS last_byte=1 epoch=1 source=1 computations=4')==1,
                        'Missing real cache invalidation extent')
            cases.append(dict(case=case,elf_sha256=sha(elf),log_sha256=sha(out/('case-'+str(case)+'-spike.log'))))
        verify();report.update(state='M4_PREFLIGHT_GNU_SPIKE_CHECKED',cases=cases,post_pins_match=True,
            policy_sha256=POLICY,source_pins_sha256=sha(out/'source-pins.json'),
            metadata_shims_only=True,numerical_producers_are_real=True)
    except BaseException as exc:report['error']=repr(exc)
    save(out/'commands.json',commands);save(out/'result.json',report)
    print(json.dumps(report,sort_keys=True),flush=True)
    return report['state']!='M4_PREFLIGHT_GNU_SPIKE_CHECKED'


if __name__=='__main__':raise SystemExit(main())
