"""Full ordinary scalar architecture plus DIV144 owned exponent-table measurements."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
from types import FunctionType

import run_scalar_div_subnormal794 as runner
import collect_scalar_fpu_fma_arbiter792 as original
from collect_c910_float_edge_initialized777 import coverage_identity

life,require,oracle=runner.life,runner.require,runner.oracle
SCOPE=original.SCOPE
SRT,ROUND=oracle.SRT,oracle.ROUND
ISSUE='ara_tb.dut.i_ara_soc.i_system.i_ariane.issue_stage_i.i_issue_read_operands'
bitmap,toggle=original.bitmap,original.toggle


def probe_widths(proof):
    root={SCOPE+'.'+n:w for n,w in dict(flush_i=1,state_q=1,fpu_valid_i=1,fpu_ready_o=1,
        fu_data_i=207,fpu_valid_o=1,fpu_trans_id_o=3,result_o=64,fpu_exception_o=203).items()}
    root.update({SCOPE+'.fpu_gen.'+n:w for n,w in dict(fpu_tag_d=3,fpu_op_d=5,fpu_rm_d=3,fpu_in_ready=1).items()})
    root.update({SCOPE+'.fpu_gen.'+n:w for n,w in dict(fpu_in_valid=1,hold_inputs=1,use_hold=1,
        operand_a_d=64,operand_b_d=64,operand_c_d=64,operand_a_q=64,operand_b_q=64,operand_c_q=64,
        fpu_op_q=5,fpu_rm_q=3,fpu_tag_q=3).items()})
    root.update({ISSUE+'.issue_instr_i':438,ISSUE+'.fpu_valid_n':1,ISSUE+'.fu_data_n':207})
    root.update({SRT+'.'+n:w for n,w in dict(ex2_pipedown=1,vfdsu_ex2_double=1,vfdsu_ex2_sqrt=1,
        vfdsu_ex2_expnt_rst=13,ex2_result_double_denorm_round_add_num=53,
        ex2_result_denorm_round_add_num=53,vfdsu_ex3_result_denorm_round_add_num=53).items()})
    root.update({ROUND+'.'+n:w for n,w in dict(ex3_pipedown=1,ex3_rslt_denorm=1,
        vfdsu_ex3_result_denorm_round_add_num=53,frac_add1_op1_with_denorm=55,
        frac_sub1_op1_with_denorm=55).items()})
    return dict(root,**{'ara_tb.clk':1,'ara_tb.rst_n':1})


def packed_field(bits,width,left,right):
    require(0<len(bits)<=width and set(bits)<=set('01xz'),'Exact packed encoding')
    bits=bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')
    field=bits[width-1-left:width-right]
    require(set(field)<=set('01'),'Unknown used packed field')
    return int(field,2)


def expected_requests(pre):
    commits=list(oracle.build.parse_spike_commits(runner.PRE/'spike.trace'))
    pc=pre['symbols']['div_matrix_insn']
    selected=[c for c in commits if c.pc in (pc-8,pc-4,pc,pc+4)]
    require(len(selected)==576,'Actual sealed reference includes432 transfer requests, not DIV-only')
    expected=[]
    for i,cell in enumerate(oracle.cells()):
        e=oracle.gold(*cell)
        for role,commit in enumerate(selected[4*i:4*i+4]):
            require(commit.pc==(pc-8,pc-4,pc,pc+4)[role],'Complete ordered cell instruction PCs')
            w=commit.instruction
            if role<2:
                require(w>>25==0x79 and (w>>20)&31==0 and (w>>12)&7==0 and
                    (w>>7)&31==role and commit.fpr_writes=={role:e['a'] if role==0 else e['b']},
                    'Independent FMV_D_X compiled opcode/value')
                item=dict(kind='FMV_X2F',result=e['a'] if role==0 else e['b'],fflags=0,
                    operand_a=e['a'] if role==0 else e['b'],rm=3)
            elif role==2:
                require(w==0x1a107153 and commit.fpr_writes=={2:e['result']},'Independent DIV result')
                item=dict(e,kind='DIV',operand_a=e['a'],operand_b=e['b'])
            else:
                rd=(w>>7)&31
                require(w>>25==0x71 and (w>>20)&31==0 and (w>>15)&31==2 and
                    (w>>12)&7==0 and rd!=0 and commit.gpr_writes=={rd:e['result']},
                    'Independent FMV_X_D compiled opcode/value')
                item=dict(kind='FMV_F2X',result=e['result'],fflags=0,operand_a=e['result'],rm=3)
            expected.append(dict(item,pc=commit.pc,instruction=w,cell=i))
    return expected


def audit_edges(decl,edges,expected,proof):
    require(all(decl.get(p,{}).get('width')==w and decl[p].get('type') in ('wire','reg')
        for p,w in probe_widths(proof).items()),'All typed aggregate/field probe declarations')
    def field(state,path,left,right):
        return packed_field(state.get(decl[path]['code'],'x'),decl[path]['width'],left,right)
    def read(state,path):return field(state,path,decl[path]['width']-1,0)
    def raw(state,path):
        bits=state.get(decl[path]['code'],'x').lower()
        width=decl[path]['width']
        require(0<len(bits)<=width and set(bits)<=set('01xz'),'Exact four-state operand representation')
        return bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')
    def operands(state,path,e):
        names=('operand_a','operation','trans_id')+ (('operand_b',) if e['kind']=='DIV' else ())
        return {n:field(state,path,*proof['fu_layout']['fields'][n]) for n in names}
    live={};issued=0;scheduled=None;schedule_count=0;completed=[];observations=[];idle_flush=[]
    pending=None;hold_count=0;stall_cycles=0
    def complete_output(before,time):
        tid=read(before,SCOPE+'.fpu_trans_id_o');require(tid in live,'Output needs unique live owner')
        owner=live[tid]
        require(owner['accepted'],'Output cannot precede accepted FPU input')
        require(owner['kind']!='DIV' or owner['ex2'] and owner['ex3'],'DIV owned pipeline before writeback')
        require(read(before,SCOPE+'.result_o')==owner['result'],'Independent result/TID output')
        ex={n:field(before,SCOPE+'.fpu_exception_o',*proof['exception_layout']['fields'][n])
            for n in ('cause','valid','tval')}
        require(ex==dict(cause=owner['fflags'],valid=0,tval=0),'Full driven transfer/DIV flags output')
        completed.append(dict(index=owner['index'],pc=owner['pc'],kind=owner['kind'],tid=tid,
            time=time,result=owner['result'],flags=ex['cause']))
        del live[tid]
    for time,before,after in edges:
        root=lambda n:read(before,SCOPE+'.'+n)
        gen=lambda n:read(before,SCOPE+'.fpu_gen.'+n)
        output_consumed=False
        if root('flush_i'):
            require(not live and pending is None and scheduled is None and root('state_q')==root('fpu_valid_i')==0 and
                read(before,ISSUE+'.fpu_valid_n')==0,'No flush during FPU owner')
            idle_flush.append(time);continue
        held_edge=pending is not None
        if held_edge:
            require(root('state_q')==1 and gen('use_hold')==1 and gen('hold_inputs')==0 and gen('fpu_in_valid')==1,
                'Owned stable STALL controls')
            require([raw(before,SCOPE+'.fpu_gen.operand_'+n+'_q') for n in 'abc']==pending['captured_abc'] and
                gen('fpu_op_q')==pending['captured_op'] and gen('fpu_rm_q')==pending['captured_rm'] and
                gen('fpu_tag_q')==pending['tid'],'Held ABC/op/RM/TID stable')
            stall_cycles+=1
            if gen('fpu_in_ready'):
                require(root('fpu_ready_o')==1 and read(after,SCOPE+'.state_q')==0,'Held acceptance and READY return')
                pending['accepted']=True;pending=None
            else:require(root('fpu_ready_o')==0 and read(after,SCOPE+'.state_q')==1,'STALL cannot release before readiness')
        elif root('fpu_valid_i'):
            require(scheduled is not None and issued<len(expected),'FPU request needs exact prior issue PC/TID')
            e=expected[issued];issued+=1
            require(root('state_q')==0 and root('fpu_ready_o')==gen('fpu_in_ready') and gen('fpu_in_valid')==1,
                'Input handshake without assuming ready is always1')
            values=operands(before,SCOPE+'.fu_data_i',e)
            if values['trans_id'] in live and root('fpu_valid_o') and root('fpu_trans_id_o')==values['trans_id']:
                # The pre-edge writeback belongs to the old owner, not this new request.
                complete_output(before,time);output_consumed=True
            require(values==scheduled['fu'] and scheduled['pc']==e['pc'],'Exact next-edge issue PC/TID/operand owner')
            name='FDIV' if e['kind']=='DIV' else e['kind']
            op='DIV' if e['kind']=='DIV' else 'SGNJ'
            require(values['operand_a']==e['operand_a'] and
                ('operand_b' not in e or values['operand_b']==e['operand_b']) and
                values['operation']==proof['ariane_ops'][name] and
                read(before,SCOPE+'.fpu_gen.fpu_op_d')==proof['fpnew_ops'][op] and
                read(before,SCOPE+'.fpu_gen.fpu_rm_d')==e['rm'] and
                values['trans_id']==read(before,SCOPE+'.fpu_gen.fpu_tag_d'),'Every transfer/DIV op/value/RM/TID')
            require(values['trans_id'] not in live,'TID reuse before previous output')
            owner=dict(e,index=issued-1,tid=values['trans_id'],ex2=False,ex3=False,accepted=bool(gen('fpu_in_ready')))
            live[values['trans_id']]=owner
            if not owner['accepted']:
                hold_count+=1
                abc=[raw(before,SCOPE+'.fpu_gen.operand_'+n+'_d') for n in 'abc']
                require(gen('operand_a_d')==e['operand_a'] and
                    (e['kind']!='DIV' or gen('operand_b_d')==e['operand_b']),
                    'Held data independently matches transfer/DIV operand gold')
                require(gen('hold_inputs')==1 and read(after,SCOPE+'.state_q')==1 and
                    [raw(after,SCOPE+'.fpu_gen.operand_'+n+'_q') for n in 'abc']==abc and
                    read(after,SCOPE+'.fpu_gen.fpu_op_q')==gen('fpu_op_d') and
                    read(after,SCOPE+'.fpu_gen.fpu_rm_q')==gen('fpu_rm_d') and
                    read(after,SCOPE+'.fpu_gen.fpu_tag_q')==values['trans_id'],'Exact holding capture')
                owner.update(captured_abc=abc,captured_op=gen('fpu_op_d'),captured_rm=gen('fpu_rm_d'))
                pending=owner
            else:require(gen('hold_inputs')==0,'No capture on accepted input')
            scheduled=None
        else:
            require(scheduled is None and root('state_q')==0,'Accepted issue next-edge FPU request; no unowned STALL')
        if read(before,ISSUE+'.fpu_valid_n'):
            require(schedule_count<len(expected),'Extra issue-stage FPU request')
            e=expected[schedule_count];schedule_count+=1
            fields=proof['issue_layout']['fields']
            pc=field(before,ISSUE+'.issue_instr_i',*fields['pc'])
            tid=field(before,ISSUE+'.issue_instr_i',*fields['trans_id'])
            fu=operands(before,ISSUE+'.fu_data_n',e)
            require(pc==e['pc'] and tid==fu['trans_id'],'Independent compiled PC/issue TID')
            require(read(after,SCOPE+'.fpu_valid_i')==1,'Issue-valid registered FPU path')
            scheduled=dict(pc=pc,fu=fu)
        if read(before,SRT+'.ex2_pipedown'):
            divisors=[v for v in live.values() if v['kind']=='DIV' and not v['ex2']]
            require(len(divisors)==1 and divisors[0]['accepted'],'One accepted EX2 transition owner');div=divisors[0]
            require(read(before,SRT+'.vfdsu_ex2_double')==1 and read(before,SRT+'.vfdsu_ex2_sqrt')==0,
                'FP64 DIV, not other format/SQRT')
            require(read(before,SRT+'.vfdsu_ex2_expnt_rst')==div['exponent_predicate'] and
                read(before,SRT+'.ex2_result_double_denorm_round_add_num')==
                read(before,SRT+'.ex2_result_denorm_round_add_num')==div['onehot'],
                'Exact exponent-table predicate/select')
            require(read(after,SRT+'.vfdsu_ex3_result_denorm_round_add_num')==div['onehot'],
                'Actual next-edge EX3 register copy')
            div['ex2']=True
        if read(before,ROUND+'.ex3_pipedown'):
            divisors=[v for v in live.values() if v['kind']=='DIV' and v['ex2'] and not v['ex3']]
            require(len(divisors)==1,'One unique round owner after EX2');div=divisors[0]
            shifted=div['onehot']<<1
            require(read(before,ROUND+'.ex3_rslt_denorm')==1 and
                read(before,ROUND+'.vfdsu_ex3_result_denorm_round_add_num')==div['onehot'] and
                read(before,ROUND+'.frac_add1_op1_with_denorm')==shifted and
                read(before,ROUND+'.frac_sub1_op1_with_denorm')==((1<<55)-1)^shifted,
                'Actual denorm round concat/complement predicate')
            div['ex3']=True
            observations.append(dict(index=div['index'],time=time,k=div['k'],table=div['onehot']))
        if root('fpu_valid_o') and not output_consumed:complete_output(before,time)
    require(issued==schedule_count==len(completed)==len(expected) and not live and scheduled is None and pending is None,
        'Complete all transfer/DIV issue/request/output owners')
    return dict(issued=issued,completed=completed,table_observations=observations,
        observed_k=sorted(set(e['k'] for e in observations)),idle_flush=idle_flush,
        exception_unobserved=dict(tval2='UNOBSERVED',tinst='UNOBSERVED',gva='UNOBSERVED'),
        hold_count=hold_count,stall_cycles=stall_cycles,no_forcing=True,all_result_flags_checked=True)


def wave_audit(path,proof,pre):
    parse=original.oracle.prior.wave.vcd
    parser=FunctionType(parse.__code__,dict(parse.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    stream=iter(parser(path));_,decl=next(stream)
    def edges():
        begun=False
        for time,before,after in stream:
            if before.get(decl['ara_tb.clk']['code'])=='0' and after.get(decl['ara_tb.clk']['code'])=='1':
                reset=before.get(decl['ara_tb.rst_n']['code'],'x');require(reset in ('0','1'),'Known reset')
                if reset=='0':require(not begun,'Unexpected reset after workload');continue
                begun=True;yield time,before,after
    return audit_edges(decl,edges(),expected_requests(pre),proof)


def architecture(rows,pre,scalar):
    require(len(rows)==pre['counts']['matched_instructions'] and
        all(r['event']=='retire' and int(r['trap'])==0 for r in rows) and
        [int(r['order']) for r in rows]==list(range(len(rows))),'Complete retire-only no-trap sequence')
    original.oracle.prior.old.architecture.scalar_exact(scalar,pre['counts'])
    memory={}
    for r in rows:
        store=original.oracle.prior.old.architecture.scalar_store(r)
        if store:
            addr,data=store;memory.update({addr+i:b for i,b in enumerate(data)})
    def word(addr,size=8):return sum(memory[addr+i]<<(8*i) for i in range(size))
    sym=pre['symbols'];expected=[oracle.gold(*e) for e in oracle.cells()]
    divisions=[r for r in rows if int(r['pc'],16)==sym['div_matrix_insn']]
    require(len(divisions)==144 and all(int(r['insn'],16)==0x1a107153 for r in divisions),'Actual all144 DIV PCs/opcodes')
    for i,e in enumerate(expected):
        require([word(sym['div_observed']+24*i+8*j) for j in range(3)]==
            [e['result'],e['fflags'],e['fcsr']],'Whole native per-cell numeric/fflags/FCSR gold')
    require(word(sym['div_csr'])==word(sym['div_csr']+8),'Full FCSR restore')
    require([word(sym['g75_result'],4),word(sym['g75_result']+4,4),word(sym['num_failed'],4)]==[436,0,0],
        'Native436 signature')
    original.guard_loads(rows,sym['div_guards'])
    return dict(cells=144,checks=436,observed_bytes=3456,FCSR_restored=True,guards_checked=True,
        scalar_counts=pre['counts'],every_DIV_PC_opcode_checked=True)


def stdout_gate(text):
    lines=text.splitlines()
    require(lines.count('SUBNORMAL_DIV_PROBE_READY')==1 and 'FMA_ARB_PROBE_READY' not in lines,
        'Exact case-owned probe marker')
    return original.stdout_gate(text.replace('SUBNORMAL_DIV_PROBE_READY','FMA_ARB_PROBE_READY').replace(
        'SUBNORMAL_DIV_PROBE_ERROR','FMA_ARB_PROBE_ERROR'))


def terminal_gate(run,record):
    return FunctionType(original.terminal_gate.__code__,dict(original.terminal_gate.__globals__,runner=runner))(run,record)


def collect(run,out,seal):
    require(not out.exists(),'Fresh qualification output')
    sidecar=run.with_name(run.name+'.prepared.json');record=life.read_bound(sidecar,seal)
    runner.verify(run,record,terminal=True)
    terminal_gate(run,record)
    text=(run/'console.log').read_text()
    stdout_gate(text)
    pre=life.read_bound(runner.PRE/'preflight.json',runner.PRE_SHA)
    out.mkdir()
    try:
        arch=original.oracle.prior.old.architecture
        scalar=arch.spike_trace.compare_commit_prefix(runner.PRE/'spike.trace',run/'commit_trace.csv',0x80000000,
            terminal_tohost_address=0x80001000,rvfi_store_data_layout='unshifted')
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        native=architecture(rows,pre,scalar)
        with (run/'vector_trace.csv').open() as f:
            require(all(r['event']=='config' for r in csv.DictReader(f)),'Zero vector data activity')
        life.save(out/'scalar-comparison.json',scalar);life.save(out/'architecture-audit.json',native)
        vpd=run/'scalar-div-subnormal794.vpd'
        require(0<vpd.stat().st_size<=128*1024*1024,'Focused VPD size')
        with (out/'converter.log').open('x') as f:
            subprocess.run([str(runner.reused.lifecycle.converter.CONVERTER),str(vpd),str(out/'probe.vcd')],
                stdout=f,stderr=subprocess.STDOUT,check=True,timeout=120)
        wave=wave_audit(out/'probe.vcd',record['source_contract'],pre);life.save(out/'native-exponent-audit.json',wave)
        ledger=out/'single-inputs.txt'
        with ledger.open('x') as f:f.write(str(life.IMAGE)+'.vdb\n'+str(run/'code.vdb')+'\n')
        folder=run/'code.vdb/snps/coverage/db/testdata'/runner.NAME
        require(list(folder.parent.iterdir())==[folder],'One exact native testcase')
        coverage_identity(folder,run,record,Path(str(life.IMAGE)+'.vdb'))
        single=bitmap.collect(ledger);base=life.read_bound(oracle.BASE/'admission-manifest.json',oracle.BASE_SHA)
        bp=oracle.BASE/'combined-bits.json';before=life.read_bound(bp,base['output_pins'][str(bp)])
        after=bitmap.combine(before,single);delta=bitmap.delta(before,after)
        require(sum(len(v) for v in before['metrics'].values())==6162 and
            after['tests']==before['tests']+single['tests'],'Full6162 compatible OR/prefix')
        tp=oracle.BASE/'combined-toggle-bits.json';bt=life.read_bound(tp,base['output_pins'][str(tp)])
        sample,sha=toggle.rows(folder/'tgl.verilog.data.xml',list(bt));at=toggle.union(bt,sample)
        gains=toggle.gains(bt,at)
        for name,value in (('single-bits.json',single),('raw-four-metric-delta.json',delta),
            ('single-toggle-bits.json',sample),('raw-toggle-gains.json',gains)):
            life.save(out/name,value)
        pins=life.merge_pins(record['pins'],{str(sidecar):seal})
        for p in run.rglob('*'):
            if p.is_file():pins=life.merge_pins(pins,{str(p):life.digest(p)})
        require(pins[str(folder/'tgl.verilog.data.xml')]==sha,'Stable raw Toggle bytes')
        life.check(pins)
        life.save(out/'qualification.json',dict(status='FULL_SCALAR_DIV_SUBNORMAL144_NATIVE_QUALIFIED_NOT_ADMITTED',
            baseline=794,baseline_seal=oracle.BASE_SHA,architecture=native,native_exponent_audit=wave,
            input_pins=pins,output_pins={str(p):life.digest(p) for p in out.iterdir()},
            vector_status='UNOBSERVABLE_ZERO_DATA_REQUESTS',measured_Toggle=sum(map(len,gains.values())),
            raw_delta=delta['metrics'],coverage_admitted=False,official_percentage_claimed=False,
            RTL_changed=False,automatic_retry=False))
        print('QUALIFIED_NOT_ADMITTED',life.digest(out/'qualification.json'))
    except BaseException as e:
        life.save(out/'failure.json',dict(status='HOLD_NOT_ADMITTED',reason=type(e).__name__+': '+str(e),retry=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal',required=True);a=p.parse_args()
    collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
