"""The successor cannot accidentally accept the archived byte-hash build."""
from pathlib import Path
import unittest
from unittest.mock import patch

import run_value_decode_fast as r


class FastRunTest(unittest.TestCase):
    def test_successor_metadata(self):
        good = dict(harness='scalar_integer_compare_word_hash_once_per_capture',
                    hash_algorithm='word_fnv64')
        for changed in ({}, dict(good, harness='old'), dict(good, hash_algorithm='byte_fnv64')):
            with self.subTest(changed=changed), patch.object(r.s, 'read_json', return_value=changed), \
                    patch.object(r, 'checked_original_build') as original:
                with self.assertRaises(ValueError):
                    r.checked_build(Path('/unused'))
                original.assert_not_called()

    def test_reuses_original_image_and_workload_gates(self):
        good = dict(harness='scalar_integer_compare_word_hash_once_per_capture',
                    hash_algorithm='word_fnv64')
        with patch.object(r.s, 'read_json', return_value=good), \
                patch.object(r, 'checked_original_build', return_value=(good, {'image':'pin'}, {})) as gate, \
                patch.object(r.s, 'hashes', return_value={'successor':'0'*64}):
            report, image, pins = r.checked_build(Path('/unused'))
        gate.assert_called_once_with(Path('/unused'))
        self.assertEqual(pins['successor'], '0'*64)
        self.assertEqual(image, {'image':'pin'})


if __name__ == '__main__':
    unittest.main()
