import copy
import unittest
from pathlib import Path
import admit_scalar_div_subnormal795 as a


class Admission(unittest.TestCase):
    def shape(self):
        metrics={m:{'s'+str(i):dict(width=2,checksum='1',bits='1') for i in range(n)}
            for m,n in a.union_tools.COUNTS.items()}
        before=dict(tests=['v'+str(i) for i in range(794)],design={'source':'frozen'},metrics=metrics,input_hashes={})
        single=copy.deepcopy(before);single['tests']=['new']
        for rows in single['metrics'].values():
            for row in rows.values():row['bits']='2'
        return before,single

    def test_full6162_exact794prefix(self):
        b,s=self.shape();r=a.full_union(b,s,Path('new'))
        self.assertEqual(r['tests'],b['tests']+['new'])
        self.assertEqual(sum(map(len,r['metrics'].values())),6162)
        self.assertTrue(all(int(row['bits'],16)==3 for rs in r['metrics'].values() for row in rs.values()))

    def test_missing_instance_checksum_width_or_bounds_rejected(self):
        for change in ('missing','checksum','width','bits'):
            b,s=self.shape();rows=s['metrics']['line']
            if change=='missing':rows.pop('s0')
            else:rows['s0'][change]={'checksum':'2','width':3,'bits':'8'}[change]
            with self.assertRaises(ValueError):a.full_union(b,s,Path('new'))

    def test_duplicate_or_wrong_population_rejected(self):
        for change in ('duplicate','population','vdb'):
            b,s=self.shape()
            if change=='duplicate':b['tests'][0]=b['tests'][1]
            elif change=='population':b['tests'].pop()
            else:s['tests']=['v0']
            with self.assertRaises(ValueError):a.full_union(b,s,Path('new'))

    def test_zero_gain_rejected(self):
        with self.assertRaises(ValueError):a.positive({'metrics':dict(line=0,cond=0,branch=0,fsm=0)},{'scope':[]})

    def test_positive_toggle_or_other_metric(self):
        a.positive({'metrics':dict(line=0,cond=0,branch=0,fsm=0)},{'scope':[4]})
        a.positive({'metrics':dict(line=1,cond=0,branch=0,fsm=0)},{'scope':[]})

    def qualification(self):return a.life.read_bound(a.QUAL/'qualification.json',a.QUAL_SHA)

    def test_actual_joint_qualification_authority(self):
        a.qualification_gate(self.qualification())

    def test_missing_successor_test_or_source_pin_rejected(self):
        q=self.qualification()
        del q['input_pins'][str(Path(a.successor.__file__).resolve())]
        with self.assertRaises(ValueError):a.qualification_gate(q)

    def test_wrong_baseline_original_or_wave_authority_rejected(self):
        for key in ('original_collector_sha','wave_evidence_sha','successor'):
            q=self.qualification();q['qualification_authority'][key]='wrong'
            with self.assertRaises(ValueError):a.qualification_gate(q)
        q=self.qualification();q['baseline']=793
        with self.assertRaises(ValueError):a.qualification_gate(q)

    def test_boolean_count_and_false_functional_qualification_rejected(self):
        q=self.qualification();q['measured_Toggle']=False
        with self.assertRaises(ValueError):a.qualification_gate(q)
        q=self.qualification();q['architecture']['guards_checked']=False
        with self.assertRaises(ValueError):a.qualification_gate(q)

    def test_actual_closed794_elf_ownership(self):
        base=a.life.read_bound(a.BASE/'admission-manifest.json',a.BASE_SHA)
        auth=a.life.merge_pins(base['input_pins'],base['output_pins'])
        ledger=(a.BASE/'combined-inputs.txt').read_text().splitlines()
        record=a.life.read_bound(a.RUN.with_name(a.RUN.name+'.prepared.json'),a.RUN_SHA)
        d=a.dedup(base,ledger,auth,record['elf_sha256'])
        self.assertEqual(len(d['members']),794)
        with self.assertRaises(ValueError):a.dedup(base,ledger,auth,list(d['members'][0]['ELF_candidates'].values())[0])


if __name__=='__main__':unittest.main()
