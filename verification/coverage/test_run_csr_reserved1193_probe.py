from pathlib import Path
import subprocess
import tempfile
import unittest

import run_csr_reserved1193_probe as m


class ProbeContract(unittest.TestCase):
    def test_reviewed_source_and_installed_uncompress(self):
        self.assertEqual(m.life.digest(m.PROBE),m.PROBE_SHA)
        self.assertIn('gui_cov_tgl_expand "uncompress"',m.MENU.read_text())

    def test_generated_hook_only_dump_boundary_changes(self):
        text=m.PROBE.read_text();new=m.diagnostic_hook(text)
        self.assertIn('gui_cov_tgl_compress -id CovDetail.1 -opt uncompress',new)
        self.assertNotIn('gui_exclusion_file',new)
        self.assertNotIn('gui_exclude_items',new)
        self.assertEqual(new.count('CSR1193_DUMP_BEGIN'),1)

    def test_unknown_transformation_rejected(self):
        with self.assertRaises(ValueError):m.diagnostic_hook('gui_dump_common_list wrong\n')

    def test_unsupported_dump_records_error_not_aborts_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            script='set ::csr_probe_test_only 1\n'+m.diagnostic_hook(m.PROBE.read_text())
            script+='\nset ::env(DVE_COVERAGE_OUTPUT) {'+tmp+'}\n'
            script+='''
proc gui_list_get {args} {return 0}
proc gui_dump_common_list {args} {error "CovDetail unsupported"}
csr_probe_rows test
puts ROWS_SURVIVED
'''
            result=subprocess.run(['tclsh'],input='if {[catch {\n'+script+'\n} msg]} {puts stderr $msg;exit 1}\n',
                                  text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('CSR1193_DUMP_UNSUPPORTED test CovDetail unsupported',result.stdout)
            self.assertEqual((Path(tmp)/'expanded-test.tsv').read_text(),'path\tmeta\tname\n')


if __name__=='__main__':unittest.main()
