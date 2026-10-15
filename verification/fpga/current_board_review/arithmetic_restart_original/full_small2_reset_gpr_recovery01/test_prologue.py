"""Small saved-prologue Host regressions, never reopen the DUT CSV."""
from copy import deepcopy
import json
import sys
import unittest
import checker as c

DIAG=c.HERE.parent/'full_small2_firstcause_diagnostic01/first_failure.json'
DIAG_SHA='284e21b85db8d02aadb54a9f00fad6cf98c1d6e0cfce2274e6d566e43488e4ba'


class Prologue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        c.need(c.sha(DIAG)==DIAG_SHA,'Pinned captured first-error evidence')
        cls.evidence=c.read(DIAG)
        cls.spec=c.plan()['specs'][c.SHAPE]
        cls.gold=c.read(c.REF/c.SHAPE/'model.json')
        cls.reset=c.Strict(cls.spec,cls.gold)
        cls.prologue=[r for r in cls.evidence['previous_retirements'] if int(r['order'])>=1653]
        cls.prologue.append(cls.evidence['row'])
        c.need([int(r['insn'],16) for r in cls.prologue]==[0x449000ef,0x1141,0xe406,0xe022],
               'Exact captured jal/sp/ra/s0 prologue')

    def state(self,legacy=False):
        state=c.legacy.Strict(self.spec,self.gold) if legacy else deepcopy(self.reset)
        # Enter at the captured pre-main boundary, not a whole-trace acceptance fixture.
        state.regs.update({int(k):int(v,16) for k,v in self.evidence['known_integer_registers'].items()})
        state.regs[2]=0x800ffff0
        state.retired=1653;state.rows=1656;state.cycle=2215
        state.bss_next=state.s['__bss_end'];state.csr_count=5
        return state

    def feed(self,state,last=None):
        for row in self.prologue[:-1]: state.consume(dict(row))
        state.consume(dict(self.prologue[-1] if last is None else last))

    def test_initial_all_gpr_zero_and_inherited_checks(self):
        self.assertEqual(self.reset.regs,{i:0 for i in range(32)})
        self.assertIs(c.Strict.consume,c.legacy.Strict.consume)
        self.assertIs(c.Strict.finish,c.legacy.Strict.finish)
        self.assertEqual(self.reset.reset_profile_sha256,c.PROFILE_SHA)

    def test_actual_main_prologue(self):
        state=self.state();self.feed(state)
        self.assertEqual(state.value(0x800fffe0,8),0)
        self.assertEqual(state.value(0x800fffe8,8),0x8000004e)
        self.assertEqual(state.retired,1657)
        self.assertEqual(len(state.calls),0)

    def test_original_failure_reproduced(self):
        with self.assertRaisesRegex(ValueError,'Scalar store enables/value/register'):
            self.feed(self.state(legacy=True))

    def test_wrong_mask_address_value(self):
        for field,value in [('mem_wmask','0f'),('mem_rmask','01'),('mem_addr','00000000800fffe8'),
                            ('mem_wdata','0000000000000001')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.feed(self.state(),dict(self.prologue[-1],**{field:value}))

    def test_unknown_source_still_rejected(self):
        state=self.state();del state.regs[8]
        with self.assertRaisesRegex(ValueError,'Scalar store enables/value/register'):
            self.feed(state)
        self.assertNotIn(8,state.regs)

    def test_no_learning_from_wdata(self):
        state=self.state();state.regs[8]=7
        with self.assertRaisesRegex(ValueError,'Scalar store enables/value/register'):
            self.feed(state)
        self.assertEqual(state.regs[8],7)
        matching=self.state();matching.regs[8]=7
        self.feed(matching,dict(self.prologue[-1],mem_wdata='0000000000000007'))
        self.assertEqual(matching.value(0x800fffe0,8),7)

    def test_mismatched_reset_profile(self):
        expected=c.read(c.HERE/'reset_profile.json')
        for field,value in [('FpgaEn',1),('regfile','ariane_regfile_fpga.sv'),('image_sha256','wrong'),
                            ('initial_gpr_values',[1]*32),('trace_origin','midstream'),('allowed_shape','rvv_matrix_e32_mf2')]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'Mismatched reset profile'):
                c.Strict(self.spec,self.gold,profile=dict(expected,**{field:value}))

    def test_complete_trace_origin_still_required(self):
        with self.assertRaisesRegex(ValueError,'Missing original startup'):
            deepcopy(self.reset).consume(dict(self.prologue[-1],order='0'))


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Prologue))
    pins={str(p):c.sha(p) for p in (c.HERE/'checker.py',c.HERE/'reset_profile.json',c.HERE/'test_prologue.py',DIAG)}
    with (c.HERE/'host01.json').open('x') as stream:
        json.dump(dict(status='PASS_PROLOGUE_HOST_ONLY' if result.wasSuccessful() else 'FAIL_PROLOGUE_HOST',
             tests=result.testsRun,failures=len(result.failures)+len(result.errors),pins=pins,
             DUT_CSV_opens=0,full_matrix_Host_runs=0,DUT_runs=0),stream,indent=2);stream.write('\n')
    sys.exit(not result.wasSuccessful())
