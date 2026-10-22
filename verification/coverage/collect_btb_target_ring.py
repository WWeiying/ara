"""Terminal-only BTB32 architecture/update/AXI and raw777 gain; never admission."""
import argparse
from collections import Counter, defaultdict, deque
import csv
import json
from pathlib import Path
import re
import subprocess
from types import FunctionType
import run_btb_target_ring as runner
import audit_gap115_axi_v2 as wave
import collect_itlb_asid_exec_bulk_axi as axi
import coverage_bitmap_delta as bitmap
from ara_verify.contract import check_contract_log, parse_contract_summary

pre, life, require = runner.pre, runner.life, runner.require
CORE = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'
BTB = pre.SCOPE
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA = '195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'
UPDATE = [('valid',1),('pc',64),('target_address',64)]
RESOLVE = [('valid',1),('pc',64),('target_address',64),('is_mispredict',1),('is_taken',1),('cf_type',3)]


def source_contract():
    pins = axi.source_contract()
    book = life.read_bound(pre.BOOK,pre.BOOK_SHA)
    names = ('hardware/deps/cva6/core/cva6.sv','hardware/deps/cva6/core/include/ariane_pkg.sv',
             'hardware/deps/cva6/core/frontend/frontend.sv','hardware/deps/cva6/core/frontend/btb.sv',
             'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv')
    for rel in names:
        p=life.ROOT/rel;pins=life.merge_pins(pins,{str(p):book[str(p)]})
    life.check(pins)
    texts=[axi.clean((life.ROOT/n).read_text()) for n in names]
    for text,typ,fields in ((texts[0],'bp_resolve_t',RESOLVE),(texts[2],'btb_update_t',UPDATE)):
        m=re.findall(r'localparamtype'+typ+r'=structpacked\{(.*?)\}',text)
        expected=''.join(('cf_t' if n=='cf_type' else 'logic[CVA6Cfg.VLEN-1:0]' if w==64 else 'logic')+n+';' for n,w in fields)
        require(m==[expected],'Frozen packed branch field order differs')
    require('typedefenumlogic[2:0]{NoCF,Branch,Jump,JumpR,Return}cf_t;' in texts[1], 'JumpR enum differs')
    require("VLEN:unsigned'(64)," in texts[4] and 'localparamCVA6ConfigBTBEntries=32;' in texts[4], 'Frozen BTB dimensions differ')
    for token in ('assignbtb_update.valid=resolved_branch_i.valid&resolved_branch_i.is_mispredict&(resolved_branch_i.cf_type==ariane_pkg::JumpR);',
                  'assignbtb_update.pc=resolved_branch_i.pc;',
                  'assignbtb_update.target_address=resolved_branch_i.target_address;'):
        require(token in texts[2],'Frozen frontend update producer differs')
    require('if(btb_update_i.valid&&!debug_mode_i)' in texts[3], 'BTB write enable differs')
    return pins


def branch_projection(iterator):
    _, decl=next(iterator);decl=dict(decl);fields=[]
    for parent,members in ((BTB+'.btb_update_i',UPDATE),(CORE+'.i_frontend.resolved_branch_i',RESOLVE)):
        total=sum(w for _,w in members);names=[parent+'.'+n for n,_ in members]
        if parent in decl:
            require(decl[parent]['width']==total and not any(n in decl for n in names),'Mixed/foreign branch encoding')
            offset=total
            for name,width in members:
                offset-=width;code='BTB_SOURCE_'+parent+'.'+name
                require(not any(d['code']==code for d in decl.values()),'Derived identifier collision')
                decl[parent+'.'+name]=dict(width=width,code=code,type='source-derived-packed-member')
                fields.append((decl[parent]['code'],total,offset,width,code))
        else:
            require(all(decl.get(parent+'.'+n,{}).get('width')==w for n,w in members), 'Missing exact native branch members')
    yield 'declarations',decl
    for time,before,after in iterator:
        states=[]
        for original in (before,after):
            state=dict(original)
            for code,total,offset,width,out in fields:
                bits=original.get(code,'x'*total)
                require(len(bits)==total and set(bits)<=set('01xz'),'Malformed packed branch value')
                state[out]=bits[total-offset-width:total-offset]
            states.append(state)
        yield time,*states


