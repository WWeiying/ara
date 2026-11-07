import unittest

from test_wide_compute import fake_shapes, fake_log
from run_wide_compute import check_log
from check_mixed_compute import check, fault_check
from mixed_scale_model_census import eligible


def arithmetic_log(shapes):
    lines=fake_log(shapes,0).splitlines(); first={}
    for i,line in enumerate(lines):
        if not line.startswith('WC_FP '):continue
        d=dict(w.split('=',1) for w in line.split()[1:])
        if int(d['state']) in (2,3) and int(d['kind'])==1:
            d['op']='3';d['a']='3f802000';d['b']='3f800001'
            if d['episode'] not in first:
                first[d['episode']]=True;d['a']='00000000'
            lines[i]='WC_FP '+' '.join(k+'='+v for k,v in d.items())
    return '\n'.join(lines)+'\n'


def observe(raw,shapes,clone,mixed,slower=False):
    _,events=check_log(raw,shapes,0)
    lines=[raw.rstrip(),f'MC_CONFIG clone={clone} mixed={mixed} width=128']
    for eid in [1000+i for i in range(5)]+list(range(len(shapes))):
        total=fast=nx=0
        for (ep,acc),rows in events.items():
            if ep!=eid:continue
            for r in rows:
                if r['kind']==1 and r['state'] in (2,3):
                    total+=1
                    if mixed and eligible(r['b'],r['a'],True):fast+=1;nx+=1
        cycles=1000+eid+(50 if mixed and slower else -50 if mixed else 0)
        multi=int(fast>0)
        lines.append(f'MC_TIME episode={eid} cycles={cycles} mixed_issue={fast} mixed_return={fast} '
                     f'mixed_nx={nx} multi_return={multi} union_nx={multi} legacy_mul={total-fast}')
    return '\n'.join(lines)+'\n'


class MixedComputeGates(unittest.TestCase):
    def setUp(self):
        self.shapes=fake_shapes();raw=arithmetic_log(self.shapes)
        self.base=observe(raw,self.shapes,0,0);self.off=observe(raw,self.shapes,1,0)
        self.on=observe(raw,self.shapes,1,1)

    def test_raw_legacy_and_physical_timing_checks(self):
        import check_mixed_compute as c
        from unittest.mock import patch
        with patch.object(c,'parse_vectors',return_value=self.shapes):
            result=check(self.base,self.off,self.on,'fixture')
        self.assertTrue(result['disabled_cycle_identical'])
        self.assertGreater(result['mixed_nx'],0)

    def test_missing_duplicate_counter_and_disabled_drift_rejected(self):
        import check_mixed_compute as c
        from unittest.mock import patch
        row=next(l for l in self.on.splitlines() if l.startswith('MC_TIME '))
        for bad in (self.on.replace(row,''),self.on+'\n'+row,
                    self.on.replace('mixed_return=19','mixed_return=18',1),
                    self.on.replace('MC_CONFIG clone=1 mixed=1','MC_CONFIG clone=1 mixed=0'),
                    self.on+'MC_UNKNOWN value=1\n'):
            # Use an unconditional changed first counter, independent of shape size.
            self.assertNotEqual(bad,self.on)
            with patch.object(c,'parse_vectors',return_value=self.shapes),self.assertRaises(ValueError):
                check(self.base,self.off,bad,'fixture')
        off=self.off.replace('cycles=2000','cycles=2001',1)
        with patch.object(c,'parse_vectors',return_value=self.shapes),self.assertRaises(ValueError):
            check(self.base,off,self.on,'fixture')

    def test_new_operand_or_missing_nx_cannot_hide_under_same_output(self):
        import check_mixed_compute as c
        from unittest.mock import patch
        for bad in (self.on.replace('a=3f802000','a=3f804000',1),
                    self.on.replace('mixed_nx=19','mixed_nx=0',1)):
            self.assertNotEqual(bad,self.on)
            with patch.object(c,'parse_vectors',return_value=self.shapes),self.assertRaises(ValueError):
                check(self.base,self.off,bad,'fixture')

    def test_slower_candidate_is_functional_not_falsely_rejected(self):
        import check_mixed_compute as c
        from unittest.mock import patch
        raw=arithmetic_log(self.shapes)
        with patch.object(c,'parse_vectors',return_value=self.shapes):
            result=check(self.base,self.off,observe(raw,self.shapes,1,1,True),'fixture')
        self.assertLess(result['cases'][0]['component_ratio'],1)

    def fault_log(self):
        lines=[l for l in self.on.splitlines() if l.startswith(('WC_CONFIG ','MC_CONFIG '))]
        selected=[l for l in self.on.splitlines() if l.startswith(('WC_FP ','WC_OUTPUT ','WC_CASE ','MC_TIME '))
                  and 'episode=1000 ' in l]
        for eid in (1005,1006):lines.extend(l.replace('episode=1000 ',f'episode={eid} ') for l in selected)
        lines.extend(['WC_FAULT kind=5 pending=0 drain=3','WC_FAULT kind=6 pending=0 drain=3',
            'MC_FAULT_TRIGGER kind=5 issue=1 response=0 mixed_busy=0 entries=4',
            'MC_FAULT_TRIGGER kind=6 issue=0 response=1 mixed_busy=1 entries=4',
            'MC_FAULT_PASS recovery=2 faults=2 drain_before_clear=1'])
        return '\n'.join(lines)+'\n'

    def test_fault_requires_observed_stages_and_original_recovery(self):
        import check_mixed_compute as c
        from unittest.mock import patch
        text=self.fault_log()
        with patch.object(c,'parse_vectors',return_value=self.shapes):
            self.assertEqual(fault_check(text,'fixture',self.base)['recovery_episodes'],[1005,1006])
        for bad in (text.replace('kind=5 issue=1','kind=5 issue=0'),
                    text.replace('kind=6 issue=0 response=1','kind=6 issue=0 response=0'),
                    text.replace('drain_before_clear=1','drain_before_clear=0'),
                    text.replace('bits=3f800000','bits=3f800001',1),
                    text.replace('WC_FAULT kind=5 pending=0','WC_FAULT kind=5 pending=1'),
                    text+'UVM_ERROR fake.sv(1) @ 1: monitor failed\n',
                    text+'UVM_FATAL fake.sv(1) @ 1: monitor failed\n'):
            self.assertNotEqual(text,bad)
            with patch.object(c,'parse_vectors',return_value=self.shapes),self.assertRaises(ValueError):
                fault_check(bad,'fixture',self.base)


if __name__=='__main__':unittest.main()
