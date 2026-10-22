#!/usr/bin/env python3
"""Replay the board MASKU/SLDU reproducer against pinned current RTL."""
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
    parser.add_argument('--expect-starvation', action='store_true')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pins = {}

    def snapshot(path):
        src = ROOT / path
        dst = out / path
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dst.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest()
        return str(dst)

    packages = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
                'hardware/deps/axi/src/axi_pkg.sv',
                'hardware/deps/cva6/core/include/config_pkg.sv',
                'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
                'hardware/deps/cva6/core/include/riscv_pkg.sv',
                'hardware/include/rvv_pkg.sv',
                'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    files = packages + [f'hardware/deps/common_cells/src/{name}.sv' for name in
                        ['spill_register_flushable', 'spill_register', 'lzc',
                         'popcount', 'delta_counter', 'fifo_v3']]
    files += ['hardware/src/sldu/p2_stride_gen.sv', 'hardware/src/sldu/sldu_op_dp.sv',
              'hardware/src/sldu/sldu.sv', 'hardware/src/masku/masku_operands.sv',
              'hardware/src/masku/masku.sv', str((HERE / 'mask_slide_restart_tb.sv').relative_to(ROOT))]
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
               '-top', 'mask_slide_restart_tb',
               '+incdir+' + str(out / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'hardware/include'), *sources,
               '-o', str(out / 'simv'), '-l', str(out / 'compile.log')]
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    status = {'expect_starvation': args.expect_starvation, 'cases': [], 'state': 'STARTED'}
    try:
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=240, check=True)
        for sew, start, down in [(2,0,0),(2,8,0),(3,0,0),(3,4,0),(1,0,1),(1,16,1)]:
            name = f'e{8 << sew}_start{start}_down{down}'
            command = [str(out / 'simv'), '-no_save', f'+SEW={sew}',
                       f'+START={start}', f'+DOWN={down}']
            if args.expect_starvation:
                command += ['+EXPECT_STARVATION']
            with (out / (name + '.log')).open('w') as log:
                result = subprocess.run(command, cwd=out, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=30)
            text = (out / (name + '.log')).read_text()
            passed = result.returncode == 0 and 'MASK_SLIDE_CHECK_PASS' in text
            status['cases'].append({'name': name, 'checked': passed, 'exit': result.returncode,
                                    'result': [line for line in text.splitlines() if line.startswith('RESULT')]})
        status['state'] = ('EXPECTED_BUG_REPRODUCED' if args.expect_starvation else 'PASS') if all(
            c['checked'] for c in status['cases']) else 'FAIL'
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
