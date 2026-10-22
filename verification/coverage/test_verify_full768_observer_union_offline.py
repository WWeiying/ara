import copy
import inspect
import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest

import verify_full768_observer_union_offline as r


class ExactUnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=r.life.read_bound(r.OUT/'config.json',r.SEAL)
        cls.receipt=r.life.read_bound(r.launch.UNIT_RECEIPT,r.launch.UNIT_RECEIPT_SHA)
        cls.live=json.loads((r.OUT/'live-identity.json').read_bytes())
        cls.failure=json.loads((r.OUT/'failure.json').read_bytes())
        cls.log=(r.OUT/'service.log').read_text()
        cls.body=inspect.getsource(r.report.base.prior.old.frozen.prior.old.base.run)
        cls.fields=dict(Id=cls.receipt['unit'],ActiveState='failed',ExecMainCode='1',ExecMainStatus='1',
            ExecMainPID=str(cls.receipt['runner_pid']),
            ExecStart=str(Path(r.report.__file__).resolve())+' '+str(r.OUT)+' '+r.SEAL)

    def test_actual_all_five_stage_full_complement_and_exact_EL(self):
        proof=r.audit_observers(r.OUT,self.c)
        self.assertEqual(proof['unique_fields'],84)
        self.assertEqual(len(proof['exact_conflicts']),168)
        self.assertEqual({i['index'] for i in proof['exact_conflicts']},{3,5,10,11})
        self.assertEqual({i['stage'] for i in proof['exact_conflicts']},{'selected','reloaded'})
        self.assertEqual(proof['changed_EL_coordinates'],0)

    def test_actual_counter_not_new_accum_target(self):
        names={t['signal'] for i in self.c['new_families']['accum66']['config']['instances'] for t in i['targets']}
        self.assertNotIn('accumulator_updates_o',names)
        groups,proof=r.corrected_groups(self.c)
        self.assertTrue(any('accumulator_updates_o[31:0]' in p['labels'] for p in proof))

    def test_unknown_or_missing_annotation_rejected(self):
        text=(r.OUT/'applied.el').read_text()
        annotation=next(l for l in text.splitlines() if l.startswith('ANNOTATION:'))
        for changed in (text.replace(annotation,'ANNOTATION: "FOREIGN"'),text.replace(annotation,'')):
            with self.assertRaises(ValueError):r.export_partition(changed,self.c)

    def test_known_scope_foreign_checksum_empty_block_rejected(self):
        text=(r.OUT/'applied.el').read_text()
        scope,block=next(iter(r.report.base.prior.old.blocks(text)))
        changed=text+'\nCHECKSUM: "0 0"\nINSTANCE: '+scope+'\n'
        with self.assertRaises(ValueError):r.export_partition(changed,self.c)

    def test_changed_direction_rejected_by_original_canonical_parser(self):
        text=(r.OUT/'applied.el').read_text()
        line=next(l for l in text.splitlines() if l.startswith('Toggle 0to1 '))
        changed=text.replace(line,line.replace('0to1','1to0'),1)
        try:
            value=r.export_records(changed,self.c)
        except ValueError:
            return
        self.assertNotEqual(value,self.c['expected_union'])

    def test_partial_old_source_does_not_authorize_whole_flag(self):
        c=copy.deepcopy(self.c)
        i=next(i for i in c['diagnostic_config']['instances'] if i['scope'].endswith('.i_qbs_engine'))
        s=next(s for s in i['signals'] if s['name']=='accumulator_updates_o')
        s['bits']=list(range(31))
        groups,_=r.corrected_groups(c)
        group=next(g for g in groups.values() if g['scope']==i['scope'])
        self.assertNotIn(s['native_label'],group['targets'])
        with self.assertRaises(ValueError):r.audit_observers(r.OUT,c)

    def test_foreign_protected_flag_or_reset_flag_rejected(self):
        original=Path.open
        for stage,name in [('selected','clk_i'),('reset','accumulator_updates_o[31:0]')]:
            path=r.OUT/('observer766_%s_3.tsv'%stage)
            lines=path.read_text().splitlines();changed=False
            for index,line in enumerate(lines[1:],1):
                row=line.split('\t')
                if row[3]==name:row[4]='1';lines[index]='\t'.join(row);changed=True
            self.assertTrue(changed)
            text='\n'.join(lines)+'\n'
            def read(p,*args,**kwargs):
                if p==path:return io.StringIO(text)
                return original(p,*args,**kwargs)
            with self.subTest(stage=stage),patch.object(Path,'open',read),self.assertRaises(ValueError):
                r.audit_observers(r.OUT,self.c)

    def test_native_zero_guard_wrapper_one_kept_separate(self):
        proof=r.terminal_evidence(self.log,self.failure,self.live,self.receipt,self.body,self.fields)
        self.assertEqual(proof['launch_process_returncode'],0)
        self.assertEqual(proof['wrapper_OS_exit_status'],1)
        self.assertFalse(proof['standalone_DVE_OS_return_receipt_available'])
        for fields in [dict(self.fields,ExecMainStatus='0'),dict(self.fields,ActiveState='active')]:
            with self.assertRaises(ValueError):r.terminal_evidence(
                self.log,self.failure,self.live,self.receipt,self.body,fields)

    def test_wrong_failure_missing_guard_or_pid_rejected(self):
        cases=[(self.log,dict(reason='FOREIGN',no_retry=True),self.live,self.body),
               (self.log,self.failure,dict(self.live,pid=0),self.body),
               (self.log,self.failure,self.live,self.body.replace('require(code == 0','require(code != 0')),
               (self.log.replace('in audit_observers','in UNKNOWN'),self.failure,self.live,self.body)]
        for log,failure,live,body in cases:
            with self.assertRaises(ValueError):r.terminal_evidence(log,failure,live,self.receipt,body,self.fields)


if __name__=='__main__':unittest.main()
