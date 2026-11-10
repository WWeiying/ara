#!/usr/bin/env python3
"""Standalone VCS reader/unified-context gate; preparation requires parent freeze."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = Path('/home/wangwy/openproject/ara_dsa')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ACCEPTED = OUT / 'resident_pv_vmfpu_20261108_04'
READER = OUT / 'resident_pv_reader_gate_20261108_02'
FROZEN = OUT / 'chain_soc_20261107_01/source'
AKV = 'hardware/src/vlsu/akv/'
LOCAL = ('reader_gate.py', 'reader_gate.sv', 'reader_gate_test.py')
CONTEXT = tuple(AKV + n + '.sv' for n in (
    'akv_v2_context', 'akv_legacy_repacker', 'akv_q_store', 'akv_unified_context'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError('Source/image identity drift: ' + name)


def source_selection():
    """Reuse selected accepted bytes only, never traverse local dependency trees."""
    pins = {}
    for root in (ACCEPTED, READER):
        report = json.loads((root/'report.json').read_text())
        if report.get('state') != 'PASS' or report.get('post_pins_match') is not True:
            raise ValueError('Unaccepted predecessor: ' + str(root))
        for name in ('report.json', 'source-pins.json'):
            pins[str(root/name)] = sha(root/name)
    accepted = json.loads((ACCEPTED/'source-pins.json').read_text())
    reader_pins = json.loads((READER/'source-pins.json').read_text())
    filelist = READER/'inputs/sources.f'
    if sha(filelist) != reader_pins[str(filelist)]:
        raise ValueError('Accepted reader filelist drift')
    pins[str(filelist)] = sha(filelist)
    sources, defines = [], []
    for line in filelist.read_text().splitlines():
        if line.startswith('+define+'):
            if line.startswith(('+define+SYNTHESIS', '+define+TARGET_SRAM_MC')):
                raise ValueError('Assertions and real generic SRAM required')
            defines.append(line)
        elif line.startswith(str(READER/'inputs/hardware')+'/'):
            relative = str(Path(line).relative_to(READER/'inputs'))
            sources.append(FROZEN/relative)
    for relative in CONTEXT:
        if FROZEN/relative not in sources:
            sources.append(FROZEN/relative)
    if len(sources) != 14 or any('`include' in p.read_text() for p in sources):
        raise ValueError('Unexpected compilation closure or unpinned includes')
    for source in sources:
        pins[str(source)] = accepted[str(source)]
    verify(pins)
    # These four production modules must still be the admitted implementation.
    for relative in CONTEXT:
        if sha(REPO/relative) != pins[str(FROZEN/relative)]:
            raise ValueError('Production context differs from accepted copy: ' + relative)
    return sources, defines, pins


def expected_cases():
    result = []
    def row(qk, t, h, d, b, s):
        return dict(qk=qk, tokens=t, heads=h, dimensions=d, base=b, skew=s,
                    qreads=d//16*h if qk else 0, columns=d//4 if qk else 0,
                    vreads=0 if qk else t*d//16)
    for s in range(2):
        for d in (64, 96, 128):
            for h in (1, 2):
                for i, t in enumerate((1, 2, 3, 9, 17, 64)):
                    result += [row(0,t,h,d,0,s), row(1,t,h,d,3 if i%2==0 else 8-h,s),
                               row(0,t,h,d,0,s)]
    for _ in range(8):
        result += [row(0,1,1,64,0,1), row(1,17,2,96,3,1)]
    return result


def fields(text):
    pairs = re.findall(r'(\w+)=(\d+)', text)
    if ' '.join(k+'='+v for k, v in pairs) != text or len(dict(pairs)) != len(pairs):
        raise ValueError('Malformed receipt: ' + text)
    return {k: int(v) for k, v in pairs}


def check_log(log):
    if re.search(r'(?im)^\s*(?:Error|Fatal|Warning-\[|\$fatal|Assertion.*fail)', log):
        raise ValueError('Simulator diagnostic')
    cases = [fields(x) for x in re.findall(r'^READER_GATE_CASE (.+)$', log, re.M)]
    if cases != expected_cases():
        raise ValueError('Missing, duplicated, reordered, or incorrect case work ledger')
    interrupts = [fields(x) for x in re.findall(r'^READER_GATE_INTERRUPT (.+)$', log, re.M)]
    if interrupts != [dict(phase=p, reset=r) for r in range(2) for p in range(4)]:
        raise ValueError('Missing interrupt phase/recovery coverage')
    cancels = [fields(x) for x in re.findall(r'^READER_GATE_CANCEL (.+)$', log, re.M)]
    if len(cancels) != 4 or [r.get('phase') for r in cancels] != list(range(4)):
        raise ValueError('Missing cancel-drain ledger')
    for row in cancels:
        if set(row) != {'phase', 'busy_cycles', 'repeat_pulses'}:
            raise ValueError('Malformed cancel-drain ledger')
        if row['phase'] == 2:
            if not 1 <= row['busy_cycles'] <= 12 or row['repeat_pulses'] != 1:
                raise ValueError('Missing busy T64 cancel/repeated pulse')
        elif row['busy_cycles'] != 0 or row['repeat_pulses'] != 0:
            raise ValueError('Wrong non-gather interrupt phase')
    totals = [fields(x) for x in re.findall(r'^READER_GATE_PASS (.+)$', log, re.M)]
    if len(totals) != 1:
        raise ValueError('Missing/duplicate completion')
    total = totals[0]
    exact = dict(normal=232, cancel=4, reset=4, invalid=4, held_done=1200)
    positive = {'checks', 'qlatency', 'vlatency', 'stalls', 'lane_stalls'}
    if set(total) != set(exact)|positive or any(total[k] != v for k,v in exact.items()):
        raise ValueError('Wrong completion totals')
    if any(total[k] <= 0 for k in positive):
        raise ValueError('Missing positive coverage')
    if total['qlatency'] < sum(r['qreads'] for r in cases) or total['vlatency'] < sum(r['vreads'] for r in cases):
        raise ValueError('Missing synchronous SRAM latency checks')
    minimum_checks = sum(sum(r['dimensions']*(1+(r['tokens']+15-l)//16)
                                for l in range(min(4,r['tokens']))) if r['qk'] else
                         4*r['tokens']*(1+r['dimensions']//16) for r in cases)
    if total['checks'] < minimum_checks:
        raise ValueError('Missing delivered lane comparisons')
    return dict(totals=total, cases=cases, interrupts=interrupts, cancellations=cancels,
                measured_q_and_v_read_latency_cycles=1)


def prepare(out):
    sources, defines, pins = source_selection()
    if subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'],
                               text=True).strip() != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong verification branch')
    out.mkdir(exist_ok=False)
    inputs = out/'inputs'
    inputs.mkdir()
    selected = []
    def copy(source, dest):
        digest = pins.get(str(source), sha(source))
        if sha(source) != digest:
            raise ValueError('Source changed before copy: '+str(source))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        dest.chmod(0o444)
        pins[str(source)] = pins[str(dest)] = digest
        if sha(dest) != digest:
            raise ValueError('Copy identity mismatch')
    for source in sources:
        dest = inputs/source.relative_to(FROZEN)
        copy(source, dest)
        selected.append(str(dest))
    for relative in (AKV+'akv_resident_pv_reader.sv', AKV+'resident_payload_fanout.sv'):
        dest = inputs/relative
        copy(REPO/relative, dest)
        selected.append(str(dest))
    for name in LOCAL:
        copy(HERE/name, inputs/name)
    # Audit-only snapshots: these are NOT instantiated in this component gate.
    for name in ('akv_resident_pv_control.sv', 'akv_engine.sv'):
        copy(REPO/AKV/name, inputs/'audit'/name)
    filelist = inputs/'sources.f'
    filelist.write_text('\n'.join(defines+selected+[str(inputs/'reader_gate.sv')])+'\n')
    pins[str(filelist)] = sha(filelist)
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('VCS is unavailable')
    pins[str(Path(vcs).resolve())] = sha(vcs)
    save(out/'selection.json', dict(vcs=vcs, top='reader_gate_tb', sources=selected,
        inherited_scope='Selected accepted dependency bytes, not reacceptance of predecessor live inputs',
        parent_settled=True, compile_seconds=240, simulation_seconds=60,
        scope='Reader/unified QKV context/fanout only; no engine/control/lane arithmetic or SoC acceptance'))
    pins[str(out/'selection.json')] = sha(out/'selection.json')
    verify(pins)
    save(out/'source-pins.json', pins)
    save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED'))


def command(argv, cwd, log, seconds):
    with log.open('x') as stream:
        process = subprocess.Popen(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            rc = process.wait(timeout=seconds)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    text = log.read_text(errors='replace')
    if rc:
        raise ValueError(f'Command exited {rc}: {log}')
    return text


def execute(out):
    pins = json.loads((out/'source-pins.json').read_text())
    config = json.loads((out/'selection.json').read_text())
    work = out/'work'
    work.mkdir(exist_ok=False)
    report = dict(state='FAIL', scope=config['scope'])
    try:
        verify(pins)
        commands = dict(tests=[sys.executable, '-B', str(out/'inputs/reader_gate_test.py')],
            compile=[config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                     '-top', 'reader_gate_tb', '+define+SIMULATION', '-f', str(out/'inputs/sources.f'), '-o', 'simv'],
            run=[str(work/'simv'), '-no_save'])
        save(out/'commands.json', commands)
        command(commands['tests'], work, out/'tests.log', 30)
        print('READER_GATE_COMPILING '+str(out), flush=True)
        command(commands['compile'], work, out/'compile.log', config['compile_seconds'])
        verify(pins)
        image = {str(p): sha(p) for p in (work/'simv.daidir').rglob('*') if p.is_file()}
        image[str(work/'simv')] = sha(work/'simv')
        save(out/'image-pins.json', image)
        print('READER_GATE_RUNNING '+str(out), flush=True)
        checked = check_log(command(commands['run'], work, out/'run.log', config['simulation_seconds']))
        verify(pins)
        verify(image)
        save(out/'source-pins-after.json', pins)
        save(out/'image-pins-after.json', image)
        report.update(state='PASS', post_pins_match=True, post_image_match=True, **checked)
    except Exception as exc:
        report['error'] = str(exc)
    report['artifacts'] = {str(out/n): sha(out/n) for n in (
        'source-pins.json', 'selection.json', 'prepared.json', 'commands.json',
        'tests.log', 'compile.log', 'run.log', 'image-pins.json',
        'source-pins-after.json', 'image-pins-after.json') if (out/n).is_file()}
    save(out/'report.json', report)
    print('READER_GATE_'+report['state']+' '+str(out/'report.json'), flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--parent-settled', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--parent-reviewed', action='store_true')
    args = parser.parse_args()
    if args.list:
        sources, defines, _ = source_selection()
        print('\n'.join(defines+[str(p) for p in sources]+[
            str(REPO/AKV/'akv_resident_pv_reader.sv'), str(REPO/AKV/'resident_payload_fanout.sv'),
            str(HERE/'reader_gate.sv')]))
        return 0
    if args.output is None or args.output.resolve().parent != OUT:
        parser.error('Use a fresh direct child of signoff verification/out')
    out = args.output.resolve()
    if args.execute:
        if not args.parent_reviewed or Path(__file__).resolve() != out/'inputs/reader_gate.py':
            parser.error('Use the frozen runner after parent review')
        return execute(out)
    if not args.parent_settled:
        parser.error('Parent must confirm sources settled before freeze')
    prepare(out)
    print('READER_GATE_PREPARED_NOT_EXECUTED '+str(out))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
