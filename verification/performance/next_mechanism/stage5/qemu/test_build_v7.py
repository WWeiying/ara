#!/usr/bin/env python3
"""Exact generated-lock handling and unchanged build receipt rigor; no build."""
import argparse
import hashlib
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
import build_v7 as v
import test_build_v6 as v6tests
import test_build_v4 as old_tests

OUTPUT = None


class LockTests(unittest.TestCase):
    def test_actual_normalized_census_matches_preserved_unique_ledger(self):
        r = v.v4.base()
        proof = v.OUT / 'stage5_qemu_census_review_20261110_01'
        self.assertEqual(v.sha(proof / 'result.json'),
                         'ac0b19dce1a63c8f0e10bbbcf6a5fbe95e9dc18207e5b6f5e04121690ae0caf7')
        saved = r.read(proof / 'result.json')
        r.verify(saved['artifacts'])
        r.verify(saved['introspection_pins'])
        paths = set()
        for file in sorted((v.OLD_BUILD / 'meson-info').glob('intro-*.json')):
            for pointer, value in v.strings(r.read(file)):
                path = v.source_reference(value)
                if path is not None:
                    paths.add(str(path.relative_to(v.OLD_SOURCE)))
        rows = r.read(proof / 'source-references.json')
        self.assertEqual(len(paths), 3119)
        self.assertEqual(paths, {row['path'] for row in rows})
        v.checked_reference_counts(rows, len(paths), len(paths))
        self.assertEqual(sum(row['status'] == 'IDENTICAL' for row in rows), 3111)
        self.assertEqual(sum(row['status'] == 'REVIEWED_OVERLAY' for row in rows), 7)

    def test_census_dropped_entries_duplicates_and_missing_mutations(self):
        rows = [dict(path='same.c', status='IDENTICAL', origins=['intro-targets.json#/0']),
                dict(path=v.ASSET, status='MISSING', origins=['intro-targets.json#/1'])]
        v.checked_reference_counts(rows, 2, 2)
        for changed, structured, combined in ((rows, 1, 2), (rows, 2, 1), (rows[:-1], 2, 2),
                                              (rows + [rows[0]], 3, 3), (rows[:1], 1, 1)):
            with self.assertRaises(ValueError):
                v.checked_reference_counts(changed, structured, combined)

    def fixture(self, root):
        original, variant = v6tests.AssetTests().copy_fixture(root)
        (original / 'qemu-10.2.0' / v.LOCK).write_bytes(b'')
        return original, variant

    def test_original_exact_empty_lock_only(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            original, variant = self.fixture(Path(tmp))
            r = v.v4.base()
            expected = v.inventory_with_lock(r.read(original / 'tree-inventory.json'), original, True)
            actual = r.tree_inventory(original / 'qemu-10.2.0') | r.tree_inventory(original / 'inputs')
            self.assertEqual(expected, actual)
            self.assertEqual(v.lock_metadata(original, True),
                             {str(original / 'qemu-10.2.0' / v.LOCK): v.EMPTY_SHA})
            self.assertEqual(v.lock_metadata(variant, False), {})

    def test_lock_nonempty_symlink_directory_extra_rejected(self):
        for kind in ('nonempty', 'symlink', 'directory', 'extra'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
                original, variant = self.fixture(Path(tmp))
                lock = original / 'qemu-10.2.0' / v.LOCK
                if kind == 'nonempty':
                    lock.write_bytes(b'x')
                elif kind == 'symlink':
                    lock.unlink()
                    lock.symlink_to('missing')
                elif kind == 'directory':
                    lock.unlink()
                    lock.mkdir()
                else:
                    (lock.parent / '.another-lock').write_bytes(b'')
                r = v.v4.base()
                expected = v.inventory_with_lock(r.read(original / 'tree-inventory.json'), original, True)
                with self.assertRaises(ValueError):
                    r.verify_membership(r.tree_inventory(original / 'qemu-10.2.0') |
                                        r.tree_inventory(original / 'inputs'), expected)

    def test_copy_skips_only_exact_lock_and_preserves_original(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            root = Path(tmp)
            original, variant = self.fixture(root)
            nested = original / 'qemu-10.2.0/subprojects/nested'
            nested.mkdir()
            (nested / '.wraplock').write_bytes(b'not the generated lock')
            output = root / 'copy'
            v.copy_without_lock(original / 'qemu-10.2.0', output)
            self.assertFalse((output / v.LOCK).exists())
            self.assertEqual((output / 'subprojects/nested/.wraplock').read_bytes(), b'not the generated lock')
            self.assertEqual((original / 'qemu-10.2.0' / v.LOCK).read_bytes(), b'')
            self.assertTrue((output / 'alias').is_symlink())
            self.assertNotEqual((output / 'test.c').stat().st_ino,
                                (original / 'qemu-10.2.0/test.c').stat().st_ino)

    def test_variant_before_and_after_build_metadata(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            original, variant = self.fixture(Path(tmp))
            with patch.object(v, 'PREPARED', original):
                v.verify_copy(variant)
                with self.assertRaises(ValueError):
                    v.verify_copy(variant, after_build=True)
                (variant / 'qemu-10.2.0' / v.LOCK).write_bytes(b'')
                v.verify_copy(variant, after_build=True)
                with self.assertRaises(ValueError):
                    v.verify_copy(variant)

    def test_variant_postbuild_other_drift_and_hardlink_rejected(self):
        for kind in ('nonempty_lock', 'source', 'hardlinked_lock', 'extra'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
                original, variant = self.fixture(Path(tmp))
                lock = variant / 'qemu-10.2.0' / v.LOCK
                lock.write_bytes(b'')
                if kind == 'nonempty_lock':
                    lock.write_bytes(b'x')
                elif kind == 'source':
                    (variant / 'qemu-10.2.0/test.c').write_bytes(b'x')
                elif kind == 'hardlinked_lock':
                    lock.unlink()
                    os.link(original / 'qemu-10.2.0' / v.LOCK, lock)
                else:
                    (lock.parent / 'extra').write_bytes(b'')
                with patch.object(v, 'PREPARED', original), self.assertRaises(ValueError):
                    v.verify_copy(variant, after_build=True)

    def build_fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old_tests.BuildTests().fixture(path)
            prepared['configure_argv'][0] = str(path / 'variant/qemu-10.2.0/configure')
            report.update(schema='stage5-qemu-build-v7', prepared=str(path / 'variant'),
                          prepare_sha256='1' * 64, original_prepare_sha256=v.PREPARE_SHA,
                          preflight=str(v.v5.TOOLENV), preflight_sha256=v.v5.TOOLENV_SHA,
                          predecessor_validator_sha256=v.V6_SHA, fdt_selection='internal',
                          source_review_sha256=v.identity()[1], generated_metadata_before={},
                          generated_metadata_after=v.lock_metadata(path / 'variant', True))
            report['commands'][0]['argv'] = v.v5.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_variant', return_value=prepared) as validate:
                result = v.checked_build(path, v.sha(path / 'build.json'))
                validate.assert_called_once_with(str(path / 'variant'), '1' * 64, after_build=True)
                return result

    def test_positive_build_receipt_and_frozen_flags(self):
        self.assertEqual(self.build_fixture()['state'], 'BUILT_NOT_EXECUTED')
        prepared = v.v4.base().read(v.PREPARED / 'prepare.json')
        argv = v.v5.configure_argv(prepared)
        self.assertEqual(argv[-3:], ['--python=/usr/bin/python3.11', '--ninja=/usr/bin/ninja',
                                     '--enable-fdt=internal'])
        self.assertEqual(argv.count('--disable-download'), 1)

    def test_build_identity_schema_and_metadata_mutations(self):
        for key, value in (('schema', 'stage5-qemu-build-v6'), ('state', 'FAIL'),
                           ('original_prepare_sha256', '0' * 64), ('preflight_sha256', '0' * 64),
                           ('predecessor_validator_sha256', '0' * 64), ('source_review_sha256', '0' * 64),
                           ('post_pins_match', False), ('executable_sha256', '0' * 64),
                           ('generated_metadata_before', {'bad': v.EMPTY_SHA}),
                           ('generated_metadata_after', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build_fixture(lambda r: r.update({key: value}))

    def test_build_argv_environment_owner_receipts_rejected(self):
        for mutation in (lambda r: r['commands'][0]['argv'].pop(),
                         lambda r: r['commands'][0]['argv'].__setitem__(0, '/old/source/configure'),
                         lambda r: r['commands'][0].update(timeout=901),
                         lambda r: r['commands'][1].update(returncode=1),
                         lambda r: r['commands'][0].update(cwd='/wrong'),
                         lambda r: r['commands'][0].update(log_sha256='0' * 64),
                         lambda r: r['commands'][0].update(pid=0),
                         lambda r: r['commands'][1].update(ended_ns=1),
                         lambda r: r['commands'][1]['argv'].__setitem__(1, '-j8'),
                         lambda r: r['environment'].update(LD_PRELOAD='/bad'),
                         lambda r: r['service_owner'].update(main_pid=0),
                         lambda r: r['commands'].pop()):
            with self.assertRaises(ValueError):
                self.build_fixture(mutation)

    def test_fixed_archive_checks_reused_unchanged(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = v6tests.AssetTests().archive(Path(tmp))
            data, checked = v.archive_assets(path, {'libfdt/fdt.h': hashlib.sha256(b'header').hexdigest()})
            self.assertEqual(data, v.ASSET_BYTES)
            self.assertEqual(len(checked), 1)
            with self.assertRaises(ValueError):
                v.archive_assets(path, {'libfdt/fdt.h': '0' * 64})

    def test_frozen_v6_and_failed_audit_preserved(self):
        self.assertEqual(v.sha(v.HERE / 'build_v6.py'), v.V6_SHA)
        self.assertEqual(v.sha(v.OUT / 'stage5_qemu_asset_audit_20261110_01/audit.json'),
                         'ac2eb808de78eac35e54f5e4ceae264e161fed76d54f5754c5fb8f6f9c357317')
        self.assertEqual(v.sha(v.PREPARED / 'tree-inventory.json'), v.ORIGINAL_TREE_SHA)


def main():
    global OUTPUT
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v7_host_')
    v6tests.OUTPUT = OUTPUT
    pins, review = v.identity()
    report = dict(schema='stage5-qemu-build-v7-host', state='FAIL', files=pins,
                  source_review_sha256=review, prepare_sha256=v.PREPARE_SHA,
                  toolenv_sha256=v.v5.TOOLENV_SHA, configure_executed=False,
                  qemu_compiled=False, guest_executed=False, dependency_probes_rerun=False)
    def expired(signum, frame):
        raise TimeoutError('180-second host check bound exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(LockTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'V7 host checks failed')
        v.require(v.identity() == (pins, review), 'V7 source drift')
        report['state'] = 'BUILD_V7_STATIC_HOST_PASS_NOT_BUILT'
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
