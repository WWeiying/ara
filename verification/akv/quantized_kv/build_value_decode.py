#!/usr/bin/env python3
"""Build original-vs-VLA V decoding using unchanged real KV bytes."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads'))
import attention_run as s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01'
    pv = ROOT/'verification/out/akv-quantkv-pv-primitives-20261024-01'
    capture = ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'
    commands = []

    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out/(label+'.log')).read_text()

    report = s.read_json(base/'build.json')
    s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True and
              s.digest(base/'source-pins.json') == report['source_pins_sha256'], 'Original build receipt drift')
    pins = s.read_json(base/'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    primitive = s.read_json(pv/'result.json')
    s.require(primitive['state'] == 'ACTUAL_GGML_QUANTIZED_V_PRIMITIVES_COMPILED' and
              s.digest(pv/'source-pins.json') == primitive['source_pins_sha256'], 'PV primitive drift')
    s.merge_pins(pins, s.read_json(pv/'source-pins.json'))
    s.merge_pins(pins, primitive['artifact_sha256'])
    s.verify_pins(pins)
    blobs = [capture/('capture-k-'+name+'-v-q8_0')/'decode/block/attn_v_input-0.bin'
             for name in ('q8_0', 'q4_0')]
    for path in blobs:
        s.require(pins.get(str(path)) == s.digest(path) and path.stat().st_size == 69632,
                  'Real V capture not fixed by accepted inputs')
    assembly = out/'value-data.S'
    assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
        f'.balign 64\n.global decode_value{i}\ndecode_value{i}:\n.incbin "{path}"\n'
        for i, path in enumerate(blobs)))
    previous = s.read_json(base/'commands.json')
    compile_command = list(next(r['argv'] for r in previous if '-c' in r['argv'] and
                                str(HERE/'rvv_qbs_main.c') in r['argv']))
    compile_command[compile_command.index(str(HERE/'rvv_qbs_main.c'))] = str(HERE/'value_decode_main.c')
    compile_command[compile_command.index('-o')+1] = str(out/'main.o')
    dep = [x for i, x in enumerate(compile_command) if i not in
           (compile_command.index('-c'), compile_command.index('-o'), compile_command.index('-o')+1)] + ['-M', '-MT', 'object']
    text = execute(dep, 'deps-main')
    s.merge_pins(pins, s.hashes(Path(x).resolve(strict=True) for x in
        shlex.split(text.replace('\\\n', ' ').split(':', 1)[1])))
    execute(compile_command, 'compile-main')
    data_command = [str(assembly) if x == str(HERE/'value_decode_main.c') else x for x in compile_command]
    data_command[data_command.index('-o')+1] = str(out/'data.o')
    execute(data_command, 'compile-data')
    elf = out/'quant_value_decode.elf'
    link = [str(out/'main.o') if x == str(base/'0.o') else
            '-Wl,-Map='+str(out/'link.map') if x == '-Wl,-Map='+str(base/'link.map') else x
            for x in next(r['argv'] for r in previous if '-nostdlib' in r['argv'])
            if x not in (str(base/'3.o'), str(base/'10.o'))]
    link[link.index('-o')+1] = str(elf)
    index = link.index('-Wl,--gc-sections')
    link[index:index] = [str(out/'data.o'), str(pv/'0.o')]
    execute(link, 'link')
    disassembly = execute([Path(compile_command[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
    for instruction in ('vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'):
        s.require(instruction in disassembly, 'Missing actual candidate instruction '+instruction)
    s.require('<dequantize_row_q8_0>:' in disassembly and '<qbs_native_execute_command>:' not in disassembly,
              'Original decoder missing or unrelated QBS runtime retained')
    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('quant_value_elf', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sections = module.alloc_sections(elf)
    s.require(min(x['address'] for x in sections) >= 0x80000000 and
              max(x['address']+x['bytes'] for x in sections) < 0x81000000-65536, 'ELF bounds')
    s.merge_pins(pins, s.hashes([Path(__file__), helper, base/'build.json', base/'source-pins.json',
                               pv/'result.json', pv/'source-pins.json']))
    s.verify_pins(pins)
    s.atomic_json(out/'source-pins.json', pins)
    s.atomic_json(out/'build.json', dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
        elf=str(elf), elf_sha256=s.digest(elf), simv=report['simv'], accepted_image_pins=report['accepted_image_pins'],
        post_pins_match=True, source_pins_sha256=s.digest(out/'source-pins.json'),
        artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()), sections=sections,
        trials=8, profiles=['q8_0', 'q4_0'], value_paths=list(map(str, blobs)),
        elements_per_trial=32768, boundary_elements=3584,
        scope='Original production decoder versus standard RVV VLA decoder; not complete Attention or GGML deployment'))
    print('BUILT_NOT_EXECUTED trials=8 boundary_elements=3584')


if __name__ == '__main__':
    main()
