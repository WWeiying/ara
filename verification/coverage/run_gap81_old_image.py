#!/usr/bin/env python3
"""Run one host-oracle-checked M4 phase12 case on the frozen coverage image."""
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
sys.path.insert(0, str(ROOT / 'verification'))
sys.path.insert(0, str(ROOT / 'verification/tests'))
import admit_gap81_m4_phase12 as admission
import analyze_gap81_m4_phase12 as target
import coverage_bitmap_delta as bitmaps
from ara_verify.contract import check_contract_log
from ara_verify.trace import validate_trace
from ara_verify.vector_commit import _parse_vector_trace, _architectural_bytes

NAME = 'qbs_gap81_m4_phase12'


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def runtime(commit, vector, log, site):
    require = target.require
    text = log.read_text(errors='replace')
    require(text.splitlines().count('GAP81 command=0 checks=18 errors=0') == 1,
            'DUT command selfcheck incomplete')
    require(text.splitlines().count('GAP81 inspected vrf_words=1024 initial_words=1024 source_bytes=3440 csr_words=12') == 1,
            'DUT full-state checks incomplete')
    require(text.splitlines().count('PASSED: qbs_gap81_m4_phase12 checks=24 errors=0') == 1,
            'DUT final selfcheck incomplete')
    require(text.count('Core Test *** SUCCESS ***') == 1 and
            not re.search(r'Fatal:|Error:|FAILED:|Core Test \*\*\* FAIL', text, re.I),
            'Simulator did not complete cleanly')
    require(not check_contract_log(log), 'Runtime contract violation')
    trace = validate_trace(commit)
    pending, custom, retired = {}, [], []
    with commit.open() as stream:
        for row in csv.DictReader(stream):
            word = int(row['insn'], 16)
            if row['event'] == 'cvx_req':
                key = int(row['trans_id'])
                require(key not in pending, 'Duplicate outstanding transaction')
                pending[key] = word
            elif row['event'] == 'cvx_resp':
                key = int(row['trans_id'])
                require(key in pending and not int(row['trap']), 'Orphan/failed response')
                if pending.pop(key) == 0x06b5045b:
                    custom.append(word)
            elif row['event'] == 'retire' and word == 0x06b5045b:
                require(not int(row['trap']), 'Faulting QBS retirement')
                retired.append(int(row['pc'], 16))
    require(not pending and len(custom) == 1 and retired == [site],
            'Custom request/response/retirement conservation failed')
    lanes, vlen, activities = _parse_vector_trace(vector)
    require((lanes, vlen) == (4, 1024), 'Wrong vector configuration')
    selected = [a for a in activities.values() if a.instruction == 0x06b5045b]
    require(len(selected) == 1 and selected[0].allocations > 0 and
            selected[0].allocations == selected[0].completions,
            'Custom activity incomplete')
    values = _architectural_bytes(selected[0].writes, lanes, vlen)
    expected = {}
    for context in range(4):
        data = struct.pack('<f', float(256*(context+1))) + bytes(124)
        expected.update({(8+context, i): value for i, value in enumerate(data)})
    require({key: value for key, (value, _) in values.items()} == expected,
            'Independent QBS architectural VRF bytes differ')
    return dict(status='PASS', trace=trace, custom_requests=1,
                compared_custom_vrf_bytes=512, full_vrf_words=1024,
                csr_words=12, source_bytes=3440,
                oracle='independent native host reference plus exact custom writeback and DUT full-state selfcheck')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    preflight = args.preflight.resolve(strict=True)
    admission.preflight(preflight)
    static = target.analyze()
    out = args.output.absolute()
    target.require(out.parent.resolve() == ROOT/'verification/out' and not out.exists(),
                   'Fresh independent output required')
    out.mkdir()
    proof = target.read(preflight/'elf-proof.json')
    elf = Path(proof['elf'])
    target.require(target.sha(elf) == proof['elf_sha256'], 'ELF changed')
    pins = dict(static['source_hashes'])
    pins.update(static['image'])
    pins[str(elf)] = proof['elf_sha256']
    pins[str(Path(__file__).resolve())] = target.sha(Path(__file__))
    def verify():
        for path, digest in pins.items():
            target.require(target.sha(path) == digest, 'Input drift: '+path)
    verify()
    save(out/'source-pins.json', pins)
    save(out/'static-plan.json', static)
    cmd = [static['simv'], '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
           '+PRELOAD='+str(elf), '+TESTCASE='+NAME,
           '+COMMIT_TRACE='+str(out/'commit_trace.csv'),
           '+VECTOR_TRACE='+str(out/'vector_trace.csv'), '+QBS_PERF',
           '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out/'code.vdb'), '-cm_name', NAME]
    save(out/'rtl.command.json', dict(command=cmd, cwd=str(out), timeout_s=600))
    save(out/'started.json', dict(status='RUNNING', image=static['simv'], rtl_changed=False))
    try:
        with (out/'console.log').open('x') as console:
            subprocess.run(cmd, cwd=out, stdout=console, stderr=subprocess.STDOUT,
                           timeout=600, check=True)
        result = runtime(out/'commit_trace.csv', out/'vector_trace.csv',
                         out/'run.vcs.log', proof['site']['pc'])
        verify()
        admission.preflight(preflight)
        inputs = out/'new-inputs.txt'
        with inputs.open('x') as stream:
            stream.write(static['design_vdb']+'\n'+str(out/'code.vdb')+'\n')
        new = bitmaps.collect(inputs)
        before = target.read(target.BASELINE/'combined-bits.json')
        after = bitmaps.combine(before, new)
        save(out/'combined-bits.json', after)
        delta = bitmaps.delta(before, after)
        save(out/'raw-bitmap-delta.json', delta)
        row = after['metrics']['cond'][target.SCOPE]
        hit = target.bit(row, 400) == '1'
        save(out/'audit.json', dict(result, target_hit=hit, rtl_bug_fixed=False))
        historical = (target.BASELINE/'combined-inputs.txt').read_text().splitlines()
        target.require(str(out/'code.vdb') not in historical and len(historical) == 688,
                       'Historical PASS population differs')
        with (out/'combined-inputs.txt').open('x') as stream:
            stream.write('\n'.join([*historical, str(out/'code.vdb')])+'\n')
        with (out/'dve.log').open('x') as log:
            subprocess.run(['bash', str(ROOT/'verification/coverage/run_dve_coverage.sh'),
                            str(out/'combined-dve'), '--inputs-file', str(out/'combined-inputs.txt')],
                           cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=1260,
                           env=dict(os.environ, DVE_COVERAGE_TIMEOUT='1200', DVE_WAIVERS='off'), check=True)
        verify()
        save(out/'status.json', dict(status='COMPLETE', coverage_status='COMPLETE',
            new_passed=1, aggregate_passed=688, target_hit=hit,
            historical_prefix_current_checker_revalidated=False,
            image=static['simv'], rtl_changed=False, new_waivers_applied=False))
    except Exception as error:
        save(out/'status.json', dict(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
            reason=f'{type(error).__name__}: {error}', coverage_status='INCOMPLETE',
            rtl_changed=False, bug_fix_deferred=True))
        raise


if __name__ == '__main__':
    main()
