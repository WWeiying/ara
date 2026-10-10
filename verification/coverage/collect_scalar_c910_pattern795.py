"""Full ordinary scalar qualification, reviewed flush-priority owners and bound probe."""
import argparse
import ast
import inspect
import json
import re
from pathlib import Path
from types import FunctionType, SimpleNamespace
import collect_scalar_div_subnormal794 as frozen
import scalar_div_subnormal794_flush_v2 as flush
import run_scalar_c910_pattern795 as runner

life,require,oracle=runner.life,runner.require,runner.oracle
SCOPE,SRT,ROUND,ISSUE=frozen.SCOPE,frozen.SRT,frozen.ROUND,frozen.ISSUE
ITER=SRT+'.x_ct_vfdsu_srt_radix16_with_sqrt'
BOUND=ITER+'.x_ct_vfdsu_srt_radix16_bound_table'


def probe_widths(proof):
    widths=frozen.probe_widths(proof)
    widths.update({SRT+'.'+n:w for n,w in dict(initial_srt_en=1,initial_srt_sel_div_in=1,
        initial_srt_sel_sqrt_in=1,initial_bound_sel_in=7).items()})
    widths[ITER+'.bound_sel']=7
    widths.update({BOUND+'.ori_digit_bound_'+str(i):12 for i in range(1,10)})
    return widths


def expected_requests(pre):
    commits=list(oracle.build.parse_spike_commits(runner.PRE/'spike.trace'))
    result=[];gold=oracle.cells()
    selected=[c for c in commits if c.pc in {pre['symbols'][n]+o for n in ('pattern_div_insn','pattern_sqrt_insn') for o in (-8,-4,0,4)}]
    require(len(selected)==896,'All896 independent compiled/reference owners')
    for i,e in enumerate(gold):
        for role,commit in enumerate(selected[4*i:4*i+4]):
            pc=pre['symbols']['pattern_sqrt_insn' if e['sqrt'] else 'pattern_div_insn']
            require(commit.pc==pc+(-8,-4,0,4)[role],'Exact per-cell compiled owner PC')
            w=commit.instruction
            if role<2:
                v=e['a'] if role==0 else e['b']
                require(w>>25==0x79 and (w>>12)&7==0 and (w>>20)&31==0 and
                    (w>>7)&31==role and commit.fpr_writes=={role:v},'Both real FMV_X2F values/opcodes')
                item=dict(kind='FMV_X2F',operand_a=v,result=v,fflags=0,rm=3)
            elif role==2:
                require(w==(0x5a007153 if e['sqrt'] else 0x1a107153) and commit.fpr_writes=={2:e['result']},'Arithmetic opcode/independent gold')
                item=dict(e,kind='SQRT' if e['sqrt'] else 'DIV',operand_a=e['a'])
                if not e['sqrt']:item['operand_b']=e['b']
            else:
                rd=(w>>7)&31
                require(w>>25==0x71 and (w>>20)&31==0 and (w>>15)&31==2 and
                    (w>>12)&7==0 and rd!=0 and commit.gpr_writes=={rd:e['result']},'Actual FMV_F2X full result')
                item=dict(kind='FMV_F2X',operand_a=e['result'],result=e['result'],fflags=0,rm=3)
            result.append(dict(item,pc=pc+(-8,-4,0,4)[role],instruction=w,cell=i))
    return result


def literal_table():
    oracle.source_evidence()
    source=(life.ROOT/oracle.reused.REL/'ct_vfdsu_srt_radix16_bound_table.v').read_text()
    bodies=re.findall(r"7'h([0-9a-f]+):\s*begin(.*?)end",source,re.S)
    table={}
    for selector,body in bodies:
        rows=re.findall(r"ori_digit_bound_([1-9])\[11:0\]\s*=\s*12'h([0-9a-f]+)",body)
        if rows:
            key=int(selector,16);require(key not in table,'Unique literal DIV selector')
            require(len(rows)==9 and len({n for n,v in rows})==9,'All9 literal bounds')
            table[key]={int(n):int(v,16)&4095 for n,v in rows}
    require(set(range(64,128))<=set(table),'All64 exact normal DIV selectors')
    return table


