import struct
import unittest

import check
import prepare


def fixture(backend='native', reuse='direct'):
    case = next(c for c in prepare.catalog()['cases'] if c['profile'] == 1 and
                c['operator'] == 'attn_q' and c['m'] == 1 and c['n'] == 64 and
                c['backend'] == backend and c['reuse'] == reuse)
    command = dict(m=1,n=32,row=0,col=0,layout=1)
    build = dict(case=case, plan=dict(commands=[command,dict(command,col=32)],
                 context_eligible=1, flags=1), build_id='test', flag_seeds=[0,8],
                 numeric_contract=dict(rvv_atol=0.0002,rvv_rtol=0.0002))
    lines = []
    if backend == 'native':
        for t in range(2):
            for i in range(2):
                access = 0 if reuse == 'direct' else ((1 if i == 0 else 3) if reuse == 'operation'
                          else ((1 if i == 0 else 2) if t == 0 else (2 if i == 0 else 3)))
                p = dict(seq=t*2+i+1,m=1,n=32,vlen=1024,lanes=4,success=1,
                    fault=0,validation_fault=0,validation_error=0,read_fault=0,
                    context_validation_fault_count=0,busy_cycles=10,
                    probe_compute_without_dot_issue_cycles=0,dot_active_cycles=2048,
                    weight_bytes=32*8*144,activation_bytes=8*292,useful_pairs=32*2048,
                    pair_capacity=32*2048,tiles=64,activation_access=access,
                    context_fill_count=int(access==1),context_reuse_count=int(access in (2,3)),
                    activation_axi_bytes_saved=8*292 if access in (2,3) else 0)
                p.update({k:0 for k in check.PHASES})
                # Synthetic accounting only, not an RTL performance result.
                p['busy_cycles'] = 2048
                p['phase_compute_cycles'] = 2048
                lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in p.items()))
    lines.append(f'OPQ_META id=test m=1 n=64 k=2048 profile=1 rvv={int(backend != "native")} trials=2')
    for t in range(2):
        r = dict(trial=t,status=0,commands=2 if backend=='native' else 0,
                 context=int(backend=='native' and reuse!='direct'),
                 eligible=int(backend=='native'),coop=0,quant_fcsr=1,fcsr=1|(8 if t else 0),vcsr=0,vstart=0)
        r.update({f't{i}':t*100000+i*10000 for i in range(6)})
        lines.append('OPQ_TRIAL '+' '.join(f'{k}={v}' for k,v in r.items()))
        lines.extend(f'OPQ_GUARD trial={t} index={i} hex='+('a5'*64) for i in range(10))
        for kind in ('Q8','PACK'):
            lines.extend(f'OPQ_{kind} trial={t} block={i} hex='+('00'*292) for i in range(8))
        lines.extend(f'OPQ_OUT trial={t} index={i} bits=3f800000' for i in range(64))
    lines += ['OPQ_DONE errors=0','Core Test *** SUCCESS ***']
    return '\n'.join(lines),build,struct.pack('<64f',*([1.0]*64)),bytes(2336),bytes(2336)


class CheckTests(unittest.TestCase):
    def test_native_and_baselines(self):
        for backend in ('native','rvv','rvv_x32'):
            result = check.parse_log(*fixture(backend))
            self.assertEqual(result['state'],'PASS')
            self.assertEqual(result['metrics']['primary_eligible'],backend!='rvv')

    def test_reuse_lifecycle(self):
        for reuse in ('operation','cross_call'):
            self.assertEqual(check.parse_log(*fixture('native',reuse))['state'],'PASS')

    def test_fail_closed_mutations(self):
        original = fixture()
        mutations = [('bits=3f800000','bits=3f800001'),(' fcsr=1 ',' fcsr=0 '),
                     (' fcsr=9 ',' fcsr=1 '),('t2=20000','t2=10000'),
                     ('a5'*64,'a4'+'a5'*63),('success=1','success=0'),
                     ('useful_pairs=65536','useful_pairs=65535'),
                     ('OPQ_Q8 trial=0 block=0 hex=00','OPQ_Q8 trial=0 block=0 hex=01'),
                     ('OPQ_PACK trial=0 block=0 hex=00','OPQ_PACK trial=0 block=0 hex=01'),
                     ('OPQ_DONE errors=0','OPQ_DONE errors=1')]
        for old,new in mutations:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check.parse_log(original[0].replace(old,new,1),*original[1:])
        for prefix in ('OPQ_GUARD trial=0 index=0','OPQ_OUT trial=1 index=63','OPQ_Q8 trial=1 block=7'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                check.parse_log('\n'.join(x for x in original[0].splitlines() if not x.startswith(prefix)),*original[1:])
        with self.assertRaises(ValueError):
            check.parse_log(original[0].replace('OPQ_DONE','OPQ_OUT trial=1 index=0 bits=3f800000\nOPQ_DONE'),*original[1:])

    def test_rvv_tolerance_and_flags(self):
        f = fixture('rvv_x32')
        check.parse_log(f[0].replace('bits=3f800000','bits=3f800001'),*f[1:])
        for value in ('7fc00000','40000000'):
            with self.assertRaises(ValueError):
                check.parse_log(f[0].replace('bits=3f800000','bits='+value,1),*f[1:])
        with self.assertRaises(ValueError):
            check.parse_log(f[0].replace(' fcsr=9 ',' fcsr=1 '),*f[1:])

    def test_catalog_scope(self):
        cat = prepare.catalog()
        ids = [c['id'] for c in cat['cases']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertTrue(set(cat['calibration']) <= set(ids))
        self.assertEqual(len(cat['format_coverage']),9)
        self.assertEqual(sum(x['status']=='gap_not_runnable' for x in cat['format_coverage']),7)
        for c in cat['cases']:
            self.assertEqual(c['k'],2048)
            self.assertEqual(c['primary_eligible'],c['backend']!='rvv')
            self.assertTrue(c['provenance'].startswith('real_capture'))

    def test_monitor_reports(self):
        text = ('[PERF] ==== Performance Report Start ====\n[PERF] total_cycles : 300\n'
                '[PERF] ==== Performance Report End ====\n')*2
        self.assertEqual(len(check.monitor_reports(text)['trials']),2)
        with self.assertRaises(ValueError):
            check.monitor_reports(text.split('[PERF] ==== Performance Report End ====')[0])


if __name__ == '__main__':
    unittest.main()
