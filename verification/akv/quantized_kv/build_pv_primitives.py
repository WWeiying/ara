#!/usr/bin/env python3
"""Compile original Q8_0 V decoder and production RVV PV helpers, no execution."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GGML = Path('/home/wangwy/llama/llama.cpp/ggml')
CC = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    commands,pins = [],{}
    def save(name,value):
        (out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    def execute(argv,label):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    flags = ['-std=gnu11','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany',
        '-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=fast','-ffunction-sections','-fdata-sections',
        *['-I'+str(p) for p in (GGML/'include',GGML/'src',GGML/'src/ggml-cpu')]]
    try:
        sources = (GGML/'src/ggml-quants.c',HERE/'pv_primitives.c')
        objects = []
        for index,source in enumerate(sources):
            deps = execute([CC,*flags,'-M','-MT','object',source],f'deps-{index}')
            for path in shlex.split(deps.replace('\\\n',' ').split(':',1)[1]):
                file = Path(path).resolve(strict=True)
                pins[str(file)] = digest(file)
            obj = out/f'{index}.o'
            execute([CC,*flags,'-c',source,'-o',obj],f'compile-{index}')
            objects.append(obj)
        objdump = CC.with_name('riscv64-unknown-elf-objdump')
        required = [('dequantize_row_q8_0',objects[0]),
                    ('quant_kv_ggml_mad_f32',objects[1]),
                    ('quant_kv_ggml_scale_f32',objects[1])]
        disassembly = {}
        for symbol,obj in required:
            text = execute([objdump,'-d','--disassemble='+symbol,obj],symbol)
            if '<'+symbol+'>:' not in text:
                raise ValueError('Missing actual production primitive '+symbol)
            if symbol.endswith('mad_f32') and not any(op in text for op in ('vfmadd.vf','vfmacc.vf')):
                raise ValueError('Production PV helper did not compile to RVV FMA')
            if symbol.endswith('scale_f32') and 'vfmul.vf' not in text:
                raise ValueError('Production scale helper did not compile to RVV multiply')
            disassembly[symbol] = dict(log=str(out/(symbol+'.log')),
                                      vector_setup='vsetvli' in text)
        for path in (Path(__file__),CC.resolve(),objdump.resolve()):
            pins[str(path)] = digest(path)
        for tool in ('cc1','as','ld'):
            path = Path(execute([CC,'-print-prog-name='+tool],tool+'-path').strip()).resolve(strict=True)
            pins[str(path)] = digest(path)
        if any(digest(path) != sha for path,sha in pins.items()):
            raise ValueError('Original source/header/tool drift')
        save('source-pins.json',pins)
        save('result.json',dict(state='ACTUAL_GGML_QUANTIZED_V_PRIMITIVES_COMPILED',
            source_pins_sha256=digest(out/'source-pins.json'),
            artifact_sha256={str(path):digest(path) for path in objects},
            disassembly=disassembly,compiler_contract='O3, no fast-math, explicit ffp-contract=fast',
            source_modified=False,native_execution=False,performance_measured=False,
            scope='Whole original generic quants TU plus thin calls to production vec.h inline helpers'))
        print('ACTUAL_GGML_QUANTIZED_V_PRIMITIVES_COMPILED')
    except BaseException as exc:
        save('result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__ == '__main__':
    main()
