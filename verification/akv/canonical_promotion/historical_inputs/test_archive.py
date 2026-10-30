"""Host-only mutation tests using small receipts, never an EDA executable."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import archive as a


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.host-test-', dir=a.HERE)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'root'
        self.root.mkdir()
        changed = {}
        for name in a.CHANGED:
            self.put(self.root / name, ('original ' + name).encode())
            changed[name] = a.digest(self.root / name)
        self.put(self.root / 'Bender.lock', b'locked dependencies')
        self.put(self.root / 'hardware/include/old.svh', b'old header')
        self.put(self.root / 'hardware/include/ara/pkg.sv', b'old package')
        self.put(self.root / 'sources.f', ('+incdir+' + str(self.root / 'hardware/include') + '\n').encode())
        all_pins = {str(p): a.digest(p) for p in self.root.rglob('*') if p.is_file()}
        self.names = ['receipts/' + str(i) + '.json' for i in range(6)]
        for i, name in enumerate(self.names):
            data = (dict(schema_version=1, repo_root=str(self.root), filelist=str(self.root / 'sources.f'),
                         files=[dict(path=k, sha256=v) for k, v in all_pins.items()]) if i == 0 else all_pins)
            self.put(self.root / name, json.dumps(data).encode())
        receipts = {n: a.digest(self.root / n) for n in self.names}
        self.constants = patch.multiple(a, CHANGED=changed, RECEIPTS=receipts, BASELINE=self.names[0])
        self.constants.start()
        self.addCleanup(self.constants.stop)
        self.output = self.base / 'archive'
        self.sha = a.prepare(self.root, self.output)
        self.archive = a.Archive(self.output, self.sha)

    @staticmethod
    def put(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_exact_copies_and_all_six_receipts(self):
        self.assertEqual(len(self.archive.report['receipts']), 6)
        for name, sha in self.archive.report['payload'].items():
            self.assertEqual(a.digest(self.output / 'payload' / name), sha)
            self.assertFalse((self.output / 'payload' / name).is_symlink())
        for name in self.names:
            self.archive.verify(self.archive.pins(name))

    def test_changed_current_root_still_consumes_old_sha(self):
        for name in a.CHANGED:
            (self.root / name).write_bytes(b'promoted different bytes')
        for name in self.names:
            self.archive.verify(self.archive.pins(name))

    def test_unknown_changed_hash_rejected(self):
        pins = self.archive.pins(self.names[0])
        pins[str(self.root / 'Bender.yml')] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Unknown historical version'):
            self.archive.verify(pins)

    def test_nonmapped_pin_still_verified(self):
        (self.root / 'Bender.lock').write_bytes(b'changed lock')
        with self.assertRaisesRegex(ValueError, 'Pin drift'):
            self.archive.verify(self.archive.pins(self.names[0]))

    def test_existing_header_change_not_exempt(self):
        (self.root / 'hardware/include/old.svh').write_bytes(b'changed old header')
        with self.assertRaisesRegex(ValueError, 'Pin drift'):
            self.archive.verify(self.archive.pins(self.names[0]))

    def test_live_added_header_is_not_historical(self):
        self.put(self.root / 'hardware/include/shared_reader_types.svh', b'new header')
        scanned = self.archive.historical_include()
        self.assertEqual(len(scanned), 2)
        self.assertNotIn('shared_reader_types.svh', ' '.join(scanned))
        self.archive.verify(self.archive.pins(self.names[0]))

    def test_archive_added_header_rejected(self):
        self.put(self.output / 'payload/hardware/include/new.svh', b'injected')
        with self.assertRaisesRegex(ValueError, 'inventory'):
            a.Archive(self.output, self.sha)
        with self.assertRaisesRegex(ValueError, 'inventory'):
            self.archive.historical_include()

    def test_archive_wrong_data_rejected(self):
        (self.output / 'payload/Bender.yml').write_bytes(b'wrong')
        with self.assertRaises(ValueError):
            a.Archive(self.output, self.sha)
        with self.assertRaises(ValueError):
            self.archive.verify(self.archive.pins(self.names[0]))

    def test_wrong_reviewed_manifest_hash(self):
        with self.assertRaisesRegex(ValueError, 'receipt drift'):
            a.Archive(self.output, 'f' * 64)

    def test_symlink_replacement_rejected(self):
        target = self.output / 'payload/Bender.yml'
        target.unlink()
        target.symlink_to(self.root / 'Bender.yml')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            a.Archive(self.output, self.sha)

    def test_relocated_archive_uses_relative_payload(self):
        moved = self.base / 'relocated'
        shutil.copytree(self.output, moved)
        archive = a.Archive(moved, self.sha)
        self.assertTrue(all(Path(p).is_relative_to(moved) for p in archive.historical_include()))
        archive.verify(archive.pins(self.names[0]))

    def test_wrong_receipt_not_admitted(self):
        with self.assertRaisesRegex(ValueError, 'six admitted'):
            self.archive.pins('new-manifest.json')

    def test_no_overwrite(self):
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            a.prepare(self.root, self.output)

    def test_new_header_cannot_be_archived_as_original(self):
        self.put(self.root / 'hardware/include/new.svh', b'new')
        with self.assertRaisesRegex(ValueError, 'historical inventory'):
            a.prepare(self.root, self.base / 'bad-archive')

    def test_original_receipt_mutation_rejected(self):
        (self.root / self.names[1]).write_text('{}')
        with self.assertRaisesRegex(ValueError, 'original receipt'):
            a.prepare(self.root, self.base / 'bad-receipt')

    def test_filelist_bytes_preserved_and_not_rebased(self):
        self.assertEqual((self.output / 'payload/sources.f').read_bytes(), (self.root / 'sources.f').read_bytes())
        self.assertIn(str(self.root).encode(), (self.output / 'payload/sources.f').read_bytes())

    def test_software_pins_are_not_canonical_mappings(self):
        path = self.root / 'software/akv/src/akv_v2_native_riscv.c'
        self.put(path, b'current software')
        pins = {str(path): hashlib.sha256(b'historical software').hexdigest()}
        self.assertEqual(self.archive.mapped_pins(pins), pins)
        with self.assertRaisesRegex(ValueError, 'Pin drift'):
            self.archive.verify(pins)


if __name__ == '__main__':
    unittest.main()
