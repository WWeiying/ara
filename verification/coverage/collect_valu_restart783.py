"""Offline full architecture gate for the frozen finite VALU12 matrix."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import shlex

import preflight_valu_restart783 as gold
import run_valu_restart783 as run
import run_mfpu_restart_word_boundary769 as mature

life,require=gold.life,gold.require
shared,decode,generic,toggle=gold.shared,mature.decode,mature.generic,mature.toggle


def terminal(state):
    require(state['status']=='SIMULATION_EXITED_NOT_ADMITTED' and type(state['returncode']) is int
        and state['returncode']==0 and state['timeout'] is False,'Normal typed terminal required')


def vector_gate(result):
    mature.vector_gate(result)
    require(all(type(result[k]) is int and result[k]==0 for k in
        ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')),
        'Typed zero vector comparison; no unknown-policy skips')


def target_metadata(targets):
    require(len(targets)==12 and [int(r['vstart']) for r in targets]==list(gold.STARTS) and
        all((int(r['vd']),int(r['eew']),int(r['vl']),int(r['use_vd']))==(8,0,1024,1)
            for r in targets),'Twelve exact accepted VALU restart configurations')


def lifecycle(rows,vectors):
    starts={};pending={};live={};history=defaultdict(list);alloc=Counter();done=Counter();req=[];resp=[]
    previous=-1
    for r in rows:
        seq,tid,cycle,event=int(r['order']),int(r['trans_id']),int(r['cycle']),r['event']
        require(cycle>=previous,'Commit cycle ordering');previous=cycle
        if event=='arch_start':
            require(seq>=0 and seq not in starts and tid not in pending,'Duplicate architecture/live ID')
            starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1] and r['insn']==starts[pending[tid][0]]['insn'],'Unowned request')
            pending[tid][1]=True;req.append((cycle,tid,int(r['insn'],16)))
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and seq==-1 and
                int(r['pc'],16)==int(r['insn'],16)==int(r['trap'])==0,'Unowned response')
            pending.pop(tid);resp.append((cycle,tid))
        elif event in ('uop_alloc','uop_done'):
            vid=int(r['port']);require(seq in starts and 0<=vid<8 and tid==int(starts[seq]['trans_id'])
                and r['insn']==starts[seq]['insn'] and cycle>=int(starts[seq]['cycle']),'Backend owner')
            if event=='uop_alloc':
                require(vid not in live,'Live SID reuse');entry=dict(seq=seq,start=cycle,end=None)
                live[vid]=entry;history[vid].append(entry);alloc[seq,vid,cycle]+=1
            else:
                require(vid in live and live[vid]['seq']==seq and cycle>=live[vid]['start'],'Unowned completion')
                live.pop(vid)['end']=cycle;done[seq,vid,cycle]+=1
        else: require(event=='retire' and int(r['trap'])==0,'Unknown event or trap')
    require(not pending and not live and len(req)==len(resp)==len(starts)>0 and
        Counter((s,v) for s,v,_ in alloc.elements())==Counter((s,v) for s,v,_ in done.elements()),'Incomplete lifecycle')
    va=Counter();vd=Counter();metadata={};previous=-1
    for r in vectors:
        cycle,seq,vid,event=int(r['cycle']),int(r['arch_seq']),int(r['vid']),r['event']
        require(cycle>=previous and (int(r['nr_lanes']),int(r['vlen_bits']))==(4,1024),'Native ordering/geometry');previous=cycle
        if event=='config':continue
        require(seq in starts and r['insn']==starts[seq]['insn'],'Native owner/opcode')
        if event=='alloc':
            key=seq,vid,cycle;require(key not in metadata,'Duplicate allocation');metadata[key]=r;va[key]+=1
        else:
            eligible=[h for h in history[vid] if h['start']<cycle] or [h for h in history[vid] if h['start']==cycle]
            require(eligible,'Missing SID history');h=eligible[-1];key=h['seq'],vid,h['start']
            require(h['seq']==seq and h['end'] is not None and h['start']<=cycle<=h['end'] and key in metadata,'Native lifetime')
            require(all(r[k]==metadata[key][k] for k in ('insn','use_vd','vd','eew','vl','vstart')),'Native metadata drift')
            if event=='done':vd[seq,vid,cycle]+=1
            else:require(event=='write' and int(r['use_vd'])==1 and 0<=int(r['lane'])<4 and 0<=int(r['source'])<5,'Native write type')
    require(va==alloc and vd==done,'Exact backend/native lifetimes')
    target_metadata([r for r in metadata.values() if int(r['insn'],16)==gold.OPCODE])
    return dict(requests=len(req),responses=len(resp),backend_uops=sum(alloc.values())),req,resp


def target_bytes(actual,n):
    require(0<=n<12,'Target count overflow')
    wanted={(8+i//128,i%128) for i in range(gold.STARTS[n],1024)}
    require(set(actual)==wanted,'Exact active write byte enables; prefix/destination protection')
    expected=gold.gold()[n][1]
    for (reg,byte),(data,write) in actual.items():
        require(type(data) is int and data==(expected[reg*16+byte//8]>>(8*(byte%8)))&255,'Independent per-vadd bytes')
    return dict(vstart=gold.STARTS[n],defined_bytes=len(actual))


def memory_oracle(memory,reads,symbols):
    def value(name,offset=0,size=8):
        address=symbols[name]+offset
        require(all(address+k in memory for k in range(size)),'Missing scalar oracle bytes')
        return int.from_bytes(bytes(memory[address+k] for k in range(size)),'little')
    gold.oracle(value)
    source=set(range(symbols['vr_source'],symbols['vr_source']+3200))
    snapshots=set(range(symbols['vr_snap'],symbols['vr_snap']+24*gold.SNAP_BYTES))
    require(source|snapshots <= reads,'Full source/guard and before/after VRF scalar readback')
    require(bytes(memory[symbols['vr_source']+i] for i in range(3200))==gold.source_bytes(),'Source/guard mutation')


def target_gain(native,preflight):
    binding,pins=gold.binding783()
    require(binding==preflight['baseline'],'Exact783 target coordinates')
    review=life.read_bound(gold.REVIEW,gold.REVIEW_SHA)
    inventory_path=Path(review['inventory'])
    inventory=life.read_bound(inventory_path,review['inventory_sha256'])
    scopes=sorted({t['scope'] for t in binding['targets']})
    before={s['scope']:s['row'] for s in inventory['scopes'] if s['scope'] in scopes}
    suffix=list((Path(binding['appended_vdb'])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(suffix)==1,'Exact783 append')
    rows,h=toggle.rows(suffix[0],scopes);require(pins[str(suffix[0])]==h,'783 suffix pin')
    before=toggle.union(before,rows)
    rows,h=toggle.rows(native/'tgl.verilog.data.xml',scopes)
    pins[str(native/'tgl.verilog.data.xml')]=h;after=toggle.union(before,rows);targets=[]
    for t in binding['targets']:
        b,a=before[t['scope']],after[t['scope']]
        require(b['checksum']==a['checksum']==t['checksum'] and b['width']==a['width']==5746,
            'Exact compiled VALU Toggle shape')
        positions=[i for i in t['missing_coordinates'] if
            not(int(b['bits'],16)>>(b['width']-1-i)&1) and int(a['bits'],16)>>(a['width']-1-i)&1]
        targets.append(dict(scope=t['scope'],name=t['name'],new_serialized_positions=positions))
    life.check(pins)
    return dict(baseline=783,baseline_seal=gold.BASE_SHA,targets=targets,
        actual_new_target_coordinates=sum(len(t['new_serialized_positions']) for t in targets),
        scoped_raw_gain=toggle.gains(before,after),official_percentage=False),pins


def collect(prepared,seal,output):
    require(not output.exists(),'Fresh qualification directory');output.mkdir()
    try:
        r=run.check(prepared,seal);native_out=Path(r['output'])
        actual=dict(r,pins=life.merge_pins(r['pins'],{str(prepared):seal}))
        require(json.loads((native_out/'manifest.json').read_bytes())==actual,'Run manifest exact')
        terminal(json.loads((native_out/'simulation-status.json').read_bytes()))
        identity=json.loads((native_out/'live-simv-identity.json').read_bytes())
        require(type(identity['pid']) is int and identity['pid']>0 and identity['executable']==str(life.IMAGE.resolve())
            and identity['executable_sha256']==r['image_sha256'] and identity['cwd']==str(native_out)
            and identity['command']==r['command'] and identity['service']==r['service'] and
            any(r['service'] in line.split(':',2)[-1].split('/') for line in identity['cgroup'].splitlines()),'Actual frozen process identity')
        prefix,rows,end=decode.prefix((native_out/'commit_trace.csv').read_bytes())
        require(end['ignored_postterminal_bytes']==0,'Post-terminal events')
        vectors=decode.table((native_out/'vector_trace.csv').read_bytes(),decode.VECTOR_FIELDS)
        require(all(int(v['cycle'])<=end['cycle'] for v in vectors),'Post-terminal vector activity')
        prefix_path=output/'commit-prefix.csv';prefix_path.write_bytes(prefix)
        reference=shared.spike_trace.parse_spike_commits(gold.OUT/'spike.trace')
        reference=reference[next(i for i,c in enumerate(reference) if c.pc==0x80000000):]
        reference=reference[:next(i for i,c in enumerate(reference) if (0x80001000,1) in c.memory_accesses)+1]
        memory,reads=mature.scalar_check(rows,reference,r['preflight']['symbols'])
        memory_oracle(memory,reads,r['preflight']['symbols'])
        control,req,resp=lifecycle(rows,vectors)
        console=(native_out/'console.log').read_text();vcslog=(native_out/'run.vcs.log').read_text()
        protocol=mature.protocol(console,req,resp,end['cycle']);generic.logs(console,vcslog,control)
        require('Coverage status: End of All Coverages' in console,'Native coverage end')
        scalar=shared.spike_trace.compare_commit_prefix(gold.OUT/'spike.trace',prefix_path,0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        shared.scalar_exact(scalar,r['preflight']['counts'])
        vector=shared.compare_vector_commits(gold.OUT/'spike.trace',prefix_path,native_out/'vector_trace.csv',0x80000000)
        vector_gate(vector)
        vc=generic.vc;lanes,vlen,activities=vc._parse_vector_trace(native_out/'vector_trace.csv')
        starts,retires,traps=vc._parse_architecture_mapping(prefix_path)
        arch=vc._map_architecture_retires(starts,retires,traps,allow_incomplete_tail=False)
        stream=vc._spike_from_entry(gold.OUT/'spike.trace',0x80000000)
        mapping=vc._map_spike_commits(arch,stream,allow_incomplete_tail=False);receipts=[]
        for seq,index in sorted(mapping.items()):
            if stream[index].instruction!=gold.OPCODE:continue
            require(seq in activities,'Missing native target')
            receipt=target_bytes(vc._architectural_bytes(activities[seq].writes,lanes,vlen),len(receipts))
            receipts.append(dict(receipt,arch_seq=seq))
        require(len(receipts)==12,'Twelve independent native target oracles')
        native=native_out/'code.vdb/snps/coverage/db/testdata'/run.CASE
        for metric in ('line','cond','branch','fsm','tgl'):toggle.xml(native/(metric+'.verilog.data.xml'))
        sim=toggle.xml(native/'siminfo.xml').find('srctest')
        require(sim is not None and int(sim.get('finishtime','0'))>int(sim.get('starttime','0'))>0 and
            shlex.split(sim.get('cmdline',''))==r['command'] and sim.get('workdir')==str(native_out),'Complete actual VDB identity')
        gain,gain_pins=target_gain(native,r['preflight'])
        pins=life.merge_pins(actual['pins'],gain_pins)
        # Launcher/service logs may append after collector completion; native outputs may not.
        files=[p for p in native_out.rglob('*') if p.is_file() and p.name not in ('worker.log','service.log')]
        pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
        result=dict(status='VALU_RESTART783_FULL_ARCHITECTURE_QUALIFIED_NOT_ADMITTED',pins=pins,
            scalar=scalar,vector=vector,lifecycle=control,protocol=protocol,per_instruction_oracles=receipts,
            software_checks=13144,full_VRF_snapshot_bytes=98304,guard_bytes=3072,source_guard_bytes=3200,
            CSR_words=60,full_scalar_retirements=len(reference),all_scalar_RVC_memory_checked=True,
            scalar_trap_rows_required=0,unknown_defined_bytes_skipped=0,baseline=783,
            directly_observed_AXI_beats=False,coverage_admitted=False,official_percentage=False,
            target_raw_gain=gain,global_union_gain_not_yet_measured=True)
        life.save(output/'qualification.json',result)
        print(json.dumps(dict(status=result['status'],path=str(output/'qualification.json'),seal=life.digest(output/'qualification.json'))))
    except Exception as error:
        life.save(output/'rejection.json',dict(reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--seal',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();collect(a.prepared.absolute(),a.seal,a.output.absolute())
