import subprocess
import unittest
from pathlib import Path
import run_cva6_mda_readonly767 as r


class ProbeTests(unittest.TestCase):
    def test_actual_tcl_procedures_have_no_session(self):
        path = r.HERE / 'probe_cva6_mda_readonly.tcl'
        result = subprocess.run(['tclsh'], input='source {' + str(path) + '}\nputs [info procs mda_read_scope]\n',
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), 'mda_read_scope')
        text = path.read_text()
        self.assertNotIn('gui_open_cov', text)
        self.assertNotIn('gui_exclusion', text)

    def test_unknown_scope_rejected_before_gui(self):
        path = r.HERE / 'probe_cva6_mda_readonly.tcl'
        result = subprocess.run(['tclsh'], input='source {' + str(path) + '}\nputs [catch {mda_read_scope injected /tmp/never-write-mda} message]\nputs $message\n',
                                text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.splitlines(), ['1', 'Unreviewed MDA scope'])

    def test_exact_three_scopes(self):
        self.assertEqual(len(set(r.source.SCOPES)), 3)
        self.assertTrue(r.source.SCOPES[-1].endswith('gen_asic_regfile.i_ariane_regfile'))


if __name__ == '__main__': unittest.main()
