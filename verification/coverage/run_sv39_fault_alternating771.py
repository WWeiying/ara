"""One600s old-image vector-fault run, then independent terminal qualification."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import re
import shlex
from types import FunctionType,SimpleNamespace
import preflight_sv39_fault_alternating771 as p
import run_pure_war_simulation as runner
import collect_opivx_vsbc_strict as common
import qualify_sv39_alias770_known_tail as memory
from ara_verify import vector_commit as vc
from ara_verify.contract import check_contract_log,parse_contract_summary
import qualify_sv39_masked_unit_fault_terminal as fault
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence_v2 as toggle
import rank_ordinary_rvv_toggle766 as cache_source

life,require=p.life,p.require
NAME='vsv39_fault_address_alternating'
PRE=life.OUT/'sv39-fault-alternating-preflight771-agent-20261007-01'
PRE_SHA='bcb2a12bbef27db0ffde0a066bf35651a75b6829156a0f20133eeb8eb556fcbf'
IMAGE_SHA='2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
BUDGET=600

def command(out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
      '+PRELOAD='+str(PRE/'input.elf'),'+TESTCASE='+NAME,'+COMMIT_TOHOST=80001000',
      '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
      '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]

def scoped_before():
    base=life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SHA)
    ledger=(p.BASE/'combined-inputs.txt').read_text().splitlines()
    cache=life.read_bound(cache_source.CACHE,cache_source.CACHE_SHA)
    prior=next(Path(n) for n in cache['input_pins'] if n.endswith('/inputs.txt'))
    require(life.digest(prior)==cache['input_pins'][str(prior)] and
      ledger[:742]==prior.read_text().splitlines() and len(ledger)==772,'Exact771 cached prefix')
    scopes=[s for s in cache['instances'] if 'i_vlsu' in s or 'i_dispatcher' in s or 'i_cva6_mmu' in s]
    require(scopes,'Fault producer scopes')
    result={s:{k:cache['instances'][s][k] for k in ('width','checksum','bits')} for s in scopes}
    pins={str(cache_source.CACHE):cache_source.CACHE_SHA,str(prior):life.digest(prior)}
    for db in ledger[742:]:
        paths=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(paths)==1,'Unique suffix Toggle')
        path=paths[0];sample,h=toggle.rows(path,scopes)
        require(h==base['input_pins'][str(path)],'Admitted suffix drift')
        pins[str(path)]=h;result=toggle.union(result,sample)
    return result,pins

def prepare(out):
    require(not out.exists() and out.parent==life.OUT,'Fresh independent run')
    pre=life.read_bound(PRE/'preflight.json',PRE_SHA);life.check(pre['input_pins'])
    require(pre['baseline_seal']==p.BASE_SHA and pre['counts']==p.validate(PRE/'spike.trace',pre['symbols']),
      'Strict preflight contract')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen66 image')
    pins=life.merge_pins(pre['input_pins'],image['image'])
    for module in (p,runner,common,memory,vc,fault,bitmap,toggle,cache_source):
        path=Path(module.__file__).resolve();pins=life.merge_pins(pins,{str(path):life.digest(path)})
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_sv39_fault_alternating771.py'),
      Path(__file__).with_name('test_run_sv39_fault_alternating771.py'),
      PRE/'preflight.json',life.PLAN):pins=life.merge_pins(pins,{str(path):life.digest(path)})
    book=life.read_bound(p.shared.SOURCE,p.shared.SOURCE_SHA)
    for rel in ('hardware/src/lane/operand_requester.sv','hardware/tb/ara_commit_monitor.sv',
      'verification/uvm/ara_acc_contract_monitor.sv'):
        path=life.ROOT/rel;pins=life.merge_pins(pins,{str(path):book[str(path)]})
    dispatch=memory.DISPATCH
    pins=life.merge_pins(pins,{str(dispatch):book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]})
    maintenance=memory.source_contract(dispatch.read_text())
    before,new=scoped_before();pins=life.merge_pins(pins,new)
    life.check(pins)
    return dict(case=NAME,command=command(out),output=str(out),timeout_s=BUDGET,pins=pins,
      elf_sha256=life.digest(PRE/'input.elf'),image_sha256=IMAGE_SHA,baseline=771,baseline_seal=p.BASE_SHA,
      authorization_source='EXPLICIT_USER_AUTHORIZATION_ONE600S_FROZEN_IMAGE_RUN',
      automatic_retry=False,coverage_admitted=False,admission_performed=False,
      scoped_toggle_before=before,maintenance_source_contract=maintenance,
      expected_vector_faults=8,expected_S_ecalls=4,
      note='RVV invalid-leaf fault; not scalar LSU-specific coverage identity')

def lifecycle(rows,vectors,words):
    pending={};starts={};rejected=[];live={};alloc=Counter();done=Counter();requests=responses=0
    for r in rows:
        event=r['event'];tid=int(r['trans_id']);seq=int(r['order']);cycle=int(r['cycle'])
        if event=='arch_start':
            require(seq not in starts and tid not in pending,'Unique architecture owner')
            starts[seq]=r;pending[tid]=[seq,False]
        elif event=='cvx_req':
            require(tid in pending and not pending[tid][1] and r['insn']==starts[pending[tid][0]]['insn'],'Request owner')
            pending[tid][1]=True;requests+=1
        elif event=='cvx_resp':
            require(tid in pending and pending[tid][1],'Response owner')
            owner=pending.pop(tid)[0];responses+=1
            if int(r['trap']):rejected.append(owner)
        elif event in ('uop_alloc','uop_done'):
            vid=int(r['port']);require(seq in starts and r['insn']==starts[seq]['insn'] and
              tid==int(starts[seq]['trans_id']),'Backend SID owner')
            if event=='uop_alloc':
                require(vid not in live,'Live VID collision');live[vid]=(seq,cycle);alloc[seq,vid,cycle]+=1
            else:
                require(vid in live and live[vid][0]==seq,'Completion owner');live.pop(vid);done[seq,vid,cycle]+=1
        else:require(event=='retire','Unknown event')
    require(not pending and not live and requests==responses==len(starts),'Complete request/backend drain')
    require(Counter((s,v) for s,v,c in alloc.elements())==Counter((s,v) for s,v,c in done.elements()),'Complete backend conservation')
    require(len(rejected)==8 and [int(starts[s]['insn'],16) for s in rejected]==words*4,'Exact rejected load/store owners')
    native_alloc=Counter((int(r['arch_seq']),int(r['vid']),int(r['cycle'])) for r in vectors if r['event']=='alloc')
    native_done=Counter((int(r['arch_seq']),int(r['vid']),int(r['cycle'])) for r in vectors if r['event']=='done')
    require(native_alloc==alloc and native_done==done,'Full commit/native lifecycle match')
    for r in vectors:
        if r['event']=='config':continue
        seq=int(r['arch_seq']);require(seq in starts and r['insn']==starts[seq]['insn'] and
          (int(r['nr_lanes']),int(r['vlen_bits']))==(4,1024),'Vector owner/geometry')
        if r['event']=='write' and seq in rejected and int(r['be'],16):
            require(int(r['source'])==3,'Fault accepted real VLDU data')
    return dict(requests=requests,responses=responses,rejected=rejected,backend_allocations=sum(alloc.values()))

def collect(out,manifest):
    qualified=out.with_name(out.name+'-qualified');require(not qualified.exists(),'Fresh qualification')
    qualified.mkdir();pins=dict(manifest['pins'])
    try:
        life.check(pins);state=json.loads((out/'simulation-status.json').read_bytes())
        require(state['returncode']==0 and state['status']=='SIMULATION_EXITED_NOT_ADMITTED','Terminal failed/timeout')
        pre=life.read_bound(PRE/'preflight.json',PRE_SHA);s=pre['symbols']
        log=(out/'run.vcs.log').read_text();fault.log_gate(log);fault.log_gate((out/'console.log').read_text())
        require(not check_contract_log(out/'run.vcs.log'),'Protocol errors')
        counts=[parse_contract_summary(x.strip()) for x in log.splitlines() if '[ARA_CONTRACT]' in x]
        require(len(counts)==1 and counts[0] is not None and counts[0]['exceptions']==8 and
          all(counts[0][k]==0 for k in ('protocol_errors','outstanding','req_stalled','resp_stalled')),'Complete fault protocol')
        rows=common.read_csv((out/'commit_trace.csv').read_bytes(),common.COMMIT_FIELDS)
        vectors=common.read_csv((out/'vector_trace.csv').read_bytes(),common.VECTOR_FIELDS)
        reference=p.build.parse_spike_commits(PRE/'spike.trace')
        entry=next(i for i,c in enumerate(reference) if c.pc==0x80000000)
        reference=reference[entry:]
        require(reference[-1].memory_accesses==((s['tohost'],1),),'Complete entry-tohost reference')
        faults=[c for c in reference if c.pc in (s['fault_load_pc'],s['fault_store_pc'])]
        require(len(faults)==8,'Exact eight reference faults')
        control=lifecycle(rows,vectors,[faults[0].instruction,faults[1].instruction])
        require(counts[0]['requests']==counts[0]['responses']==control['requests'],'Protocol trace conservation')
        scalar=common.spike_trace.compare_commit_prefix(PRE/'spike.trace',out/'commit_trace.csv',0x80000000,
          terminal_tohost_address=s['tohost'],rtl_exception_log=out/'trace_hart_0.log',rvfi_store_data_layout='unshifted')
        life.save(qualified/'scalar-comparison.json',scalar)
        require(scalar['status']=='TERMINAL_TOHOST_MATCH' and scalar['mismatch'] is None and
          scalar['skipped_unobservable_register_values']==0 and scalar['stopped_at_unobservable'] is None and
          scalar['matched_instructions']==len(reference)-8,'Full scalar/GPR reference match')
        aligned=scalar['aligned_vector_faults'];require(len(aligned)==8,'Exact aligned page faults')
        for i,f in enumerate(aligned):
            c=faults[i];require(f['pc']=='0x%016x'%c.pc and f['instruction']=='0x%08x'%c.instruction and
              f['matched_fault_csrs']=={'0x341':c.pc,'0x342':15 if i&1 else 13,'0x343':p.ADDRESSES[(i//2)&1]}
              and f['fault_handler_returned'] and not f['invalidated_fault_csrs'],'Every exact CSR/PC/tval/return')
        clean=[c for c in reference if c.pc not in (s['fault_load_pc'],s['fault_store_pc'])]
        complete_memory=memory.scalar_memory_exact(rows,clean)
        tracer=(out/'trace_hart_0.log').read_text()
        observed=Counter(int(x,16) for x in re.findall(r'^Exception @\s+\d+, PC: ([0-9a-fA-F]+),',tracer,re.M))
        require(observed==Counter({s['fault_load_pc']:4,s['fault_store_pc']:4,s['fault_s_ecall']:4}), 'Only12 expected DUT exceptions')
        # A first-format SLDU maintenance write may preserve the known full seed,
        # but a real load byte from a fault is forbidden. No global checker edits.
        lanes,bits,activities=vc._parse_vector_trace(out/'vector_trace.csv')
        require((lanes,bits)==(4,1024),'Native geometry')
        allowed=set()
        signature=lambda a:json.dumps(asdict(a),sort_keys=True)
        for seq in control['rejected']:
            a=activities[seq];accepted=[w for w in a.writes if w.be]
            require(a.allocations==a.completions,'Fault full completion')
            if accepted:
                require(all(w.source==3 and w.be==w.known_be==255 for w in accepted),'Only known SLDU maintenance')
                actual=vc._architectural_bytes(accepted,4,1024)
                reg=16 if a.instruction==faults[0].instruction else 8
                require(sum(bin(w.be).count('1') for w in accepted)==128 and
                  set(actual)=={(reg,b) for b in range(128)} and all(v[0]==0x5a for v in actual.values()),'Entire known prestate unchanged')
                allowed.add(signature(a))
        def permitted(a,c,f):
            return (signature(a) in allowed and c.pc==s['fault_load_pc'] and
              f in aligned and not c.vector_writes and not c.memory_accesses and
              c.vector_sew==64 and c.vector_vl==1 and c.vector_vstart==0 and
              f['matched_fault_csrs'].get('0x342')==13)
        private=FunctionType(vc.compare_vector_commits.__code__,dict(vc.compare_vector_commits.__globals__,
          _known_identity_load_fault=permitted),vc.compare_vector_commits.__name__,vc.compare_vector_commits.__defaults__)
        vector=private(PRE/'spike.trace',out/'commit_trace.csv',out/'vector_trace.csv',0x80000000,aligned_vector_faults=aligned)
        life.save(qualified/'vector-comparison.json',vector)
        require(vector['status']=='PASS' and vector['compared_instructions']==5 and
          vector['trapped_requests']==control['rejected'] and not vector['first_mismatch'] and
          not vector['incomplete_requests'] and not vector['unretired_requests'] and
          all(vector[k]==0 for k in ('skipped_unknown_bytes','non_bit_exact_instructions','unobservable_instructions')),'Full native vector comparison')
        gain=raw_gain(out,qualified,manifest)
        for directory in (out,qualified):
            for f in directory.rglob('*'):
                if f.is_file():pins[str(f)]=life.digest(f)
        life.check(pins)
        result=dict(status='FULL_SCALAR_VECTOR_EXACT_FAULT_MEMORY_CSR_GUARDS_PASS_NOT_ADMITTED',
          run=str(out),baseline=771,baseline_seal=p.BASE_SHA,scalar=scalar,lifecycle=control,
          scalar_memory=complete_memory,oracle=pre['counts'],raw_gain=gain,input_pins=pins,coverage_admitted=False)
        life.save(qualified/'qualification.json',result)
        print('QUALIFIED '+life.digest(qualified/'qualification.json'),flush=True)
    except Exception as e:
        life.save(qualified/'failure.json',dict(status='FAIL_OR_HOLD_NOT_ADMITTED',reason=type(e).__name__+': '+str(e),coverage_admitted=False))
        raise

def raw_gain(out,qualified,manifest):
    before_path=p.BASE/'combined-bits.json';base=life.read_bound(p.BASE/'admission-manifest.json',p.BASE_SHA)
    before=life.read_bound(before_path,base['output_pins'][str(before_path)])
    folders=list((out/'code.vdb/snps/coverage/db/testdata').iterdir())
    require(len(folders)==1 and folders[0].name==NAME,'One exact native test')
    folder=folders[0]
    for name in ('siminfo.xml','vcmArguments.xml',*[m+'.verilog.data.xml' for m in (*bitmap.METRICS,'tgl')]):
        toggle.xml(folder/name)
    records=toggle.xml(folder/'siminfo.xml').findall('srctest')
    require(len(records)==1 and shlex.split(records[0].get('cmdline',''))==manifest['command'] and
      records[0].get('workdir')==str(out) and
      int(records[0].get('finishtime','0'))>int(records[0].get('starttime','0'))>0,'Actual native command/workdir/terminal')
    inputs=qualified/'single-inputs.txt'
    with inputs.open('x') as f:f.write(before['tests'][0]+'\n'+str(out/'code.vdb')+'\n')
    single=bitmap.collect(inputs);delta=bitmap.delta(before,bitmap.combine(before,single))
    path=list((out/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(path)==1,'Unique terminal Toggle');sample,h=toggle.rows(path[0],list(manifest['scoped_toggle_before']))
    gains=toggle.gains(manifest['scoped_toggle_before'],toggle.union(manifest['scoped_toggle_before'],sample))
    life.save(qualified/'raw-delta.json',delta);life.save(qualified/'scoped-toggle-gain.json',gains)
    return dict(four_metrics=delta['metrics'],scoped_toggle=gains,official_percentage=False)

def main():
    a=argparse.ArgumentParser();a.add_argument('mode',choices=('prepare','run','collect'))
    a.add_argument('--output',type=Path,required=True);a.add_argument('--seal');args=a.parse_args();out=args.output.resolve()
    record=out.with_name(out.name+'.prepared.json')
    if args.mode=='prepare':
        life.save(record,prepare(out));print('PREPARED '+life.digest(record),flush=True)
    else:
        require(args.seal,'Prepared seal');manifest=life.read_bound(record,args.seal);life.check(manifest['pins'])
        if args.mode=='run':
            require(manifest==prepare(out),'Prepared exact contract')
            private=FunctionType(runner.run.__code__,dict(runner.run.__globals__,BUDGET=BUDGET,PRE=PRE,
              ELF_SEAL=manifest['elf_sha256'],IMAGE_SEAL=IMAGE_SHA,preflight=SimpleNamespace(NAME=NAME),command=command),
              runner.run.__name__,runner.run.__defaults__)
            try:private(out,manifest)
            finally:
                if (out/'simulation-status.json').exists():collect(out,manifest)
        else:collect(out,manifest)

if __name__=='__main__':main()
