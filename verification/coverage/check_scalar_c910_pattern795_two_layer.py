"""Independent physical FPU arithmetic ledger plus unchanged full architectural oracle."""
import argparse
from pathlib import Path
from types import FunctionType
import collect_scalar_c910_pattern795_v2 as api

c=api.original
life,require=c.life,c.require
API_SHA='444db4478896940ab9e86a299bce11548ecd46c99ba3541f2fd1cbd098b8f526'


def routes(pre):
    # This map describes immutable instruction roles, never a retirement cursor.
    mapping={}
    for arithmetic,kind in (('pattern_div_insn','DIV'),('pattern_sqrt_insn','SQRT')):
        pc=pre['symbols'][arithmetic]
        for offset,role in ((-8,'FMV_X2F'),(-4,'FMV_X2F'),(0,kind),(4,'FMV_F2X')):
            require(pc+offset not in mapping,'Unique compiled FPU instruction PC')
            mapping[pc+offset]=role
    reference=c.expected_requests(pre)
    require(set(mapping)=={r['pc'] for r in reference} and all(mapping[r['pc']]==r['kind'] for r in reference),
        'All compiled FP64 instruction roles match sealed ELF/reference')
    return mapping


class PhysicalTracker:
    def __init__(self,decl,proof,pc_roles):
        require(all(decl.get(p,{}).get('width')==w and decl[p].get('type') in ('wire','reg')
            for p,w in c.probe_widths(proof).items()),'Complete exact typed probe declarations')
        self.decl,self.proof,self.roles=decl,proof,pc_roles
        self.scheduled=None;self.pending=None;self.live={}
        self.issues=[];self.requests=[];self.outputs=[];self.canceled=[];self.stages=[]
        self.flushes=[];self.holds=0;self.stalls=0;self.last_time=None;self.table=c.literal_table()

    def raw(self,state,path):
        bits=state.get(self.decl[path]['code'],'x').lower();width=self.decl[path]['width']
        require(0<len(bits)<=width and set(bits)<=set('01xz'),'Exact four-state representation')
        return bits.rjust(width,bits[0] if bits[0] in 'xz' else '0')

    def field(self,state,path,left,right):return c.frozen.packed_field(self.raw(state,path),self.decl[path]['width'],left,right)

    def read(self,state,path):return self.field(state,path,self.decl[path]['width']-1,0)

    def root(self,state,name):return self.read(state,c.SCOPE+'.'+name)

    def gen(self,state,name):return self.read(state,c.SCOPE+'.fpu_gen.'+name)

    def packet(self,state,path,role):
        names=('operand_a','operation','trans_id')+(('operand_b',) if role=='DIV' else ())
        return {n:self.field(state,path,*self.proof['fu_layout']['fields'][n]) for n in names}

    def request(self,before,time):
        require(self.scheduled is not None,'Registered input requires exact physical prior issue')
        owner=dict(self.scheduled);role=owner['kind'];actual=self.packet(before,c.SCOPE+'.fu_data_i',role)
        require(actual==owner['packet'],'Exact used issue-to-input operands/op/TID')
        op=role if role in ('DIV','SQRT') else 'SGNJ';rm=self.gen(before,'fpu_rm_d')
        require(self.gen(before,'fpu_op_d')==self.proof['fpnew_ops'][op] and
            self.gen(before,'fpu_tag_d')==owner['tid'],'Actual operation and tag')
        a=actual['operand_a'];b=actual.get('operand_b')
        require(self.gen(before,'operand_a_d')==a and (role!='DIV' or self.gen(before,'operand_b_d')==b),
            'Used FPU input data equals source packet')
        if role in ('DIV','SQRT'):
            gold=c.oracle.gold(a,b if role=='DIV' else 0,role=='SQRT',rm)
            result,flags=gold['result'],gold['fflags']
        else:
            require(rm==3,'Source-bound exact FMV passthrough mode');result,flags=a,0
        owner.update(input_time=time,rm=rm,result=result,fflags=flags,initial=False,ex2=False,round=False,
            accepted=False,math_gold_from_actual_request=True)
        self.requests.append(owner)
        return owner

    def arithmetic_owner(self,predicate):
        owners=[o for o in self.live.values() if o['kind'] in ('DIV','SQRT') and predicate(o)]
        require(len(owners)==1 and owners[0]['accepted'],'Unique accepted physical arithmetic stage owner')
        return owners[0]

    def stage_events(self,before,after,time):
        if self.read(before,c.SRT+'.initial_srt_en'):
            o=self.arithmetic_owner(lambda o:not o['initial']);div=o['kind']=='DIV'
            selector=64+((o['packet']['operand_b']&c.oracle.MASK)>>46) if div else 0
            require(self.read(before,c.SRT+'.initial_srt_sel_div_in')==int(div) and
                self.read(before,c.SRT+'.initial_srt_sel_sqrt_in')==int(not div) and
                self.read(before,c.SRT+'.initial_bound_sel_in')==selector and
                self.read(after,c.ITER+'.bound_sel')==selector,'Actual operand-derived selector/register')
            if div:
                for n,v in self.table[selector].items():
                    require(self.read(after,c.BOUND+'.ori_digit_bound_'+str(n))==v,'Exact literal bound value')
            o['initial']=True;o['selector']=selector
            self.stages.append(dict(owner=o['physical_index'],stage='initial',selector=selector,time=time))
        if self.read(before,c.SRT+'.ex2_pipedown'):
            o=self.arithmetic_owner(lambda o:o['initial'] and not o['ex2'])
            require(self.read(before,c.SRT+'.vfdsu_ex2_double')==1 and
                self.read(before,c.SRT+'.vfdsu_ex2_sqrt')==int(o['kind']=='SQRT'),'Actual FP64 arithmetic operation')
            o['ex2']=True;self.stages.append(dict(owner=o['physical_index'],stage='ex2',time=time))
        if self.read(before,c.ROUND+'.ex3_pipedown'):
            o=self.arithmetic_owner(lambda o:o['ex2'] and not o['round'])
            require(self.read(before,c.ROUND+'.ex3_rslt_denorm')==0,'Normal mathematical result round stage')
            o['round']=True;self.stages.append(dict(owner=o['physical_index'],stage='round',time=time))

    def output(self,before,time,flush):
        tid=self.root(before,'fpu_trans_id_o');require(tid in self.live,'Output has unique live physical TID')
        o=self.live[tid];require(o['accepted'],'Output cannot precede physical acceptance')
        require(o['kind'] not in ('DIV','SQRT') or o['initial'] and o['ex2'] and o['round'],
            'Every arithmetic output has complete owned stages')
        require(self.root(before,'result_o')==o['result'],'Independent actual-request mathematical result')
        ex={n:self.field(before,c.SCOPE+'.fpu_exception_o',*self.proof['exception_layout']['fields'][n])
            for n in ('cause','valid','tval')}
        require(ex==dict(cause=o['fflags'],valid=0,tval=0),'Full driven flags/exception output gold')
        self.outputs.append(dict(o,output_time=time,flush_edge=bool(flush),physical_output_not_retirement=True))
        del self.live[tid]

    def consume(self,time,before,after):
        require(self.last_time is None or time>self.last_time,'Strict edge chronology');self.last_time=time
        flush=self.root(before,'flush_i');valid=self.root(before,'fpu_valid_i')
        self.stage_events(before,after,time)
        if self.root(before,'fpu_valid_o'):self.output(before,time,flush)
        if flush:
            require(not self.live and self.pending is None and self.root(before,'state_q')==0 and
                self.gen(before,'hold_inputs')==self.gen(before,'use_hold')==0 and
                self.read(before,c.ISSUE+'.fpu_valid_n')==0,'Flush cannot lose another accepted/held owner')
            if valid:
                o=self.request(before,time)
                require(self.gen(before,'fpu_in_valid')==1 and self.gen(before,'fpu_in_ready')==1,
                    'Observed valid/ready transaction with source-defined flush priority')
                require(self.root(after,'fpu_valid_i')==0 and self.root(after,'state_q')==0,
                    'Flush clears registered request/hold state')
                self.canceled.append(dict(o,cancel_time=time,cancellation='synchronous_flush_priority',
                    entered_surviving_pipeline=False));self.scheduled=None
            else:require(self.scheduled is None,'Flush cannot hide an unobserved scheduled input')
            self.flushes.append(time);return
        if self.pending is not None:
            o=self.pending
            require(self.root(before,'state_q')==1 and self.gen(before,'use_hold')==1 and
                self.gen(before,'hold_inputs')==0 and self.gen(before,'fpu_in_valid')==1,'Owned STALL controls')
            require([self.raw(before,c.SCOPE+'.fpu_gen.operand_'+n+'_q') for n in 'abc']==o['captured_abc'] and
                self.gen(before,'fpu_op_q')==o['captured_op'] and self.gen(before,'fpu_rm_q')==o['rm'] and
                self.gen(before,'fpu_tag_q')==o['tid'],'Stable held raw ABC/op/RM/TID, including unused X')
            self.stalls+=1
            ready=self.gen(before,'fpu_in_ready')
            require(self.root(before,'fpu_ready_o')==ready and self.root(after,'state_q')==int(not ready),
                'STALL readiness and exact next state')
            if ready:o['accepted']=True;self.pending=None
        elif valid:
            require(self.root(before,'state_q')==0 and self.gen(before,'use_hold')==0 and
                self.gen(before,'fpu_in_valid')==1,'Source READY request path')
            ready=self.gen(before,'fpu_in_ready');require(self.root(before,'fpu_ready_o')==ready,'Input ready forwarding')
            o=self.request(before,time);require(o['tid'] not in self.live,'No TID reuse before previous output')
            self.live[o['tid']]=o;self.scheduled=None;o['accepted']=bool(ready)
            if ready:require(self.gen(before,'hold_inputs')==0,'Accepted input cannot capture hold')
            else:
                self.holds+=1;o['captured_abc']=[self.raw(before,c.SCOPE+'.fpu_gen.operand_'+n+'_d') for n in 'abc']
                o['captured_op']=self.gen(before,'fpu_op_d')
                require(self.gen(before,'hold_inputs')==1 and self.root(after,'state_q')==1 and
                    [self.raw(after,c.SCOPE+'.fpu_gen.operand_'+n+'_q') for n in 'abc']==o['captured_abc'] and
                    self.gen(after,'fpu_op_q')==o['captured_op'] and self.gen(after,'fpu_rm_q')==o['rm'] and
                    self.gen(after,'fpu_tag_q')==o['tid'],'Complete source holding capture')
                self.pending=o
        else:require(self.scheduled is None and self.root(before,'state_q')==0,'No missing registered input/unowned STALL')
        if self.read(before,c.ISSUE+'.fpu_valid_n'):
            require(self.scheduled is None and self.pending is None,'One new physical next-edge issue')
            fields=self.proof['issue_layout']['fields'];path=c.ISSUE+'.issue_instr_i'
            pc=self.field(before,path,*fields['pc']);tid=self.field(before,path,*fields['trans_id'])
            require(pc in self.roles,'Only immutable ELF FP64 instruction PCs')
            role=self.roles[pc];packet=self.packet(before,c.ISSUE+'.fu_data_n',role)
            name={'DIV':'FDIV','SQRT':'FSQRT'}.get(role,role)
            require(packet['trans_id']==tid and packet['operation']==self.proof['ariane_ops'][name],
                'Exact compiled physical PC/op/issue TID')
            require(self.root(after,'fpu_valid_i')==1,'Actual next-edge registered issue valid')
            o=dict(physical_index=len(self.issues),pc=pc,tid=tid,kind=role,packet=packet,issue_time=time)
            self.issues.append(o);self.scheduled=o

    def finish(self):
        require(self.scheduled is None and self.pending is None and not self.live,'Full physical lifecycle drains')
        require(len(self.issues)==len(self.requests)==len(self.outputs)+len(self.canceled),
            'Exact physical issue/request/output/cancel conservation')
        require(len({o['physical_index'] for o in self.outputs+self.canceled})==len(self.issues),
            'Each physical attempt has one terminal outcome')
        return dict(physical_issues=len(self.issues),physical_requests=len(self.requests),
            physical_outputs=len(self.outputs),synchronous_cancels=len(self.canceled),outputs=self.outputs,
            cancellations=self.canceled,stages=self.stages,flush_edges=self.flushes,hold_count=self.holds,
            stall_cycles=self.stalls,all_actual_request_math_gold_checked=True,
            physical_output_to_retirement_mapping_claimed=False,
            exception_unobserved=dict(tval2='UNOBSERVED',tinst='UNOBSERVED',gva='UNOBSERVED'))


