#!/usr/bin/env python3
"""Host-only negative gates; never queries services or writes any sealed evidence."""
import copy
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import replay as driver
import checker


def specification(op):
    proof = driver.read(checker.DATA/'source_elf_proof.json')['results'][0 if op==1 else 1]
    name = proof['name']
    elf = Path(driver.read(checker.DATA/'soc01/programs.json')['programs'][name]['path'])
    spec = dict(name=name,operation=op,soc_routine=proof['soc_routine'])
    for field,sym in (('input_address','input'), ('index_address','indices16' if op==20 else 'indices'),
                      ('output_address','output'), ('predicate_address','predicate')):
        spec[field] = driver.symbol(elf,sym,driver.OBJDUMP)[0]
    store, = [r for r in driver.instructions(elf,'replay_exit') if r['text'].startswith('sd\t')]
    spec.update(exit_store_address=0xd0000000,exit_store_pc=store['pc'])
    return spec


def synthetic(spec, model):
    rows = []
    def put(pc=0x80010000,insn=0x13,rd=0,value=0,address=0,rmask=0,wmask=0,wdata=0):
        rows.append(dict(cycle=str(len(rows)+1),event='retire',pc=hex(pc),insn=hex(insn),rd=str(rd),
            rd_wdata=hex(value),mem_addr=hex(address),mem_rmask=hex(rmask),mem_wmask=hex(wmask),mem_wdata=hex(wdata),trap='0'))
    for expected in model['rows']:
        for reg,value in ((10,spec['input_address']), (11,spec['index_address']), (12,spec['output_address']+1),
                          (13,expected['vl']), (14,512), (15,spec['predicate_address']),
                          (16,expected['scalar']), (17,expected['vstart'])):
            put(rd=reg,value=value)
        for i,item in enumerate(spec['soc_routine']):
            rd,value = (28,expected['scalar']) if i==6 else (10,0) if i==9 else (0,0)
            put(pc=item['pc'],insn=int(item['insn'],16),rd=rd,value=value)
        for index,value in enumerate([91]+expected['output']+[91]):
            put(insn=0x03,rd=6,value=value,address=spec['output_address']+index,rmask=1)
    put(pc=spec['exit_store_pc'],insn=0x23,address=spec['exit_store_address'],wmask=255,wdata=0)
    return rows


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs = [specification(op) for op in (1,20)]
        cls.models = [checker.source.prep.model(op) for op in (1,20)]
        cls.good = synthetic(cls.specs[0],cls.models[0])

    def rejected(self, mutate):
        rows = copy.deepcopy(self.good)
        mutate(rows)
        with self.assertRaises(ValueError):
            checker.retirement(rows,self.specs[0],self.models[0])

    def test_complete_both_original_prefixes(self):
        for spec,model in zip(self.specs,self.models):
            result = checker.retirement(synthetic(spec,model),spec,model)
            self.assertEqual(result['routine_retire_counts'],[98]*13)
            self.assertEqual(result['actual_output_scalar_loads'],50372)
            self.assertEqual(result['events'][-1]['original_tuple'],[0,spec['operation'],0,6,0,1])

    def test_missing_call_even_with_full_address_union(self):
        self.rejected(lambda rows:rows.__delitem__(slice(0,535)))

    def test_missing_first_call_tail_not_hidden_by_other_calls(self):
        address = hex(self.specs[0]['output_address']+512)
        self.rejected(lambda rows:rows.pop(next(i for i,r in enumerate(rows) if r['mem_addr']==address)))

    def test_corrupt_prestart_and_guard(self):
        for offset in (0,1,513):
            def mutate(rows):
                row = next(r for r in rows if int(r['mem_addr'],16)==self.specs[0]['output_address']+offset)
                row['rd_wdata'] = '0'
            self.rejected(mutate)

    def test_setup_scalar_or_pointer_veto(self):
        for register in ('11','16','17'):
            self.rejected(lambda rows:next(r for r in rows if r['rd']==register).__setitem__('rd_wdata','0xdead'))

    def test_original_asm_and_csr_veto(self):
        for index in (2,8,9):
            pc = hex(self.specs[0]['soc_routine'][index]['pc'])
            def mutate(rows):
                row = next(r for r in rows if r['pc']==pc)
                row['rd_wdata' if index==9 else 'insn'] = '0x1'
            self.rejected(mutate)

    def test_exit_trap_veto(self):
        self.rejected(lambda rows:rows[-1].__setitem__('mem_wdata','0x3'))
        self.rejected(lambda rows:rows[-1].__setitem__('mem_wdata','0x1'))
        self.rejected(lambda rows:rows[-1].__setitem__('trap','1'))

    def test_console_failure_after_pass(self):
        name = checker.NAMES[0]
        text = '\n'.join(['BOARD_CASE_BEGIN '+name,'RVV_GATHER_PREFIX_PASS sew=8 cases=98 errors=0',
                          'BOARD_CASE_PASS '+name,'BOARD_REPLAY_PASS','Core Test *** SUCCESS ***'])
        checker.console_gate(text,name)
        for suffix in ('RVV_GATHER_PREFIX_FAIL','RVV_PERMUTE_DETAIL','ABORTED','TRAP','BOARD_REPLAY_PASS'):
            with self.assertRaises(ValueError):
                checker.console_gate(text+'\n'+suffix,name)
        with self.assertRaises(ValueError):
            checker.console_gate(text.replace('cases=98','cases=66'),name)

    def test_transfer_replaces_not_adds_fp_slots(self):
        rows = [dict(pid=i,cgroup='0::/user/'+driver.UNITS[name]+'\n',argv='simv')
                for i,name in enumerate(n for n,count in driver.QUOTAS.items() if n!='gather' for _ in range(count))]
        result = driver.resource_math(rows,40*1024**3)
        self.assertEqual(result['total_live_plus_reserved'],20)
        self.assertEqual(result['fp_slots_after_transfer'],0)
        with self.assertRaises(ValueError):
            driver.resource_math(rows+[dict(pid=999,cgroup='0::/'+driver.FP_UNIT,argv='simv')],40*1024**3)
        with self.assertRaises(ValueError):
            driver.resource_math(rows,31*1024**3)
        with self.assertRaises(ValueError):
            driver.resource_math(rows,40*1024**3,True)
        with self.assertRaises(ValueError):
            driver.resource_math(rows+[dict(pid=i+100,cgroup='0::/unknown',argv='simv') for i in range(5)],40*1024**3)

    def test_unapproved_parent_no_service_query(self):
        with patch.object(driver.dependency,'query_unit') as query:
            with self.assertRaises(ValueError):
                driver.fresh_admission({},'wrong','wrong')
            query.assert_not_called()

    def test_active_or_query_error_dependency_rejected(self):
        unit = driver.FP_UNIT
        text = '\n'.join([f'Id={unit}','LoadState=loaded','ActiveState=active','SubState=running',
                          'MainPID=2','ControlPID=0','ControlGroup=/live'])
        for rc,err in ((0,''),(1,'Failed to connect to bus')):
            with self.assertRaises(ValueError):
                driver.dependency.parse_unit(unit,driver.SimpleNamespace(stdout=text,stderr=err,returncode=rc))

    def test_unreadable_potential_simv_failclosed(self):
        class Field:
            def read_bytes(self):
                raise PermissionError(13,'unreadable')
            def read_text(self):
                return 'simv'
        class Proc:
            name = '123'
            def __truediv__(self,part):
                return Field()
        _,_,unreadable = driver.helpers.scan_processes([Proc()])
        self.assertEqual(len(unreadable),1)

    def startup(self, behavior):
        with tempfile.TemporaryDirectory(dir=driver.LOCAL,prefix='host_startup_') as directory:
            out = Path(directory)
            cgroup = '0::/user/'+driver.UNIT+'\n'
            driver.save(out/'worker.json',dict(cgroup=cgroup))
            simv = driver.read(driver.IMAGE/'image.json')['simv']
            live = []
            for pid,name in enumerate(checker.NAMES,1):
                folder = out/'replay/tests'/name
                argv = [simv,'+TESTCASE='+name,'+PRELOAD='+str(folder/'input.elf'),'+COMMIT_TRACE='+str(folder/'commit_trace.csv')]
                live.append(dict(pid=pid,argv=argv))
            samples = [0]
            clock = [0.0]
            def sample(pid,args):
                samples[0] += 1
                index = samples[0]
                if behavior=='generation' and index==3:
                    raise ProcessLookupError(3,'process exited')
                amount = 1 if index<=4 or behavior=='no_growth' else index
                return dict(pid=pid,start_ticks=100,argv=args,executable=str(Path(simv).resolve()),cgroup=cgroup,
                            cwd=str(out/'replay/tests'/checker.NAMES[pid-1]/'work'),cpu_ticks=amount,trace_bytes=amount,last_cycle=amount)
            class Done:
                def is_set(self):return False
                def wait(self,seconds):clock[0]+=seconds
            if behavior=='identity':
                live[0]['argv'][0] = '/wrong/simv'
            cancelled = threading.Event()
            with patch.object(driver,'OUT',out), patch.object(driver,'checked_plan',return_value=(dict(image=str(driver.IMAGE),unit=driver.UNIT),'')), \
                 patch.object(driver.helpers,'scan_processes',return_value=(live,False,[])), \
                 patch.object(driver.helpers,'sample',side_effect=sample), patch.object(driver.time,'monotonic',side_effect=lambda:clock[0]):
                driver.confirmation(Done(),cancelled.set)
            record = driver.read(out/'actual_simv_confirmation.json')
            return record,cancelled.is_set(),clock[0]

    def test_startup_first_no_growth_uses_original_window(self):
        result,cancelled,elapsed = self.startup('later_growth')
        self.assertEqual(result['status'],'ADVANCING_TWO_SIMV')
        self.assertFalse(cancelled)
        self.assertGreaterEqual(elapsed,1)
        self.assertLess(elapsed,60)

    def test_startup_process_race_rediscovery(self):
        result,cancelled,_ = self.startup('generation')
        self.assertEqual(result['status'],'ADVANCING_TWO_SIMV')
        self.assertFalse(cancelled)

    def test_startup_no_growth_cancel_at60_not_first_sample(self):
        result,cancelled,elapsed = self.startup('no_growth')
        self.assertEqual(result['status'],'NOT_CONFIRMED')
        self.assertTrue(cancelled)
        self.assertEqual(elapsed,60)

    def test_startup_fatal_identity_no_wait(self):
        result,cancelled,elapsed = self.startup('identity')
        self.assertEqual(result['status'],'NOT_CONFIRMED')
        self.assertTrue(cancelled)
        self.assertEqual(elapsed,0)

    def test_sticky_abort_cannot_clear(self):
        abort = driver.fp.AbortLatch()
        abort.set()
        with self.assertRaises(RuntimeError):
            abort.clear()
        result = driver.SimpleNamespace(status='PASS',reason='')
        self.assertEqual(abort.accept(result).status,'CANCELLED')


if __name__ == '__main__':
    unittest.main()
