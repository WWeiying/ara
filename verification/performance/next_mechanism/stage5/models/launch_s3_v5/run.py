#!/usr/bin/env python3
"""Strict BUILD07 S3 binding plus the sealed v3 service-budget policy."""
import argparse
import functools
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
WORKER_SHA = 'f09948cffe64a9154eb075482e24bd90283faec54f4f64661d51ba0e189fe838'
BASE = OUT/'stage5_models_execution_link_v2_20261110_01/inputs/run.py'
OWN = ('run.py', 'test_run.py')
GUEST_SECONDS, SERVICE_SECONDS = 5400, 10800
PLACEHOLDER = '@LAUNCH_PINS_SHA256@'
ROOT = Path('/home/wangwy/openproject/ara_dsa')
ORIGINAL = ROOT/'verification/performance/next_mechanism/stage5/models/launch_s3_v5'
V2 = ORIGINAL.parent/'execution_v2'
V2_SOURCE_SHA = '1bbbb4c72b42ab95522501e21287d854703dd4dc13d0d71f295e6cb6b04c020c'
READER = ROOT/'verification/performance/next_mechanism/stage5/qemu/execution/run_v4.py'
READER_SHA = 'd416c71665df4fb9995d97563493c2cfc17cd02546bf679d3a5e8cbc9a594d55'
V3 = OUT/'stage5_models_launch_host_20261110_02'
V3_RECEIPT_SHA = 'fbaca36f846643f5b1e2d0b041168d20fbf82e285af9abc001d815fadf5c697f'


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''): h.update(data)
    return h.hexdigest()


def read(path):
    def pairs(rows):
        result = {}
        for k, v in rows:
            require(k not in result, 'Duplicate JSON key'); result[k] = v
        return result
    def bad(value): raise ValueError('Nonfinite JSON: '+value)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=bad)


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False); f.write('\n')


def identity():
    files = {name: sha(HERE/name) for name in OWN}
    return hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def binding_pins():
    require(sha(READER) == READER_SHA and sha(V3/'result.json') == V3_RECEIPT_SHA, 'Reader/budget ancestry drift')
    pins = {str(READER): READER_SHA, str(V3/'result.json'): V3_RECEIPT_SHA}
    for name, digest in read(V3/'result.json')['source_files'].items():
        require(sha(V3/'inputs'/name) == digest, 'Sealed v3 source drift')
        pins[str(V3/'inputs'/name)] = digest
    for name in OWN:
        require(sha(HERE/name) == sha(ORIGINAL/name), 'Binding source identity')
        pins[str(ORIGINAL/name)] = sha(HERE/name)
    return pins


ADMITTED_IMAGE = dict(
    qemu_build=str(OUT/'stage5_qemu_build_20261110_07'),
    qemu_build_receipt_sha256='85a4939f7419c706280f6959c89a25f322f6bf5b0caf7c3bb7c1c60b7305c701',
    executable_sha256='1f4619e1573ed6626b259912d6780ac9d40e8cca8ed38ec32694a0b1d399388a',
    qemu_prepare=str(OUT/'stage5_qemu_prepare_variant_20261110_04'),
    qemu_prepare_receipt_sha256='17272253837fe18a89725dbe01e1ec59dee9a6d117ce5ad27e25bbcc99bcb17f')


def admitted_report(report):
    require(all(report.get(key) == value for key, value in ADMITTED_IMAGE.items()), 'Only the same BUILD07 image is admitted')
    require(not any(key in report for key in ('scoped_qbs_audit', 'scoped_qbs_audit_sha256',
            'original_qbs_execution', 'original_qbs_execution_state', 'checker_correction_explicit')),
            'Historical BUILD06 scoped audit is not BUILD07 admission')


def bind_reader(module):
    original = module.checked_s3
    module.S3_READER = READER
    def checked(reader, reader_sha, result_dir, result_sha):
        require(Path(reader).resolve() == READER and reader_sha == READER_SHA and sha(READER) == READER_SHA,
                'Only the explicit frozen S3 successor is admitted')
        report, pins = original(reader, reader_sha, result_dir, result_sha)
        admitted_report(report)
        return report, pins
    module.checked_s3 = checked
    return module


