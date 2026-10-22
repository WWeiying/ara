from pathlib import Path
import subprocess
import unittest


class NativeInventoryTests(unittest.TestCase):
    def test_complete_visible_inventory_and_reject_hidden_or_missing(self):
        helper = Path(__file__).with_name('lzc_selector_native_capture_v3.tcl')
        library = helper.read_text().split('\nset failed [catch {lsn_session}', 1)[0]
        script = library + r'''
rename lsn_audit_observed_rows original_audit
proc lsn_audit_observed_rows {stage target} {puts AUDITED}
set lsn_scope lzc_selector_native_mock.dut
set lsn_rows {{cond 1 0 {left | right}} {cond 1 1 {left | right}} {cond 3 0 {select ? a : b}} {cond 3 1 {select ? a : b}}}
set names {{{left | right}} {{select ? a : b}}}
proc gui_list_action {args} {}
proc gui_list_get_selected {args} {global names; return $names}
lsn_audit before -1
set names {{{left | right}}}
if {![catch {lsn_audit missing -1}]} {error "missing native expression accepted"}
set names {{{left | right}} {{select ? a : b}} {{select == 1}}}
if {![catch {lsn_audit extra -1}]} {error "unbound expression accepted"}
puts HOST_VISIBLE_INVENTORY_PASS
'''
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertEqual(result.stdout.count('AUDITED'), 1)
        self.assertIn('HOST_VISIBLE_INVENTORY_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
