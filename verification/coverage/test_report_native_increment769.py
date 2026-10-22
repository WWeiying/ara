import copy
import json
import tempfile
from pathlib import Path
import unittest
import report_native_increment769 as r


class IncrementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.extra=r.new_families()
        cls.old=r.life.read_bound(r.PREDECESSOR/'config.json',r.PREDECESSOR_SHA)

    def test_actual_new_source_bound_sets(self):
        self.assertEqual(len(self.extra['lzc23132']['canonical']),46264)
        self.assertEqual(len(self.extra['queue312']['canonical']),312)
        self.assertTrue(self.extra['lzc23132']['local_qualified'])
        self.assertFalse(self.extra['queue312']['local_qualified'])
        self.assertEqual(sum(map(len,self.extra['queue312']['reference'].values())),1360)

    def test_actual_complete_canonical_retained_union(self):
        c=copy.deepcopy(self.old);c['new_families'].update(self.extra)
        text=(r.PREDECESSOR/'combined.el').read_text()+''.join(i['el'] for i in self.extra.values())
        value=r.private_namespace()['records'](text,c)
        for key,item in self.extra.items():self.assertEqual(value.pop(key),item['canonical'])
        self.assertEqual(value,self.old['expected_union'])

    def test_actual_all_fields_shared_inventory_bijection(self):
        c=copy.deepcopy(self.old);c['new_families'].update(self.extra)
        groups=r.private_namespace()['merged_observers'](c)
        for key in self.extra:
            for scope,ref in self.extra[key]['reference'].items():
                found=[g for g in groups.values() if g['scope']==scope]
                self.assertEqual(len(found),1);self.assertEqual(sorted(found[0]['reference']),sorted(ref))

    def test_unqualified_predecessor_cannot_prepare(self):
        with self.assertRaises((ValueError,FileNotFoundError)):
            r.predecessor_gate(r.PREDECESSOR/'qualification.json','0'*64)

    def test_extra_queue_field_or_lzc_spare_rejected(self):
        item=self.extra['queue312'];bad=item['el']+'Toggle FOREIGN "logic FOREIGN"\n'
        with self.assertRaises(ValueError):r.queue.parse_el(bad,item['config'])
        item=self.extra['lzc23132'];c=copy.deepcopy(item['config'])
        for i in c['instances']:
            for s in i['signals']:
                if s['name']=='gen_lzc.sel_nodes':s['selected_dimensions']=s['dimensions']
        with self.assertRaises(ValueError):r.lzc_contract(c)

    def test_main_full_verifier_and_explicit_authorization(self):
        ns=r.namespace();self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        with self.assertRaises(ValueError):r.inherited.authorize(True,False)

    def test_actual_generated_increment_full_five_stage_host_hook(self):
        c=copy.deepcopy(self.old);c['new_families'].update(self.extra)
        ns=r.private_namespace();merged=ns['merged_observers'](c)
        text=(r.PREDECESSOR/'selection.tcl').read_text()+r.base.prior.selection_tail(dict(c,observer_captures=merged))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'selection.tcl';path.write_text(text)
            evidence=ns['host_hook'](path,c)
        self.assertEqual(evidence['stages'],list(r.base.prior.STAGES))
        self.assertFalse(evidence['EDA_launched'])

    def test_terminal_active_unknown_wrong_pid_rejected(self):
        receipt=r.life.read_bound(r.UNIT_RECEIPT,r.UNIT_RECEIPT_SHA)
        fields=dict(Id=receipt['unit'],LoadState='loaded',ActiveState='inactive',SubState='dead',
                    ExecMainCode='1',ExecMainStatus='0',ExecMainPID=str(receipt['runner_pid']),
                    ExecStart=str(r.inherited.HERE/'report_native_batch768_v3.py')+' '+str(r.PREDECESSOR)+' '+r.PREDECESSOR_SHA)
        result=r.check_real_terminal(fields,receipt)
        self.assertFalse(result['standalone_DVE_OS_receipt_available'])
        for k,v in [('LoadState','not-found'),('ActiveState','active'),('ExecMainStatus','1'),
                    ('ExecMainPID','0'),('ExecStart','FOREIGN')]:
            bad=dict(fields);bad[k]=v
            with self.subTest(field=k),self.assertRaises(ValueError):r.check_real_terminal(bad,receipt)


if __name__=='__main__':unittest.main()
