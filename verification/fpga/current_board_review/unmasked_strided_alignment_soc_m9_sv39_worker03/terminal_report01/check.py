#!/usr/bin/env python3
"""Closed terminal metadata/pin verification; no CSV semantic traversal."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
spec = importlib.util.spec_from_file_location('closed_sv39_worker', ROOT/'worker.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def main():
    out = HERE/'result.json'
    w.require(not out.exists(), 'No report overwrite')
    plan, complete = w.read(w.OUT/'plan.json'), w.read(w.OUT/'complete.json')
    w.require(w.sha(w.OUT/'plan.json') == '83a427884a035b7deda1923dd1000e6fc4043584306a15561f6c34fe8bc8d752', 'Reviewed plan')
    w.contract(plan)
    w.require(complete['status'] == w.PASS and complete['firstfailure'] is None
              and complete['aborted'] is False and complete['pins_unchanged'] is True
              and type(complete['retries']) is int and complete['retries'] == 0
              and complete['plan_sha256'] == w.sha(w.OUT/'plan.json')
              and not (w.OUT/'firstfailure.json').exists(), 'Exact accepted terminal/no failure')
    launch = w.read(w.OUT/'launch.json')
    w.review_gate(plan, complete['plan_sha256'], Path(launch['review']), complete['review_sha256'])
    mmode, _ = w.m_mode_gate()
    controls, _ = w.controls_reuse()
    w.require(complete['m_mode_reuse'] == mmode and complete['controls_reuse'] == controls, 'Independent reuse bindings')
    pins = dict(plan['pins'])
    for p, h in complete['evidence_pins'].items():
        w.require(p not in pins or pins[p] == h, 'Conflicting evidence pin')
        pins[p] = h
    for p in (w.OUT/'plan.json', w.OUT/'complete.json', w.OUT/'launch.json', Path(launch['review']),
              ROOT/'startup_observation.json', ROOT/'service.log', Path(__file__)):
        pins[str(p)] = w.sha(p)
    w.m.base.verify_pins(pins)
    ledger, _, _ = w.old.image_context()
    w.require(len(complete['results']) == 2 and {r['name'] for r in complete['results']} == {c['id'] for c in plan['cases']}, 'Two exact members')
    w.require(w.read(w.OUT/'sv39_2/summary.json') == complete['results'], 'Actual summary equality')
    run = w.read(w.OUT/'sv39_2/run.json')
    w.require(run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 2}, 'Actual runner COMPLETE')
    members = []
    for case in plan['cases']:
        r = next(x for x in complete['results'] if x['name'] == case['id'])
        root = Path(r['artifact_dir'])
        receipt, checker_exit = w.read(root/'child_exit.json'), w.read(root/'checker_exit.json')
        w.old.receipt_ok(receipt, 900)
        w.require(r['status'] == 'PASS' and type(r['returncode']) is int and r['returncode'] == 0
                  and r['elapsed_s'] == receipt['elapsed_s'] and type(checker_exit['returncode']) is int
                  and checker_exit['returncode'] == 0, 'Real child0/checker0/elapsed')
        actual_result = SimpleNamespace(**dict(r, artifact_dir=root))
        w.m.check_artifacts(actual_result, case, ledger)
        invocation = w.read(root/'checker_invocation.json')
        w.require(invocation == dict(command=w.checker_command(case, root), checker_sha256=w.CHECK_SHA), 'Actual corrected checker invocation')
        data, generic = w.read(root/'csv.json'), w.read(root/'trace_summary.json')
        w.checker_result(data, case)
        w.require((data['rows'], data['retired_rows'], data['last_cycle']) ==
                  (generic['rows'], generic['retire_count'], generic['last_cycle']), 'Complete saved traversal counts')
        w.require(data['actual_exit_events'] == [dict(pc=0x80000072, insn=0x00a2b023, address=0xd0000000, value=0, size=8)], 'Actual strict CTRL result')
        for owner in data['memory_owners']:
            w.require(owner['allocations'] and len(owner['allocations']) == len(owner['completions']), 'Every saved owner completed')
        for n, trap in enumerate(data['traps']):
            w.require(trap['0'] == (9 if n else 6 if case['member']=='store_sv39' else 4)
                      and trap['7'] == (0 if n else 1) and trap['5'] == 2 and trap['6'] == 24,
                      'Precise alignment/ecall/vstart/VL/vtype result')
        members.append(dict(member=case['member'], child_exit=receipt['returncode'], checker_exit=checker_exit['returncode'],
                            elapsed_s=receipt['elapsed_s'], checks=data['checks'], rows=data['rows'],
                            retired_rows=data['retired_rows'], last_cycle=data['last_cycle'],
                            memory_owners=data['memory_owner_count'], helper_owners=data['helper_owner_count'],
                            restore_readbacks=data['restore_readback_checks'], traps=data['traps'],
                            csv_sha256=w.sha(root/'commit_trace.csv'), oracle_sha256=w.sha(root/'csv.json')))
    w.m.base.verify_pins(pins)
    result = dict(status='SV39_TWO_TERMINAL_METADATA_AND_PINS_ACCEPTED', members=members,
                  input_pin_count=len(plan['pins']), evidence_pin_count=len(complete['evidence_pins']),
                  total_pin_count=len(pins), pins=pins, pins_unchanged=True,
                  complete_sha256=w.sha(w.OUT/'complete.json'), semantic_CSV_reparse=False,
                  combined_architectural_scope='M9 alignment4 accepted from two independently recovered M-mode CSVs plus two fresh Sv39 results; controls16 separately reused',
                  combined_counts=dict(directed_cases=4, checks=2790, csv_rows=101070, retired_rows=100374,
                                       memory_owners=36, helper_owners=28, restore_readbacks=56),
                  old_batch_relabelled=False, m_mode_reuse=mmode, controls_reuse=controls,
                  systemd_observation=dict(tool_chunk='af2bbf', LoadState='not-found', ActiveState='inactive', MainPID=0,
                                           observed_historical_worker_exit=None,
                                           reason='Successful transient unit GC; default Result/ExecMainStatus are not historical exit evidence'),
                  audit_pid=os.getpid())
    w.save(out, result)
    print(json.dumps(dict(status=result['status'], members=len(members), pins=len(pins), complete_sha256=result['complete_sha256'])))


if __name__ == '__main__':
    main()
