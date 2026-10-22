#!/usr/bin/env python3
"""Prepare-only by default: replay final04 arithmetic on the candidate02 image."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time

sys.dont_write_bytecode = True
import run as shared
from prepare import save, sha

HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
OLD = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign')
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image')
EXTENSION = REVIEW / 'extension_overlap/final04_successor01'
EXTENDED8 = REVIEW / 'masked_translation/sv39_extended/candidate02_extended8_01'
GROUPS = {'extension-original': 1, 'large-offset': 6, 'singles': 6,
          'combined': 1, 'extended': 5, 'gather': 2, 'comparison': 5,
          'flags-sequence': 1, 'reduction-epoch': 1, 'comparison-matrix': 4,
          'extension-matrix': 6}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text())


def owned(path):
    path = path.resolve()
    require(path.is_relative_to(HERE) and path != HERE, 'New plan directory must be under integration/')
    return path


def verify_pins(pins):
    for path, digest in pins.items():
        require(sha(Path(path)) == digest, 'Pinned input drift: ' + path)


def image_context():
    ledger = read(IMAGE / 'image.json')
    snapshot = Path(ledger['snapshot'])
    require(sha(snapshot / 'snapshot.json') == ledger['snapshot_sha256'], 'Snapshot identity drift')
    repo = shared.sealed(snapshot)
    framework = shared.framework(repo)
    simv = Path(ledger['simv'])
    require(framework[3](simv) == ledger['files'], 'Simulation image drift')
    require(sha(simv.parent / 'simulator.conf') == ledger['configuration_sha256'], 'Configuration drift')
    manifest = simv.parent / 'vcs_source_manifest.json'
    require(sha(manifest) == ledger['manifest_sha256'], 'Compiled manifest drift')
    from ara_verify.vcs_source_manifest import collect
    captured = read(manifest)
    require(collect(Path(captured['filelist']), repo,
                    [Path(p) for p in captured['extra_sources']]) == captured['files'], 'Compiled sources drift')
    import ara_verify.runner
    require(Path(ara_verify.runner.__file__).is_relative_to(repo), 'Wrong runner import root')
    return ledger, repo, framework


def budget(group, observed):
    if group == 'extension-matrix':
        return 1200
    require(observed['status'] == 'PASS', 'Non-extension budget requires measured PASS')
    return max(180, 60 * math.ceil(1.5 * observed['elapsed_s'] / 60))


def checked_result(result, entry, text, cancel_event):
    if result.status == 'PASS' and not shared.oracle_complete(entry, text):
        result.status, result.reason = 'FAIL', 'missing original architectural oracle completion'
    if result.status not in ('PASS', 'DRY_RUN'):
        cancel_event.set()
    return result


def runner_class(base, entries):
    class ArithmeticRunner(base):
        def _run_test(self, test, image):
            try:
                result = super()._run_test(test, image)
                text = (result.artifact_dir / 'console.log').read_text() if result.status == 'PASS' else ''
                # No gather exemption: first failure also cancels queued and live peers.
                return checked_result(result, entries[test.name], text, self.cancel_event)
            except BaseException:
                self.cancel_event.set()
                raise
    return ArithmeticRunner


def execute(plan, output, dry_run):
    ledger, repo, (base, options_type, testcase, _) = image_context()
    entries = {c['id']: c for c in plan['cases']}
    tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['original_name'], c['timeout_s'])
             for c in plan['cases']]
    # timeout=None deliberately retains each TestCase's individual bound.
    options = options_type(repo, output, 'default', 4, 1, dry_run,
                           False, True, Path(ledger['simv']), True, None)
    return runner_class(base, entries)(options, tests, sys.argv).run()


def plan(out):
    out.mkdir(parents=True, exist_ok=False)
    ledger, repo, _ = image_context()
    previous = read(OLD / 'plan.json')
    pins = {}

    def pin(path):
        pins[str(path)] = sha(path)
        return pins[str(path)]

    for path in (Path(__file__), HERE / 'run.py', HERE / 'prepare.py',
                 OLD / 'plan.json', IMAGE / 'image.json',
                 Path(ledger['snapshot']) / 'snapshot.json',
                 Path(ledger['simv']).parent / 'simulator.conf',
                 Path(ledger['simv']).parent / 'vcs_source_manifest.json'):
        pin(path)
    pins.update(ledger['files'])
    pins.update({str(repo / name): digest for name, digest in
                 read(Path(ledger['snapshot']) / 'snapshot.json')['files'].items()})
    cases = []
    observed_groups = {}
    for stage in previous['stages']:
        group = stage['name']
        if group in ('build-image', 'smokes'):
            continue
        require(group in GROUPS and len(stage['cases']) == GROUPS[group], 'Unexpected final04 group')
        observed_groups[group] = len(stage['cases'])
        programs_path = Path(stage['argv'][stage['argv'].index('--programs')+1]) / 'programs.json'
        require(pin(programs_path) == previous['inputs_sha256'][str(programs_path)], 'Original manifest drift')
        programs = read(programs_path)
        summary_path = OLD / group / 'summary.json'
        pin(summary_path)
        observations = {r['name']: r for r in read(summary_path)}
        for name in stage['cases']:
            old_dir = OLD / group / 'tests' / name
            inputs_path = old_dir / 'inputs.json'
            pin(inputs_path)
            inputs = read(inputs_path)
            source = old_dir / 'input.elf'
            digest = pin(source)
            entry = programs['programs'][name]
            require(digest == inputs['binary']['sha256'] == entry['sha256'], 'Original ELF mismatch')
            identity = group + '__' + name
            destination = out / 'inputs' / (identity + '.elf')
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(source, destination)
            require(pin(destination) == digest, 'Copied ELF mismatch')
            destination.chmod(0o444)
            markers = entry.get('pass_markers', ['BOARD_REPLAY_PASS',
                         *['BOARD_CASE_PASS ' + n for n in entry['cases']]])
            require(markers and all(isinstance(m, str) and m for m in markers), 'Empty oracle')
            cases.append(dict(id=identity, group=group, original_name=name,
                elf=str(destination), sha256=digest, original_elf=str(source),
                pass_markers=markers, cases=entry['cases'],
                timeout_s=budget(group, observations[name]), observed_final04=observations[name],
                budget_basis='1200s measured extension work bound' if group == 'extension-matrix'
                             else '1.5x observed PASS, rounded up to60s, minimum180s'))
    require(observed_groups == GROUPS and len(cases) == 38, 'Must contain exactly38 original cases')
    require(len({c['id'] for c in cases}) == 38, 'Duplicate case identity')
    data = dict(schema_version=1, status='PREPARED_NOT_LAUNCHED', image=str(IMAGE),
        image_sha256=sha(IMAGE / 'image.json'), snapshot_sha256=ledger['snapshot_sha256'],
        simv=ledger['simv'], jobs=4, seed=1, stop_first_fail=True,
        cases=cases, pins=pins, excludes='10 candidate02-passing smokes; no new software or RTL build',
        budget_basis='final04 measured per-case walltime; extension1200 from final04_successor01/plan.json',
        gates=dict(parent_review='explicit --authorize-run and --approved-plan-sha256 required',
            extended8=str(EXTENDED8 / 'complete.json'), extension_terminal=str(EXTENSION / 'status.json')),
        scope='New candidate02 arithmetic acceptance only; final04 results are budget evidence, not candidate02 PASS')
    pin(EXTENSION / 'plan.json')
    pin(EXTENDED8 / 'preflight.json')
    save(out / 'plan.json', data)
    results = execute(data, out / 'dryrun', True)
    require(len(results) == 38 and all(r.status == 'DRY_RUN' for r in results), 'Dry run unexpectedly executed')
    verify_pins(pins)
    save(out / 'preflight.json', dict(status='PASS_PREPARE_ONLY', VCS_started=False,
        count=38, jobs=4, plan_sha256=sha(out / 'plan.json'),
        dryrun_summary_sha256=sha(out / 'dryrun/summary.json'),
        extended8_gate_checked_at_launch_only=True, parent_approval=False))
    print('PREPARED_NOT_LAUNCHED 38 cases; plan SHA256 ' + sha(out / 'plan.json'))


def validate_extended8(complete, analysis, metadata, summary, inputs, ledger, image_sha):
    require(complete.get('status') == 'CANDIDATE02_EXTENDED8_PASS' and
            complete.get('returncode') == 0, 'Aquinas extended8 not terminal PASS')
    require(complete['image_sha256'] == image_sha, 'Extended8 ran a different image ledger')
    require(analysis['status'] == 'EXTENDED8_CSV_ORACLE_PASS', 'Extended8 CSV oracle not PASS')
    require(metadata['status'] == 'COMPLETE' and metadata['simv'] == ledger['simv'], 'Extended8 run incomplete/wrong simv')
    require(len(summary) == 1 and summary[0]['name'] == 'extended8' and
            summary[0]['status'] == 'PASS' and summary[0]['returncode'] == 0, 'Extended8 simulation not PASS')
    require(inputs['simv']['image_sha256'] == ledger['files'], 'Extended8 actual image differs')


def gate(plan_data):
    terminal = read(EXTENSION / 'status.json')
    require(terminal.get('status') in ('PASS', 'FAIL') and terminal.get('ended'),
            'Current three extension jobs have not completed; refuse without polling')
    require(len(terminal.get('results', [])) == 3, 'Incomplete extension successor results')
    complete = read(EXTENDED8 / 'complete.json')
    analysis_path = EXTENDED8 / 'csv_analysis.json'
    require(sha(analysis_path) == complete['analysis_sha256'], 'Extended8 analysis drift')
    ledger = read(IMAGE / 'image.json')
    metadata = read(EXTENDED8 / 'run/run.json')
    summary = read(EXTENDED8 / 'run/summary.json')
    input_path = EXTENDED8 / 'run/tests/extended8/inputs.json'
    inputs = read(input_path)
    validate_extended8(complete, read(analysis_path), metadata, summary, inputs,
                       ledger, plan_data['image_sha256'])
    preflight = read(EXTENDED8 / 'preflight.json')
    require(inputs['binary']['sha256'] == preflight['elf_sha256'], 'Extended8 different ELF')
    verify_pins(preflight['pins'])
    paths = [EXTENSION / 'status.json', EXTENDED8 / 'complete.json', analysis_path,
             EXTENDED8 / 'run/run.json', EXTENDED8 / 'run/summary.json', input_path,
             EXTENDED8 / 'run/tests/extended8/input.elf']
    pins = {str(p): sha(p) for p in paths}
    require(pins[str(paths[-1])] == inputs['binary']['sha256'], 'Extended8 input snapshot drift')
    return pins


def work(out, authorized, approved_sha):
    require(authorized, 'No launch: parent review and explicit --authorize-run required')
    require(approved_sha == sha(out / 'plan.json'), 'Parent-approved plan SHA mismatch')
    data = read(out / 'plan.json')
    verify_pins(data['pins'])
    try:
        gate_pins = gate(data)
    except Exception as error:
        save(out / ('gate_refusal_' + str(time.time_ns()) + '.json'),
             dict(status='REFUSED_NOT_LAUNCHED', error=str(error)))
        raise
    image_context()
    with (out / 'launch.json').open('x') as stream:
        json.dump(dict(started=time.time(), pid=os.getpid(), plan_sha256=approved_sha,
                       gate_pins=gate_pins, jobs=4), stream, indent=2)
    try:
        results = execute(data, out / 'replay', False)
        verify_pins(data['pins'])
        verify_pins(gate_pins)
        image_context()
        passed = len(results) == 38 and all(r.status == 'PASS' for r in results)
        save(out / 'complete.json', dict(status='PASS_38_CANDIDATE02' if passed else 'NOT_PASS',
             plan_sha256=approved_sha, image_sha256=data['image_sha256'],
             results=[dict(name=r.name, status=r.status, elapsed_s=r.elapsed_s) for r in results],
             finished=time.time(), scope=data['scope']))
        return int(not passed)
    except BaseException as error:
        save(out / 'complete.json', dict(status='ERROR_NOT_PASS', error=str(error), finished=time.time()))
        raise


def self_test():
    import threading
    import unittest
    from types import SimpleNamespace

    class Tests(unittest.TestCase):
        def test_scope(self):
            self.assertEqual(sum(GROUPS.values()), 38)
            self.assertNotIn('smokes', GROUPS)

        def test_budgets(self):
            self.assertEqual(budget('comparison-matrix', dict(status='PASS', elapsed_s=574.3)), 900)
            self.assertEqual(budget('extension-matrix', dict(status='TIMEOUT')), 1200)
            self.assertEqual(budget('gather', dict(status='PASS', elapsed_s=29.5)), 180)

        def test_gather_failure_cancels(self):
            event = threading.Event()
            result = SimpleNamespace(status='FAIL', reason='', name='gather_original')
            checked_result(result, {}, '', event)
            self.assertTrue(event.is_set())

        def test_missing_oracle_cancels(self):
            event = threading.Event()
            result = SimpleNamespace(status='PASS', reason='')
            checked_result(result, dict(pass_markers=['BOARD_REPLAY_PASS', 'ORIGINAL_ORACLE']),
                           'BOARD_REPLAY_PASS', event)
            self.assertEqual(result.status, 'FAIL')
            self.assertTrue(event.is_set())

        def test_success_and_dryrun(self):
            for status in ('PASS', 'DRY_RUN'):
                event = threading.Event()
                checked_result(SimpleNamespace(status=status, reason=''),
                               dict(pass_markers=['ORACLE']), 'ORACLE', event)
                self.assertFalse(event.is_set())

        def test_launch_requires_review(self):
            with self.assertRaisesRegex(ValueError, 'parent review'):
                work(Path('/unused'), False, None)

        def test_gate_wrong_status(self):
            with self.assertRaisesRegex(ValueError, 'terminal PASS'):
                validate_extended8(dict(status='RUNNING'), {}, {}, [], {}, {}, '')

        def test_gate_wrong_image(self):
            with self.assertRaisesRegex(ValueError, 'different image'):
                validate_extended8(dict(status='CANDIDATE02_EXTENDED8_PASS', returncode=0,
                                       image_sha256='old'), {}, {}, [], {}, {}, 'new')

        def test_gate_positive_and_bad_csv(self):
            complete = dict(status='CANDIDATE02_EXTENDED8_PASS', returncode=0, image_sha256='same')
            analysis = dict(status='EXTENDED8_CSV_ORACLE_PASS')
            metadata = dict(status='COMPLETE', simv='/pinned/simv')
            summary = [dict(name='extended8', status='PASS', returncode=0)]
            inputs = dict(simv=dict(image_sha256={'/pinned/simv': 'hash'}))
            ledger = dict(simv='/pinned/simv', files={'/pinned/simv': 'hash'})
            validate_extended8(complete, analysis, metadata, summary, inputs, ledger, 'same')
            with self.assertRaisesRegex(ValueError, 'CSV oracle'):
                validate_extended8(complete, dict(status='NOT_PASS'), metadata, summary, inputs, ledger, 'same')

        def test_worker_exception_cancels(self):
            class Base:
                def _run_test(self, test, image):
                    raise RuntimeError('fixture')
            instance = runner_class(Base, {})()
            instance.cancel_event = threading.Event()
            with self.assertRaises(RuntimeError):
                instance._run_test(None, None)
            self.assertTrue(instance.cancel_event.is_set())

    require(unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests)).wasSuccessful(),
            'Host tests failed')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['plan', 'work', 'self-test'])
    cli.add_argument('--out', type=Path)
    cli.add_argument('--authorize-run', action='store_true')
    cli.add_argument('--approved-plan-sha256')
    args = cli.parse_args()
    if args.mode == 'self-test':
        self_test()
        return 0
    require(args.out is not None, '--out required')
    environment = shared.environment()
    os.environ.clear()
    os.environ.update(environment)
    if args.mode == 'plan':
        plan(owned(args.out))
        return 0
    return work(owned(args.out), args.authorize_run, args.approved_plan_sha256)


if __name__ == '__main__':
    raise SystemExit(main())
