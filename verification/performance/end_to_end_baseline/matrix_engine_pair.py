"""Full-command checks for the matrix dot candidate; no checker relaxation."""
import re
import sys
from pathlib import Path

from audit import require
from matrix_dot_pair import candidate_vectors
from projection_resources import geometry

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'verification/qbs'))
from run_tile_context_engine import check_geometry,check_log,PATTERN


def adapt_wrapper(text):
    edits=(("    parameter bit SeedRestoreEnable = 1'b0,",
            "    parameter bit SeedRestoreEnable = 1'b0,\n    parameter bit WideMatrixDot = 1'b0,"),
           ('    .SeedRestoreEnable(SeedRestoreEnable),',
            '    .SeedRestoreEnable(SeedRestoreEnable),\n    .WideMatrixDot(WideMatrixDot),'))
    for old,new in edits:
        require(text.count(old)==1,'Wrapper anchor drift');text=text.replace(old,new,1)
    return text


def adapt_bench(text):
    edits=(('module qbs_engine_tb;',
            "module qbs_engine_tb #(parameter bit Wide = 1'b0);\n  initial $display(\"MATRIX_ENGINE_CONFIG wide=%0d\", Wide);"),
           ('  qbs_engine_composed #(', '  qbs_engine_composed #(\n    .WideMatrixDot(Wide),'))
    for old,new in edits:
        require(text.count(old)==1,'Bench anchor drift');text=text.replace(old,new,1)
    return text


def check_mode(text,vector,wide,gap,contexts,functional):
    shapes=geometry(vector);count=len(shapes)
    require(text.splitlines().count(f'MATRIX_ENGINE_CONFIG wide={wide}')==1,'Wrong elaborated width')
    require(not re.search(r'Fatal:|Error:|UVM_ERROR|UVM_FATAL',text),'RTL/testbench failure')
    if functional:
        require(contexts==0,'Functional case must not claim context coverage')
        require(text.splitlines().count(f'QBS configuration response_gap={gap} context_suite=0')==1,
                'Wrong memory schedule')
        require(text.splitlines().count(f'QBS engine PASS: {count} functional cases')==1,'Functional verdict')
        direct=[tuple(map(int,row)) for row in re.findall(PATTERN,text,re.M)]
        require(len(direct)==count and {r[0] for r in direct}==set(shapes),'Missing direct results')
        traffic=re.findall(r'^QBS traffic case=(\d+) weight=(\d+) activation=(\d+) payload=(\d+) '
                           r'ranges=(\d+) dot=(\d+) prefetch_wait=(\d+)$',text,re.M)
        require(len(traffic)==count,'Missing functional resource records')
        require([int(r[0]) for r in traffic]==list(shapes),'Traffic case order')
        for row in traffic:
            case,weights,acts,payload,ranges,dot,wait=map(int,row);s=shapes[case];c=s['counters']
            require((weights,acts,payload,dot)==(c[1],c[2],16+c[1]+c[2],c[5]),'Input work/counter mismatch')
        observed=dict(direct=direct,contexts=[],response_gap=gap)
    else:
        observed=check_log(text,count,contexts,gap)
        require(text.splitlines().count(f'QBS engine PASS: {count} functional cases plus four fault classes')==1,
                'Full suite was truncated')
        for kind in ('validation','MMU','AXI','PMA'):
            require(text.splitlines().count(f'QBS {kind} atomic-fault PASS')==1,'Missing fault class')
    check_geometry(vector,observed['direct'])
    require(all(row[-1]>0 for row in observed['direct']),'Invalid command latency')
    return observed


def pair(base,wide,base_vector,wide_vector,gap,contexts,functional):
    require(candidate_vectors(base_vector)==wide_vector,'Changed workload or reference outputs')
    b=check_mode(base,base_vector,0,gap,contexts,functional)
    c=check_mode(wide,wide_vector,1,gap,contexts,functional)
    require([r[:-1] for r in b['direct']]==[r[:-1] for r in c['direct']],'Direct work differs')
    require([r[:4] for r in b['contexts']]==[r[:4] for r in c['contexts']],'Context work differs')
    return dict(direct=[dict(case=x[0],profile=x[1],m=x[2],n=x[3],kb=x[4],
                             baseline_cycles=x[-1],candidate_cycles=y[-1],ratio=x[-1]/y[-1])
                        for x,y in zip(b['direct'],c['direct'])],
                contexts=[dict(case=x[0],m=x[1],kb=x[2],bytes=x[3],
                               baseline_fill=x[4],candidate_fill=y[4],
                               baseline_reuse=x[5],candidate_reuse=y[5])
                          for x,y in zip(b['contexts'],c['contexts'])],
                response_gap=gap,functional_only=functional)
