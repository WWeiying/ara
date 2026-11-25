"""Host-only tests of native real projection provenance, complete-K work, and compact proof."""
import unittest
from contract import cases,receipt,FIELDS,repack,ATOL,RTOL
from check import parse_log,KINDS,PHASES
from extract import extract


def fixture(c, actual_build=None):
    native=c['backend'] == 'native'
    commands=[dict(m=c['m'],n=32,row=0,col=col,layout=2 if c['m'] == 4 else 1) for col in range(0,c['n'],32)]
    build=dict(case=c,build_id='test_identity',plan=dict(commands=commands,flags=1),flag_seeds=[0,8],
        diagnostic=False,numeric_contract=dict(native='bit_exact_ordered_qbs_ref',rvv_atol=ATOL,rvv_rtol=RTOL))
    ab=c['m']*c['k_blocks']*c['activation_block_bytes']
    counts=dict(Q8=ab,PACK=ab,OUT=c['m']*c['n'],GUARD=640)
    build['comparisons']={kind:dict(count=counts[kind],expected_hash=1234567) for kind in KINDS}
    if actual_build is not None:
        build=actual_build
        commands=build['plan']['commands']
    lines=[]
    if native:
        for t in range(2):
            for i,cmd in enumerate(commands):
                useful=cmd['m']*cmd['n']*c['k']
                p=dict(seq=len(commands)*t+i+1,m=cmd['m'],n=cmd['n'],lanes=4,vlen=1024,success=1,fault=0,
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
    lines.append('OPR_META '+ ' '.join(f'{key}={value}' for key,value in dict(id=build['build_id'],
        m=c['m'],n=c['n'],k=c['k'],profile=c['profile'],ap=c['activation_profile'],kb=c['k_blocks'],
        ab=c['activation_block_bytes'],rvv=int(not native),trials=2,policy=1).items()))
    for t in range(2):
        start=100000*t+100
        values=[start,start+100,start+200,start+300,start+90000,start+90100]
        r=dict(trial=t,status=0,commands=len(commands) if native else 0,quant_fcsr=1,quant_vcsr=c['quant_vcsr'],
               fcsr=1|(8 if t else 0),vcsr=c['quant_vcsr'],vstart=0)
        r.update({f't{i}':v for i,v in enumerate(values)})
        lines.append('OPR_TRIAL '+' '.join(f'{key}={value}' for key,value in r.items()))
        for kind in KINDS:
            expected_hash=build['comparisons'][kind]['expected_hash']
            r=dict(trial=t,kind=kind,count=counts[kind],mismatches=0,first=0xffffffff,
                expected_hash=expected_hash,actual_hash=expected_hash,raw_differences=0,first_actual=0,first_expected=0)
            lines.append('OPR_CHECK '+' '.join(f'{key}={value}' for key,value in r.items()))
    lines.extend(('OPR_DONE errors=0','Core Test *** SUCCESS ***'))
    return build,'\n'.join(lines)+'\n'


class ProjectionTest(unittest.TestCase):
    def test_selection_native_not_requantized(self):
        cat=cases()
        self.assertEqual(len(cat),8)
        self.assertEqual(len({c['id'] for c in cat}),8)
        self.assertTrue(all(c['native_format_model_capture'] and not c['requantized'] for c in cat))
        self.assertFalse(any(c['phase'] == 'prefill' and c['format'] == 'q4_K' for c in cat))
        for c in cat:
            meta=next(w for w in receipt(c['phase'])['weights'] if w['tensor'] == c['tensor'])
            self.assertEqual(c['k'],meta['k'])
            self.assertEqual(c['k_blocks'],meta['k']//256)
            self.assertLessEqual(c['n'],meta['captured_n'])
            if c['phase'] == 'decode':
                self.assertEqual((c['m'],c['position']),(1,40))
            else:
                self.assertEqual((c['m'],c['kernel_symbol']),(4,'q6k_gemm_32x4'))

    def test_all_cases_and_full_K_work(self):
        for c in cases():
            build,log=fixture(c)
            with self.subTest(case=c['id']):
                metrics=parse_log(log,build)['metrics']
                self.assertEqual(metrics['k'],c['k'])
                self.assertEqual(metrics['output_values_checked'],2*c['m']*c['n'])
                self.assertEqual(metrics['q8_bytes_checked'],2*c['m']*c['k_blocks']*292)
                self.assertTrue(metrics['native_format_model_capture'])
            for field in ('weight_bytes','activation_bytes','useful_pairs','tiles','pair_capacity','dot_active_cycles'):
                if c['backend'] != 'native':
                    continue
                line=next(line for line in log.splitlines() if line.startswith('[QBS_PERF]'))
                word=next(word for word in line.split() if word.startswith(field+'='))
                with self.subTest(case=c['id'],field=field),self.assertRaises(ValueError):
                    parse_log(log.replace(word,field+'=0',1),build)

    def test_compact_proof_rejections_and_postquant_csr(self):
        for c in cases():
            build,log=fixture(c)
            first=next(line for line in log.splitlines() if line.startswith('OPR_CHECK '))
            mutations=[log.replace('mismatches=0','mismatches=1',1),
                log.replace('first=4294967295','first=0',1),
                log.replace('expected_hash=1234567','expected_hash=1',1),
                log.replace('actual_hash=1234567','actual_hash=1',1),
                log.replace('raw_differences=0','raw_differences=1',1),
                log.replace('count=640','count=639',1),log.replace('OPR_DONE errors=0','OPR_DONE errors=1'),
                log.replace('quant_vcsr=2','quant_vcsr=0',1),log.replace(' vcsr=2',' vcsr=0',1),
                log.replace('vstart=0','vstart=1',1),log.replace('fcsr=9','fcsr=1'),
                log.replace('Core Test *** SUCCESS ***',''),log.replace(first+'\n','',1),
                log.replace(first,first+'\n'+first,1),
                log.replace('[PERF] ==== Performance Report End ====','',1)]
            for index,corrupt in enumerate(mutations):
                with self.subTest(case=c['id'],mutation=index),self.assertRaises((ValueError,KeyError)):
                    parse_log(corrupt,build)

    def test_rvv_tolerance_not_hash_acceptance(self):
        for c in (c for c in cases() if c['backend'] == 'rvv_x32'):
            build,log=fixture(c)
            line=next(line for line in log.splitlines() if 'kind=OUT ' in line)
            tolerated=line.replace('raw_differences=0','raw_differences=1').replace('actual_hash=1234567','actual_hash=1')
            self.assertEqual(parse_log(log.replace(line,tolerated,1),build)['state'],'PASS')
            with self.assertRaises(ValueError):
                parse_log(log.replace(line,tolerated.replace('mismatches=0','mismatches=1'),1),build)

    def test_repack_roundtrip_N64_N128_full_K(self):
        for fmt,wb in (('q4_K',144),('q6_K',210)):
            for n,k in ((64,2048),(64,6144),(128,6144)):
                kb=k//256
                raw=bytes((i*37+i//127)&255 for i in range(n*kb*wb))
                packed=repack(raw,fmt,n,k); restored=bytearray(len(raw)); cursor=0
                for first in range(0,n,32):
                    for block in range(kb):
                        for offset,length,size in FIELDS[fmt]:
                            for element in range(0,length,size):
                                for row in range(first,first+32):
                                    start=(row*kb+block)*wb+offset+element
                                    restored[start:start+size]=packed[cursor:cursor+size]; cursor+=size
                self.assertEqual(restored,raw)

    def test_extractor_closure_and_faults(self):
        for phase in ('decode','prefill'):
            prefix='DECODE_CAPTURE_' if phase == 'decode' else 'FFN_CAPTURE_'
            rows=1 if phase == 'decode' else 4
            lines=[] if phase == 'prefill' else [prefix+'BEGIN prompt=40 token=22406 position=40 kv=q8_0 qbs=1']
            for source in range(4 if phase == 'decode' else 3):
                lines.append(prefix+f'SHAPE source=s{source} k=2 rows={rows} '+('' if phase == 'decode' else 'tokens=40 ')+'type=f32')
                for row in range(rows):
                    lines.append(prefix+f'DATA source=s{source} '+('' if phase == 'decode' else f'row={row} ')+
                                 'offset=0 bits='+('3f800000' if row%2 == 0 else '40000000')+'40400000')
            stop='before_decode_vocabulary' if phase == 'decode' else 'before_first_down'
            lines.append(prefix+f'DONE sources={4 if phase == "decode" else 3} stop={stop} performance=not_measured')
            text='\n'.join(lines)
            self.assertEqual(extract(text,phase)['s0']['rows'],rows)
            data=next(line for line in lines if prefix+'DATA ' in line)
            for bad in (text.replace(data,data+'\n'+data,1),text.replace(data,'',1),
                        text.replace('offset=0','offset=2',1),text.replace('performance=not_measured','performance=measured')):
                with self.assertRaises(ValueError):
                    extract(bad,phase)


if __name__ == '__main__':
    unittest.main()
