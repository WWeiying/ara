#!/usr/bin/env python3
"""Strict offline recheck of the two scalar-move policy rejects; no hooks/EDA."""
import argparse
import json
from pathlib import Path
import signal
import current_random_trace_replay as original

require = original.require
v = original.vector_api


def scalar_move_to_f0(instruction):
    return instruction & 0xfe0fffff == 0x42001057


def audit_byte(activity, item, register, byte, value, pre, reference, unknown, vlen):
    if register not in item.vector_writes:
        require(value is not None and register in pre and
                value == ((pre[register] >> (8*byte)) & 255),
                'Unproven transport/preservation write')
        return 'PRESERVED'
    require(all(x is not None for x in (item.vector_tail_agnostic,item.vector_mask_agnostic,
                item.vector_vl,item.vector_vstart)), 'Missing ISA tail/mask/vl/vstart policy')
    if v._uses_mask_predicate(activity.instruction):
        require(0 in pre, 'Unproven predicate state')
    mask = v._architectural_compare_mask(activity,register,byte,vlen,pre,
        item.vector_writes.keys(),item.vector_vl,item.vector_vstart,
        item.vector_tail_agnostic,item.vector_mask_agnostic)
    mask &= ~((unknown.get(register,0) >> (byte*8)) & 255)
    return original.require_known_active(value,mask,register in reference)


def unknown_audit(spike,commit,vector,entry,compared):
    lanes,vlen,activities = v._parse_vector_trace(vector)
    starts,retires,traps = v._parse_architecture_mapping(commit)
    arch = v._map_architecture_retires(starts,retires,traps,allow_incomplete_tail=False)
    commits = v._spike_from_entry(spike,entry)
    mapping = v._map_spike_commits(arch,commits)
    by_spike = {idx:(seq,activities[seq]) for seq,idx in mapping.items() if seq in activities}
    compared_indices = {mapping[x['arch_seq']] for x in compared['instructions']}
    reference,unknown = {},{}
    checked,masked,unknown_actual,preserved = 0,0,0,0
    special = []
    for idx,item in enumerate(commits):
        pre=dict(reference)
        reference.update(item.vector_writes)
        pair=by_spike.get(idx)
        if pair is None:continue
        seq,activity=pair
        v._advance_unknown_state(unknown,activity,item,pre,vlen)
        if idx not in compared_indices:continue
        count=0
        for (reg,byte),(value,write) in v._architectural_bytes(activity.writes,lanes,vlen).items():
            classification=audit_byte(activity,item,reg,byte,value,pre,reference,unknown,vlen)
            if classification=='ISA_UNKNOWN':masked+=1
            else:checked+=1
            if classification=='PRESERVED':preserved+=1;count+=1
            unknown_actual+=int(value is None)
        if count and any(x is None for x in (item.vector_tail_agnostic,item.vector_mask_agnostic,
                                             item.vector_vl,item.vector_vstart)):
            require(not item.vector_writes and scalar_move_to_f0(item.instruction),
                    'Unexpected policy-free transport instruction')
            special.append(dict(arch_seq=seq,pc=hex(item.pc),instruction=hex(item.instruction),
                scalar_fpr_writes=item.fpr_writes,preservation_bytes=count,
                vector_destination_registers=[],policy_required=False,
                proof='every accepted byte known and exactly equal to prior architectural state'))
    require(len(special)==1 and special[0]['preservation_bytes']==128,
            'Expected one exact 128-byte scalar-move preservation witness')
    return dict(status='PASS',known_active_bytes=checked,isa_unconstrained_bytes=masked,
        unknown_writeback_bytes=unknown_actual,unproven_active_unknown_bytes=0,
        preservation_bytes=preserved,policy_free_preservation=special,
        policy='policy required for every architectural destination byte; transport bytes strictly preserved')


