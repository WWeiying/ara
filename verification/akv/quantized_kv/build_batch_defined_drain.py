#!/usr/bin/env python3
"""Successor batch ELF: remove only the proven dead-tail-read scalar X spill."""
import argparse
from pathlib import Path
import sys
import subprocess

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'verification/akv/paired_heads'))
import attention_run as s

OLD = '''static void snapshot(uintptr_t *fc, uintptr_t *vc) {
  uintptr_t drain;
  __asm__ volatile("vmv.x.s %0,v12\\nfence rw,rw\\nfrcsr %1\\ncsrr %2,vcsr"
      : "=&r"(drain), "=&r"(*fc), "=&r"(*vc) : : "memory");
  (void)drain;
}'''
NEW = '''static void snapshot(uintptr_t *fc, uintptr_t *vc) {
  __asm__ volatile("vmv.x.s zero,v8\\nfence rw,rw\\nfrcsr %0\\ncsrr %1,vcsr"
      : "=&r"(*fc), "=&r"(*vc) : : "memory");
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = ROOT/'verification/out/akv-quantkv-batch-qk-build-20261024-01'
    report = s.read_json(base/'build.json')
    s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['post_pins_match'] is True and
              report['expected_commands'] == 40, 'Wrong original build')
    s.require(s.digest(base/'source-pins.json') == report['source_pins_sha256'], 'Base receipt drift')
    pins = s.read_json(base/'source-pins.json')
    s.merge_pins(pins, report['artifact_sha256'])
    s.verify_pins(pins)
    probe = ROOT/'verification/out/akv-quantkv-drain-probe-20261024-01'
    proof = s.read_json(probe/'result.json')
    s.require(proof['state'] == 'DISCRIMINATING_PROBE_COMPLETED' and proof['post_pins_match'] is True and
              proof['hypothesis_supported'] is True and
              s.digest(probe/'source-pins.json') == proof['source_pins_sha256'], 'Missing discriminating evidence')
    s.merge_pins(pins, s.read_json(probe/'source-pins.json'))
    for row in proof['runs']:
        s.merge_pins(pins, row['evidence_sha256'])
    source = (HERE/'batch_qk_main.c').read_text()
    s.require(source.count(OLD) == 1, 'Original exact helper differs')
    successor = out/'batch_defined_drain.c'
    successor.write_text(source.replace(OLD, NEW))
    commands = []
    def execute(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(out)))
        s.atomic_json(out/'commands.json', commands)
        with (out/(label+'.log')).open('x') as log:
            subprocess.run(argv, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        return (out/(label+'.log')).read_text()
    previous = s.read_json(base/'commands.json')
    compile_command = list(next(r['argv'] for r in previous if '-c' in r['argv']))
    s.require(compile_command[compile_command.index('-c')+1] == str(HERE/'batch_qk_main.c'), 'Wrong original main')
    compile_command[compile_command.index('-c')+1] = str(successor)
    compile_command[compile_command.index('-o')+1] = str(out/'batch_main.o')
    execute(compile_command, 'compile')
    elf = out/'quantized_kv_batch_qk.elf'
    link = list(next(r['argv'] for r in previous if '-nostdlib' in r['argv']))
    link = [str(out/'batch_main.o') if x == str(base/'batch_main.o') else
            '-Wl,-Map='+str(out/'link.map') if x == '-Wl,-Map='+str(base/'link.map') else x for x in link]
    link[link.index('-o')+1] = str(elf)
    execute(link, 'link')
    text = execute([Path(compile_command[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
    s.require('vmv.x.s\tzero,v8' in text and 'vmv.x.s\ta4,v12' not in text, 'Defined drain not present')
    s.merge_pins(pins, s.hashes([Path(__file__), successor, base/'build.json', base/'source-pins.json',
                               probe/'result.json', probe/'source-pins.json']))
    s.verify_pins(pins)
    s.atomic_json(out/'source-pins.json', pins)
    updated = dict(report)
    updated.update(elf=str(elf), elf_sha256=s.digest(elf), original_build=str(base),
        source_pins_sha256=s.digest(out/'source-pins.json'),
        artifact_sha256=s.hashes(p for p in out.iterdir() if p.is_file()),
        helper_change='Dead vector-tail read no longer enters scalar printf spill; no checker/RTL/data change',
        execution='NOT_RUN', post_pins_match=True)
    # Changed main size requires recomputing allocation bounds, not copying them.
    import importlib.util
    helper = ROOT/'verification/akv/refill_overlap_probe/build.py'
    spec = importlib.util.spec_from_file_location('defined_drain_elf', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    updated['sections'] = module.alloc_sections(elf)
    s.require(max(x['address']+x['bytes'] for x in updated['sections']) < 0x81000000-65536, 'ELF bounds')
    s.atomic_json(out/'build.json', updated)
    print('BUILT_NOT_EXECUTED commands=40 outputs=3336 defined_drain=1')


if __name__ == '__main__':
    main()
