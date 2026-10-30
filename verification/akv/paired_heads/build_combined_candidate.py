#!/usr/bin/env python3
"""Compile both opt-in paths together without changing sealed runtime sources."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = ROOT/'software/akv/src/akv_v2_native_riscv.c'
CC = Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-gcc')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


decode = load('akv_combined_decode_transform',HERE/'prepare_native_candidate.py')
prefill = load('akv_combined_prefill_transform',HERE/'f32_pv/prepare_prefill_candidate.py')


def transform(source):
    combined = prefill.transform(decode.transform(source))
    # Include order is immaterial, but all call-site substitutions must commute.
    reverse = decode.transform(prefill.transform(source))
    normalize = lambda text: '\n'.join(line for line in text.splitlines() if not line.startswith('#include "../experimental/'))
    if normalize(combined) != normalize(reverse):
        raise ValueError('Decode and Prefill transforms interfere')
    return combined


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    pins,commands = {},[]
    def save(name,data):
        (out/name).write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    def require(condition,message):
        if not condition:
            raise ValueError(message)
    def invoke(argv,label):
        argv = list(map(str,argv))
        commands.append(dict(argv=argv,cwd=str(out)))
        save('commands.json',commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        return (out/(label+'.log')).read_text()
    try:
        source_hash = decode.digest(SOURCE)
        candidate = out/'akv_v2_native_combined.c'
        candidate.write_text(transform(SOURCE.read_text()))
        assembly = out/'akv_v2_attention_combined.S'
        asm_inputs = [ROOT/'software/akv/src/akv_v2_attention_rvv.S',
                      ROOT/'software/akv/experimental/paired_heads/attention_rvv.S',
                      ROOT/'software/akv/experimental/paired_heads/f32_pv/attention_rvv.S']
        assembly.write_text(''.join(f'#include "{path}"\n' for path in asm_inputs))
        flags = ['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O3','-fno-fast-math',
            '-ffp-contract=off','-ffunction-sections','-fdata-sections',
            '-DAKV_REFILL_OVERLAP=0','-iquote',str(SOURCE.parent),
            '-I'+str(ROOT/'software/akv/include')]
        objects = []
        for i,src in enumerate((candidate,assembly)):
            deps = invoke([CC,*flags,'-M','-MT','object',src],f'deps-{i}')
            paths = [Path(x).resolve(strict=True) for x in shlex.split(deps.replace('\\\n',' ').split(':',1)[1])]
            pins.update({str(path):decode.digest(path) for path in paths})
            obj = out/f'{i}.o'
            invoke([CC,*flags,'-c',src,'-o',obj],f'compile-{i}')
            objects.append(obj)
        linked = out/'native_combined.o'
        invoke([CC,'-nostdlib','-r',*objects,'-o',linked],'partial-link')
        symbols = invoke([CC.with_name('riscv64-linux-nm'),linked],'symbols')
        definitions = {line.split()[-1] for line in symbols.splitlines() if len(line.split()) == 3 and
                       line.split()[-2] in ('T','t')}
        undefined = {line.split()[-1] for line in symbols.splitlines() if len(line.split()) == 2 and
                     line.split()[0] == 'U'}
        required = {'akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair',
                    'akv_experimental_pv_f32_pair','akv_attention_execute_v2_native',
                    'akv_attention_execute_v2_with_features_native','akv_attention_execute_v2_prefill_native',
                    'akv_v2_update_outputs_f16_d128_gqa6','akv_v2_update_outputs_f32_d128_gqa6',
                    'akv_v2_compute_scores_f16_generic','akv_v2_update_outputs_f16_generic',
                    'akv_v2_update_outputs_f32_generic'}
        require(required <= definitions and not required & undefined,'Missing/conflicting combined runtime definitions')
        require(not any(x in symbols for x in ('bench_active','bench_pair_enabled')),'Benchmark mutable state')
        for path in [SOURCE,Path(__file__),HERE/'prepare_native_candidate.py',
                     HERE/'f32_pv/prepare_prefill_candidate.py',CC.resolve()]:
            pins[str(path)] = decode.digest(path)
        require(decode.digest(SOURCE) == source_hash and
                all(decode.digest(Path(p)) == h for p,h in pins.items()),'Source drift')
        save('source-pins.json',pins)
        save('result.json',dict(state='COMBINED_RUNTIME_COMPILED_NOT_EXECUTED',canonical_modified=False,
            source_sha256=source_hash,source_pins_sha256=decode.digest(out/'source-pins.json'),
            artifact_sha256={str(path):decode.digest(path) for path in (candidate,assembly,*objects,linked)},
            required_definitions=sorted(required),native_rtl_accepted=False,ggml_deployed=False,
            scope='Linux GNU combined runtime C/assembly partial link only; no numerical or model acceptance'))
        print('COMBINED_RUNTIME_COMPILED_NOT_EXECUTED')
    except BaseException as exc:
        save('result.json',dict(state='FAIL',error=repr(exc),canonical_modified=False))
        raise


if __name__ == '__main__':
    main()
