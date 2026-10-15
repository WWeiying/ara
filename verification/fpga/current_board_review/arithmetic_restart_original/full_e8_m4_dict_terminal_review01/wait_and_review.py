#!/usr/bin/env python3
"""Event-only wait, then one metadata review; never opens a CSV or runs a DUT."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
SOURCE = HERE.parent / 'full_e8_m4_dict_vcs_m9_plan01/prepared01'
OUT = HERE / 'terminal01'
WAIT = G / 'wait_terminal.py'
CASE = 'arithmetic_original_e8_m4_full4095_dict'
PLAN = '4df0c5b631b8645fb51a4ca52ca1bb916dec03ad455e88c0a380a5b023f2c2db'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    if path.suffix == '.csv' or path.stat().st_size > 10000000:
        raise ValueError('Large artifact reads forbidden in metadata review: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def need(value, reason):
    if not value:
        raise ValueError(reason)


def audit():
    result = dict(status='NOT_ACCEPTED',started=time.time(),CSV_reads=0,semantic_reparses=0)
    try:
        need(sha(SOURCE/'plan.json') == PLAN, 'Exact original plan drift')
        plan = read(SOURCE/'plan.json')
        end, service, collected, waited = [read(SOURCE/n) for n in
            ('complete.json','service_exit.json','collector_result.json','collector_exit.json')]
        need(end['status'] == 'PASS_M9_FULL_ORIGINAL_E8_M4_4095_CALLS_NOT_LINUX' and
             end['plan_sha256'] == PLAN and end['aborted'] is False and end['pins_unchanged'] is True and end['retries'] == 0,
             'Producer not complete PASS/noabort/unchanged/noretry')
        need(len(end['results']) == len(plan['cases']) == 1 and plan['cases'][0]['id'] == CASE, 'Exact single membership')
        child = end['results'][0]
        root = SOURCE/'replay/tests'/CASE
        raw = read(root/'child_outcome.unvalidated.json')
        need(child['name'] == CASE and child['status'] == 'PASS' and type(child['returncode']) is int and
             child['returncode'] == 0 and not child['reason'] and 0 < child['elapsed_s'] <= 10800, 'Actual child outcome')
        need(type(raw['returncode']) is int and raw['returncode'] == 0 and raw['elapsed_s'] == child['elapsed_s'] and
             not any(raw[k] for k in ('timed_out','failure_seen','cancelled')), 'Durable monitor outcome')
        need([service[k] for k in ('SERVICE_RESULT','EXIT_CODE','EXIT_STATUS')] == ['success','exited','0'] and
             service['kind'] == 'SYSTEMD_EXEC_STOP_POST_ACTUAL_ENVIRONMENT', 'Actual original service exit, not GC defaults')
        need(type(waited['actual_wait_returncode']) is int and waited['actual_wait_returncode'] == 0 and
             waited['timed_out'] is False and waited['retries'] == 0 and 0 < waited['elapsed_s'] <= 300, 'Actual collector wait')
        need(collected['status'] == 'ACCEPTED_M9_ORIGINAL_E8_M4_FULL4095_NOT_LINUX' and
             collected['plan_sha256'] == PLAN and collected['complete_sha256'] == sha(SOURCE/'complete.json') and
             collected['actual_service'] == service and collected['actual_monitor'] == raw and
             collected['pins_pre_post_unchanged'] is True and collected['csv_semantic_reparses'] == 0, 'Collector binding')
        report = read(root/'strict_original.json')
        strict, generic, owners = report['strict'], report['generic'], report['owner_coverage']
        keys = ('calls','results','guards','returned_vstart_zero','helper_instructions','packed_output_reads')
        need([strict[k] for k in keys] == [4095,2096640,8190,4095,53235,266175] and
             strict['routine_counts'] == [4095]*13 and strict['fresh_output_bytes_each_call'] == 514 and
             strict['full_order'] is True and strict['partitioned'] is False and
             strict['status'] == 'FULL4095_ACTUAL_RVFI_ACCEPTED_NOT_LINUX', 'Full original semantic scope')
        need([owners[k] for k in ('compulsory_memory_owners','required_target_owners','required_op24_memory_targets','minimum_required_owners')] ==
             [20475,2610,117,23085], 'Full necessary owner scope')
        need(report['strict_csv_parses'] == 1 and (strict['rows'],strict['retired'],strict['last_cycle']) ==
             (generic['rows'],generic['retire_count'],generic['last_cycle']) and generic['cvx_exception_count'] == 0 and
             generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0 and
             generic['cvx_request_count'] == generic['cvx_response_count'] > 0, 'Complete strict/generic protocol')
        need(read(root/'trace_summary.json')['status'] == 'VALID', 'Frozen generic summary')
        need(collected['strict_report_sha256'] == sha(root/'strict_original.json') and
             collected['csv_sha256'] == report['actual_csv_sha256'] == end['evidence_pins'][str(root/'commit_trace.csv')], 'Closed CSV digest cross-binding')
        need(sha(root/'input.elf') == plan['cases'][0]['sha256'] and raw['command_sha256'] == sha(root/'command.json'), 'Private ELF/command binding')
        command = read(SOURCE/'collector_command.json')
        need(command['collector_sha256'] == sha(SOURCE.parent/'collect.py') == plan['pins'][str(SOURCE.parent/'collect.py')] and
             sha(SOURCE.parent/'exit_hook.py') == plan['pins'][str(SOURCE.parent/'exit_hook.py')], 'Actual pinned callback')
        checked, inherited = 0, []
        for mapping in (plan['pins'],end['evidence_pins'],end['approval_pins']):
            for name, digest in mapping.items():
                path = Path(name)
                if path.suffix == '.csv' or path.stat().st_size > 10000000:
                    inherited.append(dict(path=name,sha256=digest,bytes=path.stat().st_size))
                    continue
                need(sha(path) == digest, 'Small evidence pin drift: ' + name)
                checked += 1
        result.update(status='ACCEPTED_M9_FULL4095_METADATA_TERMINAL_NOT_LINUX',plan_sha256=PLAN,
            scope={k:strict[k] for k in keys},required_owners=23085,actual_monitor=raw,actual_service=service,
            actual_collector_wait=waited,plan_pins=len(plan['pins']),small_pin_checks=checked,
            inherited_large_pins=inherited,rows=strict['rows'],retired=strict['retired'],
            evidence_pins={str(SOURCE/n):sha(SOURCE/n) for n in
                ('plan.json','complete.json','service_exit.json','collector_result.json','collector_exit.json','collector_command.json')})
    except Exception as error:
        result['firstcause'] = type(error).__name__ + ': ' + str(error)
    result['finished'] = time.time()
    save(OUT/'result.json',result)
    return int(result['status'] != 'ACCEPTED_M9_FULL4095_METADATA_TERMINAL_NOT_LINUX')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    if args.audit:
        return audit()
    need(sha(SOURCE/'plan.json') == PLAN, 'Original plan before attachment')
    need(sha(WAIT) == 'cbc78208bc6464aad86a485f296006f17a31b272d9ef8332617a98caf2b45dd4', 'Existing event-wait helper identity')
    OUT.mkdir()
    save(OUT/'binding.json',dict(source=str(SOURCE),plan_sha256=PLAN,waiter_sha256=sha(WAIT),
        worker_sha256=sha(Path(__file__)),observation_budget_s=1800,audit_budget_s=120,
        no_simulator_restart=True,no_active_CSV_reads=True))
    deadline = time.monotonic() + 1800
    for name in ('complete.json','service_exit.json','collector_result.json','collector_exit.json'):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            save(OUT/'NOT_COMPLETED.json',dict(status='OBSERVATION_TIMEOUT_NOT_JOB_FAILURE',waiting_for=name))
            return 2
        command = [sys.executable,'-B',str(WAIT),str(SOURCE/name),'--timeout',str(remaining)]
        start = time.monotonic()
        with (OUT/(name+'.wait.log')).open('x') as log:
            child = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
            rc = child.wait()
        save(OUT/(name+'.wait.json'),dict(command=command,pid=child.pid,actual_wait_returncode=rc,elapsed_s=time.monotonic()-start))
        if rc:
            save(OUT/'NOT_COMPLETED.json',dict(status='OBSERVATION_NOT_COMPLETED_NOT_JOB_FAILURE',waiting_for=name,wait_rc=rc))
            return rc
    command = [sys.executable,'-B',str(Path(__file__).resolve()),'--audit']
    start = time.monotonic()
    with (OUT/'audit.log').open('x') as log:
        child = subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        timed = False
        try:
            rc = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
    save(OUT/'audit_wait.json',dict(command=command,pid=child.pid,actual_wait_returncode=rc,
        elapsed_s=time.monotonic()-start,timed_out=timed,retries=0))
    report = read(OUT/'result.json') if (OUT/'result.json').exists() else {}
    with (OUT/'FINAL_TERMINAL_REVIEW.md').open('x') as stream:
        stream.write('# Full E8 M4 Terminal Review\n\n')
        status = report.get('status','AUDIT_NOT_COMPLETED') if rc == 0 and not timed else 'NOT_ACCEPTED_AUDIT_EXIT'
        stream.write('Status: '+status+'\n\n')
        stream.write('Actual audit wait: '+str(rc)+'; timeout='+str(timed)+'. No CSV read, semantic reparse or DUT restart.\n\n')
        stream.write('Scope: original contiguous4095,2096640 results,8190 guards,4095 vstart,53235 helper instructions,266175 reads,23085 necessary owners; not Linux.\n\n')
        stream.write('First cause: '+report.get('firstcause','none')+'\n')
    return rc if not timed else 124


if __name__ == '__main__':
    raise SystemExit(main())
