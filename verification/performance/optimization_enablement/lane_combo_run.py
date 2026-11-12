#!/usr/bin/env python3
"""Two bounded all-on VMFPU gates, with unchanged inherited arithmetic checks."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
FP_REL = 'verification/performance/next_mechanism/stage2/run_vmfpu_fp.py'
QK_REL = 'verification/performance/resident_rvv/qk_shared'
SEALED = {
    'hardware/Makefile': '63cce8ac554f7c517a5ad5a8249f16dc5a8164fbaf6cbe028152994c52568c46',
    'hardware/include/ara_pkg.sv': 'e6e333d6461d8e071543318002798d0c46345b3724f5baad64270ea3e43e9dd5',
    'config/optimizations.mk': '9e8c9daa633f145626b2482d0b0ebff8f696842b18ca9258fa9055808146542f',
}
SCOPE = ('Current RTL, one actual VMFPU and QK/PV controller; shared FMA + shared '
         'integer MUL + borrower + Resident QK/PV. No four-lane SoC, decoder, '
         'model performance, synthesis, FPGA or physical acceptance.')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


FP = load(ROOT/FP_REL, 'combo_inherited_fp')
QK = load(ROOT/QK_REL/'run_fpu_gate.py', 'combo_inherited_qk')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def adapt(text):
    before = ".SharedFma(1'b0)"
    require(text.count(before) == 1, 'Unrecognized inherited bench FMA parameter')
    return text.replace(before, '.SharedFma(ara_pkg::EnableSharedFma)')


def probe_check(text, kind, checked):
    require(text.splitlines().count('LANE_COMBO_CONFIG shared_fma=1 shared_mul=1 '
        'resident=1 borrower=1 fma_latency=5') == 1, 'Missing/duplicate actual combo configuration')
    rows = re.findall(r'^LANE_COMBO_WORK fp16=(\d+) fp32=(\d+) private_returns=(\d+) '
                      r'borrowed=(\d+) returned=(\d+) native=(\d+)$', text, re.M)
    require(len(rows) == 1, 'Missing/duplicate actual combo work')
    values = list(map(int, rows[0]))
    if kind == 'qk':
        cases = checked['cases']
        expected = [sum(r['issued'] for r in cases if r['mode'] == mode) for mode in (0, 1)]
        expected += [sum(r['returned'] for r in cases), 25, 25, 0]
    else:
        expected = [2, 0, 2, 24, 24, 5]
    require(values == expected, 'Actual combo work differs from inherited checker ledger')
    return dict(zip(('fp16', 'fp32', 'private_returns', 'borrowed', 'returned', 'native'), values))


def prepare(out):
    require(out.parent == OUT and out.name.startswith('enablement_lane_') and not out.exists(),
            'Fresh directly owned signoff output required')
    require(subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch',
            '--show-current'], text=True).strip() == 'ara_dsa_signoff_integration', 'Wrong signoff branch')
    FP.verify({str(ROOT/p): s for p, s in SEALED.items()})
    FP.verify(FP.ADMISSION)
    accepted = json.loads((FP.ACCEPTED/'source-pins.json').read_text())
    receipt = json.loads((FP.ACCEPTED/'report.json').read_text())
    require(receipt['state'] == 'PASS' and receipt['post_pins_match'] and receipt['post_image_match'],
            'Frozen dependency admission failed')
    require(shutil.which('vcs') is not None, 'Host VCS unavailable')
    out.mkdir()
    inputs = out/'inputs'
    pins = dict(FP.ADMISSION)
    sources = list(dict.fromkeys(FP.dependencies(FP.FILELIST.read_text()) +
                                ['hardware/src/lane/akv_resident_pv_lane.sv']))
    for rel in sources:
        dependency = rel.startswith('hardware/deps/')
        source = (FP.FROZEN if dependency else ROOT)/rel
        FP.copy_pin(source, inputs/rel, pins, accepted[str(source)] if dependency else None)
    for rel in QK.PRODUCTION:
        if rel not in sources:
            FP.copy_pin(ROOT/rel, inputs/rel, pins)
    for rel in SEALED:
        if rel not in sources:
            FP.copy_pin(ROOT/rel, inputs/rel, pins, SEALED[rel])
    headers = FP.FROZEN/'hardware/deps/common_cells/include'
    for source in sorted(p for p in headers.rglob('*') if p.is_file()):
        FP.copy_pin(source, inputs/source.relative_to(FP.FROZEN), pins, accepted[str(source)])
    support = [FP_REL, 'verification/performance/resident_rvv/ordered_reference.py',
               'verification/fpnew_upstream_20261009/oracle.py']
    support += [QK_REL + '/' + n for n in QK.OWN]
    support += [str((HERE/n).relative_to(ROOT)) for n in
                ('lane_combo_run.py', 'lane_combo_probe.sv', 'lane_combo_test.py')]
    for rel in support:
        FP.copy_pin(ROOT/rel, inputs/rel, pins)
    library = Path('/home/wangwy/software/toolchains/spike/lib/libsoftfloat.so')
    FP.copy_pin(library, inputs/'libsoftfloat.so', pins)
    with (out/'vectors.log').open('x') as log:
        subprocess.run(['/usr/bin/python3', '-B', str(inputs/QK_REL/'fpu_gate_vectors.py'),
            str(out), str(inputs/'libsoftfloat.so')], stdout=log, stderr=subprocess.STDOUT,
            check=True, timeout=120)
    for name in ('vectors.txt', 'expected.json', 'vectors.log'):
        pins[str(out/name)] = FP.sha(out/name)
    jobs = []
    transformations = []
    for name, rel, top in (
        ('qk', QK_REL + '/fpu_gate_tb.sv', 'resident_qk_fpu_tb'),
        ('fullfp', str(Path(FP_REL).with_name('vmfpu_fp_tb.sv')), 'stage2_vmfpu_fp_tb')):
        source = ROOT/rel
        FP.copy_pin(source, inputs/rel, pins)
        bench = inputs/('lane_combo_' + name + '.sv')
        bench.write_text(adapt((inputs/rel).read_text()))
        pins[str(bench)] = FP.sha(bench)
        transformations.append(dict(source=str(source), source_sha256=pins[str(source)],
            derived=str(bench), derived_sha256=pins[str(bench)],
            change='Only SharedFma literal 0 -> ara_pkg::EnableSharedFma; no checker/stimulus changes'))
        filelist = inputs/('lane_combo_' + name + '.f')
        filelist.write_text('+incdir+' + str(inputs/headers.relative_to(FP.FROZEN)) + '\n' +
            '\n'.join(str(inputs/r) for r in sources) + '\n' + str(bench) + '\n' +
            str(inputs/HERE.relative_to(ROOT)/'lane_combo_probe.sv') + '\n')
        pins[str(filelist)] = FP.sha(filelist)
        jobs.append(dict(name=name, top=top, filelist=str(filelist)))
    vcs = str(Path(shutil.which('vcs')).resolve())
    pins[vcs] = FP.sha(vcs)
    static = QK.audit_sources(inputs)
    FP.save(out/'config.json', dict(scope=SCOPE, vcs=vcs, jobs=jobs, static=static,
        compile_seconds=600, run_seconds=180, transformations=transformations,
        head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        configuration=dict(shared_fma=1, shared_integer_mul=1, qbs_borrower=1, resident_qk_pv=1),
        current_rtl={r: FP.sha(ROOT/r) for r in sources if not r.startswith('hardware/deps/')},
        dependency_policy='Admitted frozen FP dependencies only; no unchecked live dependency substitution'))
    pins[str(out/'config.json')] = FP.sha(out/'config.json')
    FP.verify(pins)
    FP.save(out/'source-pins.json', pins)
    FP.save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED',
        runner=str(inputs/HERE.relative_to(ROOT)/'lane_combo_run.py'),
        source_pins_sha256=FP.sha(out/'source-pins.json'), config_sha256=FP.sha(out/'config.json')))
    print(json.dumps(json.loads((out/'prepared.json').read_text())), flush=True)


def execute(out, review):
    require(FP.sha(out/'source-pins.json') == review, 'Unreviewed snapshot')
    config = json.loads((out/'config.json').read_text())
    prepared = json.loads((out/'prepared.json').read_text())
    require(str(Path(__file__).resolve()) == prepared['runner'] and
            FP.sha(out/'config.json') == prepared['config_sha256'], 'Use frozen runner/config only')
    unit = 'enablement-lane-' + out.name + '.service'
    cgroup = Path('/proc/self/cgroup').read_text()
    owner = subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
    require('/' + unit in cgroup and owner == str(os.getpid()), 'Direct service MainPID required')
    pins = json.loads((out/'source-pins.json').read_text())
    FP.save(out/'owner.json', dict(pid=os.getpid(), cgroup=cgroup, unit=unit))
    started = time.monotonic()
    report = dict(state='FAIL', scope=SCOPE, jobs=[], source_pins_sha256=review)
    try:
        FP.verify(pins)
        with (out/'host.log').open('x') as log:
            subprocess.run(['/usr/bin/python3', '-B', str(HERE/'lane_combo_test.py')],
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
            subprocess.run(['/usr/bin/python3', '-B', str(ROOT/QK_REL/'test_fpu_gate.py'),
                            '--prepared', str(out)], stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
        expected = json.loads((out/'expected.json').read_text())
        for job in config['jobs']:
            work = out/job['name']
            work.mkdir()
            compile_cmd = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-j2',
                '+define+SIMULATION', '+define+ARA_SHARED_SIMD_MUL', '+define+ARA_SHARED_FMA=1',
                '-top', job['top'], '-o', 'simv', '-f', job['filelist']]
            run_cmd = [str(work/'simv'), '-no_save']
            if job['name'] == 'qk':
                run_cmd.append('+VECTOR=' + str(out/'vectors.txt'))
            FP.save(work/'commands.json', dict(compile=compile_cmd, run=run_cmd))
            times = {}
            for phase, command in (('compile', compile_cmd), ('run', run_cmd)):
                FP.verify(pins)
                print('LANE_COMBO_' + phase.upper() + ' ' + job['name'], flush=True)
                FP.save(out/'status.json', dict(state='RUNNING', job=job['name'], phase=phase))
                tick = time.monotonic()
                with (work/(phase + '.log')).open('x') as log:
                    subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s',
                        str(config[phase + '_seconds']), *command], cwd=work,
                        stdout=log, stderr=subprocess.STDOUT, check=True)
                times[phase] = time.monotonic() - tick
                FP.verify(pins)
                require(not FP.ERROR.search((work/(phase + '.log')).read_text(errors='replace')),
                        'Tool error in ' + job['name'] + '/' + phase)
                if phase == 'compile':
                    images = {str(p): FP.sha(p) for p in (work/'simv.daidir').rglob('*') if p.is_file()}
                    images[str(work/'simv')] = FP.sha(work/'simv')
                    FP.save(work/'image-pins.json', images)
            FP.verify(images)
            log = (work/'run.log').read_text()
            checked = QK.check(log, expected) if job['name'] == 'qk' else FP.check(log)
            probe = probe_check(log, job['name'], checked)
            report['jobs'].append(dict(name=job['name'], checked=checked, actual_work=probe,
                elapsed_seconds=times, artifacts={str(work/n): FP.sha(work/n) for n in
                    ('commands.json', 'compile.log', 'run.log', 'image-pins.json')}))
            FP.save(out/'progress.json', report)
        FP.verify(pins)
        for job in report['jobs']:
            FP.verify(job['artifacts'])
            FP.verify(json.loads((out/job['name']/'image-pins.json').read_text()))
        report.update(state='PASS', source_pins_match=True, image_pins_match=True)
    except Exception as exc:
        report['error'] = repr(exc)
    report['elapsed_seconds'] = time.monotonic() - started
    FP.save(out/'report.json', report)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('action', choices=('prepare', 'execute'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare(args.output.resolve())
    else:
        raise SystemExit(execute(args.output.resolve(), args.review_sha256))