def update_audit(iterator,s):
    _,decl=next(iterator)
    widths={'ara_tb.clk':1,'ara_tb.rst_n':1,BTB+'.update_pc':4,BTB+'.update_row_index':1,
            BTB+'.debug_mode_i':1,BTB+'.flush_bp_i':1}
    for parent,fields in ((BTB+'.btb_update_i',UPDATE),(CORE+'.i_frontend.resolved_branch_i',RESOLVE)):
        widths.update({parent+'.'+n:w for n,w in fields})
    require(all(decl.get(n,{}).get('width')==w for n,w in widths.items()),'Missing/mismatched BTB probe width')
    def value(state,name):
        bits=state.get(decl[name]['code'],'x')
        require(len(bits)==widths[name] and set(bits)<=set('01'),'Unknown active BTB field '+name)
        return int(bits,2)
    sources={s['btb_bank%d'%b]+4*r:(r,b) for b in (0,1) for r in range(16)}
    records=[];resolved=[];started=False
    for time,before,after in iterator:
        clock,reset=decl['ara_tb.clk']['code'],decl['ara_tb.rst_n']['code']
        require(not(started and before.get(reset)=='1' and after.get(reset)=='0'),'Unexpected reset after startup')
        if before.get(clock)!='0' or after.get(clock)!='1' or before.get(reset)!='1':continue
        started=True
        u=BTB+'.btb_update_i.';r=CORE+'.i_frontend.resolved_branch_i.'
        uv,rv=value(before,u+'valid'),value(before,r+'valid')
        if not rv:require(not uv,'Update without resolved branch');continue
        pc=value(before,r+'pc')
        if pc not in sources:continue
        target=value(before,r+'target_address');row,slot=sources[pc]
        require(value(before,r+'cf_type')==3 and value(before,r+'is_mispredict')==1 and uv==1,
                'Source executed without required JumpR mispredict/update')
        require(value(before,u+'pc')==pc and value(before,u+'target_address')==target and
                value(before,BTB+'.update_pc')==row and value(before,BTB+'.update_row_index')==slot and
                (pc>>2&15)==row and (pc>>1&1)==slot and
                value(before,BTB+'.debug_mode_i')==0 and value(before,BTB+'.flush_bp_i')==0,
                'Exact source/bank/update enable differs')
        record=dict(time_100fs=time,pc=hex(pc),target=hex(target),row=row,slot=slot,
                    JumpR=True,mispredict=True,preedge_update=True)
        records.append(record);resolved.append((pc,target))
    expected=[(s['btb_bank%d'%b]+4*r,t) for b in (0,1) for r in range(16) for t in pre.TARGETS]
    require(resolved==expected and len({(r['row'],r['slot']) for r in records})==32,
            'Exact32 slots/96 A-B-A updates missing, duplicated or reordered')
    return dict(status='EXACT32_SLOT_A_B_A_PREEDGE_UPDATE_PASS',records=records,
                slots=32,updates=96,direction_labels_inferred=False,stored_q_not_directly_probed=True)


