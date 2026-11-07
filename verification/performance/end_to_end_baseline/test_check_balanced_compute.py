import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import check_balanced_compute as c
from run_wide_compute import expected_counters, check_log, parse_vectors
from test_wide_compute import fake_shapes, fake_log


def shapes():
    result=fake_shapes()
    row=copy.deepcopy(result[-1]);row.update(n=7)
    row['outputs']={ctx*32+n:0x40000000+ctx*32+n for ctx in range(4) for n in range(7)}
    row['counters']=expected_counters(row)
    result.insert(1,row)
    for index,row in enumerate(result):row['case']=index
    return result


def arithmetic(ss):
    lines=fake_log(ss,1).splitlines()
    for index,line in enumerate(lines):
        if not line.startswith('WC_FP '):continue
        d=dict(word.split('=',1) for word in line.split()[1:])
        if int(d['state']) in (2,3) and int(d['kind'])==1:
            d.update(op='3',a='3f802000',b='3f800001',c='00000000')
            lines[index]='WC_FP '+' '.join(k+'='+v for k,v in d.items())
    return '\n'.join(lines)+'\n'


def observe(ss, clone, mode):
    current=c.candidate_shapes(ss) if mode else ss
    raw=arithmetic(current);_,events=check_log(raw,current,1)
    output=[raw,f'MC_CONFIG clone={clone} mixed={mode} width=256']
    episodes={s['case']:s for s in ss};episodes.update({1000+i:ss[0] for i in range(5)})
    for eid,s in episodes.items():
        total=fast=0
        for (ep,acc),rows in events.items():
            if ep!=eid:continue
            for r in rows:
                if r['kind']==1 and r['state'] in (2,3):
                    total+=1
                    if mode and c.admitted(s,acc):fast+=1
        cycles=1000+eid-(100 if fast else 0)
        last=int(mode and s['m']>=3 and c.BLOCKS[s['profile']][1]==256)
        correction=s['m']*s['n']*s['kb']*(8 if s['profile'] in (1,4) else 16 if c.BLOCKS[s['profile']][1]==256 else 1)
        output.append(f'MC_TIME episode={eid} cycles={cycles} mixed_issue={fast} mixed_return={fast} '
            f'mixed_nx={fast} multi_return={int(bool(fast))} union_nx={int(bool(fast))} legacy_mul={total-fast}')
        output.append(f'BC_PHYSICAL episode={eid} dot_issues={c.counts(s,mode)[5]} corrections={correction} '
            f'last_correction={last} fp_input_blocked=0 fp_slot_blocked=0 fp_acc_blocked=0 correction_pending=10 fp_no_uop=10')
    return '\n'.join(output)+'\n'


