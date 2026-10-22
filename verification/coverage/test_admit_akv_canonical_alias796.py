import copy
import unittest
import admit_akv_canonical_alias796 as a


class Admission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=a.life.read_bound(a.QUAL/'qualification.json',a.Q_SHA)
        cls.receipt=a.life.read_bound(a.QUAL/'sd-successor-receipt.json',a.RECEIPT_SHA)
        cls.base=a.life.read_bound(a.BASE/'admission-manifest.json',a.BASE_SHA)
        def previous(n):return a.life.read_bound(a.BASE/n,cls.base['output_pins'][str(a.BASE/n)])
        cls.before=previous('combined-bits.json');cls.bt=previous('combined-toggle-bits.json')
        cls.single=a.life.read_bound(a.QUAL/'single-bits.json',cls.q['output_pins'][str(a.QUAL/'single-bits.json')])
        cls.st=a.life.read_bound(a.QUAL/'single-toggle-bits.json',cls.q['output_pins'][str(a.QUAL/'single-toggle-bits.json')])

    def test_actual_dual_seal_qualified(self):a.qualification(self.q,self.receipt)

    def test_wrong_core_or_receipt_scope(self):
        for key,value in (('core_sha256','0'*64),('scope','Only MSTATUS'),('fields_masked',['SD']),('skipped_retirements',True),('coverage_admitted',True)):
            bad=dict(self.receipt,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):a.qualification(self.q,bad)

    def test_successor_test_pin_missing(self):
        bad=copy.deepcopy(self.receipt)
        key=next(k for k in bad['successor_pins'] if k.endswith('test_akv_canonical_alias794_sd_v2.py'))
        del bad['successor_pins'][key]
        with self.assertRaises(ValueError):a.qualification(self.q,bad)

    def test_receipt_pin_closure_not_subset(self):
        bad=copy.deepcopy(self.receipt);key=next(iter(self.q['output_pins']));del bad['input_pins'][key]
        with self.assertRaises(ValueError):a.qualification(self.q,bad)

    def test_custom_Spike_false_only(self):
        bad=dict(self.q,native_custom_Spike=True)
        with self.assertRaises(ValueError):a.qualification(bad,self.receipt)

    def test_actual_complete6162_OR_795prefix(self):
        after=a.full_union(self.before,self.single)
        self.assertEqual(after['tests'][:-1],self.before['tests']);self.assertEqual(len(after['tests']),796)
        self.assertEqual(sum(len(x) for x in after['metrics'].values()),6162)

    def test_duplicate_candidate(self):
        bad=copy.deepcopy(self.before);bad['tests'][-1]=str(a.RUN/'code.vdb')
        with self.assertRaises(ValueError):a.full_union(bad,self.single)

    def test_missing_old_member(self):
        bad=copy.deepcopy(self.before);bad['tests'].pop()
        with self.assertRaises(ValueError):a.full_union(bad,self.single)

    def test_shape_and_scope_drift(self):
        for mode in ('shape','scope'):
            bad=copy.deepcopy(self.single);key=next(iter(bad['metrics']['line']))
            if mode=='shape':bad['metrics']['line'][key]['checksum']='foreign'
            else:del bad['metrics']['line'][key]
            with self.subTest(mode=mode),self.assertRaises(ValueError):a.full_union(self.before,bad)

    def test_actual2989_OR_and_targets(self):
        after=a.c.case.old.toggle.union(self.bt,self.st);a.toggle_union.all_toggle_or(self.bt,self.st,after)
        m=a.life.read_bound(a.RUN/'manifest.json',a.RUN_SHA)
        targets=a.target_gain(self.bt,after,m['targets'])
        self.assertEqual(len(targets),13)
        self.assertEqual(sum(len(x['full_coordinates']) for x in targets),1664)
        self.assertGreater(sum(len(x['gained']) for x in targets),0)

    def test_Toggle_OR_dropped_hit(self):
        after=a.c.case.old.toggle.union(self.bt,self.st);key=next(k for k,v in after.items() if int(v['bits'],16))
        after[key]['bits']='0x0'
        with self.assertRaises(ValueError):a.toggle_union.all_toggle_or(self.bt,self.st,after)

    def test_target_coordinate_truncation(self):
        m=a.life.read_bound(a.RUN/'manifest.json',a.RUN_SHA);targets=copy.deepcopy(m['targets']);targets['fields'][0]['full_coordinates'].pop()
        with self.assertRaises(ValueError):a.target_gain(self.bt,a.c.case.old.toggle.union(self.bt,self.st),targets)

    def test_zero_latest_gain_rejected(self):
        with self.assertRaises(ValueError):a.positive(dict(metrics=dict(line=0,cond=0,branch=0,fsm=0)),{'scope':[]})

    def test_actual_history795_ELF_dedup(self):
        ledger=(a.BASE/'combined-inputs.txt').read_text().splitlines()
        authority=a.life.merge_pins(self.base['input_pins'],self.base['output_pins'])
        audit=a.historical(self.base,ledger,authority,self.q['input_pins'][str(a.runner.ELF)])
        self.assertEqual(audit['ledger_members'],795)
        self.assertEqual([x['vdb'] for x in audit['members']],ledger[1:])

    def test_history_duplicate_ELF_rejected(self):
        ledger=(a.BASE/'combined-inputs.txt').read_text().splitlines();authority=a.life.merge_pins(self.base['input_pins'],self.base['output_pins'])
        old=a.life.read_bound(a.BASE/'elf-ledger-dedup.json',self.base['output_pins'][str(a.BASE/'elf-ledger-dedup.json')])
        digest=next(iter(old['members'][0]['ELF_candidates'].values()))
        with self.assertRaises(ValueError):a.historical(self.base,ledger,authority,digest)


if __name__=='__main__':unittest.main()
