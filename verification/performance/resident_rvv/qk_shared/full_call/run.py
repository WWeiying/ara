#!/usr/bin/env python3
"""One-shot complete Attention checks on a reviewed stage-3 SoC image."""
import argparse
from collections import Counter
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
SHARED = ROOT/'verification/performance/resident_rvv/qk_shared'
EVAL = ROOT/'verification/performance/resident_rvv/soc_eval'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


b = load(HERE/'build_soc.py' if (HERE/'build_soc.py').exists() else SHARED/'build_soc.py',
         'complete_attention_build_contract')
w = load(HERE/'check_work.py', 'complete_attention_work')
OWN = ('run.py', 'test_run.py', 'check_work.py', 'test_check_work.py')
LEGACY = (
    'verification/performance/chain_profile/build_soc.py',
    'verification/performance/chain_profile/run_case.py',
    'verification/performance/resident_rvv/soc_eval/experiment.py',
    'verification/performance/resident_rvv/soc_eval/run_smoke.py',
    'verification/performance/resident_rvv/soc_eval/run_abba.py',
    'verification/performance/akv_pair_eval/integration/build.py',
    'verification/performance/akv_pair_eval/integration/check.py',
    'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
)


def legacy():
    previous, search = sys.modules.get('build_soc'), list(sys.path)
    sys.modules['build_soc'] = load(ROOT/LEGACY[0], 'complete_attention_sealed_chain')
    try:
        smoke = load(EVAL/'run_smoke.py', 'complete_attention_sealed_smoke')
        abba = load(EVAL/'run_abba.py', 'complete_attention_sealed_abba')
    finally:
        sys.path[:] = search
        if previous is None:
            sys.modules.pop('build_soc', None)
        else:
            sys.modules['build_soc'] = previous
    _, original = smoke.e.contract.sealed_modules()
    return smoke, abba, original


def expected_akv(kind):
    _, _, original = legacy()
    one = original.expected_commands()[1046:1283]
    b.require(len(one) == 237 and Counter(r['command'] for r in one) ==
              Counter({2:137, 6:96, 4:1, 5:2, 3:1}), 'Accepted SDK command template drift')
    return [r for arm in w.order(kind) for r in one if not arm or r['command'] not in (2,6)]


def check_akv(text, kind):
    _, _, original = legacy()
    expected, rows, summaries, totals = expected_akv(kind), [], [], Counter()
    for line in text.splitlines():
        if '[AKV_PERF]' in line:
            b.require(line.startswith('[AKV_PERF] ') and not summaries, 'Malformed/post-summary command')
            row = original.parse_fields(line[len('[AKV_PERF] '):], original.PERF_FIELDS)
            i = len(rows)
            b.require(i < len(expected) and row['seq'] == i+1 and
                      all(row[k] == v for k,v in expected[i].items()), 'Command sequence/work mismatch')
            b.require(row['success'] == 1 and row['busy_cycles'] > 0 and all(row[k] == 0 for k in
                      ('fault','validation_fault','validation_error','read_fault','v2_rejected')),
                      'AKV command fault')
            b.require(row['context_ready'] == int(row['command'] != 3) and row['read_payload_bytes'] ==
                      row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full'],
                      'Context lifetime/external payload mismatch')
            for key in original.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
                totals[key] = max(totals[key],row[key]) if key == 'read_outstanding_max' else totals[key]+row[key]
            rows.append(row)
        elif '[AKV_PERF_SUMMARY]' in line:
            b.require(line.startswith('[AKV_PERF_SUMMARY] ') and len(rows) == len(expected),
                      'Premature/malformed command summary')
            summaries.append(original.parse_fields(line[len('[AKV_PERF_SUMMARY] '):], original.SUMMARY_FIELDS))
    summary = dict(totals, records=len(expected), success_records=len(expected),
                   fault_records=0, validation_fault_records=0)
    b.require(len(rows) == len(expected) and summaries == [summary], 'Incomplete/inconsistent command work')
    counts = [4 if arm else 237 for arm in w.order(kind)]
    busy, offset = [], 0
    for count in counts:
        busy.append(sum(r['busy_cycles'] for r in rows[offset:offset+count]))
        offset += count
    return dict(commands=len(rows), per_call_commands=counts, busy_cycles_per_call=busy, summary=summary)


