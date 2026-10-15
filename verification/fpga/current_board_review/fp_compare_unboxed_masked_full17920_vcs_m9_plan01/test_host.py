"""Necessary isolated slices plus actual local hook subprocess, never DUT."""
import os
import tempfile
import threading
import unittest
from shared import module
from scope import *
import replay_successor02 as replay
import checker
from specification import specification,model,helper_owner

fixtures=module('masked17920_mature_host_slices','test_host.py',expressions=[
 ('16<=i<32','16<=i<24',1),
 ("c.a['input_periods']+64*row+8*(j//2)","c.a['input_periods']+32*row+8*(j//2)",1),
 ('15<<(addr%8)','3<<(addr%8)',1),
 ("[('fresh',48),('input_reads',15)]","[('fresh',40),('input_reads',7)]",1)])
monitor=module('masked17920_mature_actual_monitor_tests','test_monitor_successor.py')
ready,helper_row,run_helper,rawrow,output_value=fixtures.ready,fixtures.helper_row,fixtures.run_helper,fixtures.rawrow,fixtures.output_value


class MaskedTests(unittest.TestCase):
    def test_actual_geometry_records(self):
        s=specification()
        self.assertEqual([s['sizes'][n] for n in ('a','b','output','mask','oracle_records')],[2048,2048,130,128,71680])
        self.assertEqual((len(s['stores']),len(s['input_loads'])),(41,8))
        self.assertEqual(replay.owner_contract(),dict(memory=89600,target_required=15360,target_elidable=2560))
        for op in range(10):
            self.assertEqual((int(s['helpers'][op][8+(2 if op>=4 else 0)]['insn'],16)>>25)&1,0)
        self.assertEqual([model()[i]['record_index'] for i in (0,1,2,3,17919)],[0,0,1,1,8959])

    def test_alloff_original_tuple_flags_and_inactive_bit(self):
        c=ready(38)
        self.assertEqual((c.current()['op'],c.current()['vl'],c.current()['mode'],c.current()['flags']),(0,8,3,0))
        for i in range(10):c.consume(helper_row(c,i))
        row=helper_row(c,10);row['rd_wdata']='10'
        with self.assertRaisesRegex(ValueError,'flags oracle'):c.consume(row)
        c=ready(10);run_helper(c)
        with self.assertRaisesRegex(ValueError,'allowed'):
            c.consume(rawrow(c,c.s['output_read'],8,output_value(c)^256,c.a['output'],15))

    def test_mask_full_fresh_and_tail_input_preserved(self):
        for area,offset in [('mask',127),('output',129),('a',31),('b',31),('a',32),('b',2047)]:
            c=ready();c.memory[c.a[area]+offset]^=1
            with self.assertRaises(ValueError):c.consume(helper_row(c,0))

    def test_alloff_nonempty_owner_not_waived(self):
        from types import SimpleNamespace
        s=specification();g=model()[38];i=8;ins=int(s['helpers'][0][i]['insn'],16)
        kind,required=helper_owner(s,0,i,g)
        self.assertTrue(required)
        observer=checker.Owners(SimpleNamespace(is_vector_instruction=lambda i:True))
        observer.retvec=[ins];observer.arch=[ins]
        with self.assertRaisesRegex(ValueError,'necessary owner'):
            observer.coverage([dict(insn=ins,required=required,kind=kind,call=38,helper_index=i)])

    def test_bad_original_tuple(self):
        for register,value in ((13,3),(16,1),(17,1)):
            c=ready(38);c.regs[register]=value
            with self.assertRaisesRegex(ValueError,'Eight original arguments'):
                c.consume(helper_row(c,0))

    def test_unknown_business_store_not_defaulted_zero(self):
        from strict import Strict
        c=Strict();s=c.s;r=s['stores'][0];pc=r['pc'];desc=__import__('specification').source.base.memory_desc(int(c.code[pc]['insn'],16))
        c.nextpc=pc;c.regs[desc['base']]=c.a['mask']-desc['offset']
        c.regs.pop(desc['register'],None)
        with self.assertRaisesRegex(ValueError,'Unknown store'):
            c.consume(rawrow(c,pc,address=c.a['mask'],wmask=255,wdata=0))

    def test_actual_local_exit_hook_subprocess(self):
        # Real hook and real collector process, deliberately failed main status.
        # This is lifecycle rejection, never a fabricated successful DUT result.
        with tempfile.TemporaryDirectory(prefix='hook_host_',dir=HERE) as name:
            out=Path(name);contract=replay.service_contract();collector=HERE/'collect_successor.py'
            replay.durable(out/'plan.json',dict(service_terminal_contract=contract,pins={str(collector):sha(collector)}))
            command=[sys.executable,'-B',str(HERE/'exit_hook_successor.py'),'--out',str(out)]
            env=dict(os.environ,SERVICE_RESULT='exit-code',EXIT_CODE='exited',EXIT_STATUS='17')
            result=__import__('subprocess').run(command,cwd=HERE,env=env,stdout=__import__('subprocess').PIPE,
                stderr=__import__('subprocess').STDOUT,text=True,timeout=30)
            self.assertEqual(result.returncode,1,result.stdout)
            self.assertEqual(read(out/'service_exit.json')['EXIT_STATUS'],'17')
            wait=read(out/'collector.wait.json')
            self.assertEqual(wait['actual_wait_exit'],1)
            self.assertFalse(wait['timed_out'])
            self.assertEqual(read(out/'collector.command.json')['command'][2],str(collector))
            self.assertEqual(read(out/'terminal_event.json')['status'],'NOT_ACCEPTED')


SELECTED=[
 'test_actual_soc_spec_not_spike','test_all10_windows_zero_nonzero_last_seed',
 'test_fpr_all32seed_payload_and_x0','test_fpr_wrong_rd','test_fpr_nonzero_zero_box_highbits',
 'test_fpr_wrong_t2','test_missing_fmv','test_bad_opcode','test_deleted_fresh_and_input_ld',
 'test_wrong_record_and_input','test_original_active_guard_vl0_errors','test_tail_allowed_not_strengthened',
 'test_nv_sticky_vstart_restore','test_short_lwu_be','test_partial_eof',
 'test_owner_deletion_vl0_memory_and_nonempty_target','test_owner_alloc_done_mismatch',
 'test_detail_immediate_and_wrong_marker','test_numeric_nonzero_latched','test_metadata_seed_preload_cwd_rejected']


if __name__=='__main__':
    suite=unittest.TestSuite(fixtures.Tests(n) for n in SELECTED)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(MaskedTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(monitor.Tests))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    replay.durable(HERE/'host.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY_NOT_DUT',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=replay.owned_pins(),
        scope='Isolated real-PC/helper slices and real local hook subprocess, not full fake stream',
        actual_local_run_hook_exercised=True,DUT_started=False,reference_rerun=False))
    raise SystemExit(not result.wasSuccessful())