def wave_audit(path,proof,pre):
    parser=c.frozen.original.oracle.prior.wave.vcd
    stream=iter(FunctionType(parser.__code__,dict(parser.__globals__,ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))(path))
    _,decl=next(stream);tracker=PhysicalTracker(decl,proof,routes(pre));begun=False
    for time,before,after in stream:
        if before.get(decl['ara_tb.clk']['code'])=='0' and after.get(decl['ara_tb.clk']['code'])=='1':
            reset=before.get(decl['ara_tb.rst_n']['code'],'x');require(reset in ('0','1'),'Known reset')
            if reset=='0':require(not begun,'No reset after workload');continue
            begun=True;tracker.consume(time,before,after)
    result=tracker.finish()
    require((result['physical_issues'],result['physical_outputs'],result['synchronous_cancels'])==(1359,1176,183),
        'Complete observed case-specific physical census; not architectural owner count')
    require(sum(o['kind']=='DIV' for o in result['outputs'])==160 and
        sum(o['kind']=='SQRT' for o in result['outputs'])==64,'All normal arithmetic outputs')
    return result


def authority():
    require(life.digest(Path(api.__file__))==API_SHA,'Exact frozen API helper identity')
    api.private_runner();bookpath=c.oracle.reused.old.BUILD/'build-source-pins.json'
    book=life.read_bound(bookpath,c.oracle.reused.old.SOURCE_SHA)
    pins=life.merge_pins(api.authority(),{str(bookpath):c.oracle.reused.old.SOURCE_SHA})
    for rel in ('hardware/deps/cva6/core/fpu_wrap.sv','hardware/deps/cva6/core/issue_read_operands.sv',
        'hardware/deps/fpnew/src/fpnew_noncomp.sv','hardware/deps/fpnew/src/fpnew_divsqrt_th_64_multi.sv',
        'hardware/deps/common_cells/include/common_cells/registers.svh'):
        p=life.ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen operation/flush-priority source')
        pins[str(p)]=book[str(p)]
    for name in ('check_scalar_c910_pattern795_two_layer.py','test_check_scalar_c910_pattern795_two_layer.py'):
        p=Path(__file__).with_name(name).resolve();pins[str(p)]=life.digest(p)
    return pins


