"""Immutable v2 successor: correct the actual tuple-list architecture contract."""
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_sv39_masked_unit_fault_terminal_v2 as v2

life,require=v2.life,v2.require
V2_SHA='82731a3a70afb83a20d697929532e9569bd9cf6a1d6c4a05a3df2305b2332da7'
MARK=dict(schema='MASKED_CAUSE13_TUPLE_OWNER_V3',arch_seq=243,
          predecessor_sha256=V2_SHA,global_checker_changed=False,zero_write_fault_claimed=False)


def architecture_owner(starts,rows,symbols):
    opcode=v2.p.WORDS['smuf_masked_load']
    require(type(starts) is list and all(type(x) is tuple and len(x)==2 and
            all(type(n) is int for n in x) for x in starts),'Actual tuple-list parser contract required')
    require([x for x in starts if x[0]==243]==[(243,opcode)],'Unique exact tuple owner required')
    owners=[r for r in rows if r['event']=='arch_start' and int(r['order'])==243]
    require(len(owners)==1,'Duplicate/missing native architecture owner')
    owner=owners[0]
    require(int(owner['insn'],16)==opcode and int(owner['trans_id'])==6 and
            int(owner['pc'],16)==0 and int(owner['trap'])==0,'Native owner opcode/transaction/schema differs')
    # This monitor emits zero PC for arch_start/CVX. Fault EPC is bound by
    # v2's scalar-aligned cause13 CSR proof, not invented from that zero field.
    require(symbols['smuf_masked_load']==0x80002268,'Sealed fault PC differs')
    pending=None;seen=[]
    for row in rows:
        if int(row['trans_id'])!=6:continue
        if row['event']=='arch_start':pending=int(row['order'])
        elif row['event']=='cvx_req' and pending==243:
            require(int(row['insn'],16)==opcode and int(row['pc'],16)==0,'Fault request differs')
            seen.append('request')
        elif row['event']=='cvx_resp':
            if pending==243:
                require(int(row['trap'])==1 and int(row['pc'],16)==int(row['insn'],16)==0,
                        'Fault response differs')
                seen.append('exception')
            pending=None
        elif row['event'] in ('uop_alloc','uop_done') and int(row['order'])==243:
            require(int(row['insn'],16)==opcode and int(row['pc'],16)==0,'Backend owner differs')
    require(seen==['request','exception'],'Exact transaction request/exception pair required')
    return True


def comparator():
    require(life.digest(Path(v2.__file__))==V2_SHA,'Frozen v2 drift')
    source=inspect.getsource(v2.compare_with_proof)
    needle='ARCH in starts'
    require(source.count(needle)==1,'Unexpected predecessor source shape')
    namespace=dict(v2.compare_with_proof.__globals__,architecture_owner=architecture_owner)
    exec(compile(source.replace(needle,'architecture_owner(starts,rows,symbols)'),
                 str(Path(__file__).resolve())+':private-v2','exec'),namespace)
    return namespace['compare_with_proof']


def dependencies():
    return (Path(v2.__file__).resolve(),Path(v2.__file__).with_name('test_qualify_sv39_masked_unit_fault_terminal_v2.py'),
            Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_masked_unit_fault_terminal_v3.py'))


def prepare(output):
    comparator()
    v2.old.prepare(v2.RUN,v2.RUN_SEAL,output)
    plan=json.loads((output/'plan.json').read_bytes())
    plan['pins']=life.merge_pins(plan['pins'],{str(x):life.digest(x) for x in dependencies()})
    plan['fault_successor']=MARK
    life.check(plan['pins']);life.save(output/'successor-plan.json',plan)
    print(json.dumps(dict(plan=str(output/'successor-plan.json'),seal=life.digest(output/'successor-plan.json'),VCS_started=False)))


def verify(planpath,seal):
    plan=life.read_bound(planpath,seal)
    require(plan.get('fault_successor')==MARK and plan['run']==str(v2.RUN) and
            plan['prepared_seal']==v2.RUN_SEAL,'Exact v3 case plan required')
    require(all(plan['pins'].get(str(x))==life.digest(x) for x in dependencies()),'Successor dependency drift')
    life.check(plan['pins']);comparator()


def collect(planpath,seal,output):
    verify(planpath,seal)
    private=FunctionType(v2.old.collect.__code__,dict(v2.old.collect.__globals__,
        vc=SimpleNamespace(compare_vector_commits=comparator())),v2.old.collect.__name__,v2.old.collect.__defaults__)
    private(planpath,seal,output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','collect'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--seal')
    a=parser.parse_args()
    if a.mode=='prepare':require(a.output,'Output required');prepare(a.output.absolute())
    else:
        require(a.plan and a.seal,'Plan/seal required')
        if a.mode=='verify':verify(a.plan.absolute(),a.seal);print('VERIFY_PASS NO_VCS')
        else:require(a.output,'Output required');collect(a.plan.absolute(),a.seal,a.output.absolute())


if __name__=='__main__':main()
