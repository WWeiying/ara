#!/usr/bin/env python3
"""Freeze current production RTL with registered dependencies; build VCS only."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = OUT / 'enablement_soc_resident_deployment_20261112_022423'
GATE = 'hardware/fpga/ara_dsa_vcu118/provenance/resident_direct_20261114'
ARCHIVE = ('hardware/src', 'hardware/include', 'hardware/tb', 'hardware/Makefile',
           'Bender.yml', 'Bender.lock', 'config', 'verification/uvm', 'verification/ara_verify')


def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for data in iter(lambda: f.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def save(p, obj):
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(obj, indent=2) + '\n')
    tmp.replace(p)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def verify(pins):
    for path, expected in pins.items():
        require(sha(path) == expected, 'Source drift: ' + str(path))


def prepare(out):
    require(not out.exists(), 'Output must be new')
    baseline = json.loads((BASE / 'build.json').read_text())
    require(baseline['state'] == 'RESIDENT_DEPLOYMENT_SOC_BUILT_NOT_EXECUTED', 'Bad template')
    inv = json.loads((BASE / 'inventory.json').read_text())['source']
    verify(inv)
    out.mkdir()
    source, inputs, sim = (out / n for n in ('source', 'inputs', 'sim'))
    inputs.mkdir(); sim.mkdir()
    for name in inv:
        rel = Path(name).relative_to(BASE / 'source')
        dest = source / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(name, dest)
    revision = subprocess.check_output(['git', '-C', ROOT, 'rev-parse', 'HEAD'], text=True).strip()
    archive = subprocess.check_output(['git', '-C', ROOT, 'archive', revision, *ARCHIVE])
    (out / 'production-source.tar').write_bytes(archive)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for member in tar:
            rel = Path(member.name)
            require(not rel.is_absolute() and '..' not in rel.parts, 'Unsafe archive path')
            dest = source / rel
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                require(rel.as_posix() == 'hardware/tb/dpi/elfloader.cc', 'Unexpected source link')
                require((dest.parent / member.linkname).resolve().is_file(), 'Missing frozen DPI link target')
            else:
                require(member.isfile(), 'Unsupported archive item')
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(tar.extractfile(member).read())
    gate = json.loads(subprocess.check_output(['git', '-C', ROOT, 'show',
        revision + ':' + GATE + '/baseline-current-hashes.json']))
    for rel, expected in gate['baseline'].items():
        dest = source / 'hardware/deps/cva6' / rel
        require(sha(dest) == expected, 'Gate preimage mismatch: ' + rel)
        data = subprocess.check_output(['git', '-C', ROOT, 'show', revision +
            ':hardware/fpga/ara_dsa_vcu118/rtl/cva6/' + rel])
        require(hashlib.sha256(data).hexdigest() == gate['current'][rel], 'Gate export mismatch')
        dest.write_bytes(data)
    save(out / 'gate-receipt.json', gate)
    oldplan = json.loads((BASE / 'plan.json').read_text())
    text = (BASE / 'sources.f').read_text().replace(str(BASE / 'source'), str(source))
    (out / 'sources.f').write_text(text)
    shutil.copyfile(BASE / 'elfloader.o', out / 'elfloader.o')
    for name in ('loan.sv', 'fma.sv'):
        p = BASE / 'inputs' / name
        require(sha(p) == json.loads((BASE / 'source-pins.json').read_text())[str(p)], 'Monitor drift')
        shutil.copyfile(p, inputs / name)
    shutil.copyfile(Path(__file__).with_name('unit_activity.sv'), inputs / 'unit_activity.sv')
    shutil.copyfile(__file__, inputs / 'build_soc.py')
    command = [arg.replace(str(BASE), str(out)) for arg in oldplan['command']]
    command.append(str(inputs / 'unit_activity.sv'))
    config = dict(oldplan['configuration'], config='operator_eval_current_all',
                  direct_u_gate=1, gate_reset_strict=0)
    require(all(config[k] == 1 for k in ('shared_simd_multiplier', 'shared_fma',
        'qbs_lane_multiplier', 'resident_pv_enabled', 'resident_qk_enabled')), 'Incomplete candidate')
    require(all(token in text for token in ('+define+NR_LANES=4', '+define+VLEN=1024',
        '+define+ARA_SHARED_FMA=1', '+define+ARA_QBS_LANE_MUL_ENABLE=1',
        '+define+ARA_AKV_RESIDENT_PV_ENABLE=1', '+define+ARA_AKV_RESIDENT_QK_ENABLE=1')), 'Bad defines')
    require('IDEAL_DISPATCHER' not in text and '-R' not in command, 'Unfair core or auto execution')
    (sim / 'simulator.conf').write_text(''.join(f'{k}={v}\n' for k, v in config.items()))
    save(out / 'plan.json', dict(revision=revision, command=command, configuration=config,
        environment=oldplan['environment'], dependency_template=str(BASE),
        dirty_tb_used=False, live_dependencies_used=False, no_hardware_changes=True,
        gate_source='committed FPGA four-file export matches reviewed main gate hashes'))
    pins = {str(p): sha(p) for root in (source, inputs) for p in root.rglob('*') if p.is_file()}
    for name in ('production-source.tar', 'gate-receipt.json', 'sources.f', 'elfloader.o',
                 'plan.json', 'sim/simulator.conf'):
        pins[str(out / name)] = sha(out / name)
    save(out / 'source-pins.json', pins)
    verify(pins)
    save(out / 'status.json', dict(state='PREPARED', revision=revision, cases_run=0))


def execute(out):
    require(Path(__file__).resolve() == out / 'inputs/build_soc.py', 'Execute frozen worker')
    require(not (out / 'attempt.json').exists(), 'No automatic retry')
    save(out / 'attempt.json', dict(owner_pid=os.getpid(), started=time.time()))
    pins = json.loads((out / 'source-pins.json').read_text())
    plan = json.loads((out / 'plan.json').read_text())
    report = dict(state='FAIL', configuration=plan['configuration'], revision=plan['revision'],
                  scope='Current all-on SoC compile, not simulation acceptance', model_executed=False)
    try:
        verify(pins)
        with (out / 'compile.log').open('x') as f:
            proc = subprocess.Popen(plan['command'], cwd=out / 'sim', env=plan['environment'],
                                    stdout=f, stderr=subprocess.STDOUT)
            save(out / 'status.json', dict(state='VCS_COMPILING', child_pid=proc.pid, started=time.time()))
            try:
                rc = proc.wait(timeout=7200)
            except BaseException:
                proc.terminate()
                proc.wait(timeout=20)
                raise
        require(rc == 0, 'VCS exit ' + str(rc))
        require(not re.search(r'(?m)^\s*(?:Error-|Fatal-|Error:|Fatal:)',
                             (out / 'compile.log').read_text(errors='replace')), 'Compile errors')
        verify(pins)
        image = {str(p): sha(p) for root in (out / 'sim/simv.daidir',) for p in root.rglob('*') if p.is_file()}
        image[str(out / 'sim/simv')] = sha(out / 'sim/simv')
        save(out / 'image-pins.json', image)
        report.update(state='CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED', simv=str(out / 'sim/simv'),
                      post_pins_match=True, image_pins=image)
    except Exception as exc:
        report['error'] = repr(exc)
    save(out / 'build.json', report)
    save(out / 'status.json', dict(state=report['state'], child_pid=None, finished=time.time()))
    print(json.dumps(report), flush=True)
    return report['state'] == 'FAIL'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'execute'))
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    require(out.parent == OUT and out.name.startswith('operator_soc_20261115_'), 'Wrong output scope')
    if a.action == 'prepare':
        prepare(out)
        print(json.dumps(dict(state='PREPARED', output=str(out))))
        return 0
    return execute(out)


if __name__ == '__main__':
    raise SystemExit(main())
