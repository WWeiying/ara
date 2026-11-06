"""Check complete SDK triplet work, real-data signatures and architectural state."""
import re

from audit import require
from check_projection_native import checksum, fields
from collect_projection_native import PHASES

SCOPE = 'FFN_NATIVE_SCOPE m=4 n=128 k0=2048 k1=2048 k2=6144 trials=1 parts=3 shared_gate_up_preparation=1 full_ggml=0'


def check(text, wide, golden, packed, profiles, flags):
    require(wide in (0,1) and len(golden) == len(profiles) == len(flags) == 3 and
            all(len(g) == 2048 for g in golden) and list(map(len,packed)) == [9344,28032] and
            all(p in (1,2) for p in profiles) and all(0 <= f < 32 for f in flags), 'FFN oracle geometry')
    require(not re.search(r'Fatal:|Error:|^UVM_(?:ERROR|FATAL)\s+@',text,re.M) and
            'FFN_NATIVE_FAIL' not in text and text.splitlines().count(SCOPE) == 1, 'Simulation/scope failure')
    def rows(tag): return [fields(s,tag) for s in text.splitlines() if s.startswith(tag+' ')]
    prep, parts, result, commands = (rows(t) for t in ('FFN_NATIVE_PREP','FFN_NATIVE_PART','FFN_NATIVE_RESULT','[QBS_PERF]'))
    require((len(prep),len(parts),len(result),len(commands)) == (2,3,1,12), 'Incomplete SDK triplet')
    for stage,row in enumerate(prep):
        expected = dict(stage=stage,k=(2048,6144)[stage],fcsr=9 if stage == 0 else 9|flags[0]|flags[1],
                        valid=1,checksum=checksum(packed[stage]))
        require(all(row.get(k) == v for k,v in expected.items()) and row['cycles'] > 0, 'Quantized payload/state mismatch')
    fc = 9
    for part,row in enumerate(parts):
        fc |= flags[part]
        expected = dict(part=part,profile=profiles[part],k=(2048,2048,6144)[part],
                        fcsr=fc,vcsr=5,checksum=checksum(golden[part]),errors=0)
        require(all(row.get(k) == v for k,v in expected.items()) and row['execution'] > 0 and row['admission'] > 0,
                'Output/architectural state mismatch')
    total = result[0]
    require(total['commands'] == 12 and total['outputs'] == 1536 and total['errors'] == 0 and
            total['preparation'] == sum(p['cycles'] for p in prep) and
            total['admission'] == sum(p['admission'] for p in parts) and
            total['execution'] == sum(p['execution'] for p in parts) and
            total['region'] >= total['preparation']+total['admission']+total['execution'], 'SDK region accounting')
    for i,row in enumerate(commands):
        part = i//4; blocks = 24 if part == 2 else 8
        expected = dict(seq=i+1,m=4,n=32,vlen=1024,lanes=4,success=1,fault=0,validation_fault=0,read_fault=0,
                        useful_pairs=32768*blocks,dot_active_cycles=(512 if wide else 1024)*blocks,
                        activation_access=0,activation_bytes=1168*blocks,
                        weight_bytes=32*blocks*(144 if profiles[part] == 1 else 210))
        require(all(row.get(k) == v for k,v in expected.items()), 'Wrong command work')
        require(all('phase_'+p+'_cycles' in row for p in PHASES) and
                sum(row['phase_'+p+'_cycles'] for p in PHASES) == row['busy_cycles'], 'Command phase accounting')
    require(all(sum(c['busy_cycles'] for c in commands[p*4:p*4+4]) <= parts[p]['execution'] for p in range(3)),
            'QBS busy outside SDK interval')
    return dict(preparation=prep,parts=parts,total=total,commands=12,useful_pairs=5242880,
                qbs_busy_cycles=sum(c['busy_cycles'] for c in commands),
                dot_issue_count=sum(c['dot_active_cycles'] for c in commands),
                preparation_included=True,cold_weight_repack_included=False,full_k=True,full_n=False,
                full_ggml=False,whole_model=False,single_reset_trial=True)
