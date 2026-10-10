"""Frozen full oracle with exact packed189 projection and six readonly vectorCSR transactions."""
from pathlib import Path
import argparse
import csv
import subprocess
import traceback
import re
from types import FunctionType, SimpleNamespace
import build_itlb_asid_exec_linear as linear
import collect_itlb_asid_exec as old

life,require=old.life,old.require
bitmap,reference=old.bitmap,old.reference
CONVERTER,CONVERTER_SHA=old.CONVERTER,old.CONVERTER_SHA
BASE=life.OUT/'scalar-fpu-backpressure-offline-admitted-772-agent-20261007-01'
BASE_SHA='28cc362f64c2c48e8a3b8a1dbf568903434464cc4dcea7e2dfad2aae282ca332'
PREFLIGHT_SHA='e1ac19e6064d834f4d8b2501d1f3ced7eefc7721571e43c5f86e58691ebe6545'


def baseline():
    manifest=BASE/'admission-manifest.json'
    record=life.read_bound(manifest,BASE_SHA)
    require(record['coverage_admitted'] is True and
        record['schema']=='SCALAR_FPU_BACKPRESSURE_HISTORICAL772_ADMISSION_V1','Formal772 admission required')
    pins=life.merge_pins(record['input_pins'],record['output_pins'])
    pins=life.merge_pins(pins,{str(manifest):BASE_SHA})
    bits=life.read_bound(BASE/'combined-bits.json',pins[str(BASE/'combined-bits.json')])
    path=BASE/'combined-inputs.txt'
    require(life.digest(path)==pins[str(path)],'772 ledger drift')
    ledger=path.read_text().splitlines()
    require(len(bits['tests'])==len(set(bits['tests']))==772 and
        ledger[1:]==bits['tests'] and Path(ledger[0]).is_absolute(),'Exact772 prefix required')
    db=Path(ledger[0])/'snps/coverage/db'
    require(all(pins.get(str(db/rel))==sha for rel,sha in bits['design'].items()),
        'Compiled ledger design must have all exact historical pins')
    return bits,ledger,pins


def full_union(before,single):
    require(len(before['tests'])==len(set(before['tests']))==772 and len(single['tests'])==1 and
        single['tests'][0] not in before['tests'],'Exact772 plus unique singleton required')
    after=bitmap.combine(before,single);n=0
    for metric,scopes in before['metrics'].items():
        for scope,r in scopes.items():
            require(int(after['metrics'][metric][scope]['bits'],16)==
                int(r['bits'],16)|int(single['metrics'][metric][scope]['bits'],16),'Independent OR differs')
            n+=1
    require(n==6162 and after['tests']==before['tests']+single['tests'],'Full6162 prefix/OR differs')
    return after
FIELDS={'valid':(188,188),'is_page':(187,186),'vpn':(185,159),'asid':(158,143),
        'vmid':(142,129),'stage':(128,128),'content':(127,64),'g_content':(63,0)}


def packed_field(bits,name):
    require(len(bits)==189 and set(bits)<=set('01xz'),'Exact native packed189 encoding required')
    require(name in FIELDS,'Foreign update member')
    hi,lo=FIELDS[name]
    return bits[188-hi:189-lo]


def source_layout():
    # All widths and struct ordering are fixed by the historical build, not the
    # current waveform name or a guessed splitpacked presentation.
    proof,pins=linear.old.source_contract()
    def clean(text):return re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S))
    mmu=clean((linear.ROOT/'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv').read_text())
    cfg=clean((linear.ROOT/'hardware/deps/cva6/core/include/build_config_pkg.sv').read_text())
    struct="""localparamtypetlb_update_cva6_t=structpacked{logicvalid;
        logic[CVA6Cfg.PtLevels-2:0][HYP_EXT:0]is_page;logic[CVA6Cfg.VpnLen-1:0]vpn;
        logic[CVA6Cfg.ASID_WIDTH-1:0]asid;logic[CVA6Cfg.VMID_WIDTH-1:0]vmid;
        logic[HYP_EXT*2:0]v_st_enbl;pte_cva6_tcontent;pte_cva6_tg_content;};"""
    require(re.sub(r'\s+','',struct) in mmu,'Exact packed update field ordering differs')
    for token in ('cfg.ASID_WIDTH=(CVA6Cfg.XLEN==64)?16:1;',
        'cfg.VMID_WIDTH=(CVA6Cfg.XLEN==64)?14:1;', 'cfg.PPNW=(CVA6Cfg.XLEN==32)?22:44;',
        'intunsignedVpnLen=(CVA6Cfg.XLEN==64)?(CVA6Cfg.RVH?29:27):20;'):
        require(token in cfg,'Exact configured width differs: '+token)
    return dict(native_packed_width=189,fields=FIELDS,derived_not_native_child_signals=True,
                RVH=0,source_pins=pins)