def check_numerical(text, software):
    smoke, abba, _ = legacy()
    result = (smoke if software['kind'] == 'smoke' else abba).check_numerical(text, software)
    if software['kind'] == 'abba':
        # Reuse the unchanged bitwise/flag oracle, but name the new candidate accurately.
        cycles = result['complete_call_cycles']
        result['baseline_arm'] = 'panel4 RVV QK + rotating-register PV'
        result['candidate_arm'] = 'resident QK + resident PV'
        result['complete_call_mean_cycles'] = dict(rvv=(cycles[0]+cycles[3])/2,
                                                   resident_qk_pv=(cycles[1]+cycles[2])/2)
        result['rvv_over_resident_qk_pv'] = result.pop('complete_call_strong_rotation_over_resident_pv')
    return result


def software(build):
    build = b.output_path(build, 'stage3_attention_build_')
    receipt = b.read(build/'build.json')
    b.require(receipt.get('state') == 'BUILT_NOT_EXECUTED' and receipt.get('post_pins_match') is True and
              receipt.get('rtl_executed') is False and receipt.get('performance_measured') is False and
              receipt.get('baseline_arm') == 'panel4 RVV QK + rotating-register PV' and
              receipt.get('candidate_arm') == 'resident QK + resident PV' and
              receipt.get('shape') == dict(d=128,heads=2,tokens=137,tiles=[64,64,9]) and
              receipt.get('elf') == str(build/'attention.elf'), 'Unreviewed complete-call software')
    w.order(receipt['kind'])
    b.require(receipt['source_pins_sha256'] == b.sha(build/'source-pins.json') and
              receipt['elf_sha256'] == b.sha(receipt['elf']), 'Software identity mismatch')
    pins = b.read(build/'source-pins.json')
    b.verify(pins)
    b.exact_files(build, receipt['artifacts'], exclude=('build.json',))
    for key in ('captured','native_tile64'):
        path = receipt['golden'][key]
        b.require(b.sha(path) == receipt['golden'][key+'_sha256'], 'Numerical reference drift')
        pins[path] = receipt['golden'][key+'_sha256']
    return receipt, pins | receipt['artifacts'] | {str(build/'build.json'): b.sha(build/'build.json')}


def collect(socdir, build):
    soc, pins = b.checked_build(socdir)
    sw, extra = software(build)
    smoke, _, _ = legacy()
    smoke.e.merge(pins, extra)
    extra = smoke.checker_inventory()
    extra.update({str(ROOT/p):b.sha(ROOT/p) for p in LEGACY})
    extra.update({str(smoke.e.contract.PRIMARY/n):h for n,h in smoke.e.contract.SEALED.items()})
    extra[str(SHARED/'geometry.py')] = b.sha(SHARED/'geometry.py')
    for tool in (sys.executable,'/usr/bin/bash','/usr/bin/readelf','/usr/bin/systemctl','/usr/bin/systemd-run'):
        path = Path(tool).resolve()
        extra[str(path)] = b.sha(path)
    smoke.e.merge(pins, extra)
    b.require(b.sha(SHARED/'build_soc.py') == b.sha(socdir/'inputs/build_soc.py'),
              'Build contract differs from reviewed image')
    b.verify(pins)
    return soc, sw, pins


def output_path(path):
    return b.output_path(path, 'stage3_attention_vcs_')


def numerical_and_work(out, sw):
    log, vector = out/'work/run.vcs.log', out/'work/vector_trace.csv'
    text = log.read_text()
    smoke, _, _ = legacy()
    smoke.successful_log(text)
    return dict(numerical=check_numerical(text, sw), akv_work=check_akv(text,sw['kind']),
                resident_work=w.check(vector,text,sw['kind']))


def execution_receipts(out, plan):
    for name,command,seconds in (('console','simulation',5400),('checker','protocol',900)):
        b.require(b.read(out/'work'/(name+'.command.json')) == dict(
            argv=plan['commands'][command],cwd=str(out/'work'),timeout_seconds=seconds),
            'Executed command differs from reviewed recipe: '+command)
    ownership = b.read(out/'owner.json')
    b.require(ownership['unit'] == service_unit(out) and b.read(out/'attempt.json') ==
        dict(review_sha256=b.sha(out/'source-pins.json'),**ownership), 'Recorded owner/review mismatch')
    b.direct_owner(ownership['cgroup'],ownership['unit'],ownership['main_pid'],ownership['owner_pid'])


