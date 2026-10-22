"""Metadata/hash-only final independent dynamic checker binding; no raw reparse."""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OWNER=HERE.parent/'full682_vcs_m8_plan01'
PREP=HERE.parent/'full682_packed_prepare01'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def check(pins):
    for p,h in pins.items():assert sha(p)==h,p
def main():
    ready=read(PREP/'READY.json')
    assert sha(PREP/'READY.json')=='64f82d0e893179b253b4cced76f6f73b7820f1427b865889bd127c7d9eee62e4'
    assert sha(PREP/'pins.json')==ready['pins_sha256']
    pins=read(PREP/'pins.json');check(pins)
    for name in ('host_strict02.json','host_worker01.json'):
        host=read(OWNER/name)
        assert host['failures']==host['errors']==0
        assert host['status'] in ('PASS_HOST_ONLY','PASS_HOST_ONLY_NOT_DUT')
        check(host['pins'])
        for p,h in host['pins'].items():assert p not in pins or pins[p]==h; pins[p]=h
    assert read(OWNER/'host_worker01.json')['tests']==7
    ref=read(OWNER/'reference01/result.json');execution=read(OWNER/'reference01/execution.json')
    assert type(execution['returncode']) is int and execution['returncode']==0 and not execution['timed_out']
    assert ref['actual_process']==execution and ref['pins_unchanged'] and ref['full_reference_vectors']
    assert ref['status']=='FULL_ORIGINAL682_STRICT_ACCEPTED_NOT_FULL_PARENT'
    assert [ref[k] for k in ('target_calls','helper_instructions','full_result_bit_checks','result_bytes','guard_checks','returned_flags_checked','returned_vstart_zero')]==[682,12592,349184,43648,1364,682,682]
    assert len(ref['retired_offloads'])==6141 and sum(x['backend_required'] for x in ref['retired_offloads'])==3306
    assert len(ref['calls'])==682 and all(x['ordinal']==i+1 and x['reads']==195 and x['vstart']==0 for i,x in enumerate(ref['calls']))
    assert ref['firmware_retired_to_exit']==2123855
    assert sha(OWNER/'reference01/commits.log')==ref['raw_sha256']
    refpins=read(OWNER/'reference01/input_pins.json');check(refpins)
    for p,h in refpins.items():assert p not in pins or pins[p]==h; pins[p]=h
    proto=read(HERE/'protocol_evidence.json')
    assert proto['status']=='REAL_FROZEN_M8_PROTOCOL_COMPOSITION_HOST_PASS_NOT_FULL682' and not proto['schema_has_status']
    assert len(proto['negative'])==5 and all(x['generic_accepted'] for x in proto['negative'])
    check(proto['pins'])
    for p,h in proto['pins'].items():assert p not in pins or pins[p]==h; pins[p]=h
    assert read(HERE/'model_evidence.json')['pairs']==1536
    paths=list(OWNER.glob('*.py'))+[OWNER/n for n in ('host_strict01.json','host_strict02.json','host_worker01.json','USER_AUTHORIZATION.md')]
    paths += [OWNER/'reference01'/n for n in ('result.json','execution.json','command.json','input_pins.json','commits.log')]
    paths += [HERE/n for n in ('REVIEW.md','model_evidence.json','protocol_evidence.json','model_probe.py','protocol_probe.py','finalize_binding.py')]
    paths += [PREP/'READY.json',PREP/'pins.json']
    paths += [Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image/image.json')]
    for p in paths:
        h=sha(p);assert str(p) not in pins or pins[str(p)]==h;pins[str(p)]=h
    check(pins)
    result=dict(ready_sha256=sha(PREP/'READY.json'),decision='NO_BLOCKER_DYNAMIC_CHECKER',
       pins=pins,checker_sha256=sha(OWNER/'strict.py'),runner_sha256=sha(OWNER/'replay.py'),
       composition_sha256=sha(OWNER/'checker.py'),review_path=str(HERE/'REVIEW.md'),
       review_sha256=sha(HERE/'REVIEW.md'),blocking_findings=[],
       actual_reference=dict(returncode=execution['returncode'],elapsed_s=execution['elapsed_s'],
         audit_s=ref['audit_s'],calls=682,offloads=6141,minimum_backend_arches=3306,
         firmware_to_exit=2123855,full_result_bits=349184,guards=1364),
       real_generic_schema_verified=True,event_drop_duplicate_reorder_negatives_passed=True,
       independent_raw_reparse=False,metadata_and_hash_review_only_of_producer_raw_acceptance=True,
       scope='Original first682/681predecessors, CAP512/e16m8/alias-v8/unmasked/vstart0; not full17920/Linux ABI',
       launch_authorization='Existing user authorization remains subject to all sealed plan/Host/reference/dryrun/resource gates; this review does not itself launch',
       no_new_DUT=True,owner_files_modified=False,pins_pre_post_unchanged=True)
    with (HERE/'entry_binding.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
    print('NO_BLOCKER_DYNAMIC_CHECKER',sha(HERE/'entry_binding.json'),len(pins))
if __name__=='__main__':main()

