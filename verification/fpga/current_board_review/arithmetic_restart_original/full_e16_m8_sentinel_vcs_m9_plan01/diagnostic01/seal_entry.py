"""Freeze the exact single-pass diagnostic and actual short Host evidence."""
import diagnostic as d
host=d.read(d.HERE/'host.json');wait=d.read(d.HERE/'host_wait.json')
d.need(host['status']=='HOST_ONLY_PASS' and host['tests']==18 and host['actual_csv_reads']==0,'Actual18 short negatives/positive')
d.need(wait['actual_wait_returncode']==0 and not wait['timed_out'] and wait['retries']==0,'Actual Host numeric wait')
for p,h in host['pins'].items():d.need(d.sha(p)==h,'Host-consumed pin drift '+p)
_,pins=d.inputs()
p=d.OLD/'host_records.py';plan=d.read(d.PREP/'plan.json')
d.need(d.sha(p)==plan['pins'][str(p)],'Actual inherited fixture Builder')
pins[str(p)]=d.sha(p)
for name in ('host.json','host_wait.json','host_command.json','README.md','seal_entry.py'):
    p=d.HERE/name;pins[str(p)]=d.sha(p)
d.save(d.HERE/'ENTRY.json',dict(status='PREPARED_SINGLE_CLOSED_TIMEOUT_DIAGNOSTIC_NOT_RUN',
    producer_plan_sha256=d.PLAN_SHA,checker_sha256=d.CHECKER_SHA,private_ELF_sha256=d.base.ELF_SHA,
    csv_path=str(d.TRACE),csv_expected_bytes=296607084,pins=pins,pin_count=len(pins),
    strict_source_unchanged=True,full4095_model_retained=True,EOF_completion_only_qualified=True,
    full_program_finish_called=False,architectural_acceptance=False,max_scans=1,semantic_passes=1,
    raw_open_count=1,hash_same_pass=True,raw_preflight_reads=0,
    wall_bound_s=600,no_retry=True,DUT_authorized=False,current_worktree_runner_consumed=False,
    actual_Host_execution_sha256=d.sha(d.HERE/'host_wait.json'),short_Host_sha256=d.sha(d.HERE/'host.json'),
    short_tests=18,short_fixture_scope='first call and next entry only; constructed8288 rows, no fullstream',
    parent_conditional_authorization='Latest parent task: exact Hilbert NO_BLOCKER then ONE <=600s closed scan, no further parent wait',
    invocation=['python3','-B',str(d.HERE/'run_once.py'),'diagnose','ACTUAL_REVIEW_PATH','ACTUAL_REVIEW_SHA256'],
    required_review_status='NO_BLOCKER_ONE_CLOSED_TIMEOUT_DIAGNOSTIC'))
print('ENTRY',d.sha(d.HERE/'ENTRY.json'),'pins',len(pins))
