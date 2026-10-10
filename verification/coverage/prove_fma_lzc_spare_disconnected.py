"""Bound complete RTL reference audit; unused structure, not a known-zero/X proof."""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
import prove_fma_lzc_binary_tree as original

require=original.require
SOURCE=original.ROOT/'hardware/deps/common_cells/src/lzc.sv'


def arithmetic(expression, variables):
    def walk(node):
        if isinstance(node,ast.Constant) and type(node.value) is int:return node.value
        if isinstance(node,ast.Name) and node.id in variables:return variables[node.id]
        if isinstance(node,ast.BinOp):
            a,b=walk(node.left),walk(node.right)
            if isinstance(node.op,ast.Add):return a+b
            if isinstance(node.op,ast.Sub):return a-b
            if isinstance(node.op,ast.Mult):return a*b
            if isinstance(node.op,ast.Pow):
                require(0<=b<=16,'Bounded constant exponent');return a**b
        require(False,'Unsupported source index arithmetic')
    return walk(ast.parse(expression,mode='eval').body)


def references(text):
    # Restricted parser only for the hash-bound simple continuous-assign module.
    # Every identifier occurrence must be classified; whole-array reads fail closed.
    token=r'\b(sel_nodes|index_nodes)\b'
    indexed=re.compile(token+r'\s*\[([^\]]+)\]')
    records=[];covered=Counter()
    for match in re.finditer(r'\blogic\s+([^;]+);',text):
        for name in re.findall(token,match.group(0)):
            covered[name]+=1
            records.append(dict(signal=name,role='declaration',line=text[:match.start()].count('\n')+1))
    for match in re.finditer(r'\bassign\s+(.+?)\s*=\s*(.+?);',text,re.S):
        for role,body in (('write',match.group(1)),('read',match.group(2))):
            indexed_names=[]
            for m in indexed.finditer(body):
                name,expr=m.groups();covered[name]+=1;indexed_names.append(name)
                records.append(dict(signal=name,role=role,expression=expr.strip(),
                    line=text[:match.start()].count('\n')+1))
            require(Counter(re.findall(token,body))==Counter(indexed_names),'Whole/unclassified tree access')
    require(covered==Counter(re.findall(token,text)),'Tree reference outside audited declarations/continuous assignments')
    require(Counter((r['signal'],r['role']) for r in records)==Counter({
        ('sel_nodes','declaration'):1,('index_nodes','declaration'):1,
        ('sel_nodes','write'):4,('index_nodes','write'):4,
        ('sel_nodes','read'):4,('index_nodes','read'):3}), 'Complete reference inventory changed')
    return records


def prove(width,records):
    require(width in (25,51,109),'Matched widths only')
    levels=(width-1).bit_length();size=1<<levels;reads=set();writes=set();details=[]
    for record in records:
        if record['role']=='declaration':continue
        expr=record['expression'];names={n.id for n in ast.walk(ast.parse(expr,mode='eval')) if isinstance(n,ast.Name)}
        if names=={'level','k'}:
            envs=[dict(level=levels-1,k=k) for k in range(1<<(levels-1))]
        elif names=={'level','l'}:
            envs=[dict(level=level,l=lane) for level in range(levels-1) for lane in range(1<<level)]
        else:
            require(not names,'Unknown generate variable/domain');envs=[{}]
        values={arithmetic(expr,e) for e in envs}
        require(values and min(values)>=0 and max(values)<=size-2,'Spare is referenced or index out of range')
        (reads if record['role']=='read' else writes).update(values)
        details.append(dict(record,minimum=min(values),maximum=max(values),distinct_indices=len(values)))
    require(writes==set(range(size-1)) and reads==set(range(size-1)), 'Assigned/read heap coverage differs')
    return dict(WIDTH=width,levels=levels,size=size,spare_index=size-1,spare_read_count=0,spare_write_count=0,
                all_read_indices=[0,size-2],all_written_indices=[0,size-2],references=details)


def evidence():
    require(original.calibration.digest(SOURCE)==original.calibration.SOURCE_SHA,'Frozen LZC source drift')
    static=original.calibration.bound(original.STATIC,original.STATIC_SHA)
    for path,sha in static['pins'].items():require(original.calibration.digest(path)==sha,'Static binding drift')
    text=SOURCE.read_text();records=references(text)
    for anchor in ("unsigned'(level) < NumLevels", "unsigned'(level) == NumLevels - 1",
                   'k < 2 ** level', 'l < 2 ** level'):
        require(anchor in text,'Generate iteration domain changed')
    proofs={w:prove(w,records) for w in (25,51,109)}
    objects=[]
    for instance in static['instances']:
        width=instance['parameters']['WIDTH'];p=proofs[width]
        require(instance['parameters']['MODE']==1 and instance['parameters']['CNT_WIDTH']==p['levels'], 'Elaborated parameters')
        objects.append(dict(scope=instance['scope'],module_checksum=instance['module_checksum'],
            toggle_checksum=instance['toggle_checksum'],WIDTH=width,
            selector=dict(name='gen_lzc.sel_nodes',bit=p['spare_index']),
            index=dict(name='gen_lzc.index_nodes',row=p['spare_index'],bits=[p['levels']-1,0]),
            logical_bits=1+p['levels']))
    require(len(objects)==32 and sum(o['logical_bits'] for o in objects)==212,'Exact spare boundary')
    pins={str(SOURCE):original.calibration.SOURCE_SHA,str(original.STATIC):original.STATIC_SHA}
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_prove_fma_lzc_spare_disconnected.py')):
        pins[str(path)]=original.calibration.digest(path)
    return dict(status='EXACT212_SPARE_DISCONNECTED_SOURCE_PROOF_ONLY_NOT_NATIVE_APPROVED',
        source_reference_inventory=records,width_proofs=list(proofs.values()),objects=objects,pins=pins,
        proof='Internal reads at levels0..L-2 use left child2**(level+1)-1+2*l and right child+1. Maximum right at levelL-2,l=2**(L-2)-1 equals2**L-2. Outputs read only index0. Leaf RHS reads in_tmp/index_lut, never spare. All tree identifier occurrences accounted for.',
        value_assumption='None: spare may be0/1/X/Z; structural absence of RTL fanout makes its value irrelevant to all assigned nodes and ports',
        outputs_retained=['in_i','cnt_o','empty_o'],
        current_candidate_modified=False,current_native_job_modified=False,
        spare_bits_counted_or_excluded=False,EDA_launched=False,
        scope_limit='Only exact32 frozen lzc instances; coverage instrumentation itself is not functional RTL fanout. No claim about other lzc implementations or arbitrary hierarchical testbench deposits.',
        future_gate='Only a reviewed successor may consume this unused-structure rationale; do not add212 to the live assigned-only capture or count a native exclusion before roundtrip.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output.resolve()
    require(out.parent==original.ROOT/'verification/out' and not out.exists(),'Fresh static output only')
    result=evidence()
    with out.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(original.calibration.digest(out))
