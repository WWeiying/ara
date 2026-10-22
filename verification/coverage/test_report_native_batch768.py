import copy
import csv
import json
import tempfile
from pathlib import Path
import unittest
import report_native_batch768 as r


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=json.loads((r.BASE/'config.json').read_bytes())
        cls.c['new_families']=r.additions(True,
            r.life.OUT/'requester-read108-native767-agent-20261007-01/capture-result.json',
            'a31abca542924c82f51f53e4e2c5ed17b22c3476eae035ecdccd5f355dbe749b')
        cls.text=(r.BASE/'combined.el').read_text()+''.join(i['el'] for i in cls.c['new_families'].values())

    def test_actual_source_candidate_and_qualified_cause(self):
        self.assertFalse(self.c['new_families']['csr1193']['local_qualified'])
        self.assertTrue(self.c['new_families']['cause']['local_qualified'])
        self.assertEqual(len(self.c['new_families']['csr1193']['canonical']),2386)
        self.assertEqual(len(self.c['new_families']['cause']['canonical']),1486)
        self.assertEqual(len(self.c['new_families']['read108']['canonical']),108)

    def test_actual_canonical_complete_retained_union(self):
        value=r.records(self.text,self.c)
        for key in self.c['new_families']:
            self.assertEqual(value.pop(key),self.c['new_families'][key]['canonical'])
        self.assertEqual(value,self.c['expected_union'])

    def test_actual_native_saved_semantic_roundtrip_preserves_observer_annotations(self):
        text=(r.BASE/'reloaded.el').read_text()+''.join((Path(i['output'])/'second.el').read_text()
             for i in self.c['new_families'].values())
        self.assertEqual(r.records(text,self.c),r.records(self.text,self.c))
        retained=r.partition(self.text,self.c)['retained']
        original_blocks=dict(r.prior.old.blocks((r.BASE/'combined.el').read_text()))
        for scope,block in r.prior.old.blocks(retained):
            if 'Integration scope: observation-only' in block:
                self.assertEqual(block,original_blocks[scope])

    def test_actual_native_labels_and_partial_flag_boundary(self):
        item=self.c['new_families']['csr1193'];scope=item['config']['scope']
        self.assertEqual(len(item['native_targets'][scope]),46)
        self.assertIn('mip_q[63:0]',item['native_targets'][scope])
        self.assertNotIn('mip_q[63:0]',item['targets'][scope])
        self.assertIn('mtvt_q[63:0]',item['targets'][scope])
        self.assertEqual(sum(map(len,self.c['new_families']['read108']['targets'].values())),108)

    def test_source_retained_low_cause_rejected(self):
        item=self.c['new_families']['cause']
        text=item['el'];line=next(s for s in text.splitlines() if '.cause [' in s)
        with self.assertRaises(Exception):r.cause.records(text.replace(line,line.replace('[4]', '[0]'),1)
            if '[4]' in line else text+'Toggle foreign "logic foreign"\n',item['config'])

    def test_native_wrong_checksum_rejected(self):
        item=self.c['new_families']['csr1193']
        with self.assertRaises(Exception):r.csr.records(item['el'].replace('CHECKSUM: "','CHECKSUM: "0',1),item['config'])

    def test_missing_read_qualification_rejected(self):
        with self.assertRaises(Exception):r.additions(False,Path('/not/a/qualification.json'),'0'*64)

    def test_actual_generated_five_stage_hook(self):
        selection=(r.BASE/'selection.tcl').read_text()+r.prior.selection_tail(
            dict(self.c,observer_captures=r.merged_observers(self.c)))
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'selection.tcl';p.write_text(selection)
            self.assertFalse(r.host_hook(p,self.c)['EDA_launched'])

    def test_complete_complement_and_protected_flag_reject(self):
        observers=r.merged_observers(self.c)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for index,item in enumerate(observers.values()):
                for stage in r.prior.STAGES:
                    with (out/('observer766_%s_%d.tsv'%(stage,index))).open('w') as stream:
                        writer=csv.writer(stream,delimiter='\t');writer.writerow(['handle','path','meta','name','excluded'])
                        for handle,row in enumerate(item['reference'],1):
                            writer.writerow([handle,*row,int(stage in ('selected','reloaded') and row[2] in item['targets'])])
            r.audit_observers(out,self.c)
            index=len(observers)-1;item=list(observers.values())[-1]
            p=out/('observer766_selected_%d.tsv'%index)
            with p.open() as stream:rows=list(csv.reader(stream,delimiter='\t'))
            next(row for row in rows[1:] if row[3] not in item['targets'])[-1]='1'
            with p.open('w') as stream:csv.writer(stream,delimiter='\t').writerows(rows)
            with self.assertRaises(Exception):r.audit_observers(out,self.c)

    def test_actual768_population(self):
        ledger,selected,_=r.population(self.c)
        self.assertEqual(ledger[:-2],self.c['input_ledger'])
        self.assertEqual(len(set(selected)),768)

    def test_full6162_or_and_lost_hit_rejected(self):
        before=dict(tests=[str(i) for i in range(767)],design='x',metrics={'line':{
            str(i):dict(width=2,checksum='1',bits='1') for i in range(6162)}})
        after=copy.deepcopy(before);after['tests'].append('new')
        one=copy.deepcopy(after);one['tests']=['new']
        r.full_or(before,after,one,768)
        after['metrics']['line']['0']['bits']='0'
        with self.assertRaises(Exception):r.full_or(before,after,one,768)

    def test_runtime_substantive_complement_checks_retained(self):
        ns=r.namespace()
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('prior',r.snapshot_stdout.__code__.co_names)


if __name__=='__main__':unittest.main()
