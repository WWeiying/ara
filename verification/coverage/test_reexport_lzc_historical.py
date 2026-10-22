"""No EDA: verify second-pass ordering without changing the frozen hook."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import reexport_lzc_historical as r
from capture_lzc_batch import tcl_word


@unittest.skipUnless(shutil.which("tclsh"),"tclsh required")
class ExportTests(unittest.TestCase):
    def test_firstpass_idle_expand_recalculate_idle_secondpass(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = Path(tmp)/"frozen.tcl"
            hook.write_text('proc lzc_formal_summary {id name} {global calls; lappend calls $name}\n')
            text = 'set env(LZC_FROZEN_HOOK) %s\nsource %s\n'%(tcl_word(hook),tcl_word(r.HOOK))
            text += '''
set calls {}
proc update {args} {global calls; lappend calls $args}
proc gui_list_expand {args} {global calls; lappend calls expand}
proc gui_exclusion {args} {global calls; lappend calls recalculate}
lzc_formal_summary CoverageTable.1 summary_waived.csv.partial
if {$calls ne {summary_waived_firstpass.csv.partial idletasks expand recalculate idletasks summary_waived.csv.partial}} {puts stderr $calls; exit 1}
'''
            result = subprocess.run(["tclsh"],input=text,text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_failure_not_suppressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            hook = Path(tmp)/"frozen.tcl"
            hook.write_text('proc lzc_formal_summary {id name} {}\n')
            text = 'set env(LZC_FROZEN_HOOK) %s\nsource %s\n'%(tcl_word(hook),tcl_word(r.HOOK))
            text += '''
proc update {args} {error "failed refresh"}
if {![catch {lzc_formal_summary CoverageTable.1 summary.csv.partial} msg] || $msg ne "failed refresh"} {exit 1}
'''
            result = subprocess.run(["tclsh"],input=text,text=True,capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == "__main__":unittest.main()
