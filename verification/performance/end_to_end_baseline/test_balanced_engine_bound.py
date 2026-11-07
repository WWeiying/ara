import inspect
import json
from pathlib import Path
import unittest

from audit import digest
import run_balanced_engine as parent
import run_balanced_engine_bound as c


class BoundController(unittest.TestCase):
    def test_exact_failed_producer_and_identity_only_successor(self):
        fn,report=c.build()
        self.assertEqual(digest(parent.__file__),c.SOURCE_SHA)
        self.assertEqual(digest(c.FIRST/'result.json'),c.FIRST_SHA)
        self.assertTrue(report['source_reversible'])
        self.assertFalse(report['original_failure_relabelled'])
        self.assertEqual(inspect.signature(fn),inspect.signature(parent.run))
        self.assertIn('test_balanced_engine_bound',fn.__globals__['TESTS'])
        self.assertIsNot(fn,parent.run)
        self.assertEqual(fn.__globals__['__file__'],str(Path(c.__file__).resolve()))

    def test_probe_has_the_exact_accepted_identity_in_fault_audit(self):
        probe=parent.HERE/'matrix_replay_probe.svh'
        base=json.loads((parent.BASE/'source-pins.json').read_text())
        old=json.loads((parent.PRIOR/'source-pins.json').read_text())
        self.assertNotIn(str(probe),base)
        self.assertEqual(old[str(probe)],digest(probe))
        self.assertEqual(old[str(probe)],'2d02a70fe391613752dd633d7aacc65ce1f039ed98761f93b022b78a2755367a')

    def test_missing_duplicate_and_already_changed_identity_rejected(self):
        source=inspect.getsource(parent.run)
        for bad in ('',source+source,source.replace(c.BEFORE,c.AFTER,1)):
            with self.assertRaises(ValueError):c.patched_function(bad)


if __name__=='__main__':unittest.main()
