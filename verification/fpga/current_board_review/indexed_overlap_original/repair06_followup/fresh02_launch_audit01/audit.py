#!/usr/bin/env python3
"""Offline launch-gate audit only. Never queries services/processes or running CSVs."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
spec = importlib.util.spec_from_file_location('audited_coordinator', OWNER / 'coordinator_successor.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def main():
    fresh = OWNER / 'fresh02'
    witness = OWNER.parent / 'repair06_exit_witness01/run01'
    known = {
        OWNER / 'coordinator_successor.py': 'a78191e2e8288318fbebf67612a69ed71f2f799ec0bb11825f2e7fac15d3c130',
        fresh / 'plan.json': 'ee0b810e5bcd99cb7d2727923628a35b202db3c66219b7fac96966bf2a1124d4',
        OWNER / 'prepared01/plan.json': '4765cdfc0805b304b593b4fed7be2542a66907b4890ae777f0707bbe0c6ae007',
        c.PRE / 'complete.json': '5346d4623f744603f1a2d65677d7bed74615746bf8ec112d8604d9505f6bfd48',
    }
    c.verify(known)
    plan = c.read(fresh / 'plan.json')
    old = c.read(OWNER / 'prepared01/plan.json')
    c.require(len(plan['pins']) == 889 and len(old['pins']) == 885 and
              all(plan['pins'][p] == h for p, h in old['pins'].items()), 'Pin membership changed')
    c.verify(plan['pins'])
    pre, reg, worker = c.load_inputs()
    ledger = c.shared_validation(pre, reg, worker)
    accepted = c.accept_terminal(c.PRE, pre, c.PRE_SHA, worker, ledger, True)
    admission = c.read(fresh / 'admission.json')
    c.require(admission['predecessor'] == accepted and accepted['results'] == 3 and
              accepted['evidence_count'] == 29, 'Saved admission differs from offline gate replay')

    service = admission['predecessor_service']
    p = service['properties']
    c.require(service['historical_service_exit_verified'] is True and service['residual'] == [] and
              p['Id'] == c.PRE_UNIT and p['LoadState'] == 'loaded' and p['ActiveState'] == 'inactive' and
              p['MainPID'] == '0' and p['Result'] == 'success' and p['ExecMainCode'] == '1' and
              p['ExecMainStatus'] == '0' and p['ExecMainExitTimestamp'], 'No actual loaded exit0 admission proof')
    start = c.read(witness / 'startup.json')
    exit_record = c.read(witness / 'actualexit.json')
    exited = exit_record['properties']
    c.require(start['plan_sha256'] == c.PRE_SHA and start['before']['MainPID'] == 620452 and
              start['before']['ControlGroup'].endswith('/' + c.PRE_UNIT), 'Witness original owner mismatch')
    c.require(exit_record['kind'] == 'SYSTEMD_EXIT_FACTS_ONLY' and exit_record['exit_evidence_complete'] is True and
              exited['Id'] == c.PRE_UNIT and exited['LoadState'] == 'loaded' and exited['ActiveState'] == 'inactive' and
              exited['MainPID'] == 0 and exited['ExecMainPID'] == 620452 and exited['ExecMainCode'] == 1 and
              exited['ExecMainStatus'] == 0 and exited['Result'] == 'success' and
              exited['InvocationID'] == start['before']['InvocationID'] == start['after_ref']['InvocationID'] ==
              '94f592605b7147d3b5e47923457f3078', 'Witness exit facts disagree')

    launch = c.read(fresh / 'launch.json')
    child = c.read(fresh / 'child.json')
    reg_launch = c.read(c.REG / 'launch.json')
    c.require(launch['plan_sha256'] == known[fresh / 'plan.json'] and launch['pid'] == 628354 and
              launch['service'] == admission['owner'], 'Coordinator owner drift')
    c.owner_proof(launch['service'], launch['pid'], launch['service']['ControlGroup'])
    c.require(child['pid'] == reg_launch['pid'] == 675396 and child['parent'] == launch['pid'] and
              child['cgroup'] == launch['service']['ControlGroup'] and child['new_service'] is False and
              child['command'] == plan['command'] == c.regression_command() and
              reg_launch['plan_sha256'] == c.REG_SHA and reg_launch['image'] == str(c.IMAGE),
              'Regression child command/owner/provenance mismatch')
    for resource in (admission['resources'], reg_launch['admission']):
        c.require(resource['live'] == [] and resource['external'] == 0 and resource['jobs'] == 4 and
                  resource['total'] == 4 and resource['unused_external_reservation'] == 0 and
                  resource['available_bytes'] >= 32 * 1024**3, 'Saved admission resources differ')

    complete = c.read(c.PRE / 'complete.json')
    times = dict(predecessor_complete=complete['finished'],
                 predecessor_actual_exit=exited['ExecMainExitTimestamp'] / 1000000,
                 witness_observed_exit=exited['observed_unix'],
                 followup_admission=admission['resources']['time'],
                 regression_child_launch=reg_launch['started'])
    c.require(list(times.values()) == sorted(times.values()) and len(set(times.values())) == 5,
              'Exit/admission/launch timeline out of order')
    c.require(complete['aborted'] is False and complete['elapsed_s'] < 8800 and
              times['followup_admission'] - launch['started'] < 10800, 'Abort or budget mismatch')
    cases = []
    for result in complete['results']:
        analysis = c.read(Path(result['artifact_dir']) / 'indexed_analysis.json')
        cases.append(dict(name=result['name'], status=result['status'], returncode=result['returncode'],
                          elapsed_s=result['elapsed_s'], checks=analysis['checks'], rounds=analysis['rounds'],
                          points=len(analysis['points']), repairs=analysis['repairs'], retries=analysis['retries']))
    extra = [fresh / name for name in ('launch.json', 'admission.json', 'child.json', 'service_command.NOT_EXECUTED.json')]
    extra += [witness / 'startup.json', witness / 'actualexit.json', c.REG / 'launch.json', Path(__file__)]
    evidence_pins = {str(p): h for p, h in known.items()}
    evidence_pins.update({str(p): c.sha(p) for p in extra})
    c.verify(plan['pins']); c.verify(accepted['evidence_pins']); c.verify(evidence_pins)
    report = dict(status='M6_FRESH02_LAUNCH_GATE_AUDIT_PASS_NOT_REGRESSION48_PASS', findings=[],
                  exact_coordinator_pins_verified=889, prior885_preserved=True,
                  predecessor_evidence_verified=29, predecessor_gate_replay_matches=True,
                  cases=cases, oracle_checks=sum(x['checks'] for x in cases),
                  predecessor_service=service, witness_exit=exit_record,
                  timeline={name: dict(unix=value, utc=utc(value)) for name, value in times.items()},
                  exit_to_child_seconds=times['regression_child_launch'] - times['predecessor_actual_exit'],
                  child=child, resources_at_admission=admission['resources'], evidence_pins=evidence_pins,
                  gate_code_locations=dict(service_exit='coordinator_successor.py:129',
                    terminal_and_oracle='coordinator_successor.py:185',
                    final_admission='coordinator_successor.py:307', spawn='coordinator_successor.py:324'),
                  parent_observation='Four actual original38 M6 simvs reported by parent; not independently repolled here',
                  scope='Launch prerequisite/evidence audit. Saved full-oracle ledgers and CSV hashes verified; no CSV oracle recomputation.',
                  regression48_verdict='NOT_ASSESSED_RUNNING_CAMPAIGN_NOT_POLLED',
                  service_or_process_queries=False, simulations_launched=False, sealed_files_modified=False)
    c.save(HERE / 'report.json', report)
    lines = ['# M6 Fresh02 Launch Audit', '',
             'PASS for launch prerequisites only; no regression48 result is claimed.', '',
             '- Frozen successor a78191e2..., plan ee0b810e...: all889 pins match, all prior885 preserved.',
             '- Offline replay of the read-only admission validator matches saved admission exactly: three cases and29 evidence hashes.',
             '- All three full50-round cases PASS/rc0, no abort;48405 recorded oracle checks,3200 repairs/retries.',
             '- Recorded service proof is loaded/inactive, MainPID0, Resultsuccess, ExecMainCode1/status0, no residual owner.',
             '- Persistent witness independently binds original PID620452 and InvocationID94f592605b7147d3b5e47923457f3078 to actual exit0.',
             '- Followup MainPID628354 owns child675396 in the same cgroup; sealed regression48 command/plan/image match.',
             '', '## Ordering', '']
    lines += [f'- {name}: {utc(value)} ({value})' for name, value in times.items()]
    lines += ['', f"Actual exit precedes regression child launch by {report['exit_to_child_seconds']:.6f}s.", '',
              'The frozen code rechecks pins/shared validators and full predecessor evidence at lines307-310,',
              'requires real loaded exit0/no owners at311-312, writes admission at319, then invokes Popen at324.',
              'The strict GC refusal remains at137; old prepared01/helper files were not changed.', '',
              '## Limits', '',
              'No service/process queries, running regression CSV reads, or simulation launches were made.',
              'Parent observation of four actual M6 original38 simvs is attributed, not re-observed.',
              'This is not an independent fullCSV oracle recomputation or a48-case acceptance.',
              'Machine-readable report.json pins the launch records, witness evidence and audited inputs.']
    with (HERE / 'REPORT.md').open('x') as stream:
        stream.write('\n'.join(lines) + '\n')
    print(json.dumps(dict(status=report['status'], cases=len(cases), checks=report['oracle_checks'],
                          report=str(HERE / 'report.json'), report_sha256=c.sha(HERE / 'report.json'))))


if __name__ == '__main__':
    main()
