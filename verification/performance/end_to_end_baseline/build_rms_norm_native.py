#!/usr/bin/env python3
"""Build original/ordered fused GGML RMSNorm after real captured-output replay."""
import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from audit import digest,require,verify_pins
from rms_norm_source import translation_unit,shape_group
from run_projection_capture_v3 import HERE,ROOT,VERIFY,MODEL_RUN,GRAPH

PROGRAM=VERIFY/'verification/out/e2e_decode_native_build_20261106_02'
COMMON=VERIFY/'verification/out/e2e_qwen3_projection_native_build_20261106_03'
TOOLCHAIN=Path('/home/wangwy/openproject/ara/install/riscv-gcc').resolve()


def model_agreement(pins,model):
    for path,sha in pins.items():
        require(path not in model or model[path]==sha,'Model dependency conflict: '+path)


def link_archives(text,expected):
    found=[str(Path(m[1]).resolve(strict=True)) for m in re.finditer(r'^LOAD (.+[.]a)$',text,re.M)]
    require(found and set(found)==set(expected),'Linked runtime archive selection differs')
    for path in found:require(digest(path)==expected[path],'Runtime archive drift: '+path)
    return sorted(set(found))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();data=args.data.resolve(strict=True);out=args.output.absolute()
    require(out==out.resolve() and out.is_relative_to(VERIFY/'verification/out'),'Fresh verification output')
    out.mkdir(parents=True,exist_ok=False);pins={};commands=[];model_pins={}
    env={k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD','CPATH','C_INCLUDE_PATH',
          'CPLUS_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin',LC_ALL='C')
    report=dict(state='PREPARING',performance_measured=False,rtl_changed=False,production_library_changed=False)
    def pin(path,expected=None):
        path=str(Path(path).resolve(strict=True));sha=digest(path)
        require(expected is None or expected==sha,'Input identity: '+path)
        require(path not in model_pins or model_pins[path]==sha,'Model dependency conflict: '+path)
        require(path not in pins or pins[path]==sha,'Conflicting input identity');pins[path]=sha
    def merge(values):
        for path,sha in values.items():pin(path,sha)
    def run(argv,label):
        argv=list(map(str,argv));pin(argv[0]);verify_pins(pins)
        commands.append(dict(label=label,argv=argv));(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        report['state']=label.upper();(out/'status.json').write_text(json.dumps(report,indent=2)+'\n')
        child=subprocess.run(argv,cwd=out,env=env,capture_output=True,timeout=300)
        (out/(label+'.log')).write_bytes(child.stdout+child.stderr)
        require(child.returncode==0,label+' failed');return child.stdout.decode()
    def compiler(driver,label,target=False):
        driver=Path(driver).resolve(strict=True);pin(driver);programs={}
        for name in ('cc1plus','as','collect2','ld'):
            value=run([driver,'-print-prog-name='+name],'tool-'+label+'-'+name).strip()
            path=Path(value) if Path(value).is_absolute() else Path(shutil.which(value,path=env['PATH']) or '')
            require(path.is_file() and (not target or path.resolve().is_relative_to(TOOLCHAIN)),
                    'Compiler subprogram missing/outside toolchain: '+value)
            path=path.resolve(strict=True);pin(path);programs[name]=str(path)
        return dict(driver=str(driver),programs=programs)
    try:
        d=json.loads((data/'data.json').read_text())
        require(d['state']=='REAL_QWEN3_RMS_NORM_DATA_PREPARED_NOT_VERIFIED' and d['k']==2048 and d['rows']==4 and
                d['token_ids']==[32,4621,17654,51435] and d['decode_token']==22406 and
                digest(data/'source-pins.json')==d['source_pins_sha256'],
                'Reconstructed model-input identity')
        merge(json.loads((data/'source-pins.json').read_text()));merge(d['artifacts']);pin(data/'data.json')
        receipt=ROOT/'verification/performance/evidence/output_model_20261106_01/result.json'
        r=json.loads(receipt.read_text());pin(receipt);pin(MODEL_RUN/'source-pins.json',r['source_pins_sha256'])
        # This build consumes source/header snippets, not the model libraries or
        # QEMU tree. Bind their sealed inventory and verify every consumed file
        # below instead of repeatedly hashing unrelated emulator build inputs.
        model_pins=json.loads((MODEL_RUN/'source-pins.json').read_text())
        model_agreement(pins,model_pins)
        ops=GRAPH/'llama/ggml/src/ggml-cpu/ops.cpp';ggml=GRAPH/'llama/ggml/src/ggml.c'
        for path in (ops,ggml,GRAPH/'build/compile_commands.json'):pin(path,model_pins[str(path)])
        includes=[GRAPH/'llama/ggml/include',GRAPH/'llama/ggml/src',GRAPH/'llama/ggml/src/ggml-cpu']
        original=out/'original.cpp';candidate=out/'candidate.cpp';shape=out/'shape.cpp'
        strict_original=out/'strict-original.cpp';strict_candidate=out/'strict-candidate.cpp'
        original.write_text(translation_unit(ops.read_text()));candidate.write_text(translation_unit(ops.read_text(),True))
        strict_original.write_text(translation_unit(ops.read_text(),False,'strict_original'))
        strict_candidate.write_text(translation_unit(ops.read_text(),True,'strict_candidate'))
        shape.write_text(shape_group(ggml.read_text()))
        helper=ROOT/'software/rvv/experimental/ordered_rms_norm/rms_sum.h'
        for path in (Path(__file__),HERE/'audit.py',HERE/'rms_norm_source.py',HERE/'rms_norm_host.cpp',
                     HERE/'rms_norm_native.cpp',helper,original,candidate,strict_original,strict_candidate,shape):pin(path)
        before=json.loads((PROGRAM/'build.json').read_text());cp=json.loads((COMMON/'build.json').read_text())
        require(before['state']=='REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED' and
                digest(PROGRAM/'source-pins.json')==before['source_pins_sha256'] and
                digest(COMMON/'source-pins.json')==cp['source_pins_sha256'],'Common build identity')
        inherited=json.loads((PROGRAM/'source-pins.json').read_text())
        for path,sha in json.loads((COMMON/'source-pins.json').read_text()).items():
            require(path not in inherited or inherited[path]==sha,'Common inventory conflict');inherited[path]=sha
        verify_pins(inherited);merge(inherited);merge(before['artifacts']);pin(PROGRAM/'build.json');pin(COMMON/'build.json')
        pin(VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh')
        for path in (PROGRAM/'commands.json',COMMON/'commands.json'):pin(path,pins[str(path)])
        recipes=json.loads((PROGRAM/'commands.json').read_text())
        template=list(next(row['argv'] for row in recipes if row['label']=='compile-0'))
        tools=dict(host=compiler('/usr/bin/g++','host'),target=compiler(template[0],'target',True))
        def dependencies(argv,source,label,host=False):
            dep=[v for i,v in enumerate(argv) if i not in (argv.index('-c'),argv.index('-o'),argv.index('-o')+1)]
            text=run([*dep,'-M','-MT','object'],'deps-'+label)
            for name in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path=Path(name).resolve(strict=True)
                if str(path) in pins:pin(path,pins[str(path)])
                elif str(path) in model_pins:pin(path,model_pins[str(path)])
                elif str(path) in inherited:pin(path,inherited[str(path)])
                else:
                    # New headers are admitted only from the chosen compiler's
                    # own header installation, never arbitrary project inputs.
                    require(path.suffix in ('.h','.tcc','.inl','.inc','') and
                        (path.is_relative_to(TOOLCHAIN) or host and
                         (path.is_relative_to('/usr/include') or path.is_relative_to('/usr/lib/gcc'))),
                        'Unreviewed dependency: '+str(path));pin(path)
        # Use the real fused function, not a separately written scalar norm.
        host_objects=[]
        for i,source in enumerate((original,shape,HERE/'rms_norm_host.cpp')):
            obj=out/f'host-{i}.o'
            cmd=['/usr/bin/g++','-std=gnu++17','-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=fast',
                 '-ffunction-sections','-fdata-sections',*['-I'+str(p) for p in includes],'-c',source,'-o',obj]
            dependencies(list(map(str,cmd)),source,'host-'+str(i),True);run(cmd,'host-'+str(i));pin(obj);host_objects.append(obj)
        run(['/usr/bin/g++',*host_objects,'-Wl,--gc-sections','-lm','-o',out/'host'],'host-link');pin(out/'host')
        golden=run([out/'host',data],'host-replay')
        require(golden.strip()=='RMS_NORM_REAL_DATA_PASS source=ggml_fused_rms_norm prefill_rows=4 decode_rows=1 width=2048 outputs=10240 bitwise=1',
                'Captured-output replay failed')
        template=[v for v in template if v not in ('-Werror','-ffp-contract=off')]
        template+=['-ffp-contract=fast','-I'+str(helper.parent)]
        symbols={'rms_input':data/'input_f32.bin','rms_weight':data/'norm_weight_f32.bin',
                 'rms_expected':data/'expected_f32.bin','rms_epsilon':data/'epsilon.bin',
                 'rms_decode_input':data/'decode_input_f32.bin','rms_decode_expected':data/'decode_expected_f32.bin'}
        assembly='.section .rodata\n'
        for symbol,path in symbols.items():
            require(str(path) in d['artifacts'],'Unsealed tensor');pin(path,d['artifacts'][str(path)])
            assembly+=f'.balign 64\n.global {symbol}\n{symbol}:\n.incbin "{path}"\n'
        (out/'data.S').write_text(assembly);pin(out/'data.S')
        original_link=list(next(row['argv'] for row in recipes if row['label']=='link'))
        objects=[]
        for value in original_link:
            if value.endswith('.o') and Path(value).parent==COMMON and Path(value).name not in ('0.o','1.o','2.o'):
                pin(value,inherited[str(value)]);objects.append(value)
        require(len(objects)==8,'Common runtime object inventory')
        for label,source in (('main',HERE/'rms_norm_native.cpp'),('original',original),('candidate',candidate),
                             ('strict-original',strict_original),('strict-candidate',strict_candidate),
                             ('shape',shape),('data',out/'data.S')):
            obj=out/(label+'.o');cmd=list(template);cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(obj)
            if label.startswith('strict-'):cmd+=['-frounding-math']
            dependencies(cmd,source,label);run(cmd,'compile-'+label);pin(obj);objects.append(str(obj))
        link=[v for v in original_link if not v.endswith('.o')]
        link[link.index('-Wl,--gc-sections'):link.index('-Wl,--gc-sections')]=objects
        elf=out/'rms_norm.elf';link[link.index('-o')+1]=str(elf)
        link=['-Wl,-Map='+str(out/'link.map') if v.startswith('-Wl,-Map=') else v for v in link]
        archives={}
        for i,arg in enumerate(v for v in link if v.startswith('-l')):
            name='lib'+arg[2:]+'.a'
            value=run([link[0],'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-print-file-name='+name],
                      'runtime-'+str(i)).strip()
            path=Path(value).resolve(strict=True)
            require(path.is_file() and path.is_relative_to(TOOLCHAIN),'Runtime outside target toolchain')
            pin(path);archives[str(path)]=pins[str(path)]
        run(link,'link');pin(elf)
        linked=link_archives((out/'link.map').read_text(),archives)
        dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',elf],'disassembly')
        require(all('<'+name+'>:' in dis for name in ('original_rms_norm','candidate_rms_norm')) and
                'vfwredosum.vs' in dis and 'fadd.d' in dis,'Original/ordered sum implementation missing')
        baseline_dis=run([Path(link[0]).with_name('riscv64-unknown-elf-objdump'),'-d',out/'original.o'],'baseline-disassembly')
        require('fadd.d' in baseline_dis and 'vfwredosum.vs' not in baseline_dis,
                'Baseline already uses ordered widening reduction; reassess candidate')
        run(['/usr/bin/bash',VERIFY/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
             VERIFY/'verification/out/e2e_matrix_soc_base_20261106_01/sim',elf],'l2')
        verify_pins(pins);(out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        report.update(state='REAL_QWEN3_FUSED_RMS_NORM_ABBA_BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            source_pins_sha256=digest(out/'source-pins.json'),data=str(data),rows=[1,4],width=2048,trials=8,
            outputs_checked=40960,boundary_cases=53,sum_cases=10,boundary_rounding_math=True,
            captured_output_replay_bitwise=True,order=[0,1,1,0],
            compiler_tools=tools,runtime_archives=archives,linked_archives=linked,
            original_function_group_sha256=digest(original),candidate_function_group_sha256=digest(candidate),
            artifacts={str(p):digest(p) for p in out.iterdir() if p.is_file() and p.name not in ('status.json','build.json')})
    except BaseException as exc:report.update(state='FAIL',error=repr(exc));raise
    finally:
        (out/'status.json').write_text(json.dumps(report,indent=2)+'\n');(out/'build.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
