"""Offline tests only; never consumes or modifies a sealed coverage input."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verification_epoch import AliasBinding, EpochError, VerificationEpoch


def digest(data):
    return hashlib.sha256(data).hexdigest()


class EpochTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.file = self.root / 'input.json'
        self.data = b'{"state":[1,true,{"value":7}]}\n'
        self.file.write_bytes(self.data)
        self.sha = digest(self.data)

    def epoch(self):
        return VerificationEpoch({str(self.file): self.sha})

    def alias(self):
        link = self.root / 'alias'
        link.symlink_to(self.file.name)
        pins = {str(self.file): self.sha, str(link): self.sha}
        binding = AliasBinding(self.file.name, str(self.file), self.sha)
        return link, pins, {str(link): binding}

    def test_read_hash_parse_same_bytes_once(self):
        epoch = self.epoch()
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Second file read')):
            capture = epoch.read(self.file, self.sha)
            first = epoch.json(self.file, self.sha)
            second = epoch.json(self.file, self.sha)
        self.assertIs(first, second)
        self.assertEqual(capture.data, self.data)
        self.assertEqual(dict(epoch.finish()), dict(reads=1, hashes=1, parses=1, verified_paths=1))

    def test_json_and_capture_immutable(self):
        epoch = self.epoch()
        value = epoch.json(self.file, self.sha)
        with self.assertRaises(TypeError):
            value['state'][2]['value'] = 99
        with self.assertRaises(TypeError):
            value['state'][0] = 99
        self.assertEqual(epoch.read(self.file, self.sha).data, self.data)

    def test_wrong_sha_rejected_and_epoch_poisoned(self):
        epoch = VerificationEpoch({str(self.file): '0' * 64})
        with self.assertRaises(EpochError):
            epoch.read(self.file, '0' * 64)
        with self.assertRaises(EpochError):
            epoch.finish()

    def test_conflicting_request_after_cache_rejected(self):
        epoch = self.epoch()
        epoch.read(self.file, self.sha)
        with self.assertRaises(EpochError):
            epoch.read(self.file, '0' * 64)

    def test_unknown_pin_rejected(self):
        with self.assertRaises(EpochError):
            self.epoch().read(self.root / 'unknown', self.sha)

    def test_alias_exact_endpoint_shared_once(self):
        link, pins, aliases = self.alias()
        epoch = VerificationEpoch(pins, aliases)
        first = epoch.json(link, self.sha)
        self.assertIs(first, epoch.json(self.file, self.sha))
        self.assertEqual(dict(epoch.finish()), dict(reads=1, hashes=1, parses=1, verified_paths=2))

    def test_alias_without_endpoint_pin_rejected(self):
        link, pins, aliases = self.alias()
        del pins[str(self.file)]
        with self.assertRaises(EpochError):
            VerificationEpoch(pins, aliases)

    def test_alias_conflicting_endpoint_pin_rejected(self):
        _, pins, aliases = self.alias()
        pins[str(self.file)] = '0' * 64
        with self.assertRaises(EpochError):
            VerificationEpoch(pins, aliases)

    def test_unapproved_alias_rejected(self):
        link, pins, _ = self.alias()
        with self.assertRaises(EpochError):
            VerificationEpoch(pins).read(link, self.sha)

    def test_wrong_literal_alias_same_endpoint_rejected(self):
        link, pins, aliases = self.alias()
        link.unlink()
        link.symlink_to('./' + self.file.name)
        with self.assertRaises(EpochError):
            VerificationEpoch(pins, aliases).read(link, self.sha)

    def test_alias_retargeted_after_capture_rejected(self):
        link, pins, aliases = self.alias()
        epoch = VerificationEpoch(pins, aliases)
        epoch.read(link, self.sha)
        other = self.root / 'other.json'
        other.write_bytes(self.data)
        link.unlink()
        link.symlink_to(other.name)
        with self.assertRaises(EpochError):
            epoch.read(link, self.sha)

    def test_changed_bytes_same_size_mtime_fresh_epoch_rejected(self):
        epoch = self.epoch()
        epoch.read(self.file, self.sha)
        before = self.file.stat()
        self.file.write_bytes(self.data.replace(b'7', b'8'))
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(EpochError):
            self.epoch().read(self.file, self.sha)

    def test_visible_metadata_change_rejects_cached_reuse(self):
        epoch = self.epoch()
        epoch.read(self.file, self.sha)
        before = self.file.stat()
        os.utime(self.file, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
        with self.assertRaises(EpochError):
            epoch.read(self.file, self.sha)

    def test_invisible_metadata_change_is_not_live_content_attestation(self):
        epoch = self.epoch()
        original = epoch.read(self.file, self.sha)
        identity = epoch._guards[str(self.file)]
        self.file.write_bytes(self.data.replace(b'7', b'8'))
        # Model indistinguishable filesystem metadata; only captured bytes are
        # reusable. A fresh epoch must still reject the changed live contents.
        with patch('verification_epoch._identity', return_value=identity):
            self.assertIs(epoch.read(self.file, self.sha), original)
            self.assertEqual(original.data, self.data)
        with self.assertRaises(EpochError):
            self.epoch().read(self.file, self.sha)

    def test_replaced_inode_rejected(self):
        epoch = self.epoch()
        epoch.read(self.file, self.sha)
        replacement = self.root / 'replacement'
        replacement.write_bytes(self.data)
        replacement.replace(self.file)
        with self.assertRaises(EpochError):
            epoch.finish()

    def test_mutation_during_read_rejected(self):
        original = os.fstat
        calls = []

        def mutate(fd):
            calls.append(fd)
            if len(calls) == 2:
                self.file.write_bytes(self.data.replace(b'7', b'8'))
            return original(fd)

        with patch('verification_epoch.os.fstat', side_effect=mutate):
            with self.assertRaises(EpochError):
                self.epoch().read(self.file, self.sha)

    def test_missing_pin_finish_rejected(self):
        other = self.root / 'other'
        other.write_bytes(b'other')
        epoch = VerificationEpoch({str(self.file): self.sha, str(other): digest(b'other')})
        epoch.read(self.file, self.sha)
        with self.assertRaises(EpochError):
            epoch.finish()

    def test_nonregular_endpoint_rejected(self):
        epoch = VerificationEpoch({str(self.root): self.sha})
        with self.assertRaises(EpochError):
            epoch.read(self.root, self.sha)

    def test_parent_alias_rejected(self):
        parent = self.root / 'linked'
        parent.symlink_to(self.root, target_is_directory=True)
        path = parent / self.file.name
        with self.assertRaises(EpochError):
            VerificationEpoch({str(path): self.sha}).read(path, self.sha)

    def test_invalid_expected_sha_and_relative_path_rejected(self):
        for name, sha in ((str(self.file), True), (str(self.file), 'A' * 64),
                          ('relative', self.sha), (str(self.root) + '/x/../input.json', self.sha)):
            with self.subTest(name=name, sha=sha), self.assertRaises(EpochError):
                VerificationEpoch({name: sha})

    def test_duplicate_json_and_nonfinite_rejected(self):
        for data in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}', b'{'):
            with self.subTest(data=data):
                self.file.write_bytes(data)
                epoch = VerificationEpoch({str(self.file): digest(data)})
                with self.assertRaises(ValueError):
                    epoch.json(self.file, digest(data))
                with self.assertRaises(EpochError):
                    epoch.finish()

    def test_fresh_epoch_rehashes_and_rejects_changed_content(self):
        first = self.epoch()
        first.json(self.file, self.sha)
        first.finish()
        second = self.epoch()
        second.json(self.file, self.sha)
        self.assertEqual(second.statistics['hashes'], 1)
        self.file.write_bytes(self.data.replace(b'7', b'8'))
        with self.assertRaises(EpochError):
            self.epoch().read(self.file, self.sha)

    def test_close_disables_reuse(self):
        epoch = self.epoch()
        epoch.read(self.file, self.sha)
        epoch.close()
        with self.assertRaises(EpochError):
            epoch.read(self.file, self.sha)


if __name__ == '__main__':
    unittest.main()