def owner_implementation():
    # Change only operation routing and arithmetic-stage predicates. The reviewed
    # flush adapter still owns cancellation, cursor rewind, hold and output rules.
    flush.source_proof()
    tree=ast.parse(inspect.getsource(frozen.audit_edges));fn=tree.body[0]
    found=dict(name=0,op=0,complete=0,ex2=0,round=0)
    class Rewrite(ast.NodeTransformer):
        def visit_IfExp(self,node):
            text=ast.unparse(node)
            if text=="'FDIV' if e['kind'] == 'DIV' else e['kind']":
                found['name']+=1;return ast.parse("{'DIV':'FDIV','SQRT':'FSQRT'}.get(e['kind'],e['kind'])",mode='eval').body
            if text=="'DIV' if e['kind'] == 'DIV' else 'SGNJ'":
                found['op']+=1;return ast.parse("e['kind'] if e['kind'] in ('DIV','SQRT') else 'SGNJ'",mode='eval').body
            return self.generic_visit(node)
        def visit_Compare(self,node):
            if ast.unparse(node)=="owner['kind'] != 'DIV'":
                found['complete']+=1;return ast.parse("owner['kind'] not in ('DIV','SQRT')",mode='eval').body
            return self.generic_visit(node)
        def visit_If(self,node):
            text=ast.unparse(node.test)
            if text=="read(before, SRT + '.ex2_pipedown')":
                found['ex2']+=1
                node.body=ast.parse('''
arithmetic=[v for v in live.values() if v['kind'] in ('DIV','SQRT') and not v['ex2']]
require(len(arithmetic)==1 and arithmetic[0]['accepted'] and arithmetic[0].get('initial_seen'),'One source-bound accepted EX2 arithmetic owner')
owner=arithmetic[0]
require(read(before,SRT+'.vfdsu_ex2_double')==1 and read(before,SRT+'.vfdsu_ex2_sqrt')==int(owner['kind']=='SQRT'),'Only owned FP64 DIV/SQRT pipeline')
owner['ex2']=True
''').body
                return node
            if text=="read(before, ROUND + '.ex3_pipedown')":
                found['round']+=1
                node.body=ast.parse('''
arithmetic=[v for v in live.values() if v['kind'] in ('DIV','SQRT') and v['ex2'] and not v['ex3']]
require(len(arithmetic)==1,'One unique accepted normal-round owner')
owner=arithmetic[0]
require(read(before,ROUND+'.ex3_rslt_denorm')==0,'Finite normal result, not denorm-table case')
owner['ex3']=True
observations.append(dict(index=owner['index'],cell=owner['cell'],kind=owner['kind'],time=time))
''').body
                return node
            return self.generic_visit(node)
    tree=Rewrite().visit(tree)
    require(found==dict(name=1,op=1,complete=1,ex2=1,round=1),'Exact frozen operation/stage replacement sites')
    loop=next(n for n in fn.body if isinstance(n,ast.For))
    idx=next(i for i,n in enumerate(loop.body) if isinstance(n,ast.If) and ast.unparse(n.test)=="read(before, SRT + '.ex2_pipedown')")
    loop.body[idx:idx]=ast.parse('''
if read(before,SRT+'.initial_srt_en'):
    arithmetic=[v for v in live.values() if v['kind'] in ('DIV','SQRT') and not v.get('initial_seen')]
    require(len(arithmetic)==1 and arithmetic[0]['accepted'],'Unique accepted initial arithmetic owner')
    owner=arithmetic[0];is_div=owner['kind']=='DIV'
    selector=64+((owner['operand_b']&((1<<52)-1))>>46) if is_div else 0
    require(read(before,SRT+'.initial_srt_sel_div_in')==int(is_div) and read(before,SRT+'.initial_srt_sel_sqrt_in')==int(not is_div),'Owned initial operation selection')
    require(read(before,SRT+'.initial_bound_sel_in')==selector and read(after,ITER+'.bound_sel')==selector,'Independent legal selector and next-edge register')
    if is_div:
        for n,v in TABLE[selector].items():
            require(read(after,BOUND+'.ori_digit_bound_'+str(n))==v,'Actual literal-bound table value')
    owner['initial_seen']=True
    initial_observations.append(dict(index=owner['index'],cell=owner['cell'],kind=owner['kind'],selector=selector,time=time))
''').body
    fn.body.insert(0,ast.parse('initial_observations=[]').body[0])
    # Extract the already-reviewed exact policy literal, not a permissive copy.
    policy=ast.parse(inspect.getsource(flush.audit_edges))
    policies=[n for n in ast.walk(policy) if isinstance(n,ast.Assign) and
        any(ast.unparse(t)=='blocks[0].body' for t in n.targets)]
    require(len(policies)==1,'Unique reviewed flush replacement literal')
    literal=policies[0].value.value.args[0]
    require(isinstance(literal,ast.Constant) and type(literal.value) is str,'Literal frozen flush policy')
    blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="root('flush_i')"]
    require(len(blocks)==1,'Unique original flush gate');blocks[0].body=ast.parse(literal.value).body
    fn.body.insert(0,ast.parse('cancellations=[]').body[0])
    ret=next(n for n in fn.body if isinstance(n,ast.Return))
    ret.value=ast.parse("dict(issued=issued,completed=completed,table_observations=observations,initial_observations=initial_observations,scheduled_cancellations=cancellations,idle_flush=idle_flush,hold_count=hold_count,stall_cycles=stall_cycles,all_result_flags_checked=True,no_forcing=True,exception_unobserved=dict(tval2='UNOBSERVED',tinst='UNOBSERVED',gva='UNOBSERVED'))",mode='eval').body
    namespace=dict(frozen.audit_edges.__globals__,probe_widths=probe_widths,ITER=ITER,BOUND=BOUND,TABLE=literal_table())
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),namespace)
    return namespace['audit_edges']


