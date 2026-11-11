import io
import hashlib
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import qemu_source as q


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'primary.tar.xz'
        self.source = self.root / 'source'
        self.source.mkdir()

    def archive_rows(self, extra=(), unsafe_target=q.EXCLUDED_TARGET):
        rows = [('directory', '', b''), ('directory', 'empty/', b''),
                ('file', 'plain.c', b'upstream\n'), ('file', 'exec.sh', b'#!/bin/sh\n'),
                ('symlink', 'alias.c', 'plain.c'), ('symlink', q.EXCLUDED, unsafe_target)]
        with tarfile.open(self.archive, 'w:xz') as archive:
            for kind, name, data in [*rows, *extra]:
                member = tarfile.TarInfo(q.ROOT + ('/' + name if name else ''))
                if kind == 'directory':
                    member.type, member.mode = tarfile.DIRTYPE, 0o755
                elif kind == 'symlink':
                    member.type, member.linkname = tarfile.SYMTYPE, data
                else:
                    member.size = len(data)
                    member.mode = 0o755 if name == 'exec.sh' else 0o644
                archive.addfile(member, io.BytesIO(data) if kind == 'file' else None)
        return q.sha(self.archive)

    def capture(self):
        checksum = self.archive_rows(extra=[('directory', n, b'') for n in
            ('subprojects', 'tests', 'tests/qemu-iotests')])
        (self.source / 'empty').mkdir()
        (self.source / 'plain.c').write_bytes(b'candidate\n')
        (self.source / 'exec.sh').write_bytes(b'#!/bin/sh\n')
        (self.source / 'exec.sh').chmod(0o755)
        (self.source / 'alias.c').symlink_to('plain.c')
        (self.source / 'subprojects/dtc').mkdir(parents=True)
        (self.source / 'subprojects/dtc/file.c').write_bytes(b'tracked-dtc\n')
        (self.source / q.LOCK).write_bytes(b'')
        (self.source / q.SCRATCH).mkdir(parents=True)
        output = self.root / 'bundle'
        report = q.capture(self.archive, self.source, output, expected_sha=checksum)
        return checksum, output, report

    def test_portable_capture_and_real_tiny_source_reconstruction(self):
        checksum, bundle, report = self.capture()
        self.assertEqual((report['modified_files'], report['added_files'], report['added_directories']), (1, 1, 1))
        self.assertEqual(len(report['observed_generated']), 2)
        manifest = q.load(bundle / 'manifest.json')
        self.assertNotIn(str(self.root), q.canonical(manifest).decode())
        self.source.rename(self.root / 'unavailable-origin')
        with mock.patch.object(q, 'PRIMARY_SHA', checksum):
            result = q.reconstruct(self.archive, bundle, self.root / 'clean')
        self.assertEqual(result['state'], 'SOURCE_RECONSTRUCTED_NOT_BUILT')
        clean = self.root / 'clean' / q.ROOT
        self.assertEqual((clean / 'plain.c').read_bytes(), b'candidate\n')
        self.assertTrue((clean / 'exec.sh').stat().st_mode & 0o100)
        self.assertFalse((clean / q.EXCLUDED).exists())
        self.assertFalse((clean / q.LOCK).exists())
        self.assertFalse((clean / q.SCRATCH).exists())

    def test_archive_directory_trailing_slash_is_normalized(self):
        checksum = self.archive_rows()
        rows, _ = q.archive_inventory(self.archive, checksum)
        self.assertIn('empty', rows)
        self.assertNotIn('empty/', rows)

    def test_wrong_primary_sha_is_rejected(self):
        self.archive_rows()
        with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
            q.archive_inventory(self.archive, '0' * 64)

    def test_only_exact_unsafe_symlink_is_excluded(self):
        checksum = self.archive_rows(unsafe_target='/other')
        with self.assertRaisesRegex(ValueError, 'exclusion changed'):
            q.archive_inventory(self.archive, checksum)

    def test_unexpected_absolute_or_escaping_links_are_rejected(self):
        for target in ('/outside', '../../outside'):
            with self.subTest(target=target):
                checksum = self.archive_rows(extra=[('symlink', 'other-link', target)])
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    q.archive_inventory(self.archive, checksum)

    def test_duplicate_and_traversal_archive_members_rejected(self):
        for name in ('plain.c', '../outside'):
            with self.subTest(name=name):
                checksum = self.archive_rows(extra=[('file', name, b'bad')])
                with self.assertRaises(ValueError):
                    q.archive_inventory(self.archive, checksum)

    def test_nonempty_lock_not_ignored(self):
        (self.source / 'subprojects').mkdir()
        (self.source / q.LOCK).write_bytes(b'not-empty')
        with self.assertRaisesRegex(ValueError, 'empty generated wrap lock'):
            q.tree_inventory(self.source)

    def test_nonempty_or_symlink_scratch_not_ignored(self):
        scratch = self.source / q.SCRATCH
        scratch.parent.mkdir(parents=True)
        scratch.mkdir()
        (scratch / 'unexpected').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'empty generated scratch'):
            q.tree_inventory(self.source)
        (scratch / 'unexpected').unlink()
        scratch.rmdir()
        scratch.symlink_to('other')
        with self.assertRaisesRegex(ValueError, 'empty generated scratch'):
            q.tree_inventory(self.source)

    def test_scratch_prefix_is_not_a_general_exclusion(self):
        path = self.source / (q.SCRATCH + '-other')
        path.parent.mkdir(parents=True)
        path.write_bytes(b'not ignored')
        rows, generated = q.tree_inventory(self.source)
        self.assertIn(q.SCRATCH + '-other', rows)
        self.assertEqual(generated, [])

    def test_missing_source_file_and_duplicate_edit_rejected(self):
        row = dict(kind='file', sha256='0' * 64, size=1, executable=False)
        with self.assertRaisesRegex(ValueError, 'deletion'):
            q.delta({'a': row}, {})
        edit = dict(path='a', before=None, after=row)
        with self.assertRaisesRegex(ValueError, 'preimage mismatch'):
            q.replay({}, [edit, edit])

    def test_source_type_change_rejected(self):
        before = dict(kind='file', sha256='0' * 64, size=1, executable=False)
        with self.assertRaisesRegex(ValueError, 'type/link'):
            q.replay({'a': before}, [dict(path='a', before=before, after=dict(kind='directory'))])

    def test_payload_mutation_rejected(self):
        _, bundle, _ = self.capture()
        payload = bundle / 'payload.tar.xz'
        payload.write_bytes(payload.read_bytes() + b'drift')
        with self.assertRaisesRegex(ValueError, 'Payload SHA mismatch'):
            q.payload_bytes(payload, q.load(bundle / 'manifest.json'))

    def test_dtc_byte_identity_records_delivery_mode_without_changing_it(self):
        archive = self.root / 'dtc.tar'
        final = {}
        with tarfile.open(archive, 'w:') as original:
            for i in range(310):
                name = 'pylibfdt/setup.py' if i == 0 else 'file-' + str(i)
                member = tarfile.TarInfo(name)
                member.mode, member.size = (0o755 if i == 0 else 0o644), 1
                original.addfile(member, io.BytesIO(b'x'))
                final['subprojects/dtc/' + name] = dict(kind='file', size=1,
                    sha256=hashlib.sha256(b'x').hexdigest(), executable=False)
        final['subprojects/dtc/.meson-subproject-wrap-hash.txt'] = dict(kind='file', size=0,
            sha256=hashlib.sha256(b'').hexdigest(), executable=False)
        with mock.patch.object(q, 'DTC_SHA', q.sha(archive)):
            result = q.dtc_identity(archive, final)
            self.assertEqual(result['tracked_files'], 310)
            self.assertEqual(result['executable_bit_differences'], [dict(path='pylibfdt/setup.py',
                git_archive_executable=True, delivery_executable=False)])
            final['subprojects/dtc/file-1']['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'source byte mismatch'):
                q.dtc_identity(archive, final)


if __name__ == '__main__':
    unittest.main()