def model_binding(model):
    contract, pins = read(model/'contract.json'), read(model/'source-pins.json')
    require(contract['s3_reader'] == str(READER) and contract['s3_reader_sha256'] == READER_SHA,
            'Model was not prepared with the exact S3 successor')
    admitted_report(contract['s3'])
    require(all(pins.get(path) == digest for path, digest in binding_pins().items()), 'Unbound reader adapter')
    return contract


def model_prepare(args):
    require(HERE == ORIGINAL and identity() == args.binding_source_sha256, 'Reviewed binding source required')
    base = worker(V2/'run.py'); ancestry = base.sealed_inputs
    base.sealed_inputs = lambda: dict(ancestry(), **binding_pins())
    args.action = 'prepare'; args.source_sha256 = V2_SOURCE_SHA
    args.s3_reader = READER; args.s3_reader_sha256 = READER_SHA
    base.prepare(args)


def worker(path):
    require(sha(path) == WORKER_SHA, 'Not the frozen execution-v2 worker')
    spec = importlib.util.spec_from_file_location('sealed_model_execution_v2', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    require(module.HERE == Path(path).resolve().parent, 'Worker identity changed')
    return bind_reader(module)


def command(base, model, pins_sha, prepared_sha, out, review=PLACEHOLDER):
    argv = base.service_command(model, pins_sha, prepared_sha)
    old = '--property=RuntimeMaxSec=6300'
    require(argv.count(old) == 1 and sum(v.startswith('--property=RuntimeMaxSec=') for v in argv) == 1,
            'Original service bound changed')
    argv[argv.index(old)] = '--property=RuntimeMaxSec='+str(SERVICE_SECONDS)
    script = str(model/'inputs/run.py'); require(argv.count(script) == 1, 'Ambiguous original worker')
    at = argv.index(script)
    require(argv[at-2:at] == ['/usr/bin/python3', '-B'] and argv[at+1:] ==
            ['run', '--output', str(model), '--review-sha256', pins_sha,
             '--review-prepare-sha256', prepared_sha], 'Original worker recipe changed')
    return argv[:at]+[str(out/'inputs/run.py'), 'run', '--output', str(out), '--review-sha256', review]


def fresh(out):
    require(out == out.resolve() and out.parent == OUT and out.name.startswith('stage5_models_launch_') and
            not out.exists(), 'Fresh independent launcher output required')


def prepare(args):
    out, model = args.output.absolute(), args.model_output.resolve(); fresh(out)
    require(model.parent == OUT and model.name.startswith('stage5_models_execution_'), 'Model output scope')
    model_binding(model)
    base = worker(model/'inputs/run.py')
    argv = command(base, model, args.model_pins_sha256, args.model_prepare_sha256, out)
    contract = dict(schema='stage5-model-launch-s3-v5', model_output=str(model),
        model_pins_sha256=args.model_pins_sha256, model_prepare_sha256=args.model_prepare_sha256,
        model_worker_sha256=WORKER_SHA, s3_reader=str(READER), s3_reader_sha256=READER_SHA,
        admitted_image=ADMITTED_IMAGE, historical_qbs_audit_used=False,
        binding_source_sha256=identity(), guest_seconds=GUEST_SECONDS, service_seconds=SERVICE_SECONDS,
        previous_service_seconds=6300,
        budget_reason='Full-closure pre/post identity replay and content checking; guest timeout unchanged',
        shared_non_guest_allowance_seconds=SERVICE_SECONDS-GUEST_SECONDS,
        allowance_is_not_a_runtime_measurement=True, automatic_retry=False,
        model_checker_or_identity_rules_relaxed=False, s3_reader_successor_rebound=True,
        source_files={n: sha(HERE/n) for n in OWN})
    out.mkdir(); (out/'inputs').mkdir()
    pins = {str(model/'inputs/run.py'): WORKER_SHA, str(model/'source-pins.json'): args.model_pins_sha256,
            str(model/'prepare.json'): args.model_prepare_sha256, **binding_pins()}
    for name in OWN:
        data = (HERE/name).read_bytes(); (out/'inputs'/name).write_bytes(data)
        pins[str(HERE/name)] = contract['source_files'][name]
        pins[str(out/'inputs'/name)] = contract['source_files'][name]
    save(out/'contract.json', contract); save(out/'service-command.json', argv)
    for name in ('contract.json', 'service-command.json'): pins[str(out/name)] = sha(out/name)
    base.verify(pins); save(out/'source-pins.json', pins)
    result = dict(state='LAUNCH_BUDGET_PREPARED_NOT_EXECUTED', source_pins_sha256=sha(out/'source-pins.json'),
                  guest_seconds=GUEST_SECONDS, service_seconds=SERVICE_SECONDS, model_executed=False)
    save(out/'prepare.json', result); print(json.dumps(result, sort_keys=True))


def checked(out, review):
    require(sha(out/'source-pins.json') == review, 'Unreviewed launcher pins')
    pins = read(out/'source-pins.json')
    for path, digest in pins.items(): require(sha(path) == digest, 'Launch pin drift: '+path)
    c = read(out/'contract.json'); model = Path(c['model_output'])
    require(c['admitted_image']==ADMITTED_IMAGE and c['historical_qbs_audit_used'] is False, 'Launch image binding drift')
    require(c['s3_reader']==str(READER) and c['s3_reader_sha256']==READER_SHA and
            c['binding_source_sha256']==identity(), 'Launch reader-binding drift')
    model_binding(model)
    require(c['guest_seconds'] == GUEST_SECONDS and c['service_seconds'] == SERVICE_SECONDS and
            c['automatic_retry'] is False and c['model_checker_or_identity_rules_relaxed'] is False and
            c['s3_reader_successor_rebound'] is True, 'Launch contract drift')
    base = worker(model/'inputs/run.py')
    require(read(out/'service-command.json') == command(base, model, c['model_pins_sha256'],
            c['model_prepare_sha256'], out), 'Launch recipe drift')
    return c, model, base


class Timing:
    def __init__(self, path):
        self.path, self.serial, self.depth, self.finished = path, 0, 0, []
        with self.path.open('x'): pass

    def emit(self, row):
        with self.path.open('a') as f:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n'); f.flush()

    def wrap(self, name, function):
        @functools.wraps(function)
        def measured(*args, **kwargs):
            self.serial += 1; serial = self.serial; depth = self.depth; self.depth += 1
            start = time.monotonic_ns()
            self.emit(dict(event='start', phase=name, id=serial, depth=depth,
                           monotonic_ns=start, wall_time_ns=time.time_ns()))
            state = 'returned'
            try: return function(*args, **kwargs)
            except BaseException:
                state = 'raised'; raise
            finally:
                self.depth -= 1
                row = dict(event='end', phase=name, id=serial, depth=depth, status=state,
                           elapsed_seconds=(time.monotonic_ns()-start)/1e9)
                self.finished.append(row); self.emit(row)
        return measured


def instrument(base, model, timing):
    # All original functions execute exactly once; nested durations are inclusive.
    base.verify = timing.wrap('identity_verify', base.verify)
    base.checked_s3 = timing.wrap('s3_checked_result_replay', base.checked_s3)
    original_load = base.load
    def load(path, name):
        module = original_load(path, name)
        if Path(path) == model/'inputs/check.py': module.check = timing.wrap('model_content_check', module.check)
        return module
    base.load = load
    original = base.subprocess
    class TimedSubprocess:
        def __getattr__(self, name): return getattr(original, name)
        def Popen(self, *args, **kwargs):
            child = original.Popen(*args, **kwargs)
            timing.emit(dict(event='guest_spawn', pid=child.pid, monotonic_ns=time.monotonic_ns(), wall_time_ns=time.time_ns()))
            child.wait = timing.wrap('guest_wait', child.wait)
            return child
    base.subprocess = TimedSubprocess()


def execute(out, review):
    require(HERE == out/'inputs', 'Use the frozen launcher')
    require(not any((out/n).exists() for n in ('attempt.json', 'result.json', 'timings.jsonl')), 'No retry')
    start = time.monotonic_ns(); c, model, base = checked(out, review)
    ownership = base.service_owner(model)
    actual = subprocess.check_output(['systemctl', '--user', 'show', ownership['unit'],
                                      '--property=RuntimeMaxUSec', '--value'], text=True).strip()
    require(actual == '3h', 'Actual service bound differs from the 10800-second contract')
    save(out/'attempt.json', dict(**ownership, service_seconds=SERVICE_SECONDS,
         guest_seconds=GUEST_SECONDS, started_wall_time_ns=time.time_ns(), automatic_retry=False))
    timing = Timing(out/'timings.jsonl'); instrument(base, model, timing)
    result = dict(state='FAIL', guest_seconds=GUEST_SECONDS, service_seconds=SERVICE_SECONDS,
                  model_checker_or_identity_rules_relaxed=False, s3_reader_successor_rebound=True, automatic_retry=False)
    try:
        args = argparse.Namespace(output=model, review_sha256=c['model_pins_sha256'],
                                  review_prepare_sha256=c['model_prepare_sha256'])
        ok = base.execute(args)
        checked(out, review)
        result.update(state='SEALED_MODEL_WORKER_PASS' if ok else 'SEALED_MODEL_WORKER_FAIL',
                      model_result_sha256=sha(model/'result.json'), post_launcher_pins_match=True)
    except BaseException as e: result['error'] = repr(e)
    result.update(elapsed_seconds=(time.monotonic_ns()-start)/1e9, phases=timing.finished,
                  nested_timings_are_inclusive=True, timings_sha256=sha(out/'timings.jsonl'))
    save(out/'result.json', result); print(json.dumps(result, sort_keys=True))
    return result['state'] == 'SEALED_MODEL_WORKER_PASS'


def host(out):
    fresh(out); out.mkdir(); (out/'inputs').mkdir()
    pins = {str(BASE): WORKER_SHA, **binding_pins()}; worker(BASE)
    for name in OWN:
        (out/'inputs'/name).write_bytes((HERE/name).read_bytes())
        pins[str(HERE/name)] = sha(HERE/name); pins[str(out/'inputs'/name)] = sha(out/'inputs'/name)
    with (out/'tests.log').open('x') as log:
        done = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_run', '-v'], cwd=out/'inputs',
                              stdout=log, stderr=subprocess.STDOUT, timeout=60)
    pins[str(out/'tests.log')] = sha(out/'tests.log')
    for path, digest in pins.items(): require(sha(path) == digest, 'Host pin drift')
    save(out/'source-pins.json', pins)
    result = dict(state='HOST_PASS_NOT_MODEL' if done.returncode == 0 else 'FAIL',
                  binding_source_sha256=identity(), s3_reader_sha256=READER_SHA, admitted_image=ADMITTED_IMAGE,
                  service_seconds=SERVICE_SECONDS, guest_seconds=GUEST_SECONDS,
                  source_files={n: sha(HERE/n) for n in OWN}, pins=len(pins),
                  source_pins_sha256=sha(out/'source-pins.json'), model_executed=False)
    save(out/'result.json', result); print(json.dumps(result, sort_keys=True)); require(done.returncode == 0, 'Host tests failed')


