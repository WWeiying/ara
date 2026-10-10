"""Strict offline scalar/native legal-mask qualification and full formal786 raw OR."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shlex

import run_mask_compare_restart786 as runner
import collect_vfirst_long_mask as mature
from ara_verify import vector_commit as vc

life, require, p = runner.life, runner.require, runner.p
common, control, memory = mature.common, mature.control, mature.memory


def reference_prefix(pre):
    commits=p.build.parse_spike_commits(Path(pre['reference']))
    start=next(i for i,c in enumerate(commits) if c.pc==0x80000000)
    count=pre['counts']['runtime']['entry_to_tohost_instructions']; reference=commits[start:start+count]
    require(start==5 and count==44559 and len(reference)==count and
            reference[-1].memory_accesses==((pre['symbols']['tohost'],1),),'Exact full entry-tohost reference')
    require(p.validate(Path(pre['reference']),pre['symbols'])=={k:v for k,v in pre['counts'].items() if k!='runtime'},
            'Complete independent software oracle replay')
    return reference


def terminal(run,manifest):
    state=json.loads((run/'simulation-status.json').read_bytes())
    actual=json.loads((run/'manifest.json').read_bytes()); started=json.loads((run/'started.json').read_bytes())
    require(state.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and type(state.get('returncode')) is int and
            state['returncode']==0 and state.get('timeout') is False and state.get('case')==runner.NAME and
            state.get('coverage_admitted') is False and state.get('admission_performed') is False,'Actual successful OS terminal')
    require(actual==dict(manifest,authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL') and
            started['command']==manifest['command'] and started['input_elf']==str(runner.ELF) and
            started['elf_sha256']==runner.ELF_SHA and started['image']==str(life.IMAGE) and
            started['image_sha256']==runner.IMAGE_SHA and type(started['pid']) is int and started['pid']>0 and
            started['pid']==started['process_group']==state['pid'] and started['budget_s']==runner.BUDGET and
            started['foreground_lifetime'] is True,'Exact command/PID/image/ELF/budget')
    return state


def footprint(rows,symbols):
    guard=bytes([0x96])*16; wanted={}
    def region(name,data): wanted.update({symbols[name]+i:b for i,b in enumerate(data)})
    region('mc_init_vl',(128).to_bytes(8,'little'))
    region('mc_sources',b''.join(guard+p.source_bytes(s)+guard for s in (0,1)))
    region('mc_readback',b''.join(guard+p.source_bytes(s)+guard for c in range(3) for s in (0,1)))
    region('mc_masks',b''.join(guard+p.mask_gold(s)+guard for s in p.STARTS))
    xor=bytes(a^b for a,b in zip(p.source_bytes(0)[:64],p.source_bytes(1)[:64]))+bytes(64)
    region('mc_xors',(guard+xor+guard)*3)
    region('mc_ledger',b''.join(v.to_bytes(8,'little') for s in p.STARTS for v in (128,64,s,64,0,0,0,0)))
    required_reads=set(wanted)
    region('g75_result',(1905).to_bytes(4,'little')+bytes(4)); region('mc_checks',(1905).to_bytes(4,'little'))
    region('num_failed',bytes(4)); observed={}; reads=set(); terminals=[]
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(44559)),'All ordered retirements')
    for r in retired:
        word=int(r['insn'],16); require(not int(r['trap']) and int(r['pc'],16)!=symbols['trap_fail'],'No trap')
        rm,wm=int(r['mem_rmask'],16),int(r['mem_wmask'],16); access=common.scalar_memory(word)
        if access is None:
            require(not rm and not wm,'Unknown scalar memory effect'); continue
        kind,width=access; address=int(r['mem_addr'],16); mask=((1<<width)-1)<<(address&7)
        require(address%width==0 and 0x80000000<=address and address+width<=0x80040000 and
                rm==(mask if kind=='read' else 0) and wm==(mask if kind=='write' else 0),'Memory bounds/alignment/masks')
        value=int(r['rd_wdata'] if kind=='read' else r['mem_wdata'],16)&((1<<(8*width))-1)
        if kind=='read' and any(address+i in required_reads for i in range(width)):
            require(int(r['rd'])!=0,'Unobservable required read')
        if kind=='write' and address==symbols['tohost']: terminals.append((r,value))
        for i in range(width):
            if address+i in wanted:
                observed[address+i]=value>>(8*i)&255
                if kind=='read': reads.add(address+i)
    require(required_reads<=reads and observed==wanted,'Every source/guard/CSR/defined mask byte')
    require(terminals==[(retired[-1],1)],'Unique final tohost1')
    return dict(checks=1905,failures=0,retirements=44559,defined_mask_bits=192,required_read_bytes=len(required_reads))


def mask_postimage(before,after,start):
    require(type(before) is int and type(after) is int and 0<=before<1<<1024 and 0<=after<1<<1024,
            'Known full native mask pre/post state')
    pre=(1<<start)-1; active=((1<<64)-1)^pre; tail=((1<<1024)-1)^((1<<64)-1)
    gold=int.from_bytes(p.mask_gold(start),'little')
    require((before^after)&pre==0,'Prestart bit changed')
    require((after^gold)&active==0,'Defined active mask mismatch')
    require(before&~after&tail==0,'Agnostic tail cleared old1')
    return dict(prestart_bits=start,active_bits=64-start,tail_bits=960,tail_old_or_one_checked=True,
                whole_destination_skipped=False,unknown_accepted_bytes=0)


def request_context(rows,seq,insn,vl,vstart,vd,use_vd):
    owned=[r for r in rows if r['event']!='config' and int(r['arch_seq'])==seq]
    require(owned and all(int(r['insn'],16)==insn for r in owned),'Unique request opcode owner')
    alloc=[r for r in owned if r['event']=='alloc']; done=[r for r in owned if r['event']=='done']
    require(len(alloc)==len(done)==1,'Exact one alloc/complete owner')
    a,d=alloc[0],done[0]
    for r in (a,d):
        require(int(r['vl'])==vl and int(r['vstart'])==vstart and int(r['eew'])==0 and
                int(r['vd'])==vd and int(r['use_vd'])==int(use_vd) and
                int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024,'Exact native request context')
    require(a['vid']==d['vid'] and 0<=int(a['vid'])<8 and int(a['cycle'])<=int(d['cycle']),
            'VID completion identity/order')
    return alloc[0]


def native_state(reference,activities,mapping,symbols,rows):
    state={}; records=[]; counts=Counter(); compare_case=0
    require(all(s in mapping for s in activities),'Unmapped native activity')
    writer_names=('mc_init_a','mc_init_b','mc_clear24','mc_clear1','mc_compare','mc_xor')
    store_names=('mc_mask_store','mc_a_read','mc_b_read','mc_x_read')
    for seq,index in sorted(mapping.items()):
        c=reference[index]; a=activities.get(seq)
        name=next((n for n in writer_names+store_names if c.pc==symbols[n]),None)
        if a is None:
            require(name is None and not c.vector_writes,'Missing backend writer/store'); continue
        require(a.instruction==c.instruction and a.allocations==a.completions and a.allocations>0,
                'Native opcode/lifecycle')
        for w in a.writes:
            require(w.arch_seq==seq and w.instruction==c.instruction and 0<=w.lane<4 and 0<=w.eew<=3 and
                    0<w.be<256 and w.be&~w.known_be==0,'Unique owner/known accepted native bytes')
        actual=vc._architectural_bytes(a.writes,4,1024)
        if name in store_names:
            request_context(rows,seq,c.instruction,8 if name=='mc_mask_store' else 128,0,0,False)
            require(not c.vector_writes and not a.use_vd,'Store not an architectural writer')
            if actual:
                require(all(w.source==3 for w in a.writes),'Only identity transport on store')
                for w in a.writes:
                    individual=vc._architectural_bytes([w],4,1024)
                    require(all(reg in state and v==(state[reg]>>(8*b)&255) for (reg,b),(v,_) in individual.items()),
                            'Store identity transport changed native prestate')
            counts[name]+=1
        elif c.vector_writes:
            require(name in writer_names and actual,'Classified writer with accepted bytes')
            compare=name=='mc_compare'; start=p.STARTS[compare_case] if compare else 0
            vl=64 if name in ('mc_compare','mc_xor') else 128
            vd=next(iter(c.vector_writes)); request_context(rows,seq,c.instruction,vl,start,vd,True)
            require(a.vl==vl and a.vstart==start and a.eew==0 and a.vd==vd and a.use_vd,'Native writer context')
            source_id=4 if name in ('mc_init_a','mc_init_b') else 2 if compare else 1
            require(all(w.source==source_id for w in a.writes),'Exact writer producer')
            if compare:
                require(vd==1 and c.instruction>>26==26 and c.instruction>>12&7==0 and
                        c.instruction>>20&31==8 and c.instruction>>15&31==16 and c.instruction>>25&1==1,
                        'Exact unmasked VMSLTU.vv identity')
                require(1 in state and state[1]==0 and all(reg==1 for reg,b in actual),'Proven zero prestate/exact vd')
                after=state[1]
                for (reg,b),(value,_) in actual.items(): after=(after&~(255<<(8*b)))|(value<<(8*b))
                proof=mask_postimage(state[1],after,start); state[1]=after; compare_case+=1
            else:
                gold={(reg,b):(value>>(8*b))&255 for reg,value in c.vector_writes.items() for b in range(128)}
                if name=='mc_xor':
                    require(24 in state,'Proven initial complete xor destination')
                    require(all(reg==24 and b<64 for reg,b in actual),'Only defined active xor bytes')
                    require(set(actual)=={(24,b) for b in range(64)},'All active xor bytes present')
                    require(all(value==gold[k] for k,(value,_) in actual.items()),'Strict xor defined bytes')
                    for (reg,b),(value,_) in actual.items(): state[reg]=(state[reg]&~(255<<(8*b)))|(value<<(8*b))
                    require(state[24]==c.vector_writes[24],'Full known TU xor postimage')
                else:
                    require({k:v for k,(v,_) in actual.items()}==gold,'Strict full load/clear image')
                    state.update(c.vector_writes)
                proof=dict(strict_postimage=True)
            counts[name]+=1
            records.append(dict(arch_seq=seq,pc=c.pc,opcode=c.instruction,kind=name,proof=proof))
        else:
            require(not actual,'Unclassified native VRF writer')
    require(counts==Counter(mc_init_a=1,mc_init_b=1,mc_clear24=1,mc_clear1=3,mc_compare=3,mc_xor=3,
                           mc_mask_store=3,mc_a_read=3,mc_b_read=3,mc_x_read=3),'Complete exact writer/store population')
    return dict(status='FULL_DEFINED_AND_LEGAL_MASK_POSTIMAGE_NATIVE_PASS',counts=dict(counts),
                primary_writers=12,defined_mask_bits=192,mask_tail_bits_checked=2880,
                unknown_active_bytes_skipped=0,whole_destination_skipped=False,instructions=records)


def native(run,reference,symbols):
    lanes,vlen,activities=vc._parse_vector_trace(run/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(run/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected,'Geometry/no rejected requests')
    arch=vc._map_architecture_retires(starts,retires,rejected); mapping=vc._map_spike_commits(arch,reference)
    require(all(arch[s].pc==reference[i].pc and arch[s].instruction==reference[i].instruction for s,i in mapping.items()),
            'Exact PC/opcode/arch_seq mapping')
    rows=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
    return native_state(reference,activities,mapping,symbols,rows)


def raw_gain(run,out,manifest):
    a=life.read_bound(runner.BASE/'admission-manifest.json',runner.BASE_SHA)
    path=runner.BASE/'combined-bits.json'; before=life.read_bound(path,a['output_pins'][str(path)])
    ledger=(runner.BASE/'combined-inputs.txt').read_text().splitlines(); sample_path=run/'code.vdb'
    require(before['tests']==ledger[1:] and len(before['tests'])==786 and str(sample_path) not in ledger,'Exact786 prefix/unique')
    folder=sample_path/'snps/coverage/db/testdata'/runner.NAME
    require(list(folder.parent.iterdir())==[folder],'Exactly one native test')
    sim=runner.toggle.xml(folder/'siminfo.xml').findall('srctest')
    require(len(sim)==1 and shlex.split(sim[0].get('cmdline',''))==manifest['command'] and
            sim[0].get('workdir')==str(run) and
            int(sim[0].get('finishtime','0'))>int(sim[0].get('starttime','0'))>0,'Native command/cwd/finish witness')
    inputs=out/'single-inputs.txt'; inputs.write_text(ledger[0]+'\n'+str(sample_path)+'\n')
    single=runner.bitmap.collect(inputs); combined=runner.bitmap.combine(before,single)
    require(single['design']==before['design']==combined['design'] and len(single['tests'])==1 and
            combined['tests']==before['tests']+single['tests'],'Exact compiled shape/786 prefix OR')
    counts={'line':1892,'cond':2023,'branch':2155,'fsm':92}
    require(set(before['metrics'])==set(single['metrics'])==set(combined['metrics'])==set(counts),'Exact metric families')
    for metric,count in counts.items():
        old,new,result=(x['metrics'][metric] for x in (before,single,combined))
        require(len(old)==count and set(old)==set(new)==set(result),'Exact metric-instance universe')
        for scope,row in old.items():
            add,final=new[scope],result[scope]
            require((row['width'],row['checksum'])==(add['width'],add['checksum'])==(final['width'],final['checksum']),
                    'Exact width/checksum')
            aa,bb,cc=(int(r['bits'],16) for r in (row,add,final))
            require(min(aa,bb,cc)>=0 and max(aa,bb,cc).bit_length()<=row['width'] and cc==aa|bb,'Full6162 mathematical OR')
    sample,h=runner.toggle.rows(folder/'tgl.verilog.data.xml',manifest['scoped_toggle_before'])
    gained=runner.toggle.gains(manifest['scoped_toggle_before'],runner.toggle.union(manifest['scoped_toggle_before'],sample))
    targets=[dict(scope=t['scope'],field=t['field'],coordinate=i) for t in manifest['targets']
             for i in t['missing_coordinates'] if i in gained[t['scope']]]
    delta=runner.bitmap.delta(before,combined)
    for name,value in (('single-bits.json',single),('proposed-combined-bits.json',combined),('raw-delta.json',delta)):
        life.save(out/name,value)
    return dict(baseline=786,targets=targets,target_hit_count=len(targets),native_toggle_sha=h,
                metric_instance_records=sum(counts.values()),full_OR_verified=True,exact_prefix=True,
                scoped_toggle_new_coordinates=gained,raw_delta=delta['metrics'],official_percentage=None)


def collect(run,seal,out):
    require(out.parent==life.OUT and not out.exists(),'Fresh offline output')
    manifest=life.read_bound(run.with_name(run.name+'.prepared.json'),seal)
    require(manifest==runner.prepare(run,existing=True),'Exact reconstructed sealed runtime')
    life.check(manifest['pins']); terminal(run,manifest)
    pre=runner.preflight(); reference=reference_prefix(pre)
    pins=life.merge_pins(manifest['pins'],{str(run.with_name(run.name+'.prepared.json')):seal})
    pins=life.merge_pins(pins,{str(f):life.digest(f) for f in run.rglob('*') if f.is_file()})
    out.mkdir()
    try:
        rows=common.read_csv((run/'commit_trace.csv').read_bytes(),common.COMMIT_FIELDS)
        vectors=common.read_csv((run/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
        lifecycle=control.lifecycle(rows,vectors); mature.logs(run,lifecycle)
        scalar=common.spike_trace.compare_commit_prefix(Path(pre['reference']),run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=pre['symbols']['tohost'],rtl_exception_log=run/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        common.scalar_exact(scalar,common.reference_counts(reference,pre['symbols']))
        signature=footprint(rows,pre['symbols']); mem=memory.scalar_memory_exact(rows,reference)
        native_proof=native(run,reference,pre['symbols']); gain=raw_gain(run,out,manifest)
        pins=life.merge_pins(pins,{str(f):life.digest(f) for f in out.iterdir() if f.is_file()}); life.check(pins)
        result=dict(status='MASK_COMPARE_RESTART_FULL_STRICT_RAW786_PASS_NOT_ADMITTED',run=str(run),prepared_seal=seal,
            terminal=terminal(run,manifest),scalar=scalar,scalar_memory=mem,signature=signature,native=native_proof,
            lifecycle=lifecycle,raw_gain=gain,input_pins=pins,coverage_admitted=False,EDA_launched=False,RTL_modified=False)
        life.save(out/'qualification.json',result); print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'))
    except Exception as error:
        life.save(out/'failure.json',dict(reason=str(error),status='FAIL_OR_HOLD_NOT_ADMITTED',no_retry=True)); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--seal',required=True); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); collect(args.run.resolve(),args.seal,args.output.resolve())
