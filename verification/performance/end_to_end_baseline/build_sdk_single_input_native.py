#!/usr/bin/env python3
"""Build one ABBA ELF with independent old/candidate SDKs and accepted real operands."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from audit import digest,require,verify_pins
from check_sdk_single_input import oracle_paths
from run_projection_capture_v3 import HERE,ROOT,VERIFY

PROGRAM=VERIFY/'verification/out/e2e_decode_native_build_20261106_02'
COMMON=VERIFY/'verification/out/e2e_qwen3_projection_native_build_20261106_03'


def inherited_compile_pins(caller,common):
    combined=dict(caller)
    for path,sha in common.items():
        require(path not in combined or combined[path]==sha,'Conflicting inherited dependency: '+path)
        combined[path]=sha
    return combined


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host-result',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();host_result=args.host_result.resolve(strict=True);host=host_result.parent;out=args.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[];result=dict(state='PREPARING',performance_measured=False,whole_model=False)
    def pin(path,expected=None):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(expected is None or sha==expected,'Input identity: '+path)
        require(path not in pins or pins[path]==sha,'Input drift');pins[path]=sha
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        result['state']=label.upper();(out/'status.json').write_text(json.dumps(result,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,capture_output=True,timeout=300)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode==0,label+' failed');return child.stdout.decode()
    try:
        h=json.loads(host_result.read_text())
        require(h['state']=='SDK_SINGLE_INPUT_HOST_DIFF_PASS' and h['source_pins_sha256']==digest(host/'source-pins.json'),
                'Host differential gate')
        hp=json.loads((host/'source-pins.json').read_text());verify_pins(hp);verify_pins(h['artifacts'])
        pin(host_result);pin(host/'source-pins.json');pin(h['candidate_runtime']);pin(h['helper_path'])
        require(digest(h['baseline_runtime'])=='04d74029e5d2a80cfe70a2d5192e4d0ccfdc18fb1eeb119c0dc9bb3765edb26b',
                'Wrong generic SDK reference')
        receipt=ROOT/'verification/performance/evidence/decode_native_20261106_01/result.json';pin(receipt)
        accepted=json.loads(receipt.read_text());audit=Path(accepted['run'])
        require(digest(audit/'result.json')==accepted['result_sha256'],'Accepted native audit identity');pin(audit/'result.json')
        program=json.loads((PROGRAM/'build.json').read_text())
        require(program['state']=='REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED' and
                digest(PROGRAM/'source-pins.json')==program['source_pins_sha256'],'Real-data program gate')
        old=json.loads((PROGRAM/'source-pins.json').read_text());verify_pins(old);verify_pins(program['artifacts'])
        for path in (COMMON/'build.json',COMMON/'source-pins.json'):
            require(old.get(str(path))==digest(path),'Common compiler provenance missing');pin(path,old[str(path)])
        cp=json.loads((COMMON/'source-pins.json').read_text())
        require(json.loads((COMMON/'build.json').read_text())['source_pins_sha256']==digest(COMMON/'source-pins.json'),
                'Common compile inventory identity')
        verify_pins(cp);compile_pins=inherited_compile_pins(old,cp)
        # Preserve the checked oracle/data closure through execution and replay,
        # not just the subset needed to compile the two new objects.
        inherited=inherited_compile_pins(compile_pins,program['artifacts'])
        for path,sha in inherited.items():pin(path,sha)
        for path in oracle_paths(PROGRAM):
            require(program['artifacts'].get(str(path))==pins.get(str(path)),'Unsealed oracle payload')
        for path in (Path(__file__),HERE/'sdk_single_input_native.cpp',HERE/'decode_native.cpp',HERE/'audit.py',
                     HERE/'check_sdk_single_input.py',
                     PROGRAM/'build.json',PROGRAM/'source-pins.json',PROGRAM/'commands.json',COMMON/'commands.json'):pin(path)
        recipes=json.loads((PROGRAM/'commands.json').read_text());common=json.loads((COMMON/'commands.json').read_text())
        baseline_link=list(next(r['argv'] for r in recipes if r['label']=='link'))
        original_objects=[Path(v) for v in baseline_link if v.endswith('.o')]
        require(len(original_objects)==11,'Original object inventory')
        objects=[]
        for path in original_objects:
            if path==PROGRAM/'0.o':continue
            pin(path,old.get(str(path),program['artifacts'].get(str(path))));objects.append(str(path))
        require(COMMON/'9.o' in original_objects and digest(COMMON/'9.o')==old[str(COMMON/'9.o')],'Generic runtime object missing')
        main_cc=list(next(r['argv'] for r in recipes if r['label']=='compile-0'))
        runtime_cc=list(next(r['argv'] for r in common if r['label']=='compile-9'))
        require(h['renames'] and all(v.startswith('-Dqbs_') and '=baseline_qbs_' in v for v in h['renames']),
                'Complete baseline namespace inventory required')
        aliases=[v.replace('=baseline_qbs_','=candidate_qbs_',1) for v in h['renames']]
        for label,source,cmd,extra in (('main',HERE/'sdk_single_input_native.cpp',main_cc,[]),
            ('candidate',Path(h['candidate_runtime']),runtime_cc,
             ['-I'+h['include_dir'],'-I'+str(Path(h['helper_path']).parent),*aliases])):
            cmd=list(cmd);cmd[1:1]=extra;cmd[cmd.index('-c')+1]=str(source)
            obj=out/(label+'.o');cmd[cmd.index('-o')+1]=str(obj)
            dep=[v for i,v in enumerate(cmd) if i not in (cmd.index('-c'),cmd.index('-o'),cmd.index('-o')+1)]
            text=run([*dep,'-M','-MT','object'],'deps-'+label)
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve(strict=True)
                if path==source.resolve():pin(path)
                elif path.is_relative_to(host):
                    require(hp.get(str(path),h['artifacts'].get(str(path)))==digest(path),'Unpinned candidate input: '+str(path));pin(path)
                else:
                    require(str(path) in compile_pins,'Unreviewed compile dependency: '+str(path));pin(path,compile_pins[str(path)])
            run(cmd,'compile-'+label);pin(obj);objects.append(str(obj))
        link=[v for v in baseline_link if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
        elf=out/'sdk_single_input.elf';link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        run(link,'link');pin(elf)
        dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        require(all('<'+name+'>:' in dis for name in ('qbs_execute_with_options','candidate_qbs_execute_with_options',
                    'quantize_row_q8_K','qbs_native_execute_command')) and
                'qbs_execute_single_input' in dis and '<qbs_ref_execute>:' not in dis,'Independent SDK/native path missing')
        run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
             VERIFY/'verification/out/e2e_matrix_soc_base_20261106_01/sim',elf],'l2')
        verify_pins(hp);verify_pins(compile_pins);verify_pins(pins)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result.update(state='REAL_QWEN3_SDK_SINGLE_INPUT_ABBA_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),host_result=str(host_result),host_result_sha256=digest(host_result),
            oracle_build=str(PROGRAM),order=[0,1,1,0],trials=4,commands=112,outputs=3584,
            oracle_inputs={str(p):pins[str(p)] for p in oracle_paths(PROGRAM)},
            reused_objects=10,rebuilt_objects=2,full_k=True,full_n=False,production_sdk_changed=False,
            artifacts={str(path):digest(path) for path in out.iterdir() if path.is_file() and path.name not in ('status.json','build.json')})
    except BaseException as exc:result.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'status.json').write_text(json.dumps(result,indent=2)+'\n');(out/'build.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
