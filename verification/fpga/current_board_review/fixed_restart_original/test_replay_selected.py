"""Focused host negatives for the two-case replay gate; no simulations."""
import csv
from pathlib import Path
import re
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import replay_selected as r


class Gates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        name = 'fixed_e8_m4_pair775_776'
        self.entry = r.read(r.HERE / 'selected01/soc/programs.json')['programs'][name]
        self.entry['contexts'] = r.read(r.HERE / 'selected01' / name / 'scope.json')['selected_original_calls']
        for context in self.entry['contexts']: context['expected_vxsat'] = context['initial_vxsat']
        body = (r.HERE / 'selected01' / name / 'soc/program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        self.entry['helper'] = [dict(pc=int(m[1],16),insn=int(m[2],16)) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',body,re.M)]
        self.good = '\n'.join(self.entry['pass_markers'])+'\nFIXED_ORIGINAL_TRIAL index=775\nFIXED_ORIGINAL_TRIAL index=776\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'

    def trace(self, mutation=None):
        rows = []
        def row(pc, insn, rd=0, value=0):
            n=len(rows)
            rows.append(dict(cycle=n,event='retire',order=n,pc=f'{pc:x}',insn=f'{insn:x}',rd=rd,rd_wdata=f'{value:x}',trap=0))
        for context in self.entry['contexts']:
            for rd,value in ((13,512),(14,512),(16,context['vstart']),(17,context['control'])):
                row(0x70000000+4*rd,0x13,rd,value)
            for index,instruction in enumerate(self.entry['helper']):
                rd,value=0,0
                if index in (0,5,21): rd,value=5,512
                if index==8: rd,value=29,0
                if index==9: rd,value=30,0
                if index==10: rd,value=7,context['vxrm']
                if index==12: rd,value=7,context['initial_vxsat']
                if index==15: rd,value=10,0
                if index==16: rd,value=6,context['expected_vxsat']
                row(instruction['pc'],instruction['insn'],rd,value)
        if mutation: mutation(rows)
        path=self.root/'trace.csv'
        with path.open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        return path

    def test_exact_pair_csr_trace(self):
        self.assertEqual(r.check_trace(self.entry,self.trace())['target_count'],2)

    def test_wrong_start_rejected(self):
        with self.assertRaises(ValueError):
            r.check_trace(self.entry,self.trace(lambda rows:rows[2].update(rd_wdata='100')))

    def test_wrong_vxrm_rejected(self):
        with self.assertRaises(ValueError):
            r.check_trace(self.entry,self.trace(lambda rows:rows[14].update(rd_wdata='0')))

    def test_lost_sticky_rejected(self):
        with self.assertRaises(ValueError):
            r.check_trace(self.entry,self.trace(lambda rows:rows[20].update(rd_wdata='0')))

    def test_incomplete_second_call_rejected(self):
        with self.assertRaises(ValueError):
            r.check_trace(self.entry,self.trace(lambda rows:rows.pop()))

    def test_strict_raw_oracle_and_veto(self):
        self.assertTrue(r.strict_console(self.entry,self.good))
        for text in (self.good+'RVV_MATRIX_FAIL\n',self.good+'RVV_MATRIX_FAILED\n',self.good+'FIXED_SELECTION_FAIL\n',
                     self.good.replace('index=776','index=777'),self.good.replace('cases=2','cases=1')):
            self.assertFalse(r.strict_console(self.entry,text))

    def test_interrupted_pass_rows_rejected(self):
        r.save(self.root/'run.json',dict(status='INTERRUPTED',status_counts={'PASS':2}))
        r.save(self.root/'summary.json',[])
        with self.assertRaises(ValueError):r.terminal([],self.root)

    def test_exact_complete_positive(self):
        rows=[SimpleNamespace(name=n,status='PASS',returncode=0,artifact_dir=self.root/n) for n in r.NAMES]
        r.save(self.root/'run.json',dict(status='COMPLETE',status_counts={'PASS':2}))
        r.save(self.root/'summary.json',[dict(name=x.name,status=x.status,returncode=x.returncode,artifact_dir=str(x.artifact_dir)) for x in rows])
        r.terminal(rows,self.root)

    def test_abort_during_actual_trace_validation_vetoes_publication(self):
        abort=r.AbortLatch(); original=r.csv.DictReader
        def reader(*args,**kwargs):
            for i,row in enumerate(original(*args,**kwargs)):
                if i==20:abort.set()
                yield row
        path=self.trace()
        with patch.object(r.csv,'DictReader',reader):
            self.assertEqual(r.check_trace(self.entry,path)['target_count'],2)
        self.assertFalse(abort.publish(self.root/'complete.json',{},True))

    def test_pending_signal_rejects_pass(self):
        abort=r.AbortLatch()
        with abort.signals():
            previous=signal.pthread_sigmask(signal.SIG_BLOCK,r.SIGNALS)
            try:
                import os
                os.kill(os.getpid(),signal.SIGTERM)
                self.assertFalse(abort.publish(self.root/'complete.json',{},True))
            finally:signal.pthread_sigmask(signal.SIG_SETMASK,previous)

    def test_reserve23_and_reject25(self):
        units={k:'ara-test-'+k+'.service' for k in r.QUOTAS}
        self.assertEqual(r.resource_math([],32*1024**3,units)['total_live_plus_reserved'],23)
        self.assertEqual(r.resource_math([dict(cgroup='0::/external')],32*1024**3,units)['total_live_plus_reserved'],24)
        with self.assertRaises(ValueError):r.resource_math([dict(cgroup='0::/external')]*2,32*1024**3,units)


if __name__=='__main__':unittest.main()
