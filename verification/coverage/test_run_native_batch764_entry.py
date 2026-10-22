import inspect
import json
import unittest
from unittest.mock import patch
import run_native_batch764_entry as entry


class Entry(unittest.TestCase):
    def test_exact_three_substitutions_only(self):
        before=inspect.getsource(entry.report.old.verify)
        expected=before.replace("len(c['expected_union']['fma'])", "len(c['expected_union']['retained']['fma'])")
        expected=expected.replace('        if path.exists():','        snapshot_stdout(data,out)\n        if path.exists():')
        anchor="    audit_six(out, 'child', c['child_references'])"
        expected=expected.replace(anchor,anchor+"\n    audit_six(out, 'batch_scale', c['batch_scale_references'])")
        self.assertEqual(entry.verifier_body(),expected)

    def test_actual_sealed_metadata_path(self):
        c=entry.life.read_bound(entry.OUTPUT/'config.json',entry.CONFIG_SHA)
        self.assertEqual(len(c['expected_union']['retained']['fma']),612)
        self.assertEqual(len(c['expected_union']['c910240']),240)
        self.assertEqual(c['qualified_fsm_union'],173)

    def test_anchor_drift_rejected(self):
        with patch.object(entry.inspect,'getsource',return_value='def verify(): pass\n'):
            with self.assertRaises(Exception):entry.verifier_body()


if __name__=='__main__':unittest.main()