def axi_audit(iterator):
    _,decl=next(iterator)
    clock,reset=[decl['ara_tb.'+n]['code'] for n in ('clk','rst_n')]
    def v(state,port,field):
        full=CORE+'.'+port+'.'+field
        require(full in decl,'Missing AXI field '+full)
        bits=state.get(decl[full]['code'],'x')
        require(set(bits)<=set('01'),'Unknown active AXI field '+full)
        return int(bits,2)
    reads,writes=defaultdict(deque),defaultdict(deque)
    aws,frames,wframe=deque(),deque(),[];held={};counts=Counter();started=False
    for _,before,after in iterator:
        require(not(started and before.get(reset)=='1' and after.get(reset)=='0'),'Unexpected AXI reset')
        if before.get(clock)!='0' or after.get(clock)!='1' or before.get(reset)!='1':continue
        started=True;fired={}
        for ch,fields in axi.CHANNELS.items():
            name=ch.lower();request=ch in ('AW','AR','W')
            port='noc_req_o' if request else 'noc_resp_i';other='noc_resp_i' if request else 'noc_req_o'
            valid,ready=v(before,port,name+'_valid'),v(before,other,name+'_ready')
            payload=tuple(v(before,port,name+'.'+f) for _,f in fields) if valid else None
            require(name not in held or payload==held[name],'Unstable AXI held payload '+name)
            if valid and not ready:held[name]=payload
            else:held.pop(name,None)
            if valid and ready:fired[name]=payload;counts[name]+=1
        for ch in ('ar','aw'):
            if ch not in fired:continue
            p=fired[ch];ident,address,length,size,burst=p[:5]
            require(size<=3 and burst in (0,1) and (address&4095)+(length+1)*(1<<size)<=4096,'Illegal AXI burst')
            item=dict(beats=length+1,received=0,id=ident)
            if ch=='ar':reads[ident].append(item)
            else:require(p[10]==0,'Unexpected atomic AW');aws.append(item)
        if 'r' in fired:
            ident,_,resp,last,_=fired['r'];require(reads[ident],'Orphan R')
            item=reads[ident][0];item['received']+=1
            require(resp==0 and last==int(item['received']==item['beats']),'R response/last differs')
            if last:reads[ident].popleft()
        if 'w' in fired:
            wframe.append(fired['w'])
            if fired['w'][2]:frames.append(wframe);wframe=[]
        while aws and frames:
            item,frame=aws.popleft(),frames.popleft()
            require(len(frame)==item['beats'] and all(p[2]==int(i==len(frame)-1) for i,p in enumerate(frame)), 'W length/last differs')
            writes[item['id']].append(item)
        if 'b' in fired:
            ident,resp,_=fired['b'];require(writes[ident] and resp==0,'Orphan/error B');writes[ident].popleft()
    require(started and counts['ar']>0 and counts['aw']>0 and not held and not aws and not frames and not wframe and
            not any(reads.values()) and not any(writes.values()),'AXI incomplete final drain')
    return dict(status='FULL_SCALAR_AXI_PREEDGE_DRAIN_PASS',channels=dict(counts),no_reset_after_startup=True)


def native_gold(rows,q):
    retired=[r for r in rows if r['event']=='retire']
    require([int(r['order']) for r in retired]==list(range(len(retired))),'Retirement order gap')
    traps=[r for r in retired if int(r['trap'])]
    require(len(traps)==1 and int(traps[0]['pc'],16)==q['symbols']['btb_s_ecall'] and
            int(traps[0]['insn'],16)==0x73,'One exact S ecall retirement')
    commits=[]
    for r in retired:
        if int(r['trap']):continue
        accesses=();rd=int(r['rd']);gpr={rd:int(r['rd_wdata'],16)} if rd else {}
        if int(r['mem_wmask'],16):
            addr,data=pre.arch.scalar_store(r);accesses=((addr,int.from_bytes(data,'little')),)
        elif int(r['mem_rmask'],16):accesses=((int(r['mem_addr'],16),None),)
        commits.append(pre.arch.spike_trace.SpikeCommit(int(r['pc'],16),int(r['insn'],16),gpr,{}, {},{},accesses))
    require(pre.interval(commits)==commits,'Complete native entry/terminal interval')
    require(pre.validate(commits,q['symbols'],[('trap_supervisor_ecall',q['symbols']['btb_s_ecall'])])==q['counts'],
            'Native complete data/VRF/CSR/code/PTE/guard readback differs')
    return dict(checks=2690,failed=0,full_VRF_bytes=4096,guard_bytes=128,restored_machine_CSRs=9,
                vector_FP_CSRs=5,exact_S_ecall_PC=hex(q['symbols']['btb_s_ecall']),source_executions=96)


