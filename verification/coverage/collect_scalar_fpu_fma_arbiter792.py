"""Full architecture plus FMA-owned capture/stable-STALL/output, no admission."""
import argparse
from collections import deque
import csv
import json
import math
from pathlib import Path
import re
import subprocess
from types import FunctionType

import run_scalar_fpu_fma_arbiter792 as runner
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap
from diagnose_scalar_fpu_backpressure import guard_loads

life,require,oracle=runner.life,runner.require,runner.oracle
SCOPE=oracle.prior.SCOPE
GEN=SCOPE+'.fpu_gen'
BULK=GEN+'.i_fpnew_bulk'
OPS=('FMADD','DIV','CLASSIFY')


def expectations(pre):
    result=[]
    for b,c in enumerate(oracle.C_VALUES):
        pc=pre['symbols']['arb_batch%d'%b]
        result.append(dict(op='DIV',pc=pc,result=0x3ff0000000000000,
                           abc=[0x3ffaaaaaaaab5555,0x3ffaaaaaaaab5555,None]))
        for motif in range(4):
            for j in range(6):
                result.append(dict(op='CLASSIFY' if j==3 else 'FMADD',pc=pc+4*(1+6*motif+j),
                    result=(64 if b==0 else 2) if j==3 else c,
                    abc=[c,None,None] if j==3 else [0,0x3ff0000000000000,c]))
    return result


def paths(proof):
    d={SCOPE+'.'+n:w for n,w in dict(state_q=1,flush_i=1,fpu_valid_i=1,fpu_ready_o=1,
        fu_data_i=proof['fu_layout']['width'],fpu_trans_id_o=3,result_o=64,fpu_valid_o=1,
        fpu_exception_o=proof['exception_layout']['width']).items()}
    d.update({GEN+'.'+n:w for n,w in dict(fpu_in_ready=1,fpu_in_valid=1,fpu_out_valid=1,
        fpu_out_ready=1,hold_inputs=1,use_hold=1,operand_a_d=64,operand_b_d=64,operand_c_d=64,
        operand_a_q=64,operand_b_q=64,operand_c_q=64,fpu_op_d=proof['op_width'],
        fpu_op_q=proof['op_width'],fpu_tag_d=3,fpu_tag_q=3).items()})
    d.update({BULK+'.'+n:proof['group_width'] for n in ('opgrp_in_ready','opgrp_out_valid','opgrp_out_ready')})
    d.update({BULK+'.gen_operation_groups[0].i_opgroup_block.'+n:proof['format_width']
              for n in ('fmt_in_ready','fmt_out_valid','fmt_out_ready')})
    d.update({'ara_tb.clk':1,'ara_tb.rst_n':1})
    return d


def driven_exception(state,decl,proof):
    path=SCOPE+'.fpu_exception_o'
    width=proof['exception_layout']['width']
    require(decl[path]['width']==width==203,'Exact exception parent width')
    bits=state.get(decl[path]['code'],'x')
    require(0<len(bits)<=width and set(bits)<=set('01xz'),'Exception packed encoding')
    bits=bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')
    result={}
    for name in ('cause','valid','tval'):
        left,right=proof['exception_layout']['fields'][name]
        field=bits[width-1-left:width-right]
        require(set(field)<=set('01'),'Unknown driven FPU exception '+name)
        result[name]=int(field,2)
        require(result[name]==0,'Nonzero driven FPU exception '+name)
    return result


