#!/usr/bin/env python3
"""Compare QBS/shared Attention with an equally vectorized V-decode baseline."""
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
from run_common_attention import checked_build, s


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.base.resolve(strict=True), args.output.resolve()
    s.require(not out.is_relative_to(base), 'Use independent output')
    report, pins = checked_build(base)
    s.require(report.get('rvv_value_decode') is True and
              not report.get('rvv_baseline_decode'), 'Expected candidate-only RVV build')
    out.mkdir(parents=True, exist_ok=False)
    old = s.read_json(base / 'commands.json')
    source = HERE / 'attention_rvv_baseline_main.c'
    command = list(next(row['argv'] for row in old if '-c' in row['argv']))
    original_source = str(HERE / 'attention_value_rvv_main.c')
    s.require(command.count(original_source) == 1, 'Wrong predecessor source')
    command[command.index(original_source)] = str(source)
    command[command.index('-o') + 1] = str(out / 'main.o')
    commands = []

    def execute(argv, name):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out / 'commands.json', commands)
        with (out / (name + '.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        return (out / (name + '.log')).read_text()

    excluded = {command.index('-c'), command.index('-o'), command.index('-o') + 1}
    deps = execute([x for i, x in enumerate(command) if i not in excluded]
                   + ['-M', '-MT', 'object'], 'dependencies')
    s.merge_pins(pins, s.hashes(Path(x).resolve(strict=True) for x in
                              shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])))
    execute(command, 'compile')
    link = list(next(row['argv'] for row in old if '-nostdlib' in row['argv']))
    s.require(link.count(str(base / 'value-rvv-main.o')) == 1, 'Wrong predecessor object')
    link[link.index(str(base / 'value-rvv-main.o'))] = str(out / 'main.o')
    elf = out / 'rvv_baseline_attention.elf'
    link[link.index('-o') + 1] = str(elf)
    link = ['-Wl,-Map=' + str(out / 'link.map') if x.startswith('-Wl,-Map=') else x
            for x in link]
    execute(link, 'link')
    assembly = execute([Path(command[0]).with_name('riscv64-unknown-elf-objdump'),
                        '-d', elf], 'disassembly')
    for absent in ('dequantize_row_q8_0', 'value_rvv_decode', 'qbs_ref_execute'):
        s.require('<' + absent + '>:' not in assembly, 'Unexpected decoder/reference ' + absent)
    for present in ('fair_value_decode', 'akv_quant_native_execute',
                    'ggml_vec_dot_q4_0_q8_0', 'ggml_vec_dot_q8_0_q8_0',
                    'qbs_native_execute_command'):
        s.require('<' + present + '>:' in assembly, 'Missing ordinary/shared operation ' + present)
    decoder = assembly.split('<fair_value_decode>:', 1)[1].split('\n\n', 1)[0]
    for operation in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'):
        s.require(operation in decoder, 'Missing RVV operation ' + operation)
    helper = ROOT / 'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('fair_attention_elf', helper)
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
                   predecessor_common_build=str(base), rvv_baseline_decode=True,
                   ordinary_value_decode='same RVV decoder as candidate',
                   source_pins_sha256=s.digest(out / 'source-pins.json'),
                   artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
                   scope='Public-entry ABBA; both schedules use identical RVV V decoder')
    s.atomic_json(out / 'build.json', updated)
    checked_build(out)
    print('COMMON_ENTRY_BUILT_NOT_EXECUTED', report['kind'], 'rvv_baseline_decode=1')


if __name__ == '__main__':
    main()
