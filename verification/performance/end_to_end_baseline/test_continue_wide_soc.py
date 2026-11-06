"""The handoff admission bridge cannot change an ELF or hide failed producers."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import continue_wide_soc as c


class HandoffAdmissionTests(unittest.TestCase):
    def producer(self, root, state=c.HANDOFF_STATE):
        f = root / 'image.elf'; f.write_bytes(b'fixed ELF fixture')
        (root / 'source-pins.json').write_text(json.dumps({str(f): c.digest(f)}))
        value = dict(state=state, post_pins_match=True, expected_exceptions=0,
                     skip_is_not_acceptance=True, source_pins_sha256=c.digest(root / 'source-pins.json'),
                     artifacts={str(f): c.digest(f)}, elf=str(f), elf_sha256=c.digest(f))
        (root / 'result.json').write_text(json.dumps(value))
        return value

    def test_interface_adapter_preserves_elf_and_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = root / 'original'; original.mkdir()
            old = self.producer(original); sha = c.digest(original / 'result.json')
            with patch.object(c, 'HANDOFF_HASH', sha): new = c.handoff_adapter(original, root / 'adapter')
            self.assertEqual(new['elf_sha256'], old['elf_sha256'])
            self.assertEqual(c.digest(original / 'result.json'), sha)
            self.assertEqual(new['producer_state'], c.HANDOFF_STATE)
            self.assertFalse(new['producer_relabelled'])
            self.assertEqual(c.digest(root / 'adapter/source-pins.json'), old['source_pins_sha256'])

    def test_wrong_hash_or_failed_producer_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.producer(root, 'FAIL')
            with self.assertRaises(ValueError): c.handoff_adapter(root, root / 'bad')
            with patch.object(c, 'HANDOFF_HASH', c.digest(root / 'result.json')):
                with self.assertRaises(ValueError): c.handoff_adapter(root, root / 'bad')

    def test_no_worker_state_or_no_protocol_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertIsNone(c.require_terminal(root, 128, 'elf'))
            for state in ('FAIL', 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED', 'PASS'):
                (root / 'result.json').write_text(json.dumps(dict(state=state)))
                with self.assertRaises(ValueError): c.require_terminal(root, 128, 'elf')


if __name__ == '__main__': unittest.main()
