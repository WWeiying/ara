#!/usr/bin/env python3
"""Reuse sealed norm kernels; rebuild only the caller with an idle-complete clock."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess

from audit import digest,require,verify_pins
from build_rms_norm_native import link_archives
from rms_norm_completion import completed_caller
from run_projection_capture_v3 import HERE,VERIFY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();parent=args.build.resolve(strict=True);out=args.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False);report=dict(state='PREPARING',performance_measured=False);pins={};commands=[]
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','CPATH','C_INCLUDE_PATH',
          'CPLUS_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    def pin(path,sha=None):
        path=str(Path(path).resolve(strict=True));value=digest(path)
        require(sha is None or sha==value,'Inherited identity: '+path)
        require(path not in pins or pins[path]==value,'Input drift');pins[path]=value
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=180)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode==0,label+' failed');return child.stdout.decode()
    try:
        old=json.loads((parent/'build.json').read_text())
        require(old['state']=='REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED' and
                old['captured_output_replay_bitwise'] and old['sum_cases']==10 and old['boundary_cases']==53 and
                digest(parent/'source-pins.json')==old['source_pins_sha256'],'Parent kernel build gate')
        for values in (json.loads((parent/'source-pins.json').read_text()),old['artifacts']):
            for path,sha in values.items():pin(path,sha)
        for path in (Path(__file__),HERE/'build_rms_norm_native.py',HERE/'rms_norm_completion.py',parent/'build.json'):pin(path)
        source=out/'completed.cpp';source.write_text(completed_caller((HERE/'rms_norm_native.cpp').read_text()));pin(source)
        records=json.loads((parent/'commands.json').read_text())
        compile_main=list(next(r['argv'] for r in records if r['label']=='compile-main'))
        compile_main[compile_main.index('-c')+1]=str(source);compile_main[compile_main.index('-o')+1]=str(out/'main.o')
        dep=[v for i,v in enumerate(compile_main) if i not in (compile_main.index('-c'),compile_main.index('-o'),compile_main.index('-o')+1)]
        text=run([*dep,'-M','-MT','object'],'dependencies')
        for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
            path=Path(name).resolve(strict=True)
            require(str(path) in pins,'Unknown completed-caller dependency: '+str(path));pin(path,pins[str(path)])
        run(compile_main,'compile-main');pin(out/'main.o')
        link=list(next(r['argv'] for r in records if r['label']=='link'))
        require(link.count(str(parent/'main.o'))==1,'Parent main object inventory')
        link[link.index(str(parent/'main.o'))]=str(out/'main.o')
        elf=out/'rms_norm_completed.elf';link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        run(link,'link');pin(elf)
        linked=link_archives((out/'link.map').read_text(),old['runtime_archives'])
        objdump=Path(link[0]).with_name('riscv64-unknown-elf-objdump')
        dis=run([objdump,'-d',elf],'disassembly')
        strict=run([objdump,'-d',parent/'strict-original.o'],'strict-original-disassembly')
        require('vfwredosum.vs' not in strict and 'fadd.d' in strict,'Strict original is not the scalar reference')
        require(all('<'+n+'>:' in dis for n in ('original_rms_norm','candidate_rms_norm',
            'strict_original_rms_sum','strict_candidate_rms_sum')) and 'vfwredosum.vs' in dis,'Required kernel path missing')
        run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
             VERIFY/'verification/out/e2e_matrix_soc_base_20261106_01/sim',elf],'l2')
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report=dict(old,state='REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED',
            elf=str(elf),elf_sha256=digest(elf),parent_build=str(parent),completed_caller=str(source),
            timing_includes_csr_completion=True,recompiled_objects=1,
            reused_objects=len([p for p in link if p.endswith('.o')])-1,
            source_pins_sha256=digest(out/'source-pins.json'),linked_archives=linked,
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc:report.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n');(out/'build.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