def collect(run,out,seal):
    pins=authority();life.check(pins)
    # Reuse the exact full terminal/scalar/CSR/guard/VDB/OR consumer, only replacing physical audit.
    FunctionType(c.collect.__code__,dict(c.collect.__globals__,runner=api.private_runner(),wave_audit=wave_audit))(run,out,seal)
    core=out/'qualification.json';sha=life.digest(core);q=life.read_bound(core,sha)
    require(q['architecture']['cells']==224 and q['architecture']['checks']==675 and q['coverage_admitted'] is False,
        'Unchanged full independent architecture qualification')
    life.check(q['input_pins']);life.check(q['output_pins']);life.check(pins)
    life.save(out/'two-layer-closure.json',dict(status='FULL_INDEPENDENT_ARCHITECTURE_AND_PHYSICAL_MATH_GOLD_NOT_ADMITTED',
        core_qualification=str(core),core_sha256=sha,input_pins=pins,
        architecture_reference='Complete sealed Spike retirement/GPR/FPR/memory/CSR/gold; no skips',
        physical_reference='Exact Fraction/integer-isqrt gold from actual used operand/op/effective RM',
        physical_output_to_retirement_mapping_claimed=False,original_non_wave_gates_omitted=[],
        coverage_admitted=False,new_simulation=False))
    print('TWO_LAYER_NOT_ADMITTED',life.digest(out/'two-layer-closure.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
