#!/usr/bin/env python3
"""Fixed-FDT argv, dependency metadata and admission mutations; no build probes."""
import argparse
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v5 as v
import test_build_v4 as old_tests

OUTPUT = None


class FdtTests(unittest.TestCase):
    def test_only_internal_fdt_added_and_download_stays_disabled(self):
        prepared = v.v4.base().read(v.PREPARED / 'prepare.json')
        argv = v.configure_argv(prepared)
        self.assertEqual(argv[:-1], v.v4.configure_argv(prepared))
        self.assertEqual(argv[-1], '--enable-fdt=internal')
        self.assertEqual(argv.count('--disable-download'), 1)
        self.assertEqual([x for x in argv if 'fdt' in x], ['--enable-fdt=internal'])

    def test_fdt_branch_option_syntax_and_target_requirement(self):
        source = v.PREPARED / 'qemu-10.2.0'
        text = (source / 'meson.build').read_text()
        self.assertIn("fdt_opt = get_option('wrap_mode') == 'nodownload' ? 'disabled' : 'internal'", text)
        self.assertIn("if fdt_opt == 'internal'", text)
        self.assertIn("libfdt_proj = subproject('dtc', required: true", text)
        self.assertEqual(text.count("get_option('wrap_mode')"), 3)
        self.assertIn('--enable-fdt=*) quote_sh "-Dfdt=$2" ;;',
                      (source / 'scripts/meson-buildoptions.sh').read_text())
        self.assertIn('TARGET_NEED_FDT=y', (source / 'configs/targets/riscv64-softmmu.mak').read_text())
        self.assertIn("if sym == 'CONFIG_TCG' or target in accelerator_targets.get(sym, [])", text)

    def test_all_six_accepted_subproject_metadata_match(self):
        source = v.PREPARED / 'qemu-10.2.0'
        old = v.v4.SOURCE if hasattr(v.v4, 'SOURCE') else v.v4.OLD_BUILD.parent / 'qemu-10.2.0'
        rows = []
        for name in ('dtc', 'libvhost-user', 'libvduse', 'keycodemapdb',
                     'berkeley-softfloat-3', 'berkeley-testfloat-3'):
            before, after = old / 'subprojects' / name, source / 'subprojects' / name
            self.assertTrue((after / 'meson.build').is_file())
            for path in sorted(before.rglob('*')):
                if not path.is_file() or path.name not in ('meson.build', 'meson_options.txt', 'meson.options'):
                    continue
                target = after / path.relative_to(before)
                self.assertEqual(v.sha(path), v.sha(target), str(target))
                rows.append(dict(old=str(path), prepared=str(target), sha256=v.sha(target)))
        self.assertEqual(len(rows), 12)
        v.v4.base().write_new(OUTPUT / 'subproject-metadata.json', rows)

    def test_failed_build02_and_sealed_v4_preserved(self):
        r = v.v4.base()
        failed = r.read(v.OUT / 'stage5_qemu_build_20261110_02/build.json')
        self.assertEqual(failed['schema'], 'stage5-qemu-build-v4')
        self.assertEqual(failed['state'], 'FAIL')
        self.assertEqual(len(failed['commands']), 1)
        text = (v.OUT / 'stage5_qemu_build_20261110_02/configure.log').read_text()
        for line in ('Run-time dependency threads found: YES',
                     'Run-time dependency glib-2.0 found: YES 2.68.4',
                     'Run-time dependency zlib found: YES 1.2.11',
                     'Compiler for language rust skipped: feature rust disabled',
                     'fdt disabled but required by targets riscv64-softmmu'):
            self.assertIn(line, text)
        self.assertEqual(v.sha(v.HERE / 'build_v4.py'), v.V4_SHA)
        proof = r.read(v.TOOLENV / 'toolenv.json')
        self.assertEqual(v.sha(v.TOOLENV / 'toolenv.json'), v.TOOLENV_SHA)
        self.assertEqual(v.v4.identity(), (proof['files'], proof['source_review_sha256']))

    def checked_fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old_tests.BuildTests().fixture(path)
            report.update(schema='stage5-qemu-build-v5', preflight=str(v.TOOLENV),
                          preflight_sha256=v.TOOLENV_SHA, predecessor_validator_sha256=v.V4_SHA,
                          fdt_selection='internal', source_review_sha256=v.identity()[1])
            report['commands'][0]['argv'] = v.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_dependencies', return_value=prepared):
                return v.checked_build(path, v.sha(path / 'build.json'))

    def test_positive_fixture_only(self):
        self.assertEqual(self.checked_fixture()['state'], 'BUILT_NOT_EXECUTED')

    def test_v4_wrong_fdt_or_source_rejected(self):
        for key, value in (('schema', 'stage5-qemu-build-v4'), ('state', 'FAIL'),
                           ('fdt_selection', 'auto'), ('predecessor_validator_sha256', '0'*64),
                           ('preflight_sha256', '0'*64), ('source_review_sha256', '0'*64),
                           ('post_pins_match', False), ('executable_sha256', '0'*64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.checked_fixture(lambda r: r.update({key: value}))

    def test_option_omission_substitution_and_execution_mutations_rejected(self):
        for option in ('--enable-fdt=system', '--enable-fdt=auto', '--enable-download'):
            with self.subTest(option=option), self.assertRaises(ValueError):
                self.checked_fixture(lambda r: r['commands'][0]['argv'].__setitem__(-1, option))
        with self.assertRaises(ValueError):
            self.checked_fixture(lambda r: r['commands'][0]['argv'].pop())
        for key, value in (('cwd', '/wrong'), ('timeout', 901), ('returncode', 1),
                           ('log_sha256', '0'*64), ('pid', 0), ('ended_ns', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.checked_fixture(lambda r: r['commands'][0].update({key: value}))

    def test_environment_owner_and_missing_command_rejected(self):
        with self.assertRaises(ValueError):
            self.checked_fixture(lambda r: r['environment'].update(LD_PRELOAD='/wrong'))
        with self.assertRaises(ValueError):
            self.checked_fixture(lambda r: r['service_owner'].update(main_pid=0))
        with self.assertRaises(ValueError):
            self.checked_fixture(lambda r: r['commands'].pop())


def main():
    global OUTPUT
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v5_host_')
    pins, review = v.identity()
    report = dict(schema='stage5-qemu-build-v5-host', state='FAIL', files=pins,
                  source_review_sha256=review, prepare_sha256=v.PREPARE_SHA,
                  toolenv_sha256=v.TOOLENV_SHA, dependency_probes_rerun=False,
                  configure_executed=False, qemu_compiled=False, guest_executed=False)
    def expired(signum, frame):
        raise TimeoutError('120-second static/host check bound exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(120)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(FdtTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'FDT host checks failed')
        v.checked_dependencies()
        v.require(v.identity() == (pins, review), 'Successor source drift')
        report['state'] = 'BUILD_V5_STATIC_HOST_PASS_NOT_BUILT'
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
