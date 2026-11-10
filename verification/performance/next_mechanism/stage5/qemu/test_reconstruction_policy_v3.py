#!/usr/bin/env python3
"""Bounded host tests plus a read-only dry-run against failed prepare02."""
import argparse
import ast
from collections import Counter
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
import archive_policy_v2
import reconstruction_policy_v3 as policy
import recipe_v2
import recipe_v3 as recipe
import test_adapter
import test_archive_policy_v2 as archive_tests

OUTPUT = None
PREPARED = recipe.OUT / 'stage5_qemu_prepare_20261110_02'
PREPARE_SHA = 'a4e62511c8b21abba6246fb6af51423c523de787f2da475ed0f583680469b57f'
SOURCE04_SHA = '7684238d3719d09a39bf97d0254ec073f8dafd43fff6d6c110f1757bffced622'


class ReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OUTPUT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src, self.dst = self.root / 'frozen', self.root / 'qemu-10.2.0'
        self.src.mkdir()
        self.dst.mkdir()
        self.pins, self.links = {}, []

    def file(self, name, data=b'accepted', current=b'accepted'):
        for root, value in ((self.src, data), (self.dst, current)):
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if value is not None:
                p.write_bytes(value)
        self.pins[name] = recipe.sha(self.src / name)

    def link(self, name='alias.h', target='target.h', pinned=True):
        for root in (self.src, self.dst):
            (root / name).symlink_to(target)
        self.links.append(dict(name='qemu-10.2.0/' + name, kind='symlink', target=target))
        if pinned:
            self.pins[name] = recipe.sha(self.src / name)

    def plan(self):
        return policy.plan(self.src, self.dst, self.pins, self.links)

    def rejected_without_writes(self):
        before = recipe.tree_inventory(self.dst)
        report = self.plan()
        self.assertTrue(report['issues'])
        with self.assertRaises(ValueError):
            policy.apply(report)
        self.assertEqual(recipe.tree_inventory(self.dst), before)

    def test_keep_exact_alias_no_write_and_regular_copy(self):
        self.file('target.h')
        self.link()
        self.file('changed.h', current=b'old')
        self.file('new/path.h', current=None)
        report = self.plan()
        self.assertFalse(report['issues'])
        before = [(p.lstat(), p.stat()) for p in (self.dst / 'alias.h', self.dst / 'target.h')]
        policy.apply(report)
        after = [(p.lstat(), p.stat()) for p in (self.dst / 'alias.h', self.dst / 'target.h')]
        self.assertEqual(before, after)
        self.assertEqual((self.dst / 'changed.h').read_bytes(), b'accepted')
        self.assertEqual((self.dst / 'new/path.h').read_bytes(), b'accepted')
        self.assertEqual(report['counts'], dict(KEEP_FILE=1, KEEP_SYMLINK=1,
                                               COPY_REGULAR=1, CREATE_REGULAR=1))

    def test_mismatching_alias_rejects_before_any_regular_copy(self):
        self.file('a_first.h', current=b'old')
        self.file('target.h', current=b'conflict')
        self.link()
        self.rejected_without_writes()

    def test_conflicting_alias_pin_rejected(self):
        self.file('target.h')
        self.link()
        self.link('alias2.h')
        self.pins['alias2.h'] = '0' * 64
        self.rejected_without_writes()

    def test_unregistered_or_changed_link_target_rejected(self):
        self.file('target.h')
        self.file('same.h')
        self.link()
        saved, self.links = self.links, []
        self.rejected_without_writes()
        self.links = saved
        (self.dst / 'alias.h').unlink()
        (self.dst / 'alias.h').symlink_to('same.h')
        self.rejected_without_writes()

    def test_absolute_escape_cycle_and_dangling_rejected(self):
        self.file('target.h')
        self.link()
        for target in (str(self.src / 'target.h'), '../frozen/target.h', 'alias.h', 'missing'):
            with self.subTest(target=target):
                (self.dst / 'alias.h').unlink()
                (self.dst / 'alias.h').symlink_to(target)
                self.links[0]['target'] = target
                self.rejected_without_writes()

    def test_parent_symlink_and_destination_directory_rejected(self):
        self.file('sub/a.h', current=None)
        (self.dst / 'sub').rmdir()
        (self.dst / 'sub').symlink_to(self.src / 'sub')
        self.rejected_without_writes()
        (self.dst / 'sub').unlink()
        (self.dst / 'sub/a.h').mkdir(parents=True)
        self.rejected_without_writes()

    def test_hardlink_destination_rejected(self):
        self.file('target.h', current=b'old')
        os.link(self.dst / 'target.h', self.dst / 'alias.h')
        self.rejected_without_writes()

    def test_unpinned_file_and_directory_alias_writes_rejected(self):
        self.file('target.h', current=b'old')
        self.link(pinned=False)
        self.rejected_without_writes()
        self.file('dir/target.h', current=b'old')
        self.link('diralias', 'dir', pinned=False)
        self.rejected_without_writes()

    def test_stale_plan_rejected_before_writes(self):
        self.file('a_first.h', current=b'old')
        self.file('target.h')
        self.link()
        report = self.plan()
        (self.dst / 'target.h').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Preflight stale'):
            policy.apply(report)
        self.assertEqual((self.dst / 'a_first.h').read_bytes(), b'old')

    def test_future_copy_anchor_collision_and_alias_rejected(self):
        self.file('target.h')
        self.link()
        self.file('target/riscv/trace-events', data=b'# trace\n', current=b'# trace\n')
        self.file('anchor.c', data=b'anchor\n', current=b'old\n')
        own = self.root / 'owned'
        own.mkdir()
        (own / 'new.c').write_text('new\n')
        pins = {'new.c': recipe.sha(own / 'new.c')}
        overlay = SimpleNamespace(EDITS={'anchor.c': []}, FILES={'new.c': 'new.c'},
                                  TRACE_EVENTS='event() ""\n', transform=lambda name, text: text + 'edit\n')
        report = self.plan()
        self.assertFalse(policy.future(report, overlay, own, pins)['issues'])
        overlay.FILES['new.c'] = 'target.h'
        self.assertTrue(policy.future(report, overlay, own, pins)['issues'])
        overlay.FILES['new.c'] = 'missing/new.c'
        self.assertTrue(policy.future(report, overlay, own, pins)['issues'])
        overlay.FILES['new.c'] = 'new.c'
        overlay.EDITS = {'target.h': []}
        self.assertTrue(policy.future(report, overlay, own, pins)['issues'])
        overlay.EDITS = {'unregistered.c': []}
        self.assertTrue(policy.future(report, overlay, own, pins)['issues'])
        (own / 'new.c').unlink()
        (own / 'new.c').symlink_to(self.src / 'target.h')
        with self.assertRaises(ValueError):
            policy.future(report, overlay, own, pins)

    def test_sealed_sources_and_recipe_non_prepare_helpers_unchanged(self):
        path = recipe.OUT / 'stage5_qemu_adapter_source_20261110_04/result.json'
        self.assertEqual(recipe.sha(path), SOURCE04_SHA)
        for name, digest in recipe.read(path)['files'].items():
            self.assertEqual(recipe.sha(recipe.HERE / name), digest, name)
        old = ast.parse((recipe.HERE / 'recipe_v2.py').read_text())
        new = ast.parse((recipe.HERE / 'recipe_v3.py').read_text())
        def funcs(tree):
            return {x.name: ast.dump(x) for x in tree.body if isinstance(x, ast.FunctionDef)}
        old, new = funcs(old), funcs(new)
        self.assertEqual(set(old), set(new))
        for name in set(old) - {'prepare', 'build'}:
            self.assertEqual(old[name], new[name], name)
        self.assertEqual(recipe.CONFIGURE, recipe_v2.CONFIGURE)
        self.assertEqual(recipe.GATES, recipe_v2.GATES)

    def test_all_real_prepare02_entries_future_copies_and_preservation(self):
        self.assertEqual(recipe.sha(PREPARED / 'prepare.json'), PREPARE_SHA)
        self.assertEqual(recipe.sha(recipe.MANIFEST), recipe.MANIFEST_SHA)
        before = recipe.tree_inventory(PREPARED)
        inherited = {str(Path(p).relative_to(recipe.SOURCE)): h
                     for p, h in recipe.read(recipe.MANIFEST)['source_sha256'].items()
                     if Path(p).is_relative_to(recipe.SOURCE)}
        archive = recipe.read(PREPARED / 'archive-inventory.json')
        archive_policy_v2.require_known(archive)
        links = [r for r in archive['all_links'] if r['name'] != archive_policy_v2.SKIP_NAME]
        report = policy.plan(recipe.SOURCE, PREPARED / 'qemu-10.2.0', inherited, links)
        recipe.write_new(OUTPUT / 'prepare02-dryrun.json', report)
        policy.clear(report)
        self.assertEqual(len(report['rows']), 34940)
        self.assertEqual(report['counts'], dict(KEEP_FILE=34800, COPY_REGULAR=8,
                                               CREATE_REGULAR=122, KEEP_SYMLINK=10))
        self.assertEqual(len(report['alias_groups']), 6)
        self.assertEqual(len(report['links']), 72)
        own, _ = recipe.identity()
        future = policy.future(report, recipe.overlay, recipe.HERE, own)
        recipe.write_new(OUTPUT / 'future-copies-dryrun.json', future)
        policy.clear(future)
        self.assertEqual(len(future['edits']), 12)
        self.assertEqual(len(future['new_files']), 7)
        self.assertEqual(len(future['inputs']), 19)
        self.assertEqual(recipe.tree_inventory(PREPARED), before)
        recipe.write_new(OUTPUT / 'prepare02-preservation.json', dict(
            prepare_sha256=PREPARE_SHA, entries=len(before),
            tree_inventory_sha256=recipe.hashlib.sha256(recipe.canonical(before)).hexdigest(),
            unchanged=True, reconstruction_applied=False))


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    OUTPUT = recipe.fresh(args.output, 'stage5_qemu_adapter_source_')
    archive_tests.OUTPUT = OUTPUT
    pins, digest = recipe.identity()
    report = dict(schema='stage5-qemu-reconstruction-host-v3', state='FAIL', files=pins,
                  source_review_sha256=digest, preparation_executed=False,
                  compiler_executed=False, guest_executed=False)
    def expired(signum, frame):
        raise TimeoutError('180-second host-only test bound exceeded')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls)
                                  for cls in (test_adapter.AdapterSourceTests,
                                              archive_tests.ArchivePolicyTests, ReconstructionTests))
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        recipe.require(recipe.identity() == (pins, digest), 'Owned sources changed during tests')
        if result.wasSuccessful():
            report['state'] = 'HOST_RECONSTRUCTION_PASS_NOT_PREPARED'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['artifacts'] = recipe.tree_pins(OUTPUT)
        recipe.write_new(OUTPUT / 'result.json', report)
    print(json.dumps(report, indent=2))
    return int(report['state'] != 'HOST_RECONSTRUCTION_PASS_NOT_PREPARED')


if __name__ == '__main__':
    raise SystemExit(main())
