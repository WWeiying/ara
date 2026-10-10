"""Real scalar158 source fixture, exact EL and full typed complement boundaries."""
import tempfile
from pathlib import Path
import unittest
import capture_scalar_radix158 as m


class ScalarRadix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r=m.life.read_bound(m.SOURCE_REVIEW,m.REVIEW_SHA)
        signals=m.source_signals(r)
        protected=[n['name']+('[%s:%s]'%(n['left'],n['right']) if n['kind']=='vectornode' else '') for n in r['protected']]
        cls.c=dict(instance=dict(scope=r['scope'],design_module_checksum=r['design_module_checksum'],
            toggle_checksum=r['toggle_checksum'],signals=signals,protected=protected))
        cls.text=m.candidate(cls.c)

    def test_actual_independent_scalar158(self):
        self.assertEqual(len(m.records(self.text,self.c)),158)
        self.assertEqual(sum(s['width'] for s in self.c['instance']['signals']),9684)
        self.assertEqual(len(self.c['instance']['protected']),52)

    def test_checksum(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('3969040510','3969040511'),self.c)

    def test_vector_scope_rejected(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('.i_ariane.','.i_ara.gen_lanes[0].'),self.c)

    def test_partial_bounds(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('cur_rem[60:0]','cur_rem[59:0]'),self.c)

    def test_wrong_source_type(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('reg cur_rem[','net cur_rem['),self.c)

    def test_only_exact_net_spelling(self):
        text=self.text.replace('net cur_rem_1[','wire cur_rem_1[')
        self.assertEqual(m.records(text,self.c),m.records(self.text,self.c))
        with self.assertRaises(ValueError):m.records(self.text.replace('net cur_rem_1[','reg cur_rem_1['),self.c)

    def test_duplicate_missing_extra_control(self):
        for text in (self.text+self.text,'\n'.join(self.text.splitlines()[:-1]),
                     self.text+'Toggle bound_sel "net bound_sel[6:0]"\n'):
            with self.assertRaises(ValueError):m.records(text,self.c)

    def test_no_slice_direction(self):
        with self.assertRaises(ValueError):m.records(self.text.replace('Toggle cur_rem ','Toggle 0to1 cur_rem '),self.c)

    def test_semantic_order(self):
        rows=self.text.splitlines()
        self.assertEqual(m.records('\n'.join(rows[:2]+list(reversed(rows[2:]))),self.c),m.records(self.text,self.c))

    def test_full_inventory_and_missing_protection(self):
        names=[s['native_name'] for s in self.c['instance']['signals']]+self.c['instance']['protected']
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);path=out/'native_before_0.tsv'
            def write(values):
                path.write_text('handle\tpath\tmeta\tname\n'+''.join('%d\t%s\t%s\t%s\n'%(i,n,n,n) for i,n in enumerate(values)))
            write(names);self.assertEqual(len(m.inventory(out,self.c,'before')),210)
            write(names[:-1])
            with self.assertRaises(ValueError):m.inventory(out,self.c,'before')
            write(names[:-1]+[names[0]])
            with self.assertRaises(ValueError):m.inventory(out,self.c,'before')

    def test_exact_tcl_import_lifecycle_no_scope_exclusion(self):
        text=m.TCL.read_text()
        self.assertEqual(text.count('c910_load '),2)
        for stage in ('before','selected','reset','reloaded','final'):
            self.assertIn('c910_bind '+stage+' $instance',text)
        self.assertNotIn('gui_exclude_items',text)
        self.assertNotIn('gui_exclude_scope',text)
        self.assertIn('c910_failure $message $::errorInfo',text)


if __name__=='__main__':unittest.main()
