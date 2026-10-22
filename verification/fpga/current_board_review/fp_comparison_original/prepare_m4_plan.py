#!/usr/bin/env python3
"""Prepare only: exact three-prefix M4 replay, checks, and reviewable budgets.

There is deliberately no DUT launch entry point in this preparation script.
"""
import collections
import csv
import math
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from recover import HERE, read, save, sha
sys.path.insert(0,str(HERE.parent/'comparison_alias_original'))
import replay19 as shared_adapter

shared=shared_adapter.shared
IMAGE=Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA='e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
PREPARED=HERE/'prepared02'
FINAL38=HERE.parent/'integration/candidate04_regression38_03'
EXPECTED={'alias_v8_e16m8_prefix682':682,'restart_e16m2_prefix130':130,
          'restart_unmasked_e16m2_prefix130':130}
BAD=re.compile(r'\bRVV_[A-Z0-9_]*(?:FAIL|DETAIL)\b|BOARD_CASE_FAIL|'
    r'BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|'
    r'\b(?:MATRIX_FAIL|EXTENSION_MATRIX_FAIL|EXTENDED_FAIL|EPOCH_FAIL|SKIP)\b|'
    r'Core Test \*\*\* FAIL|Error-\[|Fatal[-:]|UVM_FATAL|Assertion[^\n]*failed')


