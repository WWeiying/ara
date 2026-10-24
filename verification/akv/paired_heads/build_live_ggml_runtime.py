#!/usr/bin/env python3
"""Compile live QBS+AKV GGML sources without a privately rewritten runtime."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from build_ggml_candidate import digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLS = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')


def check_policy(rows):
    native = set()
    for row in rows:
        argv = shlex.split(row['command'])
        arches = [a for a in argv if a.startswith('-march=')]
        if not arches or any(a != '-march=rv64gcv_zfh_zvfh' for a in arches):
            raise ValueError('Implicit or extra ISA in live build')
        if str(ROOT/'software/akv/src')+'/' in row['file'] and row['file'].endswith('.c'):
            if not all(a in argv for a in ('-fno-fast-math','-ffp-contract=off')) or any(
                    a in argv for a in ('-ffast-math','-Ofast','-ffp-contract=fast')):
                raise ValueError('Live AKV source property does not enforce the verified FP contract')
            native.add(Path(row['file']).name)
    required = {'akv_runtime.c','akv_native_riscv.c','akv_v2_native_riscv.c',
                'akv_prefill_reference.c','akv_features.c'}
    if native != required:
        raise ValueError('Actual live runtime source inventory differs')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=8)
    a = p.parse_args()
    if not 1 <= a.jobs <= 32:
        raise ValueError('Jobs must be 1..32')
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    def save(name,value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    commands = []
    def invoke(argv,label,timeout=300):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)
        return (out/(label+'.log')).read_text()
    try:
        roots = [LLAMA/'ggml']+[ROOT/'software'/name/part for name in ('akv','qbs') for part in ('src','include')]
        files = [p for base in roots for p in base.rglob('*') if p.is_file() and
                 (p.suffix in ('.c','.cpp','.h','.hpp','.S','.inc','.inl','.cmake') or p.name == 'CMakeLists.txt')]
        private = ROOT/'software/akv/experimental/paired_heads'
        files += [private/p for p in ('admission.h','dispatch.h','native_selection.h','attention_rvv.S',
                                     'f32_pv/runtime.h','f32_pv/attention_rvv.S')]
        files += [Path(__file__),HERE/'test_live_ggml_policy.py',
                  TOOLS/'riscv64-linux-gcc',TOOLS/'riscv64-linux-g++']
        pins = {str(p.resolve()):digest(p) for p in files}
        project = out/'CMakeLists.txt'
        project.write_text('cmake_minimum_required(VERSION 3.16)\n'
            'project(akv_live_ggml LANGUAGES C CXX ASM)\n'
            f'add_subdirectory("{LLAMA / "ggml"}" ggml)\n')
        build = out/'build'
        invoke(['cmake','-S',out,'-B',build,'-G','Ninja',
            '-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=riscv64',
            '-DCMAKE_C_COMPILER='+str(TOOLS/'riscv64-linux-gcc'),
            '-DCMAKE_CXX_COMPILER='+str(TOOLS/'riscv64-linux-g++'),
            '-DCMAKE_ASM_COMPILER='+str(TOOLS/'riscv64-linux-gcc'),
            '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
            '-DCMAKE_CXX_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
            '-DCMAKE_ASM_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
            '-DBUILD_SHARED_LIBS=OFF','-DGGML_NATIVE=OFF','-DGGML_BACKEND_DL=OFF',
            '-DGGML_OPENMP=OFF','-DGGML_RVV=ON','-DGGML_RV_ZFH=ON','-DGGML_RV_ZVFH=ON',
            '-DGGML_RV_ZICBOP=OFF','-DGGML_RV_ZIHINTPAUSE=OFF','-DGGML_RV_ZVFBFWMA=OFF',
            '-DGGML_RISCV_QBS=ON','-DGGML_RISCV_QBS_RUNTIME_DIR='+str(ROOT/'software/qbs'),
            '-DGGML_RISCV_AKV=ON','-DGGML_RISCV_AKV_RUNTIME_DIR='+str(ROOT/'software/akv')],'configure')
        invoke(['cmake','--build',build,'--target','ggml-cpu','-j',str(a.jobs)],'build',1800)
        rows = json.loads((build/'compile_commands.json').read_text())
        check_policy(rows)
        required = {str(LLAMA/'ggml/src/ggml-cpu/arch/riscv'/name) for name in ('akv.cpp','qbs.cpp')}
        if not required <= {r['file'] for r in rows}:
            raise ValueError('Actual GGML QBS/AKV adapters missing')
        # Capture exact compiler dependencies rather than infer include closure.
        for index,row in enumerate(rows):
            argv = shlex.split(row['command'])
            output,compile_flag = argv.index('-o'),argv.index('-c')
            argv = [x for j,x in enumerate(argv) if j not in (output,output+1,compile_flag)]+['-M','-MT','object']
            text = invoke(argv,f'deps-{index}')
            for raw in shlex.split(text.replace('\\\n',' ').split(':',1)[1]):
                path = Path(raw).resolve(strict=True)
                if str(path) in pins and pins[str(path)] != digest(path):
                    raise ValueError('Source changed during dependency collection')
                pins[str(path)] = digest(path)
        if any(digest(path) != sha for path,sha in pins.items()):
            raise ValueError('Live source/header drift')
        archives = list(build.rglob('libggml-cpu.a'))
        if len(archives) != 1:
            raise ValueError('CPU library missing/ambiguous')
        symbols = invoke([TOOLS/'riscv64-linux-nm','--defined-only',archives[0]],'symbols')
        for symbol in ('ggml_riscv_akv_flash_attn','akv_experimental_pv_f32_pair',
                       'akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair',
                       'qbs_native_execute_command'):
            if symbol not in symbols:
                raise ValueError('Missing live QBS/AKV definition '+symbol)
        save('source-pins.json',pins)
        save('result.json',dict(state='LIVE_QBS_AKV_GGML_COMPILED_NOT_EXECUTED',
            translation_units=len(rows),private_runtime_overlay=False,source_rewritten=False,
            verified_native_fp_source_properties=True,source_pins_sha256=digest(out/'source-pins.json'),
            artifacts={str(path):digest(path) for path in (archives[0],build/'compile_commands.json',project)},
            scope='Actual live GGML QBS+AKV adapters and canonical runtime; compilation not model/native execution'))
        print('LIVE_QBS_AKV_GGML_COMPILED_NOT_EXECUTED')
    except BaseException as exc:
        save('result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
