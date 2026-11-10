#!/usr/bin/env python3
"""Service owner for paired builds, smoke qualification and bounded projection jobs."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = ROOT / 'verification/performance/chain_profile/build_soc.py'
FILES = ('run_campaign.py', 'build_soc.py', 'soc_loan_monitor.sv',
         'run_projection.py', 'check_projection.py', 'run_smokes.py')


def helper():
    spec = importlib.util.spec_from_file_location('stage2_campaign_base', BASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def software_paths():
    return {f'{op}_m{mode}': OUT / f'stage2_qwen3_{op}_m{mode}_build_20261109_04'
            for op in ('attn', 'ffn') for mode in (4, 8)}


def prepare(args):
    base = helper()
    out = args.output.resolve()
    base.require(out.parent == OUT and not out.exists(), 'Fresh direct signoff campaign required')
    revision = subprocess.check_output(['git', '-C', ROOT, 'rev-parse', args.revision + '^{commit}'], text=True).strip()
    builds = software_paths()
    for name, directory in builds.items():
        report = json.loads((directory / 'build.json').read_text())
        mode = int(name[-1])
        base.require(report['state'] == 'BUILT_NOT_EXECUTED' and report['trials'] == [mode, mode] and
                     report['flag_seeds'] == [0, 8] and report['n'] == (64 if name.startswith('attn') else 128),
                     'Projection firmware scope differs')
        base.require(base.digest(directory / 'source-pins.json') == report['source_pins_sha256'],
                     'Firmware inventory drift')
        base.verify(json.loads((directory / 'source-pins.json').read_text()))
    # Both modes use identical captured tensors and independent golden outputs.
    for op in ('attn', 'ffn'):
        for name in ('input_f32.bin', 'weights_r4.bin', 'expected_q8.bin', 'expected.bin', 'flags.bin'):
            base.require(base.digest(builds[f'{op}_m4'] / 'data' / name) ==
                         base.digest(builds[f'{op}_m8'] / 'data' / name), 'Mode input/oracle mismatch')
    for name in FILES:
        base.require((HERE / name).is_file(), 'Missing reviewed campaign helper: ' + name)
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    pins = {str(BASE): base.digest(BASE)}
    for name in FILES:
        source, target = HERE / name, inputs / name
        shutil.copy2(source, target)
        pins[str(source)] = pins[str(target)] = base.digest(source)
    base.save(out / 'selection.json', dict(revision=revision, smoke_build=str(args.smoke_build.resolve(strict=True)),
              firmware={k: str(v) for k, v in builds.items()}, parallel_builds=2, parallel_runs=4,
              per_run_seconds=10800, prefix=out.name, whole_model=False))
    pins[str(out / 'selection.json')] = base.digest(out / 'selection.json')
    base.verify(pins)
    base.save(out / 'source-pins.json', pins)
    base.save(out / 'status.json', dict(state='PREPARED_NOT_EXECUTED', child_pids={}, completed=[]))
    print(inputs / 'run_campaign.py', flush=True)


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_campaign.py':
        raise ValueError('Execute frozen service owner only')
    base = helper()
    config = json.loads((out / 'selection.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    lock, failed = threading.Lock(), threading.Event()
    state = dict(state='PREFLIGHT', child_pids={}, completed=[], owner_pid=os.getpid(),
                 started=datetime.now(timezone.utc).isoformat())
    results = {}

    def publish():
        base.save(out / 'status.json', state)

    def command(name, argv, timeout):
        base.verify(pins)
        base.save(out / (name + '.command.json'), list(map(str, argv)))
        with (out / (name + '.log')).open('x') as stream:
            child = subprocess.Popen(list(map(str, argv)), cwd=out, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            with lock:
                state['child_pids'][name] = child.pid
                publish()
            try:
                rc = child.wait(timeout=timeout)
            except BaseException:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                child.wait(timeout=30)
                raise
            finally:
                with lock:
                    state['child_pids'].pop(name, None)
                    publish()
        base.require(rc == 0, name + ' failed; original log preserved')
        base.verify(pins)

    def phase(label, jobs, workers):
        with lock:
            state['state'] = label
            publish()
        def guarded(name, work):
            if failed.is_set():
                return dict(state='NOT_DISPATCHED_AFTER_FAILURE')
            try:
                value = work()
                with lock:
                    state['completed'].append(name)
                    publish()
                return value
            except BaseException as exc:
                failed.set()
                return dict(state='FAIL', error=repr(exc))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(guarded, name, work): name for name, work in jobs.items()}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
                with lock:
                    base.save(out / 'progress.json', results)
        base.require(not failed.is_set(), 'A worker failed; no later phase dispatched')

    def build(arm, enabled):
        directory = OUT / (config['prefix'] + '_' + arm + '_build')
        command(arm + '_prepare', [sys.executable, '-B', HERE / 'build_soc.py', directory,
                '--revision', config['revision'], '--enabled', enabled], 1800)
        command(arm + '_compile', [sys.executable, '-B', directory / 'inputs/build_soc.py',
                                   directory, '--execute'], 7500)
        report = json.loads((directory / 'build.json').read_text())
        base.require(report['state'] == 'STAGE2_SOC_BUILT_NOT_EXECUTED' and
                     report['post_pins_match'], 'Unsealed/failed SoC build')
        return dict(state='PASS', directory=str(directory), report=str(directory / 'build.json'))

    def projection(arm, key):
        directory = OUT / (config['prefix'] + '_' + arm + '_' + key)
        soc = results['build_' + arm]['directory']
        command(arm + '_' + key + '_prepare', [sys.executable, '-B', HERE / 'run_projection.py',
                directory, '--soc', soc, '--software', config['firmware'][key], '--timeout', '10800'], 600)
        command(arm + '_' + key + '_execute', [sys.executable, '-B', directory / 'inputs/run_projection.py',
                                              directory, '--execute'], 11500)
        report = json.loads((directory / 'result.json').read_text())
        base.require(report['state'] == 'PASS', 'Projection worker did not pass')
        return dict(state='PASS', directory=str(directory), report=str(directory / 'result.json'))

    try:
        base.verify(pins)
        phase('PAIRED_SOC_BUILDS', {f'build_{arm}': lambda arm=arm, enabled=enabled: build(arm, enabled)
              for arm, enabled in (('baseline', 0), ('candidate', 1))}, 2)
        baseline, candidate = (Path(results['build_' + arm]['directory']) for arm in ('baseline', 'candidate'))
        base.require(base.digest(baseline / 'source.tar') == base.digest(candidate / 'source.tar'),
                     'SoC arms do not use the same committed RTL')
        # Smoke execution is a prerequisite, not a substitute for paired calls.
        def smoke(arm):
            directory = OUT / (config['prefix'] + '_' + arm + '_smokes')
            command(arm + '_smokes', [sys.executable, '-B', HERE / 'run_smokes.py',
                    '--soc-build', results['build_' + arm]['directory'],
                    '--software-build', config['smoke_build'], '--output', directory], 7200)
            report = json.loads((directory / 'report.json').read_text())
            base.require(report['state'] == 'PASS', 'SoC smoke qualification failed')
            return dict(state='PASS', report=str(directory / 'report.json'))
        phase('SOC_SMOKE_QUALIFICATION', {f'smoke_{arm}': lambda arm=arm: smoke(arm)
                                         for arm in ('baseline', 'candidate')}, 2)
        phase('PAIRED_COMPLETE_SOFTWARE_CALLS', {f'{arm}_{key}': lambda arm=arm, key=key: projection(arm, key)
              for key in config['firmware'] for arm in ('baseline', 'candidate')}, 4)
        summary = {}
        for op in ('attn', 'ffn'):
            measurements = {f'{arm}_m{mode}': json.loads(Path(results[f'{arm}_{op}_m{mode}']['report']).read_text())['measured']['trials']
                            for arm in ('baseline', 'candidate') for mode in (4, 8)}
            summary[op] = []
            for trial in range(2):
                cycles = {name: rows[trial]['total'] for name, rows in measurements.items()}
                best = min(cycles['baseline_m4'], cycles['baseline_m8'])
                summary[op].append(dict(trial=('first', 'repeat')[trial], cycles=cycles,
                    best_baseline_cycle_reduction=1-cycles['candidate_m8']/best,
                    same_m8_hardware_cycle_reduction=1-cycles['candidate_m8']/cycles['baseline_m8']))
        base.verify(pins)
        base.save(out / 'report.json', dict(state='PAIRED_CALLS_CHECKED', results=results, summary=summary,
             performance_target_met=all(v[1]['best_baseline_cycle_reduction'] >= 0.2 for v in summary.values()),
             scope='Real full-K projection slices and complete SDK calls; not whole-model inference',
             whole_model=False, post_pins_match=True))
        state.update(state='PAIRED_CALLS_CHECKED', finished=datetime.now(timezone.utc).isoformat())
        publish()
        return 0
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc), finished=datetime.now(timezone.utc).isoformat())
        publish()
        base.save(out / 'report.json', dict(state='FAIL', error=repr(exc), results=results))
        return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('output', type=Path)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--smoke-build', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        def interrupted(sig, _frame):
            raise InterruptedError('Signal ' + str(sig))
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, interrupted)
        raise SystemExit(execute(args.output.resolve()))
    if args.smoke_build is None:
        parser.error('--smoke-build is required')
    prepare(args)