def projected_vcd(path):
    parser=FunctionType(old.wave.vcd.__code__,dict(old.wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    iterator=iter(parser(path));_,decl=next(iterator)
    packed=old.pre.SCOPE+'.update_i'
    require(decl.get(packed,{}).get('width')==189,'Missing/foreign packed update189')
    decl=dict(decl);projection={}
    for member in ('valid','asid','vpn'):
        name=packed+'.'+member;code='SOURCE_DECODED_ITLB_'+member;hi,lo=FIELDS[member]
        require(name not in decl and not any(d['code']==code for d in decl.values()),'Ambiguous packed/child update representation')
        decl[name]=dict(width=hi-lo+1,code=code,type='source-derived-packed-member')
        projection[member]=code
    yield 'declarations',decl
    for time,before,after in iterator:
        derived=[]
        for state in (before,after):
            state=dict(state);bits=state.get(decl[packed]['code'],'x'*189)
            for member,code in projection.items():state[code]=packed_field(bits,member)
            derived.append(state)
        yield time,derived[0],derived[1]


def waveform(path):
    layout=source_layout()
    def factory(code,namespace):
        require(code is old.wave.vcd.__code__,'Unexpected VCD reader boundary')
        return projected_vcd
    implementation=FunctionType(old.waveform.__code__,dict(old.waveform.__globals__,FunctionType=factory))
    result=implementation(path)
    return dict(result,update_encoding=layout)


def csr_lifecycle(rows):
    retired=[r for r in rows if r['event']=='retire']
    def readonly(word):return word&0xff07f==0x2073 and word>>20 in (8,15)
    csr=[r for r in retired if readonly(int(r['insn'],16))]
    require(len(csr)==6 and [int(r['insn'],16)>>20 for r in csr]==[8,15]*3,
        'Exact six architectural vstart/vcsr reads required')
    starts=[];pending={};requests=responses=0
    for row in rows:
        event=row['event']
        if event=='retire':continue
        require(event in ('arch_start','cvx_req','cvx_resp'),'Foreign backend activity')
        require(int(row['trap'])==0 and int(row['mem_rmask'],16)==int(row['mem_wmask'],16)==0,
                'Unexpected CSR exception/memory effect')
        tid=int(row['trans_id']);time=int(row['cycle'])
        if event=='arch_start':
            word=int(row['insn'],16)
            require(readonly(word) and tid not in pending and int(row['order'])==len(starts),
                    'Duplicate/live/foreign CSR start')
            record=dict(arch_seq=len(starts),trans_id=tid,word=word,start=time)
            starts.append(record);pending[tid]=record
        elif event=='cvx_req':
            require(tid in pending and 'request' not in pending[tid] and
                int(row['insn'],16)==pending[tid]['word'] and time>=pending[tid]['start'],
                'Missing/replayed/changed CSR request')
            pending[tid]['request']=time;requests+=1
        else:
            require(tid in pending and 'request' in pending[tid] and time>=pending[tid]['request'],
                    'Orphan/duplicate/early CSR response')
            pending.pop(tid)['response']=time;responses+=1
    require(len(starts)==requests==responses==6 and not pending,'Incomplete six-CSR conservation')
    for i,(start,retire) in enumerate(zip(starts,csr)):
        require(start['word']==int(retire['insn'],16) and start['response']<=int(retire['cycle']) and
            int(retire['rd_wdata'],16)==0 and not int(retire['trap']), 'CSR retire identity/value/window differs')
        if i+1<len(starts):require(int(retire['cycle'])<=starts[i+1]['start'],'CSR completion crossed consumer')
        start.update(retire_cycle=int(retire['cycle']),retire_pc=retire['pc'])
    return dict(status='SIX_READONLY_CSR_REQUEST_RESPONSE_RETIRE_EXACT',requests=6,responses=6,
        exceptions=0,records=starts,arch_start_PC_not_used_as_architectural_PC=True,
        actual_PC_opcode_and_values_further_checked_by_full_Spike_oracle=True,vector_modifications=0)


def markers(text):
    lines=text.splitlines()
    require(lines.count('Core Test *** SUCCESS ***')==1,'Exact software terminal missing')
    require(re.findall(r'\[ARA_CONTRACT\] requests=(\d+) responses=(\d+) exceptions=(\d+).*?protocol_errors=(\d+) outstanding=(\d+)',text)
        == [('6','6','0','0','0')],'Exact six readonly CSR contract differs')
    require(not any(re.match(r'^\s*(?:UVM_ERROR|UVM_FATAL|Error-|Fatal:|Exception @)',l) for l in lines),
        'Actual error/exception marker')
    # Keep the original exact object/ready checks, with only the independently
    # accounted CSR final-summary values normalized for its zero-request gate.
    normalized=re.sub(r'(\[ARA_CONTRACT\] requests=)6( responses=)6',r'\g<1>0\g<2>0',text)
    old.markers(normalized)


pre=SimpleNamespace(**linear.old.__dict__)
pre.validate=linear.validate
pre.baseline=baseline
pre.BASE,pre.BASE_SHA=BASE,BASE_SHA
exact_scalar=old.exact_scalar


def collect(prepared,seal,output):
    import run_itlb_asid_exec_linear as runner
    require(not output.exists(),'Fresh offline qualification only')
    r=life.read_bound(prepared,seal);run=Path(r['output']);pp=Path(r['preflight'])
    q=life.read_bound(pp,r['preflight_seal']);pins=life.merge_pins(r['pins'],{str(prepared):seal})
    require(r['command']==runner.command(pp.parent/'input.elf',run) and r['timeout_s']==600 and
        r['schema']=='ITLB_LINEAR_FROZEN600_AUTOQUALIFY_V1' and r['driver_variant']=='ITLB_LINEAR_SOURCE_PACKED189_CSR6' and r['preflight_seal']==PREFLIGHT_SHA and r['baseline_seal']==pre.BASE_SHA,
        'Exact prepared command differs')
    runner.validate_record(r)
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
        life.save(output/'csr-lifecycle.json',csr_lifecycle(rows))
        rows=[r for r in rows if r['event']=='retire']
        traps=old.trap_contract(rows,q['symbols'])
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
        with (output/'single-inputs.txt').open('x') as f:f.write(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
        single=bitmap.collect(output/'single-inputs.txt');after=full_union(before,single);delta=bitmap.delta(before,after)
        pred,predpins=pre.prediction();require(pred==q['prediction'],'Sealed771 targets changed')
        pins=life.merge_pins(pins,predpins);prior_toggle,pins=pre.toggle_baseline(ledger,pins)
        files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique new Toggle data required')
        sample,sha=pre.native.rows(files[0],[pre.SCOPE]);require(pins[str(files[0])]==sha,'New Toggle data drift')
        merged=pre.native.union(prior_toggle,sample);gains=pre.native.gains(prior_toggle,merged)[pre.SCOPE]
        oldbits=format(int(prior_toggle[pre.SCOPE]['bits'],16),'0%db'%prior_toggle[pre.SCOPE]['width'])
        targets=[dict(native=t['native'],before_zero=[i for i in t['fresh_positions'] if oldbits[i]=='0'],
            hit_positions=sorted(set(t['fresh_positions'])&set(gains))) for t in pred['targets']]
        gain=dict(baseline=772,scope=pre.SCOPE,before=prior_toggle[pre.SCOPE],single=sample[pre.SCOPE],after=merged[pre.SCOPE],
            new_serialized_positions=gains,new_positions=len(gains),targets=targets,
            target_new_positions=sum(len(t['hit_positions']) for t in targets),
            official_percentage=False,direction_order_calibrated=False)
        for p,h in single['input_hashes'].items():pins=life.merge_pins(pins,{p:h})
        for rel,h in single['design'].items():pins=life.merge_pins(pins,{str(Path(ledger[0])/'snps/coverage/db'/rel):h})
        for name,value in [('single-bits.json',single),('diagnostic-combined-bits.json',after),
            ('raw-delta.json',delta),('toggle-gain.json',gain)]:life.save(output/name,value)
        life.check(pins);life.save(output/'evidence-pins.json',pins)
        life.save(output/'qualification.json',dict(status='ITLB_TRUE_SMODE_ARCHITECTURE_OBSERVATIONS_RAW772_QUALIFIED_NOT_ADMITTED',
            baseline=772,software_checks=pre.CHECKS,raw_delta=delta['metrics'],toggle_new_positions=len(gains),
            target_new_positions=gain['target_new_positions'],coverage_admitted=False,official_percentage=False,
            UVM_final_report_claimed=False,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in output.iterdir() if p.is_file()}))
        print('QUALIFIED_NOT_ADMITTED',life.digest(output/'qualification.json'),gain['target_new_positions'],delta['metrics'],flush=True)
    except Exception as error:
        life.save(output/'failure.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            traceback=traceback.format_exc(),coverage_admitted=False,rerun=False));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared',type=Path,required=True)
    parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    collect(args.prepared.absolute(),args.seal,args.output.absolute())
