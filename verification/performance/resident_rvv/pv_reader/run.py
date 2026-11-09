#!/usr/bin/env python3
"""Bounded host-VCS gate for the reader and admitted, unmodified AKV context."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ACCEPTED = OUT / 'resident_pv_vmfpu_20261108_04'
FROZEN = OUT / 'chain_soc_20261107_01/source'
SOURCES = (
    'hardware/deps/tech_cells_generic/src/rtl/tc_sram.sv',
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/include/rvv_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/include/akv_pkg.sv',
    'hardware/src/vlsu/akv/akv_v2_context.sv',
)
LOCAL = ('run.py', 'tb.sv', 'README.md', 'test_run.py', 'akv_resident_pv_reader.sv')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, expected in pins.items():
        if sha(name) != expected:
            raise ValueError('Input identity drift: ' + name)


def collect_artifacts(out, pins):
    # Service stdout can still be changing as the report is written. Only
    # closed gate-owned logs/receipts and explicitly pinned snapshots belong here.
    paths = {Path(p) for p in pins if Path(p).is_relative_to(out/'inputs')}
    paths.update(out/name for name in (
        'source-pins.json', 'image-pins.json', 'source-selection.json',
        'commands.json', 'tests.log', 'compile.log', 'run.log'))
    return {str(p): sha(p) for p in sorted(paths) if p.is_file()}


def select_sources(filelist, pins, frozen=FROZEN):
    """Keep only this same frozen context/package closure, in admitted order."""
    selected, defines = [], []
    wanted = {str(frozen / p) for p in SOURCES}
    for raw in filelist.splitlines():
        line = raw.strip()
        if line in wanted:
            if line not in pins:
                raise ValueError('Unpinned selected source: ' + line)
            if line in selected:
                raise ValueError('Duplicate selected source: ' + line)
            selected.append(line)
        elif line.startswith('+define+') and line not in defines:
            # VCS is the host engine. This unused legacy target flag is excluded.
            if line != '+define+TARGET_VERILATOR':
                defines.append(line)
        elif line and not line.startswith(('/', '+incdir+', '+define+')):
            raise ValueError('Unsupported admitted file-list entry: ' + line)
    if set(selected) != wanted:
        raise ValueError('Missing same-frozen compiler sources: ' + str(wanted-set(selected)))
    if any('SYNTHESIS' == d.removeprefix('+define+') or 'TARGET_SRAM_MC' in d for d in defines):
        raise ValueError('Assertions/real generic SRAM must remain enabled')
    return selected, defines


def fields(text):
    pairs = re.findall(r'(\w+)=(\d+)', text)
    result = {k: int(v) for k, v in pairs}
    if len(result) != len(pairs) or ' '.join(f'{k}={v}' for k, v in pairs) != text:
        raise ValueError('Malformed coverage fields')
    return result


def check_log(log):
    if re.search(r'(?im)^\s*(?:Error|Fatal|Warning-\[|\$fatal|Assertion.*fail)', log):
        raise ValueError('Simulator error/assertion diagnostic')
    summaries = re.findall(r'^READER_PASS (.+)$', log, re.M)
    if len(summaries) != 1:
        raise ValueError('Missing/duplicate reader completion')
    totals = fields(summaries[0])
    expected_shapes = Counter((t, w, s) for t in (1, 9, 64) for w in (4, 6, 8) for s in (0, 1))
    expected_shapes.update((9, w, 1) for w in (4, 6, 8))
    shapes = []
    for match in re.findall(r'^READER_SHAPE_PASS (.+)$', log, re.M):
        row = fields(match)
        if set(row) != {'tokens', 'words', 'stalls', 'coefficients', 'values', 'reads'}:
            raise ValueError('Malformed shape receipt')
        if row['coefficients'] != row['tokens'] or row['values'] != row['tokens']*row['words'] or row['reads'] != row['values']:
            raise ValueError('Shape accepted-order/count mismatch')
        shapes.append(row)
    if Counter((r['tokens'], r['words'], r['stalls']) for r in shapes) != expected_shapes:
        raise ValueError('Missing/duplicate shape/reuse coverage')
    cancellations = [fields(x) for x in re.findall(r'^READER_CANCEL_PASS (.+)$', log, re.M)]
    if sorted(cancellations, key=lambda x: x.get('words', -1)) != [
            dict(words=w, reads=1, delivered=0) for w in (4, 6, 8)]:
        raise ValueError('Cancel not proven with a read outstanding')
    exact = dict(cases=40, good=21, invalid=16, cancelled=3, writes=2048,
                 reads=2829, values=2826, coefficients=474, latency=2829, max_credit=2)
    positive = ('coefficient_stalls', 'value_stalls', 'full_credit', 'busy_rejects',
                'held_done', 'final_stalls')
    if set(totals) != set(exact) | set(positive):
        raise ValueError('Malformed gate coverage')
    for key, value in exact.items():
        if totals[key] != value:
            raise ValueError('Incorrect total ' + key)
    if any(totals[k] <= 0 for k in positive) or totals['held_done'] < 6*40:
        raise ValueError('Missing protocol coverage')
    return dict(totals=totals, shapes=shapes, cancellations=cancellations,
                measured_read_latency_cycles=1)


def command(argv, cwd, log, deadline):
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        raise TimeoutError('Gate wall-time budget exhausted')
    with Path(log).open('x') as stream:
        proc = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                start_new_session=True)
        try:
            rc = proc.wait(timeout=remaining)
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
    text = Path(log).read_text(errors='replace')
    if rc:
        raise ValueError(f'Command exited {rc}: {argv[0]}; see {log}')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(OUT) or out == OUT:
        parser.error('Use a fresh signoff verification/out subdirectory')
    out.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic()+540
    pins, image = {}, {}
    report = dict(state='FAIL', scope='Raw V reader/context transport only; not FP completion, SoC, synthesis, area or FPGA acceptance',
                  wall_time_limit_seconds=540, accepted=str(ACCEPTED))
    try:
        manifest = ACCEPTED/'source-pins.json'
        receipt = ACCEPTED/'report.json'
        admitted_list = ACCEPTED/'inputs/sources.f'
        for p in (manifest, receipt, admitted_list):
            pins[str(p)] = sha(p)
        accepted = json.loads(manifest.read_text())
        admission = json.loads(receipt.read_text())
        if admission.get('state') != 'PASS' or admission.get('post_pins_match') is not True:
            raise ValueError('Predecessor gate not accepted')
        if accepted.get(str(admitted_list)) != sha(admitted_list):
            raise ValueError('Admitted filelist drift')
        selected, defines = select_sources(admitted_list.read_text(), accepted)
        inputs = out/'inputs'
        inputs.mkdir()
        copied = []
        for name in selected:
            source = Path(name)
            pins[name] = accepted[name]
            if sha(source) != pins[name]:
                raise ValueError('Frozen dependency drift: '+name)
            if '`include' in source.read_text():
                raise ValueError('Unexpected header dependency requires explicit pin: '+name)
            dest = inputs/source.relative_to(FROZEN)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            if sha(dest) != pins[name]:
                raise ValueError('Snapshot drift: '+name)
            pins[str(dest)] = pins[name]
            copied.append(str(dest))
        for name in LOCAL:
            source, dest = HERE/name, inputs/name
            pins[str(source)] = sha(source)
            shutil.copyfile(source, dest)
            if sha(dest) != pins[str(source)]:
                raise ValueError('Local snapshot drift: '+name)
            pins[str(dest)] = pins[str(source)]
        filelist = inputs/'sources.f'
        filelist.write_text('\n'.join(defines+copied+[str(inputs/'akv_resident_pv_reader.sv'), str(inputs/'tb.sv')])+'\n')
        pins[str(filelist)] = sha(filelist)
        save(out/'source-selection.json', dict(selected=selected, frozen=str(FROZEN),
             defines=defines, omitted_legacy_define='TARGET_VERILATOR',
             headers=[], top='resident_pv_reader_tb', modified_production_rtl=[]))
        save(out/'source-pins.json', pins)
        verify(pins)
        if args.prepare_only:
            report['state'] = 'PREPARED_NOT_EXECUTED'
        else:
            vcs = shutil.which('vcs')
            if not vcs:
                raise ValueError('Host VCS unavailable')
            work = out/'work'
            work.mkdir()
            unit = [sys.executable, '-B', '-m', 'unittest', '-v', 'test_run.py']
            compile_cmd = [vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                           '-top', 'resident_pv_reader_tb', '+define+SIMULATION',
                           '-f', str(filelist), '-o', 'simv']
            run_cmd = [str(work/'simv'), '-no_save']
            save(out/'commands.json', dict(tests=unit, compile=compile_cmd, run=run_cmd))
            command(unit, inputs, out/'tests.log', deadline)
            print('READER_COMPILING', flush=True)
            command(compile_cmd, work, out/'compile.log', deadline)
            verify(pins)
            image = {str(p): sha(p) for p in work.rglob('*') if p.is_file()}
            save(out/'image-pins.json', image)
            print('READER_RUNNING', flush=True)
            checked = check_log(command(run_cmd, work, out/'run.log', deadline))
            verify(pins)
            verify(image)
            report.update(checked, state='PASS', post_image_match=True)
        verify(pins)
        report['post_pins_match'] = True
    except Exception as exc:
        report.update(state='FAIL', error=str(exc))
        print('READER_FAIL '+str(exc), flush=True)
    report['artifacts'] = collect_artifacts(out, pins)
    save(out/'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('artifacts', 'shapes')}), flush=True)
    return int(report['state'] == 'FAIL')


if __name__ == '__main__':
    raise SystemExit(main())
