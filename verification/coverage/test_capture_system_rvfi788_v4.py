from types import FunctionType
import tempfile
import unittest
from unittest.mock import patch

import capture_system_rvfi788_v4 as m
import test_capture_system_rvfi788_v3 as prior_tests


class Native04(prior_tests.Exact03Entry):
    def execute(self, tmp, mutation='', native_mutation=''):
        worker = FunctionType(prior_tests.Exact03Entry.execute.__code__,
                              dict(prior_tests.Exact03Entry.execute.__globals__, m=m))
        return worker(self, tmp, mutation, native_mutation)

    def test_frozen_actual03_preflight(self):
        self.assertEqual(len(m.predecessor()['targets']), 788)

    def test_preserved_export_hash_drift_rejected(self):
        digest = m.life.digest
        with patch.object(m.life, 'digest', side_effect=lambda p: '0'*64 if p == m.ORIGIN/'first.el' else digest(p)):
            with self.assertRaises(ValueError):
                m.predecessor()

    def test_actual_directional_export_full_entry(self):
        real = (m.ORIGIN/'first.el').read_text()
        mutation = '''rename gui_exclusion_file original_save
proc gui_exclusion_file {args} {
    if {[lsearch $args -save]>=0 && [llength $::mock_active]==788} {
        set f [open [lindex [lindex $args end] 0] w]
        puts -nonewline $f $::actual_native
        close $f;return
    }
    return [eval original_save $args]
}
'''
        mutation = 'set actual_native {'+real+'}\n'+mutation
        with tempfile.TemporaryDirectory() as tmp:
            p, out = self.execute(tmp, mutation)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertIn('SYSTEM_RVFI788_NATIVE_DONE', p.stdout)
            self.assertNotIn('SYSTEM_RVFI788_FAILED', p.stdout)
            self.assertEqual(m.records((out/'first.el').read_text(), self.c),
                             m.records((out/'second.el').read_text(), self.c))
            for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
                self.assertEqual(len(m.inventory(out, self.c, stage)), 1206)


if __name__ == '__main__':
    unittest.main()
