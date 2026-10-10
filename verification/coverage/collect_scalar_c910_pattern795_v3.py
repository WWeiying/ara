"""Offline flush/writeback ordering closure, retaining every surviving-owner gate."""
import argparse
import ast
import inspect
from pathlib import Path
from types import FunctionType
import collect_scalar_c910_pattern795_v2 as api

c=api.original
life,require=api.life,api.require
API_SHA='444db4478896940ab9e86a299bce11548ecd46c99ba3541f2fd1cbd098b8f526'
DIAG=life.OUT/'scalar-c910-pattern795-first-flush-agent-20261008-01.json'
DIAG_SHA='0754a4ac4af9614e9426e5d51762b7091a3eedca1b2ffc2e26fc6bcb92ccc711'
PREFIX='''
if root('fpu_valid_o'):
    require(pending is None and root('state_q')==0 and gen('hold_inputs')==0 and gen('use_hold')==0,
        'Flush writeback cannot hide a held owner')
    complete_output(before,time)
    output_consumed=True
    completed[-1]['flush_edge']=True
'''


def source_proof():
    require(life.digest(Path(api.__file__))==API_SHA,'Frozen API closure')
    api.private_runner()
    diag=life.read_bound(DIAG,DIAG_SHA)
    wave=Path(diag['wave']);require(life.digest(wave)==diag['wave_sha256'],'Original first-rejection wave')
    bookpath=c.oracle.reused.old.BUILD/'build-source-pins.json'
    book=life.read_bound(bookpath,c.oracle.reused.old.SOURCE_SHA)
    anchors={
        'fpu_wrap.sv':("assign fpu_out_ready = 1'b1;",'assign fpu_valid_o = fpu_out_valid;'),
        'ex_stage.sv':('assign fpu_valid_o    = fpu_valid;','assign fpu_result_o   = fpu_result;'),
        'cva6.sv':('assign wt_valid_ex_id[FPU_WB] = fpu_valid_ex_id;',
            'assign wbdata_ex_id[FPU_WB]   = fpu_result_ex_id;'),
        'scoreboard.sv':('if (wt_valid_i[i] && mem_q[trans_id_i[i]].issued)',
            'mem_n[trans_id_i[i]].sbe.result = wbdata_i[i];'),
    }
    pins={str(DIAG):DIAG_SHA,str(wave):diag['wave_sha256'],str(bookpath):c.oracle.reused.old.SOURCE_SHA}
    for name,needles in anchors.items():
        path=life.ROOT/'hardware/deps/cva6/core'/name
        require(life.digest(path)==book[str(path)] and all(n in path.read_text() for n in needles),
            'Frozen dedicated FPU output/consumer source')
        pins[str(path)]=book[str(path)]
    return dict(pins=pins,policy='Consume exact accepted output at flush edge first; no other live or held owner may remain.')


def owner_implementation():
    source_proof()
    tree=ast.parse(inspect.getsource(c.owner_implementation));found=0
    for node in ast.walk(tree):
        if isinstance(node,ast.Assign) and any(ast.unparse(t)=='blocks[0].body' for t in node.targets):
            require(ast.unparse(node.value)=='ast.parse(literal.value).body','Unique frozen flush literal installation')
            node.value=ast.parse('install_policy(literal.value)',mode='eval').body;found+=1
    require(found==1,'One exact flush policy site')
    def install_policy(text):
        policy=ast.parse(text);matches=[]
        for node in ast.walk(policy):
            if isinstance(node,ast.Compare) and ast.unparse(node)=="root('fpu_valid_o') == 0":matches.append(node)
        require(len(matches)==1,'Only original output-empty gate rewritten after strict consumption')
        class Replace(ast.NodeTransformer):
            def visit_Compare(self,node):
                if node is matches[0]:return ast.BoolOp(op=ast.Or(),values=[node,ast.Name(id='output_consumed',ctx=ast.Load())])
                return self.generic_visit(node)
        return ast.parse(PREFIX).body+Replace().visit(policy).body
    ns=dict(c.owner_implementation.__globals__,install_policy=install_policy)
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),ns)
    return ns['owner_implementation']()


def audit_edges(decl,edges,expected,proof):return owner_implementation()(decl,edges,expected,proof)


def wave_audit(path,proof,pre):
    return FunctionType(c.frozen.wave_audit.__code__,dict(c.frozen.wave_audit.__globals__,
        probe_widths=c.probe_widths,expected_requests=c.expected_requests,audit_edges=audit_edges))(path,proof,pre)


def authority():
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_collect_scalar_c910_pattern795_v3.py').resolve())
    return life.merge_pins(life.merge_pins(api.authority(),source_proof()['pins']),{str(p):life.digest(p) for p in files})


def collect(run,out,seal):
    pins=authority();life.check(pins)
    FunctionType(c.collect.__code__,dict(c.collect.__globals__,runner=api.private_runner(),wave_audit=wave_audit))(run,out,seal)
    core=out/'qualification.json';sha=life.digest(core);q=life.read_bound(core,sha)
    require(q['status']=='FULL_SCALAR_C910_NORMAL224_NATIVE_QUALIFIED_NOT_ADMITTED'
        and q['baseline']==795 and q['coverage_admitted'] is False,'Full original core required')
    life.check(q['input_pins']);life.check(q['output_pins']);life.check(pins)
    life.save(out/'runner-flush-closure.json',dict(status='FULL_NORMAL224_API_FLUSH_OUTPUT_CLOSURE_NOT_ADMITTED',
        core_qualification=str(core),core_sha256=sha,input_pins=pins,source_proof=source_proof(),
        original_collector_sha256=api.COLLECTOR_SHA,original_runner_sha256=api.RUNNER_SHA,
        runner_api=sorted(api.EXPECTED_API),first_rejection_sha256=DIAG_SHA,
        policy='Same-edge valid/ready output completion before flush safety; scheduled cancel/reissue unchanged',
        original_gates_omitted=[],coverage_admitted=False,new_simulation=False))
    print('FULL_CLOSURE_NOT_ADMITTED',life.digest(out/'runner-flush-closure.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
