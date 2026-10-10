"""Offline complete scalar/VRF/CSR/memory qualification and exact796 raw gain."""
import argparse
import copy
import json
from pathlib import Path
from types import FunctionType

import run_vsmul_saturation796 as runner
import collect_vfirst_long_mask as mature
from collect_c910_float_edge_initialized777 import coverage_identity

life,require,p = runner.life,runner.require,runner.p
common,control,memory,vc = mature.common,mature.control,mature.memory,mature.vc


def reference_prefix(pre):
    commits=p.build.parse_spike_commits(Path(pre['reference']))
    start=next(i for i,c in enumerate(commits) if c.pc==0x80000000)
    require(start==5,'Exact five-instruction reference ROM prefix')
    reference=commits[start:start+18927]
    require(len(reference)==18927 and reference[-1].memory_accesses==((pre['symbols']['tohost'],1),),'Complete entry-to-tohost reference')
    require(p.validate(Path(pre['reference']),pre['symbols'])=={k:v for k,v in pre['counts'].items() if k!='runtime'},'Frozen independent software gold replay')
    return reference


def terminal(run,manifest):
    state=life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json'))
    actual=json.loads((run/'manifest.json').read_bytes());started=json.loads((run/'started.json').read_bytes())
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int
        and state['returncode']==0 and state.get('timeout') is False and state.get('case')==runner.NAME
        and state.get('coverage_admitted') is False and state.get('admission_performed') is False,'True successful OS terminal, not selfcheck alone')
    require(actual==dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL') and
        started['command']==manifest['command'] and started['input_elf']==str(runner.ELF) and
        started['elf_sha256']==runner.ELF_SHA and started['image']==str(life.IMAGE) and started['image_sha256']==runner.IMAGE_SHA
        and type(started['pid']) is int and started['pid']>0 and started['pid']==started['process_group']==state['pid']
        and started['budget_s']==runner.BUDGET and started['foreground_lifetime'] is True
        and type(state['wall_seconds']) in (int,float) and state['wall_seconds']>=0,'Exact command/ELF/image/PID/lifecycle/budget')
    return state


def expected_footprint(symbols):
    wanted={}
    def add(name,data):wanted.update({symbols[name]+i:v for i,v in enumerate(data)})
    add('sm_source',b''.join(p.image(d) for c in range(12) for d in p.case(c)['sources']))
    add('sm_snapshot',b''.join(p.image(d) for c in range(12) for d in p.case(c)['sources']+[p.case(c)['destination']]))
    add('sm_csr',b''.join(v.to_bytes(8,'little') for c in range(12) for v in p.case(c)['csr']))
    reads=set(wanted)
    add('g75_result',p.CHECKS.to_bytes(4,'little')+bytes(4));add('num_failed',bytes(4));add('sm_checks',p.CHECKS.to_bytes(4,'little'))
    return wanted,reads


def footprint(rows,symbols,reference):
    wanted,required_reads=expected_footprint(symbols);observed={};reads=set();terminals=[]
    retired=[r for r in rows if r['event']=='retire']
    require(len(retired)==len(reference)==18927 and [int(r['order']) for r in retired]==list(range(18927)),'Complete continuous retirement order')
    source_range=range(symbols['sm_source'],symbols['sm_source']+3840)
    for row,expected in zip(retired,reference):
        word=int(row['insn'],16)
        require(word==expected.instruction and int(row['pc'],16)==expected.pc and not int(row['trap'])
            and expected.pc!=symbols['trap_fail'],'Every ELF/reference opcode/PC, no trap')
        rm,wm=int(row['mem_rmask'],16),int(row['mem_wmask'],16);access=common.scalar_memory(word)
        if access is None:
            require(not rm and not wm,'No unsupported scalar memory effect');continue
        kind,width=access;address=int(row['mem_addr'],16);mask=((1<<width)-1)<<(address&7)
        require(address%width==0 and 0x80000000<=address and address+width<=0x80040000
            and rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),'Exact scalar memory range/alignment/BE')
        value=int(row['rd_wdata'] if kind=='read' else row['mem_wdata'],16)&((1<<(8*width))-1)
        if kind=='read' and any(address+i in required_reads for i in range(width)):
            require(int(row['rd'])!=0,'Required readback has observable scalar rd')
        if kind=='write':
            require(not any(address+i in source_range for i in range(width)),'Immutable source/guards cannot be written')
            if address==symbols['tohost']:terminals.append((row,value))
        for i in range(width):
            if address+i in wanted:
                observed[address+i]=value>>(8*i)&255
                if kind=='read':reads.add(address+i)
    require(required_reads<=reads and observed==wanted,'Every independent result/tail/source/guard/CSR/check byte')
    require(terminals==[(retired[-1],1)],'Exactly final successful tohost')
    operations=[i for i,c in enumerate(reference) if c.pc==symbols['sm_target']]
    require(len(operations)==12,'Exactly twelve VSMUL retirements')
    csr_records=[]
    for phase,start in enumerate(operations):
        end=operations[phase+1] if phase<11 else len(reference)
        matches=[i for i in range(start+1,end) if reference[i].instruction&127==115
            and reference[i].instruction>>20==15 and reference[i].instruction>>12&7==2
            and reference[i].instruction>>15&31==0]
        require(len(matches)==1,'One exact vcsr read after each VSMUL')
        index=matches[0];rd=reference[index].instruction>>7&31
        require(rd and int(retired[index]['rd'])==rd and int(retired[index]['rd_wdata'],16)==p.case(phase)['csr'][4],'Every independent sticky saturation/rounding CSR result')
        csr_records.append(dict(phase=phase,pc=reference[index].pc,vcsr=p.case(phase)['csr'][4]))
    return dict(checks=1272,retirements=18927,source_guard_bytes=3840,snapshot_bytes=4608,CSR_values=72,
        required_read_bytes=len(required_reads),per_operation_vcsr=csr_records)


