import unittest
from analyze import analyze


def fixture():
    lines=[f'QBS end-to-end case {i} PASS profile=1' for i in range(36)]
    for window,m in ((1,1),(2,4)):
        for cycle in range(9):
            row=dict(cycle=cycle,window=window,state=3,m=m,bank=int(cycle>=7),
                start=int(cycle==7),done=int(cycle==6),read=int(cycle in (0,8)),
                k=(248 if m==1 else 254) if cycle<8 else 0,block=256,
                compute=int(cycle<6 or cycle==8),issue=int(cycle in (0,8)),
                s0=int(cycle<2),meta=7 if cycle<5 else 0,dot=int(cycle<5),
                ctx=int(cycle==8),live=1,correction_empty=0)
            lines.append('QBS_TILE_BOUNDARY '+' '.join(f'{k}={v}' for k,v in row.items()))
    return '\n'.join(lines+['QBS engine PASS: 36 functional cases'])


class BoundaryTest(unittest.TestCase):
    def test_observation_only(self):
        r=analyze(fixture())
        self.assertEqual([b['next_read_delta'] for b in r['boundaries']],[8,8])
        self.assertFalse(r['early_overlap_safety_proven'])

    def test_reject(self):
        t=fixture()
        for bad in (t.replace('done=1 read=0','done=1 read=1',1),
                    t.replace('cycle=6','cycle=5',1),
                    t.replace('QBS engine PASS: 36 functional cases',''),
                    t+'\nFatal: probe failure',
                    t.replace('case 1 PASS','case 0 PASS',1)):
            with self.assertRaises(ValueError):analyze(bad)


if __name__=='__main__':unittest.main()
