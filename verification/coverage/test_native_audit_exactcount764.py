"""Actual Tcl source/eval equivalence; no DVE, no product mutation."""
import pathlib
import subprocess
import unittest

HERE = pathlib.Path(__file__).resolve().parent
LIBRARY = HERE / 'native_audit_exactcount764.tcl'


class ExactCount(unittest.TestCase):
    def evaluate(self, body):
        script = 'source {%s}\n%s\n' % (LIBRARY, body)
        result = subprocess.run(['tclsh'], input=script, text=True,
                                capture_output=True, check=True)
        self.assertEqual(result.stderr, '')
        self.assertIn('PASS', result.stdout)

    def test_actual_source_special_names(self):
        self.evaluate('''
set names [list {lane[0].q[3]} {a b} {brace{literal}} {semi;literal} {$literal}]
native764_exact_names $names $names
puts PASS
''')

    def test_missing_and_duplicate_reject(self):
        self.evaluate('''
foreach seen [list [list unrelated] [list target target]] {
    if {![catch {native764_exact_names $seen [list target]}]} {error accepted}
}
puts PASS
''')

    def test_empty_and_non_target_duplicates(self):
        self.evaluate('''
native764_exact_names {} {}
native764_exact_names [list target other other] [list target]
puts PASS
''')

    def test_exhaustive_old_predicate_equivalence(self):
        self.evaluate('''
proc original {seen wanted} {
    foreach name $wanted {
        set count 0
        foreach observed $seen {if {$observed eq $name} {incr count}}
        if {$count != 1} {error reject}
    }
}
set values [list a b {lane[0]}]
set sequences [list {}]
set frontier [list {}]
for {set depth 0} {$depth < 5} {incr depth} {
    set next {}
    foreach prefix $frontier {
        foreach value $values {lappend next [concat $prefix [list $value]]}
    }
    set sequences [concat $sequences $next]
    set frontier $next
}
foreach seen $sequences {
    foreach wanted [list {} {a} {b} {{lane[0]}} {a b} {a a} {absent}] {
        set before [catch {original $seen $wanted}]
        set after [catch {native764_exact_names $seen $wanted}]
        if {$before != $after} {error "Predicate changed: $seen / $wanted"}
    }
}
puts PASS
''')

    def test_five_stages_no_cached_state(self):
        self.evaluate('''
foreach stage {raw applied reset reloaded final} {
    native764_exact_names [list target protected] [list target]
    if {![catch {native764_exact_names [list protected] [list target]}]} {
        error "Stale stage counts: $stage"
    }
}
puts PASS
''')

    def test_no_gui_or_new_tcl_syntax(self):
        text = LIBRARY.read_text()
        self.assertNotIn('gui_', text)
        self.assertNotIn('{*}', text)
        self.assertNotIn('dict ', text)
        self.assertNotIn('rename ', text)


if __name__ == '__main__':
    unittest.main()
