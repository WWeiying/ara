"""Static entry evidence; no active NF2 artifacts, CSV, subprocess or service reads."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
F = HERE.parent/'vcs_m6_current96_plan02'
OLD = HERE.parent/'vcs_m6_current96_plan01'
P = F/'prepared01'
PLAN = 'eebd310b9b9ccdf5b5ca398d556b2a7b6d07746c0f4149972130716ab7481cc0'
READY = 'd212cd10f4e25293ea4780997601f57ca71863149f6f9082a007c2f19d49234a'
IMAGE = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')


def functions(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}


def verify(pins):
    for p,h in pins.items(): assert sha(p)==h, ('Pin drift',p)


def main():
    started = time.monotonic()
    assert sha(P/'plan.json')==PLAN and sha(P/'ready.json')==READY
    plan,oldplan = read(P/'plan.json'),read(OLD/'prepared01/plan.json')
    pins = dict(plan['pins']); assert len(pins)==878
    assert sha(OLD/'prepared01/plan.json')=='b29f616c1075ccf06a9294bc970382a5c7d6f897b17339b284a2bb22d829d64a'
    assert len(oldplan['pins'])==840
    # Permit only sealed preparation/code identities under the two active NF2 roots.
    allowed = {'nf2_remaining34_terminal_audit01':{'prepared.json','audit.py','wait_terminal.py'},
               'nf2_remaining34_vcs_m6_plan01/prepared01':{'plan.json'}}
    for p in pins:
        for directory,names in allowed.items():
            marker='/'+directory+'/'
            if marker in p: assert p.split(marker,1)[1] in names, ('Active artifact forbidden',p)
    verify(pins); verify(oldplan['pins'])
    assert plan['cases']==oldplan['cases'] and plan['image_sha256']==oldplan['image_sha256']==IMAGE
    assert plan['budget']==oldplan['budget']
    for name in ('checker.py','observer.py'): assert sha(F/name)==sha(OLD/name)
    oldf,newf = functions(OLD/'replay.py'),functions(F/'replay.py')
    changed = [n for n in oldf if oldf[n]!=newf[n]]
    assert set(changed)=={'validate_contract','prepare','authorization'}
    unchanged = [n for n in oldf if oldf[n]==newf[n]]
    assert all(n in unchanged for n in ('persist_child','monitored','engine_hooks','owner_gate','run','terminal_gate','options','tests','dryrun'))
    spec = importlib.util.spec_from_file_location('reviewed_static_nf2_gate',F/'nf2_gate.py')
    gate = importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
    assert plan['nf2_prerequisite']==gate.contract()
    # This function only reads the fixed prepared.json and source modules.
    static = gate.static_pins()
    assert all(pins[p]==h for p,h in static.items())
    prepared = read(gate.A/'prepared.json')
    assert prepared['plan_sha256']==gate.PLAN_SHA
    assert prepared['pins'][str(gate.A/'audit.py')]==gate.AUDIT_SHA
    assert prepared['pins'][str(gate.A/'wait_terminal.py')]==gate.WAIT_SHA
    # Replay only the prior exact HOLD payload at the new schema boundary.
    # No actual admission, hash read or terminal artifact is reachable on rejection.
    oldpayload = read(HERE.parent/'nf7_m6_entry_review01/synthetic_prerequisite/parent_review.json')['nf2_gate']
    def forbidden(*args,**kwargs): raise AssertionError('Unexpected file read on legacy-schema rejection')
    realsha,realread = gate.sha,gate.read
    gate.sha=gate.read=forbidden
    try:
        try: gate.bind_payload(oldpayload)
        except ValueError as error: rejected = str(error)
        else: raise AssertionError('Old P1 payload still accepted')
    finally: gate.sha,gate.read=realsha,realread
    assert rejected=='Exact independent NF2 evidence schema required; no text attestation'
    host=read(F/'host01/status.json'); log=(F/'host01/log.txt').read_text()
    assert host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['tests']==58 and host['failures']==host['exit_code']==0
    assert sha(F/'host01/log.txt')==host['log_sha256'] and 'Ran 58 tests' in log and log.rstrip().endswith('OK')
    verify(host['pins'])
    tests=[n.name for n in ast.walk(ast.parse((F/'test_nf2_gate.py').read_text())) if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')]
    assert len(tests)==30 and all(n in log for n in tests)
    image=Path(plan['image']); ledger=read(image/'image.json')
    assert sha(image/'image.json')==IMAGE
    snapfile=Path(ledger['snapshot'])/'snapshot.json'; snap=read(snapfile)
    assert sha(snapfile)==plan['snapshot_sha256']==ledger['snapshot_sha256']
    assert snap['state']=='SEALED' and len(snap['files'])==539 and len(ledger['files'])==66
    assert all(pins[p]==h for p,h in ledger['files'].items())
    assert all(pins[str(Path(snap['root'])/p)]==h for p,h in snap['files'].items())
    assert sha(image/'_build/vcs/simulator.conf')==ledger['configuration_sha256']=='6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    cases=plan['cases']; assert [c['id'] for c in cases]==[f'nf7_g{i:02d}' for i in range(24)]
    assert [t for c in cases for t in c['trials']]==list(range(96))
    assert sum(c['checks'] for c in cases)==284816 and sum(c['checkpoints'] for c in cases)==sum(c['traps'] for c in cases)==168
    dry=read(P/'dryrun/run.json'); summary=read(P/'dryrun/summary.json')
    assert dry['status']=='DRY_RUN' and dry['status_counts']=={'DRY_RUN':24}
    assert dry['jobs']==4 and dry['timeout_s']==2400 and dry['seed']==1 and dry['simv']==ledger['simv']
    assert dry['commit_trace'] is True and dry['code_coverage'] is False and dry['contract_monitor'] is False and dry['probe_kinds']==[]
    assert [r['name'] for r in summary]==dry['tests']==[c['id'] for c in cases]
    assert all(r['status']=='DRY_RUN' and r['returncode'] is None for r in summary)
    program_manifest=read(HERE.parent/'vcs_plan06/programs/programs.json')['programs']
    oldpins=read(HERE.parent/'vcs_plan06/plan.json')['pins']
    groups=[]
    for c in cases:
        assert c['sha256']==sha(c['elf'])==program_manifest[c['id']]['sha256']
        source=Path(c['source'])
        for p in [source/n for n in ('soc.elf','soc.symbols.json','soc.dis','cases.json','status.json')]+[Path(c['ledger'])]:
            assert pins[str(p)]==sha(p)
            if str(p) in oldpins: assert oldpins[str(p)]==pins[str(p)]
        path=P/'dryrun/tests'/c['id']/'command.json'
        assert read(path)==dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+c['elf'],
            '+TESTCASE='+c['id'],'+NO_FSDB','+COMMIT_TRACE='+str(path.parent/'commit_trace.csv')],cwd=str(path.parent/'work'))
        pins[str(path)]=sha(path)
        groups.append(dict(id=c['id'],trials=c['trials'],elf_sha256=c['sha256'],checks=c['checks'],
            ledger_sha256=sha(c['ledger']),dryrun_command_sha256=sha(path)))
    for n in ('csv_oracle.py','reference.py'):
        p=HERE.parent/n; assert oldpins[str(p)]==pins[str(p)]==sha(p)
    for p in [F/n for n in ('HANDOFF.md','README.md','host01/status.json','host01/log.txt')]+[
        P/n for n in ('plan.json','ready.json','dryrun_gate.json','dryrun/run.json','dryrun/summary.json')]:
        h=sha(p); assert str(p) not in pins or pins[str(p)]==h; pins[str(p)]=h
    verify(pins)
    save(HERE/'verified_pins.json',pins)
    save(HERE/'evidence.json',dict(status='ENTRY_ACCEPTED_FOR_FUTURE_ADMISSION_ONLY',no_blocker=True,DUT_approved=False,
        plan_sha256=PLAN,ready_sha256=READY,image_sha256=IMAGE,original_plan_pins=878,review_pins=len(pins),
        pins_pre_post_unchanged=True,sealed_plan01_pins_unchanged=840,source_files=539,image_files=66,
        source_trials=96,checks=284816,checkpoints=168,traps=168,groups=groups,
        original_checker_and_observer_byte_identical=True,unchanged_worker_functions=unchanged,changed_worker_functions=changed,
        old_P1_payload='nf7_m6_entry_review01/synthetic_prerequisite/parent_review.json',old_P1_rejection=rejected,
        old_P1_check_artifact_reads=0,Host58_reviewed_not_rerun=True,NF2_existing_tests=tests,dryrun24_reviewed_not_rerun=True,
        prerequisite_contract=gate.contract(),prerequisite_static_pins=len(static),actual_NF2_admission_executed=False,
        active_NF2_artifacts_read=0,CSV_parses=0,service_or_process_queries=0,DUT_launches=0,reference_executions=0,
        script_sha256=sha(Path(__file__)),verified_pins_sha256=sha(HERE/'verified_pins.json'),elapsed_s=time.monotonic()-started))
    print('ENTRY_ACCEPTED_FOR_FUTURE_ADMISSION_ONLY',sha(HERE/'evidence.json'),flush=True)


if __name__=='__main__': main()
