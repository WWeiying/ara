#!/usr/bin/env python3
"""Bounded subprocess adapter: own three-call oracle, reviewed analysis engine."""
import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as worker

s = worker.s


def analyze(inputs, expected, output):
    s.require(s.digest(inputs) == expected, 'Retirement input manifest drift')
    config = s.read_json(inputs)
    worker.fields(config, dict(schema='quant_hsb_worker_retirement_inputs_v1'), 'retirement manifest')
    pins = config['pins']
    s.verify_pins(pins)
    paths = {k: worker.checked_path(v) for k, v in config['files'].items()}
    s.require(set(paths) == {'elf', 'disassembly', 'log', 'commit', 'vector', 'golden', 'rtl', 'phase_map'},
              'Retirement input roles differ')
    s.require(all(pins.get(str(p)) == s.digest(p) for p in paths.values()), 'Unpinned retirement input')
    helper = worker.checked_path(config['helper'])
    s.require(helper == worker.PHASE/'analysis/analyze.py', 'Wrong retirement helper')
    engine = worker.load('phase_worker_retirement_engine', helper, pins[str(helper)])
    s.require(pins.get(str(engine.CSV_SOURCE)) == s.digest(engine.CSV_SOURCE), 'Unpinned CSV parser')
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).is_file() and Path(name).resolve().is_relative_to(worker.ROOT):
            path = Path(name).resolve()
            s.require(pins.get(str(path)) == s.digest(path), 'Unpinned consumed helper: '+str(path))
    parsed = worker.checker.check_log(paths['log'].read_text(), paths['golden'].read_bytes(), paths['rtl'].read_text())
    calls = [{k: row[k] for k in ('trial', 'mode', 'cycles')} for row in parsed['trials']]
    elf = engine.LinkedELF(paths['elf'].read_bytes())
    instructions = engine.disassembly_map(paths['disassembly'].read_text(), elf)
    # Stream every CSV row from start to EOF. Never slice, sample or limit scalar retirement.
    with paths['commit'].open(newline='') as stream:
        report = engine.analyze(instructions, stream, calls, config['boundary_pcs'],
                                s.read_json(paths['phase_map']))
    s.verify_pins(pins)
    s.require(s.digest(inputs) == expected, 'Retirement manifest post-drift')
    report.update(diagnostic_only=True, scalar_trace_truncated=False,
                  pre_post_pins_match=True, input_manifest_sha256=expected,
                  elf_sha256=pins[str(paths['elf'])], input_pins=pins)
    s.require(not output.exists(), 'Retirement output must be fresh')
    s.atomic_json(output, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--inputs-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    analyze(args.inputs, args.inputs_sha256, args.output)
