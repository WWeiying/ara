"""Read-only sealed-input review plus a focused, synthetic prerequisite counterexample."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
F = HERE.parent/'vcs_m6_current96_plan01'
P = F/'prepared01'
PLAN = 'b29f616c1075ccf06a9294bc970382a5c7d6f897b17339b284a2bb22d829d64a'
IMAGE = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576),b''): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')


def require(ok,message):
    if not ok: raise ValueError(message)


def verify(pins):
    for p,h in pins.items(): require(sha(p)==h,'Pin drift: '+p)


def prerequisite_counterexample():
    # Execute only the exact authorization function; imports/run/service paths
    # are not loaded. All files and path globals here are synthetic and owned.
    root = HERE/'synthetic_prerequisite'; root.mkdir()
    tree = ast.parse((F/'replay.py').read_text())
    node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='authorization')
    module = ast.Module(body=[node],type_ignores=[])
    ns = dict(require=require,sha=sha,read=read,Path=Path,NF2=root,
        UNIT='ara-nf7-current96-m6-01.service',checker=SimpleNamespace(IMAGE_SHA=IMAGE),
        common=SimpleNamespace(base=SimpleNamespace(verify_pins=verify)))
    exec(compile(module,str(F/'replay.py'),'exec'),ns)
    save(root/'plan.json',dict(image_sha256=IMAGE))
    nf2plan = sha(root/'plan.json')
    # Hash-valid, explicitly rejected review plus incomplete/nonzero child
    # metadata: the gate must not infer full independent acceptance from these.
    save(root/'rejected_review.json',dict(status='NOT_ACCEPTED_NO_RETRY',accepted=False,
        firstcause='SYNTHETIC: no complete independent CSV oracle'))
    save(root/'complete.json',dict(status='PASS_M6_NF2_REMAINING34_PLUS_J4_NOT_LINUX',
        aborted=False,pins_unchanged=True,plan_sha256=nf2plan,retries=1,
        results=[dict(name='wrong_member',status='FAIL',returncode=17)]))
    approval = dict(decision='AUTHORIZE_NF7_CURRENT96_M6_ONCE',plan_sha256=PLAN,
        unit=ns['UNIT'],image_sha256=IMAGE,budget_risk_accepted=True,
        nf2_gate=dict(decision='TERMINAL_INDEPENDENTLY_ACCEPTED',terminal_path=str(root/'complete.json'),
            terminal_sha256=sha(root/'complete.json'),plan_sha256=nf2plan,
            review_path=str(root/'rejected_review.json'),review_sha256=sha(root/'rejected_review.json')))
    save(root/'parent_review.json',approval)
    returned = ns['authorization'](PLAN,root/'parent_review.json',sha(root/'parent_review.json'))
    assert len(returned)==4
    return dict(status='REPRODUCED_FALSE_PREREQUISITE_ADMISSION',function='replay.py:140 authorization',
        actual_function_extracted_by_AST=True,filesystem='New owned synthetic files only; real SHA verification',
        review_accepted=False,retries=1,result_count=1,result_member='wrong_member',result_status='FAIL',numeric_rc=17,
        missing=['durable child outcomes','COMPLETE run metadata','independent audit result/actual exit','all10 membership','full evidence pins'],
        actual_gate_returned_pins=returned,real_NF2_outputs_read=False,no_DUT_execution=True)


def main():
    started=time.monotonic()
    assert sha(P/'plan.json')==PLAN
    plan=read(P/'plan.json'); pins=dict(plan['pins'])
    assert len(pins)==840; verify(pins)
    extra=[F/n for n in ('HANDOFF.md','README.md','checker.py','replay.py','observer.py','test_host.py','host01/status.json','host01/log.txt')]
    extra += [P/n for n in ('plan.json','ready.json','dryrun_gate.json','dryrun/run.json','dryrun/summary.json')]
    for p in extra:
        h=sha(p); assert str(p) not in pins or pins[str(p)]==h; pins[str(p)]=h
    image=Path(plan['image']); ledger=read(image/'image.json')
    assert sha(image/'image.json')==plan['image_sha256']==IMAGE
    snapfile=Path(ledger['snapshot'])/'snapshot.json'; snap=read(snapfile)
    assert sha(snapfile)==plan['snapshot_sha256']==ledger['snapshot_sha256']
    assert snap['state']=='SEALED' and len(snap['files'])==539 and len(ledger['files'])==66
    for p,h in ledger['files'].items(): assert pins[p]==h
    for p,h in snap['files'].items(): assert pins[str(Path(snap['root'])/p)]==h
    assert sha(image/'_build/vcs/simulator.conf')==ledger['configuration_sha256']=='6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    old=HERE.parent/'vcs_plan06'; programs=read(old/'programs/programs.json')['programs']
    oldpins=read(old/'plan.json')['pins']
    geometry=read(HERE.parent.parent/'geometry01.json')
    for p,h in geometry['source_identity'].items(): assert pins[p]==h and sha(p)==h
    cases=plan['cases']; assert len(cases)==24
    assert [c['id'] for c in cases]==[f'nf7_g{i:02d}' for i in range(24)]
    assert [t for c in cases for t in c['trials']]==list(range(96))
    assert [plan[k] for k in ('jobs','timeout_s','group_timeout_s','worker_timeout_s','service_timeout_s')]==[4,2400,2700,16200,16800]
    host=read(F/'host01/status.json')
    assert host['status']=='PASS_HOST_ONLY_NOT_DUT' and host['tests']==28 and host['failures']==host['exit_code']==0
    assert host['log_sha256']==sha(F/'host01/log.txt'); verify(host['pins'])
    assert 'Ran 28 tests' in (F/'host01/log.txt').read_text() and (F/'host01/log.txt').read_text().rstrip().endswith('OK')
    dry=read(P/'dryrun/run.json'); summary=read(P/'dryrun/summary.json')
    assert dry['status']=='DRY_RUN' and dry['status_counts']=={'DRY_RUN':24}
    assert dry['jobs']==4 and dry['timeout_s']==2400 and dry['simv']==ledger['simv'] and dry['seed']==1
    assert dry['code_coverage'] is False and dry['commit_trace'] is True
    assert [r['name'] for r in summary]==dry['tests']==[c['id'] for c in cases]
    assert all(r['status']=='DRY_RUN' and r['returncode'] is None for r in summary)
    assert read(P/'dryrun_gate.json')['status']=='DRYRUN24_PASS_NOT_DUT'
    totals=dict(trials=96,checks=0,checkpoints=0,traps=0,architectural_faults=0,ecalls=96)
    identity=[]
    for c in cases:
        d=Path(c['source']); oldentry=programs[c['id']]
        assert oldentry['path']==c['elf'] and oldentry['sha256']==c['sha256']==sha(c['elf'])
        status=read(d/'status.json'); cfg=read(d/'cases.json'); oracle=read(c['ledger'])
        assert c['trials']==status['trials']==oldentry['cases'] and cfg==geometry['cases'][c['group']*4:c['group']*4+4]
        assert len(oracle)==status['checks']==c['checks'] and len(status['traps'])==c['traps']
        assert len(status['checkpoints'])==c['checkpoints']
        for p in [d/n for n in ('soc.elf','soc.symbols.json','soc.dis','cases.json','status.json')]+[Path(c['ledger'])]:
            assert pins[str(p)]==sha(p)
            if str(p) in oldpins: assert oldpins[str(p)]==pins[str(p)]
        for k in ('checks','checkpoints','traps'): totals[k]+=c[k]
        totals['architectural_faults']+=sum(x['expected_cause'] is not None for x in cfg)
        path=P/'dryrun/tests'/c['id']/'command.json'; actual=read(path)
        want=dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1','+PRELOAD='+c['elf'],
            '+TESTCASE='+c['id'],'+NO_FSDB','+COMMIT_TRACE='+str(path.parent/'commit_trace.csv')],cwd=str(path.parent/'work'))
        assert actual==want; pins[str(path)]=sha(path)
        identity.append(dict(id=c['id'],trials=c['trials'],elf_sha256=c['sha256'],
            cases_sha256=sha(d/'cases.json'),ledger_sha256=sha(c['ledger']),checks=c['checks'],
            checkpoints=c['checkpoints'],traps=c['traps'],dryrun_command_sha256=sha(path)))
    assert totals==dict(trials=96,checks=284816,checkpoints=168,traps=168,architectural_faults=72,ecalls=96)
    for n in ('csv_oracle.py','reference.py'):
        p=HERE.parent/n; assert oldpins[str(p)]==pins[str(p)]==sha(p)
    counter=prerequisite_counterexample()
    verify(pins); assert sha(P/'plan.json')==PLAN
    save(HERE/'verified_pins.json',pins)
    save(HERE/'evidence.json',dict(status='ENTRY_BLOCKED_NF2_PREREQUISITE_GATE',no_blocker=False,DUT_approved=False,
        plan_sha256=PLAN,image_sha256=IMAGE,source_snapshot_sha256=ledger['snapshot_sha256'],
        original_plan_pins=840,review_pins=len(pins),source_files=539,image_files=66,
        pins_pre_post_unchanged=True,host_existing_tests=28,hosts_rerun=False,dryrun_existing_commands=24,dryrun_rerun=False,
        totals=totals,groups=identity,counterexample=counter,
        real_NF2_live_output_reads=0,CSV_parses=0,reference_executions=0,DUT_launches=0,service_or_process_queries=0,
        script_sha256=sha(Path(__file__)),verified_pins_sha256=sha(HERE/'verified_pins.json'),elapsed_s=time.monotonic()-started))
    print('ENTRY_BLOCKED_NF2_PREREQUISITE_GATE',sha(HERE/'evidence.json'),flush=True)


if __name__=='__main__': main()
