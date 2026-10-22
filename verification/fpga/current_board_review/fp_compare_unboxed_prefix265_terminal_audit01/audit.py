"""Static preparation, then explicitly authorized one-pass offline terminal audit."""
import argparse
import ast
import csv
from datetime import datetime
import hashlib
import importlib.util
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parent
SUPPORT = G/'merge_original_prefix98_terminal_audit01/support.py'
SUPPORT_SHA = '4ad5c6b27d60f62e36f406c809bf2aeb4a9f22822e02934f334c3c1a175c52a6'
assert hashlib.sha256(SUPPORT.read_bytes()).hexdigest() == SUPPORT_SHA
ms = importlib.util.spec_from_file_location('unboxed_audit_support', SUPPORT)
u = importlib.util.module_from_spec(ms)
ms.loader.exec_module(u)
read, sha, save, add, verify = u.read, u.sha, u.save, u.add, u.verify
from observer import observer_class

R = G/'fp_compare_unboxed_prefix265_vcs_m6_plan01'
P = R/'prepared01'
F = G/'fp_compare_unboxed_prefix265_prepare01'
NAME = 'fp_compare_unboxed_e16_mf4_prefix265'
UNIT = 'ara-fp-unboxed-original265-m6-01.service'
PLAN_SHA = 'e3bbb288f69f8f0cc0a24491125e0bb327e04d3edbaa3eb46837bb2c153e0940'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
READY_SHA = 'ee10a401774a5cb474be69c317edad4ea052c147a42b5fd03aa4cc4b1f5db731'
PASS = 'PASS_M6_ORIGINAL_UNBOXED265_NOT_FULL_PARENT'


