#!/usr/bin/env python3
"""Bounded host-only archive-policy tests; never prepares/builds/runs QEMU."""
import argparse
import ast
import io
import json
from pathlib import Path
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import archive_policy_v2 as policy
import recipe as predecessor
import recipe_v2 as successor
import test_adapter

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE.parents[3] / 'qbs/qemu/build/qemu-10.2.0.tar.xz'
OUTPUT = None
SOURCE03_SHA = 'fa792f933a0cd5eab897c03cdb6eed0aa4649a2d9d85de5fe109e03e83729eba'


def member(name, kind=tarfile.REGTYPE, target='', data=b''):
    item = tarfile.TarInfo(name)
    item.type, item.linkname, item.size = kind, target, len(data)
    return item


def inspect(items):
    return policy.inventory(items, '/stage5-archive-unit-test-not-extracted')


class ArchivePolicyTests(unittest.TestCase):
    def test_exact_known_exclusion_only(self):
        item = member(policy.SKIP_NAME, tarfile.SYMTYPE, policy.SKIP_TARGET)
        report = inspect([item])
        self.assertFalse(report['issues'])
        self.assertEqual(len(report['excluded']), 1)
        self.assertIsNone(policy.data_filter(item, '/unused'))
        with self.assertRaises(tarfile.AbsoluteLinkError):
            tarfile.data_filter(item, '/unused')

    def test_changed_target_type_and_size_rejected(self):
        for item in (member(policy.SKIP_NAME, tarfile.SYMTYPE, '/tmp/other'),
                     member(policy.SKIP_NAME, tarfile.LNKTYPE, policy.SKIP_TARGET),
                     member(policy.SKIP_NAME)):
            with self.subTest(kind=item.type, target=item.linkname):
                self.assertTrue(inspect([item])['issues'])
                with self.assertRaises(ValueError):
                    policy.data_filter(item, '/unused')
        report = dict(members=policy.EXPECTED_MEMBERS, declared_file_bytes=policy.EXPECTED_BYTES,
                      links=policy.EXPECTED_LINKS, issues=[], excluded=[dict(
                          name=policy.SKIP_NAME, kind='symlink', target=policy.SKIP_TARGET, size=1)])
        with self.assertRaises(ValueError):
            policy.require_known(report)

    def test_other_absolute_links_rejected(self):
        for name in ('qemu-10.2.0/unrelated', policy.SKIP_NAME + '-lookalike'):
            for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                item = member(name, kind, '/opt/X11/include')
                self.assertTrue(inspect([item])['issues'])
                with self.assertRaises(tarfile.AbsoluteLinkError):
                    policy.data_filter(item, '/unused')

    def test_relative_escape_and_bad_member_paths(self):
        for item in (member('qemu-10.2.0/link', tarfile.SYMTYPE, '../../outside'),
                     member('qemu-10.2.0/link', tarfile.LNKTYPE, '../outside'),
                     member('/absolute'), member('qemu-10.2.0/../outside'),
                     member('qemu-10.2.0/a/./b'), member('other-root/file')):
            self.assertTrue(inspect([item])['issues'], item.name)

    def test_duplicates_specials_and_excluded_children(self):
        self.assertTrue(inspect([member('qemu-10.2.0/a'), member('qemu-10.2.0/a')])['issues'])
        self.assertTrue(inspect([member('qemu-10.2.0/device', tarfile.CHRTYPE)])['issues'])
        self.assertTrue(inspect([member(policy.SKIP_NAME + '/header.h')])['issues'])
        self.assertTrue(inspect([member('qemu-10.2.0/link', tarfile.SYMTYPE,
                                      'roms/edk2/EmulatorPkg/Unix/Host/X11IncludeHack')])['issues'])

    def test_link_chains_and_cycles(self):
        safe = [member('qemu-10.2.0/a', tarfile.SYMTYPE, 'b'),
                member('qemu-10.2.0/b', tarfile.SYMTYPE, 'real'),
                member('qemu-10.2.0/real', tarfile.DIRTYPE), member('qemu-10.2.0/a/file')]
        self.assertFalse(inspect(safe)['issues'])
        bad = [member('qemu-10.2.0/a', tarfile.SYMTYPE, 'b'),
               member('qemu-10.2.0/b', tarfile.SYMTYPE, 'a')]
        self.assertTrue(inspect(bad)['issues'])
        bad[1] = member('qemu-10.2.0/b', tarfile.SYMTYPE, '../../outside')
        self.assertTrue(inspect(bad)['issues'])

    def test_safe_relative_and_hardlinks_preserved(self):
        items = [member('qemu-10.2.0/a'), member('qemu-10.2.0/b', tarfile.SYMTYPE, 'a'),
                 member('qemu-10.2.0/c', tarfile.LNKTYPE, 'qemu-10.2.0/a')]
        self.assertFalse(inspect(items)['issues'])
        with patch.object(policy.tarfile, 'data_filter', wraps=tarfile.data_filter) as standard:
            for item in items:
                self.assertIsNotNone(policy.data_filter(item, '/unused'))
            self.assertEqual(standard.call_count, len(items))

    def test_synthetic_extraction_keeps_standard_filter(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode='w') as archive:
            archive.addfile(member('qemu-10.2.0/a', data=b'unchanged'), io.BytesIO(b'unchanged'))
            archive.addfile(member('qemu-10.2.0/b', tarfile.SYMTYPE, 'a'))
            archive.addfile(member(policy.SKIP_NAME, tarfile.SYMTYPE, policy.SKIP_TARGET))
        raw.seek(0)
        with tempfile.TemporaryDirectory(dir=OUTPUT) as temp:
            with tarfile.open(fileobj=raw, mode='r:') as archive:
                self.assertFalse(policy.inventory(archive.getmembers(), temp)['issues'])
                archive.extractall(temp, filter=policy.data_filter)
            self.assertEqual((Path(temp) / 'qemu-10.2.0/b').read_bytes(), b'unchanged')
            excluded = Path(temp) / policy.SKIP_NAME
            self.assertFalse(excluded.exists() or excluded.is_symlink())

    def test_existing_destination_symlink_still_rejected(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as temp:
            root = Path(temp)
            (root / 'qemu-10.2.0').symlink_to('/outside-archive-test', target_is_directory=True)
            with self.assertRaises(tarfile.OutsideDestinationError):
                policy.data_filter(member('qemu-10.2.0/file'), temp)

    def test_original_source03_and_helper_functions_unchanged(self):
        receipt_path = successor.OUT / 'stage5_qemu_adapter_source_20261110_03/result.json'
        self.assertEqual(successor.sha(receipt_path), SOURCE03_SHA)
        receipt = successor.read(receipt_path)
        for name, digest in receipt['files'].items():
            self.assertEqual(successor.sha(HERE / name), digest, name)
        old = ast.parse((HERE / 'recipe.py').read_text())
        new = ast.parse((HERE / 'recipe_v2.py').read_text())
        old_funcs = {x.name: ast.dump(x) for x in old.body if isinstance(x, ast.FunctionDef)}
        new_funcs = {x.name: ast.dump(x) for x in new.body if isinstance(x, ast.FunctionDef)}
        self.assertEqual(set(old_funcs), set(new_funcs))
        for name in set(old_funcs) - {'prepare', 'build'}:
            self.assertEqual(old_funcs[name], new_funcs[name], name)
        self.assertEqual(predecessor.CONFIGURE, successor.CONFIGURE)
        self.assertEqual(predecessor.GATES, successor.GATES)

    def test_complete_known_archive_inventory(self):
        self.assertEqual(successor.sha(ARCHIVE), policy.ARCHIVE_SHA)
        with tarfile.open(ARCHIVE, 'r:xz') as archive:
            report = policy.inventory(archive.getmembers(), OUTPUT)
        successor.write_new(OUTPUT / 'archive-inventory.json', report)
        policy.require_known(report)
        self.assertEqual(len(report['all_links']), 73)
        self.assertEqual(len(report['excluded']), 1)
        self.assertFalse(report['issues'])


def main():
    global ARCHIVE, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ARCHIVE = args.archive.resolve(strict=True)
    OUTPUT = successor.fresh(args.output, 'stage5_qemu_adapter_source_')
    pins, digest = successor.identity()
    report = dict(schema='stage5-qemu-archive-host-v2', state='FAIL',
                  source_review_sha256=digest, files=pins,
                  archive_sha256=policy.ARCHIVE_SHA, compiler_executed=False,
                  preparation_executed=False, guest_executed=False)
    def expired(signum, frame):
        raise TimeoutError('180-second host-only test bound exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        suite = unittest.TestSuite([
            unittest.defaultTestLoader.loadTestsFromTestCase(test_adapter.AdapterSourceTests),
            unittest.defaultTestLoader.loadTestsFromTestCase(ArchivePolicyTests),
        ])
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        successor.require(successor.identity() == (pins, digest), 'Source drift during host checks')
        if result.wasSuccessful():
            report['state'] = 'HOST_ARCHIVE_POLICY_PASS_NOT_PREPARED'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['artifacts'] = successor.tree_pins(OUTPUT)
        successor.write_new(OUTPUT / 'result.json', report)
    print(json.dumps(report, indent=2))
    return int(report['state'] != 'HOST_ARCHIVE_POLICY_PASS_NOT_PREPARED')


if __name__ == '__main__':
    raise SystemExit(main())