def replay(profile,code):
    previous=signal.signal(signal.SIGALRM,original.deadline_expired)
    signal.alarm(300)
    try:
        with original.admission.old.no_tools():
            seal=original.admission.FileSeal()
            seal.hashes(code)
            seal.hashes(profile['input_sha256'])
            a=Path(profile['artifact']);m=profile['elf_metadata']
            for log in (a/'rtl_console.log',a/'run.vcs.log'):
                text=log.read_text(errors='replace')
                require(text.count('Core Test *** SUCCESS ***')==1 and not original.re.search(
                    r'Fatal:|Error:|commit watchdog|Core Test \*\*\* FAIL',text,original.re.I),
                    'Runtime log is not complete PASS')
                require(not original.check_contract_log(log),'Contract runtime violation')
            spike,commit,vector=a/'spike_commit.log',a/'ara_commit_trace.csv',a/'ara_vector_trace.csv'
            unobservable=v.unobservable_vector_scalar_write_indices(spike,commit,vector,m['entry'])
            fault=bool(profile['case'].get('fault_vstart_probe'))
            scalar=original.scalar_api.compare_commit_prefix(spike,commit,m['entry'],unobservable,
                terminal_ecall_pc=m['exit_pc'],terminal_tohost_address=m['tohost'],
                rtl_exception_log=Path(profile['exception_log']) if profile['exception_log'] else None,
                fault_vector_trace=vector if fault else None,fault_probe_log=a/'run.vcs.log' if fault else None)
            compared=v.compare_vector_commits(spike,commit,vector,m['entry'],
                aligned_vector_faults=scalar.get('aligned_vector_faults'),
                fault_probe_log=a/'run.vcs.log' if fault else None)
            original.strict_verdict(scalar,compared)
            require(not original._load_fault_evidence_errors(a,scalar,compared),'Fault proof binding failed')
            trace=dict(status='VALID',**original.validate_trace(commit))
            unknown=unknown_audit(spike,commit,vector,m['entry'],compared)
            obligations=original.read_coverage_obligations(profile,scalar)
            seal.finish()
            return dict(status='PASS_DIAGNOSTIC_ONLY',name=profile['name'],vdb=profile['vdb'],
                scalar=scalar,vector=compared,trace=trace,unknown_audit=unknown,obligations=obligations,
                input_sha256=profile['input_sha256'],current_checker_sourcepins=code,
                historical_checker_pins=profile['historical_checker_pins'],
                admitted687=False,application_approval=False,simulation_rerun=False)
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original',required=True,type=Path)
    p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();source=a.original.resolve(strict=True);out=a.output.absolute()
    require(source.parent==original.OUT and out.parent.resolve()==original.OUT and not out.exists(),
            'Independent fresh output required')
    manifest=source/'manifest.json'
    require(original.admission.sha_bytes(manifest.read_bytes())==a.manifest_sha256,'Original manifest drift')
    prepared=original.json_read(manifest)
    code=dict(prepared['current_checker_sourcepins'])
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_recheck_random_policy_sidecar.py'),manifest):
        code[str(path)]=original.admission.sha_bytes(path.read_bytes())
    selected=[]
    for cid,seed in [('067',820),('122',1115)]:
        oldpath=source/'cases'/f'{cid}.json';old=original.json_read(oldpath)
        require(old['status']=='FAILED_DIAGNOSTIC_ONLY' and old['reason']==
                'ValueError: Missing ISA tail/mask/vl/vstart policy','Unexpected original rejection')
        found=[x for x in prepared['profiles'] if x['name']==old['name'] and x['case']['seed']==seed]
        require(len(found)==1 and found[0]['vdb']==old['vdb'],'Original profile binding differs')
        code[str(oldpath)]=original.admission.sha_bytes(oldpath.read_bytes())
        selected.append((cid,found[0]))
    diagnostic=source/'diagnostic.json'
    code[str(diagnostic)]=original.admission.sha_bytes(diagnostic.read_bytes())
    seal=original.admission.FileSeal();seal.hashes(code);seal.finish()
    out.mkdir()
    try:
        for cid,profile in selected:
            result=replay(profile,code)
            with (out/f'{cid}.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        seal=original.admission.FileSeal();seal.hashes(code);seal.finish()
        with (out/'status.json').open('x') as f:
            json.dump(dict(status='TWO_POLICY_REJECTS_RECHECKED_PASS_DIAGNOSTIC_ONLY',passed=2,
                original_201_results_unchanged=True,original=str(source),sourcepins=code,
                admitted687=False,application_approval=False,simulation_rerun=False),f,indent=2);f.write('\n')
    except Exception as error:
        with (out/'status.json').open('x') as f:json.dump(dict(status='FAIL',reason=f'{type(error).__name__}: {error}'),f,indent=2)
        raise


if __name__=='__main__':main()
