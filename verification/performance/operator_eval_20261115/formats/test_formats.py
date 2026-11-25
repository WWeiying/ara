"""Host schema, profile-work, compact-proof and rejection tests. No simulators."""
import unittest

from contract import PROFILES, FIELDS, cases, repack, fnv, ATOL, RTOL
from check import PHASES, KINDS, parse_log


def fixture(c, actual_build=None):
    native=c['backend'] == 'native'
    commands=[dict(m=c['m'],n=32,row=0,col=col,layout=2 if c['m'] == 4 else 1) for col in (0,32)]
    build=dict(case=c,build_id='test_identity',plan=dict(commands=commands,flags=1),flag_seeds=[0,8],
        diagnostic=False,numeric_contract=dict(native='bit_exact_ordered_qbs_ref',rvv_atol=ATOL,rvv_rtol=RTOL))
    ab=c['m']*c['k_blocks']*c['activation_block_bytes']
    counts=dict(Q8=ab,PACK=ab,OUT=c['m']*64,GUARD=640)
    build['comparisons']={kind:dict(count=counts[kind],expected_hash=1234567) for kind in KINDS}
    if actual_build is not None:
        build=actual_build
        commands=build['plan']['commands']
    lines=[]
    if native:
        for t in range(2):
            for i,cmd in enumerate(commands):
                useful=cmd['m']*cmd['n']*2048
                p=dict(seq=2*t+i+1,m=cmd['m'],n=cmd['n'],lanes=4,vlen=1024,success=1,fault=0,
                    validation_fault=0,validation_error=0,read_fault=0,context_validation_fault_count=0,
                    busy_cycles=useful//32,probe_compute_without_dot_issue_cycles=0,
                    weight_bytes=cmd['n']*c['k_blocks']*c['weight_block_bytes'],activation_bytes=ab,
                    useful_pairs=useful,tiles=c['k_blocks']*8,pair_capacity=useful,dot_active_cycles=useful//32,
                    activation_access=0,context_fill_count=0,context_reuse_count=0,activation_axi_bytes_saved=0,
                    context_reuse_block_count=0,context_read_bytes=0)
                p.update({phase:useful//32 if phase == 'phase_compute_cycles' else 0 for phase in PHASES})
                lines.append('[QBS_PERF] '+' '.join(f'{key}={value}' for key,value in p.items()))
    for t in range(2):
        lines.extend(('[PERF] ==== Performance Report Start ====', '[PERF] total_cycles : 100000',
                      '[PERF] ==== Performance Report End ===='))
    lines.append('OPF_META '+ ' '.join(f'{key}={value}' for key,value in dict(id=build['build_id'],
        m=c['m'],n=64,k=2048,profile=c['profile'],ap=c['activation_profile'],kb=c['k_blocks'],
        ab=c['activation_block_bytes'],rvv=int(not native),trials=2,policy=1).items()))
    for t in range(2):
        start=100000*t+100
        values=[start,start+100,start+200,start+300,start+90000,start+90100]
        r=dict(trial=t,status=0,commands=2 if native else 0,quant_fcsr=1,quant_vcsr=c['quant_vcsr'],
               fcsr=1|(8 if t else 0),vcsr=c['quant_vcsr'],vstart=0)
        r.update({f't{i}':v for i,v in enumerate(values)})
        lines.append('OPF_TRIAL '+' '.join(f'{key}={value}' for key,value in r.items()))
        for kind in KINDS:
            expected_hash=build['comparisons'][kind]['expected_hash']
            r=dict(trial=t,kind=kind,count=counts[kind],mismatches=0,first=0xffffffff,
                expected_hash=expected_hash,actual_hash=expected_hash,raw_differences=0,first_actual=0,first_expected=0)
            lines.append('OPF_CHECK '+' '.join(f'{key}={value}' for key,value in r.items()))
    lines.extend(('OPF_DONE errors=0','Core Test *** SUCCESS ***'))
    return build,'\n'.join(lines)+'\n'


class FormatsTest(unittest.TestCase):
    def test_catalog(self):
        cat=cases()
        self.assertEqual(len(cat),36)
        self.assertEqual(len({c['id'] for c in cat}),36)
        self.assertEqual({p['profile'] for p in PROFILES.values()},set(range(1,10)))
        self.assertTrue(all(c['k'] == 2048 and c['n'] == 64 and c['m'] in (1,4) and
                            not c['native_format_model_capture'] and not c['original_f16_weights'] for c in cat))
        self.assertEqual(sum(c['primary_eligible'] for c in cat if c['backend'] == 'rvv_x32'),10)
        for c in cat:
            if c['m'] == 4 and c['format'] in ('q4_K','q6_K'):
                self.assertEqual(c['kernel_shape'],'32x4')
                self.assertIn('gemm_32x4',c['kernel_symbol'])

    def test_field_maps_exhaustive_and_roundtrip(self):
        for fmt,p in PROFILES.items():
            with self.subTest(fmt=fmt):
                covered=[i for offset,length,_ in FIELDS[fmt] for i in range(offset,offset+length)]
                self.assertEqual(sorted(covered),list(range(p['weight_block_bytes'])))
                n,k=64,2*p['block_elements']
                wb,kb=p['weight_block_bytes'],2
                raw=bytes((i*37+i//127)&255 for i in range(n*kb*wb))
                packed=repack(raw,fmt,n,k)
                restored=bytearray(len(raw)); cursor=0
                for first in range(0,n,32):
                    for block in range(kb):
                        for offset,length,size in FIELDS[fmt]:
                            for element in range(0,length,size):
                                for row in range(first,first+32):
                                    start=(row*kb+block)*wb+offset+element
                                    restored[start:start+size]=packed[cursor:cursor+size]; cursor+=size
                self.assertEqual(restored,raw)

    def test_reject_partial_repack(self):
        for fmt,p in PROFILES.items():
            with self.assertRaises(ValueError):
                repack(bytes(p['weight_block_bytes']*8*33),fmt,n=33)

    def test_fnv_known_vector(self):
        self.assertEqual(fnv(b''),2166136261)
        self.assertEqual(fnv(b'hello'),0x4f9f2cab)

    def test_all_formats_backends_and_m(self):
        for c in cases():
            with self.subTest(case=c['id']):
                build,log=fixture(c)
                result=parse_log(log,build)
                self.assertEqual(result['state'],'PASS')
                self.assertEqual(result['metrics']['q8_bytes_checked'],2*c['m']*c['k_blocks']*c['activation_block_bytes'])
                self.assertFalse(result['metrics']['hash_only_acceptance'])

    def test_all_native_profile_work_mutations(self):
        for c in cases():
            if c['backend'] != 'native':
                continue
            build,log=fixture(c)
            for key in ('weight_bytes','activation_bytes','useful_pairs','tiles','pair_capacity','dot_active_cycles'):
                first=next(line for line in log.splitlines() if line.startswith('[QBS_PERF] '))
                value=next(word for word in first.split() if word.startswith(key+'='))
                corrupt=log.replace(value,key+'=0',1)
                with self.subTest(case=c['id'],field=key), self.assertRaises(ValueError):
                    parse_log(corrupt,build)

    def test_compact_evidence_mutations(self):
        for c in cases():
            build,log=fixture(c)
            mutations=[log.replace('mismatches=0','mismatches=1',1),
                log.replace('first=4294967295','first=0',1),
                log.replace('expected_hash=1234567','expected_hash=1234568',1),
                log.replace('actual_hash=1234567','actual_hash=1234568',1),
                log.replace('raw_differences=0','raw_differences=1',1),
                log.replace('OPF_DONE errors=0','OPF_DONE errors=1'),
                log.replace('vcsr='+str(c['quant_vcsr']),'vcsr=7',1),
                log.replace(' vcsr='+str(c['quant_vcsr']),' vcsr=7',1),
                log.replace('vstart=0','vstart=1',1),log.replace('fcsr=9','fcsr=1'),
                log.replace('trials=2','trials=1',1),log.replace('policy=1','policy=2'),
                log.replace('Core Test *** SUCCESS ***',''),log+'OPF_UNRECOGNIZED x=1\n',
                log.replace('[PERF] ==== Performance Report End ====','',1)]
            check=next(line for line in log.splitlines() if line.startswith('OPF_CHECK '))
            mutations.extend((log.replace(check+'\n','',1),log.replace(check,check+'\n'+check,1)))
            for i,mutated in enumerate(mutations):
                with self.subTest(case=c['id'],mutation=i), self.assertRaises((ValueError,KeyError)):
                    parse_log(mutated,build)

    def test_q8k_postquant_vcsr_not_static_zero(self):
        c=next(c for c in cases() if c['format'] == 'q4_K')
        build,log=fixture(c)
        self.assertEqual(parse_log(log,build)['state'],'PASS')
        with self.assertRaises(ValueError):
            parse_log(log.replace('quant_vcsr=2','quant_vcsr=0').replace(' vcsr=2',' vcsr=0'),build)

    def test_tolerated_rvv_is_not_hash_equality_gate(self):
        c=next(c for c in cases() if c['backend'] == 'rvv_x32')
        build,log=fixture(c)
        line=next(line for line in log.splitlines() if line.startswith('OPF_CHECK ') and 'kind=OUT ' in line)
        changed=line.replace('raw_differences=0','raw_differences=1').replace('actual_hash=1234567','actual_hash=1')
        self.assertEqual(parse_log(log.replace(line,changed,1),build)['state'],'PASS')
        with self.assertRaises(ValueError):
            parse_log(log.replace(line,changed.replace('mismatches=0','mismatches=1'),1),build)

    def test_guard_count_and_mismatch_not_hash_only(self):
        build,log=fixture(cases()[0])
        line=next(line for line in log.splitlines() if 'kind=GUARD ' in line)
        for mutated in (line.replace('count=640','count=639'),line.replace('mismatches=0','mismatches=1')):
            with self.assertRaises(ValueError):
                parse_log(log.replace(line,mutated,1),build)


if __name__ == '__main__':
    unittest.main()
