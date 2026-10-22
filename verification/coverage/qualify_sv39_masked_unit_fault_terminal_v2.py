"""Case-only cause13 identity-maintenance proof; unchanged global comparators."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import qualify_sv39_masked_unit_fault_terminal as old
from ara_verify import vector_commit as vc

life,p,require=old.life,old.p,old.require
OLD_SHA='227628bf25a30eed80b2a21740cc714cafc56353081d01d3e986d3c9a7778416'
RUN=life.OUT/'sv39-masked-unit-fault-old-image-parent-20261006-01'
RUN_SEAL='1cef43f38496b540d1ed2391c25765a2535bdabb6564fd7e9a8701a6428b4a4a'
ELF_SHA='dc750cc776a77b0fd8a9cef50173aced42b7bce9b16c758f5f64a6adc90aba90'
ARCH=243


def signature(activity):
    return hashlib.sha256(json.dumps(asdict(activity),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def native_identity(activity,rows):
    require(activity.instruction==p.WORDS['smuf_masked_load'] and activity.allocations==activity.completions==2 and
            activity.use_vd is True and (activity.vd,activity.eew,activity.vl,activity.vstart)==(8,0,17,0),
            'Exact two-uop masked fault activity required')
    control=[r for r in rows if r['event']!='write']
    require([r['event'] for r in control]==['alloc','done','alloc','done'] and
            [int(r['vl']) for r in control]==[128,128,17,17], 'Maintenance then load lifecycle required')
    require(all(int(r['arch_seq'])==ARCH and int(r['vid'])==0 and int(r['insn'],16)==activity.instruction and
                (int(r['use_vd']),int(r['vd']),int(r['eew']),int(r['vstart']))==(1,8,0,0) and
                (int(r['nr_lanes']),int(r['vlen_bits']))==(4,1024) for r in rows),
            'Native fault scope/owner/shape differs')
    a,b,c,d=[int(r['cycle']) for r in control]
    require(a<=b<c<=d,'Maintenance/load interval overlap')
    maintenance=[w for w in activity.writes if w.source==3]
    loads=[w for w in activity.writes if w.source==4]
    require(len(activity.writes)==20 and len(maintenance)==16 and len(loads)==4,
            'Exact complete maintenance plus four zero-BE load rows required')
    require({(w.addr,w.lane) for w in maintenance}=={(addr,lane) for addr in range(32,36) for lane in range(4)} and
            all(w.arch_seq==ARCH and w.vid==0 and w.instruction==activity.instruction and w.eew==0 and
                w.be==255 and w.known_be==255 and a<=w.cycle<=b for w in maintenance),
            'Missing/duplicate/unknown/out-of-window reshuffle byte')
    require({w.lane for w in loads}==set(range(4)) and all(w.arch_seq==ARCH and w.vid==0 and
            w.instruction==activity.instruction and w.eew==0 and w.be==0 and c<=w.cycle<=d for w in loads),
            'Faulting VLDU has accepted bytes or invalid owner/window')
    require(len([r for r in rows if r['event']=='write'])==20,'Dropped/extra native write row')
    actual=vc._architectural_bytes(maintenance,4,1024)
    expected={(8,byte):(p.word(1,byte//4,False)>>(8*(byte%4)))&255 for byte in range(128)}
    require(set(actual)==set(expected) and all(actual[k][0]==value for k,value in expected.items()),
            'Complete port3 E32-to-E8 maintenance is not independent seed identity')
    return dict(status='EXACT_CAUSE13_MASKED_FAULT_IDENTITY_RESHUFFLE_AND_ZERO_VLDU_PROVED',
        arch_seq=ARCH,opcode=hex(activity.instruction),maintenance_source=3,maintenance_events=16,
        maintenance_known_bytes=128,load_source=4,load_events=4,load_accepted_bytes=0,
        activity_signature=signature(activity),whole_DUT_fault_snapshot_required=True,
        case_only=True,zero_write_fault_claimed=False)


def authorized_fault(activity,commit,fault,proof):
    require(proof['case_only'] is True and proof['arch_seq']==ARCH and proof['maintenance_known_bytes']==128 and
            proof['load_accepted_bytes']==0 and proof['zero_write_fault_claimed'] is False,'Invalid case-only proof')
    return (signature(activity)==proof['activity_signature'] and
        commit.instruction==p.WORDS['smuf_masked_load'] and commit.pc==proof['fault_pc'] and
        commit.vector_sew==8 and commit.vector_vl==17 and commit.vector_vstart==0 and
        commit.vector_lmul=='m1' and commit.vector_vtype==0 and
        commit.vector_tail_agnostic is False and commit.vector_mask_agnostic is False and
        not (commit.gpr_writes or commit.fpr_writes or commit.vector_writes or commit.memory_accesses) and
        commit.csr_writes=={8:0} and fault['pc']=='0x%016x'%commit.pc and
        fault['instruction']=='0x%08x'%commit.instruction and fault['fault_handler_returned'] is True and
        not fault.get('invalidated_fault_csrs') and
        fault['matched_fault_csrs']=={'0x341':commit.pc,'0x342':13,'0x343':0x40000300})


def compare_with_proof(spike,commit,vector,entry,aligned_vector_faults=None,**kwargs):
    require(Path(spike)==old.runner.PRE/'spike.trace' and Path(commit)==RUN/'commit_trace.csv' and
            Path(vector)==RUN/'vector_trace.csv' and entry==0x80000000 and not kwargs,
            'Only exact sealed case/full-stream comparison permitted')
    manifest=life.read_bound(RUN/'manifest.json',RUN_SEAL)
    require(manifest['elf_sha256']==ELF_SHA,'Wrong sealed case ELF')
    pre=life.read_bound(old.runner.PRE/'preflight-manifest.json',old.runner.PRE_SEAL)
    symbols=pre['symbols']
    reference,partial=old.reference_prefix(p.shared.parse_spike_commits(spike),symbols)
    fault=aligned_vector_faults or []
    require(len(fault)==1 and fault[0]['index']==partial,'Exact scalar-validated fault index required')
    rows=old.common.read_csv(Path(commit).read_bytes(),old.common.COMMIT_FIELDS)
    gold=old.observed_gold(rows,symbols)
    require(gold['independent_gold_bytes']==19460 and gold['whole_mask_tail_guards'] is True,
            'Whole fault snapshot/source/CSR/page/guard evidence required')
    native=old.common.read_csv(Path(vector).read_bytes(),old.common.VECTOR_FIELDS)
    lanes,bits,activities=vc._parse_vector_trace(Path(vector))
    starts,retires,rejected=vc._parse_architecture_mapping(Path(commit))
    require((lanes,bits)==(4,1024) and rejected=={ARCH} and ARCH in activities and ARCH in starts,
            'Exact sole native rejected masked architecture required')
    proof=native_identity(activities[ARCH],[r for r in native if int(r['arch_seq'])==ARCH])
    proof.update(fault_pc=symbols['smuf_masked_load'],whole_fault_snapshot=gold)
    require(authorized_fault(activities[ARCH],reference[partial],fault[0],proof),
            'Exact reference partial/cause/tval/EPC/return contract differs')
    def permit(activity,committed,aligned):
        if authorized_fault(activity,committed,aligned,proof):return True
        return vc._known_identity_load_fault(activity,committed,aligned)
    # Only the private predicate is extended after the complete case proof.
    # The original comparator still maps and verifies every accepted byte,
    # prestate/unknown mask, trap accounting, and all 105 normal writers.
    private=FunctionType(vc.compare_vector_commits.__code__,
        dict(vc.compare_vector_commits.__globals__,_known_identity_load_fault=permit),
        vc.compare_vector_commits.__name__,vc.compare_vector_commits.__defaults__)
    result=private(spike,commit,vector,entry,aligned_vector_faults=fault)
    require(result['status']=='PASS' and result['verified_identity_write_traps']==
            [dict(arch_seq=ARCH,compared_bytes=128)] and result['verified_zero_write_traps']==[] and
            result['verified_trapped_destination_requests']==[ARCH] and result['trapped_requests']==[ARCH] and
            result['compared_instructions']==105 and result['compared_bytes']==13321 and
            not result['unretired_requests'] and not result['incomplete_requests'] and
            result['skipped_unknown_bytes']==result['non_bit_exact_instructions']==result['unobservable_instructions']==0 and
            result['first_mismatch'] is None,'Complete comparator/identity result differs')
    result['case_only_fault_proof']=proof
    return result


def prepare(output):
    require(life.digest(Path(old.__file__))==OLD_SHA,'Frozen predecessor drift')
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(),'Fresh successor plan')
    old.prepare(RUN,RUN_SEAL,output)
    plan=json.loads((output/'plan.json').read_bytes())
    deps=(Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_masked_unit_fault_terminal_v2.py'))
    plan['pins']=life.merge_pins(plan['pins'],{str(x):life.digest(x) for x in deps})
    plan['fault_successor']=dict(schema='MASKED_CAUSE13_IDENTITY_PROOF_V1',arch_seq=ARCH,
        original_helper_sha256=OLD_SHA,global_checker_changed=False,zero_write_fault_claimed=False)
    life.check(plan['pins']);life.save(output/'successor-plan.json',plan)
    print(json.dumps(dict(plan=str(output/'successor-plan.json'),seal=life.digest(output/'successor-plan.json'),VCS_started=False)))


def collect(planpath,seal,output):
    plan=life.read_bound(planpath,seal)
    require(plan.get('fault_successor')==dict(schema='MASKED_CAUSE13_IDENTITY_PROOF_V1',arch_seq=ARCH,
        original_helper_sha256=OLD_SHA,global_checker_changed=False,zero_write_fault_claimed=False),
        'Reviewed case-only successor plan required')
    require(plan['run']==str(RUN) and plan['prepared_seal']==RUN_SEAL and
            all(plan['pins'].get(str(x))==life.digest(x) for x in
                (Path(__file__).resolve(),Path(__file__).with_name('test_qualify_sv39_masked_unit_fault_terminal_v2.py'))),
            'Successor source/test binding differs')
    private=FunctionType(old.collect.__code__,dict(old.collect.__globals__,
        vc=SimpleNamespace(compare_vector_commits=compare_with_proof)),old.collect.__name__,old.collect.__defaults__)
    private(planpath,seal,output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','verify','collect'))
    parser.add_argument('--output',type=Path);parser.add_argument('--plan',type=Path);parser.add_argument('--seal')
    a=parser.parse_args()
    if a.mode=='prepare':require(a.output,'Fresh output required');prepare(a.output.absolute())
    elif a.mode=='collect':
        require(a.output and a.plan and a.seal,'Exact plan/seal/fresh result required')
        collect(a.plan.absolute(),a.seal,a.output.absolute())
    else:
        require(a.plan and a.seal,'Plan/seal required');plan=life.read_bound(a.plan,a.seal);life.check(plan['pins'])
        print('VERIFY_PASS NO_VCS NO_COLLECTION')


if __name__=='__main__':main()
