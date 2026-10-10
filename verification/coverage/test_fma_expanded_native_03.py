"""On-disk generation, complete source entry and real Python checker regressions."""
from pathlib import Path
import tempfile
import unittest

import fma_expanded_native_03 as native
import fma_expanded_session_mock_03 as mock


class DiskEntryTests(unittest.TestCase):
    def test_sealed02_actual_source_failure(self):
        result = mock.reproduce_02()
        self.assertIn('invalid command name', result)
        self.assertIn('MOCK_STATE 0 {} {} INFO_SCRIPT {}', result)

    def test_actual_generated_selection_complete_entry_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            native.write_selection(out)
            self.assertEqual((out / 'selection.tcl').read_bytes(), native.selection_text().encode('ascii'))
            evidence = mock.qualify_disk_entry(out / 'selection.tcl')
        self.assertTrue(evidence['all_configuration_and_tool_bindings_reachable'])
        self.assertEqual([s['stage'] for s in evidence['stages']], list(native.frozen.STAGES))
        self.assertTrue(all(s['all_nontarget_objects'] == 2832 for s in evidence['stages']))
        self.assertFalse(evidence['native_qualification'])

    def test_json_selection_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'selection.tcl'
            native.life.save(p, native.selection_text())
            with self.assertRaises(ValueError):
                mock.qualify_disk_entry(p)

    def test_scope_union_and_original_selection_unchanged(self):
        old = (native.prior.OLD / 'selection.tcl').read_text().splitlines()
        new = native.selection_text().splitlines()
        self.assertEqual(old[:-1], new[:-1])
        c = native.life.read_bound(native.OLD / 'config.json', native.OLD_SEAL)
        native.life.check(c['pins'])
        self.assertEqual(c['objects'], 612)
        self.assertEqual(c['logical_bits'], 26064)


if __name__ == '__main__':
    unittest.main()
