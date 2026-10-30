#!/usr/bin/env python3
"""Build actual GGML against an isolated combined runtime overlay; no deployment."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LLAMA = Path('/home/wangwy/llama/llama.cpp')
TOOLS = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_compile_policy(rows):
    for row in rows:
        command = shlex.split(row['command'])
        arches = [x for x in command if x.startswith('-march=')]
        if not arches or any(x != '-march=rv64gcv_zfh_zvfh' for x in arches):
            raise ValueError('Unexpected or implicit ISA in production GGML command')
        if Path(row['file']).suffix in ('.c','.cpp') and not all(x in command for x in
                ('-fno-fast-math','-ffp-contract=off')):
            raise ValueError('Production FP policy differs from native acceptance')
        if any(x in command for x in ('-ffast-math','-Ofast','-ffp-contract=fast')):
            raise ValueError('Conflicting FP policy')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=8)
    a = p.parse_args()
    if not 1 <= a.jobs <= 32:
        raise ValueError('Jobs must be 1..32')
    candidate = a.candidate.resolve(strict=True)
    r = json.loads((candidate/'result.json').read_text())
    pins = json.loads((candidate/'source-pins.json').read_text())
    if (r.get('state') != 'COMBINED_RUNTIME_COMPILED_NOT_EXECUTED' or
        r.get('canonical_modified') is not False or
        digest(candidate/'source-pins.json') != r['source_pins_sha256']):
        raise ValueError('Wrong combined candidate')
    pins.update(r['artifact_sha256'])
    if any(digest(path) != sha for path,sha in pins.items()):
        raise ValueError('Candidate input/artifact drift')
    runtime = ROOT/'software/akv'
    sources = [path for base in (LLAMA/'ggml',runtime/'src',runtime/'include')
               for path in base.rglob('*') if path.is_file() and
               (path.suffix in ('.h','.hpp','.c','.cpp','.S','.inl','.inc','.cmake') or
                path.name == 'CMakeLists.txt')]
    sources += [Path(__file__),candidate/'source-pins.json',candidate/'result.json',
                TOOLS/'riscv64-linux-gcc',TOOLS/'riscv64-linux-g++']
    pins.update({str(path.resolve()):digest(path) for path in sources})
    out = a.output.resolve()
    if out.is_relative_to(candidate):
        raise ValueError('Use an independent output directory')
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
    try:
        overlay = out/'runtime'
        (overlay/'src').mkdir(parents=True)
        (overlay/'include').symlink_to(runtime/'include',target_is_directory=True)
        (overlay/'experimental').symlink_to(runtime/'experimental',target_is_directory=True)
        replacements = {'akv_v2_native_riscv.c':candidate/'akv_v2_native_combined.c',
                        'akv_v2_attention_rvv.S':candidate/'akv_v2_attention_combined.S'}
        for path in (runtime/'src').iterdir():
            if path.is_file():
                target = replacements.get(path.name,path)
                # Copies keep candidate-relative includes anchored in this overlay.
                if path.name in replacements:
                    (overlay/'src'/path.name).write_bytes(target.read_bytes())
                else:
                    (overlay/'src'/path.name).symlink_to(path)
        project = out/'CMakeLists.txt'
        project.write_text('cmake_minimum_required(VERSION 3.16)\n'
            'project(akv_combined_ggml_candidate LANGUAGES C CXX ASM)\n'
            f'add_subdirectory("{LLAMA / "ggml"}" ggml)\n')
        build = out/'build'
        invoke(['cmake','-S',out,'-B',build,'-G','Ninja',
            '-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=riscv64',
            '-DCMAKE_C_COMPILER='+str(TOOLS/'riscv64-linux-gcc'),
            '-DCMAKE_CXX_COMPILER='+str(TOOLS/'riscv64-linux-g++'),
            '-DCMAKE_ASM_COMPILER='+str(TOOLS/'riscv64-linux-gcc'),
            '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON',
            '-DCMAKE_C_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off -DAKV_REFILL_OVERLAP=0',
            '-DCMAKE_CXX_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off',
            '-DCMAKE_ASM_FLAGS=-march=rv64gcv_zfh_zvfh -mabi=lp64d',
            '-DBUILD_SHARED_LIBS=OFF','-DGGML_NATIVE=OFF','-DGGML_BACKEND_DL=OFF',
            '-DGGML_OPENMP=OFF','-DGGML_RVV=ON','-DGGML_RV_ZFH=ON','-DGGML_RV_ZVFH=ON',
            '-DGGML_RV_ZICBOP=OFF','-DGGML_RV_ZIHINTPAUSE=OFF','-DGGML_RV_ZVFBFWMA=OFF',
            '-DGGML_RISCV_QBS=OFF',
            '-DGGML_RISCV_AKV=ON','-DGGML_RISCV_AKV_RUNTIME_DIR='+str(overlay)],'configure')
        invoke(['cmake','--build',build,'--target','ggml-cpu','-j',str(a.jobs)],'build',1800)
        commands_compiled = json.loads((build/'compile_commands.json').read_text())
        required = [str(overlay/'src/akv_v2_native_riscv.c'),str(overlay/'src/akv_v2_attention_rvv.S'),
                    str(LLAMA/'ggml/src/ggml-cpu/arch/riscv/akv.cpp')]
        actual = {row['file'] for row in commands_compiled}
        if not set(required) <= actual:
            raise ValueError('GGML did not compile the combined native and production adapter')
        check_compile_policy(commands_compiled)
        if any(digest(path) != sha for path,sha in pins.items()):
            raise ValueError('Source drift during GGML build')
        archives = list(build.rglob('libggml-cpu.a'))
        if len(archives) != 1:
            raise ValueError('Missing/ambiguous production CPU archive')
        invoke([TOOLS/'riscv64-linux-nm','--defined-only',archives[0]],'symbols')
        symbols = (out/'symbols.log').read_text()
        for symbol in ('ggml_riscv_akv_flash_attn','akv_experimental_pv_f32_pair',
                       'akv_experimental_pv_f16_pair','akv_experimental_qk_f16_pair_panel4'):
            if symbol not in symbols:
                raise ValueError('Missing production call path: '+symbol)
        save('source-pins.json',pins)
        save('result.json',dict(state='ACTUAL_GGML_COMBINED_RUNTIME_COMPILED_NOT_EXECUTED',
            canonical_modified=False,external_llama_modified=False,ggml_deployed=False,
            source_pins_sha256=digest(out/'source-pins.json'),
            artifact_sha256={str(path):digest(path) for path in
                [archives[0],build/'compile_commands.json',project,*[overlay/'src'/n for n in replacements]]},
            scope='Actual production GGML CMake adapter plus combined runtime archive only; no native execution or performance'))
        print('ACTUAL_GGML_COMBINED_RUNTIME_COMPILED_NOT_EXECUTED')
    except BaseException as exc:
        save('result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
