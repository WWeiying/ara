#!/usr/bin/env python3
"""Freeze and execute the bounded host-VCS cluster protocol gate, never synthesis."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SIGNOFF = Path('/home/wangwy/openproject/ara_dsa_signoff_integration')
EXPECTED = [
    'id=1 reset=0 error=0 writes=16 flags=31',
    'id=2 reset=0 error=0 writes=64 flags=31',
    'id=3 reset=0 error=0 writes=4 flags=31',
    'id=4 reset=0 error=0 writes=2 flags=31',
    'id=5 reset=0 error=1 writes=0 flags=0',
    'id=6 reset=0 error=1 writes=0 flags=0',
    'id=7 reset=0 error=1 writes=0 flags=0',
    'id=8 reset=1', 'id=9 reset=1',
    'id=10 reset=0 error=0 writes=16 flags=31',
]
NEGATIVE = {'BAD_PENDING': 'duplicate/incorrect accepted write',
            'BAD_FLAGS': 'incorrect terminal flags/error',
            'BAD_COMPLETE': 'premature complete before final ack'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for path, digest in pins.items():
        if sha(path) != digest:
            raise RuntimeError('Pinned source/image drift: ' + path)
    return pins


def check_positive(log):
    if re.search(r'(?mi)^(Error-|Error:|Fatal:|FATAL|Assertion failed)', log):
        raise ValueError('Simulator error')
    if re.findall(r'^PV_CLUSTER_CASE_PASS (.*)$', log, re.M) != EXPECTED:
        raise ValueError('Missing/duplicate/incorrect case records')
    totals = re.findall(r'^PV_CLUSTER_PASS (.*)$', log, re.M)
    if len(totals) != 1:
        raise ValueError('Missing/duplicate final PASS')
    pairs = re.findall(r'(\w+)=(\d+)', totals[0])
    counts = {key: int(value) for key, value in pairs}
    required = {'cases', 'terminals', 'late', 'same', 'excess', 'stalls', 'cancel',
                'rejected', 'max16', 'pending_cancel', 'skew', 'done_stall',
                'resets', 'early', 'trailing'}
    if (set(counts) != required or len(pairs) != len(required) or
            counts['cases'] != 10 or counts['terminals'] != 8 or
            counts['resets'] != 2 or min(counts.values()) <= 0):
        raise ValueError('Missing required protocol exercise')
    return counts


def check_negative(rc, log, name):
    # Host VCS may return zero for $fatal. Match the precise TB checker failure.
    site = (r'^Fatal: "[^"\n]*/tb\.sv", \d+: resident_pv_cluster_tb[^:\n]*: '
            r'at time [^\n]+\n' + re.escape(NEGATIVE[name]) + r'$')
    if (rc not in (0, 1) or len(re.findall(site, log, re.M)) != 1 or
            len(re.findall(r'^Fatal:', log, re.M)) != 1 or 'PV_CLUSTER_PASS' in log):
        raise ValueError('Checker self-test missed exact failure: ' + name)


def execute(argv, cwd, log, seconds):
    with log.open('x') as stream:
        rc = subprocess.run(['timeout', '--signal=TERM', '--kill-after=5s',
                             str(seconds), *argv], cwd=cwd,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                            stdout=stream, stderr=subprocess.STDOUT).returncode
    return rc, log.read_text(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != (SIGNOFF / 'verification/out').resolve():
        parser.error('Output must be a NEW direct child of signoff verification/out')
    vcs = shutil.which('vcs')
    if not vcs:
        parser.error('Host VCS required on PATH')
    out.mkdir(exist_ok=False)
    report = dict(state='FAIL', scope='PROTOCOL ONLY; XOR responder, NOT numerical verification',
                  simulator='host VCS', synthesis=False, production_final_ack=False)
    try:
        sources = sorted(HERE.glob('*.sv')) + sorted(HERE.glob('*.py')) + [HERE / 'README.md']
        sources += [HERE.parent / 'pv_unit/akv_resident_pv_lane.sv',
                    HERE.parent / 'pv_group/akv_resident_pv_group.sv',
                    HERE.parent / 'pv_transport/resident_payload_fanout.sv', ROOT / 'AGENTS.md']
        pins = {}
        for source in sources:
            dest = out / 'inputs' / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            pins[str(source)] = sha(source)
            shutil.copyfile(source, dest)
            if sha(dest) != pins[str(source)]:
                raise RuntimeError('Snapshot race: ' + str(source))
            dest.chmod(0o444)
            pins[str(dest)] = sha(dest)
        pins[str(Path(vcs).resolve())] = sha(vcs)
        save(out / 'source-pins.json', verify(pins))
        save(out / 'source-pins-before.json', verify(pins))
        branch = subprocess.check_output(['git', '-C', str(SIGNOFF), 'branch', '--show-current'], text=True).strip()
        if branch != 'ara_dsa_signoff_integration':
            raise RuntimeError('Wrong signoff branch')
        save(out / 'provenance.json', dict(source_root=str(ROOT), signoff_branch=branch,
             source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
             compile_bound_seconds=120, per_simulation_bound_seconds=20, vcs=vcs))
        frozen = out / 'inputs' / HERE.parent.relative_to(ROOT)
        build = out / 'build'
        build.mkdir()
        argv = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-top',
                'resident_pv_cluster_tb', '-o', 'simv'] + [str(frozen / name) for name in (
                    'pv_unit/akv_resident_pv_lane.sv', 'pv_group/akv_resident_pv_group.sv',
                    'pv_transport/resident_payload_fanout.sv',
                    'pv_cluster/akv_resident_pv_cluster.sv', 'pv_cluster/tb.sv')]
        save(out / 'compile-command.json', argv)
        print('PV_CLUSTER_COMPILING ' + str(out), flush=True)
        rc, log = execute(argv, build, out / 'compile.log', 120)
        if rc or re.search(r'(?m)^(Error-|Error:|Fatal:)', log):
            raise RuntimeError(f'Compile failed rc={rc}')
        image = build / 'simv'
        image_pins = {str(image): sha(image)}
        image_pins.update({str(p): sha(p) for p in (build / 'simv.daidir').rglob('*') if p.is_file()})
        save(out / 'image-pins.json', image_pins)
        for name in ['directed', *NEGATIVE]:
            verify(pins); verify(image_pins)
            work = out / name
            work.mkdir()
            argv = [str(image), '-no_save'] + ([] if name == 'directed' else ['+' + name])
            save(work / 'command.json', argv)
            print('PV_CLUSTER_RUNNING ' + name, flush=True)
            rc, log = execute(argv, work, work / 'run.log', 20)
            save(work / 'exit.json', dict(returncode=rc))
            if name == 'directed':
                if rc:
                    raise RuntimeError(f'Simulation failed rc={rc}')
                report['counts'] = check_positive(log)
            else:
                check_negative(rc, log, name)
                report[name] = 'EXPECTED_CHECKER_FAILURE_PASS'
            verify(pins); verify(image_pins)
        save(out / 'source-pins-after.json', verify(pins))
        save(out / 'image-pins-after.json', verify(image_pins))
        report['state'] = 'PASS'
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*.log')}
    save(out / 'report.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
