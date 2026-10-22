from pathlib import Path
import subprocess
import tempfile
import unittest

import c910_srt_datapath_native_v2 as v2


class NamespaceTests(unittest.TestCase):
    def test_source_change_is_only_global_binding(self):
        old = (v2.HERE / 'c910_srt_datapath_native.tcl').read_text()
        fixed = v2.base.TCL.read_text()
        self.assertEqual(fixed, old.replace(
            'global env fma_instances fma_design fma_vdb fma_test',
            'global env fma_instances fma_design fma_vdb fma_test fma_python fma_helper c910_fma_tcl'))

    def test_private_dependency_pin_union(self):
        pins = v2.merge_pins({'/a': '1' * 64}, {'/b': '2' * 64})
        self.assertEqual(pins, {'/a': '1' * 64, '/b': '2' * 64, **v2.dependencies})
        self.assertIsNot(v2.base.life, v2.original_life)
        self.assertIsNot(v2.base.life.merge_pins, v2.original_life.merge_pins)
        with self.assertRaises(ValueError):
            v2.merge_pins({str(v2.ORIGINAL): 'bad'}, {})

    def initialize(self, tcl):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / 'selection.tcl').write_text('\n'.join([
                'set c910_fma_tcl {%s}' % (v2.HERE / 'fma_datapath_native.tcl'),
                'set fma_design design', 'set fma_vdb vdb', 'set fma_test test',
                'set fma_python python', 'set fma_helper helper', 'set fma_instances {}']))
            script = '\n'.join(['set ::c910_test_only 1', 'source {%s}' % tcl,
                'set ::env(DVE_COVERAGE_OUTPUT) {%s}' % out,
                'proc gui_open_cov {args} {',
                ' if {$::fma_python ne "python" || $::fma_helper ne "helper"} {error bad_globals}',
                ' error MOCK_OPEN_REACHED', '}',
                'catch {c910_session} failure', 'puts $failure'])
            result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, '')
            return result.stdout.strip()

    def test_real_failed_session_reproduced(self):
        self.assertIn('c910_fma_tcl', self.initialize(v2.HERE / 'c910_srt_datapath_native.tcl'))

    def test_real_fixed_session_globals(self):
        self.assertEqual(self.initialize(v2.base.TCL), 'MOCK_OPEN_REACHED')


if __name__ == '__main__':
    unittest.main()
