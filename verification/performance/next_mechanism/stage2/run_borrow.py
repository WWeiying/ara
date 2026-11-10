#!/usr/bin/env python3
"""Frozen transport + real EW8/Lat0 multiplier unit, not a VMFPU gate."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from run_product import HEADERS, OUT, PACKAGES, command, save, sha, verify

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOCAL = ('borrow_tb.sv', 'run_borrow.py', 'test_run_borrow.py', 'run_product.py')
SOURCES = (*PACKAGES, 'hardware/src/lane/simd_mul.sv', 'hardware/src/lane/qbs_lane_mul_borrow.sv')


def check_log(text):
    if re.search(r'(?im)(?:fatal|error|assertion failed|timeout)', text):
        raise ValueError('Borrow unit failure')
    matches = re.findall(r'^STAGE2_BORROW_PASS accepted=(\d+) returned=(\d+) flushed=(\d+) '
                         r'blocked=(\d+) withdrawals=(\d+) resets=(\d+) latency=(\d+)$', text, re.M)
    if len(matches) != 1:
        raise ValueError('Missing/duplicate borrow completion')
    accepted, returned, flushed, blocked, withdrawals, resets, latency = map(int, matches[0])
    if accepted != returned + flushed or returned <= 6000 or flushed == 0 or blocked < 80 or (withdrawals, resets, latency) != (6, 4, 3):
        raise ValueError('Borrow unit coverage/accounting')
    return dict(accepted=accepted, returned=returned, flushed=flushed, blocked=blocked,
                withdrawals=withdrawals, resets=resets, latency=latency)


def prepare(out):
    if out.parent != OUT:
        raise ValueError('Use a new direct signoff out child')
    if subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip() != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong signoff worktree')
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('No host VCS')
    out.mkdir(exist_ok=False)
    inputs, pins = out / 'inputs', {}
    for rel in (*SOURCES, *HEADERS, *(str(HERE.relative_to(ROOT) / name) for name in LOCAL)):
        source, target = ROOT / rel, inputs / rel
        digest = sha(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if sha(target) != digest:
            raise ValueError('Copy race: ' + rel)
        pins[str(source)] = pins[str(target)] = digest
    local = inputs / HERE.relative_to(ROOT)
    filelist = inputs / 'sources.f'
    filelist.write_text('+incdir+' + str(inputs / 'hardware/deps/common_cells/include') + '\n' +
                        '\n'.join(str(inputs / p) for p in SOURCES) + '\n' + str(local / 'borrow_tb.sv') + '\n')
    save(out / 'selection.json', dict(vcs=vcs, local=str(local), timeout_seconds=360))
    for p in (filelist, out / 'selection.json', Path(vcs).resolve()):
        pins[str(p)] = sha(p)
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / 'run_borrow.py')))
    print(local / 'run_borrow.py')


def execute(out):
    config = json.loads((out / 'selection.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / 'run_borrow.py':
        raise ValueError('Use the frozen runner')
    pins = json.loads((out / 'source-pins.json').read_text())
    work = out / 'work'
    work.mkdir(exist_ok=False)
    deadline = time.monotonic() + config['timeout_seconds']
    report = dict(state='FAIL', scope='borrow transport + real EW8 Lat0 core only; no VMFPU/mux/clock-gate acceptance')
    try:
        verify(pins)
        command([sys.executable, '-B', str(Path(config['local']) / 'test_run_borrow.py')],
                work, work / 'host-tests.log', deadline)
        compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                       '-top', 'stage2_borrow_tb', '-o', 'simv', '-f', str(out / 'inputs/sources.f')]
        run_cmd = [str(work / 'simv'), '-no_save']
        save(work / 'commands.json', dict(compile=compile_cmd, run=run_cmd))
        print('STAGE2_BORROW_COMPILING', flush=True)
        command(compile_cmd, work, work / 'compile.log', deadline)
        verify(pins)
        image = {str(p): sha(p) for p in (work / 'simv.daidir').rglob('*') if p.is_file()}
        image[str(work / 'simv')] = sha(work / 'simv')
        save(work / 'image-pins.json', image)
        print('STAGE2_BORROW_RUNNING', flush=True)
        command(run_cmd, work, work / 'run.log', deadline)
        report['work'] = check_log((work / 'run.log').read_text())
        verify(pins)
        verify(image)
        save(out / 'source-pins-after.json', pins)
        report.update(state='PASS', post_pins_match=True, post_image_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(p): sha(p) for p in work.glob('*') if p.is_file()}
    save(out / 'report.json', report)
    print('STAGE2_BORROW_' + report['state'] + ' ' + str(out / 'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.execute:
        return execute(out)
    prepare(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
