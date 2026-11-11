#!/usr/bin/env python3
"""Strict BUILD07 rebind of the sealed three-guest worker and four-gate reader."""
import importlib.util
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('execution_v3_check', HERE / 'check_v3.py')
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
c = check.c
BASE_SHA = '54ea1bd95d894dc9bd2d7e688658e687893acfaa67be772707d8e0ab971027fe'
b = c.load(HERE / 'run.py', BASE_SHA, 'execution_v3_sealed_worker')
OUT, require, sha, read, ORIGINAL = b.OUT, b.require, b.sha, b.read, b.ORIGINAL
BUILD = OUT / 'stage5_qemu_build_20261110_07'
BUILD_SHA = '85a4939f7419c706280f6959c89a25f322f6bf5b0caf7c3bb7c1c60b7305c701'
BINARY_SHA = '1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a'
GATE_SHA = '25cc469351349c291dd58b386f62b49e8b7876eeaa4579c8dc39f742a7bb4d4e'
PREPARE = OUT / 'stage5_qemu_prepare_variant_20261110_04'
PREPARE_SHA = '17272253837fe18a89725dbe01e1ec59dee9a6d117ce5ad27e25bbcc99bcb17f'
OWN = (*b.OWN, 'check_v2.py', 'run_v3.py', 'check_v3.py', 'test_run_v3.py')
old_recipes, old_selection = b.recipes, b.selection
old_service, old_gate = b.service_argv, b.checked_gate


def shared():
    require(isinstance(GATE_SHA, str) and re.fullmatch('[0-9a-f]{64}', GATE_SHA), 'Final directed reader not bound')
    path = HERE / 'shared/run_v10.py' if HERE != ORIGINAL else ORIGINAL.parent / 'gates/run_v10.py'
    return c.load(path, GATE_SHA, 'execution_v3_directed_reader')


def recipes(out, qemu, reports, python):
    rows = old_recipes(out, qemu, reports, python)
    for row in rows:
        row['checker'][2] = str(out / 'inputs/check_v3.py')
    return rows


def selection(out, qemu, reports, g, python=None):
    require(all(isinstance(h, str) and re.fullmatch('[0-9a-f]{64}', h)
                for h in (BUILD_SHA, BINARY_SHA, GATE_SHA)), 'Final BUILD07 identities not bound')
    require(qemu['prepared'] == str(PREPARE) and qemu['prepare_sha256'] == PREPARE_SHA,
            'Wrong repaired source variant')
    result = old_selection(out, qemu, reports, g, python)
    result.update(schema='stage5-qemu-unchanged-execution-v3', checker_rebind='v10-same-image-qbs',
                  historical_qbs_audit_used=False, qbs_checker_sha256=check.QBS_CHECK_SHA)
    return result


def service_argv(out, selection, review):
    return [str(out / 'inputs/run_v3.py') if x == str(out / 'inputs/run.py') else x
            for x in old_service(out, selection, review)]


def checked_gate(proof, kind):
    old_gate(proof, kind)
    if kind == 'qbs':
        require(proof['work']['trap_layers'] == {'helper': 46, 'decode': 3, 'access': 20} and
                proof['correction'] == 'qemu10.2-exact-helper-decode-tval' and
                proof['checker_rebind'] == 'v10-same-image-qbs' and
                proof['qemu_source'] == str(check.SOURCE) and proof['trap_sources_sha256'] == check.q.SOURCES,
                'Incomplete same-image exact QBS contract')


def prepare(out):
    require(HERE == ORIGINAL, 'Prepare from reviewed original source')
    out = b.output_path(out)
    require(not out.exists(), 'Fresh output required; do not retry')
    out.mkdir()
    (out / 'inputs').mkdir()
    (out / 'work').mkdir()
    g = shared()
    report = dict(state='FAIL', guest_executed=False)
    try:
        v = g.validator()
        qemu, pins = g.collect_qemu(BUILD, BUILD_SHA, v)
        fw, fpins = b.collect_firmware(g)
        g.merge(pins, fpins)
        for name, source in b.layout(g, v).items():
            target = out / 'inputs' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            g.merge(pins, {source: sha(source)})
        inventory = g.files(out / 'inputs')
        g.save(out / 'runner-inventory.json', inventory)
        g.merge(pins, inventory)
        s = selection(out, qemu, fw, g)
        g.save(out / 'selection.json', s)
        g.save(out / 'launch-receipt.json', dict(service_command=service_argv(out, s, '{SOURCE_PINS_SHA256}')))
        for label, argv, seconds in (
            ('host-tests', [s['python'], '-B', str(out / 'inputs/test_run_v3.py'), '-v'], 180),
            ('runtime-link', ['/usr/bin/ldd', qemu['executable']], 30)):
            with (out / (label + '.log')).open('x') as log:
                result = subprocess.run(argv, cwd=out, env=s['environment'], stdout=log,
                                        stderr=subprocess.STDOUT, timeout=seconds)
            g.save(out / (label + '.command.json'), dict(argv=argv, cwd=str(out),
                   timeout_seconds=seconds, returncode=result.returncode))
            require(result.returncode == 0, 'Preparation failed: ' + label)
        text = (out / 'runtime-link.log').read_text()
        require('not found' not in text, 'Missing runtime library')
        libs = re.findall(r'(?:=>\s+|^\s*)(/[^\s()]+)', text, re.M)
        require(libs, 'Missing runtime loader evidence')
        runtime = {str(p): sha(p) for item in libs for p in (Path(item), Path(item).resolve())}
        g.save(out / 'runtime-pins.json', runtime)
        g.merge(pins, runtime)
        for p in (s['python'], '/usr/bin/systemd-run', '/usr/bin/systemctl', '/usr/bin/ldd'):
            g.merge(pins, {p: sha(p)})
        g.merge(pins, g.files(out))
        g.verify(pins)
        g.save(out / 'source-pins.json', pins)
        report.update(state='PREPARED_NOT_EXECUTED', source_pins_sha256=sha(out / 'source-pins.json'))
    except BaseException as exc:
        report['error'] = repr(exc)
    g.save(out / 'prepared.json', report)
    require(report['state'] == 'PREPARED_NOT_EXECUTED', 'Preparation failed; preserve ' + str(out))
    return report


# The sealed worker still owns execution, receipts, exact command validation,
# source verification and same-image aggregation. Only these bindings change.
b.BUILD, b.BUILD_SHA, b.BINARY_SHA, b.GATE_SHA, b.OWN = BUILD, BUILD_SHA, BINARY_SHA, GATE_SHA, OWN
b.shared, b.recipes, b.selection = shared, recipes, selection
b.service_argv, b.checked_gate, b.prepare = service_argv, checked_gate, prepare
checked_result, checked_execution = b.checked_result, b.checked_execution


if __name__ == '__main__':
    def interrupted(sig, frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    raise SystemExit(b.main())
