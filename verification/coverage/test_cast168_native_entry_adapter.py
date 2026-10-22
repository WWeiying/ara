import importlib.util
from pathlib import Path
import tkinter
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cast_entry_test', HERE/'capture_cast168_native_entry.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class EntryAdapter(unittest.TestCase):
    def test_routes_and_gates(self):
        self.assertEqual(tool.base.HERE/'capture_cast168_native.tcl', HERE/'capture_cast168_native_entry.tcl')
        self.assertEqual(tool.base.__file__, str(HERE/'capture_cast168_native_entry.py'))
        self.assertIs(tool.base.inventory, tool.v2.inventory)
        self.assertIs(tool.base.parse_el, tool.v2.parse_el)
        self.assertIs(tool.base.contract, tool.v2.contract)

    def test_single_session_and_exit_without_script_context(self):
        t = tkinter.Tcl()
        self.assertEqual(t.eval('info script'), '')
        t.eval('rename source real_source; set calls 0; set exits 0; proc source {p} {real_source $p; proc cast_session {} {incr ::calls}}; proc gui_exit {args} {incr ::exits}')
        t.eval((HERE/'capture_cast168_native_entry.tcl').read_text())
        self.assertEqual(t.eval('set calls'), '1')
        self.assertEqual(t.eval('set exits'), '1')
        for name in ('capture_cast168_native.tcl', 'fma_datapath_native.tcl'):
            self.assertNotIn('[info script]', (HERE/name).read_text())


if __name__ == '__main__':
    unittest.main()
