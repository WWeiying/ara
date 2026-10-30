#!/usr/bin/env python3
"""Two bounded original-image runs to discriminate dead-vector-read X spills."""
import argparse
from pathlib import Path
import re
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
    report = s.read_json(base/'build.json')
    pins = s.read_json(base/'source-pins.json')
    s.require(s.digest(base/'source-pins.json') == report['source_pins_sha256'], 'Base pins drift')
    s.merge_pins(pins, report['artifact_sha256'])
    s.merge_pins(pins, s.hashes([Path(__file__), HERE/'drain_probe.c', base/'build.json', base/'source-pins.json']))
    image, accepted = s.checked_image(ROOT/'verification/out/qbacc-soc-accept-20261023-02', Path(report['simv']))
    s.require(image == report['accepted_image_pins'], 'Image drift')
    s.merge_pins(pins, accepted)
    s.verify_pins(pins)
    old_commands = s.read_json(base/'commands.json')
    compiler = next(r['argv'] for r in old_commands if '-c' in r['argv'] and str(HERE/'rvv_qbs_main.c') in r['argv'])
    linker = next(r['argv'] for r in old_commands if '-nostdlib' in r['argv'])
    rows = []
    for safe in (0, 1):
        work = out/str(safe)
        work.mkdir()
        commands = []
        def execute(argv, label, timeout=180):
            argv = list(map(str, argv))
            commands.append(dict(argv=argv, cwd=str(work)))
            s.atomic_json(work/'commands.json', commands)
            with (work/(label+'.log')).open('x') as log:
                subprocess.run(argv, cwd=work, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=timeout)
            return (work/(label+'.log')).read_text()
        compile_command = [str(HERE/'drain_probe.c') if x == str(HERE/'rvv_qbs_main.c') else x for x in compiler]
        compile_command.insert(1, '-DPROBE_SAFE_DRAIN='+str(safe))
        compile_command[compile_command.index('-o')+1] = str(work/'main.o')
        execute(compile_command, 'compile')
        elf = work/'probe.elf'
        link = [str(work/'main.o') if x == str(base/'0.o') else
                '-Wl,-Map='+str(work/'link.map') if x == '-Wl,-Map='+str(base/'link.map') else x
                for x in linker if x != str(base/'3.o')]
        link[link.index('-o')+1] = str(elf)
        execute(link, 'link')
        execute([Path(compile_command[0]).with_name('riscv64-unknown-elf-objdump'), '-d', elf], 'disassembly')
        log = execute([report['simv'], '-no_save', '+PRELOAD='+str(elf), '+TESTCASE=quant_drain_probe',
                       '+NO_FSDB', '+NO_INSTR_TRACE'], 'simulation')
        found = re.findall(r'^QUANT_DRAIN_PROBE safe=([01]) hash=([0-9a-f]{8})$', log, re.M)
        s.require(len(found) == 1 and int(found[0][0]) == safe and
                  'Core Test *** SUCCESS *** (tohost = 0)' in log, 'Incomplete probe execution')
        rows.append(dict(safe=safe, hash=found[0][1],
            invalid_write_failures=len(re.findall(r'a_invalid_write_data: started at .* failed at', log)),
            evidence_sha256=s.hashes([elf, work/'simulation.log', work/'disassembly.log', work/'commands.json'])))
    s.verify_pins(pins)
    s.require(rows[0]['hash'] == rows[1]['hash'], 'Query quantization output changed')
    s.atomic_json(out/'source-pins.json', pins)
    s.atomic_json(out/'result.json', dict(state='DISCRIMINATING_PROBE_COMPLETED', runs=rows,
        post_pins_match=True, source_pins_sha256=s.digest(out/'source-pins.json'),
        hypothesis_supported=rows[0]['invalid_write_failures'] > 0 and rows[1]['invalid_write_failures'] == 0,
        scope='Test-helper dead read/printf spill only; not whole batch or hardware acceptance'))
    print(rows)


if __name__ == '__main__':
    main()
