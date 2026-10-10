import copy
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
import queue_fp_temporaries_native_alias as q
from test_queue_fp_temporaries_native import fixture_text


class ActualSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c,cls.rows = q.fixture()
        with (q.ORIGIN/'native_before_0.tsv').open(newline='') as f:
            cls.raw = list(csv.reader(f,delimiter='\t'))

    def test_actual68_unique_bijection_and_all_targets(self):
        self.assertEqual(len(self.rows),68)
        q.contract(self.c)
        self.assertEqual(sum(len(i['protected']) for i in self.c['instances']),752)
        self.assertEqual(sum(len(i['targets']) for i in self.c['instances']),336)
        self.assertFalse(any('queue_alu_' in i['scope'] for i in self.c['instances']))

    def test_compiled_aliases_roundtrip_identity(self):
        i = self.c['instances'][0]
        for binding in i['protection_bindings']:
            n = binding['compiled']; name = binding['native_name']
            self.assertEqual(q.protection(n),name)
            self.assertEqual(sum(r[2] == name for r in self.rows),1)
            if n['name'] in q.SCALARS:
                self.assertEqual((n['kind'],n['left'],n['right']),('vectornode','0','0'))
                self.assertEqual(name,n['name'])
        self.assertEqual(len(i['protection_bindings']),47)

    def test_union_all_dimensions_no_dropping(self):
        actual = {n['name']:q.protection(n) for n in self.c['instances'][0]['protected_compiled'] if n['kind'] == 'arrays'}
        self.assertEqual(actual,{'ntr.w8':'ntr.w8[7:0][7:0]','ntr.w16':'ntr.w16[3:0][15:0]',
                                'ntr.w32':'ntr.w32[1:0][31:0]','ntr.w64':'ntr.w64[0][63:0]'})
        for n in self.c['instances'][0]['protected_compiled']:
            if n['kind'] != 'arrays': continue
            dims = q.UNIONS[n['name']]
            bad = dict(n,packedrange=' '.join(map(str,[dims[0]+1]+dims[1:])))
            self.assertNotEqual(list(map(int,bad['packedrange'].split())),dims)
            with self.assertRaises(ValueError): q.protection(bad)

    def test_no_generic_single_bit_alias(self):
        n = next(n for n in self.c['instances'][0]['protected_compiled'] if n['name'] in q.SCALARS)
        for bad in (dict(n,left='1'),dict(n,right='1'),dict(n,kind='node')):
            with self.assertRaises(ValueError): q.protection(bad)
        self.assertEqual(q.protection(dict(n,name='unknown_control')),'unknown_control[0:0]')

    def inventory_mutation(self,rows):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with (out/'native_before_0.tsv').open('w',newline='') as f:
                csv.writer(f,delimiter='\t',lineterminator='\n').writerows(rows)
            with self.assertRaises(ValueError): q.inventory(out,self.c,'before',0)

    def test_every_protected_object_missing_rejected(self):
        protected = set(self.c['instances'][0]['protected'])
        for index,row in enumerate(self.raw[1:],1):
            if row[3] in protected:
                self.inventory_mutation(self.raw[:index]+self.raw[index+1:])

    def test_extra_scalar_vector_collision_rejected(self):
        for name in q.SCALARS:
            row = next(r for r in self.raw[1:] if r[3] == name)
            self.inventory_mutation(self.raw+[row])
            bad = [copy.copy(r) for r in self.raw]
            for r in bad[1:]:
                if r[3] == name: r[1:] = [name+'[0:0]']*3
            self.inventory_mutation(bad)

    def test_path_meta_name_and_handle_drift(self):
        for column in (0,1,2,3):
            bad = [copy.copy(r) for r in self.raw]
            bad[1][column] = bad[2][column]
            self.inventory_mutation(bad)
        bad = [copy.copy(r) for r in self.raw]; bad[1][2] = 'logic '+bad[1][2]
        self.inventory_mutation(bad)

    def test_protected_mapping_config_drift(self):
        c = copy.deepcopy(self.c); c['instances'][0]['protected'].pop()
        with self.assertRaises(ValueError): q.contract(c)
        c = copy.deepcopy(self.c); c['instances'][0]['protected_compiled'][0]['portnode'] = '0'
        with self.assertRaises(ValueError): q.contract(c)

    def test_actual_bare_meta_never_used_as_typed_EL(self):
        text = fixture_text(self.c)
        self.assertEqual(len(q.old.parse_el(text,self.c)),336)
        for bad in (text.replace('"logic fp8[0].e','"fp8[0].e',1),
                    text.replace('"logic fp8[0].e','"wire fp8[0].e',1),
                    text.replace('fp8[0].e[4:0]','fp8[0].e[3:0]',1)):
            with self.assertRaises(ValueError): q.old.parse_el(bad,self.c)
        self.assertEqual(q.old.parse_el(text,self.c),q.old.parse_el(fixture_text(self.c,directions=True),self.c))

    def test_protected_fields_and_union_never_excluded(self):
        text = fixture_text(self.c)
        for extra in ('Toggle operand_ready_i "logic operand_ready_i"',
                      'Toggle ntr.w8 "logic ntr.w8[7:0][7:0]"',
                      'Toggle 0to1 fp8[0].s "logic fp8[0].s"'):
            with self.assertRaises(ValueError): q.old.parse_el(text+extra+'\n',self.c)

    def test_five_stage_actual_schema_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for stage in q.old.STAGES:
                (out/('native_%s_0.tsv' % stage)).write_bytes((q.ORIGIN/'native_before_0.tsv').read_bytes())
                self.assertEqual(q.inventory(out,self.c,stage,0),self.rows)
            (out/'native_final_0.tsv').write_text((out/'native_final_0.tsv').read_text().replace('ntr.w64[0][63:0]','ntr.w64[0][62:0]'))
            with self.assertRaises(ValueError): q.inventory(out,self.c,'final',0)

    def test_actual_before_bind_and_bracket_safe_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); t = tkinter.Tcl(); t.eval('set ::qfp_alias_test_only 1')
            t.eval((q.HERE/'queue_fp_temporaries_native_alias.tcl').read_text())
            body = (q.HERE/'fma_datapath_native.tcl').read_text()
            t.eval(body.split('if {[catch {fma_session} message]} ',1)[0])
            t.setvar('env(DVE_COVERAGE_OUTPUT)',str(out)); t.setvar('fma_python','model'); t.setvar('fma_helper','model')
            rows = self.raw[1:]; handles = {r[0]:n for n,r in enumerate(rows)}
            state = dict(selected='',bad_readback=False)
            def get(*args):
                if '-firstChild' in args: return rows[0][0] if len(args) == 3 else ''
                index = handles[args[-1]]; row = rows[index]
                if '-nextSibling' in args: return rows[index+1][0] if index+1 < len(rows) else ''
                if '-path' in args: return row[1]
                if '-meta' in args: return row[2]
                if '-text' in args: return row[3]
                raise AssertionError(args)
            def selected(*args):
                if '-count' in args: return str(int(bool(state['selected'])))
                return 'WRONG' if state['bad_readback'] else state['selected']
            def select(*args):
                state['selected'] = '' if '-unselect' in args else t.splitlist(args[-1])[0]
                return ''
            def worker(*args): return str(len(q.inventory(out,self.c,args[-3],int(args[-1]))))
            t.createcommand('gui_list_get',get); t.createcommand('gui_list_get_selected',selected)
            t.createcommand('gui_list_select',select); t.createcommand('exec',worker)
            t.eval('proc gui_list_action {args} {}; proc gui_covdetail_query {args} {return Toggle}; proc gui_list_expand {args} {}; proc gui_process_events {args} {}')
            i = self.c['instances'][0]
            instance = t.call('list',i['scope'],tuple(x['native_name'] for x in i['targets']),tuple(i['protected']),0)
            target_rows = t.call('qfp_bind','before',instance)
            self.assertEqual(len(target_rows),21)
            for row in target_rows:
                t.call('qfp_select',row)
                self.assertEqual(state['selected'],row[0])
            state['bad_readback'] = True
            with self.assertRaises(tkinter.TclError): t.call('qfp_select',target_rows[0])


if __name__ == '__main__': unittest.main()