def main():
    p = argparse.ArgumentParser(allow_abbrev=False); sub = p.add_subparsers(dest='action', required=True)
    for action in ('host', 'model-prepare', 'prepare', 'service-command', 'run'):
        a = sub.add_parser(action, allow_abbrev=False); a.add_argument('--output', type=Path, required=True)
        if action == 'model-prepare':
            for name in ('library-prepare', 'library-build', 's3-result'):
                a.add_argument('--'+name, type=Path, required=True)
            for name in ('library-sha256', 'case', 's3-sha256', 'binding-source-sha256'):
                a.add_argument('--'+name, required=True)
        if action == 'prepare':
            a.add_argument('--model-output', type=Path, required=True)
            a.add_argument('--model-pins-sha256', required=True); a.add_argument('--model-prepare-sha256', required=True)
        if action in ('service-command', 'run'): a.add_argument('--review-sha256', required=True)
    args = p.parse_args(); out = args.output.resolve()
    if args.action == 'host': host(out)
    elif args.action == 'model-prepare': model_prepare(args)
    elif args.action == 'prepare': prepare(args)
    elif args.action == 'service-command':
        c, model, base = checked(out, args.review_sha256)
        print(json.dumps(command(base, model, c['model_pins_sha256'], c['model_prepare_sha256'], out, args.review_sha256), indent=2))
    else: return 0 if execute(out, args.review_sha256) else 1
    return 0


if __name__ == '__main__':
    def interrupted(signum, frame): raise InterruptedError('Signal '+str(signum))
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupted)
    sys.exit(main())
