import tempfile
from pathlib import Path
import tkinter
import unittest
import run_half_fma_finite as r


class FocusedRunner(unittest.TestCase):
    def test_exact_scopes_budget_and_command(self):
        self.assertEqual(len(set(r.scopes())),16)
        command=r.command(r.OUT)
        self.assertEqual(command[0],str(r.life.IMAGE))
        self.assertIn('+NO_FSDB',command);self.assertIn('-ucli',command)
        self.assertFalse(any('RESET_ON_AXI' in x for x in command))
        self.assertIn('gen_parallel_slices[2]',r.scopes()[0])

    def test_actual_tcl_body_no_forcing(self):
        text=(r.HERE/'capture_half_fma_finite.tcl').read_text()
        self.assertNotIn('force ',text);self.assertNotIn('info script',text)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'selection.tcl';p.write_text('set hfm_scopes {'+' '.join(r.scopes())+'}\n')
            t=tkinter.Tcl()
            t.eval('rename source real_source')
            t.setvar('config',str(p))
            t.eval('proc source {ignored} {uplevel 1 [list real_source $::config]}')
            t.eval('set adds 0; set runs 0; proc dump {args} {if {[lindex $args 0] eq "-add"} {incr ::adds}; return 1}; proc show {args} {}; proc run {} {incr ::runs}; proc exit {args} {error "unexpected exit"}')
            t.eval(text)
            self.assertEqual(t.eval('set adds'),'178')
            self.assertEqual(t.eval('set runs'),'1')


if __name__=='__main__':unittest.main()
