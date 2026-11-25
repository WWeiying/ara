import copy
import unittest

import check
import prepare
from test_qbs import fixture


def matrix_fixture(m=8,n=128,tile=8,cooperative=True,backend='native'):
    _,base,_,_,_ = fixture()
    b = copy.deepcopy(base)
    c = next(c for c in prepare.catalog()['cases'] if c['m']==m and c['n']==n and
             c['tile']==tile and c['backend']==backend and c['operator']=='attn_q' and
             c['reuse']=='direct')
    b['case'] = c
    tn = 16 if tile==8 else 32
    commands = [dict(m=tile,n=tn,row=r,col=col,layout=3 if tile==8 else 2)
                for r in range(0,m,tile) for col in range(0,n,tn)]
    b['plan'] = dict(commands=commands,context_eligible=0,flags=1)
    native = backend=='native'
    lines = []
    if native:
        for t in range(2):
            for i,c in enumerate(commands):
                pairs = c['m']*c['n']*2048
                capacity = 64 if cooperative and c['m']==8 else 32
                p = dict(seq=t*len(commands)+i+1,m=c['m'],n=c['n'],vlen=1024,lanes=4,
                    success=1,fault=0,validation_fault=0,validation_error=0,read_fault=0,
                    context_validation_fault_count=0,busy_cycles=pairs//capacity,
                    probe_compute_without_dot_issue_cycles=0,dot_active_cycles=pairs//capacity,
                    weight_bytes=c['n']*8*144,activation_bytes=c['m']*8*292,useful_pairs=pairs,
                    pair_capacity=pairs,tiles=8*(c['n']//4)*(2 if c['m']>4 else 1),
                    activation_access=0,context_fill_count=0,context_reuse_count=0,
                    activation_axi_bytes_saved=0)
                p.update({k:0 for k in check.PHASES})
                p['phase_compute_cycles'] = p['busy_cycles']
                lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in p.items()))
    lines.append(f'OPQ_META id=test m={m} n={n} k=2048 profile=1 rvv={int(not native)} trials=2')
    for t in range(2):
        r = dict(trial=t,status=0,commands=len(commands) if native else 0,
            context=0,eligible=0,coop=int(native and cooperative),quant_fcsr=1,
            fcsr=1|(8 if t else 0),vcsr=0,vstart=0)
        r.update({f't{i}':t*10000000+i*1000000 for i in range(6)})
        lines.append('OPQ_TRIAL '+' '.join(f'{k}={v}' for k,v in r.items()))
        lines.extend(f'OPQ_GUARD trial={t} index={i} hex='+('a5'*64) for i in range(10))
        for kind in ('Q8','PACK'):
            lines.extend(f'OPQ_{kind} trial={t} block={i} hex='+('00'*292) for i in range(m*8))
        lines.extend(f'OPQ_OUT trial={t} index={i} bits=3f800000' for i in range(m*n))
    lines += ['OPQ_DONE errors=0','Core Test *** SUCCESS ***']
    return '\n'.join(lines),b,bytes.fromhex('0000803f')*(m*n),bytes(m*8*292),bytes(m*8*292)


class MatrixCheckTests(unittest.TestCase):
    def test_m4_m8_and_tiled_scheduling(self):
        for m,n,tile in ((4,64,4),(8,128,8),(8,128,4)):
            for coop in (False,True):
                self.assertEqual(check.parse_log(*matrix_fixture(m,n,tile,coop))['state'],'PASS')

    def test_m8_x32(self):
        self.assertEqual(check.parse_log(*matrix_fixture(8,128,4,False,'rvv_x32'))['state'],'PASS')

    def test_cooperation_rate_not_silently_assumed(self):
        f = matrix_fixture()
        with self.assertRaises(ValueError):
            check.parse_log(f[0].replace('coop=1','coop=0'),*f[1:])


if __name__ == '__main__':
    unittest.main()
