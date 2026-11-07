"""Check identical completion instrumentation for real RVV/native Decode calls."""
import re
import struct

from audit import require
from check_projection_native import checksum
from check_decode_rvv import fields, K, PROFILE

SCOPE = ('MATCHED_DECODE_SCOPE m=1 n=64 parts=7 stages=4 order=ABBA full_k=1 '
         'full_n=0 full_ggml=0 completion=csr_and_fence')
ORDER = (0,1,1,0)


def check(text, native, rvv, packed, flags):
    require(len(native)==len(rvv)==7 and all(len(r)==256 for r in (*native,*rvv)) and
            list(map(len,packed))==[2336,2336,7008,2336] and len(flags)==7 and
            all(type(f) is int and 0<=f<32 for f in flags), 'Matched oracle geometry')
    lines=text.replace('\r','').splitlines()
    require(lines.count(SCOPE)==1 and not re.search(
        r'MATCHED_DECODE_FAIL|Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@|mcause_val',text,re.M),
        'Matched scope or execution failure')
    def records(tag): return [fields(line,tag) for line in lines if line.startswith(tag+' ')]
    prep,parts,trials,ends=[records(tag) for tag in
        ('MATCHED_DECODE_PREP','MATCHED_DECODE_PART','MATCHED_DECODE_TRIAL','MATCHED_DECODE_RESULT')]
    require(tuple(map(len,(prep,parts,trials)))==(16,28,4) and ends==[
        dict(trials=4,native_commands=28,outputs_checked=1792,errors=0)], 'Missing/extra matched work')
    for trial,backend in enumerate(ORDER):
        selected_prep=prep[trial*4:trial*4+4]
        selected_parts=parts[trial*7:trial*7+7]
        for stage,row in enumerate(selected_prep):
            expected=dict(trial=trial,backend=backend,stage=stage,fcsr=9,vcsr=3,vstart=0,
                          checksum=checksum(packed[stage]),errors=0)
            require(set(row)==set(expected)|{'cycles'} and row['cycles']>0 and
                    all(row[k]==v for k,v in expected.items()), 'Matched preparation/state mismatch')
        wanted=9
        for part,row in enumerate(selected_parts):
            if backend: wanted|=flags[part]
            expected=dict(trial=trial,backend=backend,part=part,profile=PROFILE[part],k=K[part],
                          fcsr=wanted,vcsr=3,vstart=0,checksum=checksum((native if backend else rvv)[part]),errors=0)
            require(set(row)==set(expected)|{'admission','execution'} and row['admission']>0 and
                    row['execution']>0 and all(row[k]==v for k,v in expected.items()),
                    'Matched output/state/work mismatch')
        row=trials[trial]
        expected=dict(trial=trial,backend=backend,preparation=sum(r['cycles'] for r in selected_prep),
            admission=sum(r['admission'] for r in selected_parts),execution=sum(r['execution'] for r in selected_parts),
            commands=14 if backend else 0,q4_calls=0 if backend else 4,q6_calls=0 if backend else 192,outputs=448,errors=0)
        require(set(row)==set(expected)|{'region'} and all(row[k]==v for k,v in expected.items()) and
                row['region']>=row['preparation']+row['admission']+row['execution'],
                'Matched interval conservation/call count mismatch')
    a=[r for r in trials if r['backend']==0];b=[r for r in trials if r['backend']==1]
    return dict(trials=trials,preparation=prep,parts=parts,order=list(ORDER),
        speedups={k:sum(r[k] for r in a)/sum(r[k] for r in b)
                  for k in ('region','preparation','admission','execution')},
        warmed_rvv_region_speedup=2*a[-1]['region']/sum(r['region'] for r in b),
        native_commands=28,outputs_checked=1792,matched_csr_completion=True,
        complete_measured_region=True,cold_repack_included=False,whole_model=False,
        oracle_policy='Native QBS C-reference bits and separately executed exact RVV ISA bits',
        limitations=['One same-ELF ABBA per platform; no whole-model timing',
                     'Seven real N64 prefixes with full K, not full output dimensions',
                     'No assumed CSR-cycle correction or ISA-model timing'])


def oracle(build):
    root=build / 'oracle'
    native=[(root/f'native_{p}.bin').read_bytes() for p in range(7)]
    rvv=[(root/f'rvv_{p}.bin').read_bytes() for p in range(7)]
    packed=[(root/f'activation_{s}.bin').read_bytes() for s in range(4)]
    flags=struct.unpack('<7I',(root/'flags.bin').read_bytes())
    return native,rvv,packed,flags
