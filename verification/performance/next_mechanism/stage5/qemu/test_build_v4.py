#!/usr/bin/env python3
"""Focused host mutations plus one actual offline prerequisite preflight."""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v4 as v

OUTPUT = None


class BuildTests(unittest.TestCase):
    def test_pkg_config_wrappers_expanded_before_ldd(self):
        result = v.classify_tools(['/usr/bin/pkg-config'])
        self.assertEqual({p for p, row in result.items() if row['kind'] == 'wrapper'},
                         set(map(str, v.PKG_WRAPPERS)))
        self.assertEqual({p for p, row in result.items() if row['kind'] == 'elf'},
                         {'/usr/bin/sh', '/usr/bin/rpm', '/usr/bin/pkgconf'})
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            unknown = Path(tmp) / 'unknown-wrapper'
            unknown.write_text('#!/usr/bin/sh\nexit 0\n')
            with self.assertRaisesRegex(ValueError, 'Unreviewed non-ELF'):
                v.classify_tools([unknown])

    def test_minimal_environment_ignores_injection(self):
        path = Path('/owned/output')
        baseline = v.environment(path)
        with patch.dict(os.environ, dict(PYTHONPATH='/bad', CPATH='/bad', LD_PRELOAD='/bad',
                                        PKG_CONFIG_PATH='/bad', PKG_CONFIG_LIBDIR='/bad')):
            self.assertEqual(v.environment(path), baseline)
        self.assertEqual(baseline['PATH'], '/usr/bin:/bin')
        self.assertEqual(baseline['PKG_CONFIG_LIBDIR'], v.PKGDIR)
        self.assertFalse(set(baseline) & {'PYTHONPATH', 'CPATH', 'LD_PRELOAD', 'PKG_CONFIG_PATH'})

    def test_only_two_explicit_configure_additions(self):
        receipt = v.base().read(v.PREPARED / 'prepare.json')
        actual = v.configure_argv(receipt)
        self.assertEqual(actual[:-2], receipt['configure_argv'])
        self.assertEqual(actual[-2:], ['--python=/usr/bin/python3.11', '--ninja=/usr/bin/ninja'])
        self.assertIn('--disable-download', actual)

    def test_original_failure_and_helpers_preserved(self):
        r = v.base()
        self.assertEqual(v.sha(v.PREPARED / 'prepare.json'), v.PREPARE_SHA)
        for name, digest in v.HELPERS.items():
            self.assertEqual(v.sha(v.HERE / name), digest)
        failed = r.read(v.OUT / 'stage5_qemu_build_20261110_01/build.json')
        self.assertEqual(failed['state'], 'FAIL')
        self.assertEqual(len(failed['commands']), 1)
        self.assertEqual(failed['commands'][0]['returncode'], 1)
        self.assertIn('tomli', (v.OUT / 'stage5_qemu_build_20261110_01/configure.log').read_text())

    def fixture(self, root):
        r = v.base()
        path = Path(root)
        for name in ('configure.log', 'build.log', 'qemu-system-riscv64'):
            (path / name).write_text('host-fixture-only\n')
        prepared = r.read(v.PREPARED / 'prepare.json')
        commands = []
        for i, (argv, timeout, log) in enumerate(zip(
                (v.configure_argv(prepared), [v.NINJA, '-j4', 'qemu-system-riscv64']),
                (900, 1800), ('configure.log', 'build.log'))):
            commands.append(dict(argv=argv, cwd=str(path), timeout=timeout, state='EXITED',
                                 returncode=0, pid=100+i, started_ns=10+i*10, ended_ns=15+i*10,
                                 log_sha256=v.sha(path / log)))
        report = dict(schema='stage5-qemu-build-v4', state='BUILT_NOT_EXECUTED',
                      prepare_sha256=v.PREPARE_SHA, prepared=str(v.PREPARED), guest_executed=False,
                      post_pins_match=True, source_review_sha256=v.identity()[1],
                      required_execution_gates=r.GATES, preflight='/host-fixture-only',
                      preflight_sha256='unused', environment=v.environment(path), commands=commands,
                      service_owner=dict(unit='stage5-qemu-build-fixture.service', main_pid=1,
                                         invocation_id='a'*32, cgroup='/stage5-qemu-build-fixture.service'),
                      executable=str(path / 'qemu-system-riscv64'),
                      executable_sha256=v.sha(path / 'qemu-system-riscv64'))
        return report, prepared

    def check_fixture(self, mutate=None, wrong_sha=False):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = self.fixture(path)
            if mutate:
                mutate(report)
            v.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_prepared', return_value=prepared), \
                 patch.object(v, 'checked_toolenv', return_value={}):
                return v.checked_build(path, '0'*64 if wrong_sha else v.sha(path / 'build.json'))

    def test_positive_admission_fixture_only(self):
        self.assertEqual(self.check_fixture()['state'], 'BUILT_NOT_EXECUTED')

    def test_wrong_review_schema_state_or_image_rejected(self):
        with self.assertRaises(ValueError):
            self.check_fixture(wrong_sha=True)
        for key, value in (('schema', 'stage5-qemu-build-v3'), ('state', 'FAIL'),
                           ('executable_sha256', '0'*64), ('prepare_sha256', '0'*64),
                           ('source_review_sha256', '0'*64), ('post_pins_match', False)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check_fixture(lambda r: r.update({key: value}))

    def test_argv_cwd_timeout_or_log_mutations_rejected(self):
        for key, value in (('argv', ['/usr/bin/true']), ('cwd', '/tmp'), ('timeout', 901),
                           ('returncode', 1), ('log_sha256', '0'*64), ('state', 'RUNNING'),
                           ('pid', 0), ('ended_ns', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check_fixture(lambda r: r['commands'][0].update({key: value}))
        with self.assertRaises(ValueError):
            self.check_fixture(lambda r: r['commands'].append(copy.deepcopy(r['commands'][0])))

    def test_environment_or_owner_mutations_rejected(self):
        with self.assertRaises(ValueError):
            self.check_fixture(lambda r: r['environment'].update(PYTHONPATH='/bad'))
        for key, value in (('unit', 'unrelated.service'), ('main_pid', 0),
                           ('invocation_id', 'bad'), ('cgroup', '/wrong')):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check_fixture(lambda r: r['service_owner'].update({key: value}))

    def test_unreviewed_toolenv_rejected_before_import(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            (path / 'toolenv.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Unreviewed tool environment'):
                v.checked_toolenv(path, '0'*64)


def main():
    global OUTPUT
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--toolenv', type=Path, required=True)
    args = p.parse_args()
    r = v.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v4_host_')
    own, review = v.identity()
    report = dict(schema='stage5-qemu-build-v4-host', state='FAIL', files=own,
                  source_review_sha256=review, configure_executed=False,
                  qemu_compiled=False, guest_executed=False)
    def expired(signum, frame):
        raise TimeoutError('240-second host preflight bound exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(240)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(BuildTests))
        report.update(tests=result.testsRun, errors=len(result.errors), failures=len(result.failures))
        v.require(result.wasSuccessful(), 'Host mutation checks failed')
        toolenv = v.preflight(args.toolenv)
        report.update(toolenv=str(args.toolenv), toolenv_sha256=v.sha(args.toolenv / 'toolenv.json'),
                      prerequisite_state=toolenv['state'])
        v.require(v.identity() == (own, review), 'Successor source drift')
        report['state'] = 'BUILD_V4_HOST_PREFLIGHT_PASS_NOT_BUILT'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['artifacts'] = r.tree_pins(OUTPUT)
        r.write_new(OUTPUT / 'result.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
