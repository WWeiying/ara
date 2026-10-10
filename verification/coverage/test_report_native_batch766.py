import copy
import csv
import json
import tempfile
from pathlib import Path
import unittest
import report_native_batch766 as report


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((report.BASE/'config.json').read_bytes())
        cls.additions, _ = report.captures()
        cls.c = copy.deepcopy(cls.original)
        cls.c['observer_captures'] = cls.additions
        cls.text = (report.BASE/'combined.el').read_text()+''.join(
            (Path(i['output'])/'first.el').read_text() for i in cls.additions.values())

    def test_actual_canonical_union_retains_all765(self):
        union = report.records(self.text,self.c)
        self.assertEqual(len(union.pop('rvfi788')),788)
        self.assertEqual(len(union.pop('cva6rvfi457')),457)
        self.assertEqual(len(union.pop('pmp770')),770)
        self.assertEqual(union,self.original['expected_union'])

    def test_full_complement_and_exact_targets(self):
        self.assertEqual([(len(i['reference']),len(i['targets'])) for i in self.additions.values()],
                         [(1206,788),(1772,457),(2077,770)])

    def test_unqualified_status_rejected(self):
        q=copy.deepcopy(self.additions['rvfi788']['qualification']);q['semantic_reload']=False
        with self.assertRaises(Exception):report.observers.qualification_gate(q,self.additions['rvfi788']['config'])

    def test_actual_generated_five_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'selection.tcl'
            p.write_text((report.BASE/'selection.tcl').read_text()+report.selection_tail(self.c))
            self.assertFalse(report.host_hook(p,self.c)['EDA_launched'])

    def test_full_or_and_lost_prefix_rejected(self):
        before=dict(tests=[str(i) for i in range(765)],design='x',metrics={'cond':{}})
        before['metrics']['cond']={str(i):dict(width=2,checksum='a',bits='1') for i in range(6162)}
        bits=copy.deepcopy(before);bits['tests'].append('new')
        one=copy.deepcopy(bits);one['tests']=['new']
        report.full_or(before,bits,one)
        bits['metrics']['cond']['0']['bits']='0'
        with self.assertRaises(Exception):report.full_or(before,bits,one)

    def test_actual_population_authority(self):
        ledger,selected,_=report.population(self.original)
        self.assertEqual(ledger[:-1],self.original['input_ledger'])
        self.assertEqual(len(set(selected)),766)

    def test_runtime_substantive_audits_preserved(self):
        ns=report.namespace()
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)

    def test_complete_readback_rejects_protected_exclusion_and_missing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            for index,item in enumerate(self.additions.values()):
                for stage in report.STAGES:
                    with (out/('observer766_%s_%d.tsv'%(stage,index))).open('w') as f:
                        writer=csv.writer(f,delimiter='\t')
                        writer.writerow(['handle','path','meta','name','excluded'])
                        for handle,row in enumerate(item['reference'],1):
                            writer.writerow([handle,*row,int(stage in ('selected','reloaded') and row[2] in item['targets'])])
            report.audit_observers(out,self.c)
            p=out/'observer766_selected_0.tsv'
            with p.open() as f:rows=list(csv.reader(f,delimiter='\t'))
            protected=next(r for r in rows[1:] if r[3] not in self.additions['rvfi788']['targets'])
            protected[-1]='1'
            with p.open('w') as f:csv.writer(f,delimiter='\t').writerows(rows)
            with self.assertRaises(Exception):report.audit_observers(out,self.c)
            protected[-1]='0'
            with p.open('w') as f:csv.writer(f,delimiter='\t').writerows(rows[:-1])
            with self.assertRaises(Exception):report.audit_observers(out,self.c)


if __name__=='__main__':unittest.main()
