"""Small actual-PC/epoch/ABI/marker fixtures, not fullstream reference proof."""
from copy import copy
import unittest
from context import *
from lifecycle import Lifecycle
class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,cls.code,cls.helpers,_=artifacts()
        cls.entries=[cls.helpers['op_'+str(i)][0]['pc'] for i in range(25)]
    def clone(self,obj):
        new=copy(obj);new.memory=obj.memory.copy();return new
    def boot(self):
        o=Lifecycle(self.s,self.code,self.entries);p=o.profile
        for a in range(self.s['__bss_start'],self.s['__bss_end'],8):
            o.source_store(p['bss_pc'],p['bss_code'],a,8,0,{0:0,5:a})
        o.enter(self.s['main']);o.enter(self.s['arithmetic_main']);return o
    def event(self,o,e):
        d=memory_op(e['insn'])
        address=self.s[e['bank']]+e['offset'];regs={0:0,d['base']:address-d['offset'],d['register']:e['value']}
        o.source_store(e['pc'],e['insn'],address,e['size'],e['value'],regs)
    def setup_first(self):
        o=self.boot()
        for e in o.profile['seed_profiles'][0]['events']:self.event(o,e)
        for e in o.profile['mask_profiles'][0]['events']:self.event(o,e)
        return o
    def init(self,o):
        for e in o.profile['initializer']:self.event(o,e)
    def test_actual_source_first_epoch_positive(self):
        o=self.setup_first();self.init(o);o.enter(self.entries[0])
        self.assertEqual((o.calls,o.stores,o.seed_cursor),(1,0,1472))
        self.assertEqual(o.value(self.s['out'],8),0x005b005b005b005b)
        self.assertEqual(o.value(self.s['out']+1024,4),0x005b005b)
    def test_deleted_duplicate_reorder_init(self):
        o=self.setup_first();init=o.profile['initializer']
        for event in (init[1],dict(init[0],offset=1032),dict(init[0],value=0x5b5b5b5b5b5b5b5b)):
            with self.assertRaises(ValueError):self.event(self.clone(o),event)
        self.event(o,init[0])
        with self.assertRaises(ValueError):self.event(o,init[0])
        with self.assertRaises(ValueError):o.enter(self.entries[0])
    def test_tail_wrong_width_high_guard(self):
        o=self.setup_first();items=o.profile['initializer'];tail=next(i for i,e in enumerate(items) if e['size']==4)
        for e in items[:tail]:self.event(o,e)
        for change in (dict(items[tail],size=8),dict(items[tail],value=0x5b5b5b5b)):
            with self.assertRaises(ValueError):self.event(self.clone(o),change)
    def test_mask_wrong_epoch_drop_reorder(self):
        o=self.boot()
        for e in o.profile['seed_profiles'][0]['events']:self.event(o,e)
        e=o.profile['mask_profiles'][0]['events']
        with self.assertRaises(ValueError):self.event(o,e[1])
        self.event(o,e[0])
        with self.assertRaises(ValueError):self.event(o,e[0])
        with self.assertRaises(ValueError):o.enter(self.entries[0])
    def test_rng_wrong_seed_value_missing(self):
        o=self.boot();e=o.profile['seed_profiles'][0]['events']
        for wrong in (e[1],dict(e[0],value=e[0]['value']^1)):
            with self.assertRaises(ValueError):self.event(self.clone(o),wrong)
        with self.assertRaises(ValueError):o.enter(self.entries[0])
    def test_source_GPR_not_default_zero(self):
        o=self.setup_first();e=o.profile['initializer'][0];d=memory_op(e['insn']);a=self.s['out']+e['offset']
        with self.assertRaises(ValueError):o.source_store(e['pc'],e['insn'],a,e['size'],e['value'],{d['base']:a-d['offset']})
        with self.assertRaises(ValueError):o.source_store(e['pc'],e['insn'],a,e['size'],e['value'],{d['base']:a-d['offset'],d['register']:0})
    def test_actual_ABI_save_only(self):
        o=self.boot();pc=next(iter(o.abi));d=memory_op(self.code[pc]);sp=self.s['__stack_top']-304
        o.source_store(pc,self.code[pc],sp+d['offset'],8,0,{2:sp})
        e=o.profile['initializer'][0];d=memory_op(e['insn']);a=self.s['out']+e['offset']
        with self.assertRaises(ValueError):o.source_store(e['pc'],e['insn'],a,8,e['value'],{d['base']:a-d['offset']})
    def test_BSS_missing_or_late(self):
        o=Lifecycle(self.s,self.code,self.entries)
        with self.assertRaises(ValueError):o.enter(self.s['main'])
        o=self.boot()
        with self.assertRaises(ValueError):o.source_store(o.profile['bss_pc'],o.profile['bss_code'],self.s['out'],8,0,{0:0,5:self.s['out']})
    def test_failure_PC_veto(self):
        o=self.boot()
        for pc in o.profile['failure_pcs']:
            with self.assertRaises(ValueError):o.enter(pc)
    def test_marker_fullscope_and_failure_veto(self):
        console_gate(MARKER+'\n')
        for text in (MARKER+'\nFAIL\n',MARKER.replace('4095','4094'),MARKER+'\n'+MARKER, 'BOARD_CASE_BEGIN\n'+MARKER):
            with self.assertRaises(ValueError):console_gate(text)
    def test_EOF_park_late_effect_veto(self):
        p=read(HERE/'PROFILE02.json');park_gate(p['park_pc'],p['park_insn'],'',p)
        for pc,insn,rest in ((p['park_pc']+2,p['park_insn'],''),(p['park_pc'],p['park_insn']^1,''),(p['park_pc'],p['park_insn'],' x1 0x0'),(p['park_pc'],p['park_insn'],' mem 0x80000000 0x0'),(p['park_pc'],p['park_insn'],' c8_vstart 0x0')):
            with self.assertRaises(ValueError):park_gate(pc,insn,rest,p)
    def test_shared_shadow_no_fork(self):
        o=self.boot();shadow=o.memory;self.assertIs(shadow,o.memory)
        o.memory[self.s['out']]=0x79;self.assertEqual(o.value(self.s['out'],1),0x79)
    def test_incomplete_full_source_not_closed(self):
        o=self.setup_first();self.init(o);o.enter(self.entries[0])
        with self.assertRaises(ValueError):o.finish()
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    save(HERE/'HOST02.json',dict(status='PASS_SHORT_HOST_NOT_FULLSTREAM' if result.wasSuccessful() else 'FAIL_SHORT_HOST',
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),raw_reads=0,reference_runs=0,DUT_runs=0,
        fixtures='Actual decoded PC/profile/first original source epoch; not full raw or ISA execution'))
    raise SystemExit(not result.wasSuccessful())
