import tkinter
import unittest
from pathlib import Path


class DveEntry(unittest.TestCase):
    def test_real_eval_context_has_no_script_path(self):
        t=tkinter.Tcl();self.assertEqual(t.eval('info script'),'')
        t.eval('set ::cast_v2_test_only 1')
        entry=Path(__file__).with_name('capture_cast168_native_entry.tcl')
        t.eval(entry.read_text())
        self.assertEqual(t.eval('info args cast_session'),'')
        self.assertEqual(t.eval('info args cast_bind'),'stage instance')
        self.assertNotIn('info script', '\n'.join(entry.read_text().splitlines()[1:]))

    def test_original_relative_entry_fails_in_actual_eval_context(self):
        t=tkinter.Tcl();t.eval('set ::cast_v2_test_only 1')
        old=Path(__file__).with_name('capture_cast168_native_v2.tcl')
        with self.assertRaises(tkinter.TclError):t.eval(old.read_text())


if __name__=='__main__':unittest.main()
