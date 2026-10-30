#!/usr/bin/env python3
"""Build normal llama/GGML libraries independently, with frozen source evidence."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from compile_shared_decode import opcodes

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_half_scale_soc import atomic_json,hashes,digest
from run_tile_context_engine import run_command


def source_inputs(llama):
    paths={llama/'CMakeLists.txt',llama/'ggml/CMakeLists.txt'}
    for directory in ('include','src','cmake','ggml/include','ggml/src','ggml/cmake'):
        paths.update(p for p in (llama/directory).rglob('*') if p.is_file() and
                     (p.name=='CMakeLists.txt' or p.suffix in ('.c','.cc','.cpp','.h','.hpp','.cmake','.in','.S','.inc','.inl')))
    for directory in (ROOT/'software/qbs',ROOT/'software/akv'):
        paths.update(p for p in directory.rglob('*') if p.is_file() and
                     (p.name=='CMakeLists.txt' or p.suffix in ('.c','.cpp','.h','.hpp','.cmake','.inc','.inl')))
    return paths


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'verification/out'):raise ValueError('Independent output required')
    llama=Path('/home/wangwy/llama/llama.cpp')
    toolchain=Path('/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake')
    paths=source_inputs(llama)|{toolchain,Path(__file__),HERE/'compile_shared_decode.py'}
    pins=hashes(paths)
    out.mkdir(parents=True,exist_ok=False)
    atomic_json(out/'source-pins.json',pins)
    state=dict(state='PREPARING',pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/'status.json',state)
    def started(pid):state['child_pid']=pid;save()
    def run(cmd,label,limit):
        cmd=list(map(str,cmd));state.update(state=label.upper(),child_pid=None);save()
        atomic_json(out/(label+'.command.json'),cmd)
        if run_command(cmd,out/(label+'.log'),limit,os.environ.copy(),started):raise RuntimeError(label+' failed')
    try:
        cmake=['cmake','-S',llama,'-B',out/'build','-DCMAKE_TOOLCHAIN_FILE='+str(toolchain),
               '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DCMAKE_EXE_LINKER_FLAGS=-static',
               '-DBUILD_SHARED_LIBS=OFF','-DGGML_NATIVE=OFF','-DGGML_OPENMP=OFF','-DGGML_CPU=ON',
               '-DGGML_CPU_REPACK=ON','-DGGML_BACKEND_DL=OFF','-DGGML_RVV=ON','-DGGML_RV_ZFH=ON',
               '-DGGML_RV_ZVFH=ON','-DGGML_RV_ZICBOP=OFF','-DGGML_RV_ZIHINTPAUSE=OFF','-DGGML_RV_ZVFBFWMA=OFF',
               '-DGGML_RISCV_QBS=ON','-DGGML_RISCV_AKV=ON','-DGGML_RISCV_AKV_QUANT_KV=ON',
               '-DGGML_RISCV_QBS_RUNTIME_DIR='+str(ROOT/'software/qbs'),
               '-DGGML_RISCV_AKV_RUNTIME_DIR='+str(ROOT/'software/akv')]
        for name in ('COMMON','TESTS','EXAMPLES','TOOLS','SERVER','APP','MTMD'):
            cmake.append('-DLLAMA_BUILD_'+name+'=OFF')
        cmake+=['-DLLAMA_CURL=OFF','-DLLAMA_OPENSSL=OFF','-DLLAMA_HTTPLIB=OFF']
        run(cmake,'configure',300)
        run(['cmake','--build',out/'build','--target','llama','-j','8'],'build',1800)
        records=json.loads((out/'build/compile_commands.json').read_text())
        objects={}
        for relative in ('ggml/src/ggml-cpu/arch/riscv/qbs.cpp','ggml/src/ggml-cpu/arch/riscv/quants.c','ggml/src/ggml-cpu/repack.cpp'):
            rows=[r for r in records if Path(r['file']).resolve()==llama/relative]
            if len(rows)!=1:raise ValueError('Missing production compile record: '+relative)
            cmd=shlex.split(rows[0]['command'])
            if [x for x in cmd if x.startswith('-march=')][-1:]!=['-march=rv64gcv_zfh_zvfh']:
                raise ValueError('Effective ISA differs from accepted build')
            for define in ('-DGGML_USE_RISCV_QBS','-DGGML_USE_RISCV_AKV','-DGGML_USE_RISCV_QUANT_KV'):
                if define not in cmd:raise ValueError('Missing production feature: '+define)
            objects[relative]=Path(rows[0]['directory'])/cmd[cmd.index('-o')+1]
        objdump=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-objdump')
        reference=ROOT/'verification/out/q8k-decode-layout-compile-20261026-01/candidate.o'
        code=[]
        for name,obj in (('measured',reference),('normal-build',objects['ggml/src/ggml-cpu/arch/riscv/quants.c'])):
            listing=subprocess.run([str(objdump),'-d','--disassemble=quantize_row_q8_K',str(obj)],
                                   capture_output=True,text=True,check=True,timeout=30).stdout
            (out/(name+'.asm')).write_text(listing);code.append(opcodes(listing))
        if code[0]!=code[1]:raise ValueError('Normal CMake build changed measured quantizer opcodes')
        libraries=[out/'build/src/libllama.a',*[out/'build/ggml/src'/n for n in ('libggml.a','libggml-cpu.a','libggml-base.a')]]
        if hashes(map(Path,pins))!=pins:raise ValueError('Source drift during build')
        pins.update(hashes([*libraries,*objects.values(),out/'build/compile_commands.json',out/'build/CMakeCache.txt']))
        atomic_json(out/'manifest.json',pins)
        state.update(state='PASS',source_files=len(paths),libraries=list(map(str,libraries)),
                     scope='Normal clean CMake build; runtime execution still requires its own gate')
    except BaseException as exc:
        state.update(state='FAIL',error=repr(exc));raise
    finally:
        state['child_pid']=None;save();atomic_json(out/'result.json',state)


if __name__=='__main__':main()
