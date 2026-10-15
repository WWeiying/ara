"""One admitted terminal CSV pass per NF2 job; no simulator/reference execution."""
import argparse
import ast
from collections import Counter
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
F = HERE.parent/'nf2_remaining34_vcs_m6_plan01'
P = F/'prepared01'
REF = HERE.parent/'nf2_remaining34_prepare01'
J4 = HERE.parent/'sv39'
OLD = HERE.parent/'nf2_remaining4_terminal_audit01'
UNIT = 'ara-nf2-remaining34-j4-m6-01.service'
PLAN_SHA = 'b2fb0d810d7004769a18c7b0527e14b013979791ace008edb4155240126bb586'
PARENT_SHA = 'e2cfb7f342f73fe7e8597ddb68a469bdd0341800d320d0d5e06d7776a6e919a6'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
PASS = 'PASS_M6_NF2_REMAINING34_PLUS_J4_NOT_LINUX'
ACCEPT = 'INDEPENDENT_M6_NF2_34_PLUS_J4_ACCEPTED_40_WITH_PINNED_PILOT_NOT_LINUX'
OLD_AUDIT_SHA = '67aeb830406e679513dea0bb3a14236b6afd0ae9e1e2c97af40402b02f737110'
OLD_WAIT_SHA = '1b46120b0e1d74353f61e247fc4aaadcc548c072975888c019c34d69815d2c41'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


assert hashlib.sha256((OLD/'audit.py').read_bytes()).hexdigest() == OLD_AUDIT_SHA
u = load(OLD/'audit.py', 'nf2_frozen_utilities')
sha, read, save, add, verify = u.sha, u.read, u.save, u.add, u.verify


def normalized(value): return json.loads(json.dumps(value))


def source_identity(plan):
    manifest = read(REF/'source_manifest.json')
    all_cases = manifest['all_cases']
    assert len(all_cases) == len({c['id'] for c in all_cases}) == 40
    assert len({c['case_sha256'] for c in all_cases}) == 40
    sources = []
    for c in all_cases:
        root = Path(c['source_directory'])
        assert sha(root/'case.json') == c['case_sha256']
        meta = read(root/'case.json')
        assert meta['name'] == c['historical_name'] and meta['scenario_role'] == 'single_current_oracle_trial'
        assert meta['selected_trial'] == {k:c[k] for k in ('unmapped','store','boundary','mode','split')}
        assert sha(root/'scenario.elf') == c['elf_sha256']
        for name, h in c['source_hashes'].items(): assert sha(root/name) == h
        assert c['measured_failure']['status'] == 'failed' and c['measured_failure']['exit_code'] == 1
        sources.append({k:c[k] for k in ('id','case_sha256','source_directory','source_hashes','elf_sha256')})
    new = [c for job in plan['cases'][:9] for c in job['source_cases']]
    old = plan['cases'][-1]['source_cases']
    pilot = manifest['excluded_pilot4']
    assert len(new) == 34 and old == manifest['excluded_J2'] and len(old) == 2 and len(pilot) == 4
    assert len(set(new+old+pilot)) == 40 and set(new+old+pilot) == {c['id'] for c in all_cases}
    controls = plan['cases'][-1]['positive_controls']
    assert controls == ['u0_s0_b5_m2_f1','u0_s1_b5_m2_f1'] and not set(controls)&set(new+old+pilot)
    return dict(failed_sources=sources,new34=new,J4_failed2=old,pilot4=pilot,J4_positive2=controls)


