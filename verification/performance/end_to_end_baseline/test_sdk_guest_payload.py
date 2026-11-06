"""In-memory negative tests for the successor guest payload gate."""
from copy import deepcopy
from pathlib import Path
import stat
import struct
import unittest
from unittest.mock import patch

import audit_sdk_guest_payload as a


def elf(tag):
    data = bytearray(64)
    data[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI', data, 16, 2, 243, 1)
    struct.pack_into('<H', data, 52, 64)
    return bytes(data) + tag


def expected():
    return {name: elf(name.encode()) for name in ('init', 'base', 'candidate', 'test')}


def record(name, data=b'', mode=0, ino=0, magic=b'070701', links=None):
    encoded = name.encode() + b'\0'
    trailer = name == 'TRAILER!!!'
    fields = [ino, mode, 0, 0, links if links is not None else (2 if stat.S_ISDIR(mode) else 1),
              0, len(data), 0 if trailer else 3, 0 if trailer else 1,
              5 if name == 'dev/console' else 0, 1 if name == 'dev/console' else 0,
              len(encoded), sum(data) & 0xffffffff if magic == b'070702' else 0]
    result = magic + b''.join(f'{field:08x}'.encode() for field in fields) + encoded
    result += bytes((-len(result)) % 4)
    result += data
    result += bytes((-len(result)) % 4)
    return result


def archive(payloads=None, overrides=None, extra=(), magic=b'070701'):
    payloads = expected() if payloads is None else payloads
    overrides = overrides or {}
    parts = []
    for ino, (name, mode) in enumerate(a.EXPECTED_MODES.items(), 1):
        parts.append(record(name, payloads.get(name, b''), overrides.get(name, mode), ino, magic))
    parts.extend(extra)
    return b''.join(parts) + record('TRAILER!!!', magic=magic)


class NewcTests(unittest.TestCase):
    def test_complete_exact_mapping_and_crc_format(self):
        for magic in (b'070701', b'070702'):
            raw = archive(magic=magic)
            report = a.validate_payload(raw + bytes(511), expected())
            self.assertEqual(set(report['entries']), {'/' + name for name in a.EXPECTED_MODES})
            self.assertEqual(report['layout']['trailing_nul_bytes'], 511)
            self.assertEqual(report['entries']['/candidate']['sha256'], a.sha(expected()['candidate']))

    def test_reject_aa_packaging_and_aa_expected_targets(self):
        payloads = expected()
        payloads['candidate'] = payloads['base']
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            a.validate_payload(archive(payloads), expected())
        with self.assertRaisesRegex(ValueError, 'A/A'):
            a.validate_payload(archive(payloads), payloads)

    def test_duplicate_and_extraneous_entry(self):
        for extra, message in ((record('base', elf(b'base'), stat.S_IFREG | 0o755, 99), 'Duplicate archive name'),
                               (record('extra', b'x', stat.S_IFREG | 0o755, 99), 'entry set')):
            with self.assertRaisesRegex(ValueError, message):
                a.validate_payload(archive(extra=[extra]), expected())

    def test_every_truncated_prefix_rejected(self):
        raw = archive()
        for end in range(len(raw)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                a.parse_newc(raw[:end])

    def test_traversal_absolute_aliases_and_bad_nul_names(self):
        for name in ('../evil', 'dev/../evil', '/base', './base', 'dev//console', 'dev/./console',
                     'dev\\console', 'base\0evil', 'base\nfile', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                a.parse_newc(record(name, b'', stat.S_IFREG | 0o755, 99) + record('TRAILER!!!'))
        raw = bytearray(archive())
        raw[110 + len('dev')] = ord('x')
        with self.assertRaisesRegex(ValueError, 'final NUL'):
            a.parse_newc(bytes(raw))

    def test_wrong_modes_symlink_setuid_and_extraneous_data(self):
        for mode in (stat.S_IFREG | 0o644, stat.S_IFLNK | 0o755, stat.S_IFREG | 0o4755):
            with self.assertRaisesRegex(ValueError, 'mode/owner'):
                a.validate_payload(archive(overrides={'candidate': mode}), expected())
        payloads = expected()
        payloads['tmp'] = b'not empty'
        with self.assertRaisesRegex(ValueError, 'Nonempty'):
            a.validate_payload(archive(payloads), expected())

    def test_bad_magic_hex_lengths_and_alignment_padding(self):
        raw = archive()
        mutations = []
        for start, content in ((0, b'070707'), (6, b'       1'), (94, b'00000000'),
                               (94, b'ffffffff'), (54, b'ffffffff'), (114, b'\x01')):
            broken = bytearray(raw)
            broken[start:start + len(content)] = content
            mutations.append(bytes(broken))
        for broken in mutations:
            with self.assertRaises(ValueError):
                a.parse_newc(broken)
        entries, _ = a.parse_newc(raw)
        start = entries['candidate']['header_offset']
        payload_start = (start + 110 + len('candidate') + 1 + 3) & ~3
        payload_end = payload_start + len(expected()['candidate'])
        self.assertNotEqual(payload_end % 4, 0)
        broken = bytearray(raw)
        broken[payload_end] = 1
        with self.assertRaisesRegex(ValueError, 'payload alignment'):
            a.parse_newc(bytes(broken))

    def test_missing_bad_trailer_and_nonzero_tail_or_second_archive(self):
        raw = archive()
        for broken in (raw[:-len(record('TRAILER!!!'))], raw + b'x', raw + archive(),
                       raw[:-len(record('TRAILER!!!'))] + record('TRAILER!!!', b'x')):
            with self.assertRaises(ValueError):
                a.parse_newc(broken)

    def test_crc_corruption_and_noncrc_checksum(self):
        raw = bytearray(archive(magic=b'070702'))
        entries, _ = a.parse_newc(bytes(raw))
        start = entries['base']['header_offset']
        data_start = (start + 110 + len('base') + 1 + 3) & ~3
        raw[data_start] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            a.parse_newc(bytes(raw))
        raw = bytearray(archive())
        raw[102:110] = b'00000001'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            a.parse_newc(bytes(raw))

    def test_duplicate_inode_and_hardlink_count(self):
        raw = bytearray(archive())
        entries, _ = a.parse_newc(bytes(raw))
        offset = entries['base']['header_offset']
        raw[offset + 6:offset + 14] = b'00000001'
        with self.assertRaisesRegex(ValueError, 'inode'):
            a.parse_newc(bytes(raw))
        raw = bytearray(archive())
        raw[offset + 38:offset + 46] = b'00000002'
        with self.assertRaisesRegex(ValueError, 'hardlinks'):
            a.validate_payload(bytes(raw), expected())

    def test_non_riscv_or_non_elf_target_rejected(self):
        for payload in (b'#!/bin/sh\n', elf(b'x')[:63], b'\x7fELF\x01' + bytes(80)):
            payloads = expected()
            payloads['test'] = payload
            with self.assertRaisesRegex(ValueError, 'RV64'):
                a.validate_payload(archive(payloads), payloads)


class BindingTests(unittest.TestCase):
    def test_link_exact_only_archive_output_change(self):
        original = ['/compiler', '-static', '/model.o', '/baseline.a', '-lm', '-o', '/old']
        result = a.expected_link(original, Path('/model.o'), Path('/baseline.a'), Path('/new.a'),
                                 Path('/old'), Path('/worker/candidate'))
        self.assertEqual(result, ['/compiler', '-static', '/model.o', '/new.a', '-lm', '-o', '/worker/candidate'])
        row = dict(label='link-candidate', argv=result, returncode=0, cwd='/worker')
        a.validate_link([row], result, Path('/worker'))
        for key, value in (('returncode', 1), ('cwd', '/other'), ('argv', original)):
            broken = deepcopy(row)
            broken[key] = value
            with self.assertRaises(ValueError):
                a.validate_link([broken], result, Path('/worker'))
        with self.assertRaises(ValueError):
            a.validate_link([row, row], result, Path('/worker'))

    def test_target_must_be_in_worker_pins_and_match_accepted_identity(self):
        path = Path(__file__).resolve()
        pins = a.Pins()
        with self.assertRaisesRegex(ValueError, 'absent'):
            a.pinned_input(pins, {}, path, 'a' * 64)
        with self.assertRaisesRegex(ValueError, 'disagrees'):
            a.pinned_input(pins, {str(path): 'a' * 64}, path, 'b' * 64)
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            a.pinned_input(pins, {str(path): 'a' * 64}, path, 'a' * 64)

    def test_pin_drift_is_not_replaced_and_other_outputs_refused(self):
        pins, path = a.Pins(), Path(__file__).resolve()
        with patch.object(a, 'digest', side_effect=['old', 'new', 'new']):
            pins.pin(path)
            with self.assertRaisesRegex(ValueError, 'drift'):
                pins.pin(path)
            self.assertEqual(pins.values[str(path)], 'old')
            with self.assertRaisesRegex(ValueError, 'drift'):
                pins.verify()
        with self.assertRaisesRegex(ValueError, 'assigned fresh'):
            a.audit(a.MAIN / 'not-allowed')
        with patch.object(a, 'ownership', return_value=[]), \
                patch.object(Path, 'mkdir', side_effect=FileExistsError), patch.object(a, 'write_new') as write:
            with self.assertRaises(FileExistsError):
                a.audit(a.OUT)
            write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