def static_identity():
    # Only frozen plan/source/spec inputs; never enumerate or read replay/ here.
    assert sha(P/'plan.json') == PLAN_SHA and sha(F/'READY.json') == READY_SHA
    plan, ready = read(P/'plan.json'), read(F/'READY.json')
    assert plan['status'] == 'PREPARED_NOT_RUN' and len(plan['pins']) == 733
    assert plan['image_sha256'] == IMAGE_SHA and plan['unit'] == UNIT
    assert (plan['jobs'], plan['timeout_s'], plan['service_timeout_s']) == (1, 5400, 6600)
    assert all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb'))
    assert plan['full_parent_acceptance'] is False and plan['reference_ready_sha256'] == READY_SHA
    pins = {str(P/'plan.json'): PLAN_SHA, str(F/'READY.json'): READY_SHA,
            str(SUPPORT): SUPPORT_SHA, str(u.TRANSPORT): u.TRANSPORT_SHA}
    case, s = plan['case'], plan['spec']
    assert case['id'] == NAME and case['timeout_s'] == 5400 and s['spike'] is False
    assert case['sha256'] == s['elf_sha256'] == ready['soc_elf']['sha256'] == sha(case['elf'])
    assert ready['scope'] == dict(calls=265, predecessors=264, capacity=16, result_bits=4240, guards=530, vstart=265, flags=265)
    paths = [Path(case['elf']), R/'checker.py', R/'dut_strict.py', R/'replay.py', F/'model.py',
             F/'software_prepare.py', F/'software/case.c', F/'software/original/parent.c',
             F/'software/original/scenario.S', F/'soc/elf.json']
    for p in paths:
        add(pins, {str(p): plan['pins'][str(p)]})
    verify(pins)
    get, symbols = u.elf(case['elf'])
    assert s['symbols'] == {n: symbols[n][0] for n in s['symbols']}
    for key, row in s['code'].items():
        assert int(key, 16) == row['pc'] and get(row['pc'], len(row['insn'])//2) == bytes.fromhex(row['insn'])[::-1]
    for name, rows in s['functions'].items():
        assert rows[0]['pc'] == symbols[name][0]
        assert all(s['code'][f"{r['pc']:x}"] == r for r in rows)
        assert all(b['pc'] == a['pc']+len(a['insn'])//2 for a, b in zip(rows, rows[1:]))
    assert s['routines'] == [s['functions']['op_'+str(i)] for i in range(10)]
    assert [len(rr) for rr in s['routines']] == [17]*4+[19]*6
    assert s['routines'][4][7]['insn'] == 'f2038053' and s['routines'][4][10]['insn'] == '62805c57'
    assert s['capacity'] == s['functions']['capacity'] and [r['insn'] for r in s['capacity']] == ['52fd', '00e2f557', '8082']
    assert len(s['prelude']) == 6 and s['exit_address'] == 0xd0000000 and s['park']['insn'] == 'a001'
    base = read(F/'soc/elf.json')
    assert all(s[k] == base[k] for k in base)
    original = (F/'software/original/parent.c').read_text()
    port = (F/'software/case.c').read_text()
    assert original[original.index('        if((uint32_t)status)'):original.index('        ++cases;')] in port
    assert 'if(cases==265)goto prefix_done;' in port
    sys.path.insert(0, str(R))
    checker = u.load(R/'checker.py', 'sealed_unboxed265_checker')
    assert Path(checker.source.__file__).resolve() == R/'dut_strict.py'
    # Pure integer model only; never specification(), disassembler or guest execution.
    gold = checker.source.model()
    assert len(gold['rows']) == 265 and gold['predecessors'] == 264
    assert [sum(g['op'] == op for g in gold['rows']) for op in range(5)] == [56]*4+[41]
    assert (gold['rows'][-1]['op'], gold['rows'][-1]['vl'], gold['rows'][-1]['flags']) == (4, 15, 0)
    for module in tuple(sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and str(Path(p).resolve()) in plan['pins']:
            p = str(Path(p).resolve()); add(pins, {p: plan['pins'][p]})
    verify(pins)
    transport = u.load(u.TRANSPORT, 'sealed_lossless_transport')
    return plan, pins, gold, checker, observer_class(transport)


def prepare():
    assert not (HERE/'prepared.json').exists()
    plan, pins, gold, _, _ = static_identity()
    for name in ('audit.py', 'observer.py', 'README.md'):
        p = HERE/name
        if p.suffix == '.py': ast.parse(p.read_text(), filename=str(p))
        add(pins, {str(p): sha(p)})
    save(HERE/'prepared.json', dict(status='STATIC_PREPARED_NOT_TERMINAL_AUDITED',
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, static_pins=pins, full_plan_pin_count=len(plan['pins']),
        calls=265, predecessors=264, result_bits=4240, guards=530, flags=265, vstart=265,
        helper_instructions=4587, unused_full_ranges=5, rawft0_instructions=41,
        pure_model_sha256=hashlib.sha256(__import__('json').dumps(gold, sort_keys=True).encode()).hexdigest(),
        csv_reads=0, terminal_reads=0, live_queries=0, host_suite_executed=False,
        guest_execution=False, requires_terminal_authorization=True, full_parent_acceptance=False))
    print('STATIC_PREPARED_NOT_TERMINAL_AUDITED', sha(HERE/'prepared.json'), flush=True)


def terminal(args):
    assert args.authorize_terminal_audit and args.prepared_sha256 and args.complete_sha256 and args.out
    assert sha(HERE/'prepared.json') == args.prepared_sha256
    prepared = read(HERE/'prepared.json'); verify(prepared['static_pins'])
    target = args.out.resolve()
    assert target.parent == HERE and not target.exists(), 'Fresh owned output only'
    target.mkdir()
    started = time.monotonic()
    try:
        plan, _, gold, checker, Observer = static_identity()
        assert sha(P/'complete.json') == args.complete_sha256
        done, run, summary = read(P/'complete.json'), read(P/'replay/run.json'), read(P/'replay/summary.json')
        assert done['status'] == PASS and done['plan_sha256'] == PLAN_SHA
        assert done['aborted'] is False and done['pins_unchanged'] is True and done['retries'] == 0 and not done.get('error')
        assert done['full_child_acceptance'] is False and done['results'] == summary and len(summary) == 1
        result = summary[0]; root = P/'replay/tests'/NAME
        assert result['name'] == NAME and result['kind'] == 'app' and result['status'] == 'PASS'
        assert type(result['returncode']) is int and result['returncode'] == 0 and not result['reason']
        assert 0 < result['elapsed_s'] <= 5400 and result['artifact_dir'] == str(root)
        assert run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 1} and run['tests'] == [NAME]
        assert run['jobs'] == run['seed'] == 1 and run['timeout_s'] == 5400
        assert run['commit_trace'] is True and run['code_coverage'] is False and run['input_snapshots'] is True
        assert datetime.fromisoformat(run['completed_at']) > datetime.fromisoformat(run['created_at'])
        image = Path(plan['image']); ledger = read(image/'image.json')
        assert sha(image/'image.json') == IMAGE_SHA and run['simv'] == ledger['simv']
        snapshot = Path(ledger['snapshot'])/'snapshot.json'; snap = read(snapshot)
        assert sha(snapshot) == plan['snapshot_sha256'] == ledger['snapshot_sha256']
        assert snap['state'] == 'SEALED' and len(snap['files']) == 539 and len(ledger['files']) == 66
        assert sha(image/'_build/vcs/simulator.conf') == ledger['configuration_sha256'] == '6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
        assert sha(image/'_build/vcs/vcs_source_manifest.json') == ledger['manifest_sha256']
        artifacts = ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log', 'commit_trace.csv', 'trace_summary.json', 'strict_prefix.json')
        expected = [P/'launch.json', P/'replay/run.json', P/'replay/summary.json']+[root/n for n in artifacts]
        assert set(done['evidence_pins']) == {str(p) for p in expected}
        pins = dict(prepared['static_pins']); add(pins, plan['pins']); add(pins, done['evidence_pins'])
        add(pins, {str(HERE/'prepared.json'): args.prepared_sha256, str(P/'complete.json'): args.complete_sha256})
        add(pins, ledger['files']); add(pins, {str(Path(snap['root'])/p): h for p, h in snap['files'].items()})
        launch = read(P/'launch.json'); add(pins, launch['approval_pins'])
        assert launch['plan_sha256'] == PLAN_SHA and launch['started'] <= done['finished'] < launch['started']+6600
        owner = launch['owner']; prop = owner['properties']
        assert prop['Id'] == UNIT and prop['MainPID'] == str(owner['pid']) and int(prop['MainPID']) > 0
        assert (prop['LoadState'], prop['ActiveState'], prop['SubState']) == ('loaded', 'active', 'running')
        assert prop['Restart'] == 'no' and prop['KillMode'] == 'control-group' and prop['RuntimeMaxUSec'] == '1h 50min'
        assert prop['ControlGroup'].endswith('/'+UNIT) and prop['ControlGroup'] in [l.split(':', 2)[-1] for l in owner['cgroup'].splitlines()]
        argv = run['invocation']
        assert argv[:2] == [str(R/'replay.py'), 'run'] and '--authorize-run' in argv
        assert argv[argv.index('--plan-sha256')+1] == PLAN_SHA
        rp, rh = argv[argv.index('--parent-review')+1], argv[argv.index('--parent-review-sha256')+1]
        add(pins, {rp: rh}); review = read(rp)
        assert review['decision'] == 'AUTHORIZE_UNBOXED_ORIGINAL265_ONCE' and review['plan_sha256'] == PLAN_SHA
        assert review['unit'] == UNIT and review['budget_risk_accepted'] is True and review['reference_ready_sha256'] == READY_SHA
        for key in ('reference_audit', 'reference_review'):
            entry = review[key]; add(pins, {entry['path']: entry['sha256']})
        ref = read(review['reference_audit']['path'])
        assert ref['status'] == 'ACCEPTED_SOURCE_REFERENCE_ONLY_NOT_DUT' and ref['ready_sha256'] == READY_SHA
        verify(pins)
        assert not (P/'complete.tmp').exists()
        assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout', p.name, re.I) for p in P.rglob('*') if p.is_file())
        case = plan['case']
        assert sha(root/'input.elf') == case['sha256'] == sha(case['elf'])
        assert read(root/'inputs.json')['binary'] == dict(source=case['elf'], path=str(root/'input.elf'), sha256=case['sha256'])
        assert read(root/'inputs.json')['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files'])
        assert read(root/'command.json') == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
            '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+NAME, '+NO_FSDB', '+COMMIT_TRACE='+str(root/'commit_trace.csv')], cwd=str(root/'work'))
        for path in (root/'console.log', root/'work/run.vcs.log'):
            text = path.read_text(); checker.console_gate(text)
            assert not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b', text, re.I)
        observer = Observer(plan['spec'], gold)
        with (root/'commit_trace.csv').open(newline='') as stream:
            strict = checker.source.audit(checker.convert(observer.rows(csv.DictReader(stream))), plan['spec'])
        generic = observer.finish()
        assert strict['retired'] == generic['retire_count'] and strict['helper_instructions'] == 4587
        assert strict['actual_initialization_stores'] == 76850
        assert strict['target_calls'] == 265 and strict['full_result_bit_checks'] == 4240 and strict['guard_checks'] == 530
        assert strict['returned_vstart_zero'] == strict['returned_flags_checked'] == 265
        assert strict['unused_helper_retirements'] == 0 and strict['full_reference_vectors'] is False
        generated = dict(strict=strict, generic=generic, csv_sha256=pins[str(root/'commit_trace.csv')],
                         scope='Scalar full oracle, no direct DUT vector payload claim')
        assert generated == read(root/'strict_prefix.json')
        assert dict(generic, status='VALID') == read(root/'trace_summary.json')
        verify(pins)
        save(target/'verified_pins.json', pins)
        save(target/'result.json', dict(status='INDEPENDENT_M6_UNBOXED265_FULL_ORACLE_ACCEPTED_NOT_FULL_PARENT',
            accepted=True, plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, prepared_sha256=args.prepared_sha256,
            complete_sha256=args.complete_sha256, elf_sha256=case['sha256'], generated=generated,
            observer=observer.evidence(), pins_pre_post_unchanged=True, pins_verified=len(pins),
            full_plan_pins=len(plan['pins']), terminal_evidence_pins=len(expected), csv_parses=1,
            child_returncode=result['returncode'], child_elapsed_s=result['elapsed_s'], aborted=False,
            raw_logs_firsterror_veto_pass=True, outer_service_terminal_observed=False,
            outer_service_returncode=None, outer_service_result=None, reference_used_as_DUT_evidence=False,
            full_parent_acceptance=False, original_Linux_ELF_replay=False, no_guest_execution=True,
            audit_seconds=time.monotonic()-started))
        print('INDEPENDENT_M6_UNBOXED265_FULL_ORACLE_ACCEPTED_NOT_FULL_PARENT', sha(target/'result.json'), flush=True)
    except BaseException as error:
        save(target/'not_accepted.json', dict(status='NOT_ACCEPTED', accepted=False, error=repr(error),
             plan_sha256=PLAN_SHA, complete_sha256=args.complete_sha256))
        raise


def main():
    assert __debug__, 'Assertions require Python without -O'
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'terminal'))
    p.add_argument('--authorize-terminal-audit', action='store_true')
    p.add_argument('--prepared-sha256'); p.add_argument('--complete-sha256'); p.add_argument('--out', type=Path)
    args = p.parse_args()
    if args.mode == 'prepare':
        assert not any((args.authorize_terminal_audit, args.prepared_sha256, args.complete_sha256, args.out))
        prepare()
    else: terminal(args)


if __name__ == '__main__': main()