def static_identity():
    assert sha(P/'plan.json') == PLAN_SHA and sha(F/'parent_review.json') == PARENT_SHA
    plan, review = read(P/'plan.json'), read(F/'parent_review.json')
    assert plan['status'] == 'PREPARED_NOT_RUN' and len(plan['pins']) == 1240
    assert [plan[k] for k in ('jobs','timeout_s','worker_timeout_s','service_timeout_s')] == [3,6300,25200,27000]
    assert plan['unit'] == UNIT and plan['image_sha256'] == IMAGE_SHA
    assert all(plan[k] is True for k in ('no_build','no_retry','no_fsdb','stop_first_fail'))
    assert review['decision'] == 'AUTHORIZE_NF2_REMAINING34_J4_M6_ONCE'
    assert review['plan_sha256'] == PLAN_SHA and review['unit'] == UNIT and review['jobs'] == 3
    assert review['budget_risk_accepted'] is True
    assert review['independent_reference_pins'] == plan['independent_reference_pins']
    assert review['pilot_audit_sha256'] == plan['pilot_audit_sha256']
    pins = dict(plan['pins'])
    add(pins,{str(P/'plan.json'):PLAN_SHA,str(F/'parent_review.json'):PARENT_SHA,
              str(OLD/'audit.py'):OLD_AUDIT_SHA,str(OLD/'wait_terminal.py'):OLD_WAIT_SHA,
              str(u.TRANSPORT):u.TRANSPORT_SHA,str(u.SUPPORT):u.SUPPORT_SHA})
    verify(pins)
    sys.path.insert(0,str(F))
    checker = load(F/'checker.py','checker')
    assert checker.scope() == plan['cases']
    gates = load(F/'gates.py','nf2_frozen_prerequisites')
    assert gates.accepted_reference() == plan['independent_reference_pins']
    pilotpins = gates.pilot_gate(OLD/'terminal01/result.json',plan['pilot_audit_sha256'])
    assert sha(gates.PILOT/'complete.json') == plan['pilot_complete_sha256']
    add(pins,pilotpins)
    image = Path(plan['image']); ledger = read(image/'image.json')
    assert sha(image/'image.json') == IMAGE_SHA
    snapshot = Path(ledger['snapshot'])/'snapshot.json'; snap = read(snapshot)
    assert sha(snapshot) == ledger['snapshot_sha256'] == plan['snapshot_sha256']
    assert snap['state'] == 'SEALED' and len(snap['files']) == 539 and len(ledger['files']) == 66
    assert sha(image/'_build/vcs/simulator.conf') == ledger['configuration_sha256'] == '6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    assert sha(image/'_build/vcs/vcs_source_manifest.json') == ledger['manifest_sha256']
    add(pins,ledger['files']); add(pins,{str(Path(snap['root'])/p):h for p,h in snap['files'].items()})
    trace = Path(snap['root'])/'verification/ara_verify/trace.py'
    assert str(trace) in pins
    return plan,pins,checker,ledger,trace


