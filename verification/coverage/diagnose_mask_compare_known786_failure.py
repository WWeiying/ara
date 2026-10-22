"""Read-only architectural first-error evidence, not qualification or coverage."""
import argparse
import json
from pathlib import Path
import subprocess
import collect_mask_compare_restart_known786 as frozen

life,require=frozen.life,frozen.require
RUN=life.OUT/'mask-compare-restart-known-old-image786-agent-20261008-01'
FAILED=life.OUT/'mask-compare-restart-known-qualified786-parent-20261008-01/failure.json'
SEAL='de05bbfff9d5fee5b3c582e734d0a80801b351e8f30e02e24346110d00e2eca5'
CONVERTER=Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')


def diagnose(out):
    require(out.parent==life.OUT and not out.exists(),'Fresh independent diagnostic output')
    prepared=RUN.with_name(RUN.name+'.prepared.json')
    manifest=life.read_bound(prepared,SEAL); life.check(manifest['pins'])
    status=frozen.terminal(RUN,manifest)
    pins=life.merge_pins(manifest['pins'],{str(prepared):SEAL,str(FAILED):life.digest(FAILED),
        str(Path(__file__).resolve()):life.digest(Path(__file__)),str(CONVERTER):life.digest(CONVERTER)})
    for name in ('console.log','run.vcs.log','simulation-status.json','manifest.json','started.json',
                 'live-simv-identity.json','commit_trace.csv','vector_trace.csv','trace_hart_0.log','mask-compare-known.vpd'):
        path=RUN/name; pins[str(path)]=life.digest(path)
    pre=frozen.runner.preflight(); reference=frozen.reference_prefix(pre)
    out.mkdir()
    scalar=frozen.common.spike_trace.compare_commit_prefix(Path(pre['reference']),RUN/'commit_trace.csv',0x80000000,
        terminal_tohost_address=pre['symbols']['tohost'],rtl_exception_log=RUN/'trace_hart_0.log',
        rvfi_store_data_layout='unshifted')
    life.save(out/'scalar-comparison.json',scalar)
    vc=frozen.vc
    lanes,vlen,activities=vc._parse_vector_trace(RUN/'vector_trace.csv')
    starts,retires,rejected=vc._parse_architecture_mapping(RUN/'commit_trace.csv')
    require((lanes,vlen)==(4,1024) and not rejected,'Native geometry/rejections')
    arch=vc._map_architecture_retires(starts,retires,rejected)
    mapping=vc._map_spike_commits(arch,reference)
    rows=frozen.common.read_csv((RUN/'vector_trace.csv').read_bytes(),frozen.common.VECTOR_FIELDS)
    state={}; cases=[]; strict_writers=[]; unknown=[]
    for seq,index in sorted(mapping.items()):
        commit=reference[index]; activity=activities.get(seq)
        if activity is None or not activity.writes: continue
        for w in activity.writes:
            if w.be&~w.known_be: unknown.append(dict(arch_seq=seq,row=w.row,be=w.be,known_be=w.known_be))
        actual=vc._architectural_bytes(activity.writes,4,1024)
        before=dict(state)
        for (reg,b),(value,_) in actual.items():
            require(value is not None,'Unknown accepted byte: diagnostic cannot invent prestate')
            state[reg]=(state.get(reg,0)&~(255<<(8*b)))|(value<<(8*b))
        if commit.pc==pre['symbols']['mc_compare']:
            case=len(cases); start=frozen.p.STARTS[case]
            old=before.get(1); after=state.get(1)
            require(old is not None and after is not None,'Missing native old-vd')
            gold=int.from_bytes(frozen.p.mask_gold(start),'little')
            allocated=[r for r in rows if r['event']=='alloc' and int(r['arch_seq'])==seq]
            require(len(allocated)==1,'Exact native compare allocation')
            entry=dict(case=case,vstart=start,arch_seq=seq,pc=hex(commit.pc),opcode=hex(commit.instruction),
                actual_context=allocated[0],write_cycle_first=min(w.cycle for w in activity.writes),
                write_cycle_last=max(w.cycle for w in activity.writes),
                old_v1_full_hex='%0256x'%old,new_v1_full_hex='%0256x'%after,
                old_v1_matches_seed=old==int.from_bytes(frozen.p.old_bytes(0),'little'),
                v2_matches_seed=before.get(2)==int.from_bytes(frozen.p.old_bytes(1),'little'),
                expected_low64='%016x'%gold,actual_low64='%016x'%(after&((1<<64)-1)),
                prestart_wrong_bits=[i for i in range(start) if (old^after)>>i&1],
                active_wrong_bits=[i for i in range(start,64) if (gold^after)>>i&1])
            try: entry['legal_postimage']=frozen.mask_postimage(old,after,start)
            except Exception as error: entry['legal_postimage_error']=str(error)
            cases.append(entry)
        elif commit.vector_writes:
            errors=[]
            for (reg,b),(value,_) in actual.items():
                expected=commit.vector_writes.get(reg)
                if expected is None or value!=(expected>>(8*b)&255): errors.append(dict(reg=reg,byte=b,actual=value,
                    expected=None if expected is None else expected>>(8*b)&255))
            strict_writers.append(dict(arch_seq=seq,pc=hex(commit.pc),mismatches=errors))
    require(len(cases)==3 and not unknown,'All three native compares/known accepted data')
    life.save(out/'native-compares.json',dict(cases=cases,nonmask_writer_checks=strict_writers,unknown=unknown))
    with (out/'vpd2vcd.log').open('x') as log:
        result=subprocess.run([str(CONVERTER),'-splitpacked',str(RUN/'mask-compare-known.vpd'),str(out/'focused.vcd')],
            stdout=log,stderr=subprocess.STDOUT,timeout=120)
    require(result.returncode==0,'VPD conversion failed; no retry')
    life.check(pins)
    life.save(out/'diagnostic.json',dict(status='FAILURE_DIAGNOSTIC_NOT_QUALIFICATION',terminal=status,
        original_failure=str(FAILED),scalar_status=scalar['status'],first_scalar_mismatch=scalar.get('first_mismatch'),
        compare_cases=cases,input_pins=pins,conversion_returncode=result.returncode,
        conversion_outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},
        coverage_admitted=False,RTL_modified=False,VCS_launched=False))
    print(json.dumps(dict(output=str(out),seal=life.digest(out/'diagnostic.json'),scalar_status=scalar['status'],
        first_scalar_mismatch=scalar.get('first_mismatch'),cases=[{k:x[k] for k in
        ('case','vstart','arch_seq','prestart_wrong_bits','active_wrong_bits','expected_low64','actual_low64')}
        for x in cases])))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True)
    diagnose(parser.parse_args().output.resolve())
