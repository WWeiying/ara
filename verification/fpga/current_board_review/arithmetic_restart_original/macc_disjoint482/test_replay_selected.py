"""Offline acceptance negatives; synthetic CSV tests are not DUT evidence."""
import copy
import csv
import os
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import replay_selected as r


class Gates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.entry = r.entries()['macc_e8_m4_pair480_481']
        self.good = '\n'.join(['BOARD_CASE_BEGIN macc_e8_m4_pair480_481', *self.entry['pass_markers'],
            'MACC_ORIGINAL_TRIAL index=480', 'MACC_ORIGINAL_TRIAL index=481',
            'Core Test *** SUCCESS *** (tohost = 0)', '$finish']) + '\n'

    def trace(self, mutation=None):
        rows = []
        def row(pc, insn, rd=0, value=0):
            n = len(rows)
            rows.append(dict(cycle=n, event='retire', order=n, pc=f'{pc:x}', insn=f'{insn:x}',
                             rd=rd, rd_wdata=f'{value:x}', trap=0))
        for context in self.entry['contexts']:
            pointers = self.entry['operand_addresses']
            for rd, value in zip(range(10,18), [*pointers[:3],512,512,pointers[3],context['vstart'],0]):
                row(0x70000000 + rd*4, 0x13, rd, value)
            for index, instruction in enumerate(self.entry['helper']):
                rd, value = (5,512) if index in (0,5,10) else (28,0) if index == 6 else (10,0) if index == 9 else (0,0)
                row(instruction['pc'], instruction['insn'], rd, value)
        if mutation: mutation(rows)
        path = self.root / 'trace.csv'
        with path.open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        return path

    def test_exact_pair_trace(self):
        audit = r.check_trace(self.entry, self.trace())
        self.assertEqual([x['original_trial'] for x in audit['contexts']], [480,481])
        self.assertEqual(audit['target_count'],2)

    def test_bad_start(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[6].update(rd_wdata='100')))

    def test_bad_operand_pointer(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[0].update(rd_wdata='0')))

    def test_bad_vl(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[8].update(rd_wdata='100')))

    def test_bad_target(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[16].update(insn='13')))

    def test_bad_scalar_load(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[14].update(rd_wdata='1')))

    def test_bad_return_high32(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x[17].update(rd_wdata='100000000')))

    def test_trap_and_missing_order(self):
        for field, value in (('trap',1),('order',7)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                r.check_trace(self.entry, self.trace(lambda x:x[16].update({field:value})))

    def test_missing_final_instruction(self):
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(lambda x:x.pop()))

    def test_extra_call(self):
        def mutate(rows):
            additional = copy.deepcopy(rows[:21])
            for n, row in enumerate(additional, len(rows)): row.update(cycle=n,order=n)
            rows.extend(additional)
        with self.assertRaises(ValueError): r.check_trace(self.entry, self.trace(mutate))

    def test_raw_oracle_veto(self):
        self.assertTrue(r.strict_console(self.entry,self.good))
        for bad in ('RVV_MATRIX_FAIL','RVV_MATRIX_FAILED','MACC_SELECTION_FAIL','BOARD_REPLAY_TRAP','fatal',
                    'RVV_MATRIX_UNSUPPORTED_CAPACITY'):
            with self.subTest(bad=bad): self.assertFalse(r.strict_console(self.entry,self.good+bad+'\n'))

    def test_wrong_or_missing_marker(self):
        for before, after in (('cases=2','cases=482'),('index=481','index=480'),('BOARD_REPLAY_PASS',''),
                              ('errors=0','errors=1'),('BOARD_CASE_BEGIN','WRONG_BEGIN')):
            with self.subTest(before=before): self.assertFalse(r.strict_console(self.entry,self.good.replace(before,after)))
        self.assertFalse(r.strict_console(self.entry,self.good+'BOARD_REPLAY_PASS\n'))

    def test_exact_terminal_and_exit(self):
        results = [SimpleNamespace(name=n,status='PASS',returncode=0,artifact_dir=self.root/n) for n in r.NAMES]
        r.save(self.root/'run.json',dict(status='COMPLETE',status_counts={'PASS':2},tests=sorted(r.NAMES)))
        rows = [dict(name=x.name,status=x.status,returncode=x.returncode,artifact_dir=str(x.artifact_dir)) for x in results]
        r.save(self.root/'summary.json',rows); r.terminal(results,self.root)
        results[0].returncode = 1
        with self.assertRaises(ValueError): r.terminal(results,self.root)

    def test_incomplete_terminal(self):
        r.save(self.root/'run.json',dict(status='INTERRUPTED',status_counts={'PASS':2},tests=sorted(r.NAMES)))
        r.save(self.root/'summary.json',[])
        with self.assertRaises(ValueError): r.terminal([],self.root)

    def test_resources_replace_not_add(self):
        self.assertEqual(r.resource_math([],32*1024**3,r.UNITS)['total_live_plus_reserved'],23)
        live = [dict(cgroup='0::/user.slice/'+r.FIXED_UNIT)]
        with self.assertRaises(ValueError): r.resource_math(live,64*1024**3,r.UNITS)
        self.assertEqual(r.resource_math([dict(cgroup='0::/external')],32*1024**3,r.UNITS)['total_live_plus_reserved'],24)
        with self.assertRaises(ValueError): r.resource_math([dict(cgroup='0::/external')]*2,64*1024**3,r.UNITS)

    def test_wrong_fpmerge_and_low_memory(self):
        units = dict(r.UNITS,fpmerge='ara-wrong.service')
        with self.assertRaises(ValueError): r.resource_math([],64*1024**3,units)
        with self.assertRaises(ValueError): r.resource_math([],31*1024**3,r.UNITS)

    def test_fixed_parent_decision_required(self):
        review = dict(fixed_disposition='PENDING',fixed_terminal_parent_reviewed=False,
                      fixed_plan_sha256=r.FIXED_PLAN_SHA,units=r.UNITS)
        with self.assertRaises(ValueError): r.fixed_disposition(review)
        review.update(fixed_disposition='ACCEPTED_PASS',fixed_terminal_parent_reviewed=True)
        self.assertEqual(r.fixed_disposition(review),'ACCEPTED_PASS')
        review['fixed_disposition'] = 'FAILURE_HOLD'
        with self.assertRaises(ValueError): r.fixed_disposition(review)
        review['fixed_failure_reason'] = 'Explicit parent timeout hold; not data acceptance'
        self.assertEqual(r.fixed_disposition(review),'FAILURE_HOLD')

    def test_missing_terminal_evidence_not_service_absence(self):
        review = dict(fixed_disposition='ACCEPTED_PASS',fixed_terminal_parent_reviewed=True,
                      fixed_plan_sha256=r.FIXED_PLAN_SHA,units=r.UNITS,fixed_evidence={})
        with patch.object(r.shared.dependency,'query_unit') as query:
            with self.assertRaises(ValueError): r.fixed_gate(review)
            query.assert_not_called()

    def test_active_fixed_service_rejected(self):
        response = SimpleNamespace(returncode=0,stderr='',stdout='\n'.join([
            'Id='+r.FIXED_UNIT,'LoadState=loaded','ActiveState=active','SubState=running',
            'MainPID=12','ControlPID=0','ControlGroup=/user.slice/'+r.FIXED_UNIT]))
        with self.assertRaises(ValueError): r.shared.dependency.parse_unit(r.FIXED_UNIT,response)

    def test_abort_during_trace_vetoes_publication(self):
        abort = r.AbortLatch(); original = r.csv.DictReader
        def reader(*args,**kwargs):
            for i,row in enumerate(original(*args,**kwargs)):
                if i == 12: abort.set()
                yield row
        path = self.trace()
        with patch.object(r.csv,'DictReader',reader): self.assertEqual(r.check_trace(self.entry,path)['target_count'],2)
        self.assertFalse(abort.publish(self.root/'complete.json',{},True))

    def test_pending_signal_rejects_pass(self):
        abort = r.AbortLatch()
        with abort.signals():
            previous = signal.pthread_sigmask(signal.SIG_BLOCK,r.SIGNALS)
            try:
                os.kill(os.getpid(),signal.SIGTERM)
                self.assertFalse(abort.publish(self.root/'complete.json',{},True))
            finally: signal.pthread_sigmask(signal.SIG_SETMASK,previous)

    def test_publication_success_once(self):
        abort = r.AbortLatch()
        self.assertTrue(abort.publish(self.root/'complete.json',{},True))
        with self.assertRaises(ValueError): abort.publish(self.root/'complete.json',{},True)


if __name__ == '__main__': unittest.main()