def audit_edges(decl,edges,wants,proof):
    require(all(decl.get(n,{}).get('width')==w and decl[n].get('type') in ('wire','reg')
                for n,w in paths(proof).items()),'Exact typed probe declarations')
    def read(state,path):
        bits=state.get(decl[path]['code'],'x')
        require(0<len(bits)<=decl[path]['width'] and set(bits)<=set('01'),'Unknown active probe '+path)
        return int(bits,2)
    def root(s,n):return read(s,SCOPE+'.'+n)
    def gen(s,n):return read(s,GEN+'.'+n)
    def fields(value,layout):return {n:(value>>r)&((1<<(l-r+1))-1) for n,(l,r) in layout['fields'].items()}
    live={};pending=None;issued=0;completed=[];witnesses=[];history=deque(maxlen=8);idle_flush=[];stalls=0
    for time,before,after in edges:
        state,valid=root(before,'state_q'),root(before,'fpu_valid_i')
        if root(before,'flush_i'):
            require(not live and pending is None and state==0 and valid==0 and
                    gen(before,'hold_inputs')==gen(before,'use_hold')==0,'Flush with FPU owner')
            idle_flush.append(time);continue
        ogv=read(before,BULK+'.opgrp_out_valid');ogr=read(before,BULK+'.opgrp_out_ready')
        require(root(before,'fpu_valid_o')==gen(before,'fpu_out_valid')==int(bool(ogv)),
                'Native group/top output valid consistency')
        if ogv:
            require(bin(ogv&ogr).count('1')==1 and gen(before,'fpu_out_ready')==1,
                    'Exactly one requesting group granted')
        if ogv&1 and ogv&6 and not ogr&1:
            history.append(dict(time=time,valid=ogv,ready=ogr))
        if pending is not None:
            require(state==1 and gen(before,'use_hold')==1 and gen(before,'hold_inputs')==0,
                    'Missing stable owned STALL')
            require([gen(before,'operand_'+n+'_q') for n in 'abc']==pending['captured_abc'] and
                    gen(before,'fpu_op_q')==pending['native_op'] and gen(before,'fpu_tag_q')==pending['tid'],
                    'Held A/B/C/op/tag changed')
            stalls+=1
            require(gen(before,'fpu_in_valid')==1,'Held input must remain valid')
            if gen(before,'fpu_in_ready'):
                require(root(before,'fpu_ready_o')==1 and root(after,'state_q')==0,'Held acceptance/READY')
                live[pending['tid']]['accepted']=True
                w=dict(pending,release_time=time,competition=list(history))
                if pending['op']=='FMADD':
                    require(bool(w['competition']),'FMA hold without measured group competition')
                    witnesses.append(w)
                pending=None
        else:
            require(state==0,'Unowned STALL')
            if valid:
                require(issued<len(wants),'Extra FPU request')
                want=wants[issued];issued+=1
                op=gen(before,'fpu_op_d');tid=gen(before,'fpu_tag_d')
                abc=[gen(before,'operand_'+n+'_d') for n in 'abc']
                fu=fields(root(before,'fu_data_i'),proof['fu_layout'])
                require(tid==fu['trans_id'] and tid not in live,'TID reuse before completion')
                require(op==proof['fpnew_ops'][want['op']] and
                    all(e is None or e==g for e,g in zip(want['abc'],abc)),'Independent requested op/operands')
                native_name=dict(FMADD='FMADD',DIV='FDIV',CLASSIFY='FCLASS')[want['op']]
                require(fu['operation']==proof['ariane_ops'][native_name],'Native architectural operation owner')
                if want['op']=='FMADD':
                    require([fu[n] for n in ('operand_a','operand_b','imm')]==abc,'Packed FMA ABC producer')
                accepted=bool(gen(before,'fpu_in_ready'))
                require(gen(before,'fpu_in_valid')==1 and root(before,'fpu_ready_o')==int(accepted),
                        'Input acceptance controls')
                owner=dict(want,tid=tid,native_op=op,accepted=accepted,capture_time=time,captured_abc=abc)
                live[tid]=owner
                if not accepted:
                    require(gen(before,'hold_inputs')==1 and root(after,'state_q')==1,'Missing capture transition')
                    require([gen(after,'operand_'+n+'_q') for n in 'abc']==abc and
                        gen(after,'fpu_op_q')==op and gen(after,'fpu_tag_q')==tid,'Exact next-edge captured ABC/op/tag')
                    pending=owner
                else:require(gen(before,'hold_inputs')==0,'Spurious capture')
        if root(before,'fpu_valid_o'):
            tid=root(before,'fpu_trans_id_o')
            require(tid in live and live[tid]['accepted'],'Unowned/unaccepted FPU output')
            want=live.pop(tid)
            require(root(before,'result_o')==want['result'] and gen(before,'fpu_out_ready')==1,
                    'Independent native output result/ready')
            driven_exception(before,decl,proof)
            completed.append(dict(pc=want['pc'],op=want['op'],tid=tid,time=time,result=want['result']))
    require(issued==len(wants)==len(completed) and not live and pending is None,'Complete FPU owner/output lifecycle')
    return dict(FMA_hold_observed=bool(witnesses),FMA_hold_count=len(witnesses),witnesses=witnesses,
        issued=issued,completed=completed,stall_cycles=stalls,idle_ownerless_flush_times=idle_flush,
        PC_binding='source reference request order plus op/operands; complete retire PCs separately exact',
        exception_observed=['cause','valid','tval'],
        exception_unobserved={n:'UNOBSERVED' for n in ('tval2','tinst','gva')},no_retry=True)


