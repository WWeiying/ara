import copy
from pathlib import Path
from types import FunctionType
import unittest
from unittest.mock import patch
import check_scalar_c910_pattern795_two_layer as a
import test_run_collect_scalar_c910_pattern795 as inherited


class Physical(inherited.Native):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pre=a.life.read_bound(a.c.runner.PRE/'preflight.json',a.c.runner.PRE_SHA)
        cls.wave=a.life.OUT/'scalar-c910-pattern795-qualified-v2-parent-20261008-01/probe.vcd'
        parse=a.c.frozen.original.oracle.prior.wave.vcd
        stream=iter(FunctionType(parse.__code__,dict(parse.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))(cls.wave))
        _,cls.real_decl=next(stream);cls.real_prefix=[]
        for time,before,after in stream:
            if before.get(cls.real_decl['ara_tb.clk']['code'])=='0' and after.get(cls.real_decl['ara_tb.clk']['code'])=='1' and before.get(cls.real_decl['ara_tb.rst_n']['code'])=='1':
                if time>=51055000:cls.real_prefix.append((time,before,after))
            if time>=51165000:break

    def audit(self,expected,edges):
        tracker=a.PhysicalTracker(self.decl,self.proof,{e['pc']:e['kind'] for e in expected})
        for time,before,after in edges:tracker.consume(time,before,after)
        r=tracker.finish()
        # Compatibility aliases exist only in these inherited fixtures, never the production receipt.
        return dict(r,completed=r['outputs'],table_observations=[s for s in r['stages'] if s['stage']=='round'],
            initial_observations=[s for s in r['stages'] if s['stage']=='initial'],scheduled_cancellations=r['cancellations'])

    def prefix(self,edges):
        tracker=a.PhysicalTracker(self.real_decl,self.proof,a.routes(self.pre))
        for time,before,after in edges:tracker.consume(time,before,after)
        return tracker

    def test_actual_full_wave_independent_1176_math_outputs(self):
        result=a.wave_audit(self.wave,self.proof,self.pre)
        self.assertEqual((result['physical_issues'],result['physical_requests'],result['physical_outputs'],
            result['synchronous_cancels']),(1359,1359,1176,183))
        self.assertEqual(sum(o['kind']=='SQRT' for o in result['cancellations']),16)
        self.assertEqual(sum(o['kind']=='DIV' for o in result['outputs']),160)
        self.assertEqual(sum(o['kind']=='SQRT' for o in result['outputs']),64)
        self.assertFalse(result['physical_output_to_retirement_mapping_claimed'])

    def test_flush_priority_cancel_then_reissue(self):
        e,normal=self.fixture();issue=[-2,dict(normal[0][1]),dict(normal[0][2])]
        before=dict(normal[1][1]);before[a.c.SCOPE+'.flush_i']='1'
        before[a.c.ISSUE+'.fpu_valid_n']='0';before[a.c.SCOPE+'.fpu_valid_o']='0'
        after={p:'0'*v['width'] for p,v in self.decl.items()}
        full=self.audit(e,[issue,[-1,before,after]]+normal)
        self.assertEqual(len(full['cancellations']),1);self.assertEqual(len(full['outputs']),4)
        canceled_only=self.audit(e,[issue,[-1,before,after]])
        self.assertEqual(canceled_only['physical_outputs'],0)
        self.assertFalse(canceled_only['physical_output_to_retirement_mapping_claimed'])
        with self.assertRaises(ValueError):a.c.architecture([],self.pre,{})

    def test_actual_prefix_output_before_flush_then_same_PC_reissue(self):
        t=self.prefix(self.real_prefix)
        self.assertEqual(len(t.outputs),2)
        self.assertEqual(len(t.issues),3)
        self.assertEqual(t.issues[0]['pc'],t.issues[-1]['pc'])
        self.assertNotEqual(t.issues[0]['physical_index'],t.issues[-1]['physical_index'])
        self.assertTrue(t.outputs[-1]['flush_edge'])

    def test_actual_wave_wrong_output_fields_and_unknowns_rejected(self):
        for name,value in (('result_o',0),('fpu_trans_id_o',6),('fpu_exception_o',1<<139),
            ('result_o','x'),('fpu_trans_id_o','x'),('fpu_exception_o','x'),('fpu_valid_o',0)):
            edges=copy.deepcopy(self.real_prefix);path=a.c.SCOPE+'.'+name
            for time,before,after in edges:
                if time==51075000:
                    before[self.real_decl[path]['code']]=value if type(value) is str else format(value,'b')
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):self.prefix(edges)

    def test_actual_wave_used_operand_op_RM_unknown_or_illegal_rejected(self):
        for name,value in (('operand_a_d','x'),('fpu_op_d','x'),('fpu_rm_d','x'),('fpu_rm_d','111')):
            edges=copy.deepcopy(self.real_prefix);path=a.c.SCOPE+'.fpu_gen.'+name
            for time,before,after in edges:
                if time==51065000:before[self.real_decl[path]['code']]=value
            with self.subTest(name=name),self.assertRaises(ValueError):self.prefix(edges)

    def test_math_gold_does_not_use_reference_result_or_cursor(self):
        e,edges=self.fixture();altered=copy.deepcopy(e)
        for row in altered:row['result']=0;row['fflags']=31;row['cell']=999
        r=self.audit(altered,edges)
        self.assertEqual(len(r['outputs']),4)
        self.assertTrue(all(o['math_gold_from_actual_request'] for o in r['outputs']))

    def test_math_result_oracle_changes_cannot_be_filled_from_output(self):
        e,edges=self.fixture();gold=a.c.oracle.gold
        def wrong(*args):
            g=gold(*args);return dict(g,result=g['result']^1)
        with patch.object(a.c.oracle,'gold',side_effect=wrong):
            with self.assertRaisesRegex(ValueError,'mathematical result'):self.audit(e,edges)

    def test_source_authority_all_pins_and_exact_roles(self):
        pins=a.authority();a.life.check(pins)
        self.assertIn(str(Path(a.__file__).resolve()),pins)
        self.assertEqual(len(a.routes(self.pre)),8)

    def test_missing_probe_or_wrong_width_rejected(self):
        for change in ('missing','width'):
            decl=copy.deepcopy(self.decl);path=a.c.SCOPE+'.result_o'
            if change=='missing':del decl[path]
            else:decl[path]['width']=63
            with self.assertRaises(ValueError):a.PhysicalTracker(decl,self.proof,{})

    def test_wrong_or_unknown_each_driven_exception_field_rejected(self):
        for field in ('cause','valid','tval'):
            for unknown in (False,True):
                e,edges=self.fixture();path=a.c.SCOPE+'.fpu_exception_o'
                left,right=self.proof['exception_layout']['fields'][field]
                bits=list(edges[2][1][path]);width=self.decl[path]['width']
                bits[width-left-1:width-right]=('x'*(left-right+1) if unknown else format(1,'0%db'%(left-right+1)))
                edges[2][1][path]=''.join(bits)
                with self.subTest(field=field,unknown=unknown),self.assertRaises(ValueError):self.audit(e,edges)

    def test_new_unknown_PC_and_unclosed_lifecycle_rejected(self):
        e,edges=self.fixture();roles={r['pc']:r['kind'] for r in e};del roles[4]
        t=a.PhysicalTracker(self.decl,self.proof,roles)
        with self.assertRaises(ValueError):t.consume(*edges[0])
        t=a.PhysicalTracker(self.decl,self.proof,{r['pc']:r['kind'] for r in e});t.consume(*edges[0])
        with self.assertRaises(ValueError):t.finish()


if __name__=='__main__':unittest.main()