def strict_console(entry,text):
    lines=[s.strip() for s in text.splitlines()]
    summaries=re.findall(r'^RVV_FP_COMPARE_PASS sew=(\d+) cases=(\d+) errors=(\d+)\s*$',text,re.M)
    return (not BAD.search(text) and summaries==[('16',str(entry['calls']),'0')]
        and all(lines.count(marker)==1 for marker in entry['pass_markers'])
        and 'Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text)


def check_trace(entry,path):
    targets={int(x['pc'],16):x for x in entry['target_retirements']}
    found=collections.Counter(); retired=0; last=-1
    with path.open() as stream:
        for row in csv.DictReader(stream):
            cycle=int(row['cycle']); assert cycle>=last,'Nonmonotonic trace'
            last=cycle
            if row['event']!='retire':continue
            assert int(row['trap'],0)==0 and int(row['order'])==retired,'Trap or missing retire row'
            retired+=1; pc=int(row['pc'],16)
            if pc in targets:
                assert int(row['insn'],16)==int(targets[pc]['opcode'],16),'Wrong target instruction'
                found[pc]+=1
    assert retired>0 and all(found[pc]==x['calls'] for pc,x in targets.items()),'Missing or duplicated original target'
    return dict(retired=retired,last_cycle=last,target_counts={hex(pc):found[pc] for pc in targets})


def checked_result(result,entry,text,cancel):
    if result.status!='PASS' or result.returncode!=0 or not strict_console(entry,text):
        cancel.set()
        if result.status=='PASS':result.status,result.reason='FAIL','Strict original oracle/raw exit veto'
    return result


def runner_class(parent,entries):
    class Checked(parent):
        def _run_test(self,test,image):
            try:
                result=super()._run_test(test,image)
                if result.status=='PASS':
                    checked_result(result,entries[test.name],(result.artifact_dir/'console.log').read_text(),self.cancel_event)
                    if result.status=='PASS':
                        save(result.artifact_dir/'architectural_trace_audit.json',
                             check_trace(entries[test.name],result.artifact_dir/'commit_trace.csv'))
                elif result.status!='DRY_RUN':self.cancel_event.set()
                return result
            except BaseException:
                self.cancel_event.set()
                raise
    return Checked


def completed38(plan,terminal):
    rows=terminal.get('results',[])
    return (terminal.get('status')=='PASS_38_CANDIDATE04' and terminal.get('pins_unchanged') is True
        and terminal.get('image_sha256')==IMAGE_SHA and len(rows)==38
        and {x['name'] for x in rows}=={x['id'] for x in plan['cases']}
        and all(x['status']=='PASS' and x['returncode']==0 for x in rows))


def self_test():
    import tempfile
    import threading
    from types import SimpleNamespace
    entry=dict(calls=130,pass_markers=['RVV_FP_COMPARE_PASS sew=16 cases=130 errors=0',
        'BOARD_CASE_PASS sample','BOARD_REPLAY_PASS'])
    good='\n'.join(entry['pass_markers'])+'\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    checks=[]
    def test(name,value):
        assert value,name
        checks.append(name)
    test('complete_original_oracle',strict_console(entry,good))
    for marker in ['RVV_FP_COMPARE_FAIL','RVV_FP_COMPARE_DETAIL','RVV_FP_COMPARE_CAPACITY_FAIL',
                   'RVV_OTHER_FAIL','BOARD_REPLAY_TRAP','MATRIX_FAIL','EXTENSION_MATRIX_FAIL',
                   'EXTENDED_FAIL','EPOCH_FAIL','SKIP','Error-[SIM]']:
        test('veto_'+marker,not strict_console(entry,good+'\n'+marker))
    for marker in entry['pass_markers']+['Core Test *** SUCCESS *** (tohost = 0)','$finish']:
        test('missing_'+marker,not strict_console(entry,good.replace(marker,'')))
    test('wrong_count',not strict_console(entry,good.replace('cases=130','cases=129')))
    test('duplicate_pass',not strict_console(entry,good+'\n'+entry['pass_markers'][0]))
    event=threading.Event(); result=SimpleNamespace(status='PASS',returncode=1,reason='')
    checked_result(result,entry,good,event)
    test('nonzero_exit_cancels',result.status=='FAIL' and event.is_set())
    class Broken:
        def _run_test(self,test,image):raise OSError('missing console')
    instance=runner_class(Broken,{})()
    instance.cancel_event=threading.Event()
    try:instance._run_test(None,None)
    except OSError:pass
    test('exception_cancels',instance.cancel_event.is_set())
    test('empty38_not_pass',not completed38({'cases':[]},dict(status='PASS_38_CANDIDATE04',results=[])))
    trace_entry=dict(target_retirements=[dict(pc='80000508',opcode='62881457',calls=1)])
    with tempfile.TemporaryDirectory() as d:
        path=Path(d)/'trace.csv'
        header='cycle,event,order,pc,insn,trap\n'
        row='1,retire,0,80000508,62881457,0\n'
        path.write_text(header+row)
        test('trace_positive',check_trace(trace_entry,path)['retired']==1)
        for name,content in [('missing_target',header),('wrong_opcode',header+row.replace('62881457','62881456')),
            ('trap',header+row[:-2]+'1\n'),('missing_retire',header+row.replace('retire,0','retire,1'))]:
            path.write_text(content)
            try:check_trace(trace_entry,path)
            except AssertionError:test(name,True)
            else:raise AssertionError(name)
    return checks


def main():
    out=HERE/'candidate04_plan03'; out.mkdir(exist_ok=False)
    checks=self_test(); save(out/'host_checks.json',dict(status='PASS',checks=checks,count=len(checks)))
    assert sha(IMAGE/'image.json')==IMAGE_SHA
    ledger=read(IMAGE/'image.json'); snap=Path(ledger['snapshot']); simv=Path(ledger['simv'])
    assert sha(snap/'snapshot.json')==ledger['snapshot_sha256']
    repo=shared.sealed(snap)
    _,_,_,identity=shared.framework(repo)
    assert identity(simv)==ledger['files']
    assert sha(simv.parent/'simulator.conf')==ledger['configuration_sha256']
    manifest=simv.parent/'vcs_source_manifest.json'
    assert sha(manifest)==ledger['manifest_sha256']
    from ara_verify.vcs_source_manifest import collect
    capture=read(manifest)
    assert collect(Path(capture['filelist']),repo,[Path(p) for p in capture['extra_sources']])==capture['files']
    programs=read(PREPARED/'soc/programs.json')
    assert set(programs['programs'])==set(EXPECTED) and programs['backend']=='vcs-soc'
    assert read(PREPARED/'reference.json')['status']=='PASS_3_BOUNDED_ORIGINAL_PREFIXES_NOT_DUT'
    assert read(HERE/'ready_audit01/finding.json')['status']=='READY_3_PREFIXES_HOST_SPIKE_NOT_DUT'
    pins=dict(read(PREPARED/'pins.json'))
    for source in (HERE/'ready_audit01/pins.json',HERE/'budget01/pins.json'):pins.update(read(source))
    pins.update(ledger['files'])
    pins.update({str(repo/p):h for p,h in read(snap/'snapshot.json')['files'].items()})
    paths=[p for p in PREPARED.rglob('*') if p.is_file()]
    paths += [Path(__file__),Path(shared.__file__),Path(shared_adapter.__file__),
        IMAGE/'image.json',snap/'snapshot.json',simv.parent/'simulator.conf',manifest,
        HERE/'budget01/finding.json',FINAL38/'plan.json',out/'host_checks.json']
    for p in paths:pins[str(p.resolve())]=sha(p)
    shared_adapter.verify(pins)
    measured=read(HERE/'budget01/finding.json'); maps=read(PREPARED/'address_map.json')
    cases=[]
    for count in measured['counts']:
        name=count['name']; entry=programs['programs'][name]
        sequence=read(PREPARED/'prepared'/name/'call_sequence.json')
        assert len(sequence)==EXPECTED[name]
        ops=collections.Counter(x['op'] for x in sequence)
        # FP long-run calibration is600..679 retire/s; allow500 then1.5x+120s.
        estimate=count['retired']/500
        timeout=math.ceil((estimate*1.5+120)/300)*300
        cases.append(dict(id=name,elf=entry['path'],sha256=entry['sha256'],calls=EXPECTED[name],
            pass_markers=entry['pass_markers'],spike_retired=count['retired'],estimate_s=estimate,
            timeout_s=timeout,estimate_at330_retire_s=count['retired']/330,
            target_retirements=[dict(pc=pc,opcode=opcode,instruction=asm,calls=ops[i])
                for i,(pc,opcode,asm) in enumerate(maps[name]['soc']['targets'])]))
    plan=dict(schema_version=1,status='PREPARED_NOT_AUTHORIZED',scope='Three bounded original prefixes only, not237 parent acceptance',
        image=str(IMAGE),image_sha256=IMAGE_SHA,snapshot=str(snap),programs=str(PREPARED/'soc'),pins=pins,cases=cases,
        jobs=2,stop_first_fail=True,no_build=True,no_software_rebuild=True,launch_entrypoint_present=False,
        checker=dict(raw_failure_veto=BAD.pattern,require_zero_returncode=True,require_success_tohost_zero=True,
            require_finish=True,require_exact_original_pass_count=True,trace_exact_target_counts=True,
            exception_cancels_all=True),
        resources=dict(global_cap=24,mem_floor_gib=32,reserved_others_after_all_gates=dict(whole=6,NF7=2,NF8=8,gather=0,prefix5=2),
            own_reserved_slots=2,current_reservation_includes_running38=24,
            admission='Require38PASS/workers released, Gather75 terminal/workers released, NF8 first admission, and explicit parent coordination. Gather per-case admission reserves old38four, so its first admission is NOT enough. Do not start FP/prefix while Gather75 remains live. At startup/every dispatch: external live simv+own2<=24 and preserve unoccupied reservations; no automatic capacity retry.'),
        gates=dict(final38_terminal=str(FINAL38/'complete.json'),final38_plan_sha256=sha(FINAL38/'plan.json'),
            final38_terminal_not_read=True,require_parent_approval_of_this_exact_plan_hash=True,
            require_explicit_long_budget_approval=True,require_final38_service_and_workers_released=True,
            require_nf8_initial_admission_before_fp=True,
            require_gather75_terminal_and_workers_released_before_fp=True,
            gather_initial_admission_is_not_sufficient=True,
            require_parent_confirmation_of_old38_reservation_accounting=True,
            admission_evidence_paths_not_yet_supplied=True,
            require_pins_unchanged_before_after=True),
        budget=dict(formula='ceil_to300(1.5 * measured_Spike_retired / 500 + 120)',
            basis='Completed M2 FP matrix600..679 retire/s; M4 integer controls109..488 retire/s, small-startup and opcode differences; no current38 polling',
            raw_budget01_tiny_control_minimum_rejected_as_nonrepresentative=True,
            inner_sum_s=sum(c['timeout_s'] for c in cases),two_job_schedule_upper_s=max(c['timeout_s'] for c in cases),
            proposed_outer_s=64800,warning='682calls is20.26M scalar retirements, hours not minutes. At330 retire/s its nominal duration already exceeds proposed inner bound; requires parent choice, not an automatic timeout increase.',
            no_dut_timing_guarantee=True))
    save(out/'plan.json',plan)
    save(out/'preflight.json',dict(status='READY_FOR_REVIEW_NOT_LAUNCHED',plan_sha256=sha(out/'plan.json'),
        jobs=2,cases=len(cases),host_checks=len(checks),pins=len(pins),pins_unchanged=True,
        image_manifest_sources=len(capture['files']),VCS_started=False,final38_polled=False))
    print(read(out/'preflight.json'))


if __name__=='__main__':main()
