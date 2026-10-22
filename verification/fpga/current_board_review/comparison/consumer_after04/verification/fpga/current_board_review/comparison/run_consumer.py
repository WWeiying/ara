#!/usr/bin/env python3
"""Snapshot and test real MASKU + masku_operands through their public ports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / 'integration'))
from run import environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--case', action='append', help='select named probe(s) before execution')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    out.mkdir(parents=True, exist_ok=False)
    pins = {}
    def snapshot(path):
        data = (ROOT / path).read_bytes()
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        pins[path] = hashlib.sha256(data).hexdigest()
        return str(target)
    files = ['hardware/deps/common_cells/src/cf_math_pkg.sv', 'hardware/deps/axi/src/axi_pkg.sv',
             'hardware/deps/cva6/core/include/config_pkg.sv',
             'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
             'hardware/deps/cva6/core/include/riscv_pkg.sv', 'hardware/include/rvv_pkg.sv',
             'hardware/deps/fpnew/src/fpnew_pkg.sv', 'hardware/include/ara_pkg.sv']
    files += ['hardware/deps/common_cells/src/' + n + '.sv' for n in
              ('spill_register_flushable', 'spill_register', 'lzc', 'popcount', 'delta_counter', 'fifo_v3')]
    files += ['hardware/src/masku/masku_operands.sv', 'hardware/src/masku/masku.sv',
              str((HERE / 'consumer_tb.sv').relative_to(ROOT))]
    sources = [snapshot(p) for p in files]
    for directory in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells'):
        for path in sorted((ROOT / directory).glob('*.svh')):
            snapshot(str(path.relative_to(ROOT)))
    snapshot(str(Path(__file__).resolve().relative_to(ROOT)))
    (out / 'pins.json').write_text(json.dumps(pins, indent=2) + '\n')
    command = ['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps', '-top', 'consumer_tb',
               '+incdir+' + str(out / 'hardware/deps/common_cells/include'),
               '+incdir+' + str(out / 'hardware/include'), *sources, '-o', str(out / 'simv'),
               '-l', str(out / 'compile.log')]
    (out / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    cases = [('measured_slot2_alloff', []), ('measured_slot2_active', ['+PATTERN=3']),
             ('quiet_payload', ['+NV=-1']),
             ('multiword_unstalled', ['+VL=273', '+NV=261', '+PATTERN=1', '+TRACE_QUEUE']),
             ('multiword_active', ['+VL=273', '+NV=261', '+PATTERN=1', '+STALLS=1', '+TRACE_QUEUE']),
             ('multiword_off', ['+VL=273', '+NV=260', '+PATTERN=1', '+STALLS=1']),
             ('multiword_prefix', ['+VL=273', '+START=262', '+NV=261', '+PATTERN=0', '+STALLS=1']),
             ('full_two_word', ['+VL=512', '+NV=511', '+PATTERN=0', '+STALLS=1'])]
    for sew in (1, 2, 3):
        common = [f'+SEW={sew}', '+STALLS=1']
        cases += [(f'e{8<<sew}_prefix', common + ['+VL=8', '+START=6', '+NV=5', '+PATTERN=0']),
                  (f'e{8<<sew}_tail', common + ['+VL=7', '+NV=7', '+PATTERN=0']),
                  (f'e{8<<sew}_unmasked', common + ['+VL=8', '+NV=5', '+UNMASKED=1']),
                  (f'e{8<<sew}_multislice', common + ['+VL=65', '+NV=61', '+PATTERN=1']),
                  (f'e{8<<sew}_integer', common + ['+VL=65', '+NV=-2', '+PATTERN=1', '+INTEGER=1'])]
    if args.case:
        unknown = set(args.case) - {name for name, _ in cases}
        if unknown:
            raise ValueError('unknown case: ' + repr(unknown))
        cases = [(name, options) for name, options in cases if name in args.case]
    status = dict(state='STARTED', cases=[])
    try:
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(command, cwd=out, env=environment(), stdout=log,
                           stderr=subprocess.STDOUT, timeout=240, check=True)
        for name, options in cases:
            cmd = [str(out / 'simv'), '-no_save', *options]
            with (out / (name + '.log')).open('w') as log:
                result = subprocess.run(cmd, cwd=out, env=environment(), stdout=log,
                                        stderr=subprocess.STDOUT, timeout=20)
            lines = (out / (name + '.log')).read_text().splitlines()
            markers = [x for x in lines if x.startswith('CONSUMER_PASS ')]
            passed = result.returncode == 0 and len(markers) == 1
            status['cases'].append(dict(name=name, command=cmd, passed=passed, exit=result.returncode,
                                        result=markers))
            (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
            print(name, 'PASS' if passed else 'FAIL', flush=True)
            if not passed:
                break
        status['state'] = 'PASS' if len(status['cases']) == len(cases) and all(x['passed'] for x in status['cases']) else 'FAIL'
        for name, digest in pins.items():
            if hashlib.sha256((out / name).read_bytes()).hexdigest() != digest:
                raise ValueError('snapshot drift')
    except Exception as exc:
        status.update(state='ERROR', error=repr(exc))
    (out / 'status.json').write_text(json.dumps(status, indent=2) + '\n')
    print(json.dumps(status, indent=2))
    return status['state'] != 'PASS'


if __name__ == '__main__':
    raise SystemExit(main())
