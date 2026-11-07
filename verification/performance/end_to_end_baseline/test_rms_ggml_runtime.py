#!/usr/bin/env python3
"""Bounded host/Spike+pk functional test of the actual frozen GGML wrapper; no EDA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

HERE=Path(__file__).resolve().parent
RUNS=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ARCH=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv')
CC=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-g++')
SPIKE=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
SPIKE_SHA='c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2'
PK=Path('/home/wangwy/software/toolchains/riscv-pk/riscv64-unknown-elf/bin/pk')
ACCEPTED=RUNS/'e2e_output_tile_20261106_03'
HEADERS={'rms-norm.h':'15419c5ed566e490325b09eafd124226d2118d0b3b627ba53dbbfc7acc12d3da',
         'rms-sum.h':'d4c54ce1a9865934d84ed5e58b6ed0137a3045a041b3a23247ab74fc2a60ddbe',
         'rms-output.h':'e2e497ab156a64aa75ae24a33872971616678a373de3b03339c5572dcf56aa6a'}


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def require(ok,message):
    if not ok:raise ValueError(message)


def run(out):
    out=out.absolute();require(out==out.resolve() and out.is_relative_to(RUNS),'Fresh sole-verification output')
    out.mkdir(parents=True,exist_ok=False)
    pins={};commands=[];result=dict(state='RMS_GGML_RUNTIME_TEST_FAIL',functional_only=True,
        rtl_executed=False,performance_measured=False,live_sources_modified=False)
    def pin(path,expected=None):
        path=Path(path).resolve(strict=True);value=digest(path)
        require(expected is None or value==expected,'Pinned identity differs: '+str(path))
        require(str(path) not in pins or pins[str(path)]==value,'Input drift: '+str(path));pins[str(path)]=value
    def verify():
        for path,sha in pins.items():require(digest(path)==sha,'Source/artifact drift: '+path)
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','LD_LIBRARY_PATH','CPATH','C_INCLUDE_PATH','CPLUS_INCLUDE_PATH','GCC_EXEC_PREFIX','LIBRARY_PATH','COMPILER_PATH')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    def command(argv,name,timeout=45):
        argv=list(map(str,argv));pin(argv[0]);verify();commands.append(dict(label=name,argv=argv,timeout_seconds=timeout))
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=timeout)
        (out/(name+'.log')).write_bytes(child.stdout+child.stderr);commands[-1]['returncode']=child.returncode
        require(child.returncode==0,name+' failed; preserve first attempt');verify()
        return (child.stdout+child.stderr).decode(errors='replace')
    try:
        for path in (Path(__file__),HERE/'test_rms_ggml_runtime.cpp'):pin(path)
        snapshot=out/'inputs';snapshot.mkdir()
        for name,sha in HEADERS.items():
            pin(ARCH/name,sha);(snapshot/name).write_bytes((ARCH/name).read_bytes());pin(snapshot/name,sha)
        source=snapshot/'test_rms_ggml_runtime.cpp';source.write_bytes((HERE/source.name).read_bytes());pin(source)
        known=json.loads((ACCEPTED/'source-pins.json').read_text());pin(ACCEPTED/'source-pins.json')
        pin(ACCEPTED/'commands.json');pin(ACCEPTED/'result.json')
        flags=['-O3','-static','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-fno-tree-vectorize',
               '-fno-fast-math','-ffp-contract=off','-frounding-math','-Wall','-Wextra','-Werror','-I'+str(snapshot)]
        for tool in ('cc1plus','as','ld','collect2'):
            path=command([CC,'-print-prog-name='+tool],'locate-'+tool).strip();pin(path,known.get(str(Path(path).resolve())))
        for lib in ('libm.a','libc.a','libgcc.a','libstdc++.a','libgcc_eh.a'):
            path=command([CC,'-print-file-name='+lib],'locate-'+lib).strip();pin(path,known.get(str(Path(path).resolve())))
        deps=command([CC,*flags,'-M','-MT','object',source],'dependencies')
        for path in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):pin(path)
        command(['/usr/bin/g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-I'+str(snapshot),source,'-o',out/'host'],'build-host')
        pin(out/'host');host=command([out/'host'],'host-fallback')
        require(host.strip()=='RMS_GGML_RUNTIME_HOST_FALLBACK_PASS no_writes=1','Host fallback did not pass')
        command([CC,*flags,source,'-lm','-o',out/'runtime.elf'],'build-rvv');pin(out/'runtime.elf')
        dis=command([CC.with_name('riscv64-linux-objdump'),'-d',out/'runtime.elf'],'disassembly')
        gate=re.search(r'(?m)^[0-9a-f]+ <rms_runtime_gate>:\n(.*?)(?=\n[0-9a-f]+ <)',dis,re.S)
        require(gate is not None,'Missing actual guard shim')
        lines=gate[1].splitlines();capture=next(i for i,line in enumerate(lines) if re.search(r'\bcsrr\s+\w+,vstart',line))
        before=lines[:capture]
        require(not any(re.search(r'\b(?:jal|jalr|call|v[a-z0-9]+[.])\b',line) for line in before),
                'Call/vector instruction before entry VSTART capture')
        result['guard_disassembly']={'entry_vstart_capture_before_calls_and_vector_ops':True,'lines_before_capture':len(before)}
        (out/'guard-disassembly.log').write_text(gate[0])
        pin(SPIKE,SPIKE_SHA);pin(PK)
        text=command([SPIKE,'--isa=rv64gcv_zfh_zicntr_zvfh_zvl1024b','--priv=MSU','--pmpregions=16',
                      '-m512','--instructions=20000000',PK,out/'runtime.elf'],'spike-pk-functional',90)
        markers=[line for line in text.splitlines() if line.startswith('RMS_GGML_RUNTIME_')]
        require(markers==['RMS_GGML_RUNTIME_PASS cases=90 aliases=30 rejected=7 modes=5 exact=1 flags=1'],
                'Actual wrapper arithmetic/state/guard/alias checks incomplete')
        verify();result.update(state='RMS_GGML_RUNTIME_HOST_AND_SPIKE_FUNCTIONAL_PASS',post_pins_match=True,
            marker=markers[0],limits=['Actual frozen wrapper, not full ops.cpp/model integration',
            'Spike+pk is a functional ISA environment, not SoC/PMP or hardware timing equivalence',
            'No performance measured; current CSR-first header only; no live variant edits'])
    except BaseException as exc:result.update(error=repr(exc),post_pins_match=False);raise
    finally:
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result['source_pins_sha256']=digest(out/'source-pins.json')
        result['artifacts']={str(p):digest(p) for p in out.rglob('*') if p.is_file() and p.name!='result.json'}
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='artifacts'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=RUNS/'e2e_rms_ggml_runtime_20261106_01')
    run(p.parse_args().output)
