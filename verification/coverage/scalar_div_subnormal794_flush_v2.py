"""Offline-only cancellation audit; never mutates the frozen collector."""
import ast
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType

import collect_scalar_div_subnormal794 as old

OLD_SHA='cb4a6b8f0e57693090909c150ad0adb2447b474dfb25686edd711ff0dd53d751'
WAVE=old.life.OUT/'scalar-div-subnormal794-qualified-parent-20261008-01/probe.vcd'


def source_proof():
    life=old.life
    old.require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen original audit')
    book=life.read_bound(old.oracle.old.BUILD/'build-source-pins.json',old.oracle.old.SOURCE_SHA)
    pins={str(Path(old.__file__).resolve()):OLD_SHA}
    anchors={
        'hardware/deps/cva6/core/csr_regfile.sv':('riscv::CSR_FCSR: begin','fcsr_d[7:0] = csr_wdata[7:0];','flush_o = 1\'b1;'),
        'hardware/deps/cva6/core/controller.sv':('if (flush_csr_i || flush_acc_i) begin','flush_ex_o             = 1\'b1;'),
        'hardware/deps/cva6/core/cva6.sv':('.flush_ex_o            (flush_ctrl_ex)', '.flush_i(flush_ctrl_ex)'),
        'hardware/deps/cva6/core/ex_stage.sv':('.flush_i,',),
        'hardware/deps/cva6/core/fpu_wrap.sv':('if (flush_i) begin','state_d = READY;','.flush_i,'),
        'hardware/deps/cva6/core/issue_read_operands.sv':('if (flush_i) begin',"fpu_valid_n    = '0;",'fpu_valid_q    <= fpu_valid_n;'),
        'hardware/deps/fpnew/src/fpnew_noncomp.sv':('`FFLARNC(inp_pipe_valid_q[i+1], inp_pipe_valid_q[i], inp_pipe_ready[i], flush_i,',),
    }
    for rel,needles in anchors.items():
        p=life.ROOT/rel
        old.require(life.digest(p)==book[str(p)],'Frozen flush source closure')
        text=p.read_text();old.require(all(n in text for n in needles),'Flush source semantics')
        pins[str(p)]=book[str(p)]
    return dict(pins=pins,policy='Only one not-yet-accepted scheduled FMV canceled; reference cursor rewound; reissue required. Accepted/held owners never canceled.')


def audit_edges(decl,edges,expected,proof):
    source_proof()
    tree=ast.parse(inspect.getsource(old.audit_edges))
    blocks=[n for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=="root('flush_i')"]
    old.require(len(blocks)==1 and 'No flush during FPU owner' in ast.unparse(blocks[0]),'Exact original flush block')
    blocks[0].body=ast.parse('''
require(not live and pending is None and root('state_q')==0 and root('fpu_valid_o')==0 and
    gen('hold_inputs')==0 and gen('use_hold')==0 and read(before,ISSUE+'.fpu_valid_n')==0,
    'Flush cannot lose accepted or held output owner')
if scheduled is not None:
    require(root('fpu_valid_i')==1 and schedule_count==issued+1 and
        scheduled['pc']==expected[issued]['pc'] and expected[issued]['kind']=='FMV_X2F',
        'Only exact next-reference not-accepted FMV cancellation')
    require(operands(before,SCOPE+'.fu_data_i',expected[issued])==scheduled['fu'],
        'Canceled request exact used operands/op/TID')
    require(read(after,SCOPE+'.fpu_valid_i')==0 and read(after,SCOPE+'.state_q')==0,
        'Flush clears registered valid and hold state')
    cancellations.append(dict(time=time,pc=scheduled['pc'],tid=scheduled['fu']['trans_id'],reference_index=issued))
    schedule_count-=1
    scheduled=None
else:
    require(root('fpu_valid_i')==0,'Idle flush cannot hide unowned request')
idle_flush.append(time)
continue
''').body
    fn=tree.body[0]
    fn.body.insert(0,ast.parse('cancellations=[]').body[0])
    returns=[n for n in fn.body if isinstance(n,ast.Return)]
    old.require(len(returns)==1 and isinstance(returns[0].value,ast.Call),'Original complete audit return')
    returns[0].value.keywords.append(ast.keyword(arg='scheduled_cancellations',value=ast.Name(id='cancellations',ctx=ast.Load())))
    ns=dict(old.audit_edges.__globals__)
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),ns)
    return ns['audit_edges'](decl,edges,expected,proof)


def wave_audit(path,proof,pre):
    return FunctionType(old.wave_audit.__code__,dict(old.wave_audit.__globals__,audit_edges=audit_edges))(path,proof,pre)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();old.require(not args.output.exists(),'Exclusive fresh wave evidence')
    pre=old.life.read_bound(old.runner.PRE/'preflight.json',old.runner.PRE_SHA)
    result=wave_audit(WAVE,old.runner.source_contract(),pre)
    inputs=[WAVE,Path(__file__).resolve(),Path(__file__).with_name('test_scalar_div_subnormal794_flush_v2.py'),
        old.runner.PRE/'preflight.json',WAVE.parent/'scalar-comparison.json',WAVE.parent/'architecture-audit.json']
    pins=old.life.merge_pins(source_proof()['pins'],{str(p.resolve()):old.life.digest(p) for p in inputs})
    old.life.check(pins)
    old.life.save(args.output,dict(status='OFFLINE_WAVE_ONLY_NOT_FULL_QUALIFICATION',
        audit=result,source=source_proof(),input_pins=pins,coverage_admitted=False,RTL_changed=False,VCS_rerun=False))
    print('OFFLINE_WAVE_ONLY',old.life.digest(args.output),'owners',len(result['completed']),
        'DIV',len(result['table_observations']),'cancellations',len(result['scheduled_cancellations']))
