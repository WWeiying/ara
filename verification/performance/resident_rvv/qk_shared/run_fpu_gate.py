#!/usr/bin/env python3
"""Bounded real-VMFPU QK/PV arithmetic gate, plus unchanged native/full-FP regression."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FP_HELPER = ROOT / 'verification/performance/next_mechanism/stage2/run_vmfpu_fp.py'
spec = importlib.util.spec_from_file_location('accepted_fp_gate', FP_HELPER)
FP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FP)
OWN = ('run_fpu_gate.py', 'fpu_gate_vectors.py', 'fpu_gate_tb.sv', 'test_fpu_gate.py')
PRODUCTION = ('hardware/src/lane/akv_resident_pv_lane.sv', 'hardware/src/lane/vmfpu.sv',
              'hardware/src/lane/lane.sv', 'hardware/src/lane/vector_fus_stage.sv')
PACKAGE_REV = '11fd3e580'
FIELDS = ('id mode elements heads iterations rm action issued returned writes flags cancelled').split()
SCOPE = ('One actual controller and VMFPU, sequential logical lane geometries; independent '
         'Spike SoftFloat ordered QK/PV. Standard/shared integer banks; SharedFma=0. '
         'Wrapper source contracts only; no four-lane group, ABI, Q SRAM, LDU-final, '
         'SoC, synthesis, board or performance acceptance.')


def check(text, expected):
    if FP.ERROR.search(text):
        raise ValueError('Simulator fatal/error')
    rows = []
    for line in text.splitlines():
        if line.startswith('QKFPU_CASE '):
            pairs = [p.split('=') for p in line.split()[1:]]
            if ([p[0] for p in pairs] != FIELDS or any(len(p) != 2 or not p[1].isdigit() for p in pairs)):
                raise ValueError('Malformed case accounting')
            rows.append({k: int(v) for k, v in pairs})
    if len(rows) != len(expected['cases']) or [r['id'] for r in rows] != list(range(len(rows))):
        raise ValueError('Missing/duplicate/out-of-order cases')
    for row, case in zip(rows, expected['cases']):
        if any(row[k] != case[k] for k in ('mode', 'elements', 'heads', 'iterations', 'rm', 'action')):
            raise ValueError('Shape/mode identity mismatch')
        if case['action'] == 0:
            if any(row[k] != case[k] for k in ('issued', 'writes', 'flags')) or row['returned'] != row['issued'] or row['cancelled']:
                raise ValueError('Ordered arithmetic/flags/work mismatch')
        elif case['action'] == 1:
            if not 0 < row['issued'] < case['issued'] or row['returned'] != row['issued'] or row['writes'] or row['cancelled']:
                raise ValueError('Abort did not drain accepted arithmetic without writes')
        elif (row['cancelled'] == 0 or row['issued'] != row['returned'] + row['cancelled'] or row['writes']):
            raise ValueError('Reset cancellation did not close')
    final = re.findall(r'^QKFPU_PASS cases=(\d+) inactive=(\d+) aborts=(\d+) resets=(\d+) '
        r'prestart=(\d+) qbs_issued=(\d+) qbs_returned=(\d+) reset_cancelled=(\d+) '
        r'return_stalls=(\d+) scope=controller_vmfpu_not_soc$', text, re.M)
    if len(final) != 1:
        raise ValueError('Missing/duplicate focused terminal')
    values = list(map(int, final[0]))
    if values[:7] != [26, 2, 1, 1, 182, 25, 25] or values[7] != sum(x['cancelled'] for x in rows) or values[7] == 0 or values[8] == 0:
        raise ValueError('Insufficient ownership/stall/drain evidence')
    return dict(cases=rows, prestart_cycles=values[4], actual_qbs_issues=values[5],
                actual_qbs_returns=values[6], reset_cancelled=values[7], return_stalls=values[8])


def audit_sources(inputs):
    ctrl = (inputs / PRODUCTION[0]).read_text()
    vm = (inputs / PRODUCTION[1]).read_text()
    lane = (inputs / PRODUCTION[2]).read_text()
    fus = (inputs / PRODUCTION[3]).read_text()
    if len(re.findall(r'logic\s+\[63:0\]\s+accum_q\s*\[16\]', ctrl)) != 1:
        raise ValueError('Controller accumulator is not the single original array')
    if ctrl.count('logic [64:0] fifo_q [2]') != 1 or vm.count(') i_fpnew_bulk (') != 1:
        raise ValueError('Ingress/FPU duplication')
    for fragment in ('resident_fp32_q <= resident_fp32_i;', 'if (resident_valid_i)',
                     'resident_mask_i[(2*b)/FPULanes]', 'resident_mask_i[(4*b)/FPULanes]'):
        if fragment not in vm:
            raise ValueError('VMFPU format/mask contract missing')
    for fragment in ('assign pv_fpu_fp32 = cmd_captured_q && qk_q;',
                     'assign start_command = (pv_start_i === 1\'b1) && pv_ready_o && active;',
                     '.resident_fp32_i          (pv_fpu_fp32)', 'operand_request_idle[q]'):
        if fragment not in lane:
            raise ValueError('Wrapper capture/active/idle contract missing')
    if '.resident_fp32_i          (resident_fp32_i)' not in fus:
        raise ValueError('FUS format passthrough missing')
    return dict(single_accumulator=True, single_fpu=True, wrapper='STATIC_ONLY', full_wrapper_executed=False)


def prepare(out):
    if out.parent != FP.OUT or out.exists() or not shutil.which('vcs'):
        raise ValueError('Require unique signoff output and host VCS')
    FP.verify(FP.ADMISSION)
    admitted = json.loads((FP.ACCEPTED / 'report.json').read_text())
    if admitted['state'] != 'PASS' or not admitted['post_pins_match'] or not admitted['post_image_match']:
        raise ValueError('Frozen dependency admission failed')
    accepted = json.loads((FP.ACCEPTED / 'source-pins.json').read_text())
    out.mkdir()
    inputs = out / 'inputs'
    pins = dict(FP.ADMISSION)
    sources = FP.dependencies(FP.FILELIST.read_text())
    for rel in sources:
        dest = inputs / rel
        if rel == 'hardware/include/ara_pkg.sv':
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show', PACKAGE_REV + ':' + rel]))
            pins[str(dest)] = FP.sha(dest)
        else:
            src = (ROOT if rel in FP.OVERLAY else FP.FROZEN) / rel
            FP.copy_pin(src, dest, pins, None if rel in FP.OVERLAY else accepted[str(src)])
    for rel in PRODUCTION:
        FP.copy_pin(ROOT / rel, inputs / rel, pins)
    controller = PRODUCTION[0]
    sources.append(controller)
    headers = FP.FROZEN / 'hardware/deps/common_cells/include'
    for src in sorted(p for p in headers.rglob('*') if p.is_file()):
        FP.copy_pin(src, inputs / src.relative_to(FP.FROZEN), pins, accepted[str(src)])
    local = inputs / HERE.relative_to(ROOT)
    for name in OWN:
        FP.copy_pin(HERE / name, local / name, pins)
    FP.copy_pin(FP_HELPER, inputs / FP_HELPER.relative_to(ROOT), pins)
    FP.copy_pin(FP_HELPER.parent / 'vmfpu_fp_tb.sv', inputs / 'vmfpu_fp_tb.sv', pins)
    for rel in ('verification/performance/resident_rvv/ordered_reference.py', 'verification/fpnew_upstream_20261009/oracle.py'):
        FP.copy_pin(ROOT / rel, inputs / rel, pins)
    library = Path('/home/wangwy/software/toolchains/spike/lib/libsoftfloat.so')
    FP.copy_pin(library, inputs / 'libsoftfloat.so', pins)
    audit = audit_sources(inputs)
    with (out / 'vectors.log').open('x') as stream:
        subprocess.run([sys.executable, '-B', str(local / 'fpu_gate_vectors.py'), str(out), str(inputs / 'libsoftfloat.so')],
                       stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    for name in ('vectors.txt', 'vectors.log', 'expected.json'):
        pins[str(out / name)] = FP.sha(out / name)
    configurations = []
    for shared in (0, 1):
        for old in (0, 1):
            name = ('fullfp' if old else 'qk') + '_shared' + str(shared)
            filelist = inputs / (name + '.f')
            tb = inputs / 'vmfpu_fp_tb.sv' if old else local / 'fpu_gate_tb.sv'
            filelist.write_text('+incdir+' + str(inputs / headers.relative_to(FP.FROZEN)) + '\n' +
                '\n'.join(str(inputs / rel) for rel in sources) + '\n' + str(tb) + '\n')
            pins[str(filelist)] = FP.sha(filelist)
            configurations.append(dict(name=name, old=old, shared=shared, filelist=str(filelist),
                                       top='stage2_vmfpu_fp_tb' if old else 'resident_qk_fpu_tb'))
    vcs = str(Path(shutil.which('vcs')).resolve())
    pins[vcs] = FP.sha(vcs)
    FP.save(out / 'config.json', dict(scope=SCOPE, package_source_revision=PACKAGE_REV,
        arithmetic_sources=sources, vcs=vcs, configurations=configurations, local=str(local), static=audit))
    pins[str(out / 'config.json')] = FP.sha(out / 'config.json')
    FP.verify(pins)
    FP.save(out / 'source-pins.json', pins)
    FP.save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', frozen_runner=str(local / OWN[0])))
    print(local / OWN[0], flush=True)


def execute(out):
    config = json.loads((out / 'config.json').read_text())
    if Path(__file__).resolve() != Path(config['local']) / OWN[0]:
        raise ValueError('Use frozen runner')
    pins = json.loads((out / 'source-pins.json').read_text())
    report = dict(state='FAIL', scope=SCOPE, configurations=[], static=config['static'],
                  source_pins_sha256=FP.sha(out / 'source-pins.json'))
    try:
        FP.verify(pins)
        cgroup = Path('/proc/self/cgroup').read_text()
        if '.service' not in cgroup:
            raise ValueError('Direct systemd owner required')
        FP.save(out / 'owner.json', dict(pid=os.getpid(), cgroup=cgroup))
        with (out / 'host.log').open('x') as stream:
            subprocess.run([sys.executable, '-B', str(Path(config['local']) / 'test_fpu_gate.py'),
                            '--prepared', str(out)], stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
        expected = json.loads((out / 'expected.json').read_text())
        for c in config['configurations']:
            work = out / c['name']
            work.mkdir()
            cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j4',
                   '+define+SIMULATION', '-top', c['top'], '-o', 'simv', '-f', c['filelist']]
            if c['shared']:
                cmd.append('+define+ARA_SHARED_SIMD_MUL')
            run = [str(work / 'simv'), '-no_save']
            if not c['old']:
                run.append('+VECTOR=' + str(out / 'vectors.txt'))
            FP.save(work / 'commands.json', dict(compile=cmd, run=run))
            for phase, argv, seconds in (('compile', cmd, 600), ('run', run, 180)):
                FP.save(out / 'status.json', dict(state='RUNNING', configuration=c['name'], phase=phase))
                print('QKFPU_' + phase.upper() + ' ' + c['name'], flush=True)
                with (work / (phase + '.log')).open('x') as stream:
                    subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s', str(seconds), *argv],
                                   cwd=work, stdout=stream, stderr=subprocess.STDOUT, check=True)
                FP.verify(pins)
                if FP.ERROR.search((work / (phase + '.log')).read_text(errors='replace')):
                    raise ValueError('Tool error: ' + c['name'] + '/' + phase)
                if phase == 'compile':
                    images = {str(f): FP.sha(f) for f in (work / 'simv.daidir').rglob('*') if f.is_file()}
                    images[str(work / 'simv')] = FP.sha(work / 'simv')
                    FP.save(work / 'image-pins.json', images)
            FP.verify(images)
            log = (work / 'run.log').read_text()
            checked = FP.check(log) if c['old'] else check(log, expected)
            artifacts = {str(work / n): FP.sha(work / n) for n in ('commands.json', 'compile.log', 'run.log', 'image-pins.json')}
            report['configurations'].append(dict(**c, checked=checked, artifacts=artifacts))
            FP.save(out / 'progress.json', report)
        FP.verify(pins)
        for c in report['configurations']:
            FP.verify(c['artifacts'])
            FP.verify(json.loads((out / c['name'] / 'image-pins.json').read_text()))
        report.update(state='PASS', source_pins_match=True, image_pins_match=True)
    except Exception as exc:
        report['error'] = str(exc)
    report['host_log_sha256'] = FP.sha(out / 'host.log') if (out / 'host.log').is_file() else None
    FP.save(out / 'report.json', report)
    FP.save(out / 'status.json', dict(state=report['state']))
    print('QKFPU_' + report['state'], flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--execute', action='store_true')
    args = p.parse_args()
    if args.execute:
        raise SystemExit(execute(args.output.resolve()))
    prepare(args.output.resolve())
