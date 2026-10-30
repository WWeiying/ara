#!/usr/bin/env python3
"""Compile the untouched GGML RVV TU and inspect actual quantized-QK primitives."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
GGML = Path('/home/wangwy/llama/llama.cpp/ggml')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
SYMBOLS = ('quantize_row_q8_0','ggml_vec_dot_q4_0_q8_0','ggml_vec_dot_q8_0_q8_0')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    source = GGML/'src/ggml-cpu/arch/riscv/quants.c'
    source_hash = digest(source)
    objdump = CC.with_name('riscv64-unknown-elf-objdump')
    commands = []
    def execute(argv,name):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        with (out/(name+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(name+'.log')).read_text()
    pins = {str(p):digest(p) for p in (source,Path(__file__).resolve(),CC.resolve(),objdump.resolve())}
    flags = ['-std=gnu11','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany',
        '-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=fast','-ffunction-sections','-fdata-sections',
        *['-I'+str(p) for p in (GGML/'include',GGML/'src',GGML/'src/ggml-cpu')]]
    try:
        execute([CC,'--version'],'gcc-version')
        for tool in ('cc1','as','ld'):
            path = Path(execute([CC,'-print-prog-name='+tool],tool+'-path').strip()).resolve(strict=True)
            pins[str(path)] = digest(path)
        deps = execute([CC,*flags,'-M','-MT','primitives',source],'dependencies')
        for path in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):
            file = Path(path).resolve(strict=True)
            pins[str(file)] = digest(file)
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
        obj = out/'ggml_rvv_quants.o'
        execute([CC,*flags,'-c',source,'-o',obj],'compile')
        disassembly = {}
        for name in SYMBOLS:
            text = execute([objdump,'-d','--disassemble='+name,obj],name)
            if f'<{name}>:' not in text:
                raise ValueError('Missing actual source primitive '+name)
            disassembly[name] = dict(file=str(out/(name+'.log')),
                vector_instructions=any(op in text for op in ('vle','vwmul','vfredmax')),
                scalar_fma='fmadd.s' in text,scalar_multiply='fmul.s' in text)
        if not all(item['vector_instructions'] for item in disassembly.values()):
            raise ValueError('An actual RVV primitive compiled to fallback')
        if digest(source) != source_hash or any(digest(p) != h for p,h in pins.items()):
            raise ValueError('Source/tool/header drift')
        result = dict(state='ACTUAL_GGML_RVV_PRIMITIVES_COMPILED',source=str(source),source_sha256=source_hash,
            source_pins_sha256=digest(out/'source-pins.json'),object_sha256=digest(obj),
            disassembly=disassembly,compiler_contract='O3, no fast-math, explicit ffp-contract=fast, RNE tested later',
            native_execution=False,rtl_performance=False,
            scope='Untouched complete production TU, not extracted or reimplemented functions. Compilation/disassembly only; link and numerical gates remain.')
        (out/'result.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
        print(json.dumps({k:result[k] for k in ('state','source_sha256','native_execution')}))
    except BaseException as exc:
        (out/'result.json').write_text(json.dumps(dict(state='FAIL',error=repr(exc)),indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
