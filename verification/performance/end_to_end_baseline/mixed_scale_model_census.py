#!/usr/bin/env python3
"""Dynamic-MUL-weighted eligibility on accepted real Prefill/Decode scale bytes."""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct

from audit import digest, require, verify_pins
from run_supply_sdk import PROGRAMS, bind
from prepare_wide_soc import ROOT, HERE, RUNS

NAMES = ('attn_q','attn_v','attn_k','ffn_gate','ffn_up','ffn_down','vocabulary')
STAGE = (0,0,0,1,1,2,3)


def half_expand(bits):
    e = (bits >> 10) & 31; f = bits & 1023; sign = (bits & 0x8000) << 16
    if e == 0:
        if not f: return sign
        top = f.bit_length()-1
        return sign | ((top+103)<<23) | ((f<<(23-top)) & 0x7fffff)
    if e == 31: return sign | 0x7f800000 | (f<<13) | (0x400000 if f else 0)
    return sign | ((e+112)<<23) | (f<<13)


def eligible(a, w, expanded=False):
    ea, ew = (a>>23)&255, (w>>23)&255
    base = ea+ew-127
    return 0<ea<255 and (103 if expanded else 113)<=ew<=142 and not(w&8191) and 1<=base<=252


def count_scales(weights, activations, n, blocks, profile):
    size, offsets = (144,(0,2)) if profile == 'Q4_K' else (210,(208,))
    require(profile in ('Q4_K','Q6_K') and len(weights)==n*blocks*size and
            activations and all(len(row)==blocks for row in activations), 'Exact native scale geometry required')
    counters = Counter()
    for row in activations:
        for col in range(n):
            for block, a in enumerate(row):
                for offset in offsets:
                    half = struct.unpack_from('<H',weights,(col*blocks+block)*size+offset)[0]
                    w = half_expand(half); counters['scale_mul'] += 1
                    counters['normal_admitted'] += eligible(a,w)
                    counters['expanded_admitted'] += eligible(a,w,True)
                    if ((half>>10)&31)==0 and half&1023: counters['weight_half_subnormal'] += 1
                    if half&0x7fff==0: counters['weight_zero'] += 1
    total = counters['scale_mul']
    require(total == len(activations)*n*blocks*len(offsets), 'Scale operation conservation')
    return {**counters, 'normal_fraction':counters['normal_admitted']/total,
            'expanded_fraction':counters['expanded_admitted']/total}


def run(output):
    out = output.absolute(); require(out==out.resolve() and out.is_relative_to(RUNS), 'Fresh verification output required')
    out.mkdir(parents=True, exist_ok=False); pins={}
    def pin(p,s=None): bind(pins,p,s)
    result=dict(state='PREPARING', performance_measured=False, rtl_executed=False,
                scope='Accepted real Qwen3 first-layer/output slices, not model-wide activity')
    try:
        for p in (Path(__file__),HERE/'test_mixed_scale_model_census.py',ROOT/'verification/qbs/qbs_ref.h'):
            pin(p)
        rows=[]
        for phase in ('decode','prefill'):
            name,sha,state,_,_=PROGRAMS[phase]; build=RUNS/name
            pin(build/'build.json',sha); report=json.loads((build/'build.json').read_text())
            require(report['state']==state, 'Accepted real native benchmark required')
            pin(build/'source-pins.json',report['source_pins_sha256'])
            inventory=json.loads((build/'source-pins.json').read_text())
            def payload(path):
                p=Path(path); key=str(p.resolve()); expected=inventory.get(key,report['artifacts'].get(key))
                require(expected is not None,'Unpinned real payload'); pin(p,expected); return p.read_bytes()
            if phase=='decode':
                capture=Path(report['capture']); pin(capture/'result.json')
                details=json.loads((capture/'result.json').read_text())
                require(details['activation']['phase']=='decode' and details['activation']['input_differs_from_prefill'],
                        'Not a genuine post-Prefill Decode capture')
                data={}
                for stage in range(4):
                    raw=payload(build/f'activation_{stage}.bin'); blocks=24 if stage==2 else 8
                    require(len(raw)==292*blocks,'Q8_K row size')
                    data[stage]=[[struct.unpack_from('<I',raw,b*292)[0] for b in range(blocks)]]
                by_name={Path(w['file']).stem:w for w in details['weights']}
                for i,name in enumerate(NAMES):
                    w=by_name[name]; path=capture/w['file']; pin(path,w['sha256']); raw=path.read_bytes()
                    rows.append(dict(phase=phase,part=name,profile=w['type'],m=1,n=w['captured_n'],k=w['k'],
                        **count_scales(raw,data[STAGE[i]],w['captured_n'],w['k']//256,w['type'])))
            else:
                raw=payload(build/'activation_q8k_m4.bin')
                require(len(raw)==8*1168,'Q8_K M4 interleaved blocks')
                scales=[[struct.unpack_from('<I',raw,b*1168+r*4)[0] for b in range(8)] for r in range(4)]
                for name,n,profile in (('attn_q',2048,'Q4_K'),('attn_k',1024,'Q4_K'),('attn_v',1024,'Q6_K')):
                    rows.append(dict(phase=phase,part=name,profile=profile,m=4,n=n,k=2048,
                        **count_scales(payload(build/(name+'.bin')),scales,n,8,profile)))
        totals={}
        for phase in ('decode','prefill'):
            selected=[r for r in rows if r['phase']==phase]
            total={k:sum(r.get(k,0) for r in selected) for k in
                ('scale_mul','normal_admitted','expanded_admitted','weight_half_subnormal','weight_zero')}
            total.update(normal_fraction=total['normal_admitted']/total['scale_mul'],
                         expanded_fraction=total['expanded_admitted']/total['scale_mul']); totals[phase]=total
        require(totals['decode']['scale_mul']==13312 and totals['prefill']['scale_mul']==229376,
                'Dynamic scale work does not match actual measured native commands')
        verify_pins(pins); result.update(state='REAL_MODEL_MIXED_SCALE_ELIGIBILITY_CHECKED', rows=rows,totals=totals,
            post_pins_match=True,limits=['Eligibility weighted by scale operations, not commands or cycles',
                'Expanded-subnormal admission is a prospective arithmetic-domain extension, not RTL acceptance',
                'No QBS/AKV arithmetic order, production library or model data changed'])
    except BaseException as exc: result.update(state='FAIL',error=repr(exc)); raise
    finally:
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
        result['source_pins_sha256']=digest(out/'source-pins.json')
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result.get('totals',result),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
