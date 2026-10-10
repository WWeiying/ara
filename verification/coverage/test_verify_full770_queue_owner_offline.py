import copy
import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest
import verify_full770_queue_owner_offline as r


class QueueOwner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=r.life.read_bound(r.OUT/'config.json',r.SEAL)
        cls.original=r.frozen.context()['private_namespace']()['merged_observers'](cls.c)
        cls.groups,cls.proof=r.corrected_groups(cls.c,cls.original)
        cls.log=(r.OUT/'service.log').read_text()
        cls.failure=json.loads((r.OUT/'failure.json').read_text())
        cls.live=json.loads((r.OUT/'live-identity.json').read_text())
        import inspect
        cls.body=inspect.getsource(r.frozen.closure.report.base.prior.old.frozen.prior.old.base.run)
        cls.fields=dict(Id=r.UNIT,LoadState='loaded',ActiveState='failed',SubState='failed',
            ExecMainCode='1',ExecMainStatus='1',ExecMainPID='252774',
            ExecStart=str(Path(r.frozen.__file__).resolve())+' run --output '+str(r.OUT)+' --seal '+r.SEAL)

    def test_exact_real_twenty_scopes_forty_scalars(self):
        self.assertEqual(len(self.proof),20)
        for item in self.proof:
            self.assertEqual(item['labels'],['cmd_pop_o','flush_i'])
            key=item['key']
            self.assertEqual(set(self.groups[key]['targets'])-set(self.original[key]['targets']),{'cmd_pop_o','flush_i'})
            self.assertNotIn('operand_queue_cmd_i.conv[3:0]',self.groups[key]['targets'])

    def test_all_actual_five_stage_flags_full_complement(self):
        r.frozen.closure.report.base.prior.audit_observers(r.OUT,dict(self.c,observer_captures=self.groups))

    def test_missing_direction_rejected(self):
        c=copy.deepcopy(self.c)
        rows=c['expected_union']['retained']['retained']['prior']['queue']
        scope=self.proof[0]['scope']
        rows.remove([scope,'cmd_pop_o',0,'1to0'])
        with self.assertRaises(ValueError):r.corrected_groups(c,self.original)

    def test_partial_or_wrong_port_rejected(self):
        for key,value in [('bits',[]),('scalar',False),('right',1)]:
            c=copy.deepcopy(self.c)
            instance=next(i for i in c['queue_config']['instances'] if i['scope']==self.proof[0]['scope'])
            next(s for s in instance['signals'] if s['name']=='cmd_pop_o')[key]=value
            with self.assertRaises(ValueError):r.corrected_groups(c,self.original)
        c=copy.deepcopy(self.c)
        c['queue_config']['instances'][0]['signals'][0]['shape']['portnode']='2'
        with self.assertRaises(ValueError):r.corrected_groups(c,self.original)

    def test_unknown_protected_and_reset_flags_rejected(self):
        original=Path.open
        index=self.proof[0]['index']
        for stage,name in [('selected','clk_i'),('reset','cmd_pop_o'),('final','flush_i')]:
            path=r.OUT/('observer766_%s_%d.tsv'%(stage,index))
            lines=path.read_text().splitlines();changed=False
            for n,line in enumerate(lines[1:],1):
                row=line.split('\t')
                if row[3]==name:row[4]='1';lines[n]='\t'.join(row);changed=True
            self.assertTrue(changed)
            text='\n'.join(lines)+'\n'
            def read(p,*args,**kwargs):
                if p==path:return io.StringIO(text)
                return original(p,*args,**kwargs)
            with patch.object(Path,'open',read),self.assertRaises(ValueError):
                r.frozen.closure.report.base.prior.audit_observers(r.OUT,dict(self.c,observer_captures=self.groups))

    def test_native_identity_drift_rejected(self):
        original=copy.deepcopy(self.original)
        original[self.proof[0]['key']]['reference'][0][1]='FOREIGN_META'
        with self.assertRaises(ValueError):r.corrected_groups(self.c,original)

    def test_real_wrapper_one_not_fabricated_zero(self):
        proof=r.terminal_evidence(self.log,self.failure,self.live,self.body,self.fields)
        self.assertEqual(proof['launch_process_returncode'],0)
        self.assertEqual(proof['wrapper_OS_exit_status'],1)
        self.assertFalse(proof['standalone_DVE_OS_return_receipt_available'])
        for fields in [dict(self.fields,ExecMainStatus='0'),dict(self.fields,ActiveState='active'),
                       dict(self.fields,ExecMainPID='0')]:
            with self.assertRaises(ValueError):r.terminal_evidence(self.log,self.failure,self.live,self.body,fields)

    def test_wrong_failure_or_missing_zero_guard_rejected(self):
        with self.assertRaises(ValueError):r.terminal_evidence(self.log,dict(reason='FOREIGN',no_retry=True),self.live,self.body,self.fields)
        with self.assertRaises(ValueError):r.terminal_evidence(self.log,self.failure,self.live,self.body.replace('require(code == 0','require(code != 0'),self.fields)


if __name__=='__main__':unittest.main()
