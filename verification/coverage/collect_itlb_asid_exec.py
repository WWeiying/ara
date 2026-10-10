"""Terminal-only exact scalar/PTE/code/CSR and preedgeITLB/AXI evidence; no admission."""
import argparse
from collections import Counter, defaultdict, deque
import csv
from pathlib import Path
import re
import subprocess
from types import FunctionType
import traceback
import build_itlb_asid_exec as pre
import run_itlb_asid_exec as runner
import collect_tlb_asid_matrix as reference
import coverage_bitmap_delta as bitmap
import audit_gap115_axi_v2 as wave

life,require=pre.life,pre.require
CONVERTER=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')
CONVERTER_SHA='195fae31e4cbacabcbbd97bfd61c98a333f68ff2fd013002ab322e5108f97002'
CORE=pre.SCOPE.split('.ex_stage_i')[0]


def trap_contract(rows,symbols):
    require(rows and all(r['event']=='retire' for r in rows) and
        [int(r['order']) for r in rows]==list(range(len(rows))),'Complete contiguous retirement required')
    traps=[i for i,r in enumerate(rows) if int(r['trap'])]
    require(len(traps)==48,'Exactly48 supervisor ECALLs required')
    bindings=[]
    for index,i in enumerate(traps):
        p,e=divmod(index,16);r=rows[i];pc=pre.address(p,e)+8
        require(int(r['pc'],16)==pc and int(r['insn'],16)==0x73 and int(r['rd'])==0 and
            int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0,'Exact ECALL PC/encoding/no effect differs')
        require(i+1<len(rows),'Missing trap handler');h=rows[i+1];word=int(h['insn'],16)
        require(int(h['pc'],16)==symbols['itm_handler'] and word>>20==0x342 and word&0x707f==0x2073
            and int(h['rd_wdata'],16)==9 and not int(h['trap']),'Exact immediate cause9 handler differs')
        end=next((j for j in range(i+2,len(rows)) if int(rows[j]['pc'],16)==symbols['itm_resume']),None)
        require(end is not None and not any(int(x['trap']) for x in rows[i+1:end]),'Missing unique trap return')
        epc=[x for x in rows[i+1:end] if int(x['insn'],16)>>20==0x341 and int(x['insn'],16)&0x707f==0x2073]
        require(len(epc)==1 and int(epc[0]['rd_wdata'],16)==pc and
            int(rows[end-1]['insn'],16)==0x30200073,'Exact mepc/MRET/resume differs')
        bindings.append(dict(phase=p,entry=e,ecall_pc=hex(pc),trap_order=i,resume_order=end))
    require(len({b['resume_order'] for b in bindings})==48,'Reused trap return')
    return bindings


def exact_scalar(result,counts):
    expected=dict(counts,status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
        rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
        stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=48,mismatch=None,
        terminal_ecall=None,vector_state_compared=False,
        ara_retired_instructions=counts['matched_instructions']+48,
        ara_committed_instructions=counts['matched_instructions'])
    for key,value in expected.items():
        require(type(result.get(key)) is type(value) and result[key]==value,'Exact scalar differs: '+key)
    require(result['terminal_tohost']['address']=='0x0000000080001000' and
        result['terminal_tohost']['write_value']=='0x1','Terminal value differs')


def markers(text):
    reference.console_gate(text)
    lines=text.splitlines()
    expected=['ara_tb.clk','ara_tb.rst_n',CORE+'.noc_req_o',CORE+'.noc_resp_i']+[
        pre.SCOPE+'.'+s for s in ('update_i','replace_en','lu_hit_o','lu_access_i','lu_asid_i',
            'lu_vaddr_i','plru_tree_q','flush_i','s_st_enbl_i')]
    require([l for l in lines if l.startswith('ITLB_EXEC_OBJECT ')]==['ITLB_EXEC_OBJECT '+x for x in expected] and
        lines.count('ITLB_EXEC_READY')==1 and not any(l.startswith('ITLB_EXEC_ERROR') for l in lines),
        'Actual observation object/ready/error differs')


