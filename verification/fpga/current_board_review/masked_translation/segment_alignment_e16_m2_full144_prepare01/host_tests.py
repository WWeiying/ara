#!/usr/bin/env python3
"""Full144 initializer/oracle equivalence and byte/phase/capability negatives."""
import ctypes as ct
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import model as m

def run(out):
    lib=ct.CDLL(str(out/'host.so'))
    lib.mx_reset.argtypes=[ct.c_uint]
    lib.mx_compare.restype=ct.c_uint64
    lib.mx_allowed.argtypes=[ct.c_uint64]*3
    arrays={n:(ct.c_uint8*8192).in_dll(lib,'mx_'+n) for n in ('input','memory','output','expected')}
    mask=(ct.c_uint8*128).in_dll(lib,'mx_mask')
    scene=(ct.c_uint64*4).in_dll(lib,'mx_scene')
    ret=ct.c_uint64.in_dll(lib,'mx_return')
    target=ct.c_uint64.in_dll(lib,'mx_current_target');target.value=0x80001234
    negative=0;seen=[]
    for c in m.cases():
        # Contaminate every byte to prove no prior child's data leaks through reset.
        for a in arrays.values(): ct.memset(ct.addressof(a),0xa6,8192)
        lib.mx_reset(c['id'])
        gold=m.expected(c)
        m.require(gold==m.independent_expected(c),'Independent byte/halfword oracles')
        initial=dict(input=m.INPUT,memory=m.FILL if c['store'] else m.MEMORY,output=m.FILL,expected=gold)
        for n,want in initial.items(): m.require(bytes(arrays[n])==want,'Full reset '+n)
        m.require(bytes(mask)==bytes([0 if c['off'] else 255])*128,'Full128 predicate')
        actual=arrays['memory' if c['store'] else 'output']
        ct.memmove(ct.addressof(actual),gold,8192);ret.value=0;scene[0]=2
        m.require(lib.mx_compare()==0,'Packed positive differs')
        # Every byte lane plus external and internal field/tail boundaries.
        positions=sorted(set(list(range(8))+list(range(56,72))+list(range(8192-8,8192))+
                             [64+f*256+x for f in range(c['nf']) for x in (0,1,254,255)]))
        for at in positions:
            actual[at]^=1;scene[1]=scene[2]=scene[3]=0
            m.require(lib.mx_compare()==1 and scene[1]==at and scene[2]==gold[at] and
                      scene[3]==(gold[at]^1),'First byte/guard/tail corruption swallowed')
            actual[at]^=1;negative+=1
        # Multiple-byte mismatch counts and first byte (not first word only).
        actual[63]^=4;actual[8191]^=2
        m.require(lib.mx_compare()==2 and scene[1]==63,'Multi-error byte order/count')
        actual[63]^=4;actual[8191]^=2;negative+=1
        ret.value=1;scene[1]=scene[2]=scene[3]=0
        m.require(lib.mx_compare()==1 and scene[1]==0,'Original nonzero-vstart failure')
        ret.value=0;negative+=1
        eligible=bool(c['offset'] and c['vl'] and not c['off'])
        cause=6 if c['store'] else 4
        m.require(bool(lib.mx_allowed(cause,target.value,1))==eligible,'Capability geometry')
        for badcause,badpc,phase in ((cause,target.value-4,1),(cause,target.value+4,1),
                                   (cause,target.value,0),(cause,target.value,2),
                                   (13,target.value,1),(15,target.value,1),
                                   (2,target.value,1),(4 if c['store'] else 6,target.value,1)):
            m.require(not lib.mx_allowed(badcause,badpc,phase),'Non-target/wrong phase/page trap waived')
            negative+=1
        seen.append(dict(case=c['id'],oracle_sha256=m.sha_bytes(gold) if hasattr(m,'sha_bytes') else __import__('hashlib').sha256(gold).hexdigest(),
                         full_bytes_checked=8192,capability_eligible=eligible))
    m.require(len(seen)==144 and sum(x['capability_eligible'] for x in seen)==24,'Full144 membership')
    result=dict(status='HOST_FULL144_EQUIVALENT_NOT_REFERENCE_OR_DUT',cases=144,
                initialized_bytes=144*4*8192,predicate_bytes=144*128,positive_oracle_bytes=144*8192,
                negative_checks=negative,case_oracles=seen)
    with (out/'host.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k!='case_oracles'}))

if __name__=='__main__':run(Path(sys.argv[1]))