def admitted_smoke(path, socdir):
    path = output_path(path)
    report = b.read(path/'result.json')
    plan, pins, soc, sw = verify_prepared(path)
    b.require(sw['kind'] == 'smoke' and plan['smoke_run'] is None and plan['soc_build'] == str(socdir) and
              all(report.get(k) == v for k,v in dict(state='PASS',numerical_checked=True,
                independent_protocol_checked=True,post_pins_match=True,post_image_match=True,
                kind='smoke',image_pins=soc['image_pins'],elf_sha256=sw['elf_sha256'],
                source_pins_sha256=b.sha(path/'source-pins.json')).items()), 'Accepted same-image smoke required')
    b.exact_files(path, report['artifacts'], exclude=('result.json','status.json','service.stdout.log','service.stderr.log'))
    execution_receipts(path,plan)
    evidence = numerical_and_work(path, sw)
    b.require(all(report[k] == v for k,v in evidence.items()), 'Smoke acceptance replay mismatch')
    smoke, abba, _ = legacy()
    log, vector = path/'work/run.vcs.log', path/'work/vector_trace.csv'
    proof = b.read(path/'work/uvm_result.json')
    smoke.check_protocol(proof,soc,sw,log,vector)
    repeated = abba.recheck_protocol(log,vector)
    b.require(repeated.get('status') == 'PASS' and repeated.get('issues') == [] and
              all(proof.get(k) == v for k,v in repeated.items()), 'Independent smoke protocol replay mismatch')
    pins.update(report['artifacts'])
    pins[str(path/'result.json')] = b.sha(path/'result.json')
    return pins


def selection(out,socdir,build,soc,sw,smoke_run,env,python):
    old, _, _ = legacy()
    commands = old.recipes(out,soc,sw,python)
    args = commands['simulation']
    args[args.index('+TESTCASE=resident_pv_soc_smoke')] = '+TESTCASE=resident_qk_pv_'+sw['kind']
    return dict(schema='stage3-complete-attention-v1',kind=sw['kind'],soc_build=str(socdir),build=str(build),
        soc_receipt_sha256=b.sha(socdir/'build.json'),software_receipt_sha256=b.sha(build/'build.json'),
        smoke_run=str(smoke_run) if smoke_run else None,configuration=soc['configuration'],
        commands=commands,environment=env,python=python,automatic_retry=False,whole_model=False)


def prepare(out,socdir,build,smoke_run=None):
    out, socdir, build = output_path(out),b.output_path(socdir),Path(build).resolve(strict=True)
    b.require(not out.exists(), 'Preserve old attempt')
    soc, sw, pins = collect(socdir,build)
    b.require((sw['kind']=='abba') == (smoke_run is not None), 'ABBA requires accepted smoke; smoke cannot inherit one')
    if smoke_run is not None:
        smoke_run = output_path(smoke_run)
        pins.update(admitted_smoke(smoke_run,socdir))
    out.mkdir()
    (out/'inputs').mkdir()
    (out/'work').mkdir()
    for name in OWN:
        shutil.copyfile(HERE/name,out/'inputs'/name)
    shutil.copyfile(SHARED/'build_soc.py',out/'inputs/build_soc.py')
    old, _, _ = legacy()
    plan = selection(out,socdir,build,soc,sw,smoke_run,old.environment(),str(Path(sys.executable).resolve()))
    b.save(out/'selection.json',plan)
    pins.update(b.files(out/'inputs'))
    pins[str(out/'selection.json')] = b.sha(out/'selection.json')
    b.verify(pins)
    b.save(out/'source-pins.json',pins)
    b.save(out/'prepared.json',dict(state='PREPARED_ATTENTION_NOT_EXECUTED',
                                   source_pins_sha256=b.sha(out/'source-pins.json')))
    verify_prepared(out)
    return plan


def verify_prepared(out):
    out = output_path(out)
    pins,plan = b.read(out/'source-pins.json'),b.read(out/'selection.json')
    b.require(b.read(out/'prepared.json') == dict(state='PREPARED_ATTENTION_NOT_EXECUTED',
        source_pins_sha256=b.sha(out/'source-pins.json')), 'Prepared inventory changed')
    b.verify(pins)
    socdir,build = Path(plan['soc_build']),Path(plan['build'])
    soc,sw,required = collect(socdir,build)
    b.require((sw['kind']=='abba') == (plan['smoke_run'] is not None), 'Invalid smoke admission')
    if plan['smoke_run'] is not None:
        required.update(admitted_smoke(Path(plan['smoke_run']),socdir))
    b.require(plan == selection(out,socdir,build,soc,sw,plan['smoke_run'],plan['environment'],plan['python']),
              'Execution selection changed')
    frozen = b.files(out/'inputs')
    b.require(set(frozen) == {str(out/'inputs'/n) for n in (*OWN,'build_soc.py')}, 'Unexpected runner inputs')
    required.update(frozen)
    required[str(out/'selection.json')] = b.sha(out/'selection.json')
    b.require(all(pins.get(p) == h for p,h in required.items()), 'Missing required input pin')
    return plan,pins,soc,sw