def vector_gate(result,commits):
    expected=[c for c in commits if c.vector_writes]
    require(len(expected)==4 and sum(len(c.vector_writes)*128 for c in expected)==4096,'Independent four m8 full seed writers')
    fixed=dict(status='PASS',compared_instructions=4,compared_bytes=4096,skipped_unknown_bytes=0,
               non_bit_exact_instructions=0,unobservable_instructions=0,incomplete_requests=[],
               unretired_requests=[],trapped_requests=[],first_mismatch=None,nr_lanes=4,vlen_bits=1024)
    require(all(type(result.get(k)) is type(v) and result.get(k)==v for k,v in fixed.items()),'Complete exact VRF comparator contract differs')
    records=result.get('instructions',[])
    require(len(records)==4,'Missing vector writer records')
    for record,gold in zip(records,expected):
        require(record['pc']=='0x%016x'%gold.pc and record['instruction']=='0x%08x'%gold.instruction and
                all(record.get(k)==v for k,v in dict(status='PASS',compared_bytes=1024,skipped_unknown_bytes=0,
                    unknown_write_bytes=0,mismatch_count=0,first_mismatch=None).items()),'Per-writer identity/unknown/byte contract differs')


def lifecycle(rows,vectors,summary):
    starts,pending,backend,done={}, {}, {}, {}
    requests,replies,allocs,completes=Counter(),Counter(),Counter(),Counter()
    retired={int(r['order']):r for r in rows if r['event']=='retire'}
    for r in rows:
        event,seq,tid=r['event'],int(r['order']),int(r['trans_id'])
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Duplicate start/live TID')
            starts[seq]=r;pending[tid]=(seq,False)
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1],'Unknown/duplicate request')
            seq=pending[tid][0];require(r['insn']==starts[seq]['insn'],'Request opcode differs')
            pending[tid]=(seq,True);requests[seq]+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1] and not int(r['trap']) and
                seq==-1 and int(r['pc'],16)==int(r['insn'],16)==0,'Unknown/exception response')
            seq=pending.pop(tid)[0];replies[seq]+=1
        elif event in ('uop_alloc','uop_done'):
            key=(seq,int(r['port']))
            require(seq in starts and r['insn']==starts[seq]['insn'] and
                int(r['cycle'])>=int(starts[seq]['cycle']),'Backend identity/time differs')
            if event=='uop_alloc':
                require(key not in backend,'Live backend VID reused');backend[key]=r;allocs[key]+=1
            else:
                require(key in backend and int(r['cycle'])>=int(backend[key]['cycle']),'Unallocated/early done')
                done[key]=r;backend.pop(key);completes[key]+=1
        else:require(event=='retire','Unknown commit event')
    require(not pending and not backend and requests==replies==Counter(starts.keys()) and allocs==completes,
            'Full request/backend conservation differs')
    for seq,start in starts.items():
        require(seq in retired and not int(retired[seq]['trap']) and retired[seq]['insn']==start['insn'] and
            int(retired[seq]['cycle'])>=int(start['cycle']),'Accepted request unretired/identity mismatch')
    live,finished={},{};va,vd=Counter(),Counter()
    for r in vectors:
        event,seq=r['event'],int(r['arch_seq'])
        if event=='config':continue
        key=(seq,int(r['vid']))
        require(seq in starts and r['insn']==starts[seq]['insn'] and
            int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024 and
            event in ('alloc','done','write'),'Foreign vector activity')
        if event=='alloc':
            require(key not in live,'Live vector VID reused');live[key]=r;va[key]+=1
        else:
            owner=live.get(key)
            if owner is None and event=='write':
                owner=finished.get(key)
                require(owner is not None and owner['cycle']==r['cycle'],'Late write beyond done')
            require(owner is not None and int(r['cycle'])>=int(owner['cycle']) and
                all(r[k]==owner[k] for k in ('insn','use_vd','vd','eew','vl','vstart')), 'Vector activity metadata/time differs')
            if event=='done':finished[key]=r;live.pop(key);vd[key]+=1
    require(not live and va==vd==allocs and summary['requests']==sum(requests.values()) and
            summary['responses']==sum(replies.values()),'Commit/vector/summary conservation differs')
    return dict(requests=sum(requests.values()),responses=sum(replies.values()),backend_uops=sum(allocs.values()),
                all_requests_retired=True,all_vector_uops_complete=True)


