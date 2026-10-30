#!/usr/bin/env python3
"""Build a successor public-entry experiment without touching sealed inputs."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from run_common_attention import checked_build
from build_common_attention import s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = args.base.resolve(strict=True)
    out = args.output.resolve()
    s.require(not out.is_relative_to(base), 'Use an independent output')
    report, pins = checked_build(base)
    s.require(not report.get('rvv_value_decode'), 'Expected original scalar decoder build')
    out.mkdir(parents=True, exist_ok=False)
    old = s.read_json(base / 'commands.json')
    original_main = str(HERE / 'attention_common_main.c')
    template = list(next(row['argv'] for row in old
                         if '-c' in row['argv'] and original_main in row['argv']))
    commands = []

    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out / 'commands.json', commands)
        with (out / (label + '.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return (out / (label + '.log')).read_text()

    source = HERE / 'attention_value_rvv_main.c'
    template[template.index(original_main)] = str(source)
    template[template.index('-o') + 1] = str(out / 'value-rvv-main.o')
    excluded = {template.index('-c'), template.index('-o'), template.index('-o') + 1}
    deps = execute([x for i, x in enumerate(template) if i not in excluded]
                   + ['-M', '-MT', 'object'], 'dependencies')
    s.merge_pins(pins, s.hashes(Path(x).resolve(strict=True) for x in
                              shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])))
    execute(template, 'compile')
    elf = out / 'value_rvv_attention.elf'
    link = list(next(row['argv'] for row in old if '-nostdlib' in row['argv']))
    s.require(link.count(str(base / 'main.o')) == 1, 'Wrong original main object')
    link[link.index(str(base / 'main.o'))] = str(out / 'value-rvv-main.o')
    link[link.index('-o') + 1] = str(elf)
    link = ['-Wl,-Map=' + str(out / 'link.map') if x.startswith('-Wl,-Map=') else x
            for x in link]
    execute(link, 'link')
    disassembly = execute([Path(template[0]).with_name('riscv64-unknown-elf-objdump'),
                           '-d', elf], 'disassembly')
    for name in ('value_rvv_decode', 'dequantize_row_q8_0', 'akv_quant_native_execute',
                 'qbs_native_execute_command'):
        s.require('<' + name + '>:' in disassembly, 'Missing implementation ' + name)
    s.require('<qbs_ref_execute>:' not in disassembly, 'Reference linked into native ELF')
    decoder = disassembly.split('<value_rvv_decode>:', 1)[1].split('\n\n', 1)[0]
    for mnemonic in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'):
        s.require(mnemonic in decoder, 'Missing RVV decoder operation ' + mnemonic)
    helper = ROOT / 'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('value_attention_elf', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sections = module.alloc_sections(elf)
    s.require(min(x['address'] for x in sections) >= 0x80000000 and
              max(x['address'] + x['bytes'] for x in sections) < 0x81000000 - 65536,
              'ELF bounds')
    s.merge_pins(pins, s.hashes([Path(__file__), helper]))
    s.verify_pins(pins)
    s.atomic_json(out / 'source-pins.json', pins)
    updated = dict(report)
    updated.update(elf=str(elf), elf_sha256=s.digest(elf), sections=sections,
                   predecessor_common_build=str(base), rvv_value_decode=True,
                   ordinary_value_decode='unchanged production scalar decoder',
                   source_pins_sha256=s.digest(out / 'source-pins.json'),
                   artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
                   scope='Same public-entry ABBA Attention; only candidate V decode uses RVV')
    s.atomic_json(out / 'build.json', updated)
    checked_build(out)
    print('COMMON_ENTRY_BUILT_NOT_EXECUTED', report['kind'], 'rvv_value_decode=1')


if __name__ == '__main__':
    main()
