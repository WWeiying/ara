"""Regression for original generated Tcl multiline list failure."""
import subprocess
import unittest

from lzc_selector_native_product_discover_v2 import selection_successor


class SelectionSuccessorTests(unittest.TestCase):
    def test_actual_tcl_interpretation_preserves_all_child_values(self):
        original = ('set untouched {same}\nset lpd_children [list\n'
                    '  [list {child[0].lzc} {3250293308} {WIDTH=10} [list {(a | b)} {((s == 1) ? l : r)}]]\n'
                    '  [list {child[1].lzc} {3250293308} {WIDTH=23} [list {(c | d)}]]\n]\n')
        script = selection_successor(original) + '''
if {[llength $lpd_children] != 2 || $untouched ne "same"} {error "Population changed"}
if {[lindex $lpd_children 0 0] ne "child\[0\].lzc"} {error "Instance changed"}
if {[lindex $lpd_children 0 3 1] ne "((s == 1) ? l : r)"} {error "Expression changed"}
puts PASS
'''
        result = subprocess.run(['tclsh'], input=script, text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), 'PASS')
        self.assertEqual(result.stderr, '')
        self.assertEqual(selection_successor(original).replace(' \\\n', '\n'), original)

    def test_unrecognized_selection_rejected(self):
        with self.assertRaises(ValueError):
            selection_successor('set different [list]\n')


if __name__ == '__main__':
    unittest.main()