def service_unit(out):
    return 'stage3-attention-'+out.name+'.service'


def service_command(out,review):
    plan, *_ = verify_prepared(out)
    b.require(review == b.sha(out/'source-pins.json') and not (out/'attempt.json').exists() and
              not (out/'result.json').exists(), 'Review mismatch or already attempted')
    return ['/usr/bin/systemd-run','--user','--unit='+service_unit(out),
        '--property=WorkingDirectory='+str(out/'work'),'--property=RuntimeMaxSec=7200',
        '--property=KillMode=control-group','--property=TimeoutStopSec=20',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        plan['python'],'-B','-u',str(out/'inputs/run.py'),'run','--output',str(out),'--review-sha256',review]


def run(out,review):
    out = output_path(out)
    b.require(Path(__file__).resolve() == out/'inputs/run.py', 'Execute frozen runner')
    ownership = b.claim_attempt(out,review,service_unit(out),terminal='result.json')
    base,_ = b.helpers()
    status = dict(state='PREFLIGHT',child_pid=None,**ownership)
    result = dict(state='FAIL',numerical_checked=False,independent_protocol_checked=False,
                  performance_measured=False,performance_acceptance=False,whole_model=False,
                  deployment_approved=False,automatic_retry=False)
    try:
        b.require(not any((out/'work').iterdir()), 'Stale work; no retry')
        plan,pins,soc,sw = verify_prepared(out)
        old,_,_ = legacy()
        os.environ.clear()
        os.environ.update(plan['environment'])
        for name in ('test_run.py','test_check_work.py'):
            base.execute([plan['python'],'-B',str(out/'inputs'/name)],out/'inputs',
                         out/(name+'.log'),120,status,out/'status.json','HOST_TESTS')
        commands = plan['commands']
        base.execute(commands['image_contract'],out/'work',out/'image-contract.log',180,
                     status,out/'status.json','IMAGE_CONTRACT')
        verify_prepared(out)
        start = time.monotonic()
        base.execute(commands['simulation'],out/'work',out/'work/console.log',5400,
                     status,out/'status.json','RUNNING')
        wall = time.monotonic()-start
        checked = numerical_and_work(out,sw)
        base.execute(commands['protocol'],out/'work',out/'work/checker.log',900,
                     status,out/'status.json','PROTOCOL_CHECK')
        old.check_protocol(b.read(out/'work/uvm_result.json'),soc,sw,
                           out/'work/run.vcs.log',out/'work/vector_trace.csv')
        execution_receipts(out,plan)
        verify_prepared(out)
        b.require(b.sha(out/'source-pins.json') == review, 'Review identity changed')
        result.update(state='PASS',kind=sw['kind'],numerical_checked=True,independent_protocol_checked=True,
            performance_measured=True,post_pins_match=True,post_image_match=True,source_pins_sha256=review,
            image_pins=soc['image_pins'],elf_sha256=sw['elf_sha256'],simulation_wall_seconds=wall,**checked)
    except BaseException as exc:
        result['error'] = repr(exc)
    result['artifacts'] = b.files(out,exclude=('status.json','service.stdout.log','service.stderr.log'))
    b.save(out/'result.json',result)
    status.update(state=result['state'],child_pid=None)
    base.save(out/'status.json',status)
    print(json.dumps(dict(state=result['state'],output=str(out))),flush=True)
    return int(result['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    subs = parser.add_subparsers(dest='action',required=True)
    for name in ('prepare','preflight','service-command','run'):
        p = subs.add_parser(name,allow_abbrev=False)
        p.add_argument('--output',type=Path,required=True)
        if name == 'prepare':
            p.add_argument('--soc-build',type=Path,required=True)
            p.add_argument('--build',type=Path,required=True)
            p.add_argument('--smoke-run',type=Path)
        if name in ('service-command','run'):
            p.add_argument('--review-sha256',required=True)
    a = parser.parse_args()
    out = output_path(a.output)
    if a.action == 'prepare':
        prepare(out,a.soc_build,a.build,a.smoke_run)
        print('PREPARED_ATTENTION_NOT_EXECUTED '+b.sha(out/'source-pins.json'))
    elif a.action == 'preflight':
        verify_prepared(out)
        print('PREFLIGHT_PASS_NOT_EXECUTED')
    elif a.action == 'service-command':
        print(shlex.join(service_command(out,a.review_sha256)))
    else:
        return run(out,a.review_sha256)
    return 0


if __name__ == '__main__':
    def interrupted(sig,_frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,interrupted)
    sys.exit(main())
