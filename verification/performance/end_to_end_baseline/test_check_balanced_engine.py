from pathlib import Path
import unittest

from matrix_dot_pair import candidate_vectors
from run_wide_default_engine import ORIGINAL
from run_wide_compute import parse_vectors
import check_balanced_engine as c


def line(tag,**values):return tag+' '+' '.join(k+'='+str(v) for k,v in values.items())


def fake(vector, clone, balanced):
    shapes=parse_vectors(vector)
    lines=['WIDE_ENGINE_CONFIG bits=256 matrix=1','MATRIX_ENGINE_CONFIG wide=1',
           line('BE_CONFIG',clone=clone,balanced=balanced,controller=balanced,compute=balanced,bits=256,matrix=1),
           'QBS configuration response_gap=0 context_suite=0']
    for s in shapes:
        fast=balanced and s['m']>=3 and c.BLOCKS[s['profile']][1]==256
        cycles=10000+s['case']-(100 if fast else 0)
        lines.append(f'QBS end-to-end case {s["case"]} PASS profile={s["profile"]} M={s["m"]} N={s["n"]} '
                     f'Kb={s["kb"]} layouts={s["wl"]}/{s["al"]} cycles={cycles}')
        cnt=c.counts(s,balanced)
        lines.append(line('BE_WORK',case=s['case'],
            **dict(zip(('tiles','weights','activation','pairs','capacity','dot','uops','updates'),cnt)),
            flags=s['flags'],words=s['m']*((s['n']+7)//8 if s['m']>4 else 4),mixed=int(bool(fast)),nx=0))
        phase={k:0 for k in c.PHASES};phase['setup']=cycles+1
        lines.append(line('BE_PHASE',case=s['case'],cycles=cycles,**phase))
        ranges=1+((s['n']+3)//4 if s['wl']==2 else s['n'])*s['kb']+(1 if s['al']>1 else s['m'])*s['kb']
        payload=16+cnt[1]+cnt[2]
        lines.append(line('WIDE_ENGINE_TRAFFIC',case=s['case'],ranges=ranges,ar=ranges,
                          beats=max(ranges,(payload+15)//16),payload=payload,weight=cnt[1],activation=cnt[2]))
    s=shapes[0]
    lines.append(f'QBS activation context FILL/REUSE/RELEASE PASS case=0 M={s["m"]} Kb={s["kb"]} '
                 f'bytes={s["counters"][2]} fill_cycles=10000 reuse_cycles=9000')
    lines.extend(f'QBS next-block fault/replay PASS kind={kind}' for kind in range(3))
    lines.append('QBS next-block reset/replay PASS')
    for release in range(2):
        lines.extend(f'QBS context weight fault/retry PASS case=0 release={release} kind={kind}' for kind in range(3))
    lines.extend(f'QBS {kind} atomic-fault PASS' for kind in ('validation','MMU','AXI','PMA'))
    lines.extend(['WIDE_ENGINE_BUS bits=256 narrow=2 wide=3 upper=1',
                  'QBS engine PASS: 36 functional cases plus four fault classes'])
    return '\n'.join(lines)+'\n'


class EngineChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vector=candidate_vectors((ORIGINAL/'matrix-base.txt').read_text())
        cls.new=c.balanced_vector(cls.vector)

    def setUp(self):
        self.base=fake(self.vector,0,0);self.off=fake(self.vector,1,0);self.on=fake(self.vector,1,1)

    def test_raw_numerical_protocol_work_and_pair(self):
        a=c.check(self.base,self.vector,self.vector,0,0,0,1)
        b=c.check(self.off,self.vector,self.vector,1,0,0,1)
        z=c.check(self.on,self.vector,self.new,1,1,0,1)
        result=c.pair(a,b,z)
        self.assertTrue(result['default_off_exact'])
        self.assertGreater(result['baseline_cycles'],result['candidate_cycles'])

    def test_missing_or_false_phase_work_and_atomic_rejected(self):
        work=next(l for l in self.on.splitlines() if l.startswith('BE_WORK '))
        for bad in (self.on.replace(work,''),self.on+'\n'+work,
                    self.on.replace('words=4','words=5',1),
                    self.on.replace('setup=10001','setup=10000',1),
                    self.on.replace('QBS MMU atomic-fault PASS',''),
                    self.on.replace('controller=1','controller=0',1),
                    self.on+'BE_UNKNOWN value=1\n',self.on+'UVM_FATAL failure\n'):
            self.assertNotEqual(bad,self.on)
            with self.assertRaises(ValueError):c.check(bad,self.vector,self.new,1,1,0,1)

    def test_altered_payload_or_work_and_image_rejected(self):
        with self.assertRaises(ValueError):c.check(self.on,self.vector,self.new+'\n',1,1,0,1)
        with self.assertRaises(ValueError):c.check(self.on,self.vector,self.vector,1,1,0,1)
        with self.assertRaises(ValueError):c.check(self.off,self.vector,self.vector,0,0,0,1)
        bad=self.on.replace('dot=128','dot=127',1)
        self.assertNotEqual(bad,self.on)
        with self.assertRaises(ValueError):c.check(bad,self.vector,self.new,1,1,0,1)

    def test_default_or_unqualified_timing_drift_rejected(self):
        a=c.check(self.base,self.vector,self.vector,0,0,0,1)
        b=c.check(self.off,self.vector,self.vector,1,0,0,1)
        z=c.check(self.on,self.vector,self.new,1,1,0,1)
        b['direct'][0]=(*b['direct'][0][:-1],b['direct'][0][-1]+1)
        with self.assertRaises(ValueError):c.pair(a,b,z)
        z['direct'][0]=(*z['direct'][0][:-1],z['direct'][0][-1]+1)
        with self.assertRaises(ValueError):c.pair(a,a,z)


if __name__=='__main__':unittest.main()
