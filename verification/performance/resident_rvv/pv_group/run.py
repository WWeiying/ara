#!/usr/bin/env python3
"""Snapshot and run a bounded host-VCS group protocol gate in signoff output."""
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
OUTPUT_ROOT = SIGNOFF / 'verification/out'
EXPECTED = [(1, 0, 15, 4), (2, 0, 17, 3), (3, 1, 0, 0), (4, 1, 0, 0),
            (5, 1, 0, 0), (6, 1, 0, 0), (7, 1, 0, 0), (8, 1, 0, 0),
            (9, 1, 0, 0), (10, 0, 4, 1)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    drift = [name for name, digest in pins.items() if sha(name) != digest]
    if drift:
        raise RuntimeError('Pinned input/image drift: ' + ', '.join(drift))
    return pins


def check_positive(log):
    if re.search(r'(?m)^(Error-|Error:|Fatal:|FATAL)', log):
        raise ValueError('Simulator reported an error')
    records = [tuple(map(int, row)) for row in re.findall(
        r'^PV_GROUP_CASE_PASS id=(\d+) error=(\d+) flags=(\d+) writes=(\d+)$', log, re.M)]
    if records != EXPECTED:
        raise ValueError('Missing, duplicated or incorrect directed case records')
    totals = re.findall(
        r'^PV_GROUP_PASS cases=(\d+) terminals=(\d+) cycles=(\d+) stalled=(\d+) '
        r'rejected=(\d+) cancel=(\d+) done_stalls=(\d+)$', log, re.M)
    if len(totals) != 1:
        raise ValueError('Missing/duplicate final PASS')
    values = list(map(int, totals[0]))
    if values[:2] != [10, 10] or not 0 < values[2] <= 500 or min(values[3:]) <= 0:
        raise ValueError('Invalid totals or unexercised required handshake conditions')
    return dict(zip(('cases', 'terminals', 'cycles', 'stalled', 'rejected', 'cancel',
                     'done_stalls'), values))


def check_negative(rc, log):
    # This host VCS returns zero for $fatal; require the exact fatal site/message.
    expected = (r'^Fatal: "[^"\n]*/akv_resident_pv_group\.sv", \d+: '
                r'resident_pv_group_tb\.dut(?:\.[A-Za-z0-9_$]+)?: at time [^\n]+\n'
                r'Resident PV group post-authorization lane error$')
    if (rc not in (0, 1) or
        log.count('PV_GROUP_EXPECT_POSTCOMMIT_FATAL writes=1') != 1 or
        len(re.findall(expected, log, re.M)) != 1 or
        len(re.findall(r'^Fatal:', log, re.M)) != 1 or
        'PV_GROUP_PASS' in log or 'MISSING post-authorization' in log):
        raise ValueError('Negative test did not fail at the required assertion')


def run(argv, cwd, log, seconds):
    with log.open('x') as stream:
        result = subprocess.run(
            ['timeout', '--signal=TERM', '--kill-after=5s', str(seconds), *argv],
            cwd=cwd, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
            stdout=stream, stderr=subprocess.STDOUT)
    return result.returncode, log.read_text(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--compile-seconds', type=int, default=120)
    parser.add_argument('--run-seconds', type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.compile_seconds <= 180 or not 1 <= args.run_seconds <= 30:
        parser.error('Bounds: compile 1..180 seconds, each simulation 1..30 seconds')
    out = args.output.resolve()
    if out.parent != OUTPUT_ROOT.resolve():
        parser.error('Use a new direct child of ' + str(OUTPUT_ROOT))
    vcs = shutil.which('vcs')
    if not vcs:
        parser.error('Host VCS is required on PATH')
    out.mkdir(exist_ok=False)
    report = dict(state='FAIL', scope='Direct four-lane protocol only; no arithmetic/SoC/FPGA acceptance',
                  simulator='host VCS', synthesis=False)
    pins = {}
    try:
        inputs = out / 'inputs'
        local = [HERE / name for name in
                 ('akv_resident_pv_group.sv', 'tb.sv', 'run.py', 'test_run.py', 'README.md')]
        references = [HERE.parent / 'pv_unit/akv_resident_pv_lane.sv',
                      HERE.parent / 'pv_vmfpu/SOC_INTEGRATION.md', ROOT / 'AGENTS.md']
        for source in local + references:
            dest = inputs / source.relative_to(ROOT)
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
        save(out / 'provenance.json', dict(
            source_root=str(ROOT),
            source_head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
            signoff_branch=subprocess.check_output(['git', '-C', str(SIGNOFF), 'branch', '--show-current'], text=True).strip(),
            vcs=vcs, compile_seconds=args.compile_seconds, run_seconds=args.run_seconds,
            references_only=[str(p) for p in references]))
        frozen = inputs / HERE.relative_to(ROOT)
        compile_dir = out / 'build'
        compile_dir.mkdir()
        compile_cmd = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
                       '-top', 'resident_pv_group_tb', '-o', 'simv',
                       str(frozen / 'akv_resident_pv_group.sv'), str(frozen / 'tb.sv')]
        save(out / 'compile-command.json', compile_cmd)
        print('PV_GROUP_COMPILING ' + str(out), flush=True)
        rc, log = run(compile_cmd, compile_dir, out / 'compile.log', args.compile_seconds)
        if rc or re.search(r'(?m)^(Error-|Error:|Fatal:)', log):
            raise RuntimeError(f'VCS compile failed rc={rc}')
        verify(pins)
        image = compile_dir / 'simv'
        image_pins = {str(image): sha(image)}
        image_pins.update({str(p): sha(p) for p in (compile_dir / 'simv.daidir').rglob('*')
                           if p.is_file()})
        save(out / 'image-pins.json', image_pins)
        for name, extra in [('directed', []), ('postcommit_error', ['+POSTCOMMIT_ERROR'])]:
            work = out / name
            work.mkdir()
            argv = [str(image), '-no_save', *extra]
            save(work / 'command.json', argv)
            verify(pins); verify(image_pins)
            print('PV_GROUP_RUNNING ' + name, flush=True)
            rc, log = run(argv, work, work / 'run.log', args.run_seconds)
            save(work / 'exit.json', dict(returncode=rc))
            if name == 'directed':
                if rc:
                    raise RuntimeError(f'Directed simulation failed rc={rc}')
                report['directed'] = check_positive(log)
            else:
                check_negative(rc, log)
                report['postcommit_error'] = 'EXPECTED_ASSERTION_PASS'
            verify(pins); verify(image_pins)
        save(out / 'source-pins-after.json', verify(pins))
        save(out / 'image-pins-after.json', verify(image_pins))
        report['state'] = 'PASS'
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in sorted(out.rglob('*'))
                           if p.is_file() and 'inputs' not in p.relative_to(out).parts
                           and 'build' not in p.relative_to(out).parts}
    save(out / 'report.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
