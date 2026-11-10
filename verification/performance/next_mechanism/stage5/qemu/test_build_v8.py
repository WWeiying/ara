#!/usr/bin/env python3
"""Fixed full Git asset closure, minimal API repair and admission host checks."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_v8 as v
import test_build_v4 as old_tests

OUTPUT = None


class ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        v.require(v.sha(v.ARCHIVE) == v.ARCHIVE_SHA, 'Accepted archive drift')
        cls.raw = subprocess.check_output(['/usr/bin/git', '-C', str(v.v7.OLD_SOURCE / v.DTC),
            'ls-tree', '-rz', '--full-tree', v.DTC_COMMIT], timeout=30,
            env=dict(PATH='/usr/bin:/bin', LANG='C', LC_ALL='C',
                     GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null'))
        (OUTPUT / 'git-tree.raw').write_bytes(cls.raw)
        cls.members, cls.payload = v.archive_payload(v.ARCHIVE, cls.raw)
        cls.manifest = v.asset_plan(v.PARENT, cls.members, cls.payload)
        v.v4.base().write_new(OUTPUT / 'asset-manifest.json', cls.manifest)

    def test_all_tracked_files_bytes_modes_and_missing_set(self):
        self.assertEqual(len(self.members), 310)
        rows = self.manifest['tracked']
        added = [row for row in rows if row['action'] == 'ADD_MISSING']
        self.assertEqual(len(added), 194)
        self.assertEqual(sum(row['action'] == 'KEEP_IDENTICAL' for row in rows), 116)
        self.assertEqual(sum(bool(row['mode'] & 0o111) for row in added), 11)
        self.assertIn('libfdt/version.lds', [row['path'] for row in added])
        self.assertEqual(sum(Path(row['path']).suffix in ('.c', '.h') for row in added), 0)

    def test_all_four_meson_conditional_build_assets_covered(self):
        self.assertEqual(set(self.manifest['meson_sources']), set(v.MESON_FILES))
        for name in ('version_gen.h.in', 'libfdt/version.lds', 'convert-dtsv0-lexer.l',
                     'dtc-lexer.l', 'dtc-parser.y', 'pylibfdt/libfdt.i', 'tests/trees.S',
                     'tests/run_tests.sh', 'tests/incbin.bin'):
            self.assertIn(name, self.payload)
        source = self.manifest['meson_sources']
        self.assertIn("link_depends: 'version.lds'", source['libfdt/meson.build'])
        self.assertIn('link_args:', source['libfdt/meson.build'])
        self.assertIn("input: 'version_gen.h.in'", source['meson.build'])
        self.assertFalse(any('configure_file(' in data for data in source.values()))

    def test_git_duplicate_traversal_and_nonregular_rejected(self):
        first = self.raw.split(b'\0')[0] + b'\0'
        for bad in (first + first, b'100644 blob ' + b'0' * 40 + b'\t../escape\0',
                    b'120000 blob ' + b'0' * 40 + b'\tlink\0', b''):
            with self.assertRaises(ValueError):
                v.git_members(bad)

    def miniature(self, root, member_type=tarfile.REGTYPE, data=b'content', duplicate=False, mode=0o644):
        archive = root / 'test.tar'
        with tarfile.open(archive, 'w:') as stream:
            for _ in range(2 if duplicate else 1):
                row = tarfile.TarInfo('file')
                row.mode, row.type, row.size = mode, member_type, len(data)
                row.linkname = '/unsafe'
                stream.addfile(row, io.BytesIO(data) if member_type == tarfile.REGTYPE else None)
        blob = hashlib.sha1(b'blob 7\0content').hexdigest()
        raw = ('100644 blob ' + blob + '\tfile\0').encode()
        return archive, raw

    def test_archive_blob_mode_membership_and_link_mutations(self):
        for mutation in ({'data': b'changed'}, {'member_type': tarfile.SYMTYPE},
                         {'duplicate': True}, {'mode': 0o755}, {'mode': 0o600}):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
                archive, raw = self.miniature(Path(tmp), **mutation)
                with self.assertRaises(ValueError):
                    v.archive_payload(archive, raw)
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            archive, raw = self.miniature(Path(tmp))
            self.assertEqual(v.archive_payload(archive, raw)[1], {'file': b'content'})
            with self.assertRaises(ValueError):
                v.archive_payload(archive, raw + raw.replace(b'file', b'missing'))

    def test_git_archive_group_write_does_not_change_executable_mode(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            archive, raw = self.miniature(Path(tmp), mode=0o664)
            members, data = v.archive_payload(archive, raw)
            self.assertEqual(members['file']['mode'], 0o644)
            self.assertEqual(members['file']['archive_mode'], 0o664)
            self.assertEqual(data['file'], b'content')

    def test_existing_dtc_change_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            root = Path(tmp)
            dtc = root / 'qemu-10.2.0' / v.DTC
            dtc.mkdir(parents=True)
            (dtc / 'meson.build').write_bytes(b'wrong')
            with self.assertRaises(ValueError):
                v.asset_plan(root, self.members, self.payload)

    def test_only_approved_adapter_token_repaired(self):
        row, after, diff = v.repair_record(v.PARENT)
        before = (v.PARENT / 'qemu-10.2.0' / v.REPAIR_PATH).read_bytes()
        self.assertEqual(after.replace(v.REPAIR_NEW, v.REPAIR_OLD), before)
        self.assertEqual(after.count(v.REPAIR_NEW), 1)
        self.assertEqual(row['before_sha256'], v.REPAIR_BEFORE)
        self.assertIn('-    CharBackend console;', diff)
        self.assertIn('+    CharFrontend console;', diff)
        v.v4.base().write_new(OUTPUT / 'adapter-repair.json', row)
        (OUTPUT / 'adapter-repair.patch').write_text(diff)
        with self.assertRaises(ValueError):
            v.repaired(before + b' ')
        with self.assertRaises(ValueError):
            v.repaired(after)

    def test_expected_tree_registers_all_assets_and_one_repair(self):
        destination = OUTPUT / 'not-created'
        repair, _, _ = v.repair_record(v.PARENT)
        inventory = v.expected_inventory(destination, self.manifest, repair)
        for row in self.manifest['tracked']:
            self.assertEqual(inventory[str(destination / 'qemu-10.2.0' / v.DTC / row['path'])],
                             dict(kind='file', sha256=row['sha256']))
        self.assertEqual(inventory[str(destination / 'qemu-10.2.0' / v.REPAIR_PATH)]['sha256'],
                         repair['after_sha256'])
        self.assertNotIn(str(destination / 'qemu-10.2.0' / v.v7.LOCK), inventory)
        post = v.expected_inventory(destination, self.manifest, repair, after_build=True)
        self.assertEqual(set(post) - set(inventory), {str(destination / 'qemu-10.2.0' / v.v7.LOCK)})

    def build_fixture(self, mutation=None):
        with tempfile.TemporaryDirectory(dir=OUTPUT) as tmp:
            path = Path(tmp)
            report, prepared = old_tests.BuildTests().fixture(path)
            prepared['configure_argv'][0] = str(path / 'variant/qemu-10.2.0/configure')
            report.update(schema='stage5-qemu-build-v8', prepared=str(path / 'variant'),
                          prepare_sha256='1' * 64, original_prepare_sha256=v.v7.PREPARE_SHA,
                          preflight=str(v.v5.TOOLENV), preflight_sha256=v.v5.TOOLENV_SHA,
                          predecessor_validator_sha256=v.V7_SHA, fdt_selection='internal',
                          source_review_sha256=v.identity()[1], generated_metadata_before={},
                          generated_metadata_after=v.v7.lock_metadata(path / 'variant', True))
            report['commands'][0]['argv'] = v.v5.configure_argv(prepared)
            if mutation:
                mutation(report)
            v.v4.base().write_new(path / 'build.json', report)
            with patch.object(v, 'checked_variant', return_value=prepared) as check:
                result = v.checked_build(path, v.sha(path / 'build.json'))
                check.assert_called_once_with(str(path / 'variant'), '1' * 64, after_build=True)
                return result

    def test_positive_build_and_unchanged_flags(self):
        self.assertEqual(self.build_fixture()['state'], 'BUILT_NOT_EXECUTED')
        args = v.v5.configure_argv(v.v4.base().read(v.PARENT / 'prepare.json'))
        self.assertEqual(args[-3:], ['--python=/usr/bin/python3.11', '--ninja=/usr/bin/ninja', '--enable-fdt=internal'])
        self.assertIn('--disable-download', args)

    def test_build_identity_and_metadata_mutations(self):
        for key, value in (('schema', 'stage5-qemu-build-v7'), ('state', 'FAIL'),
                           ('source_review_sha256', '0' * 64), ('preflight_sha256', '0' * 64),
                           ('predecessor_validator_sha256', '0' * 64), ('executable_sha256', '0' * 64),
                           ('post_pins_match', False), ('generated_metadata_after', {})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.build_fixture(lambda r: r.update({key: value}))

    def test_argv_environment_owner_and_command_receipt_mutations(self):
        for mutate in (lambda r: r['commands'][0]['argv'].pop(),
                       lambda r: r['commands'][1]['argv'].__setitem__(1, '-j8'),
                       lambda r: r['commands'][0].update(timeout=901),
                       lambda r: r['commands'][0].update(cwd='/wrong'),
                       lambda r: r['commands'][1].update(returncode=1),
                       lambda r: r['commands'][0].update(log_sha256='0' * 64),
                       lambda r: r['environment'].update(LD_PRELOAD='/bad'),
                       lambda r: r['service_owner'].update(main_pid=0),
                       lambda r: r['commands'].pop()):
            with self.assertRaises(ValueError):
                self.build_fixture(mutate)

    def test_prior_failure_and_sealed_parent_preserved(self):
        self.assertEqual(v.sha(v.PARENT / 'prepare.json'), v.PARENT_SHA)
        self.assertEqual(v.sha(v.HERE / 'build_v7.py'), v.V7_SHA)
        self.assertEqual(v.sha(v.OUT / 'stage5_qemu_build_20261110_04/build.json'),
                         '5cad76d71fb693e730b142e78c69fb1ee7d2902dccd7bc63a2281cd8fd9bd1a4')
        self.assertFalse((v.PARENT / 'qemu-10.2.0' / v.DTC / 'libfdt/version.lds').exists())
        self.assertIn(v.REPAIR_OLD, (v.PARENT / 'qemu-10.2.0' / v.REPAIR_PATH).read_bytes())


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    r = v.v4.base()
    OUTPUT = r.fresh(args.output, 'stage5_qemu_build_v8_host_')
    pins, review = v.identity()
    report = dict(schema='stage5-qemu-build-v8-host', state='FAIL', files=pins, source_review_sha256=review,
                  parent_prepare_sha256=v.PARENT_SHA, archive_sha256=v.ARCHIVE_SHA,
                  configure_executed=False, qemu_compiled=False, guest_executed=False)
    def expired(signum, frame):
        raise TimeoutError('180-second host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (OUTPUT / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(ClosureTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        v.require(result.wasSuccessful(), 'V8 host checks failed')
        v.require(v.identity() == (pins, review), 'V8 source drift')
        report['state'] = 'BUILD_V8_STATIC_HOST_PASS_NOT_BUILT'
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