def prepare():
    assert not (HERE/'prepared.json').exists()
    plan,pins,_,_,trace = static_identity()
    coverage = source_identity(plan)
    elf_reader = load(u.SUPPORT,'nf2_static_elf_reader')
    groups = {g['id']:g for g in read(REF/'source_manifest.json')['groups']}
    specs = {}
    for case in plan['cases']:
        root = REF/case['group']/'reference02' if case['kind'] == 'remaining34' else J4/'reference01'
        symbols = read(root/'soc.symbols.json')
        code = {str(int(m[1],16)):int(m[2],16) for m in re.finditer(
            r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',(root/'soc.dis').read_text(),re.M)}
        get,actual = elf_reader.elf(case['elf'])
        for name,pc in symbols.items(): assert actual[name][0] == pc
        for pc,insn in code.items():
            assert int.from_bytes(get(int(pc),4 if insn&3 == 3 else 2),'little') == insn
        assert code[str(symbols['mx_segment_load'])] == 0x20055c07
        assert code[str(symbols['mx_segment_store'])] == 0x20055c27
        cfg = groups[case['group']]['cases'] if case['kind'] == 'remaining34' else None
        if cfg is not None:
            assert len(cfg) == case['MX_N'] and [c['id'] for c in cfg] == case['source_cases']
        specs[case['id']] = dict(symbols=symbols,code=code,cases=cfg)
    for name in ('audit.py','wait_terminal.py','AUTHORIZATION.md'):
        path = HERE/name
        if path.suffix == '.py': ast.parse(path.read_text(),filename=str(path))
        add(pins,{str(path):sha(path)})
    verify(pins)
    save(HERE/'prepared.json',dict(status='PREPARED_CONDITIONAL_TERMINAL_AUDIT_NOT_DUT',
        plan_sha256=PLAN_SHA,parent_sha256=PARENT_SHA,pins=pins,specs=specs,coverage=coverage,
        trace_module=str(trace),wait_seconds=27000,audit_timeout_seconds=3600,case_audit_timeout_seconds=600,
        service_timeout_seconds=33000,csv_reads=0,reference_parses=0,Host_executed=False,
        DUT_executed=False,no_retry=True,original_plan_pins=1240))
    print('PREPARED',sha(HERE/'prepared.json'),flush=True)


def admission(prepared_sha, complete_sha):
    assert sha(HERE/'prepared.json') == prepared_sha
    prepared = read(HERE/'prepared.json'); verify(prepared['pins'])
    assert sha(P/'complete.json') == complete_sha
    done = read(P/'complete.json')
    assert done['status'] == PASS and done['plan_sha256'] == PLAN_SHA
    assert done['aborted'] is False and done['pins_unchanged'] is True and not done.get('error')
    assert type(done['retries']) is int and done['retries'] == 0
    assert done['new34_accepted'] is True and done['J4_current_M6_accepted'] is True
    assert done['positive_controls_not_failure_count'] == 2 and done['source_failure_count_with_accepted_pilot'] == 40
    assert done['Linux_signalframe_proved'] is False
    plan,pins,checker,ledger,_ = static_identity()
    add(pins,prepared['pins']); add(pins,{str(HERE/'prepared.json'):prepared_sha,str(P/'complete.json'):complete_sha})
    assert source_identity(plan) == prepared['coverage']
    results,run = read(P/'replay/summary.json'),read(P/'replay/run.json')
    assert done['results'] == results and len(results) == 10
    names = [c['id'] for c in plan['cases']]
    assert [r['name'] for r in results] == names
    assert run['status'] == 'COMPLETE' and run['tests'] == names and run['status_counts'] == {'PASS':10}
    assert run['jobs'] == 3 and run['timeout_s'] is None and run['seed'] == 1 and run['simv'] == ledger['simv']
    assert run['commit_trace'] is True and run['input_snapshots'] is True and run['code_coverage'] is False
    assert run['contract_monitor'] is False and run['probe_kinds'] == []
    assert datetime.fromisoformat(run['completed_at']) > datetime.fromisoformat(run['created_at'])
    argv = run['invocation']
    assert argv[:2] == [str(F/'replay.py'),'run'] and '--authorize-run' in argv
    for opt,want in (('--plan-sha256',PLAN_SHA),('--parent-review',str(F/'parent_review.json')),('--parent-review-sha256',PARENT_SHA)):
        assert argv[argv.index(opt)+1] == want
    launch = read(P/'launch.json'); owner = launch['owner']; prop = owner['properties']
    assert launch['plan_sha256'] == PLAN_SHA and launch['started'] <= done['finished'] < launch['started']+27000
    assert prop['Id'] == UNIT and prop['MainPID'] == str(owner['pid']) and owner['pid'] > 0
    assert [prop[k] for k in ('LoadState','ActiveState','SubState','RuntimeMaxUSec','KillMode','Restart')] == ['loaded','active','running','7h 30min','control-group','no']
    assert prop['ControlGroup'].endswith('/'+UNIT) and prop['ControlGroup'] in [l.split(':',2)[-1] for l in owner['cgroup'].splitlines()]
    assert launch['approval_pins'][str(F/'parent_review.json')] == PARENT_SHA
    add(pins,launch['approval_pins'])
    expected = {str(P/n) for n in ('launch.json','replay/run.json','replay/summary.json')}
    for case,result in zip(plan['cases'],results):
        root = P/'replay/tests'/case['id']
        assert result['kind'] == 'app' and result['status'] == 'PASS' and not result['reason']
        assert type(result['returncode']) is int and result['returncode'] == 0
        assert 0 < result['elapsed_s'] <= case['timeout_s'] and result['artifact_dir'] == str(root)
        assert sha(root/'input.elf') == case['sha256']
        inputs = read(root/'inputs.json')
        assert inputs['binary'] == dict(source=case['elf'],path=str(root/'input.elf'),sha256=case['sha256'])
        assert inputs['simv'] == dict(path=ledger['simv'],image_sha256=ledger['files'])
        command = dict(command=[ledger['simv'],'-l','run.vcs.log','+ntb_random_seed=1',
            '+PRELOAD='+str(root/'input.elf'),'+TESTCASE='+case['id'],'+NO_FSDB','+COMMIT_TRACE='+str(root/'commit_trace.csv')],cwd=str(root/'work'))
        assert read(root/'command.json') == command
        child = read(root/'child_outcome.unvalidated.json')
        assert child['schema'] == 'UNVALIDATED_CHILD_OUTCOME_V1' and child['architectural_acceptance'] is False
        for k in ('name','status','returncode','elapsed_s','reason','artifact_dir'): assert child[k] == result[k]
        assert type(child['returncode']) is int and child['returncode'] == 0 and not child.get('command_read_error')
        assert child['command'] == command and child['command_sha256'] == sha(root/'command.json')
        assert child['command_path'] == str(root/'command.json')
        producer = read(root/'strict_original.json')
        report = producer['observer']
        assert producer == dict(status='STRICT_NF2_ORIGINAL_SCOPE_PASS',case_id=case['id'],observer=report,
            source_cases=case['source_cases'],positive_controls=case.get('positive_controls',[]),
            observer_generation=case['kind'],current_image='M6',Linux_signalframe_proved=False,
            child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
        assert report['status'] == 'NF2_CSV_ORACLE_PASS' and report['cases'] == list(range(case['MX_N']))
        assert len(report['checkpoints']) == 2*case['MX_N']
        assert len(report['alternate_protected_field']) == case['MX_N'] and all(type(x) is bool for x in report['alternate_protected_field'])
        assert report['checks'] == case['checks']-sum(report['alternate_protected_field'])
        observer_command = read(root/'observer.command.json')
        oc = observer_command['command']
        assert Path(oc[0]).resolve() == Path(sys.executable).resolve()
        if case['kind'] == 'remaining34':
            assert oc[1:] == ['-B',str(REF/'observer_cli.py'),'--group',case['group'],'--csv',str(root/'commit_trace.csv'),'--out',str(root/'observer.json')]
            assert read(root/'observer.json') == report
        else:
            assert oc[1:] == ['-B',str(J4/'csv_check.py'),str(root/'commit_trace.csv'),'--symbols',str(J4/'reference01/soc.symbols.json')]
            assert read(root/'observer.stdout') == report
        assert observer_command['cwd'] == str(F) and observer_command['timeout_s'] == 600
        assert not (root/'observer.stderr').read_text().strip()
        for path in (root/'console.log',root/'work/run.vcs.log'):
            text = path.read_text()
            assert not checker.VETO.search(text) and not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b',text,re.I)
            assert text.count(case['pass_markers'][0]) == 1 and checker.common.SUCCESS in text and '$finish' in text
        files = ['input.elf','inputs.json','command.json','console.log','work/run.vcs.log','commit_trace.csv',
            'trace_summary.json','child_outcome.unvalidated.json','observer.command.json','observer.stdout','observer.stderr','strict_original.json']
        if case['kind'] == 'remaining34': files.append('observer.json')
        expected.update(str(root/n) for n in files)
    assert set(done['evidence_pins']) == expected
    add(pins,done['evidence_pins']); verify(pins)
    assert not (P/'complete.tmp').exists()
    assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout',p.name,re.I) for p in P.rglob('*') if p.is_file())
    assert sha(P/'complete.json') == complete_sha
    return prepared,plan,pins


def audit_case(prepared_sha,complete_sha,name):
    assert sha(HERE/'prepared.json') == prepared_sha and sha(P/'complete.json') == complete_sha
    prepared = read(HERE/'prepared.json'); plan = read(P/'plan.json')
    assert sha(P/'plan.json') == PLAN_SHA
    admitted = read(HERE/'terminal01/admission.json')
    assert admitted['complete_sha256'] == complete_sha and admitted['prepared_sha256'] == prepared_sha
    case = next(c for c in plan['cases'] if c['id'] == name)
    out = HERE/'terminal01'/name; out.mkdir()
    root = P/'replay/tests'/name; spec = prepared['specs'][name]
    module_root = REF if case['kind'] == 'remaining34' else J4
    sys.path.insert(0,str(module_root))
    checker = load(module_root/'csv_check.py','nf2_original_csv_checker')
    if case['kind'] == 'remaining34':
        checker.configure(spec['cases'])
        strict = checker.Checker(spec['symbols'],spec['code'])
    else: strict = checker.Checker(spec['symbols'])
    transport = load(u.TRANSPORT,'nf2_lossless_transport')
    code = {int(k):v for k,v in spec['code'].items()}
    class Observer(transport.Observer):
        def __init__(self):
            self.count = Counter(); self.before = hashlib.sha256(); self.after = hashlib.sha256()
            self.pcs = Counter()
        def observe(self,row):
            self.count['rows'] += 1; self.count[row['event']] += 1
            if row['event'] == 'retire':
                pc,insn = int(row['pc'],16),int(row['insn'],16)
                assert code.get(pc) == insn, ('Actual PC/code mismatch',hex(pc),hex(insn))
                self.pcs[pc] += 1
            strict.row(row)
    observer = Observer()
    trace = load(Path(prepared['trace_module']),'nf2_frozen_generic_trace')
    class Reader:
        def __init__(self,stream):
            self.reader = csv.DictReader(stream); self.fieldnames = self.reader.fieldnames
        def __iter__(self): return observer.rows(self.reader)
    trace.csv = SimpleNamespace(DictReader=Reader)
    started = time.monotonic()
    generic = trace.validate_trace(root/'commit_trace.csv')
    report = strict.finish()
    assert observer.count['rows'] == observer.count['unmodified_delivered_rows'] == generic['rows']
    assert observer.before.digest() == observer.after.digest()
    assert observer.count['retire'] == generic['retire_count']
    assert observer.pcs[spec['symbols']['check']] == report['checks']
    if case['kind'] == 'remaining34':
        report.update(group=case['group'],CSV_sha256=admitted['pins'][str(root/'commit_trace.csv')])
    assert normalized(report) == read(root/'strict_original.json')['observer'], 'Full rebuilt observer differs'
    assert dict(generic,status='VALID') == read(root/'trace_summary.json')
    if spec['cases'] is not None:
        phases = [(i,p) for i,c in enumerate(spec['cases']) for p in ((1,2) if c['fault'] else (3,2))]
        causes = [v for c in spec['cases'] for v in ([15 if c['store'] else 13,9] if c['fault'] else [9])]
    else:
        phases = [(i,p) for i in range(4) for p in (1,2)]
        causes = [13,9,15,9,13,9,15,9]
    assert [(p['case'],p['phase']) for p in report['checkpoints']] == phases
    assert [t['values'][0] for t in report['traps']] == causes
    save(out/'result.json',dict(status='INDEPENDENT_ONE_CSV_ACCEPTED',name=name,csv_parses=1,
        generic=generic,observer=report,source_cases=case['source_cases'],positive_controls=case.get('positive_controls',[]),
        child_outcome=read(root/'child_outcome.unvalidated.json'),csv_sha256=admitted['pins'][str(root/'commit_trace.csv')],
        lossless=dict(rows=observer.count['rows'],delivered=observer.count['unmodified_delivered_rows'],
            before_sha256=observer.before.hexdigest(),after_sha256=observer.after.hexdigest()),
        actual_pc_counts={hex(k):v for k,v in observer.pcs.items()},audit_seconds=time.monotonic()-started))
    print('INDEPENDENT_ONE_CSV_ACCEPTED',name,flush=True)


def terminal(prepared_sha,complete_sha):
    target = HERE/'terminal01'; target.mkdir()
    started = time.monotonic(); child = None
    def cancelled(sig,frame): raise RuntimeError('Offline audit signal '+str(sig))
    signal.signal(signal.SIGTERM,cancelled); signal.signal(signal.SIGINT,cancelled)
    try:
        prepared,plan,pins = admission(prepared_sha,complete_sha)
        save(target/'admission.json',dict(status='ALL10_TERMINAL_ADMITTED_NOT_AUDIT_PASS',
            prepared_sha256=prepared_sha,complete_sha256=complete_sha,pins=pins))
        results = []; exits = []
        for case in plan['cases']:
            name = case['id']; command = [sys.executable,'-B',str(HERE/'audit.py'),'case',
                '--authorize-terminal-audit','--prepared-sha256',prepared_sha,'--complete-sha256',complete_sha,'--name',name]
            with (target/(name+'.stdout')).open('x') as stdout,(target/(name+'.stderr')).open('x') as stderr:
                child = subprocess.Popen(command,cwd=HERE,stdout=stdout,stderr=stderr)
                save(target/(name+'.invocation.json'),dict(pid=child.pid,parent_pid=__import__('os').getpid(),command=command,started=time.time()))
                rc = child.wait(timeout=prepared['case_audit_timeout_seconds'])
            evidence = dict(name=name,pid=child.pid,actual_wait_returncode=rc,time=time.time(),
                stdout_sha256=sha(target/(name+'.stdout')),stderr_sha256=sha(target/(name+'.stderr')))
            save(target/(name+'.exit.json'),evidence); exits.append(evidence)
            assert rc == 0, ('First offline failure; no further CSV or retry',name,rc)
            item = read(target/name/'result.json')
            assert item['status'] == 'INDEPENDENT_ONE_CSV_ACCEPTED' and item['name'] == name
            results.append(item)
        verify(pins)
        assert sha(P/'complete.json') == complete_sha and len(results) == 10
        save(target/'verified_pins.json',pins)
        save(target/'result.json',dict(status=ACCEPT,accepted=True,plan_sha256=PLAN_SHA,parent_sha256=PARENT_SHA,
            prepared_sha256=prepared_sha,complete_sha256=complete_sha,image_sha256=IMAGE_SHA,
            cases=results,case_audit_exits=exits,source_coverage=prepared['coverage'],
            aggregate=dict(csv_files=10,csv_parses=10,rows=sum(r['generic']['rows'] for r in results),
                retired_rows=sum(r['generic']['retire_count'] for r in results),
                checks=sum(r['observer']['checks'] for r in results),checkpoints=sum(len(r['observer']['checkpoints']) for r in results),
                pagefaults=sum(t['values']['0'] in (13,15) for r in results for t in r['observer']['traps']),
                ecalls=sum(t['values']['0'] == 9 for r in results for t in r['observer']['traps'])),
            pins_verified=len(pins),original_plan_pins=1240,pins_pre_post_unchanged=True,
            source_failures_this_batch=36,prior_pilot_source_failures=4,distinct_failed_sources_current_M6=40,
            positive_controls_separate=2,prior_pilot_audit_sha256=plan['pilot_audit_sha256'],
            outer_service_returncode=None,outer_service_terminal_observed=False,no_retry=True,
            Linux_signalframe_proved=False,original_linux_ELF_replay=False,reference_substituted_for_DUT=False,
            vector_data_evidence='Pinned firmware full scalar oracle, not direct vector payload capture',
            CSR_restore_boundary='Only existing firmware checks; no added readback or inferred internal CSR state',
            audit_seconds=time.monotonic()-started))
        print(ACCEPT,sha(target/'result.json'),flush=True)
    except BaseException as error:
        if child is not None and child.poll() is None: child.kill(); child.wait()
        save(target/'firstfailure.json',dict(status='NOT_ACCEPTED_NO_RETRY',firstcause=repr(error),time=time.time()))
        raise


if __name__ == '__main__':
    assert __debug__
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('prepare','terminal','case'))
    parser.add_argument('--authorize-terminal-audit',action='store_true')
    parser.add_argument('--prepared-sha256'); parser.add_argument('--complete-sha256'); parser.add_argument('--name')
    args = parser.parse_args()
    if args.mode == 'prepare':
        assert not args.authorize_terminal_audit and not args.prepared_sha256 and not args.complete_sha256 and not args.name
        prepare()
    else:
        assert args.authorize_terminal_audit and args.prepared_sha256 and args.complete_sha256
        if args.mode == 'case': audit_case(args.prepared_sha256,args.complete_sha256,args.name)
        else:
            assert not args.name
            terminal(args.prepared_sha256,args.complete_sha256)
