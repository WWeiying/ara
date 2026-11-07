#!/usr/bin/env python3
"""Bounded silent ISA snapshots, without changing the ELF or raising its budget."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE
from run_decode_rvv_isa import spike_command, SPIKE_SHA, SPIKE
from collect_decode_rvv_build import ELF_SHA, BUILD


def main(output):
    out = output.absolute(); require(out == out.resolve() and out.is_relative_to(RUNS), 'Fresh probe output')
    out.mkdir(parents=True, exist_ok=False)
    prior = RUNS / 'e2e_decode_rvv_isa_20261106_02'
    pins = json.loads((prior / 'source-pins.json').read_text()); verify_pins(pins)
    report = json.loads((prior / 'result.json').read_text()); verify_pins(report['artifacts'])
    require(report['state'] == 'FAIL' and report['error'] == "ValueError('Missing/extra RVV work')",
            'Probe is scoped to incomplete ISA execution only')
    elf, plugin = BUILD / 'decode_rvv.elf', prior / 'spike_soc_ports.so'
    require(digest(elf) == ELF_SHA and digest(SPIKE) == SPIKE_SHA and
            pins.get(str(plugin)) == digest(plugin), 'Exact failing inputs required')
    commands = []
    for count in (500000, 1500000, 2000000):
        commands += [f'rs {count}', 'pc 0', 'reg 0 mepc', 'reg 0 mcause', 'reg 0 mtval', 'reg 0 sp']
    commands += ['q']
    control = out / 'probe.cmd'; control.write_text('\n'.join(commands)+'\n')
    argv = spike_command(plugin, elf); argv[1:1] = ['-d', '--debug-cmd='+str(control)]
    env = {k:v for k,v in os.environ.items() if k not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')}
    env.update(PATH='/usr/bin:/bin', LC_ALL='C')
    for path in (Path(__file__), HERE / 'run_decode_rvv_isa.py', control, prior / 'result.json'):
        pins[str(path)] = digest(path)
    (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    (out / 'command.json').write_text(json.dumps(argv, indent=2)+'\n')
    with (out / 'probe.log').open('xb') as stream:
        p = subprocess.run(argv, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
    verify_pins(pins)
    result = dict(state='ISA_SNAPSHOTS_RECORDED_NOT_ACCEPTANCE', returncode=p.returncode,
        elf_sha256=ELF_SHA, instruction_snapshots=[500000,2000000,4000000], performance_measured=False,
        source_pins_sha256=digest(out / 'source-pins.json'), log_sha256=digest(out / 'probe.log'))
    (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    main(p.parse_args().output)