class BalancedChecks(unittest.TestCase):
    def setUp(self):
        self.shapes=shapes();self.base=observe(self.shapes,0,0)
        self.off=observe(self.shapes,1,0);self.on=observe(self.shapes,1,1)

    def check(self, on=None, off=None):
        with patch.object(c,'parse_vectors',return_value=self.shapes),patch.object(c,'vector',return_value='new'):
            return c.check(self.base,self.off if off is None else off,self.on if on is None else on,'old','new')

    def test_raw_acceptance_and_strict_m1_identity(self):
        measured=self.check();self.assertTrue(measured['m1_m2_and_short_format_timing_identical'])
        self.assertGreater(measured['last_correction_issues'],0)
        bad=self.on.replace('episode=0 cycles=1000','episode=0 cycles=1001',1)
        self.assertNotEqual(bad,self.on)
        with self.assertRaises(ValueError):self.check(bad)
        line=next(l for l in self.on.splitlines() if l.startswith('BC_PHYSICAL episode=0 '))
        bad=self.on.replace(line,line.replace('last_correction=0','last_correction=1'))
        self.assertNotEqual(bad,self.on)
        with self.assertRaises(ValueError):self.check(bad)

    def test_missing_counter_route_and_diagnostic_rejected(self):
        line=next(l for l in self.on.splitlines() if l.startswith('BC_PHYSICAL '))
        nx=next(l for l in self.on.splitlines() if l.startswith('MC_TIME ') and 'mixed_nx=0' not in l)
        for bad in (self.on.replace(line,''),self.on+'\n'+line,
                    self.on.replace(nx,nx.replace('mixed_nx=112','mixed_nx=0')),
                    self.on.replace('dot_issues=128','dot_issues=127',1),
                    self.on+'BC_UNKNOWN x=1\n',self.on+'UVM_ERROR failure\n'):
            self.assertNotEqual(bad,self.on)
            with self.assertRaises(ValueError):self.check(bad)
        off=self.off.replace('episode=0 cycles=1000','episode=0 cycles=1001',1)
        with self.assertRaises(ValueError):self.check(off=off)

    def test_real_vector_changes_only_physical_capacity_and_dot(self):
        old=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mixed_scale_edges_20261106_01/combined-matrix1-76.txt').read_text()
        changed=c.vector(old);a=old.splitlines();b=changed.splitlines()
        self.assertEqual(len(a),len(b));seen=0
        for x,y in zip(a,b):
            if not x.startswith('C '):self.assertEqual(x,y)
            else:
                left,right=x.split(),y.split()
                for index in (0,1,2,3,4,7,8):self.assertEqual(left[index],right[index])
                seen+=x!=y
        self.assertGreater(seen,0)
        self.assertEqual(len(c.candidate_shapes(parse_vectors(old))),76)

    def test_work_model_exhaustive_small_geometries(self):
        for p in range(1,10):
            block=c.BLOCKS[p][1]
            for m in range(1,9):
                for n in (1,3,4,7,9):
                    s=dict(profile=p,m=m,n=n,kb=3,al=1)
                    s['counters']=expected_counters(s)
                    count=0
                    for first in range(0,m,4):
                        size=min(4,m-first)
                        step=128//(4*4) if block==256 and size>=3 else 8 if size==1 else 4 if size==2 else 2
                        count+=sum(1 for _ in range(0,block,step))
                    got=c.counts(s,True)
                    self.assertEqual(got[5],3*((n+3)//4)*count)
                    self.assertEqual(got[4],3*n*count*32)
                    for index in (0,1,2,3,6,7):self.assertEqual(got[index],s['counters'][index])
                    for ctx in range(m):
                        acc=ctx*(16 if m>4 else 32)
                        self.assertEqual(c.admitted(s,acc),block==256 and min(4,m-(ctx//4)*4)>=3)

    def fault_log(self):
        output=[l for l in self.on.splitlines() if l.startswith(('WC_CONFIG ','MC_CONFIG '))]
        selected=[l for l in self.on.splitlines() if l.startswith(('WC_FP ','WC_OUTPUT ','WC_CASE ','MC_TIME ','BC_PHYSICAL '))
                  and 'episode=1 ' in l]
        for eid in (1005,1006,1007):
            output.extend(l.replace('episode=1 ',f'episode={eid} ').replace('recovery=0','recovery=1') for l in selected)
        output.extend([f'WC_FAULT kind={i} pending=0 drain=3' for i in (5,6,7)])
        output.extend(['MC_FAULT_TRIGGER kind=5 issue=1 response=0 mixed_busy=0 entries=4',
                       'MC_FAULT_TRIGGER kind=6 issue=1 response=1 mixed_busy=1 entries=4',
                       'BC_FAULT_TRIGGER kind=7 last_correction=1 lanes=8 integer_busy=1',
                       'MC_FAULT_PASS recovery=3 faults=3 drain_before_clear=1'])
        return '\n'.join(output)+'\n'

    def test_fault_stages_and_original_recovery_sequences(self):
        text=self.fault_log()
        with patch.object(c,'parse_vectors',return_value=self.shapes):
            self.assertEqual(c.fault_check(text,'old',self.base)['recovery_outputs'],84)
        for bad in (text.replace('last_correction=1 lanes=8','last_correction=0 lanes=8'),
                    text.replace('lanes=8','lanes=4'),text.replace('kind=5 issue=1','kind=5 issue=0'),
                    text.replace('bits=40000000','bits=40000001',1),text+'UVM_FATAL failure\n'):
            self.assertNotEqual(bad,text)
            with patch.object(c,'parse_vectors',return_value=self.shapes),self.assertRaises(ValueError):
                c.fault_check(bad,'old',self.base)


if __name__=='__main__':unittest.main()
