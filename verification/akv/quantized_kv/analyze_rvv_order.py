#!/usr/bin/env python3
"""Compare accepted QBS matrices with a target-disassembly-anchored FP-order model."""
import argparse
import hashlib
import math
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'verification/akv/paired_heads'))
import attention_run as s
from check_rvv_qbs import HostOracle
from check_batch_qk import SCORE
from batch_spec import sequence


def ulp_distance(a,b):
    def ordered(x):
        return (~x)&0xffffffff if x&0x80000000 else x|0x80000000
    return abs(ordered(a)-ordered(b))


def block_precision(kind,weights,query):
    """Double represents these <=31-significand-bit products exactly."""
    result=[]
    for block in range(4):
        wb=18 if kind else 34
        w=weights[block*wb:(block+1)*wb]; q=query[block*34:(block+1)*34]
        dw=struct.unpack_from('<e',w)[0]; dq=struct.unpack_from('<e',q)[0]
        integers=struct.unpack_from('<32b',q,2)
        if kind:
            wi=[((w[2+i] & 15)-8) if i<16 else ((w[2+i-16]>>4)-8) for i in range(32)]
        else:
            wi=struct.unpack_from('<32b',w,2)
        dot=sum(a*b for a,b in zip(wi,integers))
        exact_first=dot*dw
        rounded_first=struct.unpack('<f',struct.pack('<f',exact_first))[0]
        exact_scale=dw*dq
        rounded_scale=struct.unpack('<f',struct.pack('<f',exact_scale))[0]
        result.append(dict(integer_dot=dot,first_product_rounded=exact_first!=rounded_first,
            first_product_abs_rounding=abs(exact_first-rounded_first),scale_product_rounded=exact_scale!=rounded_scale))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    run=ROOT/'verification/out/akv-quantkv-batch-qk-20261024-02'
    m1=ROOT/'verification/out/akv-quantkv-rvv-qbs-20261024-01'
    linked=ROOT/'verification/out/akv-quantkv-rvv-qbs-build-20261024-01/disassembly.log'
    source=Path('/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/quants.c')
    try:
        receipt=s.read_json(ROOT/'verification/akv/results/quantized-kv-batch-qk-20261024.json')
        s.require(s.digest(run/'result.json')==receipt['run_result_sha256'],'Accepted QK result drift')
        audit_dir=ROOT/receipt['audit']; audit=s.read_json(audit_dir/'result.json')
        s.require(s.digest(audit_dir/'result.json')==receipt['audit_result_sha256'] and
            s.digest(audit_dir/'source-pins.json')==receipt['audit_pins_sha256'] and
            audit['state']=='INDEPENDENT_BATCH_QK_ACCEPTED','Independent QK audit drift')
        accepted=s.read_json(audit_dir/'source-pins.json')
        result=s.read_json(run/'result.json'); prior=s.read_json(m1/'result.json')
        keys=[ROOT/'verification/out/akv-quantkv-host-capture-20261024-01'/
            ('capture-k-'+name+'-v-q8_0')/'decode/block/attn_k_input-0.bin' for name in ('q8_0','q4_0')]
        raw=run/'work/run.vcs.log'
        inputs=[raw,m1/'result.json',source,linked,*keys]
        for path in inputs:
            s.require(accepted.get(str(path))==s.digest(path),'Input not fixed by accepted native inquiry: '+str(path))
        pins=s.hashes(inputs+[ROOT/'verification/akv/results/quantized-kv-batch-qk-20261024.json',
            run/'result.json',audit_dir/'result.json',audit_dir/'source-pins.json',
            Path(__file__),HERE/'rvv_order_score.c',HERE/'test_rvv_order_score.py',HERE/'test_order_precision.py',
            HERE/'batch_spec.py',HERE/'check_batch_qk.py',HERE/'check_rvv_qbs.py',
            ROOT/'verification/qbs/qbs_ref.c',ROOT/'verification/qbs/qbs_ref.h',
            Path('/usr/bin/gcc').resolve(),Path('/lib64/libm.so.6').resolve(),Path('/lib64/libc.so.6').resolve()])
        text=linked.read_text()
        patterns=[('ggml_vec_dot_q4_0_q8_0','fmul.s\tfa4,fa4,fa3','fmadd.s\tfa2,fa4,fa5,fa2'),
                  ('ggml_vec_dot_q8_0_q8_0','fmul.s\tfa5,fa5,fa4','fmadd.s\tfa3,fa4,fa5,fa3')]
        for symbol,mul,madd in patterns:
            match=re.search(r'<'+symbol+r'>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',text,re.S)
            s.require(match is not None and mul in match[1] and madd in match[1] and
                match[1].index(mul)<match[1].index(madd),'Pinned target scalar FP order differs')
        library=out/'rvv-order.so'
        command=['/usr/bin/gcc','-std=gnu11','-O2','-shared','-fPIC','-fno-fast-math',
            '-ffp-contract=off','-frounding-math','-I'+str(ROOT),str(HERE/'rvv_order_score.c'),
            str(ROOT/'verification/qbs/qbs_ref.c'),'-lm','-o',str(library)]
        s.atomic_json(out/'compile.command.json',dict(argv=command,cwd=str(out)))
        with (out/'compile.log').open('x') as log:
            subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        oracle=HostOracle(library)
        key_data=[path.read_bytes() for path in keys]
        queries={(q['kind'],q['head']):bytes.fromhex(q['hex']) for q in result['query_exports']}
        prior_queries={(q['kind'],q['head']):bytes.fromhex(q['hex']) for q in prior['queries']}
        for score in prior['scores']:
            kind,head,token=(score[k] for k in ('kind','head','token'))
            query=prior_queries[kind,head]
            s.require(query==queries[kind,head*6],'Actual prior/current Query bytes differ')
            row_bytes=72 if kind else 136
            start=(head*256+token)*row_bytes
            bits,flags=oracle(kind,key_data[kind][start:start+row_bytes],query)
            s.require((bits,flags)==(score['rvv_bits'],score['rvv_flags']),'Model differs from actual prior RVV score/flags')
        rows=[SCORE.fullmatch(line) for line in raw.read_text().splitlines() if SCORE.fullmatch(line)]
        commands=sequence(); s.require(len(rows)==len(commands)==40,'Incomplete accepted raw score records')
        comparisons=[]; command_comparisons=[]; precision=[[],[]]
        for index,(match,c) in enumerate(zip(rows,commands)):
            s.require(hashlib.sha256(match[9].encode('ascii')).hexdigest()==result['score_rows'][index]['score_hex_sha256'],
                      'Raw score word sequence drift')
            aggregate=0
            for row in range(c.m):
                for column in range(c.n):
                    start,end=c.key_range(column)
                    model,flags=oracle(c.kind,key_data[c.kind][start:end],queries[c.kind,c.first_q+row])
                    precision[c.kind].extend(block_precision(c.kind,key_data[c.kind][start:end],queries[c.kind,c.first_q+row]))
                    offset=8*(row*c.n+column); hardware=int(match[9][offset:offset+8],16)
                    actual,expected=(struct.unpack('<f',struct.pack('<I',x))[0] for x in (hardware,model))
                    s.require(math.isfinite(actual) and math.isfinite(expected),'Nonfinite modeled score')
                    aggregate|=flags
                    comparisons.append(dict(kind=c.kind,query_head=c.first_q+row,kv_head=c.kv_head,
                        token=c.first_token+column,hardware_bits=f'{hardware:08x}',modeled_rvv_bits=f'{model:08x}',
                        modeled_rvv_flags=flags,exact=hardware==model,ulp=ulp_distance(hardware,model),
                        abs_difference=abs(actual-expected)))
            command_comparisons.append(dict(seq=index+1,kind=c.kind,
                observed_qbs_flags=result['score_rows'][index]['fcsr'],modeled_rvv_aggregate_flags=aggregate))
        summaries=[]
        for kind in (0,1):
            subset=[r for r in comparisons if r['kind']==kind]
            flags=[r for r in command_comparisons if r['kind']==kind]
            summaries.append(dict(kind=kind,outputs=len(subset),bits_different=sum(not r['exact'] for r in subset),
                max_ulp=max(r['ulp'] for r in subset),max_abs=max(r['abs_difference'] for r in subset),
                commands_with_different_flags=sum(r['observed_qbs_flags']!=r['modeled_rvv_aggregate_flags'] for r in flags),
                examples=[r for r in subset if not r['exact']][:8],
                block_evaluations=len(precision[kind]),
                max_abs_integer_dot=max(abs(r['integer_dot']) for r in precision[kind]),
                rvv_first_product='integer_dot_times_weight_scale' if kind else 'weight_scale_times_query_scale',
                rvv_first_product_rounded_blocks=sum(r['first_product_rounded' if kind else 'scale_product_rounded']
                                                     for r in precision[kind]),
                q4_first_product_max_abs_rounding=max(r['first_product_abs_rounding'] for r in precision[kind]) if kind else None,
                half_scale_product_rounded_blocks=sum(r['scale_product_rounded'] for r in precision[kind])))
        s.require(summaries[0]['bits_different']==summaries[0]['commands_with_different_flags']==0,
                  'Unexpected Q8_0 order-model contradiction; investigate before making equivalence claims')
        s.atomic_json(out/'comparisons.json',comparisons)
        s.atomic_json(out/'command-flags.json',command_comparisons)
        s.merge_pins(pins,s.hashes([library,out/'compile.command.json',out/'compile.log',
                                   out/'comparisons.json',out/'command-flags.json']))
        s.verify_pins(pins); s.atomic_json(out/'source-pins.json',pins)
        s.atomic_json(out/'result.json',dict(state='HOST_RVV_ORDER_ANALYZED',summaries=summaries,
            actual_rvv_anchor_scores=16,modeled_rvv_score_comparisons=3336,native_qbs_scores=3336,
            per_score_hardware_flags_observed=False,observed_flags_granularity='Per-command OR',
            full_native_rvv_matrix_execution=False,whole_attention_accepted=False,
            source_pins_sha256=s.digest(out/'source-pins.json'),post_pins_match=True,
            scope='Host FP-order model anchored to pinned target instructions and sixteen actual RVV results; not a new RTL matrix test'))
        print(summaries)
    except BaseException as exc:
        s.atomic_json(out/'result.json',dict(state='FAIL',error=repr(exc)))
        raise


if __name__=='__main__':
    main()
