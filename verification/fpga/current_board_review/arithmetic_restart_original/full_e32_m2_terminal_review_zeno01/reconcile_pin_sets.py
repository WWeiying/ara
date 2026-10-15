"""Set reconciliation only: reads small JSON manifests, not raw/log contents."""
import hashlib,json
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent;A=HERE.parent
P=A/'full_e32_m2_block_vcs_m9_plan01/prepared01'
ENTRY=A/'e32_m2_block_m9_entry_review01/result.json'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=read(HERE/'REVIEW.json');p=read(P/'plan.json');e=read(ENTRY);end=read(P/'complete.json');c=read(P/'collector_result.json')
exclude=r['raw_and_log_pins_not_rehashed'];checked=r['pins']
plan_skipped={k:v for k,v in exclude.items() if k in p['pins']}
plan_checked={k:v for k,v in checked.items() if k in p['pins']}
added={k:v for k,v in checked.items() if k not in p['pins']}
missing=sorted(set(p['pins'])-set(checked)-set(exclude))
def category(path):
    if '/software01/host_original/' in path:return 'native_original_compile_and_cases'
    if '/software01/host_packed/' in path:return 'native_packed_compile_and_cases'
    if '/software01/host_' in path:return 'six_native_negative_compile_and_case_logs'
    if '/software01/soc/' in path or '/software01/spike/' in path:return 'cross_compile_and_size_logs'
    if path.endswith('/reference01/commits.log'):return 'source_reference_raw_commit_log'
    if '/reference_entry01/host.log' in path:return 'source_reference_host_log'
    if '/prepared01/replay/' in path:return 'DUT_raw_CSV_and_console_run_logs'
    return 'worker_Host01_Host02_logs'
groups={}
for path,digest in exclude.items():groups.setdefault(category(path),{})[path]=digest
assert len(p['pins'])==903 and e['pins']==p['pins']
assert len(plan_checked)==857 and len(plan_skipped)==46 and len(added)==16
assert len(checked)==873 and len(exclude)==49 and missing==[]
assert e['verification']['non_raw_pins_rehashed']==902 and e['verification']['accepted_raw_pin_receipt_bound_not_reread']==1
assert end['pins_unchanged'] and c['pins_pre_post_unchanged']
assert end['approval_pins'][str(ENTRY)]==sha(ENTRY)==checked[str(ENTRY)]
assert c['complete_sha256']==sha(P/'complete.json') and c['strict_report_sha256']==sha(P/'replay/tests'/p['cases'][0]['id']/'strict_original.json')
assert all(p['pins'][k]==v for k,v in plan_skipped.items())
out=dict(status='PIN_SET_RECONCILED_NO_UNEXPLAINED_OMISSION',
    plan_pins=903,entry_bound_pins=len(e['pins']),entry_rehashed=902,entry_inherited_reference_raw_pin=1,
    terminal_plan_nonraw_checked=857,terminal_plan_logs_raw_not_rehashed=46,
    terminal_added_nonraw=16,terminal_nonraw_total=873,terminal_all_excluded=49,
    additional_excluded_DUT_evidence=3,
    arithmetic='903 - 46 + 16 = 873; entry 902 rehash + 1 accepted source raw = 903 bound pins',
    unexplained_plan_omissions=missing,entry_vs_plan_pin_difference=[],
    excluded_category_counts={k:len(v) for k,v in groups.items()},
    excluded_paths_and_inherited_hashes=groups,added_nonraw_paths_and_current_hashes=added,
    authorities=dict(entry_path=str(ENTRY),entry_sha256=sha(ENTRY),entry_verification=e['verification'],
        plan_sha256=sha(P/'plan.json'),complete_path=str(P/'complete.json'),complete_sha256=sha(P/'complete.json'),
        producer_terminal_pins_unchanged=end['pins_unchanged'],producer_evidence_pins=end['evidence_pins'],
        collector_path=str(P/'collector_result.json'),collector_sha256=sha(P/'collector_result.json'),
        collector_pins_pre_post_unchanged=c['pins_pre_post_unchanged'],
        collector_complete_sha256=c['complete_sha256'],collector_strict_report_sha256=c['strict_report_sha256'],
        collector_actual_csv_sha256=c['csv_sha256'],
        strict_and_complete_and_collector_raw_hash_equal=True,
        receipt_paths=[str(P/'service_exit.json'),str(P/'collector_exit.json'),str(HERE/'review_execution01.json')]),
    independence_limit='873 current nonraw hashes plus inherited raw/log pin chain; not 903 independent fresh file hashes',
    raw_and_log_content_reads=0,large_file_rehashes=0,e64_progress_queries=0)
with (HERE/'PIN_RECONCILIATION.json').open('x') as f:json.dump(out,f,indent=2);f.write('\n')
print(json.dumps({k:out[k] for k in ('status','arithmetic','excluded_category_counts','unexplained_plan_omissions')},indent=2))