def wave_audit(path,pre,proof):
    prior=oracle.prior
    parser=FunctionType(prior.wave.vcd.__code__,dict(prior.wave.vcd.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    stream=iter(parser(path));tag,decl=next(stream);require(tag=='declarations','VCD header')
    def edges():
        begun=False
        for time,before,after in stream:
            if before.get(decl['ara_tb.clk']['code'])=='0' and after.get(decl['ara_tb.clk']['code'])=='1':
                reset=before.get(decl['ara_tb.rst_n']['code'],'x')
                require(reset in ('0','1'),'Known reset on sampled edge')
                if reset=='0':
                    require(not begun,'Unexpected post-start reset');continue
                begun=True
                yield time,before,after
    return audit_edges(decl,edges(),expectations(pre),proof)


def stdout_gate(text):
    lines=text.splitlines()
    require(lines.count('Core Test *** SUCCESS ***')==lines.count('FMA_ARB_PROBE_READY')==1,'Single actual SUCCESS/probe ready')
    require(not any(x.startswith('FMA_ARB_PROBE_ERROR') or re.match(r'^(?:Error-|UCLI_ERROR)',x) or
        re.search(r'\b(?:UVM_ERROR|UVM_FATAL)\b(?!\s*:\s*0\s*$)',x) for x in lines),'Actual log error')
    contracts=[x for x in lines if x.startswith('[ARA_CONTRACT] ')]
    fields='requests responses exceptions mmu_request_cycles protocol_errors outstanding req_stalled resp_stalled'.split()
    require(len(contracts)==1,'Unique contract')
    match=re.fullmatch(r'\[ARA_CONTRACT\] '+' '.join(n+r'=(\d+)' for n in fields),contracts[0])
    require(match is not None and all(v=='0' for v in match.groups()),'Complete exact zero contract')
    return dict(zip(fields,map(int,match.groups())))


def terminal_gate(run,record):
    s=json.loads((run/'simulation-status.json').read_bytes());identity=json.loads((run/'live-identity.json').read_bytes())
    started=json.loads((run/'started.json').read_bytes())
    runner.exact_fields(s,dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,
        case=runner.NAME,coverage_admitted=False,admission_performed=False,terminal_oracle_verified=False),'Successful terminal')
    require(type(s['wall_seconds']) in (int,float) and math.isfinite(s['wall_seconds']) and
            0<=s['wall_seconds']<=runner.BUDGET,'Bounded terminal')
    require(type(s['pid']) is int and s['pid']>0 and not Path('/proc/%d'%s['pid']).exists(),'Terminal PID')
    runner.exact_fields(started,dict(pid=s['pid'],process_group=s['pid'],budget_s=runner.BUDGET,
        input_elf=str(runner.ELF),elf_sha256=record['elf_sha256'],image=str(life.IMAGE),
        image_sha256=runner.IMAGE_SHA,command=record['command'],foreground_lifetime=True,
        coverage_admitted=False),'Exact startup receipt')
    runner.exact_fields(identity,dict(pid=s['pid'],executable=str(life.IMAGE.resolve()),cwd=str(run),
        command=record['command'],process_group=s['pid'],service=record['service'],verified=True),'Actual live identity receipt')
    require(any(x.rsplit('/',1)[-1]==record['service'] for x in identity['cgroup'].splitlines()),'Exact service cgroup')
    require(json.loads((run/'manifest.json').read_bytes())==record,'Executed manifest')


def collect(run,out,seal):
    require(not out.exists(),'Fresh qualification')
    sidecar=run.with_name(run.name+'.prepared.json');record=life.read_bound(sidecar,seal)
    runner.verify(run,record,terminal=True);terminal_gate(run,record)
    pre=life.read_bound(runner.PRE/'preflight.json',runner.PRE_SHA)
    contract=stdout_gate((run/'console.log').read_text());out.mkdir()
    try:
        arch=oracle.prior.old.architecture
        scalar=arch.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',run/'commit_trace.csv',
            0x80000000,terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        arch.scalar_exact(scalar,pre['counts']);life.save(out/'scalar-comparison.json',scalar)
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        require(len(rows)==613 and all(r['event']=='retire' and int(r['trap'])==0 for r in rows) and
                [int(r['order']) for r in rows]==list(range(613)),'Exact complete retire-only prefix')
        memory={}
        for row in rows:
            store=arch.scalar_store(row)
            if store:
                address,data=store;memory.update({address+i:b for i,b in enumerate(data)})
        def word(a,size=8):return sum(memory[a+i]<<(8*i) for i in range(size))
        sym=pre['symbols']
        for b,c in enumerate(oracle.C_VALUES):
            require([word(sym['arb_observed']+168*b+8*i) for i in range(21)]==[c]*20+[0x3ff0000000000000], 'All native numeric results')
            require([word(sym['arb_class']+32*b+8*i) for i in range(4)]==[64 if b==0 else 2]*4,'All native classes')
        csr=[word(sym['arb_csr']+8*i) for i in range(5)]
        require(csr==[csr[0],0,0,0,csr[0]],'Full native FCSR/flags/restore')
        require([word(sym['g75_result'],4),word(sym['g75_result']+4,4),word(sym['num_failed'],4)]==[56,0,0],'Full56 signature')
        guards=oracle.build._elf_symbol(runner.ELF,oracle.build.LLVM/'llvm-readelf','arb_guards')
        guard_loads(rows,guards)
        with (run/'vector_trace.csv').open() as f:
            require(all(r['event']=='config' for r in csv.DictReader(f)),'Exact zero vector activity')
        vpd=run/'scalar-fpu-fma-arbiter792.vpd'
        require(0<vpd.stat().st_size<=64*1024*1024,'Bounded focused VPD')
        with (out/'converter.log').open('x') as f:
            subprocess.run([str(runner.lifecycle.converter.CONVERTER),str(vpd),str(out/'probe.vcd')],
                stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        audit=wave_audit(out/'probe.vcd',pre,record['source_contract']);life.save(out/'FMA-owner-audit.json',audit)
        ledger=out/'single-inputs.txt'
        with ledger.open('x') as f:f.write(str(life.IMAGE)+'.vdb\n'+str(run/'code.vdb')+'\n')
        single=bitmap.collect(ledger)
        base=life.read_bound(oracle.BASE/'admission-manifest.json',oracle.BASE_SHA)
        before=life.read_bound(oracle.BASE/'combined-bits.json',base['output_pins'][str(oracle.BASE/'combined-bits.json')])
        combined=bitmap.combine(before,single);delta=bitmap.delta(before,combined)
        life.save(out/'raw-four-metric-delta.json',delta)
        before_t=life.read_bound(oracle.BASE/'combined-toggle-bits.json',base['output_pins'][str(oracle.BASE/'combined-toggle-bits.json')])
        files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files)==1,'Unique candidate Toggle data')
        sample,sample_sha=toggle.rows(files[0],list(before_t));after=toggle.union(before_t,sample)
        gain={}
        for scope,old in before_t.items():
            new=after[scope];changed=int(new['bits'],16)&~int(old['bits'],16);positions=[]
            while changed:
                bit=changed&-changed;positions.append(old['width']-bit.bit_length());changed^=bit
            if positions:gain[scope]=sorted(positions)
        life.save(out/'raw-toggle-delta.json',gain)
        life.save(out/'single-bits.json',single);life.save(out/'single-toggle-bits.json',sample)
        pins=life.merge_pins(record['pins'],{str(sidecar):seal})
        for p in run.rglob('*'):
            if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
        require(pins[str(files[0])]==sample_sha,'Stable candidate Toggle')
        life.check(pins)
        life.save(out/'qualification.json',dict(status='FULL_ARCHITECTURE_FMA_HOLD_OBSERVED_NOT_ADMITTED'
            if audit['FMA_hold_observed'] else 'FULL_ARCHITECTURE_FMA_HOLD_NOT_TRIGGERED_NO_RETRY_NOT_ADMITTED',
            baseline=792,baseline_seal=oracle.BASE_SHA,input_pins=pins,
            output_pins={str(p):life.digest(p) for p in out.iterdir()},scalar_counts=pre['counts'],
            checks=56,FMA_audit=audit,contract=contract,vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',
            measured_toggle_gain=sum(map(len,gain.values())),raw_four_metric_delta=delta['metrics'],
            coverage_admitted=False,automatic_retry=False,official_percentage_claimed=False))
        print(out,life.digest(out/'qualification.json'))
    except BaseException as e:
        life.save(out/'failure.json',dict(status='HOLD_NOT_ADMITTED',reason=type(e).__name__+': '+str(e),retry=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
