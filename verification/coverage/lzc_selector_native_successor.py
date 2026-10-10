#!/usr/bin/env python3
"""Timing-only successor of the sealed independent selector calibration plan."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

import lzc_selector_native_prepare as frozen
import lzc_selector_native_run as runner

TIMING = '-timescale=1ns/1ps'
ORIGINAL = frozen.OUT / 'lzc_selector_native_prepare-705-20261006-02'


def successor_plan(plan, old, new):
    result = copy.deepcopy(plan)
    for row in result['experiments']:
        row['cwd'] = row['cwd'].replace(str(old), str(new))
        for field in ('compile_argv', 'run_argv'):
            row[field] = [arg.replace(str(old), str(new)) for arg in row[field]]
        row['compile_argv'].insert(3, TIMING)
    return result


def validate_successor(original, successor, old, new):
    frozen.require(len(original['experiments']) == len(successor['experiments']) == 8,
                   'Exactly eight cases required')
    seen = set()
    for before, after in zip(original['experiments'], successor['experiments']):
        key = before['width'], before['selector'], before['parity']
        frozen.require(key not in seen, 'Duplicate input/parameter case')
        seen.add(key)
        normalized = copy.deepcopy(after)
        frozen.require(normalized['compile_argv'].count(TIMING) == 1, 'One default timescale required')
        normalized['compile_argv'].remove(TIMING)
        normalized['cwd'] = normalized['cwd'].replace(str(new), str(old))
        for field in ('compile_argv', 'run_argv'):
            normalized[field] = [arg.replace(str(new), str(old)) for arg in normalized[field]]
        frozen.require(normalized == before, 'Non-timing compile/runtime/input/parameter delta')
    frozen.require(seen == {(w, s, p) for w in (10, 23) for s in (0, 1) for p in (0, 1)},
                   'Missing selector/result parity cross')


def prepare(output):
    frozen.require(output.parent == frozen.OUT and not output.exists(), 'Fresh direct output required')
    binding = json.loads((ORIGINAL / 'binding.json').read_bytes())
    runner.check_pins(binding['pins'])
    original = json.loads((ORIGINAL / 'experiments.json').read_bytes())
    successor = successor_plan(original, ORIGINAL, output)
    validate_successor(original, successor, ORIGINAL, output)
    help_result = subprocess.run(['vcs', '-help'], capture_output=True, text=True, timeout=30)
    frozen.require(help_result.returncode == 0 and '-timescale=<time_unit>/<time_precision>' in
                   help_result.stdout + help_result.stderr, 'VCS option not documented on host')
    output.mkdir()
    frozen.write(output / 'vcs-help.txt', help_result.stdout + help_result.stderr)
    pins = binding['pins']
    for path in (ORIGINAL / 'binding.json', ORIGINAL / 'experiments.json', Path(__file__).resolve(),
                 Path(runner.__file__).resolve(), output / 'vcs-help.txt'):
        pins[str(path)] = frozen.sha(path)
    for before, after in zip(original['experiments'], successor['experiments']):
        old_source = Path(before['cwd']) / (before['top'] + '.sv')
        case = Path(after['cwd'])
        case.mkdir()
        new_source = case / (after['top'] + '.sv')
        frozen.write(new_source, old_source.read_text())
        frozen.require(frozen.sha(old_source) == frozen.sha(new_source), 'Testbench byte drift')
        pins[str(old_source)] = frozen.sha(old_source)
        pins[str(new_source)] = frozen.sha(new_source)
    for path in [frozen.SOURCE.parent / 'cf_math_pkg.sv',
                 *sorted((frozen.SOURCE.parent.parent / 'include').rglob('*.svh'))]:
        pins[str(path)] = frozen.sha(path)
    binding['successor'] = dict(parent=str(ORIGINAL), timing_only=TIMING, input_parameter_delta=False)
    frozen.write(output / 'binding.json', binding)
    frozen.write(output / 'experiments.json', successor)
    frozen.write(output / 'successor-review.json', dict(status='TIMING_ONLY_SUCCESSOR_APPROVED',
                 cases=8, only_compile_option_delta=TIMING, original_source_modified=False,
                 old_processor_exclusions=False, tool_help=str(output / 'vcs-help.txt')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'calibration', 'bind'))
    parser.add_argument('--prepared', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    prepared = args.prepared.absolute()
    if args.stage == 'prepare':
        prepare(prepared)
    else:
        frozen.require(args.output is not None, 'Evidence output required')
        original = json.loads((ORIGINAL / 'experiments.json').read_bytes())
        successor = json.loads((prepared / 'experiments.json').read_bytes())
        validate_successor(original, successor, ORIGINAL, prepared)
        runner.PREPARED = prepared
        if args.stage == 'calibration':
            runner.calibration(args.output.absolute())
        else:
            runner.bind(args.output.absolute())


if __name__ == '__main__':
    main()