def known_writes(writes,seq,commit):
    seen=set()
    for write in writes:
        require(write.arch_seq==seq and write.instruction==commit.instruction and 0<=write.lane<4
            and 0<write.be<=255 and not write.be&~write.known_be,'Exact accepted write owner/known bytes/lane')
        for byte in range(8):
            if write.be&(1<<byte):
                key=write.addr,write.lane,byte
                require(key not in seen,'Duplicate accepted producer byte');seen.add(key)
    return vc._architectural_bytes(writes,4,1024)


def store_context(raw,seq,commit):
    rows=[r for r in raw if int(r['arch_seq'])==seq]
    require(rows and all(int(r['insn'],16)==commit.instruction for r in rows),'Store raw opcode/arch_seq identity')
    main=[r for r in rows if r['event'] in ('alloc','done') and int(r['use_vd'])==0]
    alloc=[r for r in main if r['event']=='alloc'];done=[r for r in main if r['event']=='done']
    require(len(alloc)==len(done)==1,'Unique architectural whole-store allocation/completion')
    a,d=alloc[0],done[0]
    require(all(int(r['vd'])==0 and int(r['eew'])==0 and int(r['vl'])==128 and int(r['vstart'])==0
        and int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024 for r in (a,d))
        and int(a['vid'])==int(d['vid']) and 0<=int(a['vid'])<8 and int(a['cycle'])<=int(d['cycle']),
        'Source-bound whole-store128-byte context/VID/order, not parser None fields')
    require(commit.instruction&127==39 and commit.instruction>>20&31==8
        and commit.instruction>>29==0 and commit.instruction>>12&7==0,'Exact vs1r instruction')