def collect(prepared,seal,out,vcd=None):
    require(out.parent==life.OUT and not out.exists(),'Fresh offline output')
    r=life.read_bound(prepared,seal);run=runner.validate_record(r)
    q=life.read_bound(Path(r['preflight']),r['preflight_seal'])
    pins=life.merge_pins(r['pins'],{str(prepared):seal});life.check(pins)
    require(json.loads((run/'manifest.json').read_bytes())==dict(r,pins=pins),'Executed/prepared full manifest differs')
    terminal=json.loads((run/'simulation-status.json').read_bytes())
    require(terminal.get('status')=='SIMULATION_EXITED_NOT_ADMITTED' and type(terminal.get('returncode')) is int and
            terminal['returncode']==0 and terminal['case']==runner.CASE and terminal['coverage_admitted'] is False,
            'No successful simulator terminal')
    pins=life.merge_pins(pins,source_contract())
    for module in (runner,pre,pre.arch,pre.arch.spike_trace,wave,axi,bitmap,pre.toggle,pre.toggle.base):
        p=Path(module.__file__).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_btb_target_ring.py').resolve(),
              Path(pre.arch.compare_vector_commits.__code__.co_filename).resolve(),
              Path(check_contract_log.__code__.co_filename).resolve()):
        pins=life.merge_pins(pins,{str(p):life.digest(p)})
    for p in run.rglob('*'):
        if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    if vcd is not None:pins=life.merge_pins(pins,{str(vcd):life.digest(vcd)})
    life.check(pins);out.mkdir()
    try:
        lines=(run/'console.log').read_text().splitlines()
        require(lines.count('BTB_RING_READY')==1 and len([l for l in lines if l.startswith('BTB_RING_OBJECT ')])==10 and
                not any(l.startswith(('BTB_RING_ERROR','UCLI_ERROR','Error-')) for l in lines),'Exact probe startup/error')
        require(not check_contract_log(run/'console.log'),'Complete real accelerator contract log rejected')
        summaries=[parse_contract_summary(l) for l in lines if '[ARA_CONTRACT]' in l]
        require(len(summaries)==1 and summaries[0]['exceptions']==0,'Unexpected accelerator exception')
        pp=Path(r['preflight']).parent
        commits=pre.interval(pre.build.parse_spike_commits(pp/'spike.trace'))
        exc=[(k,int(pc,16)) for k,pc in re.findall(r'exception (\w+), epc (0x[0-9a-f]+)',(pp/'spike.trace').read_text())]
        require(pre.validate(commits,q['symbols'],exc)==q['counts'],'Sealed actual Spike gold differs')
        scalar=pre.arch.spike_trace.compare_commit_prefix(pp/'spike.trace',run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(out/'scalar-comparison.json',scalar)
        pre.arch.scalar_exact(scalar,dict(q['counts'],ara_trap_events=1))
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        life.save(out/'native-gold.json',native_gold(rows,q))
        with (run/'vector_trace.csv').open() as f:vectors=list(csv.DictReader(f))
        life.save(out/'lifecycle.json',lifecycle(rows,vectors,summaries[0]))
        vector=pre.arch.compare_vector_commits(pp/'spike.trace',run/'commit_trace.csv',run/'vector_trace.csv',0x80000000)
        life.save(out/'vector-comparison.json',vector);vector_gate(vector,commits)
        wavefile=run/'btb-target-ring.vpd'
        require(0<wavefile.stat().st_size<=r['wave_limit_bytes'],'Focused VPD cap')
        if vcd is None:
            require(life.digest(CONVERTER)==CONVERTER_SHA,'Frozen converter differs')
            pins=life.merge_pins(pins,{str(CONVERTER):CONVERTER_SHA});vcd=out/'btb-target-ring.vcd'
            with (out/'convert.log').open('x') as f:
                subprocess.run([str(CONVERTER),'-splitpacked',str(wavefile),str(vcd)],stdout=f,stderr=subprocess.STDOUT,timeout=120,check=True)
        parser=FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
        life.save(out/'slot-updates.json',update_audit(iter(branch_projection(iter(parser(vcd)))),q['symbols']))
        life.save(out/'axi-audit.json',axi_audit(iter(axi.project(iter(parser(vcd))))))
        pred,bpins=pre.static_evidence();require(pred==q['prediction'],'Formal777 scoped baseline differs')
        pins=life.merge_pins(pins,bpins)
        fs=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(fs)==1,'Unique Toggle sample')
        sample,sha=pre.toggle.rows(fs[0],[BTB]);pins=life.merge_pins(pins,{str(fs[0]):sha})
        before={BTB:pred['baseline']};merged=pre.toggle.union(before,sample)
        gain=pre.toggle.gains(before,merged)[BTB]
        life.save(out/'toggle-gain.json',dict(baseline=777,scope=BTB,before=before[BTB],single=sample[BTB],
            after=merged[BTB],new_positions=len(gain),new_serialized_positions=gain,
            direction_labels_verified=False,official_percentage=False))
        base=life.read_bound(pre.BASE/'admission-manifest.json',pre.BASE_SHA)
        ledger=pre.BASE/'combined-inputs.txt';design=ledger.read_text().splitlines()[0]
        with (out/'single-inputs.txt').open('x') as f:f.write(design+'\n'+str(run/'code.vdb')+'\n')
        single=bitmap.collect(out/'single-inputs.txt');bpath=pre.BASE/'combined-bits.json'
        bsha=base['output_pins'][str(bpath)];old=life.read_bound(bpath,bsha);pins=life.merge_pins(pins,{str(bpath):bsha})
        require(len(old['tests'])==len(set(old['tests']))==777 and single['tests']==[str(run/'code.vdb')], 'Exact777 prefix plus unique test')
        combined=bitmap.combine(old,single);count=0
        for metric,instances in old['metrics'].items():
            for scope,a in instances.items():
                require(int(combined['metrics'][metric][scope]['bits'],16)==int(a['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Independent full OR')
                count+=1
        require(count==6162 and combined['tests']==old['tests']+single['tests'] and len(set(combined['tests']))==778,'Full6162 exact prefix/unique OR')
        for path,h in single['input_hashes'].items():pins=life.merge_pins(pins,{path:h})
        for rel,h in single['design'].items():pins=life.merge_pins(pins,{str(Path(design)/'snps/coverage/db'/rel):h})
        life.save(out/'single-bits.json',single);life.save(out/'raw-delta777.json',bitmap.delta(old,combined))
        life.check(pins);life.save(out/'evidence-pins.json',pins)
        life.save(out/'qualification.json',dict(status='BTB32_ARCHITECTURE_AXI_ACTUAL_UPDATES_QUALIFIED_NOT_ADMITTED',
            baseline=777,slots=32,updates=96,checks=2690,full_scalar_ISA=True,coverage_admitted=False,
            measured_toggle_positions=len(gain),input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}))
        print('BTB_QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'),flush=True)
    except Exception as e:
        life.save(out/'failure.json',dict(reason=str(e),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--vcd',type=Path)
    a=p.parse_args();collect(a.prepared.absolute(),a.seal,a.output.absolute(),a.vcd.absolute() if a.vcd else None)
