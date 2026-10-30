#!/usr/bin/env python3
"""The one-run exception must never admit changed executable or missing input."""
import unittest
import audit_native_document_drift as a


class DocumentDriftTest(unittest.TestCase):
    def test_only_known_document_may_differ(self):
        pins = {str(a.DOCUMENT):a.OLD_DOCUMENT,'/example/runtime.c':'same'}
        current = {str(a.DOCUMENT):'new','/example/runtime.c':'same'}
        self.assertEqual(a.classify_drift(pins,current)['current'],'new')
        for changed in ({str(a.DOCUMENT):'new','/example/runtime.c':'changed'},
                        {str(a.DOCUMENT):'new'},pins):
            with self.assertRaises(ValueError):
                a.classify_drift(pins,changed)
        with self.assertRaises(ValueError):
            a.classify_drift({str(a.DOCUMENT):'other version'},current)


if __name__ == '__main__':
    unittest.main()
