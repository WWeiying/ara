"""Actual20-scope fixture, specialization swaps, typed EL and all-stage protection."""
import ast
import copy
import csv
from pathlib import Path
import tempfile
import tkinter
import unittest
import qualify_queue_fp312_native as m


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bindings,cls.pins=m.historical_binding()
        cls.c=dict(instances=m.instances(),historical_bindings=cls.bindings,timeout_seconds=900,
            population_application=False,automatic_retry=False,launch_authorized=False,source_review_seal=m.REVIEW_SHA)
        lines=['ANNOTATION: "'+m.ANNOTATION+'"']
        for i in cls.c['instances']:
            lines+=['CHECKSUM: "%s %s"'%(i['design_module_checksum'],i['toggle_checksum']),'INSTANCE: '+i['scope']]
            lines+=['Toggle %s "logic %s%s"'%(n['name'],m.bounds(n),n['name']) for n in i['targets']]
        cls.el='\n'.join(lines)+'\n'

    def rows(self,index=0,stage='before'):
        path=Path(self.bindings[index]['actual_file'])
        with path.open(newline='') as f:actual=list(csv.reader(f,delimiter='\t'))[1:]
        targets={n['name']+m.bounds(n) for n in self.c['instances'][index]['targets']}
        return [r[:4]+['1' if stage in ('selected','reloaded') and r[3] in targets else '0'] for r in actual]

    def reject(self,el):
        with self.assertRaises(ValueError):m.parse_el(el,self.c)

    def test_actual20_full68_scope_bijection(self):
        m.contract(self.c);m.life.check(self.pins)
        self.assertEqual(len(self.bindings),20)
        self.assertEqual(sum(len(i['targets']) for i in self.c['instances']),312)
        self.assertEqual(sum(len(i['protected']) for i in self.c['instances']),1048)
        self.assertEqual(len(m.parse_el(self.el,self.c)),312)

    def test_no_checksum_only_specialization_substitution(self):
        c=copy.deepcopy(self.c)
        alu=next(i for i in c['instances'] if i['source_FPUSupport']==0)
        fp=next(i for i in c['instances'] if i['source_FPUSupport']==56)
        alu['scope']=fp['scope']
        with self.assertRaises(ValueError):m.contract(c)
        self.reject(self.el.replace('i_operand_queue_alu_a','i_operand_queue_mfpu_a',1))

    def test_dynamic_MFPU_FP16_32_protected(self):
        for i in self.c['instances']:
            if i['source_FPUSupport']!=56:continue
            names={n['name'] for n in i['protected']}
            self.assertIn('fp16[0].m',names);self.assertIn('fp32.m',names)
            self.assertEqual({n['name'] for n in i['targets']},m.source.FP8)
        fp=next(i for i in self.c['instances'] if i['source_FPUSupport']==56)
        self.reject(self.el+'CHECKSUM: "%s %s"\nINSTANCE: %s\nToggle fp16[0].m "logic fp16[0].m[9:0]"\n'%
            (fp['design_module_checksum'],fp['toggle_checksum'],fp['scope']))

    def test_type_checksum_annotation_local_shadow(self):
        for old,new in (('2109767059','2109767058'),('[4:0]fp8[0].e','[3:0]fp8[0].e'),
                        (m.ANNOTATION,'any annotation'),('fp8[0].m','type_conversion.fp8.m')):
            self.reject(self.el.replace(old,new,1))

    def test_missing_duplicate_direction_and_other_metric(self):
        lines=self.el.splitlines();self.reject('\n'.join(lines[:-1]));self.reject(self.el+lines[-1]+'\n')
        self.reject(self.el.replace('Toggle fp8[0].s','Toggle 0to1 fp8[0].s',1))
        for line in ('Line 1','Branch 1','Toggle operand_o "logic operand_o[63:0]"'):
            self.reject(self.el+line+'\n')

    def test_complete_scalar_pairs(self):
        lines=[]
        for line in self.el.splitlines():
            if line.startswith('Toggle ') and '.s "' in line:
                lines.extend([line.replace('Toggle ','Toggle 0to1 ',1),line.replace('Toggle ','Toggle 1to0 ',1)])
            else:lines.append(line)
        self.assertEqual(m.parse_el('\n'.join(lines),self.c),m.parse_el(self.el,self.c))

    def test_every68_row_stage_flags_all20_scopes(self):
        for k,i in enumerate(self.c['instances']):
            for stage in m.STAGES:
                rows=self.rows(k,stage);bound=m.bind_rows(rows,i,stage)
                self.assertEqual(len(bound),68)
                row=next(r for r in rows if any(r[3] in m.aliases(n) for n in i['protected']))
                row[4]='1'
                with self.assertRaises(ValueError):m.bind_rows(rows,i,stage)

    def test_missing_duplicate_extra_unknown_flags(self):
        rows=self.rows();i=self.c['instances'][0]
        for bad in (rows[:-1],rows+[rows[0]],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):m.bind_rows(bad,i,'before')
        rows[0][4]='X'
        with self.assertRaises(ValueError):m.bind_rows(rows,i,'before')

    def test_alias_bounds_and_union_arrays_protected(self):
        i=self.c['instances'][0];rows=self.rows()
        row=next(r for r in rows if r[3].startswith('ntr.w64'))
        self.assertEqual(row[3],'ntr.w64[0][63:0]')
        row[3]=row[1]=row[2]='ntr.w64[1][63:0]'
        with self.assertRaises(ValueError):m.bind_rows(rows,i,'before')

    def test_empty_EL_and_pin_drift(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'final-empty.el';p.write_bytes(b'');m.check_file(p.parent,self.c,p.name)
            pin={str(p):m.life.digest(p)};p.write_bytes(b'// not empty')
            with self.assertRaises(ValueError):m.life.check(pin)
            with self.assertRaises(ValueError):m.check_file(p.parent,self.c,p.name)

    def test_launch_unapproved_and_bad_configuration_reject(self):
        for key,value in (('launch_authorized',True),('timeout_seconds',1800),('automatic_retry',True),('population_application',True)):
            c=dict(self.c);c[key]=value
            with self.assertRaises(ValueError):m.contract(c)

    def test_full_Tcl8_body20scopes312_targets_five_stages(self):
        t=tkinter.Tcl();t.eval('set ::qfp312_test_only 1')
        t.eval('source {%s}'%(m.HERE/'qualify_queue_fp312_native.tcl'))
        for command in ('dict','lassign'):
            if t.eval('info commands '+command):t.eval('rename '+command+' {}')
        # Reuse the reviewed GUI host stub as data, not another lifecycle.
        fixture=m.HERE/'test_qualify_requester_read108_native.py'
        tree=ast.parse(fixture.read_text())
        stubs=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)
               and 'set selected {};set excluded {};set saved {}' in n.value]
        self.assertEqual(len(stubs),1)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);t.setvar('env(DVE_COVERAGE_OUTPUT)',d)
            values=dict(fma_design='HOST',fma_vdb='HOST',fma_test='HOST',fma_python='HOST',fma_helper='HOST',
                        qfp_primitives=str(m.HERE/'fma_datapath_native.tcl'))
            lines=['set %s {%s}\n'%v for v in values.items()]+['set fma_instances {}\n']
            for k,i in enumerate(self.c['instances']):
                rows=self.rows(k);t.setvar('labels_%d'%k,t.call('list',*[r[3] for r in rows]))
                lines.append('lappend fma_instances [list {%s} {%s} {%s} %d %d 68]\n'%(i['scope'],
                    ' '.join(n['name']+m.bounds(n) for n in i['targets']),
                    ' '.join(n['name']+m.bounds(n) for n in i['protected']),k,len(i['targets'])))
            (out/'selection.tcl').write_text(''.join(lines));t.eval(stubs[0])
            self.assertEqual(t.eval('llength $chosen'),'312');self.assertEqual(t.eval('llength $excluded'),'0')
            self.assertEqual(len(t.splitlist(t.eval('set saves'))),5)
            for k in range(20):
                for stage in m.STAGES:self.assertEqual(len(m.inventory(out,self.c,stage,k)),68)


if __name__=='__main__':unittest.main()