def audit_edges(decl,edges,expected,proof):
    return owner_implementation()(decl,edges,expected,proof)


def wave_audit(path,proof,pre):
    return FunctionType(frozen.wave_audit.__code__,dict(frozen.wave_audit.__globals__,audit_edges=audit_edges,
        expected_requests=expected_requests))(path,proof,pre)


def architecture(rows,pre,scalar):
    counts=pre['counts'];arch=frozen.original.oracle.prior.old.architecture
    require(len(rows)==counts['matched_instructions'] and all(r['event']=='retire' and int(r['trap'])==0 for r in rows)
        and [int(r['order']) for r in rows]==list(range(len(rows))),'Complete no-trap native scalar sequence')
    arch.scalar_exact(scalar,counts)
    memory={}
    for r in rows:
        store=arch.scalar_store(r)
        if store:
            address,data=store;memory.update({address+i:b for i,b in enumerate(data)})
    def word(addr,size=8):return sum(memory[addr+i]<<(8*i) for i in range(size))
    for i,e in enumerate(oracle.cells()):
        require([word(pre['symbols']['pattern_observed']+24*i+8*j) for j in range(3)]==
            [e['result'],e['fflags'],e['fcsr']],'Full224 normal integer result/flags/FCSR gold')
    symbols=pre['symbols'];require(word(symbols['pattern_csr'])==word(symbols['pattern_csr']+8),'Full FCSR restore')
    require([word(symbols['g75_result'],4),word(symbols['g75_result']+4,4),word(symbols['num_failed'],4)]==[675,0,0],'675 native checks')
    frozen.original.guard_loads(rows,symbols['pattern_guards'])
    for name,opcode,count in (('pattern_div_insn',0x1a107153,160),('pattern_sqrt_insn',0x5a007153,64)):
        owners=[r for r in rows if int(r['pc'],16)==symbols[name]]
        require(len(owners)==count and all(int(r['insn'],16)==opcode for r in owners),'All arithmetic retired owners')
    return dict(cells=224,checks=675,observed_bytes=5376,FCSR_restored=True,guards_checked=True,scalar_counts=counts)


def stdout_gate(text):
    lines=text.splitlines()
    require(lines.count('C910_PATTERN_PROBE_READY')==1 and 'SUBNORMAL_DIV_PROBE_READY' not in lines,
        'Exact normal224 case-owned probe marker')
    return frozen.stdout_gate(text.replace('C910_PATTERN_PROBE_READY','SUBNORMAL_DIV_PROBE_READY').replace(
        'C910_PATTERN_PROBE_ERROR','SUBNORMAL_DIV_PROBE_ERROR'))


def collect(run,out,seal):
    tree=ast.parse(inspect.getsource(frozen.collect))
    replacements={'scalar-div-subnormal794.vpd':'scalar-c910-pattern795.vpd',
        'FULL_SCALAR_DIV_SUBNORMAL144_NATIVE_QUALIFIED_NOT_ADMITTED':'FULL_SCALAR_C910_NORMAL224_NATIVE_QUALIFIED_NOT_ADMITTED'}
    class Rewrite(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is str and node.value in replacements:return ast.copy_location(ast.Constant(replacements[node.value]),node)
            return node
        def visit_keyword(self,node):
            if node.arg=='baseline' and isinstance(node.value,ast.Constant) and node.value.value==794:
                node.value=ast.Constant(795)
            return self.generic_visit(node)
    tree=Rewrite().visit(tree)
    def exact_union(before,single):
        require(len(before)==2989 and set(before)==set(single),'Complete2989 native Toggle population')
        return frozen.toggle.union(before,single)
    native=SimpleNamespace(**vars(frozen.toggle));native.union=exact_union
    ns=dict(frozen.collect.__globals__,runner=runner,oracle=oracle,toggle=native,architecture=architecture,wave_audit=wave_audit,
        terminal_gate=FunctionType(frozen.terminal_gate.__code__,dict(frozen.terminal_gate.__globals__,runner=runner)),stdout_gate=stdout_gate)
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),ns)
    ns['collect'](run,out,seal)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--prepared-seal',required=True);a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
