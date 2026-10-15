#!/usr/bin/env python3
"""Pinned real-MASKU VCS port test; no other RTL is elaborated or injected."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--expect-bug', action='store_true')
    parser.add_argument('--regression', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        parser.error('Output must remain in the owned gather directory')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def snapshot(path):
        data = (ROOT / path).read_bytes()
        dest = out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest()
        return str(dest)

    files = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
             'hardware/deps/axi/src/axi_pkg.sv',
             'hardware/deps/cva6/core/include/config_pkg.sv',
             'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
             'hardware/deps/cva6/core/include/riscv_pkg.sv',
             'hardware/include/rvv_pkg.sv',
             'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    files += [f'hardware/deps/common_cells/src/{name}.sv' for name in
              ['spill_register_flushable', 'spill_register', 'lzc',
               'popcount', 'delta_counter', 'fifo_v3']]
    files += ['hardware/src/masku/masku_operands.sv', 'hardware/src/masku/masku.sv',
              str((HERE / 'gather_prestart_tb.sv').relative_to(ROOT))]
    sources = [snapshot(path) for path in files]
    for directory in ['hardware/include/ara', 'hardware/deps/common_cells/include/common_cells']:
        for path in sorted((ROOT / directory).glob('*.svh')):
            snapshot(str(path.relative_to(ROOT)))
    snapshot(str(Path(__file__).resolve().relative_to(ROOT)))
    (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    vcs = '/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1'
    env = dict(os.environ, VCS_HOME=vcs, SNPSLMD_LICENSE_FILE='27000@t7920')
    env['PATH'] = vcs + '/bin:' + env['PATH']
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
               '-top', 'gather_prestart_tb',
               '+incdir+' + str(out / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'hardware/include'), *sources,
               '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    cases = [('historical', [])]
    if args.regression:
        cases += [('start0', ['+START=0']), ('unmasked', ['+MASKED=0']),
                  ('mask_off', ['+PATTERN=2']),
                  ('empty_body', ['+START=2']),
                  ('out_of_range', ['+INDEX=64']),
                  ('vector_indices', ['+MODE=1', '+VL=19', '+START=17']),
                  ('ei16_indices', ['+MODE=2', '+SEW=2', '+VL=11', '+START=9'])]
        for sew in range(4):
            word = 32 >> sew
            cases.append((f'e{8 << sew}_crossword',
                          [f'+SEW={sew}', f'+VL={word+3}', f'+START={word+1}',
                           '+MODE=1', '+PATTERN=1']))
    status = {'state': 'STARTED', 'cases': []}
    try:
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=240, check=True)
        for name, options in cases:
            command = [str(out / 'simv'), '-no_save', *options]
            if args.expect_bug:
                command.append('+EXPECT_BUG')
            with (out / (name + '.log')).open('w') as log:
                result = subprocess.run(command, cwd=out, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=30)
            lines = (out / (name + '.log')).read_text().splitlines()
            marker = 'GATHER_EXPECTED_BUG_REPRODUCED' if args.expect_bug else 'GATHER_PRESTART_PASS'
            passed = result.returncode == 0 and marker in lines
            status['cases'].append({'name': name, 'command': command, 'passed': passed,
                                    'exit': result.returncode,
                                    'result': [line for line in lines if line.startswith('RESULT')]})
            if not passed:
                break
        status['state'] = ('EXPECTED_BUG_REPRODUCED' if args.expect_bug else 'PASS') if all(
            c['passed'] for c in status['cases']) else 'FAIL'
        for name, digest in pins.items():
            if hashlib.sha256((out / name).read_bytes()).hexdigest() != digest:
                raise RuntimeError('Snapshot drift: ' + name)
    except Exception as exc:
        status.update(state='ERROR', error=repr(exc))
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2))
    return 0 if status['state'] in ['PASS', 'EXPECTED_BUG_REPRODUCED'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
