"""Static preparation now; one offline terminal reconstruction after parent authorization."""
import argparse
import ast
import csv
from datetime import datetime
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
from support import HERE, G, TRANSPORT, TRANSPORT_SHA, add, elf, load, read, save, sha, verify
from observer import Observer, model

R = G/'merge_original_prefix98_vcs_m6_plan01'
P = R/'prepared01'
F = G/'merge_original_prefix98_prepare01'
NAME = 'merge_prefix_e16_m8_ops4'
UNIT = 'ara-merge-original-prefix98-m6-01.service'
PLAN_SHA = 'f97d3e2a933bfde527b1dd06b54f0055cb1bc2fca103d97308b1d0d45104b079'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
READY_SHA = '8381b90ee089c90be273faca67b8096f802f628f655fd5756a186ef57b3ed175'
CHECKER_SHA = '68ea8fac710500f9dda01606b4c633d91d09fdf1c75d6db766e316b7dfd01683'
RUNNER_SHA = 'fba6b7d84d530d0b7a40e2ac25ae99231970a610aeeb34020cfc9dd2a13b7942'
PASS = 'PASS_M6_ORIGINAL_MERGE_PREFIX98_NOT_FULL_CHILD'


def static_identity():
    # Never open or scan replay/, launch.json, service.log or complete.json here.
    assert sha(P/'plan.json') == PLAN_SHA and sha(F/'READY.json') == READY_SHA
    plan, ready = read(P/'plan.json'), read(F/'READY.json')
    assert plan['status'] == 'PREPARED_NOT_RUN' and len(plan['pins']) == 725
    assert plan['image_sha256'] == IMAGE_SHA and plan['unit'] == UNIT
    assert (plan['jobs'], plan['timeout_s'], plan['service_timeout_s']) == (1, 9000, 10200)
    assert all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb'))
    assert plan['full_child_acceptance'] is False and plan['exact_historical_stopped_tuple'] is None
    pins = {str(P/'plan.json'): PLAN_SHA, str(F/'READY.json'): READY_SHA,
            str(TRANSPORT): TRANSPORT_SHA, str(R/'checker.py'): CHECKER_SHA, str(R/'replay.py'): RUNNER_SHA}
    def bind(path):
        path = str(path)
        assert path in plan['pins'], ('missing static source pin', path)
        add(pins, {path: plan['pins'][path]})
    case, spec = plan['case'], plan['spec']
    assert case['id'] == case['original_name'] == NAME and case['timeout_s'] == 9000
    assert (spec['sew'], spec['lmul'], spec['element_bytes']) == (16, 8, 2)
    assert case['sha256'] == spec['elf_sha256'] == ready['soc_elf']['sha256'] == sha(case['elf'])
    for path in (Path(case['elf']), F/'source_elf_proof.json', F/'reference_check.py',
                 F/'prepared'/NAME/'case.c', F/'prepared'/NAME/'original/scenario.c',
                 F/'prepared'/NAME/'original/operations.S', F/'soc01/programs.json'):
        bind(path)
    proof = read(F/'source_elf_proof.json')
    original_c = next(Path(p) for p in ready['baseline_pins'] if p.endswith('/original.c'))
    original_binary = next(Path(p) for p in ready['baseline_pins'] if '/release/binaries/' in p)
    bind(original_c); bind(original_binary)
    assert sha(original_c) == proof['original_c_sha256']
    assert sha(original_binary) == proof['original_linux_elf_sha256']
    ctext = original_c.read_text(); port = (F/'prepared'/NAME/'case.c').read_text()
    oracle = ctext[ctext.index('static unsigned selected'):ctext.index('void probe_main')]
    assert oracle in port and 'if(cases==98)goto prefix_done;' in port
    assert 'if(output[0]!=(word)0x5b || output[cap+1]!=(word)0x5b)++errors;' in port
    assert 'for(unsigned i=0;i<cap;++i){\n                unsigned pick=selected(mode,i);' in port
    get, symbols = elf(case['elf']); old, _ = elf(original_binary)
    assert spec['symbols'] == {n: symbols[n][0] for n in spec['symbols']}
    assert spec['addresses'] == {n: symbols[n][0] for n in spec['addresses']}
    instructions = sorted(spec['instructions'].values(), key=lambda row: row['pc'])
    for key, row in spec['instructions'].items():
        assert int(key, 16) == row['pc'] and get(row['pc'], len(row['insn'])//2) == bytes.fromhex(row['insn'])[::-1]
    routine = spec['routine']
    assert routine == proof['soc_routine'] and len(routine) == 13
    assert len(proof['original_routine']) == 13 and routine[8]['insn'] == '5c880c57'
    for a, b in zip(proof['original_routine'], routine):
        assert a['insn'] == b['insn'] and old(a['pc'], len(a['insn'])//2) == get(b['pc'], len(b['insn'])//2)
    ranges = []
    for op in range(21):
        start = symbols[NAME+'_op_'+str(op)][0]
        rows = [r for r in instructions if r['pc'] >= start][:13]
        assert len(rows) == 13 and rows[0]['pc'] == start and rows[-1]['insn'] == '8082'
        assert all(b['pc'] == a['pc']+len(a['insn'])//2 for a, b in zip(rows, rows[1:]))
        if op == 4: assert rows == routine
        else: ranges.append([rows[0]['pc'], rows[-1]['pc']+len(rows[-1]['insn'])//2])
    assert ranges == spec['unused_ranges'] and len(ranges) == 20
    cap = [r for r in instructions if r['pc'] >= symbols[NAME+'_capacity'][0]][:3]
    assert cap == spec['capacity'] and [r['insn'] for r in cap] == ['52fd', '00b2f557', '8082']
    sy = spec['symbols']
    prelude = [r for r in instructions if int(r['insn'], 16)&127 == 0x73 and (int(r['insn'], 16)>>12)&7 and
               (r['pc'] < sy['trap_entry'] or sy['main'] <= r['pc'] < sy['text'] or sy[NAME+'_main'] <= r['pc'] < sy[NAME+'_capacity'])]
    assert prelude == spec['prelude'] and len(prelude) == 7
    assert [r['insn'] for r in prelude[:5]] == ['30401073', '30529073', '3002a073', '00305073', '00805073']
    assert all(int(r['insn'], 16)&~0xf80 == 0xc2202073 for r in prelude[5:])
    enc = dict(input='00e81023', indices='00f51023', indices16='00f59023', pred_clear='00068023',
               pred_pack='00f70023', output_init='00d71023', output_read='002a5683',
               guard0='fd07d783', guard1='0007d783', filter='20fc1963')
    for name, encoding in enc.items():
        assert [r['pc'] for r in instructions if r['insn'] == encoding and sy[NAME+'_main'] <= r['pc'] < sy[NAME+'_capacity']] == [spec['sites'][name]]
    assert spec['exit_address'] == 0xd0000000 and spec['park']['insn'] == 'a001'
    assert spec['exit_store'] in instructions and spec['park'] in instructions
    verify(pins)
    # Pure model evaluation only; none of the disassembler/Spike/Host entrypoints is called.
    checker = load(R/'checker.py', 'sealed_merge98_checker')
    gold = model()
    assert gold == checker.source.model(), 'Independent original formula/tuple model differs'
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and str(Path(path).resolve()) in plan['pins']:
            bind(Path(path).resolve())
    verify(pins)
    return plan, pins, gold, checker


def prepare():
    assert not (HERE/'prepared.json').exists() and not (HERE/'model.json').exists()
    plan, pins, gold, _ = static_identity()
    for name in ('audit.py', 'observer.py', 'support.py', 'README.md'):
        path = HERE/name
        if path.suffix == '.py': ast.parse(path.read_text(), filename=str(path))
        add(pins, {str(path): sha(path)})
    counts = [0, 0]
    for row in gold['rows']:
        for i in range(row['vstart'], row['vl']): counts[(row['predicate'][i//8] >> (i % 8)) & 1] += 1
    assert counts == [2722, 2669]
    save(HERE/'model.json', gold); add(pins, {str(HERE/'model.json'): sha(HERE/'model.json')})
    save(HERE/'prepared.json', dict(status='STATIC_PREPARED_NOT_TERMINAL_AUDITED', plan_sha256=PLAN_SHA,
        image_sha256=IMAGE_SHA, static_pins=pins, full_plan_pin_count=len(plan['pins']),
        calls=98, predecessors=97, fullcap_element_checks=50176, guard_element_checks=196,
        scalar_lhu_checks=50372, returned_vstart_reads=98, helper_instructions_per_call=13,
        unused_helper_ranges=20, selector_zero_body_elements=2722, selector_one_body_elements=2669,
        terminal_reads=0, csv_reads=0, live_queries=0, host_suite_executed=False,
        Spike_executed=False, DUT_executed=False, compiler_executed=False,
        static_checks='AST, pinned source/ELF/spec bytes and independent pure source model parity only',
        requires_later_parent_authorization=True, full_child_acceptance=False,
        exact_historical_stopped_tuple=None, reference_is_not_DUT_evidence=True))
    print('STATIC_PREPARED_NOT_TERMINAL_AUDITED', sha(HERE/'prepared.json'), flush=True)


def terminal(args):
    assert args.authorize_terminal_audit and args.prepared_sha256 and args.complete_sha256 and args.out
    assert sha(HERE/'prepared.json') == args.prepared_sha256
    prepared = read(HERE/'prepared.json'); verify(prepared['static_pins'])
    started = time.monotonic()
    plan, _, gold, checker = static_identity()
    assert gold == read(HERE/'model.json')
    assert sha(P/'complete.json') == args.complete_sha256
    done, run, summary = read(P/'complete.json'), read(P/'replay/run.json'), read(P/'replay/summary.json')
    assert done['status'] == PASS and done['plan_sha256'] == PLAN_SHA
    assert done['aborted'] is False and done['pins_unchanged'] is True and done['retries'] == 0 and not done.get('error')
    assert done['full_child_acceptance'] is False and done['exact_historical_stopped_tuple'] is None
    assert done['results'] == summary and len(summary) == 1
    result = summary[0]; root = P/'replay/tests'/NAME
    assert result['name'] == NAME and result['kind'] == 'app' and result['status'] == 'PASS'
    assert result['returncode'] == 0 and not result['reason'] and 0 < result['elapsed_s'] <= 9000
    assert result['artifact_dir'] == str(root)
    assert run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 1} and run['tests'] == [NAME]
    assert run['completed_at'] and run['jobs'] == run['seed'] == 1 and run['timeout_s'] == 9000
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
    expected = [P/'launch.json', P/'replay/run.json', P/'replay/summary.json'] + [root/n for n in artifacts]
    assert set(done['evidence_pins']) == {str(p) for p in expected} and len(expected) == 11
    pins = dict(prepared['static_pins']); add(pins, plan['pins']); add(pins, done['evidence_pins'])
    add(pins, {str(HERE/'prepared.json'): args.prepared_sha256, str(P/'complete.json'): args.complete_sha256})
    add(pins, ledger['files']); add(pins, {str(Path(snap['root'])/p): h for p, h in snap['files'].items()})
    launch = read(P/'launch.json'); add(pins, launch['approval_pins'])
    assert launch['plan_sha256'] == PLAN_SHA and launch['started'] <= done['finished'] < launch['started']+10200
    owner = launch['owner']; prop = owner['properties']
    assert prop['Id'] == UNIT and prop['MainPID'] == str(owner['pid']) and int(prop['MainPID']) > 0
    assert prop['LoadState'] == 'loaded' and prop['ActiveState'] == 'active' and prop['SubState'] == 'running'
    assert prop['Restart'] == 'no' and prop['KillMode'] == 'control-group' and prop['RuntimeMaxUSec'] == '2h 50min'
    assert prop['ControlGroup'].endswith('/'+UNIT) and prop['ControlGroup'] in [l.split(':', 2)[-1] for l in owner['cgroup'].splitlines()]
    argv = run['invocation']
    assert argv[:2] == [str(R/'replay.py'), 'run'] and '--authorize-run' in argv
    assert argv[argv.index('--plan-sha256')+1] == PLAN_SHA
    review_path, review_sha = argv[argv.index('--parent-review')+1], argv[argv.index('--parent-review-sha256')+1]
    add(pins, {review_path: review_sha}); review = read(review_path)
    assert review['decision'] == 'AUTHORIZE_MERGE_PREFIX98_ONCE' and review['plan_sha256'] == PLAN_SHA
    assert review['unit'] == UNIT and review['budget_risk_accepted'] is True
    for key in ('reference_ready_sha256', 'reference_admission_sha256', 'reference_review_sha256'):
        assert review[key] == plan[key]
    verify(pins)
    assert not (P/'complete.tmp').exists()
    assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout', p.name, re.I) for p in P.rglob('*') if p.is_file())
    case = plan['case']
    assert sha(root/'input.elf') == case['sha256'] == sha(case['elf'])
    assert read(root/'inputs.json')['binary'] == dict(source=case['elf'], path=str(root/'input.elf'), sha256=case['sha256'])
    assert read(root/'inputs.json')['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files'])
    assert read(root/'command.json') == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
        '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+NAME, '+NO_FSDB', '+COMMIT_TRACE='+str(root/'commit_trace.csv')], cwd=str(root/'work'))
    target = args.out.resolve()
    assert target.parent == HERE and not target.exists(), 'Fresh owned audit output only'
    target.mkdir()
    try:
        for path in (root/'console.log', root/'work/run.vcs.log'):
            text = path.read_text(); checker.console_gate(text)
            assert not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b', text, re.I)
        observer = Observer(plan['spec'], gold)
        with (root/'commit_trace.csv').open(newline='') as stream:
            strict = checker.retirement(observer.rows(csv.DictReader(stream)), plan['spec'], gold)
        generic = observer.finish()
        generated = dict(generic=generic, strict=strict, csv_sha256=pins[str(root/'commit_trace.csv')])
        assert generated == read(root/'strict_prefix.json')
        assert dict(generic, status='VALID') == read(root/'trace_summary.json')
        verify(pins)
        save(target/'verified_pins.json', pins)
        save(target/'result.json', dict(status='INDEPENDENT_M6_MERGE98_FULL_ORACLE_ACCEPTED_NOT_FULL_CHILD',
            accepted=True, plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, prepared_sha256=args.prepared_sha256,
            complete_sha256=args.complete_sha256, elf_sha256=case['sha256'], generated=generated,
            observer=observer.evidence(), pins_pre_post_unchanged=True, pins_verified=len(pins),
            full_plan_pins=725, terminal_evidence_pins=11, csv_parses=1,
            child_returncode=result['returncode'], child_elapsed_s=result['elapsed_s'], aborted=False,
            raw_logs_firsterror_veto_pass=True, outer_service_terminal_observed=False,
            outer_service_returncode=None, outer_service_result=None, reference_used_as_DUT_evidence=False,
            full_child_acceptance=False, exact_historical_stopped_tuple=None,
            original_Linux_ELF_replay=False, no_guest_execution=True, audit_seconds=time.monotonic()-started))
        print('INDEPENDENT_M6_MERGE98_FULL_ORACLE_ACCEPTED_NOT_FULL_CHILD', sha(target/'result.json'), flush=True)
    except BaseException as error:
        save(target/'not_accepted.json', dict(status='NOT_ACCEPTED', accepted=False, error=repr(error),
            plan_sha256=PLAN_SHA, complete_sha256=args.complete_sha256))
        raise


def main():
    assert __debug__, 'Assertion gates require python without -O'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'terminal'])
    parser.add_argument('--authorize-terminal-audit', action='store_true')
    parser.add_argument('--prepared-sha256'); parser.add_argument('--complete-sha256')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        assert not any((args.authorize_terminal_audit, args.prepared_sha256, args.complete_sha256, args.out))
        prepare()
    else: terminal(args)


if __name__ == '__main__': main()
