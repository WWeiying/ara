#!/usr/bin/env python3
"""Build an opposite-owner read-fault fixture using sealed handoff startup/tools."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_handoff import baseline, s, ROOT


def build(base, out):
    base, out = base.resolve(strict=True), out.resolve()
    original, pins = baseline.checked_build(base)
    commands = s.read_json(base / 'commands.json')
    old_main = str(HERE.parent / 'reader_handoff/main.c')
    templates = [r['argv'] for r in commands if '-c' in r['argv'] and old_main in r['argv']]
    links = [r['argv'] for r in commands if '-nostdlib' in r['argv']]
    s.require(len(templates) == len(links) == 1, 'Ambiguous sealed compiler/linker template')
    own = [Path(__file__), HERE / 'fault_main.c', HERE / 'fault_probe.S']
    s.merge_pins(pins, s.hashes(own))
    s.verify_pins(pins)
    out.mkdir(parents=True, exist_ok=False)
    performed = []

    def execute(command, label):
        performed.append(dict(argv=list(map(str, command)), cwd=str(out)))
        s.atomic_json(out / 'commands.json', performed)
        with (out / (label + '.log')).open('x') as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)
        return (out / (label + '.log')).read_text()

    objects = []
    for name, source in (('fault_main', own[1]), ('fault_probe', own[2])):
        command = list(templates[0])
        command[command.index(old_main)] = str(source)
        target = out / (name + '.o')
        command[command.index('-o') + 1] = str(target)
        skip = {command.index('-c'), command.index('-o'), command.index('-o') + 1}
        deps = execute([a for i, a in enumerate(command) if i not in skip] + ['-M', '-MT', 'object'],
                       'deps-' + name)
        s.merge_pins(pins, s.hashes(Path(p).resolve(strict=True) for p in
            shlex.split(deps.replace('\\\n', ' ').split(':', 1)[1])))
        s.verify_pins(pins)
        execute(command, 'compile-' + name)
        objects.append(target)
    elf = out / 'reader_fault.elf'
    link = list(links[0])
    s.require(link.count(str(base / 'fixture-0.o')) == 1 and
              link.count(str(base / 'fixture-1.o')) == 1, 'Wrong sealed fixture objects')
    link[link.index(str(base / 'fixture-0.o'))] = str(objects[0])
    link.insert(link.index('-Wl,--gc-sections'), str(objects[1]))
    link[link.index('-o') + 1] = str(elf)
    link = ['-Wl,-Map=' + str(out / 'link.map') if a.startswith('-Wl,-Map=') else a for a in link]
    execute(link, 'link')
    objdump = Path(templates[0][0]).with_name('riscv64-unknown-elf-objdump')
    assembly = execute([str(objdump), '-d', str(elf)], 'disassembly')
    for name in ('main', 'rf_qbs_only', 'rh_akv_full', 'rh_trap_handler'):
        s.require('<' + name + '>:' in assembly, 'Missing live function ' + name)
    s.require('<archived_main>:' not in assembly and 'qbs_ref_execute' not in assembly,
              'Archived or scalar-reference program retained')
    wrapper = assembly.split('<rh_akv_full>:', 1)[1].split('\n\n', 1)[0].strip().splitlines()
    s.require(len(wrapper) == 4 and 'li\ta1,0' in wrapper[0] and
              'fence' in wrapper[1] and '00b5605b' in wrapper[2],
              'Trap-PC formula no longer matches the sealed four-byte wrapper')
    execute(['bash', str(ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'),
             str(Path(original['simv']).parent), str(elf)], 'image-contract')
    s.merge_pins(pins, s.hashes([objdump, objdump.resolve()]))
    s.verify_pins(pins)
    s.atomic_json(out / 'source-pins.json', pins)
    s.atomic_json(out / 'build.json', dict(state='READER_FAULT_BUILT_NOT_EXECUTED',
        elf=str(elf), elf_sha256=s.digest(elf), qbs_commands=3, akv_commands=11,
        expected_traps=1, trap_owner='akv', predecessor=str(base),
        source_pins_sha256=s.digest(out / 'source-pins.json'), post_pins_match=True,
        artifact_pins=s.hashes(p for p in out.iterdir() if p.is_file())))
    print('READER_FAULT_BUILT_NOT_EXECUTED qbs=3 akv=11')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.output)
