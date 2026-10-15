"""Metadata/hash review only. Never opens DUT CSV or reference commit logs."""
import hashlib
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
AUDIT = BASE/'full_e32_mf2_terminal_audit01'
A = AUDIT/'run01'
WORK = BASE/'full_e32_mf2_vcs_m6_plan01'
RUN = WORK/'prepared01'
ROOT = RUN/'replay/tests/arithmetic_full_e32_mf2'
RAW = ROOT/'commit_trace.csv'
SKIP = {str(RAW)} | {str(BASE/'full_small2_prepare01'/s/'reference01/commits.log')
                           for s in ('rvv_matrix_e8_mf8','rvv_matrix_e32_mf2')}


def need(ok, message):
    if not ok: raise ValueError(message)


def read(p):
    need(str(p) not in SKIP,'Raw read forbidden')
    return json.loads(p.read_text())


def sha(p):
    p = Path(p)
    need(str(p) not in SKIP and p.suffix != '.csv','Raw hash reread forbidden')
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


start = time.monotonic()
need(sha(AUDIT/'READY.json') == 'b9df628b3ed8cee4b14d2a44d5e9b04cd35584caa7818922348acd4c31cd15cf','READY drift')
need(sha(AUDIT/'pins.json') == '8035e1ec3b1102989b07f830c9f4b3f25220e506dece1e0a025d218043b92303','Auditor pin drift')
terminal, report, exit_record = (read(A/n) for n in ('TERMINAL.json','candidate_report.json','audit_process_exit.json'))
need(terminal['status'] == 'INDEPENDENT_FULL_E32_MF2_TERMINAL_ACCEPTED' and
     terminal['report_sha256'] == sha(A/'candidate_report.json') and
     terminal['actual_audit_exit_sha256'] == sha(A/'audit_process_exit.json'),'Terminal hash chain')
need(type(exit_record['returncode']) is int and exit_record['returncode'] == 0 and
     not exit_record['timed_out'] and exit_record['error'] is None and exit_record['attempt'] == 1 and
     exit_record['elapsed_s'] <= 900,'Actual auditor numeric exit')
need(not (A/'FIRST_ERROR.json').exists(),'Auditor failure marker')
complete = read(RUN/'complete.json')
need(report['complete_sha256'] == sha(RUN/'complete.json') and
     complete['status'] == 'PASS_M6_FULL_ORIGINAL_E32_MF2_5985_CALLS_NOT_LINUX' and
     complete['aborted'] is False and complete['pins_unchanged'] is True and
     complete['retries'] == 0 and not complete.get('error') and not complete.get('first_failure'), 'Worker final gate')
need(terminal['plan_sha256'] == complete['plan_sha256'] == sha(RUN/'plan.json') ==
     'b75d801b6533b73bfa9127ff695b60642a421535f9528202b07248fc3f368c93','Exact plan chain')
pins = dict(read(AUDIT/'pins.json'))
pins.update(complete['approval_pins'])
pins.update(complete['evidence_pins'])
checked, skipped = [], {}
for p,digest in pins.items():
    if p in SKIP:
        skipped[p] = digest
    else:
        need(sha(p) == digest,'Changed evidence: '+p)
        checked.append(p)
summary, meta = read(RUN/'replay/summary.json'),read(RUN/'replay/run.json')
need(complete['results'] == summary and len(summary) == 1 and summary[0]['status'] == 'PASS' and
     type(summary[0]['returncode']) is int and summary[0]['returncode'] == 0 and not summary[0]['reason'], 'Whole1 result')
need(meta['status'] == 'COMPLETE' and meta['status_counts'] == {'PASS':1} and meta['jobs'] == 1 and
     meta['timeout_s'] == 10800 and meta['tests'] == ['arithmetic_full_e32_mf2'], 'Whole1 runner metadata')
outcome, command = read(ROOT/'child_outcome.unvalidated.json'),read(ROOT/'command.json')
need(type(outcome['returncode']) is int and outcome['returncode'] == 0 and not outcome['timed_out'] and
     not outcome['failure_seen'] and not outcome['cancelled'] and outcome['elapsed_s'] == summary[0]['elapsed_s'] <= 10800
     and outcome['command_sha256'] == sha(ROOT/'command.json') and outcome['command'] == command['command'] and
     outcome['cwd'] == command['cwd'],'Numeric simulator exit/command')
