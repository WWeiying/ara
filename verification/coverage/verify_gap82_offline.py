#!/usr/bin/env python3
"""Offline GAP82 recheck using pinned QBS backend VL semantics; preserve FAIL."""
import argparse
import csv
from pathlib import Path
import struct
import run_gap82_old_image as frozen

require = frozen.require
target = frozen.target
ROOT = frozen.ROOT
EXPECTED_DISPATCHER = '9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43'


def activity_bytes(a, start, response):
    # Backend reservation covers four complete e32 registers, not CSR vl=1.
    require(a.instruction == frozen.WORD and a.allocations == a.completions == 1 and
            a.use_vd and (a.vd,a.eew,a.vl,a.vstart) == (8,2,4*(1024//32),0),
            'M4 backend activity metadata differs')
    require(all(start <= w.cycle <= response and 0 <= w.lane < 4 and
                w.eew == 2 and w.source == 4 and w.be == w.known_be == 255
                for w in a.writes), 'Custom write timing/source/known bytes differ')
    values = frozen._architectural_bytes(a.writes,4,1024)
    expected = {(8+c,i):v for c in range(4)
                for i,v in enumerate(struct.pack('<f',float(256*(c+1)))+bytes(124))}
    require(len(a.writes) == 64 and {k:v for k,(v,w) in values.items()} == expected,
            'Exact independent custom 512-byte output/tail differs')


def runtime(run, proof):
    commit,vector = run/'commit_trace.csv',run/'vector_trace.csv'
    frozen.software(run/'run.vcs.log')
    trace = frozen.validate_trace(commit)
    with commit.open() as stream:
        starts,responses = frozen.conservation(list(csv.DictReader(stream)),[s['pc'] for s in proof['sites']])
    all_starts,retires,traps = frozen._parse_architecture_mapping(commit)
    mapping = frozen._map_architecture_retires(all_starts,retires,traps)
    lanes,vlen,activities = frozen._parse_vector_trace(vector)
    require((lanes,vlen) == (4,1024), 'Wrong vector configuration')
    selected = {s:a for s,a in activities.items() if a.instruction == frozen.WORD}
    require(set(selected) == {s for s,k,c in starts}, 'Custom arch_seq set differs')
    owners,done = {},set()
    with vector.open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] == 'config' or int(row['insn'],16) != frozen.WORD:
                continue
            seq,vid = int(row['arch_seq']),int(row['vid'])
            if row['event'] == 'alloc':
                require(seq not in owners and seq not in done, 'Duplicate custom allocation')
                owners[seq] = vid
            else:
                require(owners.get(seq) == vid, 'Custom event outside lifecycle')
                if row['event'] == 'done':
                    del owners[seq]
                    done.add(seq)
                else:
                    require(row['event'] == 'write', 'Unknown custom event')
    require(not owners and done == set(selected), 'Incomplete custom lifecycle')
    bindings = []
    for i,((seq,key,start),(response_key,request,response)) in enumerate(zip(starts,responses)):
        require(seq in mapping and mapping[seq].pc == proof['sites'][i]['pc'] and
                mapping[seq].instruction == frozen.WORD, 'Activity-to-PC mapping differs')
        activity_bytes(selected[seq],start,response)
        bindings.append(dict(command=i,arch_seq=seq,pc=mapping[seq].pc,trans_id=key,
                             backend_vl=128,architectural_csr_vl=1,writeback_bytes=512))
    return dict(status='PASS',trace=trace,bindings=bindings,custom_requests=2,
                custom_responses=2,custom_retirements=2,custom_writeback_bytes=1024,
                full_vrf_words=2048,initial_vrf_words=2048,source_bytes=6880,csr_words=24,
                per_command_checks=17,total_checks=41)


def verify(run, preflight, output):
    run,preflight = run.resolve(strict=True),preflight.resolve(strict=True)
    require(run.parent == ROOT/'verification/out' and preflight.parent == run.parent,
            'Foreign evidence paths')
    require(output.absolute().parent.resolve() == run.parent and not output.exists(), 'Fresh sidecar required')
    status = target.read(run/'status.json')
    require(status['status'] == 'FAIL' and status['reason'] ==
            'ValueError: Custom activity identity/configuration/lifecycle differs', 'Different failure needs separate audit')
    frozen.admission.preflight(preflight)
    static,proof = target.read(run/'static-plan.json'),target.read(preflight/'elf-proof.json')
    require(static == target.read(preflight/'static-plan.json') and proof['vl'] == 1 and
            proof['m'] == 4 and len(proof['sites']) == 2, 'Sealed software shape differs')
    pins = target.read(run/'source-pins.json')
    snapshot = ROOT/'verification/out/old-image-source-evidence-20261006-01'
    manifest = target.read(snapshot/'manifest.json')
    build_path = ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    require(target.sha(build_path) == static['source_hashes'][str(build_path)], 'Build pin manifest drift')
    build = target.read(build_path)
    original = ROOT/'hardware/src/ara_dispatcher.sv'
    entry = [x for x in manifest['files'] if x['original_relative_path'] == 'hardware/src/ara_dispatcher.sv']
    require(len(entry) == 1 and entry[0]['snapshot_file'] == 'ara_dispatcher.sv' and
            entry[0]['sha256'] == build[str(original)] == EXPECTED_DISPATCHER,
            'Historical dispatcher binding differs')
    dispatcher = snapshot/'ara_dispatcher.sv'
    require(target.sha(dispatcher) == EXPECTED_DISPATCHER and
            "ara_req.vl = vlen_t'(qbs_m * (VLEN / 32));" in dispatcher.read_text(),
            'Pinned historical backend VL semantics differ')
    monitor = ROOT/'hardware/tb/ara_commit_monitor.sv'
    require(target.sha(monitor) == build[str(monitor)], 'Old monitor source drift')
    paths = [run/'status.json',run/'static-plan.json',run/'rtl.command.json',
             run/'commit_trace.csv',run/'vector_trace.csv',run/'run.vcs.log',
             dispatcher,snapshot/'manifest.json',build_path,monitor,Path(__file__).resolve(),
             preflight/'elf-proof.json']
    paths.extend(p for p in (run/'code.vdb').rglob('*') if p.is_file())
    for path in paths:
        pins[str(path)] = target.sha(path)
    def fresh():
        for p,h in pins.items():
            require(target.sha(p) == h, 'Evidence drift: '+p)
    fresh()
    audit = runtime(run,proof)
    measured = frozen.measure(run/'code.vdb',static)
    fresh()
    output.mkdir()
    frozen.save(output/'evidence-pins.json',pins)
    frozen.save(output/'runtime-audit.json',audit)
    frozen.save(output/'target-measurement.json',measured)
    frozen.save(output/'status.json',dict(status='OFFLINE_SINGLE_CASE_VERIFIED',
        original_status_preserved='FAIL',checker_error='CSR vl=1 incorrectly compared with backend reservation vl=128',
        historical_dispatcher_sha256=EXPECTED_DISPATCHER,both_targets_hit=measured['both_targets_hit'],
        rtl_error_observed=False,simulation_rerun=False,aggregate_combined=False,dve_run=False,receipt_issued=False))
    return audit,measured


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--preflight',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    a=parser.parse_args()
    print(verify(a.run,a.preflight,a.output))
