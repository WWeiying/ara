"""Short real-PC store-width boundaries plus exact fullHost/current code diff."""
import ast
from copy import copy
import unittest
import checker as c
import replay as r
from host_records import Builder
def clone(s):
    n=copy(s);n.regs=s.regs.copy();n.memory=s.memory.copy()
    n.fresh={k:v.copy() for k,v in s.fresh.items()}
    n.counts=s.counts.copy();n.console=bytearray(s.console);n.calls=s.calls.copy();n.offloads=s.offloads.copy()
    return n
def normalized(text,worker=False):
    tree=ast.parse(text)
    if worker:tree.body=[n for n in tree.body if not (isinstance(n,ast.FunctionDef) and n.name=='prepare')]
    class Width(ast.NodeTransformer):
        def visit_BinOp(self,n):
            self.generic_visit(n)
            if isinstance(n.op,ast.BitAnd) and isinstance(n.left,ast.Name) and n.left.id=='wd' and isinstance(n.right,ast.Name) and n.right.id=='bits':
                return ast.Name(id='wd',ctx=ast.Load())
            return n
    return ast.dump(Width().visit(tree),include_attributes=False)
class Short(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec=c.specification();cls.state=c.Strict(cls.spec);cls.builder=Builder(cls.spec)
        for row in cls.builder.abi():cls.state.consume(row)
        for j,e in enumerate(cls.spec['backend']['helpers']['capacity']):
            cls.state.consume(cls.builder.row(e['pc'],5 if j==0 else 10 if j==1 else 0,
                c.MASK64 if j==0 else 512 if j==1 else 0))
        cls.first=cls.spec['source_seed'][0]['events'][0]
        c.require(cls.first['size']==2 and cls.first['source_register_value']>65535,'Actual compiled SH high source bits')
        cls.before_SH=clone(cls.state)
        rows=list(cls.builder.write(cls.state.s[cls.first['bank']]+cls.first['offset'],
            cls.first['source_register_value'],2,cls.first['pc']))
        for row in rows[:-1]:cls.before_SH.consume(row)
        cls.SH=rows[-1]
        s=c.Strict(cls.spec);b=Builder(cls.spec)
        for row in b.abi():s.consume(row)
        for j,e in enumerate(cls.spec['backend']['helpers']['capacity']):
            s.consume(b.row(e['pc'],5 if j==0 else 10 if j==1 else 0,c.MASK64 if j==0 else 512 if j==1 else 0))
        for e in cls.spec['source_seed'][0]['events']+cls.spec['source_mask'][0]['events']:
            for row in b.write(s.s[e['bank']]+e['offset'],e['source_register_value'],e['size'],e['pc']):s.consume(row)
        for pc,insn,size,offset in cls.spec['init_stores']:
            value=0x005b005b if size==4 else 0x005b005b005b005b
            if size==4:
                # Same real SW PC/active bytes, legal nonzero inactive carrier bits;
                # this is an RVFI boundary fixture, not a new original C input.
                rows=list(b.write(s.s['out']+offset,value|(0xfeedface<<32),size,pc))
                for row in rows[:-1]:s.consume(row)
                cls.before_SW=clone(s);cls.SW=rows[-1];break
            for row in b.write(s.s['out']+offset,value,size,pc):s.consume(row)
    def test_actual_SH_full_source_positive(self):
        s=clone(self.before_SH);s.consume(self.SH);self.assertEqual(s.seed_index,1)
    def test_actual_SW_inactive_high_positive(self):
        s=clone(self.before_SW);before=s.init_index;s.consume(self.SW);self.assertEqual(s.init_index,before+1)
    def test_active_low_wrong_and_BE_rejected(self):
        for state,row in ((self.before_SH,self.SH),(self.before_SW,self.SW)):
            for field,value in (('mem_wdata',f'{int(row["mem_wdata"],16)^1:016x}'),('mem_wmask','00')):
                with self.subTest(field=field),self.assertRaises(ValueError):clone(state).consume(dict(row,**{field:value}))
    def test_unknown_source_and_wrong_epoch_rejected(self):
        for state,row in ((self.before_SH,self.SH),(self.before_SW,self.SW)):
            s=clone(state);del s.regs[c.memory_op(int(row['insn'],16))['register']]
            with self.assertRaises(ValueError):s.consume(row)
        s=clone(self.before_SH);s.seed_index=1
        with self.assertRaises(ValueError):s.consume(self.SH)
        s=clone(self.before_SW);s.init_index+=1
        with self.assertRaises(ValueError):s.consume(self.SW)
    def test_current_code_is_only_width_and_prepare_binding_delta(self):
        old=c.HERE/'host01_frozen_code'
        self.assertEqual(normalized((old/'checker.py').read_text()),normalized((c.HERE/'checker.py').read_text()))
        self.assertEqual(normalized((old/'replay.py').read_text(),True),normalized((c.HERE/'replay.py').read_text(),True))
        pre=c.read(c.HERE/'host01_preflight.json')
        for name in ('checker.py','replay.py','test_host.py','host_records.py','reset_profile.json','soc_profile.json','owner_policy.py','run_host.py'):
            p=old/name if name in ('checker.py','replay.py') else c.HERE/name
            self.assertEqual(c.sha(p),pre[str(c.HERE/name)])
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Short))
    pins={str(p):c.sha(p) for p in c.HERE.iterdir() if p.is_file() and p.suffix in ('.py','.json','.md') and p.name!='width_successor_result.json'}
    r.durable(c.HERE/'width_successor_result.json',dict(status='PASS_NARROW_STORE_WIDTH_SUCCESSOR' if result.wasSuccessful() else 'FAIL',
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),pins=pins,
        complete_Host_reruns=0,constructed_first_epoch_only=True,DUT_runs=0,reference_runs=0,
        SW_high_bits_fixture_not_original_C_input=True))
    raise SystemExit(not result.wasSuccessful())
