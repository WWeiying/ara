#!/usr/bin/env python3
"""Run the independent two-command GAP82 case; no aggregate or DVE."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'verification'))
sys.path.insert(0, str(ROOT/'verification/tests'))
import admit_gap82_m4_phase4_phase8 as admission
import analyze_gap82_m4_phase4_phase8 as target
import coverage_bitmap_delta as bitmaps
from ara_verify.contract import check_contract_log
from ara_verify.trace import validate_trace
from ara_verify.vector_commit import (_parse_vector_trace, _architectural_bytes,
    _parse_architecture_mapping, _map_architecture_retires)

NAME = 'qbs_gap82_m4_phase4_phase8'
WORD = 0x06b5045b
require = target.require


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def software(log):
    text = log.read_text(errors='replace')
    lines = text.splitlines()
    for line in ['GAP82 command=0 checks=17 errors=0',
                 'GAP82 command=1 checks=17 errors=0',
                 'GAP82 inspected vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',
                 'PASSED: qbs_gap82_m4_phase4_phase8 checks=41 errors=0']:
        require(lines.count(line) == 1, 'Incomplete/duplicate software selfcheck: '+line)
    require(text.count('Core Test *** SUCCESS ***') == 1 and
            not re.search(r'Fatal:|Error:|FAILED:|Core Test \*\*\* FAIL', text, re.I),
            'Simulator did not complete cleanly')
    require(not check_contract_log(log), 'Runtime contract violation')


def conservation(rows, sites):
    require(len(sites) == 2 and len(set(sites)) == 2, 'Two distinct sealed PCs required')
    pending, starts, completed, retired = {}, [], [], []
    for row in rows:
        word, cycle = int(row['insn'],16), int(row['cycle'])
        key = int(row['trans_id'])
        if row['event'] == 'arch_start' and word == WORD:
            starts.append((int(row['order']), key, cycle))
        elif row['event'] == 'cvx_req':
            require(key not in pending, 'Duplicate outstanding transaction')
            pending[key] = (word, cycle)
        elif row['event'] == 'cvx_resp':
            require(key in pending and not int(row['trap']), 'Orphan/failed response')
            request, request_cycle = pending.pop(key)
            require(cycle >= request_cycle, 'Response precedes request')
            if request == WORD:
                completed.append((key, request_cycle, cycle))
        elif row['event'] == 'retire' and word == WORD:
            require(not int(row['trap']), 'Faulting custom retirement')
            retired.append((int(row['pc'],16),cycle))
    require(not pending and len(starts) == len(completed) == len(retired) == 2 and
            [p for p,c in retired] == sites and len({s for s,k,c in starts}) == 2,
            'Two-command request/response/retirement conservation failed')
    for i, ((seq,key,start),(response_key,request,response),(pc,retire)) in enumerate(
            zip(starts,completed,retired)):
        require(key == response_key and start <= request <= response <= retire,
                'Custom architecture/transaction order differs')
        if i:
            require(start > retired[i-1][1], 'Commands overlap across software selfcheck')
    return starts, completed


def activity_bytes(activity, lanes, vlen, start, response):
    require(activity.instruction == WORD and activity.allocations == 1 and
            activity.completions == 1 and activity.vd == 8 and
            activity.vl == 1 and activity.vstart == 0 and activity.eew == 2,
            'Custom activity identity/configuration/lifecycle differs')
    require(all(start <= w.cycle <= response and 0 <= w.lane < lanes and
                w.eew == 2 and w.be == w.known_be == 255 for w in activity.writes),
            'Custom write timing/known bytes/configuration differs')
    values = _architectural_bytes(activity.writes, lanes, vlen)
    expected = {}
    for context in range(4):
        data = struct.pack('<f',float(256*(context+1))) + bytes(124)
        expected.update({(8+context,i):value for i,value in enumerate(data)})
    require(sum(bin(w.be).count('1') for w in activity.writes) == 512 and
            {k:v for k,(v,w) in values.items()} == expected,
            'Exact independent 512-byte custom VRF writeback differs')


def runtime(commit, vector, log, sites):
    software(log)
    trace = validate_trace(commit)
    with commit.open() as stream:
        starts, completed = conservation(list(csv.DictReader(stream)), sites)
    all_starts, retires, trapped = _parse_architecture_mapping(commit)
    mapping = _map_architecture_retires(all_starts,retires,trapped)
    lanes,vlen,activities = _parse_vector_trace(vector)
    require((lanes,vlen) == (4,1024), 'Wrong vector configuration')
    selected = {s:a for s,a in activities.items() if a.instruction == WORD}
    require(set(selected) == {s for s,k,c in starts}, 'Custom arch_seq set differs')
    owners, done = {}, set()
    with vector.open() as stream:
        for row in csv.DictReader(stream):
            if row['event'] == 'config' or int(row['insn'],16) != WORD:
                continue
            seq,vid = int(row['arch_seq']),int(row['vid'])
            if row['event'] == 'alloc':
                require(seq not in owners and seq not in done, 'Duplicate custom allocation')
                owners[seq] = vid
            else:
                require(owners.get(seq) == vid, 'Custom event outside allocated lifecycle')
                if row['event'] == 'done':
                    del owners[seq]
                    done.add(seq)
                else:
                    require(row['event'] == 'write' and int(row['source']) == 4,
                            'Unexpected custom write source')
    require(not owners and done == set(selected), 'Custom uop lifecycle incomplete')
    bindings = []
    for i, ((seq,key,start),(response_key,request,response)) in enumerate(zip(starts,completed)):
        require(seq in mapping and mapping[seq].pc == sites[i] and
                mapping[seq].instruction == WORD, 'Activity-to-PC mapping differs')
        activity_bytes(selected[seq],lanes,vlen,start,response)
        bindings.append(dict(command=i,pc=sites[i],arch_seq=seq,trans_id=key,
                             start_cycle=start,response_cycle=response,vrf_bytes=512))
    return dict(status='PASS',trace=trace,bindings=bindings,custom_requests=2,
                custom_responses=2,custom_retirements=2,compared_custom_vrf_bytes=1024,
                full_vrf_words=2048,initial_vrf_words=2048,csr_words=24,source_bytes=6880,
                per_command_checks=17,total_checks=41)


def measure(vdb, static):
    files = list((vdb/'snps/coverage/db/testdata').glob('*/cond.verilog.data.xml'))
    require(len(files) == 1 and files[0].parent.name == NAME, 'One named raw condition VDB required')
    digest = target.sha(files[0])
    row = bitmaps.read_metric(files[0])[target.SCOPE]
    require(target.sha(files[0]) == digest, 'Condition bitmap changed during read')
    hits = []
    for c in static['commands']:
        require(str(row['checksum']) == str(c['target']['checksum']), 'Condition shape checksum differs')
        hits.append(dict(command=c['id'],raw_index=c['raw_index'],native_id=c['native_id'],
                         vector='1',hit=target.bit(row,c['raw_index']) == '1'))
    return dict(scope=target.SCOPE,checksum=row['checksum'],width=row['width'],
                raw_file=str(files[0]),raw_sha256=digest,targets=hits,
                both_targets_hit=all(x['hit'] for x in hits),aggregate_combined=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    preflight = args.preflight.resolve(strict=True)
    admission.preflight(preflight)
    static = target.read(preflight/'static-plan.json')
    proof = target.read(preflight/'elf-proof.json')
    out = args.output.absolute()
    require(out.parent.resolve() == ROOT/'verification/out' and not out.exists(), 'Fresh independent output required')
    out.mkdir()
    # Only local launch evidence is rehashed; no historical test population is collected.
    pins = dict(static['image'])
    pins.update({p:h for p,h in static['source_hashes'].items()
                 if '/hardware/' in p or '/simv.vdb/' in p})
    elf = Path(proof['elf'])
    pins[str(elf)] = proof['elf_sha256']
    for path in [Path(__file__).resolve(),Path(bitmaps.__file__),
                 ROOT/'verification/ara_verify/trace.py',ROOT/'verification/ara_verify/contract.py',
                 ROOT/'verification/ara_verify/vector_commit.py',preflight/'static-plan.json',preflight/'elf-proof.json']:
        pins[str(path)] = target.sha(path)
    def verify():
        for path,digest in pins.items():
            require(target.sha(path) == digest, 'Input drift: '+path)
    verify()
    save(out/'source-pins.json',pins)
    save(out/'static-plan.json',static)
    cmd = [static['simv'],'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
           '+PRELOAD='+str(elf),'+TESTCASE='+NAME,'+COMMIT_TRACE='+str(out/'commit_trace.csv'),
           '+VECTOR_TRACE='+str(out/'vector_trace.csv'),'+QBS_PERF',
           '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',NAME]
    save(out/'rtl.command.json',dict(command=cmd,cwd=str(out),timeout_s=600))
    try:
        with (out/'console.log').open('x') as console:
            process = subprocess.Popen(cmd,cwd=out,stdout=console,stderr=subprocess.STDOUT)
            save(out/'started.json',dict(status='RUNNING',runner_pid=os.getpid(),simv_pid=process.pid,
                                         image=static['simv'],timeout_s=600))
            try:
                code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise
            require(code == 0, 'Simulator exit code '+str(code))
        result = runtime(out/'commit_trace.csv',out/'vector_trace.csv',out/'run.vcs.log',
                         [s['pc'] for s in proof['sites']])
        verify()
        measured = measure(out/'code.vdb',static)
        save(out/'runtime-audit.json',result)
        save(out/'target-measurement.json',measured)
        admission.preflight(preflight)
        verify()
        save(out/'artifact-hashes.json',{str(p):target.sha(p) for p in out.rglob('*') if p.is_file()})
        save(out/'status.json',dict(status='SINGLE_CASE_VERIFIED',software_pass=True,
             both_targets_hit=measured['both_targets_hit'],aggregate_combined=False,
             dve_run=False,receipt_issued=False,rtl_changed=False))
    except Exception as error:
        save(out/'status.json',dict(status='TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'FAIL',
             reason=f'{type(error).__name__}: {error}',aggregate_combined=False,dve_run=False))
        raise


if __name__ == '__main__':
    main()