need(len(report['reports']) == 1 and report['raw_parses'] == terminal['raw_parses'] == 1 and
     report['reference_raw_parses'] == 0 and report['pins_unchanged'] is True,'Single raw pass')
item = report['reports'][0]
need(item['report_sha256'] == sha(A/'arithmetic_full_e32_mf2.json'),'Case report hash')
case = read(A/'arithmetic_full_e32_mf2.json')
strict, generic = case['strict'],case['generic']
need(strict == read(ROOT/'strict_original.json') and dict(status='VALID',**generic) == read(ROOT/'trace_summary.json'),
     'Worker/auditor exact report equality')
need(item['csv_sha256'] == case['raw_sha256'] == complete['evidence_pins'][str(RAW)], 'Recorded single-pass raw hash chain')
need([strict[k] for k in ('calls','results','guards','vstart_checks','helper_instructions')] ==
     [5985,95760,11970,5985,77805] and strict['full_order'] is True and strict['partitioned'] is False,
     'Original full e32 totals')
plan = read(RUN/'plan.json')
gold = read(BASE/'full_small2_prepare01/rvv_matrix_e32_mf2/model.json')
helpers = plan['specs']['rvv_matrix_e32_mf2']['backend']['helpers']
need(len(strict['call_ledger']) == len(gold) == 5985,'All call ledger entries')
for ordinal,(c,g) in enumerate(zip(strict['call_ledger'],gold)):
    target = helpers['op_'+str(g['op'])][8]
    need(c['ordinal'] == ordinal and all(c[k] == g[k] for k in ('op','seed','vl','mode','vstart')) and
         c['reads'] == list(range(18)) and c['returned_vstart'] == 0 and
         c['target_pc'] == target['pc'], 'Original ordered call ledger: '+str(ordinal))
need({c['op'] for c in strict['call_ledger']} == set(range(35)) and
     {c['seed'] for c in strict['call_ledger']} == {0,1,2},'All original ops/seeds')
need(generic['cvx_request_count'] == generic['cvx_response_count'] == generic['architecture_request_count'] == 65838 and
     generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] == 33687 and
     generic['cvx_exception_count'] == generic['cvx_replay_count'] == generic['arch_request_replay_count'] == 0,
     'Six-event paired protocol ledger')
need(generic['rows'] == generic['retire_count']+generic['cvx_request_count']+generic['cvx_response_count']+
     generic['architecture_request_count']+generic['backend_uop_alloc_count']+generic['backend_uop_done_count'],
     'Lossless six-event count sum')
event = read(A/'worker_exit_event.json')
need(event['mode'] == 'pidfd_exit' and event['pid'] == 1691221 and report['cgroup']['state'] in ('empty','removed'),
     'Recorded exited worker/empty cgroup')
stat = RAW.stat()  # Identity metadata only; do not reopen the raw CSV.
evidence = [A/n for n in ('TERMINAL.json','candidate_report.json','audit_process_exit.json',
                         'worker_exit_event.json','arithmetic_full_e32_mf2.json')]
evidence += [RUN/'complete.json',ROOT/'child_outcome.unvalidated.json',HERE/'review.py']
result = dict(status='ACCEPT_E32_FULL5985_TERMINAL_METADATA',blocking_findings=[],
              metadata_only=True,new_DUT_CSV_reads=0,new_reference_raw_reads=0,new_simulations=0,
              nonraw_unique_pins_verified=len(checked),skipped_raw_pins=skipped,
              evidence_pins={str(p):sha(p) for p in evidence},
              simulator_numeric_exit=outcome['returncode'],simulator_elapsed_s=outcome['elapsed_s'],
              audit_process_exit=exit_record,generic=generic,
              strict_summary={k:v for k,v in strict.items() if k != 'call_ledger'},
              call_ledger_entries_checked=5985,original_operations=35,original_seeds=3,
              raw_sha256_from_verified_auditor_chain=case['raw_sha256'],
              current_raw_stat_only=[stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns],
              service_exit_status='UNCONFIRMED_NOT_INFERRED',worker_cgroup_at_audit=report['cgroup'],
              scope='Original reconstructed byte-equivalent e32 mf2 SoC full program; not Linux/all22',
              historical_small2_NOT_PASS_and_cancelled_e32_preserved=True,elapsed_s=time.monotonic()-start)
with (HERE/'REVIEW.json').open('x') as f:
    json.dump(result,f,indent=2); f.write('\n')
print(result['status'],sha(HERE/'REVIEW.json'),flush=True)
