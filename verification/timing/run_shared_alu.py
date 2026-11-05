#!/usr/bin/env python3
"""Freeze an ALU miter, then launch matched local DC only after passing tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PACKAGES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/include/ara_pkg.sv',
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def verify(out):
    manifest = json.loads((out/'manifest.json').read_text())
    for name, digest in manifest['hashes'].items():
        if sha(out/name) != digest:
            raise RuntimeError(f'Frozen input changed: {name}')
    return manifest


def launch(out, action):
    stamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    unit = f'shared-alu-{action}-{stamp}'
    subprocess.run(['systemd-run', '--user', '--unit='+unit,
        '--property=StandardOutput=append:'+str(out/(action+'.worker.log')),
        '--property=StandardError=append:'+str(out/(action+'.worker.log')),
        sys.executable, str(out/'worker.py'), str(out), '--worker', action], check=True)
    save(out/(action+'.launch.json'), {'unit': unit, 'action': action})
    print(unit, flush=True)


def command(cmd, cwd, log, marker=None, seconds=900):
    with log.open('w') as stream:
        proc = subprocess.run(['timeout', '--signal=TERM', '--kill-after=30s',
            str(seconds), *cmd], cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    content = log.read_text(errors='replace')
    if proc.returncode or re.search(r'(?m)^(?:Error(?:-|:)|Fatal:)', content):
        raise RuntimeError(f'Command failed: {log} (exit {proc.returncode})')
    if marker and marker not in content:
        raise RuntimeError(f'Missing completion marker: {log}')


def worker(out, action):
    status = {'state': 'RUNNING', 'pid': os.getpid(),
              'started': datetime.now(timezone.utc).isoformat()}
    save(out/(action+'.status.json'), status)
    try:
        manifest = verify(out)
        if action == 'test':
            sources = [str(out/'src'/Path(p).name) for p in PACKAGES]
            sources += [str(out/'src'/n) for n in
                        ('fixed_p_rounding.sv', 'simd_alu.sv', 'reference.sv')]
            tests = [
                ('miter', 'shared_alu_tb', [], 'SHARED_ALU_PASS'),
                ('rounding', 'simd_alu_equivalence_tb', ['+EDGES_ONLY'],
                 'SIMD ALU equivalence PASS')]
            if manifest.get('shift_test'):
                tests.insert(0, ('shift', 'shared_alu_shift_tb', [], 'SHARED_ALU_SHIFT_PASS'))
            for name, top, args, marker in tests:
                d = out/name
                d.mkdir()
                command(['vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
                         '-top', top, '-o', 'simv', *sources,
                         str(out/'src'/(top+'.sv'))], d, d/'compile.log')
                command(['./simv', *args], d, d/'run.log', marker)
        else:
            if json.loads((out/'test.status.json').read_text())['state'] != 'PASS':
                raise RuntimeError('Functional gate not passed')
            d = out/action
            d.mkdir()
            shutil.copytree(out/'src', d/'src')
            if action == 'baseline':
                (d/'src/simd_alu.sv').write_bytes((out/'baseline.sv').read_bytes())
            shutil.copy2(out/'shared_alu_ppa.tcl', d/'shared_alu_ppa.tcl')
            shutil.copy2(out/'library_env.tcl', d/'library_env.tcl')
            command(['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}',
                     '-e', f'HOME={Path.home()}', '-w', str(d),
                     'synopsys_workspace', 'bash', '-lc',
                     'exec dc_shell -f shared_alu_ppa.tcl'], d, d/'dc.log',
                    'SHARED_ALU_PPA_COMPLETE', seconds=7200)
        verify(out)
        status['state'] = 'PASS'
    except Exception as exc:
        status.update(state='FAIL', error=str(exc))
    status['finished'] = datetime.now(timezone.utc).isoformat()
    save(out/(action+'.status.json'), status)
    return 0 if status['state'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reference', default='b69df88f0')
    parser.add_argument('--worker', choices=('test', 'baseline', 'candidate'))
    parser.add_argument('--start-dc', action='store_true')
    parser.add_argument('--shift-test', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.worker:
        return worker(out, args.worker)
    if args.start_dc:
        verify(out)
        if json.loads((out/'test.status.json').read_text())['state'] != 'PASS':
            raise RuntimeError('Functional gate not passed')
        for action in ('baseline', 'candidate'):
            if (out/action).exists() or (out/(action+'.launch.json')).exists():
                raise RuntimeError(f'DC already dispatched: {action}')
        for action in ('baseline', 'candidate'):
            launch(out, action)
        return 0
    out.mkdir(parents=True, exist_ok=False)
    (out/'src').mkdir()
    reference = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
        args.reference], text=True).strip()
    original = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        reference+':hardware/src/lane/simd_alu.sv'], text=True)
    (out/'baseline.sv').write_text(original)
    (out/'src/reference.sv').write_text(re.sub(r'\bsimd_alu\b', 'simd_alu_reference', original))
    for path in PACKAGES + ['hardware/src/lane/fixed_p_rounding.sv',
                            'hardware/src/lane/simd_alu.sv']:
        shutil.copy2(ROOT/path, out/'src'/Path(path).name)
    for name in ('shared_alu_tb.sv', 'simd_alu_equivalence_tb.sv', 'simd_alu_timing.sv'):
        shutil.copy2(HERE/name, out/'src'/name)
    if args.shift_test:
        shutil.copy2(HERE/'shared_alu_shift_tb.sv', out/'src/shared_alu_shift_tb.sv')
    shutil.copy2(HERE/'shared_alu_ppa.tcl', out/'shared_alu_ppa.tcl')
    shutil.copy2(ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env',
                 out/'library_env.tcl')
    shutil.copy2(__file__, out/'worker.py')
    hashes = {str(f.relative_to(out)): sha(f) for f in out.rglob('*') if f.is_file()}
    save(out/'manifest.json', {'reference': reference, 'hashes': hashes,
        'shift_test': args.shift_test,
        'scope': 'local combinational SIMD ALU with registered timing boundary',
        'period_ns': 1.0, 'setup_uncertainty_ns': 0.15,
        'functional_configurations': ['fixed_point_disabled', 'fixed_point_enabled'],
        'synthesis_configuration': 'fixed_point_enabled',
        'not_claimed': ['SoC regression', 'FPGA acceptance', 'measured area benefit']})
    launch(out, 'test')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