def waveform(path):
    parse=FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    iterator=iter(parse(path));_,decl=next(iterator)
    widths={'update_i.valid':1,'update_i.asid':16,'update_i.vpn':27,'replace_en':16,'lu_hit_o':1,
        'lu_access_i':1,'lu_asid_i':16,'lu_vaddr_i':64,'plru_tree_q':30,'flush_i':1,'s_st_enbl_i':1}
    for name,width in widths.items():
        require(decl.get(pre.SCOPE+'.'+name,{}).get('width')==width,'Frozen ITLB packed declaration differs: '+name)
    def val(state,name):
        require(name in decl,'Missing named waveform field: '+name)
        bits=state.get(decl[name]['code'],'x')
        require(set(bits)<=set('01'),'Unknown active waveform field: '+name)
        return int(bits,2)
    def t(state,name):return val(state,pre.SCOPE+'.'+name)
    def c(state,name):return val(state,CORE+'.'+name)
    channel_fields={'ar':['id','addr','len','size','burst','lock','cache','prot','qos','region','user'],
        'aw':['id','addr','len','size','burst','lock','cache','prot','qos','region','atop','user'],
        'w':['data','strb','last','user'],'r':['id','data','resp','last','user'],'b':['id','resp','user']}
    reads,writes=defaultdict(deque),defaultdict(deque);aws,frames,frame=deque(),deque(),[]
    held={};counts=Counter();updates=[];lookups=[];plru=[];active=False;phase=-1;previous_asid=None
    for time,before,after in iterator:
        clk=decl['ara_tb.clk']['code'];rst=decl['ara_tb.rst_n']['code']
        require(not(active and before.get(rst)=='1' and after.get(rst)=='0'),'Unexpected post-startup reset')
        if before.get(clk)!='0' or after.get(clk)!='1' or before.get(rst)!='1':continue
        active=True
        if t(before,'update_i.valid') and not t(before,'lu_hit_o') and not t(before,'flush_i'):
            asid=t(before,'update_i.asid');vpn=t(before,'update_i.vpn');mask=t(before,'replace_en')
            require(mask>0 and mask&(mask-1)==0,'Ambiguous ITLB replacement entry')
            if asid!=previous_asid:phase+=1;previous_asid=asid
            require(phase<3 and asid==[0x5555,0xaaaa,0x5555][phase] and
                vpn in {pre.shared.vpn(phase,e) for e in range(16)},'Foreign/reordered translated update')
            updates.append(dict(time_100fs=time,phase=phase,asid=asid,vpn=vpn,entry=mask.bit_length()-1,
                plru=t(before,'plru_tree_q'),lookup_vaddr=hex(t(before,'lu_vaddr_i'))))
        if t(before,'s_st_enbl_i') and t(before,'lu_access_i') and t(before,'lu_hit_o'):
            asid=t(before,'lu_asid_i');vpn=(t(before,'lu_vaddr_i')>>12)&0x7ffffff
            # Speculation may request another instruction inside the same target page.
            require(asid in (0x5555,0xaaaa),'Foreign translated lookup ASID')
            lookups.append(dict(time_100fs=time,asid=asid,vpn=vpn))
        tree=t(before,'plru_tree_q')
        if not plru or plru[-1]['value']!=tree:plru.append(dict(time_100fs=time,value=tree))
        fired={}
        for channel,names in channel_fields.items():
            req=channel in ('ar','aw','w');p='noc_req_o' if req else 'noc_resp_i';q='noc_resp_i' if req else 'noc_req_o'
            valid=c(before,p+'.'+channel+'_valid');ready=c(before,q+'.'+channel+'_ready')
            payload=tuple(c(before,p+'.'+channel+'.'+n) for n in names) if valid else None
            require(channel not in held or held[channel]==payload,'Unstable AXI held '+channel)
            if valid and not ready:held[channel]=payload
            else:held.pop(channel,None)
            if valid and ready:fired[channel]=payload;counts[channel]+=1
        for channel in ('ar','aw'):
            if channel not in fired:continue
            p=fired[channel];ident,addr,length,size,burst=p[:5]
            require(size<=3 and burst in (0,1) and (addr&4095)+(length+1)*(1<<size)<=4096,
                'Invalid scalar AXI burst')
            rec=dict(id=ident,beats=length+1,received=0)
            if channel=='ar':reads[ident].append(rec)
            else:
                require(p[10]==0 and not 0xd0000000<=addr<0xd0001000,'Unexpected ATOP/CTRL write')
                aws.append(rec)
        if 'r' in fired:
            ident,data,resp,last,_=fired['r'];require(reads[ident],'Orphan AXI R')
            rec=reads[ident][0];rec['received']+=1
            require(resp==0 and last==int(rec['received']==rec['beats']),'RRESP/RLAST differs')
            if last:reads[ident].popleft()
        if 'w' in fired:
            frame.append(fired['w'])
            if fired['w'][2]:frames.append(frame);frame=[]
        while aws and frames:
            rec,ws=aws.popleft(),frames.popleft()
            require(len(ws)==rec['beats'] and all(w[2]==int(i==len(ws)-1) for i,w in enumerate(ws)),
                'AXI W length/last differs')
            writes[rec['id']].append(rec)
        if 'b' in fired:
            ident,resp,_=fired['b'];require(writes[ident] and resp==0,'Orphan/error AXI B');writes[ident].popleft()
    require(active and not held and not aws and not frames and not frame and not any(reads.values()) and
        not any(writes.values()),'Incomplete AXI final drain')
    require(phase==2 and all({x['vpn'] for x in updates if x['phase']==p}==
        {pre.shared.vpn(p,e) for e in range(16)} for p in range(3)),'Missing actual instruction-page update')
    visits=[sorted({x['entry'] for x in updates if x['phase']==p}) for p in range(3)]
    require(all(v==list(range(16)) for v in visits),'Actual replacement did not visit all16 slots')
    require(lookups and len(plru)>1,'No actual lookup-hit/PLRU observation')
    return dict(status='PREEDGE_ITLB16_SLOT_THREE_PHASE_AND_AXI_DRAIN_PASS',updates=updates,
        hits=lookups,plru_changes=plru,entry_visits=visits,AXI_channels=dict(counts),
        pre_timebucket_sampling=True,no_post_startup_reset=True)


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==771 and len(single['tests'])==1 and
        single['tests'][0] not in before['tests'],'Exact771 plus unique singleton required')
    after=bitmap.combine(before,single);n=0
    for metric,scopes in before['metrics'].items():
        for scope,r in scopes.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
                int(r['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Independent OR differs')
            n+=1
    require(n==6162 and after['tests']==before['tests']+single['tests'],'Full6162 prefix/OR differs')
    return after


def collect(prepared,seal,output):
    require(not output.exists(),'Fresh offline qualification only')
    r=life.read_bound(prepared,seal);run=Path(r['output']);pp=Path(r['preflight'])
    q=life.read_bound(pp,r['preflight_seal']);pins=life.merge_pins(r['pins'],{str(prepared):seal})
    require(r['command']==runner.command(pp.parent/'input.elf',run) and r['timeout_s']==600 and
        r['schema']=='ITLB_EXEC_FROZEN600_AUTOQUALIFY_V1' and r['baseline_seal']==pre.BASE_SHA,
        'Exact prepared command differs')
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==dict(r,pins=pins),'Actual run manifest differs')
    terminal=life.read_bound(run/'simulation-status.json',life.digest(run/'simulation-status.json'))
    require(terminal.get('returncode')==0 and terminal['status']=='SIMULATION_EXITED_NOT_ADMITTED','No successful terminal')
    for p in run.rglob('*'):
        if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins);output.mkdir()
    try:
        markers((run/'console.log').read_text())
        ref=pre.build.parse_spike_commits(pp.parent/'spike.trace');pre.validate(pre.with_ecalls(ref,q['symbols']),q['symbols'])
        scalar=pre.architecture.spike_trace.compare_commit_prefix(pp.parent/'spike.trace',run/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        life.save(output/'scalar-comparison.json',scalar);exact_scalar(scalar,q['counts'])
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        traps=trap_contract(rows,q['symbols'])
        nontrap=[dict(row,order=str(i)) for i,row in enumerate(x for x in rows if not int(x['trap']))]
        commits=reference.native_reference(nontrap)
        terminal_index=next(i for i,c in enumerate(ref) if (0x80001000,1) in c.memory_accesses)
        ref=ref[:terminal_index+1]
        require(len(commits)==len(ref),'Complete native/reference prefix differs')
        for index,(a,b) in enumerate(zip(commits,ref)):
            require((a.pc,a.instruction,a.gpr_writes,a.memory_accesses)==
                (b.pc,b.instruction,b.gpr_writes,b.memory_accesses),'Complete compressed/uncompressed scalar differs at '+str(index))
        pre.validate(pre.with_ecalls(commits,q['symbols']),q['symbols'])
        with (run/'vector_trace.csv').open() as f:vectors=list(csv.DictReader(f))
        require(all(x['event']=='config' for x in vectors),'Unexpected vector side effect')
        life.save(output/'native-oracle.json',dict(checks=pre.CHECKS,failed=0,traps=traps,
            true_S_mode_instructions=144,full_code_bytes=65536,complete_scalar_including_compressed=True,
            scalar_memory_accesses=sum(bool(c.memory_accesses) for c in commits),vector_writes=0,
            CSR_restored=True,UVM_final_report_claimed=False))
        vpd=run/'itlb-exec.vpd';require(0<vpd.stat().st_size<=64*1024*1024,'Focused waveform64MB cap exceeded')
        require(life.digest(CONVERTER)==CONVERTER_SHA,'Converter drift')
        vcd=output/'itlb-exec.vcd'
        with (output/'convert.log').open('x') as log:
            subprocess.run([str(CONVERTER),'-splitpacked',str(vpd),str(vcd)],stdout=log,stderr=subprocess.STDOUT,
                timeout=120,check=True)
        life.save(output/'itlb-axi-observations.json',waveform(vcd))
        before,ledger,bpins=pre.baseline();pins=life.merge_pins(pins,bpins)
        with (output/'single-inputs.txt').open('x') as f:f.write(str(pre.DESIGN)+'\n'+str(run/'code.vdb')+'\n')
        single=bitmap.collect(output/'single-inputs.txt');after=full_union(before,single);delta=bitmap.delta(before,after)
        pred,predpins=pre.prediction();require(pred==q['prediction'],'Sealed771 targets changed')
        pins=life.merge_pins(pins,predpins);old,pins=pre.toggle_baseline(ledger,pins)
        files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique new Toggle data required')
        sample,sha=pre.native.rows(files[0],[pre.SCOPE]);require(pins[str(files[0])]==sha,'New Toggle data drift')
        merged=pre.native.union(old,sample);gains=pre.native.gains(old,merged)[pre.SCOPE]
        targets=[dict(native=t['native'],before_zero=t['fresh_positions'],
            hit_positions=sorted(set(t['fresh_positions'])&set(gains))) for t in pred['targets']]
        gain=dict(baseline=771,scope=pre.SCOPE,before=old[pre.SCOPE],single=sample[pre.SCOPE],after=merged[pre.SCOPE],
            new_serialized_positions=gains,new_positions=len(gains),targets=targets,
            target_new_positions=sum(len(t['hit_positions']) for t in targets),
            official_percentage=False,direction_order_calibrated=False)
        for p,h in single['input_hashes'].items():pins=life.merge_pins(pins,{p:h})
        for rel,h in single['design'].items():pins=life.merge_pins(pins,{str(pre.DESIGN/'snps/coverage/db'/rel):h})
        for name,value in [('single-bits.json',single),('diagnostic-combined-bits.json',after),
            ('raw-delta.json',delta),('toggle-gain.json',gain)]:life.save(output/name,value)
        life.check(pins);life.save(output/'evidence-pins.json',pins)
        life.save(output/'qualification.json',dict(status='ITLB_TRUE_SMODE_ARCHITECTURE_OBSERVATIONS_RAW771_QUALIFIED_NOT_ADMITTED',
            baseline=771,software_checks=pre.CHECKS,raw_delta=delta['metrics'],toggle_new_positions=len(gains),
            target_new_positions=gain['target_new_positions'],coverage_admitted=False,official_percentage=False,
            UVM_final_report_claimed=False,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
        print('QUALIFIED_NOT_ADMITTED',life.digest(output/'qualification.json'),gain['target_new_positions'],delta['metrics'],flush=True)
    except Exception as error:
        life.save(output/'failure.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            traceback=traceback.format_exc(),coverage_admitted=False,rerun=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    collect(a.prepared.absolute(),a.seal,a.output.absolute())
