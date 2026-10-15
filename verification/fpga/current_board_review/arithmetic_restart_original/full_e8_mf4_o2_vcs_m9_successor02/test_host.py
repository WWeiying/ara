"""Full e8 model once plus actual ELF ABI startup; no DUT/reference CSV reads."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
import checker as c
import replay as r

import host_records as fixture
OLD_HOST = c.HERE/'host_records.py'


def abi_rows(spec):
    """Exact compiled _start/BSS/main-save path, instruction semantics from e8 ELF.

    These are constructed architectural rows, not claimed captured DUT rows.
    The legacy full-core generator omits this ABI path; both are tested here.
    """
    code = {int(k): v for k, v in spec['backend']['code'].items()}
    symbols = spec['backend']['symbols']
    base = symbols['_start']
    c.require(base == 0x80000000 and symbols['main'] == 0x800010a2 and
              [code[base+i] for i in (0,4,8,12,0x4a)] ==
              [0x00002197,0x17018193,0x00100117,0xfe810113,0x058010ef] and
              [code[symbols['main']+i] for i in (0,2,4,6)] ==
              [0x1141,0xe406,0xe022,0xc2202773], 'Actual e8 ABI instruction identity')
    order = 0
    def row(pc, rd=0, value=0, address=0, wm=0, data=0):
        nonlocal order
        d = dict(cycle=str(order+1),event='retire',order=str(order),port='0',trans_id='-1',
                 pc=f'{pc:016x}',insn=f'{code[pc]:08x}',rd=str(rd),rd_wdata=f'{value:016x}',
                 mem_addr=f'{address:016x}',mem_rmask='00',mem_wmask=f'{wm:02x}',
                 mem_wdata=f'{data:016x}',trap='0')
        order += 1
        return d
    for offset,rd,value in ((0,3,0x80002000),(4,3,0x80002170),(8,2,0x80100008),
            (12,2,0x800ffff0),(0x10,0,0),(0x14,5,0x80000014),(0x18,5,0x80000050),
            (0x1c,0,0),(0x20,5,0x6000),(0x22,5,0x6600),(0x26,0,0),
            (0x2a,0,0),(0x2e,0,0),(0x32,5,0x80002032),
            (0x36,5,symbols['__bss_start']),(0x3a,6,symbols['__bss_end'])):
        yield row(base+offset,rd,value)
    for address in range(symbols['__bss_start'],symbols['__bss_end'],8):
        yield row(base+0x3e)
        yield row(base+0x42,address=address,wm=255,data=0)
        yield row(base+0x46,5,address+8)
        yield row(base+0x48)
    yield row(base+0x3e)
    yield row(base+0x4a,1,base+0x4e)
    main = symbols['main']
    yield row(main,2,0x800fffe0)
    yield row(main+2,address=0x800fffe8,wm=255,data=base+0x4e)
    yield row(main+4,address=0x800fffe0,wm=255,data=0)
    yield row(main+6,14,128)


def with_owners(rows):
    seq=0
    for row in rows:
        if row['event']=='retire' and c.MemoryOwners.memory(int(row['insn'],16)):
            event=dict(row,order=str(seq),port='-1',trans_id='0',pc='0000000000000000',
                       rd='0',rd_wdata='0000000000000000',mem_addr='0000000000000000',
                       mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000')
            yield dict(event,event='arch_start')
            yield dict(event,event='uop_alloc',port='0')
            yield dict(event,event='uop_done',port='0')
            seq+=1
        yield row


class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = c.specification(c.SHAPE)
        cls.gold = c.read(c.REF/c.SHAPE/'model.json')
        cls.reset = c.Strict(cls.spec,cls.gold)
        cls.abi = list(abi_rows(cls.spec))
        cls.before_save = deepcopy(cls.reset)
        for row in cls.abi[:-2]:
            cls.before_save.consume(row)
        cls.full = deepcopy(cls.reset)
        cls.snapshots = {}
        fixture_spec = deepcopy(cls.spec)
        fixture_spec['backend']['symbols'].update(failure=cls.reset.s['failure'],
                                                  selected=cls.spec['backend']['symbols']['number'])
        for row in with_owners(fixture.records(fixture_spec,cls.gold)):
            address = int(row['mem_addr'],16)
            if cls.full.active and cls.full.active['ordinal'] == 4094 and row['mem_rmask'] != '00':
                lane = (address-cls.full.s['out'])
                if lane in (1,33):
                    cls.snapshots[lane] = (deepcopy(cls.full),dict(row))
            cls.full.consume(row)
        cls.full_result = cls.full.finish()

    def test_full4095_original_positive(self):
        d = self.full_result
        self.assertEqual([d[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')],
                         [4095,131040,8190,4095,53235])
        self.assertEqual({x['op'] for x in d['call_ledger']},set(range(25)))
        self.assertEqual({x['seed'] for x in d['call_ledger']},{0,1,2})
        self.assertTrue(d['full_order']); self.assertFalse(d['partitioned'])

    def test_actual_e8_complete_abi_entry(self):
        s = deepcopy(self.reset)
        for row in self.abi: s.consume(row)
        self.assertEqual(s.value(0x800fffe8,8),0x8000004e)
        self.assertEqual(s.value(0x800fffe0,8),0)
        self.assertEqual(s.bss_next,s.s['__bss_end'])
        self.assertEqual(s.csr_count,6)
        self.assertTrue(s.main_entered)

    def test_abi_wrong_mask_address_value(self):
        for field,value in (('mem_wmask','0f'),('mem_rmask','01'),
                            ('mem_addr','00000000800fffe8'),('mem_wdata','0000000000000001')):
            with self.subTest(field=field),self.assertRaises(ValueError):
                deepcopy(self.before_save).consume(dict(self.abi[-2],**{field:value}))

    def test_unknown_source_rejected(self):
        s = deepcopy(self.before_save); del s.regs[8]
        with self.assertRaisesRegex(ValueError,'Scalar store enables/value/register'):
            s.consume(self.abi[-2])
        self.assertNotIn(8,s.regs)

    def test_no_learning(self):
        s = deepcopy(self.before_save); s.regs[8] = 7
        with self.assertRaises(ValueError): s.consume(self.abi[-2])
        self.assertEqual(s.regs[8],7)

    def test_profile_spec_model_mismatch(self):
        with self.assertRaises(ValueError): c.Strict(self.spec,self.gold[:-1])
        with self.assertRaises(ValueError): c.Strict(dict(self.spec,ctrl=0xdead),self.gold)
        self.assertEqual(self.reset.regs,{i:0 for i in range(32)})

    def test_missing_nonempty_memory_owner_pair(self):
        s=deepcopy(self.full)
        seq=next(seq for seq in s.owners.memory_arch if s.owners.arch[seq]['allocs'])
        s.owners.arch[seq]['allocs']=s.owners.arch[seq]['dones']=0
        s.owners.allocs-=1;s.owners.dones-=1
        with self.assertRaisesRegex(ValueError,'Missing nonempty memory owner'):s.finish()

    def test_missing_active_target_owner_pair(self):
        s=deepcopy(self.full)
        index=next(i for i,x in enumerate(s.owners.expected) if x['active_target'])
        seq=s.owners.memory_arch[index]
        count=s.owners.arch[seq]['allocs']
        self.assertGreater(count,0)
        s.owners.arch[seq]['allocs']=s.owners.arch[seq]['dones']=0
        s.owners.allocs-=count;s.owners.dones-=count
        with self.assertRaisesRegex(ValueError,'Missing nonempty memory owner'):s.finish()

    def test_empty_target_owner_may_elide(self):
        s=deepcopy(self.full)
        index=next(i for i,x in enumerate(s.owners.expected) if not x['required'])
        seq=s.owners.memory_arch[index];count=s.owners.arch[seq]['allocs']
        s.owners.arch[seq]['allocs']=s.owners.arch[seq]['dones']=0
        s.owners.allocs-=count;s.owners.dones-=count
        self.assertEqual(s.finish()['memory_owners']['required_active_memory_targets'],117)

    def test_wrong_memory_owner_identity(self):
        owner=c.MemoryOwners(self.spec)
        row=dict(event='arch_start',order='0',port='-1',trans_id='2',insn='02050407')
        owner.consume(row)
        with self.assertRaises(ValueError):owner.consume(dict(row,event='uop_alloc',port='0',trans_id='3'))
        with self.assertRaises(ValueError):owner.consume(dict(row,event='uop_done',port='0'))
        
    def test_missing_start(self):
        with self.assertRaisesRegex(ValueError,'Missing original startup'):
            deepcopy(self.reset).consume(dict(self.abi[-2],order='0'))

    def test_last_result_guard_and_signed_mask(self):
        for lane in (1,33):
            state,row = self.snapshots[lane]
            for field,value in (('rd_wdata',f'{int(row["rd_wdata"],16)^1:016x}'),('mem_rmask','0f')):
                with self.subTest(lane=lane,field=field),self.assertRaises(ValueError):
                    deepcopy(state).consume(dict(row,**{field:value}))
        self.assertEqual(c.loaded_value(0x8000,2,True),0xffffffffffff8000)

    def test_incomplete_tail_rejected(self):
        with self.assertRaises(ValueError): self.snapshots[33][0].finish()

    def test_durable_numeric_exit_before_postcheck(self):
        for numeric,timed,failed in ((0,False,False),(124,True,False),(2,False,True)):
            with tempfile.TemporaryDirectory(dir=c.HERE) as temp:
                root = Path(temp); abort = threading.Event()
                r.durable(root/'command.json',dict(command=['host-fixture'],cwd=str(root)))
                monitor = r.monitored_with_outcome(lambda *a:(numeric,0.01,timed,failed),abort)
                monitor(['host-fixture'],root,root/'console.log',10800)
                saved = c.read(root/'child_outcome.unvalidated.json')
                self.assertEqual(saved['returncode'],numeric)
                self.assertEqual(saved['timed_out'],timed)
                self.assertFalse(saved['architectural_acceptance'])
                self.assertEqual(abort.is_set(),numeric != 0 or timed or failed)

    def test_late_abort_and_postcheck_error(self):
        for throws in (False,True):
            abort = threading.Event()
            result = SimpleNamespace(status='PASS',returncode=0,reason='')
            class Parent:
                def __init__(self): pass
                def _run_test(self,*a): return result
            def check(_):
                abort.set()
                if throws: raise ValueError('postcheck')
            got = r.checked_runner(Parent,abort,check,lambda n:None)()._run_test(SimpleNamespace(name='e8'),None)
            self.assertNotEqual(got.status,'PASS'); self.assertEqual(got.returncode,0)

    def test_exact_bounds_owner_and_entry_gate(self):
        props = dict(Id=r.UNIT,LoadState='loaded',ActiveState='active',SubState='running',MainPID='7',
                     ControlGroup='/owned/'+r.UNIT,RuntimeMaxUSec='3h 40min',KillMode='control-group',Restart='no')
        r.owner_gate(props,'0::/owned/'+r.UNIT,7)
        for k,v in (('MainPID','8'),('KillMode','process'),('RuntimeMaxUSec','4h')):
            with self.assertRaises(ValueError): r.owner_gate(dict(props,**{k:v}),'0::/owned/'+r.UNIT,7)
        self.assertEqual((r.JOBS,r.CASE_BOUND,r.WORKER_BOUND,r.OUTER),(1,10800,12000,13200))
        with self.assertRaises(ValueError): r.reviews({'pins':{}},'sha',None,None,None,None)

    def test_late_plan_drift(self):
        with tempfile.TemporaryDirectory(dir=c.HERE) as temp:
            root = Path(temp); r.durable(root/'plan.json',{})
            with self.assertRaises(ValueError): r.terminal_disk_gate(root,'wrong',r.IMAGE)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins = {str(c.HERE/n):c.sha(c.HERE/n) for n in ('checker.py','replay.py','test_host.py','reset_profile.json')}
    pins[str(OLD_HOST)] = c.sha(OLD_HOST)
    r.durable(c.HERE/'host01.json',dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
         tests=result.testsRun,failures=len(result.failures)+len(result.errors),pins=pins,
         full_positive_shapes=[c.SHAPE] if result.wasSuccessful() else [],
         actual_abi_entry_checked=result.wasSuccessful(), full4095_streams=1,
         ABI_fixture='Actual e8 ELF instruction sequence; constructed architectural rows, not captured CSV',
         CSV_reads=0,DUT_reference_build_runs=0))
    raise SystemExit(not result.wasSuccessful())
