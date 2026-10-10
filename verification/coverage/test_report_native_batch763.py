import copy
import json
from pathlib import Path
import tempfile
import unittest

import report_native_batch763 as r


def fixture():
    q=r.life.read_bound(r.BASE/'qualification.json',r.BASE_SHA)
    c=r.life.read_bound(r.BASE/'config.json',q['config_seal'])
    c=copy.deepcopy(c);c['batch_captures']={}
    for key,(directory,sha,_) in r.CAPTURES.items():
        out=r.life.OUT/directory
        q=r.life.read_bound(out/'capture-result.json',sha)
        cfg=json.loads((out/'config.json').read_bytes())
        c['batch_captures'][key]=dict(config=cfg,qualification=q,seal=sha,output=str(out))
    r.append_groups(c)
    selection=(r.BASE/'selection.tcl').read_text()+r.selection_tail(c)
    text=(r.BASE/'applied.el').read_text()+''.join((Path(i['output'])/'first.el').read_text() for i in c['batch_captures'].values())
    return c,selection,text


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.c,cls.selection,cls.text=fixture()

    def test_all_sealed_qualification_gates(self):
        for key,item in self.c['batch_captures'].items():r.qualification_gates(key,item['qualification'])

    def test_actual_seven_capture_pin_fold_and_reload(self):
        captures,pins=r.captures()
        self.assertEqual(set(captures),set(r.CAPTURES))
        self.assertGreater(len(pins),500)
        for key,item in captures.items():self.assertEqual(item['seal'],r.CAPTURES[key][1])

    def test_unqualified_and_foreign_seals_rejected(self):
        for key,item in self.c['batch_captures'].items():
            q=copy.deepcopy(item['qualification']);q['status']='HOLD'
            with self.assertRaises(Exception):r.qualification_gates(key,q)

    def test_actual_combined_typed_partial_and_fsm_union(self):
        actual=r.records(self.text,self.c)
        self.assertEqual({k:len(v) for k,v in actual['batch'].items()},
                         dict(scalar22=22,scalar158=158,queue336=336,scale120=240,half816=816,parity=19328))
        prior=json.loads((r.BASE/'config.json').read_bytes())['expected_union']
        retained=copy.deepcopy(actual);del retained['batch']
        old=prior['retained']['prior']['original']['prior'][0]
        new=retained['retained']['prior']['original']['prior'][0]
        self.assertEqual(len(new),len(old)+2)
        retained['retained']['prior']['original']['prior'][0]=old
        self.assertEqual(retained,prior)

    def test_missing_whole_object_rejected(self):
        item=self.c['batch_captures']['scalar158']
        text=(Path(item['output'])/'first.el').read_text()
        line=next(line for line in text.splitlines() if line.startswith('Toggle '))
        with self.assertRaises(Exception):r.records(self.text.replace(line+'\n','',1),self.c)

    def test_extra_partial_bit_rejected(self):
        item=self.c['batch_captures']['parity'];i=item['config']['instances'][0];s=i['signals'][0]
        other=next((j for j in self.c['batch_captures']['scale120']['config']['instances'] if j['scope']==i['scope']))
        old=next((j['bits'] for j in other['signals'] if j['name']==s['name']),[])
        bit=next(b for b in range(s['left']+1) if b not in s['bits'] and b not in old)
        extra='CHECKSUM: "%s %s"\nINSTANCE: %s\nToggle 0to1 %s [%d]\n' % (i['design_module_checksum'],i['toggle_checksum'],i['scope'],s['name'],bit)
        with self.assertRaises(Exception):r.records(self.text+extra,self.c)

    def test_duplicate_partial_policy_rejected(self):
        c=copy.deepcopy(self.c)
        i=c['batch_captures']['scale120']['config']['instances'][0]
        p=next(j for j in c['batch_captures']['parity']['config']['instances'] if j['scope']==i['scope'])
        s=next(s for s in i['signals'] if any(t['name']==s['name'] for t in p['signals']))
        t=next(t for t in p['signals'] if t['name']==s['name']);t['bits'].append(s['bits'][0])
        with self.assertRaises(Exception):r.target_fields(c)

    def test_generated_proc_scope_all_stages_real_bracketed_scopes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'selection.tcl';path.write_text(self.selection)
            result=r.host_hook(path,self.c)
            self.assertEqual(result['stages'],list(r.old.STAGES))
            self.assertEqual(result['design_loads'],1)
            self.assertFalse(result['native_GUI_measured'])
        self.assertIn('set ::batch_scale_instances',self.selection)

    def test_existing_fsm_complement_preserved(self):
        old=json.loads((r.BASE/'config.json').read_bytes())['plan']
        self.assertEqual(self.c['plan']['targets'],old['targets']+2)
        self.assertEqual(self.c['plan']['protected'],old['protected']-2)
        self.assertEqual(len(self.c['plan']['groups']),len(old['groups']))
        changed=[a['raw_index'] for g,h in zip(old['groups'],self.c['plan']['groups']) for a,b in zip(g['rows'],h['rows']) if a!=b]
        self.assertEqual(changed,[23,47])

    def test_manifest_wrong_population_rejected(self):
        with self.assertRaises(Exception):r.population(self.c,r.MANIFEST,'0'*64)

    def test_actual_formal763_full6162_OR_and_design_no_testdata(self):
        ledger,selected,pins,admission=r.population(self.c,r.MANIFEST,r.MANIFEST_SHA)
        self.assertEqual(len(ledger),764)
        self.assertEqual(len(selected),763)
        self.assertTrue(admission['full6162_OR'])
        self.assertTrue(admission['exact762prefix'])
        self.assertGreater(len(pins),5000)
        self.assertFalse((Path(ledger[0])/'snps/coverage/db/testdata').exists())

    def test_private_substantive_namespace(self):
        ns=r.namespace()
        self.assertIs(ns['records'],r.records)
        self.assertIs(ns['check'],r.check)
        self.assertEqual(ns['TCL'],r.TCL)
        self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertEqual(r.old.frozen.prior.inherited.original_verify.__code__.co_filename.split('/')[-1],
                         'report_c910_combo742.py')


if __name__=='__main__':unittest.main()
