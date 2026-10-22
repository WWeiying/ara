import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import admit_itlb_ppn_aba794 as a


def qualification(directory):
    return dict(status='ITLB_PPN_ABA792_ARCHITECTURE_ACTUAL16_SLOT_QUALIFIED_NOT_ADMITTED',
        baseline=792,software_checks=3846,coverage_admitted=False,official_percentage=False,
        toggle_new_positions=10,target_new_positions=8,
        output_pins={str(directory/n):'sealed' for n in a.REQUIRED})


class Gates(unittest.TestCase):
    def test_exact_successful_qualification(self):
        a.qualification_gate(qualification(a.life.OUT/'qualified'),a.life.OUT/'qualified')

    def test_only_actual_independently_reviewed_v2_qualification(self):
        for directory,seal in ((a.QUALIFIED,'foreign'),(a.life.OUT/'foreign',a.QUALIFIED_SHA)):
            with self.assertRaisesRegex(ValueError,'reviewed complete v2'):
                a.evaluate(directory,seal)

    def test_actual_six_CSR_evidence_required_and_pinned(self):
        q=a.life.read_bound(a.QUALIFIED/'qualification.json',a.QUALIFIED_SHA)
        p=a.QUALIFIED/'console-csr-contract.json'
        c=a.life.read_bound(p,q['output_pins'][str(p)])
        self.assertEqual(c['summary']['requests'],6)
        self.assertEqual(c['summary']['responses'],6)
        self.assertEqual(len(c['lifecycle']['records']),6)
        self.assertTrue(c['zero_vector_writes'])
        self.assertEqual(q['input_pins'][str(Path(a.__file__).with_name('collect_itlb_ppn_aba_v2.py').resolve())],a.SUCCESSOR_SHA)

    def test_failed_or_wrong_qualification_rejected(self):
        directory=a.life.OUT/'qualified'
        for key,value in [('status','HOLD'),('baseline',793),('software_checks',True),
                          ('coverage_admitted',True),('official_percentage',True),
                          ('toggle_new_positions',True),('target_new_positions',-1)]:
            q=qualification(directory);q[key]=value
            with self.assertRaises(ValueError):a.qualification_gate(q,directory)

    def test_missing_each_required_output_rejected(self):
        directory=a.life.OUT/'qualified'
        for name in a.REQUIRED:
            q=qualification(directory);del q['output_pins'][str(directory/name)]
            with self.assertRaises(ValueError):a.qualification_gate(q,directory)

    def test_exact793_prefix(self):
        before={'tests':['/test/'+str(i) for i in range(793)]}
        ledger=['/design',*before['tests']]
        a.prefix(before,ledger,ledger[:793])

    def test_same_count_foreign_reordered_or_duplicate_ledger(self):
        before={'tests':['/test/'+str(i) for i in range(793)]};ledger=['/design',*before['tests']]
        for index,value in [(4,'/foreign'),(2,ledger[1]),(0,'/different-design')]:
            bad=ledger.copy();bad[index]=value
            with self.assertRaises(ValueError):a.prefix(before,bad,ledger[:793])
        bad=ledger.copy();bad[1],bad[2]=bad[2],bad[1]
        with self.assertRaises(ValueError):a.prefix(before,bad,ledger[:793])

    def test_actual793_sealed_status_full_prefix_and_OR(self):
        base=a.life.read_bound(a.BASE/'admission-manifest.json',a.BASE_SHA)
        def read(name):
            p=a.BASE/name;return a.life.read_bound(p,base['output_pins'][str(p)])
        before=read('combined-bits.json');status=read('status.json')
        _,_,original,pins=a.case.baseline()
        ledger=(a.BASE/'combined-inputs.txt').read_text().splitlines()
        a.prefix(before,ledger,original)
        self.assertEqual(status['aggregate_passed'],793)
        singleton=copy.deepcopy(before);singleton['tests']=['/new/candidate/code.vdb']
        for rows in singleton['metrics'].values():
            for row in rows.values():row['bits']='0x0'
        after=a.full_union(before,singleton,Path(singleton['tests'][0]))
        self.assertEqual(after['tests'][:793],before['tests'])
        self.assertEqual(after['metrics'],before['metrics'])
        self.assertEqual(sum(len(v) for v in after['metrics'].values()),6162)

    def small_metric_fixture(self):
        counts={m:1 for m in a.COUNTS}
        row={'width':4,'checksum':'sealed','bits':'0x3'}
        before=dict(design={'shape':'hash'},tests=['/historical'],input_hashes={},
                    metrics={m:{'ara_tb.dut.i_ara_soc.i_system.scope':dict(row)} for m in counts})
        single=copy.deepcopy(before);single['tests']=['/candidate'];single['metrics']['line'][next(iter(single['metrics']['line']))]['bits']='0xc'
        return counts,before,single

    def test_OR_exact_not_count_equivalence(self):
        counts,before,single=self.small_metric_fixture()
        with patch.object(a,'COUNTS',counts):
            after=a.full_union(before,single,Path('/candidate'))
            self.assertEqual(next(iter(after['metrics']['line'].values()))['bits'],'0xf')
            with patch.object(a.bitmap,'combine',return_value=copy.deepcopy(before)):
                with self.assertRaises(ValueError):a.full_union(before,single,Path('/candidate'))

    def test_wrong_width_checksum_instance_metric_or_overflow(self):
        for kind in ('width','checksum','scope','metric','overflow'):
            counts,before,single=self.small_metric_fixture();scope=next(iter(single['metrics']['line']))
            if kind=='width':single['metrics']['line'][scope]['width']=5
            elif kind=='checksum':single['metrics']['line'][scope]['checksum']='foreign'
            elif kind=='scope':single['metrics']['line']['foreign']=single['metrics']['line'].pop(scope)
            elif kind=='metric':del single['metrics']['fsm']
            else:single['metrics']['line'][scope]['bits']='0x10'
            with patch.object(a,'COUNTS',counts):
                with self.assertRaises(ValueError):a.full_union(before,single,Path('/candidate'))

    def test_duplicate_vdb_or_foreign_singleton(self):
        counts,before,single=self.small_metric_fixture()
        for names in (['/historical'],['/foreign'],['/candidate','/extra']):
            single['tests']=names
            with patch.object(a,'COUNTS',counts):
                with self.assertRaises(ValueError):a.full_union(before,single,Path('/candidate'))

    def test_Toggle_rebase_deducts_suffix_and_preserves_complement(self):
        scope=a.case.SCOPE
        before={scope:dict(width=8,checksum='817233724',bits='0x80'),
                'protected':dict(width=2,checksum='other',bits='0x1')}
        added={scope:dict(width=8,checksum='817233724',bits='0xc0'),
               'protected':dict(width=2,checksum='other',bits='0x3')}
        after,gain=a.rebase(before,added)
        self.assertEqual(gain['new_serialized_positions'],[1])
        self.assertEqual(after['protected']['bits'],'0x3')
        self.assertTrue(gain['historical792_gain_not_recounted'])
        self.assertFalse(gain['direction_order_calibrated'])
        self.assertFalse(gain['official_percentage'])

    def test_zero_gain_or_foreign_Toggle_identity(self):
        before={a.case.SCOPE:dict(width=8,checksum='817233724',bits='0x80')}
        for row in (dict(before[a.case.SCOPE]),dict(width=8,checksum='foreign',bits='0xc0'),
                    dict(width=9,checksum='817233724',bits='0xc0')):
            with self.assertRaises(ValueError):a.rebase(before,{a.case.SCOPE:row})

    def test_historical_only_dedup_argument_and_complete_authority(self):
        ledger=['/design',*['/historical/'+str(i) for i in range(793)]]
        authority={'/historical/receipt':'sealed'}
        result=dict(ledger_members=793,duplicate=False,members=[{'vdb':v} for v in ledger[1:]],
                    pins=dict(authority))
        with patch.object(a,'dedup',return_value=result) as invoke:
            a.historical_dedup(ledger,a.ELF_SHA,authority)
            invoke.assert_called_once_with(ledger,a.ELF_SHA,authority)

    def test_dedup_candidate_receipt_cannot_own_history(self):
        ledger=['/design',*['/historical/'+str(i) for i in range(793)]]
        result=dict(ledger_members=793,duplicate=False,members=[{'vdb':v} for v in ledger[1:]],
                    pins={'/candidate/receipt':'not-historical'})
        with patch.object(a,'dedup',return_value=result):
            with self.assertRaises(ValueError):a.historical_dedup(ledger,a.ELF_SHA,{'/history':'sealed'})

    def test_dedup_true_duplicate_never_ignored(self):
        with patch.object(a,'dedup',side_effect=ValueError('Duplicate historical ELF')):
            with self.assertRaisesRegex(ValueError,'Duplicate'):a.historical_dedup([],a.ELF_SHA,{})

    def test_prepared_fixed_ELF_and_service(self):
        r=a.life.read_bound(a.PREPARED,a.PREPARED_SHA)
        a.runner.validate(r)
        elf=Path(r['preflight']).parent/'input.elf'
        self.assertEqual(r['pins'][str(elf)],a.ELF_SHA)
        self.assertEqual(r['service'],'ara-itlb-ppn-aba792-parent-20261008-01.service')

    def test_cli_has_no_simulator_or_model_entry(self):
        text=Path(a.__file__).read_text()
        for token in ('subprocess.','runner.run(','.collect.collect(','.parse_spike_commits('):
            self.assertNotIn(token,text)


if __name__=='__main__':unittest.main()
