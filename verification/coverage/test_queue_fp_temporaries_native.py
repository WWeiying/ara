import copy
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch
import queue_fp_temporaries_native as q


def fixture_text(c, directions=False, prefix=False):
    lines = []
    for i in c['instances']:
        lines += ['CHECKSUM: "%s %s"' % (i['design_module_checksum'],i['toggle_checksum']),
                  'INSTANCE: '+i['scope']]
        for t in i['targets']:
            dims = '[%s:%s]' % (t['left'],t['right']) if t['kind'] == 'vectornode' else ''
            meta = 'logic '+(dims+t['name'] if prefix else t['name']+dims)
            for direction in ('0to1','1to0') if directions else ('',):
                lines.append('Toggle '+(direction+' ' if direction else '')+t['name']+' "'+meta+'"')
    return '\n'.join(lines)+'\n'


class QueueNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = q.life.read_bound(q.REVIEW,q.REVIEW_SHA)
        q.life.check(cls.review['input_pins'])
        cls.c = dict(instances=q.instances(cls.review),population_application=False,timeout_seconds=900)
        cls.text = fixture_text(cls.c)

    def test_exact_source_population(self):
        q.contract(self.c)
        self.assertEqual(len(self.c['instances']),16)
        self.assertEqual(sum(len(i['targets']) for i in self.c['instances']),336)
        self.assertEqual(sum(len(i['protected']) for i in self.c['instances']),688)
        self.assertFalse(any('queue_alu_' in i['scope'] for i in self.c['instances']))

    def test_complete_typed_bracket_fields_both_forms(self):
        records = q.parse_el(self.text,self.c)
        self.assertEqual(len(records),336)
        self.assertEqual(records,q.parse_el(fixture_text(self.c,prefix=True),self.c))
        self.assertEqual(records,q.parse_el(fixture_text(self.c,directions=True),self.c))

    def reject(self,text):
        self.assertNotEqual(text,self.text)
        with self.assertRaises(ValueError): q.parse_el(text,self.c)

    def test_directions_no_partial_duplicate_or_mix(self):
        split = fixture_text(self.c,directions=True)
        line = next(l for l in split.splitlines() if l.startswith('Toggle 1to0'))
        for bad in (split.replace(line+'\n','',1),split+line+'\n',split+self.text.splitlines()[2]+'\n'):
            with self.assertRaises(ValueError): q.parse_el(bad,self.c)

    def test_names_array_indices_and_fields(self):
        for name in ('fp8[4].m','fp8[0].other','fp8[0][0].m','fp8.m'):
            self.reject(self.text.replace('fp8[0].m',name,1))

    def test_every_full_bound(self):
        for i in self.c['instances'][:1]:
            for t in i['targets']:
                if t['kind'] != 'vectornode': continue
                good = '"logic '+q.label(t)+'"'
                bad = '"logic '+t['name']+'[%d:%s]"' % (int(t['left'])+1,t['right'])
                self.reject(self.text.replace(good,bad,1))

    def test_metric_type_qualifier_slice(self):
        for old,new in (('Toggle fp8[0].m','Line fp8[0].m'),('"logic fp8[0].m','"reg fp8[0].m'),
                        ('"logic fp8[0].m','"logic signed fp8[0].m'),
                        ('Toggle fp8[0].m ','Toggle fp8[0].m [0] ')):
            self.reject(self.text.replace(old,new,1))

    def test_scope_checksum_and_held_ALU(self):
        for old,new in (('1532764271','1532764272'),('4023802205','4023802206'),
                        ('i_operand_queue_st_mask_a','i_operand_queue_alu_a')):
            self.reject(self.text.replace(old,new,1))

    def test_extra_protected_duplicate_missing(self):
        line = self.text.splitlines()[2]
        self.reject(self.text.replace(line+'\n','',1))
        self.reject(self.text+line+'\n')
        self.reject(self.text+'Toggle rst_ni "logic rst_ni"\n')

    def test_config_drift(self):
        c = copy.deepcopy(self.c); c['instances'][0]['targets'][0]['left'] = '2'
        with self.assertRaises(ValueError): q.contract(c)

    def test_native_meta_and_empty_guard(self):
        meta = {(i['scope'],t['name']):'logic '+q.label(t) for i in self.c['instances'] for t in i['targets']}
        self.assertEqual(len(q.parse_el(self.text,self.c,meta)),336)
        meta[next(iter(meta))] = 'logic fp8[0].m[2:0]'
        with self.assertRaises(ValueError): q.parse_el(self.text,self.c,meta)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out/'final-empty.el').write_text(self.text)
            with self.assertRaises(ValueError): q.check_file(out,self.c,'final-empty.el')

    def test_five_stage_inventory_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); i = self.c['instances'][0]
            rows = [('h'+str(n),'p.'+t['native_name'],'logic '+q.label(t),t['native_name'])
                    for n,t in enumerate(i['targets'])]
            rows += [('p'+str(n),'p.'+name,'logic '+name,name) for n,name in enumerate(i['protected'])]
            text = 'handle\tpath\tmeta\tname\n'+''.join('\t'.join(r)+'\n' for r in rows)
            for stage in q.STAGES:
                (out/('native_%s_0.tsv' % stage)).write_text(text)
                self.assertEqual(len(q.inventory(out,self.c,stage,0)),64)
            (out/'native_final_0.tsv').write_text(text.replace(rows[-1][3],'MISSING_PROTECTED'))
            with self.assertRaises(ValueError): q.inventory(out,self.c,'final',0)

    def test_full_actual_Tcl_body_host_model(self):
        # Host schema/roundtrip model only, not fabricated native qualification.
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); tcl = tkinter.Tcl(); tcl.eval('set ::qfp_test_only 1')
            tcl.eval((q.HERE/'queue_fp_temporaries_native.tcl').read_text())
            tcl.setvar('env(DVE_COVERAGE_OUTPUT)',str(out))
            lines = ['set %s {%s}\n' % (k,v) for k,v in dict(fma_design='model',fma_vdb='model',
                fma_test='model',fma_python='model',fma_helper='model',
                qfp_primitives=str(q.HERE/'fma_datapath_native.tcl')).items()]
            lines += ['set fma_instances {}\n']
            for index,i in enumerate(self.c['instances']):
                lines.append('lappend fma_instances [list {%s} {%s} {%s} %d]\n' %
                    (i['scope'],' '.join(t['native_name'] for t in i['targets']),' '.join(i['protected']),index))
            (out/'selection.tcl').write_text(''.join(lines))
            model = dict(index=0,selected='',excluded=set(),select_count=0)
            def native_rows():
                i = self.c['instances'][model['index']]
                return [(x['native_name'],'logic '+q.label(x)) for x in i['targets']]+[(n,'logic '+n) for n in i['protected']]
            def action(*args):
                model['index'] = next(n for n,i in enumerate(self.c['instances']) if i['scope'] == args[-1])
                return ''
            def get(*args):
                if '-firstChild' in args:
                    return '' if len(args) > 3 else 'h0'
                n = int(args[-1][1:]); name,meta = native_rows()[n]
                if '-nextSibling' in args: return 'h%d' % (n+1) if n+1 < len(native_rows()) else ''
                if '-path' in args: return 'native.'+name
                if '-meta' in args: return meta
                if '-text' in args: return name
                raise AssertionError(args)
            def selected(*args):
                return str(bool(model['selected'])*1) if '-count' in args else model['selected']
            def select(*args):
                if '-unselect' in args: model['selected'] = ''
                else: model['selected'] = tcl.splitlist(args[-1])[0]; model['select_count'] += 1
                return ''
            def exclude(*args):
                model['excluded'].add((model['index'],model['selected'].removeprefix('native.')))
                return ''
            def exclusion(*args):
                if '-reset' in args: model['excluded'].clear()
                return ''
            def save(*args):
                path = Path(tcl.splitlist(args[-1])[0])
                path.write_text(self.text if model['excluded'] else '')
                if model['excluded']: self.assertEqual(len(model['excluded']),336)
                return ''
            def load_save(*args):
                if '-save' in args: return save(*args)
                self.assertEqual(len(q.parse_el(Path(tcl.splitlist(args[-1])[0]).read_text(),self.c)),336)
                model['excluded'] = {(n,x['native_name']) for n,i in enumerate(self.c['instances']) for x in i['targets']}
                return ''
            def worker(*args):
                if 'inventory' in args:
                    return str(len(q.inventory(out,self.c,args[args.index('--stage')+1],int(args[-1]))))
                return str(q.check_file(out,self.c,args[-1]))
            for name,fn in dict(gui_list_action=action,gui_list_get=get,gui_list_get_selected=selected,
                gui_list_select=select,gui_exclude_items=exclude,gui_exclusion=exclusion,
                gui_exclusion_file=load_save,exec=worker).items(): tcl.createcommand(name,fn)
            tcl.eval('proc gui_open_cov {args} {}; proc gui_list_expand {args} {}; proc gui_process_events {args} {}; proc gui_covdetail_query {args} {return Toggle}; proc gui_cov_excl_review {args} {return 1}')
            tcl.eval('qfp_session')
            self.assertEqual(model['select_count'],336)
            self.assertEqual(model['excluded'],set())
            for index in range(16):
                before = q.inventory(out,self.c,'before',index)
                for stage in q.STAGES[1:]: self.assertEqual(before,q.inventory(out,self.c,stage,index))
            self.assertEqual((out/'first.el').read_bytes(),(out/'second.el').read_bytes())


if __name__ == '__main__': unittest.main()
