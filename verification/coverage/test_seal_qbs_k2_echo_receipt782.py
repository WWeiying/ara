from pathlib import Path
import tempfile
from unittest.mock import patch
import unittest

import seal_qbs_k2_echo_receipt782 as receipt


class ReceiptTests(unittest.TestCase):
    def test_actual_core_structure_and_guard(self):
        with patch.object(receipt.life,'check'):
            r=receipt.record()
        self.assertEqual(r['core_qualification_sha256'],receipt.CORE_SHA)
        self.assertEqual(r['guard']['actual_objects'],42)
        self.assertFalse(r['coverage_admitted']);self.assertFalse(r['changes_to_core'])

    def test_core_hash_drift_reject(self):
        with patch.object(receipt,'CORE_SHA','a'*64),self.assertRaises(ValueError):receipt.record()

    def test_echo_source_drift_reject(self):
        with patch.object(receipt,'ECHO_SHA','b'*64),self.assertRaises(ValueError):receipt.record()

    def test_exclusive_publication_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d,patch.object(receipt.life,'OUT',Path(d)):
            p=Path(d)/'receipt.json';receipt.publish(p,{'sentinel':1});before=p.read_bytes()
            with self.assertRaises(ValueError):receipt.publish(p,{'sentinel':2})
            self.assertEqual(p.read_bytes(),before)


if __name__=='__main__':unittest.main()