def native_state(reference,activities,mapping,symbols,raw):
    require(set(activities)<=set(mapping),'No unmapped native request')
    roles={symbols[n]:n for n in ('sm_load_a','sm_load_b','sm_seed','sm_target','sm_store_a','sm_store_b','sm_store_d')}
    counts={n:0 for n in roles.values()};records=[];transport=[];states={};prestates={}
    indices=set(mapping.values())
    for index,commit in enumerate(reference):
        if index in indices:prestates[index]=dict(states)
        states.update(commit.vector_writes)
    filtered=copy.deepcopy(activities)
    for seq,index in sorted(mapping.items()):
        commit=reference[index];activity=activities.get(seq);role=roles.get(commit.pc)
        if activity is None:
            require(role is None,'Required backend activity missing');continue
        require(activity.instruction==commit.instruction and activity.allocations>0
            and activity.allocations==activity.completions,'Every native request exact identity and complete lifecycle')
        identities=[w for w in activity.writes if w.source==3]
        if identities:
            actual=known_writes(identities,seq,commit);prestate=prestates[index]
            require(actual and all(reg in prestate and value is not None
                and value==(prestate[reg]>>(8*byte)&255) for (reg,byte),(value,w) in actual.items()),
                'All reshuffle transport equals fully known architectural prestate')
            transport.append(dict(arch_seq=seq,pc=commit.pc,opcode=commit.instruction,compared_bytes=len(actual)))
        filtered[seq].writes=[w for w in filtered[seq].writes if w.source!=3]
        if role is None:
            require(not filtered[seq].writes and not commit.vector_writes,'No non-fixture architectural VRF writer');continue
        phase=counts[role];counts[role]+=1;require(phase<12,'No duplicate role beyond twelve phases')
        expected=p.case(phase)
        if role.startswith('sm_store'):
            require(not filtered[seq].writes and not commit.vector_writes,'Whole-store cannot have non-transport VRF writer')
            store_context(raw,seq,commit);continue
        reg,source,data=(8,4,expected['sources'][0]) if role=='sm_load_a' else (16,4,expected['sources'][1]) if role=='sm_load_b' else (24,0,bytes([0x5a])*128) if role=='sm_seed' else (24,1,expected['destination'][:32])
        eew=phase//3 if role=='sm_target' else 0;vl=expected['vl'] if role=='sm_target' else 128
        require(activity.use_vd and activity.vd==reg and activity.eew==eew and activity.vl==vl and activity.vstart==0,'Exact destination/VL/EEW/vstart')
        writes=filtered[seq].writes
        require(writes and all(w.source==source and w.eew==eew for w in writes),'Required unique ALU/MFPU/VLDU producer')
        actual=known_writes(writes,seq,commit);wanted={(reg,i):byte for i,byte in enumerate(data)}
        require(set(actual)==set(wanted) and all(actual[k][0]==v for k,v in wanted.items()),'Every defined primary byte; no missing/extra/incorrect accepted write')
        records.append(dict(arch_seq=seq,pc=commit.pc,opcode=commit.instruction,role=role,phase=phase,
            eew=eew,vl=vl,compared_bytes=len(data)))
    require(all(v==12 for v in counts.values()) and len(records)==48 and sum(r['compared_bytes'] for r in records)==4992,'All48 architectural writers/36 stores,4992 primary bytes')
    return dict(operations=counts,writers=records,primary_compared_bytes=4992,identity_transport=transport,
        identity_compared_bytes=sum(r['compared_bytes'] for r in transport),unknown_bytes=0),filtered


