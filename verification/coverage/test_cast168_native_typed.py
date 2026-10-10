import copy
from pathlib import Path
import tempfile
import tkinter
import unittest
import capture_cast168_native_typed as m


class TypedFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.meta, cls.records = m.fixture()
        cls.text = (m.ORIGIN/'first.el').read_text()

    def test_full_actual168_and_all_complements(self):
        self.assertEqual(len(self.records), 168)
        self.assertEqual(sum(len(i['protected']) for i in self.c['instances']), 2064)
        self.assertEqual(sum(len(i['protected_compiled']) for i in self.c['instances']), 2064)
        self.assertEqual(self.records, m.parse_el(m.normalize(self.text), self.c, self.meta))

    def test_every_saved_array_form_reload_order_and_clear(self):
        normalized = m.normalize(self.text)
        lines = normalized.splitlines()
        self.assertEqual(sum('"logic [' in line for line in self.text.splitlines()), 56)
        # Every record is re-emitted in the other legal spelling, not only the
        # first failed array. Annotation/order has no identity significance.
        alternate = []
        import re
        for line in lines:
            match = re.fullmatch(r'Toggle (\w+) "logic (\w+)(.+)"', line)
            if match:
                name, declared, dims = match.groups()
                line = 'Toggle %s "logic %s%s"' % (name, dims, declared)
            alternate.append(line)
        self.assertEqual(self.records, m.parse_el('\n'.join(alternate), self.c, self.meta))
        for name in ('initial-empty.el', 'cleanup-empty.el'):
            self.assertEqual((m.ORIGIN/name).read_bytes(), b'')
        with self.assertRaises(ValueError):
            m.parse_el('', self.c, self.meta)

    def reject(self, old, new):
        self.assertIn(old, self.text)
        mutated = self.text.replace(old, new, 1)
        self.assertNotEqual(mutated, self.text)
        with self.assertRaises(ValueError):
            m.parse_el(mutated, copy.deepcopy(self.c), self.meta)

    def test_type_and_signed_rejected(self):
        for typ in ('integer', 'wire', 'reg', 'logic signed'):
            self.reject('"logic [0:1][63:0]', '"'+typ+' [0:1][63:0]')

    def test_each_dimension_bound_order_and_element_rejected(self):
        for dims in ('[0:0][63:0]', '[0:1][62:0]', '[1:0][63:0]',
                     '[63:0][0:1]', '[0:1]', '[0:1][63:0][0:0]', '[0][63:0]'):
            self.reject('[0:1][63:0]mid_pipe_input_mant_q', dims+'mid_pipe_input_mant_q')

    def test_every_record_every_dimension_bound_rejected(self):
        import re
        count = 0
        for line in self.text.splitlines():
            if not line.startswith('Toggle '):
                continue
            for dim in re.finditer(r'\[(-?\d+):(-?\d+)\]', line):
                bad = line[:dim.start()]+('[%d:%s]' % (int(dim[1])+1, dim[2]))+line[dim.end():]
                with self.assertRaises(ValueError):
                    m.parse_el(self.text.replace(line, bad, 1), self.c, self.meta)
                count += 1
        self.assertEqual(count, 224)

    def test_direction_partial_and_other_metric_rejected(self):
        for prefix in ('Toggle 0to1', 'Toggle 1to0', 'Line', 'Condition'):
            self.reject('Toggle mid_pipe_input_mant_q', prefix+' mid_pipe_input_mant_q')

    def test_names_scope_checksum_and_protected_extra_rejected(self):
        self.reject('[0:1][63:0]mid_pipe_input_mant_q', '[0:1][63:0]operands_q')
        self.reject('1144939760 400336858', '1144939760 400336859')
        self.reject(self.c['instances'][0]['scope'], self.c['instances'][0]['scope']+'.child')
        with self.assertRaises(ValueError):
            m.parse_el(self.text+'Toggle out_pipe_ready "logic out_pipe_ready[0:0]"\n', self.c)

    def test_missing_duplicate_and_native_meta_rejected(self):
        line = next(x for x in self.text.splitlines() if x.startswith('Toggle '))
        for text in (self.text.replace(line+'\n', '', 1), self.text+'\n'+line):
            with self.assertRaises(ValueError):
                m.parse_el(text, self.c, self.meta)
        meta = dict(self.meta); meta[next(iter(meta))] = 'wrong'
        with self.assertRaises(ValueError):
            m.parse_el(self.text, self.c, meta)

    def test_actual_entry_and_whole_session_host_roundtrip(self):
        # Execute the complete frozen session body with a host GUI model.
        # Actual identities/typed EL are supplied by03, not invented GUI IDs.
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out/'selection.tcl').write_bytes((m.ORIGIN/'selection.tcl').read_bytes())
            t = tkinter.Tcl()
            t.eval('set ::cast_v2_test_only 1')
            t.eval((m.HERE/'capture_cast168_native_entry.tcl').read_text())
            t.setvar('env(DVE_COVERAGE_OUTPUT)', str(out))
            def check(name):
                self.assertEqual(m.parse_el((out/name).read_text(), self.c, self.meta), self.records)
                return '168'
            def save(name):
                (out/name).write_text(self.text if int(t.getvar('::excluded')) else '')
                return ''
            t.createcommand('host_check', check); t.createcommand('host_save', save)
            t.eval('''
set excluded 0; set stages {}; set selections 0
proc gui_open_cov {args} {}
proc gui_list_expand {args} {}
proc gui_exclusion {args} {}
proc gui_cov_excl_review {args} {return 1}
proc gui_exclude_items {args} {incr ::excluded}
proc cast_reset {} {set ::excluded 0}
proc cast_load {} {host_check first.el; set ::excluded 168}
proc cast_select {row} {incr ::selections}
proc cast_bind {stage instance} {
    lappend ::stages $stage
    return [lindex $instance 1]
}
rename uplevel original_uplevel
proc uplevel {args} {
    original_uplevel #0 [lindex $args end]
    proc fma_save {name} {host_save $name}
    proc fma_check {name} {host_check $name}
}
cast_session
''')
            self.assertEqual(t.eval('set selections'), '168')
            self.assertEqual(t.eval('set excluded'), '0')
            for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
                self.assertIn(stage, t.eval('set stages').split())
            for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
                self.assertEqual((out/name).read_bytes(), b'')
            self.assertEqual((out/'first.el').read_bytes(), (out/'second.el').read_bytes())


if __name__ == '__main__':
    unittest.main()
