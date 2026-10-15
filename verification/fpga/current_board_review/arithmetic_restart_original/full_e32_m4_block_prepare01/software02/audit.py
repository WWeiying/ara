"""Actual linked artifacts and weighted full positive CFG, no reference run."""
import collections
import hashlib
import json
from pathlib import Path
import re
import struct
import time
from leaf_cfg import Leaf,old,require
from main_cfg import main_bound
HERE=Path(__file__).resolve().parent
A=HERE.parents[1]
MODEL=A/'full_e32_m4_source_model01/generated01'
read,sha,save=old.read,old.sha,old.save

def analyze(root,rows,gold):
    f=read(root/'functions.json');s=read(root/'symbols.json');raw=(root/'program.elf').read_bytes()
    machine=Leaf(f,s,raw);code={x['pc']:x for v in f.values() for x in v};helperpcs=set();joined=bytearray()
    original=read(HERE.parent/'software01/soc/functions.json');previous=s['capacity']
    for name in ['capacity']+[f'op_{i}' for i in range(35)]:
        require([x['insn'] for x in f[name]]==[x['insn'] for x in original[name]],'Original source/ELF helper window '+name)
        for x in f[name]:
            require(x['pc']==previous,'Contiguous source-order helper region');previous+=len(old.instruction_bytes(x))
            joined.extend(old.instruction_bytes(x));helperpcs.add(x['pc'])
    require(len(helperpcs)==458 and hashlib.sha256(joined).hexdigest()=='d44dea9535d297c3c6dc1894db7086c82ca5fb1ec8c32a4f891450b7676c417e','Full original region identity')
    for x in code.values():require(old.executable_bytes(raw,x['pc'],len(old.instruction_bytes(x)))==old.instruction_bytes(x),'File-backed actual code bytes')
    extra=[x for p,x in code.items() if p not in helperpcs and x['insn']&3==3 and
        (x['insn']&127==0x57 or (x['insn']&127 in (7,39) and (x['insn']>>12)&7 in (0,5,6,7)))]
    require(not extra,'No extra RVV')
    own=[x for n,w in f.items() if n.startswith('e32m4_') or n in ('arithmetic_main','number','failure.part.0') for x in w]
    require(not [x for x in own if x['insn']&3==3 and (x['insn']&127==0x0f or (x['insn']&127==0x73 and (x['insn']>>12)&7))],'No new scalar CSR/fence')
    for filename,sym in [('dictionary64.bin','e32m4_expected_blocks'),('indices_u16le.bin','e32m4_expected_ids'),('fp_expected640_u32le.bin','fp_expected'),('fp_inputs8_u32le.bin','fp_inputs')]:
        data=(MODEL/filename).read_bytes()
        require(machine.initial(s[sym],len(data)).to_bytes(len(data),'little')==data,'Symbol-qualified exact payload '+filename)
    names={k:next(n for n in f if n.startswith('e32m4_'+k)) for k in ('packed','initialize_output','refresh_fp','initialize_mask')}
    packed=f[names['packed']];pcode={x['pc']:x for x in packed};static=collections.Counter(x['op'] for x in packed)
    require(static['beq']==72 and static['li']==66 and static['sext.w']==1 and static['ret']==1,'Exact linked65 comparator pairs and7 tags')
    require(not any(x['op'] in ('sd','sw','sb') for x in packed),'Actual cache has no stack/cache spill writes')
    def check_cache(cfg,row):
        ev=cfg['events'];actual=[e for e in ev if e['kind']=='OUT'];wanted=[e for e in ev if e['kind']=='GOLD'];ids=[e for e in ev if e['kind']=='ID']
        require([e['address']-s['out'] for e in actual]==list(range(0,520,8)) and all(e['op']=='ld' for e in actual),'All65 actual LD in order including final8')
        require([e['address']-s['e32m4_expected_ids'] for e in ids]==[18*(row['ordinal']-1)+2*i for i in range(9)],'Exact9 per-call ID addresses')
        require([e['value'] for e in ids]==row['ids'] and all(e['op']=='lhu' for e in ids),'Exact9 ID values')
        addresses=[];last=None
        for i,b in enumerate(row['ids']):
            if i==8:addresses.append(s['e32m4_expected_blocks']+64*b)
            elif b!=last:addresses.extend(s['e32m4_expected_blocks']+64*b+8*j for j in range(8))
            last=b
        require([e['address'] for e in wanted]==addresses,'First unconditional fill / same-ID cache / full refresh / tail')
        comparisons=[b for b in cfg['branches'] if b['taint']==['GOLD','OUT']];tags=[b for b in cfg['branches'] if b['taint']==['ID']]
        require(len(comparisons)==65 and len(tags)==7,'Every actual paired comparison and tag')
        require([b['taken'] for b in tags]==[row['ids'][i]==row['ids'][i+1] for i in range(7)],'Exact tag decision independent of sticky error')
        return actual,wanted,ids,comparisons,tags
    totals=collections.Counter();pcvisits=collections.Counter();cost=[];pairs=None
    for i,row in enumerate(rows):
        cfg=machine.walk(names['packed'],s['e32m4_expected_ids']+18*i,gold[520*i:520*(i+1)])
        actual,wanted,ids,comparisons,tags=check_cache(cfg,row)
        require(cfg['return_value']==0 and all(b['taken'] and b['sticky']==0 for b in comparisons),'Every positive comparison preserves0')
        cost.append(cfg['instructions']);pcvisits.update(cfg['pcs'])
        totals.update(actual_LD=len(actual),expected_LD=len(wanted),ID_LHU=len(ids),hit=sum(b['taken'] for b in tags),miss=1+sum(not b['taken'] for b in tags))
        if pairs is None:pairs=comparisons
    require(tuple(totals[k] for k in ('actual_LD','expected_LD','ID_LHU','hit','miss'))==(389025,124041,53865,33123,14757),'Exact whole cache events')
    proof=[]
    for b in pairs:
        pc=int(b['pc'],16);branch=pcode[pc];w=branch['insn'];li=pcode[pc+4]
        require(w&127==0x63 and (w>>12)&7==0,'Actual64-bit BEQ opcode')
        offset=old.sign((((w>>31)&1)<<12)|(((w>>7)&1)<<11)|(((w>>25)&63)<<5)|(((w>>8)&15)<<1),13)
        require(li['insn']==0x4505 and li['op']=='li' and li['args']=='a0,1' and offset==6,'BEQ skips precisely C.LI a0,1')
        require(((w>>15)&31)!=10 and ((w>>20)&31)!=10,'Sticky output distinct from both live compare inputs')
        require(int(branch['args'].split(',')[-1].split()[0],16)==pc+offset,'Encoded branch target matches decoded label')
        proof.append(dict(pc=b['pc'],BEQ=hex(w),LI=hex(li['insn']),next_pc=hex(pc+6),truth_table=[dict(before=bad,equal=eq,after=bad if eq else 1) for bad in (0,1) for eq in (False,True)]))
    require([x['args'] for x in packed if x['op']=='sext.w']==['a0,a0'] and [x['args'] for x in packed if x['op']=='li'].count('a0,0')==1,'Canonical unsigned sticky0/1 and final32-bit extension')
    negatives=[]
    mixed=next(i for i,r in enumerate(rows) if any(r['ids'][k]==r['ids'][k+1] for k in range(7)) and any(r['ids'][k]!=r['ids'][k+1] for k in range(7)))
    for offsets in ([0],[260],[519],[0,519],[0,260,519],[4],[512]):
        row=rows[mixed];data=bytearray(gold[520*mixed:520*(mixed+1)])
        for o in offsets:data[o]^=0x80
        cfg=machine.walk(names['packed'],s['e32m4_expected_ids']+18*mixed,data)
        _,_,_,comparisons,_=check_cache(cfg,row);bad=0
        for b in comparisons:
            require(b['sticky']==bad,'Sticky prior0/1 tracks all previous failures')
            bad|=int(not b['taken'])
        require(cfg['return_value']==bad==1,'Actual linked inequality returns1 after all65 reads')
        negatives.append(dict(offsets=offsets,ordinal=mixed+1,instructions=cfg['instructions'],all65_actual_reads=True,return_value=1))
    init=machine.walk(names['initialize_output'],0);ev=[e for e in init['events'] if e['kind']=='OUT']
    require([e['address']-s['out'] for e in ev]==list(range(0,520,8)) and all(e['op']=='sd' and e['value']==0x5b0000005b for e in ev),'65 exact initialization SD')
    fp={};mask={};inputs=list(struct.unpack('<8I',(MODEL/'fp_inputs8_u32le.bin').read_bytes()))
    for seed in range(3):
        cfg=machine.walk(names['refresh_fp'],seed);stores=[e for e in cfg['events'] if e['kind'] in ('A','B')];loads=[e for e in cfg['events'] if e['kind']=='FP']
        want=[(s[bank]+4*i,inputs[((i if bank=='a' else 3*i)+seed)%8]) for i in range(128) for bank in ('a','b')]
        require([(e['address'],e['value']) for e in stores]==want and all(e['op']=='sw' for e in stores),'All256 ordered original FP SW')
        require([e['address']-s['fp_inputs'] for e in loads]==list(range(0,32,4)) and all(e['op']=='lw' for e in loads),'8 fresh per-call FP inputs')
        fp[seed]=cfg
    for mode in range(3):
        cfg=machine.walk(names['initialize_mask'],mode);events=[e for e in cfg['events'] if e['kind']=='MASK']
        require([(e['address']-s['mask'],e['op'],e['value']) for e in events[:16]]==[(i,'sd',0) for i in range(0,128,8)],'128B fullclear first')
        shadow=bytearray(128);want=[]
        for i in range(128):
            if mode==0 or (mode==1 and i%2) or (mode==2 and i%7==2):
                shadow[i//8]|=1<<(i%8);want.append((s['mask']+i//8,'sb',shadow[i//8]))
        require([(e['address'],e['op'],e['value']) for e in events[16:]]==want,'All ordered cumulative constant SB; no obsolete LBU requirement')
        mask[mode]=cfg
    leaves=dict(output=init['instructions'],FP={k:v['instructions'] for k,v in fp.items()},mask={k:v['instructions'] for k,v in mask.items()})
    main=main_bound(machine,f,s,rows,cost,leaves,read(MODEL/'seed_inputs.json'))
    # Startup is straight-line apart from its exact BSS zero loop. Bound every
    # startup PC once per BSS loop, deliberately more than actual4/word.
    startup=f['_start'];require(sum(x['op']=='bgeu' for x in startup)==1 and sum(x['op']=='j' for x in startup)==2,'Known startup clear/return structure')
    loop=next(x for x in startup if x['op']=='bgeu');body=[x for x in startup if x['pc']>loop['pc']][:3]
    require([(x['op'],x['args']) for x in body[:2]]==[('sd','zero,0(t0)'),('addi','t0,t0,8')] and body[2]['op']=='j' and int(body[2]['args'].split()[0],16)==loop['pc'],'Actual BSS clear loop')
    require(loop['args'].startswith('t0,t1,'),'Exact clear-loop bounds registers')
    for reg,sym in [('t0','__bss_start'),('t1','__bss_end')]:
        end=max(i for i,x in enumerate(startup) if x['pc']<loop['pc'] and x['op']=='addi' and x['args'].startswith(reg+','+reg+','))
        pair=startup[end-1:end+1]
        require(pair[0]['op']=='auipc' and pair[0]['args'].startswith(reg+','),'Actual BSS base setup')
        pointer=pair[0]['pc']+old.sign((int(pair[0]['args'].split(',')[1],0)<<12)&0xffffffff,32)+int(pair[1]['args'].split('#')[0].strip().split(',')[-1],0)
        require(pointer==s[sym],'Actual linked BSS bound '+sym)
    startup_upper=len(startup)*(1+(s['__bss_end']-s['__bss_start']+7)//8)
    terms=main['terms'];terms['startup_upper']=startup_upper;terms['main_trampoline']=len(f['main']);terms['runtime_exit_through_completion']=len(f['replay_exit'])
    upper=sum(terms.values());gap=s['__stack_top']-s['__bss_end']
    frames=[dict(pc=hex(x['pc']),bytes=-int(x['args'].split('#')[0].strip().split(',')[-1])) for x in code.values() if x['op']=='addi' and x['args'].startswith('sp,sp,-')]
    require(gap>=65536 and sum(x['bytes'] for x in frames)<65536,'Actual linked stack reserve and all frame allocations')
    return dict(elf_sha256=sha(root/'program.elf'),whole_positive_upper=upper,within3M=upper<=3000000,main=main,leaf_costs=leaves,
        cache_total_instructions=sum(cost),cache_PC_visits={hex(k):v for k,v in sorted(pcvisits.items())},cache_per_call=cost,
        cache_events=dict(totals),asm_pairs=proof,linked_negative_paths=negatives,leaf_paths=dict(output=init,FP=fp,mask=mask),
        frames=frames,cache_frame=0,cache_stack_transfers=0,stack_gap=gap,gp=hex(machine.gp),helper_instructions=458,
        extra_RVV=0,new_scalar_CSR_fence=0,FP_SW=483840,mask_SB=154350,mask_clear_SD=35280,output_SD=389025)

def main():
    start=time.monotonic();out=HERE/'artifact01';out.mkdir(exist_ok=False)
    pins=read(HERE/'preflight.json')['pins']
    for p in HERE.rglob('*'):
        if p.is_file() and out not in p.parents and HERE/'audit_execution01' not in p.parents:pins[str(p)]=sha(p)
    for p,h in pins.items():require(sha(p)==h,'Actual pre-audit pins '+p)
    save(out/'INPUT_PINS.json',pins)
    receipt=read(HERE/'execution_receipt.json');require(type(receipt['returncode'])is int and receipt['returncode']==0 and not receipt['timed_out'],'Actual Host/two-build outcome')
    host=read(HERE/'host_result.json');require(len(host['runs'])==46,'46 actual Host runs')
    for r in host['runs']:require(type(r['returncode'])is int and r['returncode']==r['expected_returncode'] and not r['timed_out'] and sha(r['log'])==r['sha256'],'Host receipt/log identity')
    require(host['short']['returncode']==0 and not host['short']['timed_out'],'Actual short Host outcome')
    rows=read(MODEL/'calls.json');gold=(MODEL/'gold_u32le.bin').read_bytes();results={}
    require(len(rows)==5985 and len(gold)==5985*520,'Full source ledger')
    for backend in ('soc','spike'):
        print('ANALYZE '+backend,flush=True);root=HERE/backend;rc=read(root/'compile.log.exit.json')
        require(type(rc['returncode'])is int and rc['returncode']==0 and not rc['timed_out'],'Actual backend compile0')
        result=analyze(root,rows,gold);save(out/(backend+'.json'),result)
        results[backend]=dict(elf_sha256=result['elf_sha256'],whole_positive_upper=result['whole_positive_upper'],within3M=result['within3M'],terms=result['main']['terms'])
    for p,h in pins.items():require(sha(p)==h,'Post audit drift '+p)
    save(out/'PINS.json',pins)
    result=dict(status='ACTUAL_LINKED_CFG_PASS_PENDING_INDEPENDENT_REVIEW' if all(r['within3M'] for r in results.values()) else 'ACTUAL_LINKED_CFG_COST_HOLD',
        backends=results,host_runs=46,short_host_cases=6,pins_unchanged=True,pin_count=len(pins),reference_executed=False,DUT_executed=False,
        cost_scope='Full successful source history conditional scalar CFG, not retired/architectural validation; source error fallback retained, not successful-path cost',elapsed_seconds=time.monotonic()-start)
    save(out/'RESULT.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