def generic_gate(result):
    require(result['status']=='PASS' and result['stopped_at_spike_index'] is None
        and result['vector_destination_requests']==result['prefix_vector_destination_requests']==result['compared_instructions']==48
        and result['compared_bytes']==4992 and result['first_mismatch'] is None
        and all(result[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions'))
        and not result['incomplete_requests'] and not result['unretired_requests'] and not result['trapped_requests']
        and all(r['unknown_write_bytes']==r['skipped_unknown_bytes']==r['mismatch_count']==0 for r in result['instructions']),
        'All architectural requests exact generic diff without stop or unknown skips')


def native(run,reference,symbols,pre):
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected,'Frozen native geometry; no trapped request')
    mapping=vc._map_spike_commits(vc._map_architecture_retires(starts,retires,rejected),reference)
    raw=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
    proof,filtered=native_state(reference,activities,mapping,symbols,raw)
    def parse(path):
        require(Path(path)==run/'vector_trace.csv','Exact bound raw trace only')
        return lanes,vlen,filtered
    result=FunctionType(vc.compare_vector_commits.__code__,{**vc.compare_vector_commits.__globals__,'_parse_vector_trace':parse},
        argdefs=vc.compare_vector_commits.__defaults__)(Path(pre['reference']),run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
    generic_gate(result)
    return dict(primary_and_transport=proof,architectural_vector_diff=result,
        comparison_partition='All source3 identity bytes compared separately to strict known prestate; all48 architectural writers compared without stop/skip')


def exact_raw_union(before,single,combined,population=796):
    counts=dict(line=1892,cond=2023,branch=2155,fsm=92)
    require(set(before['metrics'])==set(single['metrics'])==set(combined['metrics'])==set(counts)
        and before['design']==single['design']==combined['design']
        and len(before['tests'])==len(set(before['tests']))==population and len(single['tests'])==1
        and single['tests'][0] not in before['tests'] and combined['tests']==before['tests']+single['tests'],'Full metric identity/exact796 prefix/unique candidate')
    for metric,count in counts.items():
        old,new,final=(v['metrics'][metric] for v in (before,single,combined))
        require(len(old)==count and set(old)==set(new)==set(final),'Exact per-metric instance universe')
        for scope,row in old.items():
            add,result=new[scope],final[scope]
            require((row['width'],row['checksum'])==(add['width'],add['checksum'])==(result['width'],result['checksum']),'Exact compiled width/checksum')
            a,b,c=(int(r['bits'],16) for r in (row,add,result))
            require(min(a,b,c)>=0 and max(a,b,c).bit_length()<=row['width'] and c==a|b,'Full6162 bounded mathematical OR')
    return dict(metric_instances=6162,counts=counts,exact_prefix=True,exact_OR=True)


def exact_toggle_union(before,sample):
    require(len(before)==len(sample)==2989 and set(before)==set(sample),'All2989 actual Toggle scopes')
    combined=runner.toggle.union(before,sample)
    for scope,row in before.items():
        add,result=sample[scope],combined[scope]
        require((row['width'],row['checksum'])==(add['width'],add['checksum'])==(result['width'],result['checksum'])
            and max(int(r['bits'],16).bit_length() for r in (row,add,result))<=row['width']
            and int(result['bits'],16)==int(row['bits'],16)|int(add['bits'],16),'All2989 exact compiled Toggle OR')
    return combined


def gain(run,out,manifest):
    base,before,tgl,ledger=runner.baseline();design=Path(ledger[0]);db=run/'code.vdb'
    require(str(db) not in ledger,'No duplicate VDB')
    folder=db/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'One actual native coverage sample')
    pins=coverage_identity(folder,run,manifest,design)
    inputs=out/'single-inputs.txt';inputs.write_text(str(design)+'\n'+str(db)+'\n')
    single=runner.bitmap.collect(inputs);combined=runner.bitmap.combine(before,single)
    proof=exact_raw_union(before,single,combined);delta=runner.bitmap.delta(before,combined)
    sample,sha=runner.toggle.rows(folder/'tgl.verilog.data.xml',list(tgl))
    require(sha==pins[str(folder/'tgl.verilog.data.xml')],'Actual Toggle read SHA')
    merged=exact_toggle_union(tgl,sample);additions=runner.toggle.gains(tgl,merged)
    targets=[dict(scope=t['scope'],field=t['name'],new_serialized_coordinates=[i for i in t['raw_coordinates'] if i in additions[t['scope']]]) for t in manifest['targets']]
    for name,value in (('single-bits.json',single),('proposed-combined-bits.json',combined),('raw-delta.json',delta),
                       ('single-toggle-bits.json',sample),('proposed-combined-toggle-bits.json',merged),('full-toggle-gain.json',additions)):
        life.save(out/name,value)
    return dict(baseline=796,full6162=proof,full2989=True,metrics=delta['metrics'],
        full_toggle_new_slots=sum(map(len,additions.values())),targets=targets,
        primary_new_slots=sum(len(t['new_serialized_coordinates']) for t in targets),official_percentage=None),pins


def collect(run,seal,out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent offline output')
    manifest=life.read_bound(run.with_name(run.name+'.prepared.json'),seal)
    require(manifest==runner.prepare(run,existing=True),'Original prepared contract/pins exact')
    terminal(run,manifest);pre=runner.preflight();reference=reference_prefix(pre)
    pins=mature.evidence_pins(run,seal,manifest);life.check(pins);out.mkdir()
    try:
        rows=common.read_csv((run/'commit_trace.csv').read_bytes(),common.COMMIT_FIELDS)
        vectors=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
        lifecycle=control.lifecycle(rows,vectors);signature=footprint(rows,pre['symbols'],reference);mature.logs(run,lifecycle)
        scalar=common.spike_trace.compare_commit_prefix(Path(pre['reference']),run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'],rtl_exception_log=run/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,common.reference_counts(reference,pre['symbols']))
        scalar_memory=memory.scalar_memory_exact(rows,reference)
        vector=native(run,reference,pre['symbols'],pre);raw,gainpins=gain(run,out,manifest)
        pins=life.merge_pins(life.merge_pins(pins,gainpins),{str(f):life.digest(f) for f in out.iterdir() if f.is_file()});life.check(pins)
        result=dict(status='VSMUL796_FULL_SCALAR_NATIVE_SOURCE_CSR_MEMORY_PASS_NOT_ADMITTED',run=str(run),prepared_seal=seal,
            terminal=terminal(run,manifest),scalar=scalar,scalar_memory=scalar_memory,native=vector,signature=signature,
            lifecycle=lifecycle,raw_gain=raw,input_pins=pins,coverage_admitted=False,EDA_launched=False,RTL_modified=False)
        life.save(out/'qualification.json',result);print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),raw['primary_new_slots'],flush=True)
    except Exception as error:
        life.save(out/'failure.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',reason=str(error),no_retry=True));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--seal',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();collect(args.run.resolve(),args.seal,args.output.resolve())
