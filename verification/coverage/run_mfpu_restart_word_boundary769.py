"""One frozen 600s run; strict automatic qualification, never automatic admission."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import prepare_mfpu_restart_word_boundary as gold
import verify_mfpu_restart_word_boundary_preflight as precheck
import run_pure_war_simulation as runner
import qualify_operand_mask_data_timeout_offline as decode
import qualify_pure_war_parent_terminal as generic
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap

life, require = gold.life, gold.require
OUT = life.OUT/'mfpu-restart-word-boundary-old-image769-agent-20261007-01'
QUAL = OUT.with_name(OUT.name+'-qualified')
NAME = 'mfpu_restart_word_boundary_e16m8'
ACCEPT_SHA = '2729b8024b22d811bc156445475f5d4dda65c15d98eac555fd1643004060e85d'
BASE = life.OUT/'tlb-asid-vpn-rsw-offline-admitted-769-agent-20261007-01'
BASE_SHA = 'b6bd6cca9a31b67b38ae834bfb5736ed04c31f14302efeac2440657147317ecf'
PREPARED = OUT.with_name(OUT.name+'.prepared.json')
shared = gold.reused.reused.old.shared.shared


def baseline():
    manifest = life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(manifest['coverage_admitted'] is True,'Formal769 must be admitted')
    paths = [BASE/name for name in ('combined-inputs.txt','combined-bits.json')]
    for path in paths: require(life.digest(path)==manifest['output_pins'][str(path)],'Formal769 output drift')
    ledger = paths[0].read_text().splitlines()
    require(len(ledger)==len(set(ledger))==770 and ledger[0]==str(life.IMAGE)+'.vdb','Exact769 ledger')
    return manifest,ledger


def command(output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(gold.OUT/'input.elf'),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME]


def prepare():
    require(not OUT.exists(),'One fresh run only')
    accepted = life.read_bound(gold.OUT/'acceptance.json',ACCEPT_SHA);life.check(accepted['pins'])
    require(accepted['tests_passed']==10 and accepted['tests_skipped']==0 and not accepted['DUT_launched'],'Exact authorized preflight')
    pre = life.read_bound(gold.OUT/'preflight.json',precheck.PREFLIGHT_SHA)
    commits = shared.spike_trace.parse_spike_commits(gold.OUT/'spike.trace')
    require(precheck.context_check(commits,pre['symbols'])==accepted['context'],'Actual context replay')
    require(gold.validate_commits(commits,pre['symbols'],pre['instruction'])==pre['checks'],'Actual oracle replay')
    base,ledger = baseline()
    plan = life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(plan['image'])==66 and plan['simv']==str(life.IMAGE)
            and plan['image'][str(life.IMAGE)]==runner.IMAGE_SEAL,'Frozen66 image')
    pins = life.merge_pins(accepted['pins'],plan['image'])
    files = [Path(__file__).resolve(),Path(__file__).with_name('test_run_mfpu_restart_word_boundary769.py'),
             Path(runner.__file__),Path(decode.__file__),Path(generic.__file__),Path(toggle.__file__),
             Path(toggle.base.__file__),Path(bitmap.__file__),Path(life.__file__),life.PLAN,
             gold.OUT/'acceptance.json',BASE/'admission-manifest.json',BASE/'combined-inputs.txt',BASE/'combined-bits.json']
    files += sorted((life.ROOT/'verification/ara_verify').glob('*.py'))
    pins = life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    require(str(OUT/'code.vdb') not in ledger and pre['symbols']['tohost']==0x80001000,'Independent test and terminal')
    record = dict(case=NAME,command=command(OUT),output=str(OUT),timeout_s=600,pins=pins,
        preflight=pre,baseline=769,baseline_seal=BASE_SHA,no_FSDB=True,automatic_retry=False,
        coverage_admitted=False,RTL_changed=False,authorization='USER_SINGLE_FROZEN_600S_RUN_AFTER_ACCEPTANCE',
        elf_sha256=life.digest(gold.OUT/'input.elf'),image_sha256=runner.IMAGE_SEAL)
    life.save(PREPARED,record)
    print(json.dumps({'prepared':str(PREPARED),'seal':life.digest(PREPARED),'pins':len(pins)}))


def scalar_check(rows, reference, symbols):
    retired = [r for r in rows if r['event']=='retire']
    require(len(retired)==len(reference)>0,'Complete scalar reference length')
    regs = dict.fromkeys(range(32),0);memory={};reads=set();terminals=[]
    for i,(r,c) in enumerate(zip(retired,reference)):
        require(int(r['order'])==i and not int(r['trap']) and
                (int(r['pc'],16),int(r['insn'],16))==(c.pc,c.instruction),'Scalar PC/order/opcode/trap')
        actual = {int(r['rd']):int(r['rd_wdata'],16)} if int(r['rd']) else {}
        require(not c.fpr_writes and actual=={k:v for k,v in c.gpr_writes.items() if k},'Full scalar GPR/CSR comparison')
        d = decode.memory_decode(c.instruction)
        rm,wm = int(r['mem_rmask'],16),int(r['mem_wmask'],16)
        if d:
            address = (regs[d['base']]+d['offset']) & ((1<<64)-1)
            width=d['size'];mask=((1<<width)-1)<<(address&7)
            require(int(r['mem_addr'],16)==address and address%width==0 and mask<=255,'Full scalar effective address')
            if d['kind']=='write':
                value=regs[d['register']] & ((1<<(width*8))-1)
                require(c.memory_accesses==((address,value),) and rm==0 and wm==mask and
                        int(r['mem_wdata'],16)&((1<<(width*8))-1)==value,'Full scalar store')
                if address==symbols['tohost']:terminals.append((i,width,value))
            else:
                require(c.memory_accesses==((address,None),) and rm==mask and wm==0 and d['register'] in actual,'Full scalar load')
                value=actual[d['register']] & ((1<<(width*8))-1)
                reads.update(range(address,address+width))
            memory.update({address+k:b for k,b in enumerate(value.to_bytes(width,'little'))})
        else:
            require(rm==wm==0,'Unknown scalar memory effect')
            require(not c.memory_accesses or c.instruction&127 in (7,0x27),'Unverified memory instruction')
        regs.update(actual);regs[0]=0
    require(terminals==[(len(reference)-1,8,1)],'Exact final terminal store')
    return memory,reads


def lifecycle(rows,vectors):
    starts={};pending={};live={};history=defaultdict(list);req=[];resp=[];alloc=Counter();done=Counter()
    for r in rows:
        seq,tid,cycle,event=int(r['order']),int(r['trans_id']),int(r['cycle']),r['event']
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Duplicate live architectural request')
            starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1] and r['insn']==starts[pending[tid][0]]['insn'],'Unowned request')
            pending[tid][1]=True;req.append((cycle,tid,int(r['insn'],16)))
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and seq==-1 and
                    int(r['pc'],16)==int(r['insn'],16)==int(r['trap'])==0,'Unowned response')
            pending.pop(tid);resp.append((cycle,tid))
        elif event in ('uop_alloc','uop_done'):
            vid=int(r['port']);require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id']) and r['insn']==starts[seq]['insn'],'Backend identity')
            if event=='uop_alloc':
                require(vid not in live,'Live SID reuse');entry=dict(seq=seq,start=cycle,end=None)
                live[vid]=entry;history[vid].append(entry);alloc[seq,vid,cycle]+=1
            else:
                require(vid in live and live[vid]['seq']==seq,'Unowned completion')
                live.pop(vid)['end']=cycle;done[seq,vid,cycle]+=1
    require(not pending and not live and len(req)==len(resp)==len(starts)>0 and
            Counter((s,v) for s,v,_ in alloc.elements())==Counter((s,v) for s,v,_ in done.elements()),'Incomplete lifecycle')
    va=Counter();vd=Counter();metadata={};last=-1
    for r in vectors:
        cycle,seq,vid,event=int(r['cycle']),int(r['arch_seq']),int(r['vid']),r['event']
        require(cycle>=last and (int(r['nr_lanes']),int(r['vlen_bits']))==(4,1024),'Native ordering/geometry');last=cycle
        if event=='config':continue
        require(seq in starts and r['insn']==starts[seq]['insn'],'Native owner/opcode')
        if event=='alloc':
            key=seq,vid,cycle;require(key not in metadata,'Duplicate native allocation');metadata[key]=r;va[key]+=1
        else:
            owners=[h for h in history[vid] if h['start']<cycle] or [h for h in history[vid] if h['start']==cycle]
            require(owners,'Missing SID owner');h=owners[-1];key=h['seq'],vid,h['start']
            require(h['seq']==seq and h['end'] is not None and h['start']<=cycle<=h['end'] and key in metadata,'Native completion/write ownership')
            require(all(r[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Native metadata')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(event=='write' and int(r['use_vd'])==1 and 0<=int(r['lane'])<4 and 0<=int(r['source'])<5,'Native write type')
    require(va==alloc and vd==done,'Exact native/backend lifecycle')
    targets=[r for r in metadata.values() if int(r['insn'],16)==gold.OPCODE]
    require(len(targets)==12 and [int(r['vstart']) for r in targets]==list(gold.STARTS) and
            all((int(r['vd']),int(r['eew']),int(r['vl']))==(24,1,512) for r in targets),'Twelve actual restart configurations')
    return dict(requests=len(req),responses=len(resp),backend_uops=sum(alloc.values())),req,resp


def protocol(text,req,resp,terminal):
    pending=0;requests=[];responses=[];records=[]
    for line in text.splitlines():
        require('[ARA_CONTRACT_ERROR]' not in line,'Contract error')
        if '[ARA_CONTRACT_TRACE]' not in line:continue
        match=decode.CONTRACT.fullmatch(line.strip());require(match is not None,'Malformed protocol trace')
        v=match.groups()
        cycle,rv,rr,rf,rid,insn,sv,sr,sf,sid,exc,before,rs,ss,errors=(
            int(x,16 if i in (4,5,9,11) else 2 if i==14 else 10) for i,x in enumerate(v))
        require(not records or cycle>records[-1]['cycle'],'Protocol cycle order')
        require(0<=rid<8 and 0<=sid<8 and pending==before and rf==rv*rr and sf==sv*sr and
                (rf or sf) and exc==errors==0,'Protocol fire/pending/errors')
        require(not rf or not(pending>>rid&1) or(sf and rid==sid),'Duplicate request ID')
        require(not sf or(pending>>sid&1) or(rf and rid==sid),'Orphan response ID')
        if rf:requests.append((cycle,rid,insn))
        if sf:responses.append((cycle,sid))
        if rf:pending|=1<<rid
        if sf:pending&=~(1<<sid)
        if rf and sf and rid==sid:pending=before
        records.append(dict(cycle=cycle,before=before,after=pending,rv=rv,sv=sv,sr=sr,rs=rs,ss=ss,sid=sid))
    require(len(requests)==len(req)==len(responses)==len(resp)>0 and len(records)<100000,'Protocol trace complete')
    require(all(a[1:]==b[1:] for a,b in zip(requests,req)) and all(a[1:]==b[1:] for a,b in zip(responses,resp)),'Protocol exact identities')
    offsets={a[0]-b[0] for a,b in zip(requests,req)}|{a[0]-b[0] for a,b in zip(responses,resp)}
    require(offsets=={5},'Exact reset-origin cycle offset')
    last=records[-1]
    require(pending==0 and last['before']==1<<last['sid'] and last['after']==0 and
            last['rv']==last['rs']==last['ss']==0 and last['sv']==last['sr']==1 and
            last['cycle']-5<terminal,'Lastdrain incomplete')
    return dict(status='EXACT_HANDSHAKE_LASTDRAIN_PASS',requests=len(req),responses=len(resp),last=last,cycle_offset=5)


def vector_gate(result):
    require(result['status']=='PASS' and all(result[k]==0 for k in
            ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')) and
            all(not result[k] for k in ('incomplete_requests','unretired_requests','trapped_requests')) and
            all(r['status']=='PASS' and r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0
                for r in result['instructions']),'Strict defined vector bytes, no blanket skip')


def raw_gain():
    manifest,ledger=baseline()
    cachepath=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache=life.read_bound(cachepath,'8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    review=life.read_bound(gold.REVIEW,gold.REVIEW_SHA)
    prefix=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(life.digest(prefix)==cache['input_pins'][str(prefix)] and prefix.read_text().splitlines()==ledger[:742],'741 exact prefix')
    scopes=sorted({t['scope'] for t in review['targets']});merged={s:cache['instances'][s] for s in scopes}
    evidence=dict(manifest['input_pins'])
    for p,h in list(evidence.items()):
        if p.endswith('/evidence-pins.json'):
            require(life.digest(Path(p))==h,'Evidence ledger drift');evidence=life.merge_pins(evidence,json.loads(Path(p).read_bytes()))
    pins={str(cachepath):life.digest(cachepath),str(prefix):life.digest(prefix)}
    for name in ledger[742:]:
        files=list((Path(name)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'));require(len(files)==1,'769 native Toggle identity')
        sample,sha=toggle.rows(files[0],scopes);require(evidence.get(str(files[0]))==sha,'769 actual Toggle pin')
        pins[str(files[0])]=sha;merged=toggle.union(merged,sample)
    source=OUT/'code.vdb/snps/coverage/db/testdata'/NAME/'tgl.verilog.data.xml'
    sample,sha=toggle.rows(source,scopes);pins[str(source)]=sha;after=toggle.union(merged,sample)
    targets=[]
    for t in review['targets']:
        before,new=merged[t['scope']],after[t['scope']]
        require(before['checksum']==new['checksum']==t['checksum'] and before['width']==new['width']==t['serialized_width'],'Exact typed target checksum/width')
        positions=[i for i in t['exact_missing_serialized_positions'] if not(int(before['bits'],16)>>(before['width']-1-i)&1) and int(new['bits'],16)>>(new['width']-1-i)&1]
        targets.append(dict(scope=t['scope'],name=t['name'],new_serialized_positions=positions))
    single=QUAL/'candidate-inputs.txt';single.write_text(ledger[0]+'\n'+str(OUT/'code.vdb')+'\n')
    candidate=bitmap.collect(single);base=json.loads((BASE/'combined-bits.json').read_bytes())
    require(base['tests']==ledger[1:] and len(base['tests'])==769,'Bitmap exact769 membership')
    delta=bitmap.delta(base,bitmap.combine(base,candidate))
    pins=life.merge_pins(pins,candidate['input_hashes']);life.check(pins)
    return dict(baseline=769,baseline_seal=BASE_SHA,target_objects=targets,
        target_new_serialized_positions=sum(len(t['new_serialized_positions']) for t in targets),
        scoped_toggle=toggle.gains(merged,after),raw_delta=delta,official_percentage=False,coverage_admitted=False,pins=pins)


def collect(record):
    require(not QUAL.exists(),'Fresh qualification');QUAL.mkdir()
    try:
        life.check(record['pins'])
        state=json.loads((OUT/'simulation-status.json').read_bytes())
        require(state['status']=='SIMULATION_EXITED_NOT_ADMITTED' and state['returncode']==0 and not state['timeout'],'Normal terminal required')
        require(json.loads((OUT/'manifest.json').read_bytes())==record,'Run manifest identity')
        started=json.loads((OUT/'started.json').read_bytes())
        require(started['pid']==state['pid'] and started['command']==record['command'] and
                started['elf_sha256']==record['elf_sha256'] and started['budget_s']==600,'Actual process/ELF/command')
        console=(OUT/'console.log').read_text();log=(OUT/'run.vcs.log').read_text()
        prefix,rows,terminal=decode.prefix((OUT/'commit_trace.csv').read_bytes())
        require(terminal['ignored_postterminal_bytes']==0,'Unexpected post-terminal retirement/event')
        vectors=decode.table((OUT/'vector_trace.csv').read_bytes(),decode.VECTOR_FIELDS)
        require(all(int(r['cycle'])<=terminal['cycle'] for r in vectors),'Post-terminal vector activity')
        (QUAL/'commit-prefix.csv').write_bytes(prefix)
        reference=shared.spike_trace.parse_spike_commits(gold.OUT/'spike.trace')
        begin=next(i for i,c in enumerate(reference) if c.pc==0x80000000)
        reference=reference[begin:];end=next(i for i,c in enumerate(reference) if (0x80001000,1) in c.memory_accesses)
        reference=reference[:end+1]
        memory,reads=scalar_check(rows,reference,record['preflight']['symbols'])
        symbols=record['preflight']['symbols']
        def value(name,offset=0,size=8):
            address=symbols[name]+offset;require(all(address+k in memory for k in range(size)),'Missing oracle byte')
            return int.from_bytes(bytes(memory[address+k] for k in range(size)),'little')
        gold.oracle(value)
        require(set(range(symbols['mr_source'],symbols['mr_source']+3200))<=reads,'Full source/guard readback')
        require(bytes(memory[symbols['mr_source']+i] for i in range(3200))==gold.source_bytes(),'Independent source/guard memory')
        control,req,resp=lifecycle(rows,vectors);protocol_result=protocol(console,req,resp,terminal['cycle'])
        generic.logs(console,log,control)
        require('Coverage status: End of All Coverages' in console,'Native coverage end missing')
        scalar=shared.spike_trace.compare_commit_prefix(gold.OUT/'spike.trace',QUAL/'commit-prefix.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        shared.scalar_exact(scalar,record['preflight']['counts']);life.save(QUAL/'scalar-comparison.json',scalar)
        vector=shared.compare_vector_commits(gold.OUT/'spike.trace',QUAL/'commit-prefix.csv',OUT/'vector_trace.csv',0x80000000)
        life.save(QUAL/'vector-comparison.json',vector);vector_gate(vector)
        # Bind each actual FMA's accepted defined bytes to the independent full-VRF oracle.
        vc=generic.vc;lanes,vlen,activities=vc._parse_vector_trace(OUT/'vector_trace.csv')
        starts,retires,traps=vc._parse_architecture_mapping(QUAL/'commit-prefix.csv')
        arch=vc._map_architecture_retires(starts,retires,traps,allow_incomplete_tail=False)
        stream=vc._spike_from_entry(gold.OUT/'spike.trace',0x80000000)
        mapping=vc._map_spike_commits(arch,stream,allow_incomplete_tail=False)
        expected,_=gold.gold();receipts=[]
        for seq,index in sorted(mapping.items()):
            if stream[index].instruction!=gold.OPCODE:continue
            require(seq in activities,'Missing actual FMA activity')
            a=activities[seq];actual=vc._architectural_bytes(a.writes,lanes,vlen);n=len(receipts)
            start=gold.STARTS[n];wanted={(24+i//64,(i%64)*2+b) for i in range(start,512) for b in range(2)}
            require(set(actual)==wanted,'Actual FMA defined byte extent')
            for (reg,byte),(data,write) in actual.items():
                target=(expected[n][reg*16+byte//8]>>(8*(byte%8)))&255
                require(data is not None and data==target,'Independent actual per-FMA result byte')
            receipts.append(dict(arch_seq=seq,start=start,defined_bytes=len(actual)))
        require(len(receipts)==12,'All twelve independent per-instruction FMA oracles')
        native=OUT/'code.vdb/snps/coverage/db/testdata'/NAME
        for metric in ('line','cond','branch','fsm','tgl'):
            toggle.xml(native/(metric+'.verilog.data.xml'))
        sim=toggle.xml(native/'siminfo.xml').find('srctest')
        import shlex
        require(sim is not None and int(sim.get('finishtime','0'))>int(sim.get('starttime','0'))>0 and
                shlex.split(sim.get('cmdline',''))==record['command'] and sim.get('workdir')==str(OUT),'Actual native VDB end/command/cwd')
        gain=raw_gain();life.save(QUAL/'raw-gain769.json',gain)
        pins=life.merge_pins(record['pins'],gain['pins'])
        files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='worker.log']
        files += [p for p in QUAL.iterdir() if p.is_file()]
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
        result=dict(status='MFPU_RESTART_FULL_ARCHITECTURE_QUALIFIED_NOT_ADMITTED',pins=pins,
            full_scalar_retirements=len(reference),scalar=scalar,vector=vector,lifecycle=control,protocol=protocol_result,
            software_checks=6264,full_VRF_snapshot_bytes=12288,source_guard_bytes=3200,CSR_words=60,
            per_instruction_FMA_oracles=receipts,raw_gain=gain,coverage_admitted=False,official_percentage=False)
        life.save(QUAL/'qualification.json',result)
    except Exception as error:
        life.save(QUAL/'qualification-reject.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise


def run(seal):
    record=life.read_bound(PREPARED,seal);life.check(record['pins'])
    require(record['command']==command(OUT) and record['timeout_s']==600 and not OUT.exists(),'One exact authorized command')
    namespace=dict(vars(runner),PRE=gold.OUT,ELF_SEAL=record['elf_sha256'],preflight=SimpleNamespace(NAME=NAME),command=command)
    try:FunctionType(runner.run.__code__,namespace)(OUT,record)
    finally:
        if (OUT/'simulation-status.json').exists():collect(record)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','verify'));p.add_argument('--seal')
    a=p.parse_args()
    if a.mode=='prepare':prepare()
    elif a.mode=='run':require(a.seal,'Prepared seal required');run(a.seal)
    else:
        result=json.loads((QUAL/'qualification.json').read_bytes());life.check(result['pins'])
        require(not result['coverage_admitted'] and result['raw_gain']['baseline']==769,'Qualified only, relative769')
        print(json.dumps(dict(status=result['status'],seal=life.digest(QUAL/'qualification.json'))))
