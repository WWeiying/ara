"""Offline mock of documented summary-root/ratio API sequence."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import inspect_lzc_summary as s


@unittest.skipUnless(shutil.which("tclsh"),"tclsh required")
class SummaryTests(unittest.TestCase):
    def test_reselect_rebuild_cumulative_and_official_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"frozen.tcl"
            p.write_text('proc lzc_formal_summary {id name} {global calls; lappend calls $name}\nproc apply_reviewed_waivers {id} {}\n')
            script = 'set env(LZC_FROZEN_HOOK) {%s}\nsource {%s}\n'%(p,s.HOOK)
            script += '''
set calls {}
proc gui_list_action {args} {global calls; lappend calls metric}
proc gui_covdetail_query {args} {return Condition}
proc gui_covtable_setroot {args} {global calls; lappend calls [lindex $args end]}
proc gui_covtable_show {args} {global calls; lappend calls cumulative}
proc gui_exclusion {args} {global calls; lappend calls refresh}
proc gui_cov_show_value {args} {global calls; lappend calls [lindex $args end]}
lzc_formal_summary CoverageTable.1 summary_waived.csv.partial
if {$calls ne {summary_waived_cached.csv.partial metric ara_tb.dut.i_ara_soc.i_system cumulative refresh summary_waived_system_percent.csv.partial true summary_waived_system_ratio.csv.partial false ara_tb summary_waived.csv.partial}} {puts stderr $calls; exit 1}
'''
            result = subprocess.run(["tclsh"],input=script,text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == "__main__":unittest.main()
