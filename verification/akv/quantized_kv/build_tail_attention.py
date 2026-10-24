#!/usr/bin/env python3
"""Build a correctness-only RTL tail probe from sealed physical-cache inputs."""
import argparse
import importlib.util
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE / 'tail_native'))
import prepare_tail_gold as gold_tools
from run_strided_attention import checked_build, s


def checked_gold(path, kind):
    result = s.read_json(path / 'result.json')
    s.require(result.get('state') == 'PASS' and result.get('post_pins_match') is True and
              result.get('native_execution') is False and result.get('graphs') == 6 and
              result.get('rtl_performance') is False, 'Independent host graph gold not accepted')
    s.require(s.digest(path / 'source-pins.json') == result['source_pins_sha256'], 'Gold source receipt drift')
    pins = s.read_json(path / 'source-pins.json')
    s.merge_pins(pins, result['artifact_sha256'])
    s.merge_pins(pins, s.hashes([path / 'result.json', path / 'source-pins.json']))
    s.verify_pins(pins)
    errors = gold_tools.parse_reference((path / ('reference-' + kind + '.log')).read_text(), kind)
    s.require(errors['128'] == result['baseline128'][kind]['capture_max_abs'] == 0,
              'Host reference does not reproduce the original full-prefix capture')
    records = {}
    for visible in (5, 33):
        record = result['outputs'][kind][str(visible)]
        file = Path(record['path']).resolve(strict=True)
        s.require(file.is_relative_to(path) and gold_tools.output_record(file, kind, visible) == record and
                  pins.get(str(file)) == record['sha256'], 'Gold coordinates/bytes/provenance mismatch')
        records[visible] = record
    return records, pins


def build(base, gold, output):
    base, gold, out = base.resolve(strict=True), gold.resolve(strict=True), output.resolve()
    s.require(not out.is_relative_to(base) and not out.is_relative_to(gold), 'Independent fresh output required')
    report, pins = checked_build(base)
    records, prior = checked_gold(gold, report['kind'])
    s.merge_pins(pins, prior)
    source = HERE / 'attention_tail_main.c'
    previous = str(HERE / 'attention_strided_main.c')
    commands = s.read_json(base / 'commands.json')
    choices = [r['argv'] for r in commands if '-c' in r['argv'] and previous in r['argv']]
    links = [r['argv'] for r in commands if '-nostdlib' in r['argv']]
    s.require(len(choices) == len(links) == 1, 'Ambiguous predecessor commands')
    template, link = list(choices[0]), list(links[0])
    s.require(template.count(previous) == 1 and '-ffp-contract=fast' in template and
              '-fno-fast-math' in template and '-Werror' in template and
              link.count(str(base / 'main.o')) == 1, 'Compile/link policy differs')
    own = [Path(__file__), source, HERE / 'test_tail_attention_build.py', gold_tools.HERE / 'prepare_tail_gold.py']
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name:
            path = Path(name).resolve()
            if path.is_relative_to(ROOT) and path.is_file():
                own.append(path)
    s.merge_pins(pins, s.hashes(own))
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    performed = []

    def execute(argv, label):
        argv = list(map(str, argv))
        performed.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out / 'commands.json', performed)
        with (out / (label + '.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out / (label + '.log')).read_text()

    try:
        assembly = out / 'tail-gold.S'
        assembly.write_text('.section .rodata,"a",@progbits\n' + ''.join(
            f'.balign 64\n.global attention_tail_gold_{visible}\nattention_tail_gold_{visible}:\n'
            f'.incbin "{records[visible]["path"]}"\n' for visible in (5, 33)))
        s.merge_pins(pins, s.hashes([assembly]))
        objects = []
        for file, name in ((source, 'main'), (assembly, 'tail-gold')):
            command = list(template)
            command[command.index(previous)] = str(file)
            target = out / (name + '.o')
            command[command.index('-o') + 1] = str(target)
            skip = {command.index('-c'), command.index('-o'), command.index('-o') + 1}
            deps = execute([arg for i, arg in enumerate(command) if i not in skip] + ['-M', '-MT', 'object'], 'deps-' + name)
            s.merge_pins(pins, s.hashes(Path(arg).resolve(strict=True) for arg in
                shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])))
            s.verify_pins(pins)
            execute(command, 'compile-' + name)
            objects.append(target)
        elf = out / 'tail_attention.elf'
        link = [str(objects[0]) if arg == str(base / 'main.o') else
                '-Wl,-Map=' + str(out / 'link.map') if arg.startswith('-Wl,-Map=') else arg for arg in link]
        link[link.index('-o') + 1] = str(elf)
        link.insert(link.index('-Wl,--gc-sections'), str(objects[1]))
        execute(link, 'link')
        disassembly = execute([Path(template[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        for name in ('main', 'tail_execute', 'akv_quant_strided_execute', 'tail_value_decode',
                     'ggml_vec_dot_q4_0_q8_0', 'ggml_vec_dot_q8_0_q8_0', 'qbs_native_execute_command'):
            s.require('<' + name + '>:' in disassembly, 'Required implementation missing: ' + name)
        for name in ('qbs_ref_execute', 'archived_main', 'strided_value_decode', 'dequantize_row_q8_0'):
            s.require('<' + name + '>:' not in disassembly, 'Reference or old main/decoder retained')
        decoder = disassembly.split('<tail_value_decode>:', 1)[1].split('\n\n', 1)[0]
        for op in ('vle8.v', 'vsext.vf4', 'vfcvt.f.x.v', 'vfmul.vf', 'vse32.v'):
            s.require(op in decoder, 'Missing real RVV decoder: ' + op)
        helper = ROOT / 'verification/akv/refill_overlap_probe/build.py'
        spec = importlib.util.spec_from_file_location('tail_elf_sections', helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sections = module.alloc_sections(elf)
        s.require(sections and min(row['address'] for row in sections) >= 0x80000000 and
                  max(row['address'] + row['bytes'] for row in sections) < 0x81000000 - 65536, 'ELF bounds')
        execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                 Path(report['simv']).parent, elf], 'image-contract')
        s.require(s.hashes(s.image_files(Path(report['simv']))) == report['accepted_image_pins'], 'Image drift')
        s.merge_pins(pins, s.hashes([helper]))
        s.verify_pins(pins)
        s.atomic_json(out / 'source-pins.json', pins)
        updated = dict(report)
        updated.update(state='TAIL_ENTRY_BUILT_NOT_EXECUTED', execution='NOT_RUN', elf=str(elf),
                       elf_sha256=s.digest(elf), sections=sections, prefixes=[5, 33], trials=6,
                       expected_commands=12, native_calls=4, outputs_per_trial=768,
                       independent_gold=records, gold_directory=str(gold), mapping_timed=False,
                       admission_timed=False, gather_timed=False, performance=False,
                       predecessor_strided_build=str(base),
                       scope='Full selected six-head Attention at visible5 and33; strided cache, independent host GGML gold, exact QBS score replay; correctness only',
                       source_pins_sha256=s.digest(out / 'source-pins.json'), post_pins_match=True,
                       artifact_sha256=s.hashes(path for path in out.iterdir() if path.is_file()))
        s.atomic_json(out / 'build.json', updated)
        print('TAIL_ENTRY_BUILT_NOT_EXECUTED', report['kind'], 'commands=12')
    except BaseException as exc:
        s.atomic_json(out / 'build.json', dict(state='FAIL', execution='NOT_RUN', error=repr(exc)))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base', 'gold', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.gold, args.output)


if __name__ == '__main__':
    main()
