#!/usr/bin/env python3
"""Bounded source-copy and build-admission mutations; no configure or guest."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v6 as v
import test_build_v4 as old_tests

OUTPUT = None


class AssetTests(unittest.TestCase):
    def test_recursive_sources_and_generator_inputs(self):
        root = dict(target_sources=[dict(sources=['a.c'], generated_sources=['generated.h'])],
                    generator=dict(inputs=['version_gen.h.in']))
        self.assertEqual(list(v.strings(root)), [('/target_sources/0/sources/0', 'a.c'),
                         ('/target_sources/0/generated_sources/0', 'generated.h'),
                         ('/generator/inputs/0', 'version_gen.h.in')])
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            root = Path(tmp)
            source, build = root / 'source', root / 'build'
            source.mkdir()
            build.mkdir()
            (source / 'a.c').write_bytes(b'x')
            (build / 'generated.h').write_bytes(b'x')
            self.assertEqual(v.source_reference('../source/a.c', source, build), source / 'a.c')
            self.assertIsNone(v.source_reference(str(build / 'generated.h'), source, build))
            self.assertIsNone(v.source_reference('../source/missing', source, build))

    def test_regeneration_query_parser(self):
        text = 'build.ninja:\n  input: REGENERATE_BUILD\n    ../source/a\n    | meson-private/coredata.dat\n  outputs:\n'
        self.assertEqual(v.regeneration_inputs(text), ['../source/a', 'meson-private/coredata.dat'])
        for bad in (text.replace('REGENERATE_BUILD', 'OTHER'), text.replace('  outputs:\n', ''),
                    'build.ninja:\n  input: REGENERATE_BUILD\n  outputs:\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                v.regeneration_inputs(bad)

    def archive(self, root, template=v.ASSET_BYTES, header=b'header', link=False):
        path = root / 'archive.tar'
        with tarfile.open(path, 'w:') as archive:
            for name, data in [('version_gen.h.in', template), ('libfdt/fdt.h', header)]:
                row = tarfile.TarInfo(name)
                row.size = len(data)
                if link and name == 'version_gen.h.in':
                    row.type = tarfile.SYMTYPE
                    row.linkname = '/bad'
                    archive.addfile(row)
                else:
                    archive.addfile(row, io.BytesIO(data))
        return path

    def test_commit_archive_template_and_all_frozen_headers(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            frozen = {'libfdt/fdt.h': hashlib.sha256(b'header').hexdigest()}
            data, checked = v.archive_assets(self.archive(Path(tmp)), frozen)
            self.assertEqual(data, v.ASSET_BYTES)
            self.assertEqual(checked, frozen)

    def test_archive_mutations_rejected(self):
        for mutation in ({'template': b'wrong'}, {'header': b'changed'}, {'link': True}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
                with self.assertRaises(ValueError):
                    v.archive_assets(self.archive(Path(tmp), **mutation),
                                     {'libfdt/fdt.h': hashlib.sha256(b'header').hexdigest()})
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp, self.assertRaises(ValueError):
            v.archive_assets(self.archive(Path(tmp)), {'absent.c': '0' * 64})

    def copy_fixture(self, root):
        original, variant = root / 'old', root / 'new'
        (original / 'qemu-10.2.0/subprojects/dtc').mkdir(parents=True)
        (original / 'inputs').mkdir()
        (original / 'qemu-10.2.0/test.c').write_bytes(b'frozen')
        (original / 'qemu-10.2.0/alias').symlink_to('test.c')
        (original / 'inputs/helper.py').write_bytes(b'pass\n')
        r = v.v4.base()
        r.write_new(original / 'tree-inventory.json', r.tree_inventory(original / 'qemu-10.2.0') |
                    r.tree_inventory(original / 'inputs'))
        for name in ('qemu-10.2.0', 'inputs'):
            shutil.copytree(original / name, variant / name, symlinks=True, copy_function=shutil.copy2)
        (variant / 'qemu-10.2.0' / v.ASSET).write_bytes(v.ASSET_BYTES)
        return original, variant

    def test_copy_preserves_links_bytes_and_no_hardlinks(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            original, variant = self.copy_fixture(Path(tmp))
            with patch.object(v, 'PREPARED', original):
                actual = v.verify_copy(variant)
            self.assertEqual(actual[str(variant / 'qemu-10.2.0/alias')],
                             dict(kind='symlink', target='test.c'))
            self.assertFalse((original / 'qemu-10.2.0' / v.ASSET).exists())

    def test_copy_missing_extra_changed_and_hardlink_rejected(self):
        for kind in ('missing', 'extra', 'changed', 'hardlink', 'link'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
                original, variant = self.copy_fixture(Path(tmp))
                path = variant / 'qemu-10.2.0/test.c'
                if kind == 'missing':
                    path.unlink()
                elif kind == 'extra':
                    (variant / 'qemu-10.2.0/extra').write_bytes(b'x')
                elif kind == 'changed':
                    path.write_bytes(b'x')
                elif kind == 'hardlink':
                    path.unlink()
                    os.link(original / 'qemu-10.2.0/test.c', path)
                else:
                    path = variant / 'qemu-10.2.0/alias'
                    path.unlink()
                    path.symlink_to('inputs')
                with patch.object(v, 'PREPARED', original), self.assertRaises(ValueError):
                    v.verify_copy(variant)

    def build_fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old_tests.BuildTests().fixture(path)
            prepared['configure_argv'][0] = str(path / 'variant/qemu-10.2.0/configure')
            report.update(schema='stage5-qemu-build-v6', prepared=str(path / 'variant'),
                          prepare_sha256='1' * 64, original_prepare_sha256=v.PREPARE_SHA,
                          preflight=str(v.v5.TOOLENV), preflight_sha256=v.v5.TOOLENV_SHA,
                          predecessor_validator_sha256=v.V5_SHA, fdt_selection='internal',
                          source_review_sha256=v.identity()[1])
            report['commands'][0]['argv'] = v.v5.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_variant', return_value=prepared) as validate:
                result = v.checked_build(path, v.sha(path / 'build.json'))
                validate.assert_called_once_with(str(path / 'variant'), '1' * 64)
                return result

    def test_positive_build_fixture_and_exact_v5_flags(self):
        self.assertEqual(self.build_fixture()['state'], 'BUILT_NOT_EXECUTED')
        before = v.v4.base().read(v.PREPARED / 'prepare.json')
        after = copy.deepcopy(before)
        after['configure_argv'][0] = '/new/source/configure'
        self.assertEqual(v.v5.configure_argv(before)[1:], v.v5.configure_argv(after)[1:])

    def test_build_schema_identity_and_image_mutations(self):
        for key, value in (('schema', 'stage5-qemu-build-v5'), ('state', 'FAIL'),
                           ('original_prepare_sha256', '0' * 64), ('preflight_sha256', '0' * 64),
                           ('predecessor_validator_sha256', '0' * 64), ('source_review_sha256', '0' * 64),
                           ('fdt_selection', 'auto'), ('post_pins_match', False),
                           ('guest_executed', True), ('executable_sha256', '0' * 64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build_fixture(lambda r: r.update({key: value}))

    def test_build_argv_environment_and_owner_mutations(self):
        for mutation in (lambda r: r['commands'][0]['argv'].pop(),
                         lambda r: r['commands'][0]['argv'].__setitem__(-1, '--enable-fdt=auto'),
                         lambda r: r['commands'][0]['argv'].__setitem__(0, '/old/source/configure'),
                         lambda r: r['commands'][1]['argv'].__setitem__(1, '-j8'),
                         lambda r: r['environment'].update(LD_PRELOAD='/bad'),
                         lambda r: r['service_owner'].update(main_pid=0),
                         lambda r: r['commands'].pop()):
            with self.assertRaises(ValueError):
                self.build_fixture(mutation)

    def test_build_command_receipt_mutations(self):
        for key, value in (('cwd', '/wrong'), ('timeout', 901), ('returncode', 1),
                           ('log_sha256', '0' * 64), ('pid', 0), ('ended_ns', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build_fixture(lambda r: r['commands'][0].update({key: value}))

    def test_failed_build03_and_prepared03_preserved(self):
        r = v.v4.base()
        failed = r.read(v.OUT / 'stage5_qemu_build_20261110_03/build.json')
        self.assertEqual(failed['state'], 'FAIL')
        self.assertEqual(len(failed['commands']), 1)
        self.assertIn('version_gen.h.in', (v.OUT / 'stage5_qemu_build_20261110_03/configure.log').read_text())
        self.assertFalse((v.PREPARED / 'qemu-10.2.0' / v.ASSET).exists())
        self.assertEqual(v.sha(v.PREPARED / 'prepare.json'), v.PREPARE_SHA)


def main():
    global OUTPUT
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v6_host_')
    pins, review = v.identity()
    report = dict(schema='stage5-qemu-build-v6-host', state='FAIL', files=pins,
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
                unittest.defaultTestLoader.loadTestsFromTestCase(AssetTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'V6 host checks failed')
        v.require(v.identity() == (pins, review), 'V6 source drift')
        report['state'] = 'BUILD_V6_STATIC_HOST_PASS_NOT_BUILT'
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
