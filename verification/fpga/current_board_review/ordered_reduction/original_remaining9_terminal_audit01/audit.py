"""Prepare static identities now; audit terminal CSVs only after fresh authorization."""
import argparse
import ast
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import time

sys.dont_write_bytecode = True
from observer import Observer

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
R = ROOT/'original_remaining9_vcs_m6_plan01'
P = R/'prepared01'
F = ROOT/'original_remaining9_prepare01'
PLAN_SHA = '10807a26d22d6beb48acdd075e3e1ccea37e5ca69f38c783ce2ed9027375891a'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
CHECKER_SHA = '2e92159b44879c96e2faca67cec3744d08c2633d507abd3d0afc91cf6f65ee15'
RUNNER_SHA = 'ca22d0134b40d53fb14534b853128d1ae20362c8cdd2b289566ab4b44536bab8'
SHAPES = ['e16_mf2', 'e16_m1', 'e16_m2', 'e16_m4', 'e16_m8', 'e32_mf2', 'e32_m2', 'e32_m4', 'e32_m8']
CAPS = [32, 64, 128, 256, 512, 16, 64, 128, 256]
UNIT = 'ara-redspecial-remaining9-original-m6-01.service'
PASS = 'PASS_M6_ORIGINAL_REMAINING9_SINGLES1296_NOT_FULL_PARENTS'
LIMITATION = ('DUT observes original CSR reads and retirement/saved-zero operands of restore writes; '
              'no post-restore frm/fflags readback or internal signal observation. '
              'Reference CSR logs do not extend DUT scope.')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2); f.write('\n')


def add(pins, mapping):
    for path, digest in mapping.items():
        assert path not in pins or pins[path] == digest, ('conflicting identity', path)
        pins[path] = digest


def verify(pins):
    for path, digest in pins.items(): assert sha(path) == digest, ('pin drift', path)


def elf_reader(path):
    b = Path(path).read_bytes()
    assert b[:6] == b'\x7fELF\x02\x01'
    ph = struct.unpack_from('<Q', b, 32)[0]
    size, n = struct.unpack_from('<HH', b, 54)
    segments = []
    for j in range(n):
        t, _, off, va, _, fs, _, _ = struct.unpack_from('<IIQQQQQQ', b, ph+j*size)
        if t == 1: segments.append((va, va+fs, off))
    def get(a, size):
        for lo, hi, off in segments:
            if lo <= a and a+size <= hi: return b[off+a-lo:off+a-lo+size]
        raise AssertionError(('unmapped ELF address', hex(a)))
    return get


def static_identity():
    # Deliberately no directory scan, terminal existence check, log or CSV open here.
    assert sha(P/'plan.json') == PLAN_SHA
    plan = read(P/'plan.json')
    assert len(plan['pins']) == 1352 and plan['status'] == 'PREPARED_NOT_RUN'
    assert plan['image_sha256'] == IMAGE_SHA and plan['unit'] == UNIT
    assert (plan['jobs'], plan['timeout_s'], plan['worker_timeout_s'], plan['service_timeout_s']) == (3, 5400, 18900, 19800)
    assert all(plan[k] is True for k in ('no_build', 'no_retry', 'no_fsdb', 'stop_first_fail'))
    assert [c['shape'] for c in plan['cases']] == SHAPES and list(plan['specs']) == SHAPES
    pins = {str(P/'plan.json'): PLAN_SHA, str(R/'checker.py'): CHECKER_SHA, str(R/'replay.py'): RUNNER_SHA}
    for path in (R/'checker.py', R/'replay.py'):
        assert plan['pins'][str(path)] == pins[str(path)]
        ast.parse(path.read_text(), filename=str(path))
    geometry = []
    def bind(path):
        path = str(path)
        assert path in plan['pins'], ('missing static pin', path)
        add(pins, {path: plan['pins'][path]})
    for case, shape, cap in zip(plan['cases'], SHAPES, CAPS):
        ref, spec = F/shape, plan['specs'][shape]
        c = spec['config']
        sew = int(shape.split('_')[0][1:]); width = sew//8
        assert (c['shape'], c['identity'], c['sew'], c['word_bytes'], c['cap'], c['vl']) == (
            shape, 'original_'+shape, sew, width, cap, cap//2)
        assert c['lmul'] == shape.split('_')[1] and c['nan'] == (0x7e00 if sew == 16 else 0x7fc00000)
        assert c['inf'] == (0x7c00 if sew == 16 else 0x7f800000)
        assert case['id'] == case['original_name'] == c['identity'] and case['timeout_s'] == 5400
        assert case['elf'] == str(ref/'soc/program.elf') and case['sha256'] == spec['elf_sha256']
        for path in (ref/'sourceproof.json', ref/'soc/symbols.json', ref/'soc/program.elf', ref/'prepared/scenario.elf'):
            bind(path)
        proof = read(ref/'sourceproof.json')
        assert c == proof['config'] and spec['symbols'] == read(ref/'soc/symbols.json')
        source = Path(c['source'])
        assert 'rvv_verified_handoff03/rvv_small_redspecial02/' in str(source)
        for name in ('scenario.c', 'operations.S', 'operations.h', 'fixtures.h', 'input_bits.h', 'fp_reduction_inputs.h'):
            bind(source/name); bind(ref/'prepared'/name)
            assert (source/name).read_bytes() == (ref/'prepared'/name).read_bytes(), (shape, name)
        get, old = elf_reader(case['elf']), elf_reader(ref/'prepared/scenario.elf')
        assert sha(case['elf']) == case['sha256']
        ins = sorted(spec['instructions'].values(), key=lambda r: r['pc'])
        for key, row in spec['instructions'].items():
            assert int(key, 16) == row['pc'] and get(row['pc'], len(row['insn'])//2) == bytes.fromhex(row['insn'])[::-1]
        for window in proof['helper_windows']['soc'].values():
            assert len(window['original']) == len(window['new']) == 21
            for a, b in zip(window['original'], window['new']):
                assert a[1] == b[1] and old(a[0], len(a[1])//2) == get(b[0], len(b[1])//2)
        windows = proof['helper_windows']['soc']
        assert spec['routine'] == [dict(pc=p, insn=i, text=t) for p, i, t in windows['op_0']['new']]
        assert spec['unused_ranges'] == [[windows[n]['new'][0][0], windows[n]['new'][-1][0]+len(windows[n]['new'][-1][1])//2] for n in ('op_1', 'op_2')]
        sy = spec['symbols']
        capacity = [r for r in ins if sy['capacity'] <= r['pc'] < sy['op_0']]
        vtype = (8 if sew == 16 else 16) | {'mf2': 7, 'm1': 0, 'm2': 1, 'm4': 2, 'm8': 3}[c['lmul']]
        assert capacity == spec['capacity_routine'] and [x['insn'] for x in capacity] == ['52fd', f'{(vtype << 20)|0x2f557:08x}', '8082']
        prelude = [r for r in ins if int(r['insn'], 16)&127 == 0x73 and (int(r['insn'], 16)>>12)&7 and
                   (r['pc'] < sy['trap_entry'] or sy['main'] <= r['pc'] < sy['text'] or sy[c['identity']+'_main'] <= r['pc'] < sy['capacity'])]
        assert prelude == spec['csr_prelude'] and len(prelude) == 7
        assert [r['insn'] for r in prelude[:5]] == ['30401073', '30529073', '3002a073', '00305073', '00805073']
        assert all(int(r['insn'], 16)&~0xf80 == 0xc2202073 for r in prelude[5:])
        encodings = dict(input_store='00ff9023' if sew == 16 else '00f2a023', seed_store='fefb1f23' if sew == 16 else 'fefb2e23',
                         mask_store='00e60023', output_init='00c68023', fixture_bits='6398', fixture_flags='479c',
                         output_read='00064803' if sew == 16 else '00064503')
        for name, encoding in encodings.items():
            matches = [r['pc'] for r in ins if r['insn'] == encoding and sy[c['identity']+'_main'] <= r['pc'] < sy['capacity']]
            assert matches == [spec['sites'][name]]
        fixtures = [[int(a, 16), int(b)] for a, b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}', (ref/'prepared/fixtures.h').read_text())]
        bits = [int(x, 16) for x in re.findall(r'UINT64_C\(0x([0-9a-fA-F]+)\)', (ref/'prepared/input_bits.h').read_text())]
        assert len(fixtures) == 6720 and fixtures == spec['fixtures'] and fixtures[4905] == [c['nan'], 16]
        assert len(bits) == 16 and bits == spec['input_bits'] and bits[12] == c['inf']
        assert spec['exit_address'] == 0xd0000000 and spec['park']['insn'] == 'a001'
        geometry.append(dict(shape=shape, sew=sew, cap=cap, vl=cap//2, word_bytes=width,
            result=hex(c['nan']), full_oracle_bytes=144, input_stores=8*cap, seed_stores=512,
            mask_stores=215040, fixture_field_reads=6720, helper_instructions=21,
            soc_elf_sha256=case['sha256'], source=str(source), unused_ranges=spec['unused_ranges']))
    verify(pins)
    return plan, pins, geometry


def prepare():
    assert not (OUT/'prepared.json').exists(), 'Exclusive preparation output'
    plan, pins, geometry = static_identity()
    for name in ('audit.py', 'observer.py', 'README.md'):
        path = OUT/name
        if path.suffix == '.py': ast.parse(path.read_text(), filename=str(path))
        add(pins, {str(path): sha(path)})
    save(OUT/'prepared.json', dict(status='STATIC_PREPARED_NOT_TERMINAL_AUDITED',
        plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, full_plan_pin_count=len(plan['pins']),
        static_pins=pins, geometry=geometry, csv_reads=0, terminal_reads=0, live_queries=0,
        runtime_tests_executed=False, reference_executed=False, DUT_executed=False,
        static_check='AST syntax plus immutable source/ELF/spec identity only; no Host suite run',
        post_restore_csr_state_directly_measured=False, limitation=LIMITATION,
        future_mode_requires='explicit parent terminal authorization and exact complete/prepared hashes'))
    print('STATIC_PREPARED_NOT_TERMINAL_AUDITED', sha(OUT/'prepared.json'), flush=True)


def terminal_metadata(plan, terminal, run, summary):
    assert terminal['status'] == PASS and terminal['plan_sha256'] == PLAN_SHA
    assert terminal['aborted'] is False and terminal['pins_unchanged'] is True and terminal['retries'] == 0
    assert terminal['full_parents_accepted'] is False and not terminal.get('error')
    assert terminal['results'] == summary and len(summary) == 9
    names = [c['id'] for c in plan['cases']]
    assert len({r['name'] for r in summary}) == 9 and {r['name'] for r in summary} == set(names)
    for row in summary:
        assert row['kind'] == 'app' and row['status'] == 'PASS' and row['returncode'] == 0 and not row['reason']
        assert 0 < row['elapsed_s'] <= 5400 and row['artifact_dir'] == str(P/'replay/tests'/row['name'])
    assert run['status'] == 'COMPLETE' and run['status_counts'] == {'PASS': 9} and run['tests'] == names
    assert run['completed_at'] and run['jobs'] == 3 and run['seed'] == 1 and run['timeout_s'] == 5400
    assert run['commit_trace'] is True and run['code_coverage'] is False and run['input_snapshots'] is True
    assert run['simv'] == str(Path(plan['image'])/'_build/vcs/simv')
    assert datetime.fromisoformat(run['completed_at']) > datetime.fromisoformat(run['created_at'])


def terminal_audit(args):
    # Authorization must be supplied later; this branch is not used by prepare.
    assert args.authorize_terminal_audit and args.complete_sha256 and args.prepared_sha256
    assert sha(OUT/'prepared.json') == args.prepared_sha256
    prepared = read(OUT/'prepared.json')
    verify(prepared['static_pins'])
    assert prepared['status'] == 'STATIC_PREPARED_NOT_TERMINAL_AUDITED'
    started = time.monotonic()
    plan, static_pins, geometry = static_identity()
    complete_path = P/'complete.json'
    assert sha(complete_path) == args.complete_sha256
    terminal = read(complete_path)
    run, summary = read(P/'replay/run.json'), read(P/'replay/summary.json')
    terminal_metadata(plan, terminal, run, summary)
    expected_evidence = [P/'launch.json', P/'replay/run.json', P/'replay/summary.json']
    artifact_names = ('input.elf', 'inputs.json', 'command.json', 'console.log', 'work/run.vcs.log',
                      'commit_trace.csv', 'trace_summary.json', 'strict_original.json')
    for case in plan['cases']: expected_evidence.extend(P/'replay/tests'/case['id']/n for n in artifact_names)
    assert set(terminal['evidence_pins']) == {str(p) for p in expected_evidence} and len(expected_evidence) == 75
    pins = dict(prepared['static_pins'])
    add(pins, plan['pins']); add(pins, terminal['evidence_pins'])
    add(pins, {str(complete_path): args.complete_sha256, str(OUT/'prepared.json'): args.prepared_sha256})
    ledger = read(Path(plan['image'])/'image.json')
    assert sha(Path(plan['image'])/'image.json') == IMAGE_SHA
    snapshot = Path(ledger['snapshot'])/'snapshot.json'
    assert sha(snapshot) == plan['snapshot_sha256'] == ledger['snapshot_sha256']
    snap = read(snapshot)
    assert snap['state'] == 'SEALED' and len(snap['files']) == 539 and len(ledger['files']) == 66
    image = Path(plan['image'])
    assert sha(image/'_build/vcs/simulator.conf') == ledger['configuration_sha256'] == '6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785'
    assert sha(image/'_build/vcs/vcs_source_manifest.json') == ledger['manifest_sha256']
    add(pins, ledger['files']); add(pins, {str(Path(snap['root'])/p): h for p, h in snap['files'].items()})
    # Bind recorded admission files without inferring a later outer service exit.
    argv = run['invocation']
    assert argv[0:2] == [str(R/'replay.py'), 'run'] and '--authorize-run' in argv
    for option in ('parent-review', 'mf4-acceptance'):
        path = argv[argv.index('--'+option)+1]
        digest = argv[argv.index('--'+option+'-sha256')+1]
        add(pins, {path: digest})
    assert argv[argv.index('--plan-sha256')+1] == PLAN_SHA
    parent = read(argv[argv.index('--parent-review')+1])
    assert parent['decision'] == 'AUTHORIZE_ORIGINAL_REMAINING9_M6_ONCE' and parent['plan_sha256'] == PLAN_SHA
    assert parent['unit'] == UNIT and parent['budget_risk_accepted'] is True
    mf4 = read(argv[argv.index('--mf4-acceptance')+1])
    assert parent['mf4_acceptance_sha256'] == argv[argv.index('--mf4-acceptance-sha256')+1]
    assert mf4['image_sha256'] == IMAGE_SHA and mf4['audit_status'] == 'INDEPENDENT_M6_ORIGINAL_E16_MF4_SINGLE144_ACCEPTED_NOT_FULL_PARENT'
    add(pins, mf4['evidence_pins'])
    launch = read(P/'launch.json')
    assert launch['plan_sha256'] == PLAN_SHA and terminal['finished'] >= launch['started']
    assert terminal['finished']-launch['started'] < plan['worker_timeout_s']
    owner = launch['owner']; props = owner['properties']
    assert props['Id'] == UNIT and props['MainPID'] == str(owner['pid']) and int(props['MainPID']) > 0
    assert props['LoadState'] == 'loaded' and props['ActiveState'] == 'active' and props['SubState'] == 'running'
    assert props['KillMode'] == 'control-group' and props['Restart'] == 'no' and props['RuntimeMaxUSec'] == '5h 30min'
    assert props['ControlGroup'].endswith('/'+UNIT) and props['ControlGroup'] in [x.split(':', 2)[-1] for x in owner['cgroup'].splitlines()]
    verify(pins)
    # This scan happens only after exact nine-result terminal authorization.
    assert not any(re.search(r'first[ _-]?(?:failure|error)|abort|cancel|timeout', p.name, re.I) for p in P.rglob('*') if p.is_file())
    assert not (P/'complete.tmp').exists()
    target = args.out.resolve()
    assert target.parent == OUT and not target.exists(), 'Fresh audit output in owned directory only'
    target.mkdir()
    module_spec = importlib.util.spec_from_file_location('sealed_remaining9_checker', R/'checker.py')
    checker = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(checker)
    results = []
    try:
        for case in plan['cases']:
            shape, spec = case['shape'], plan['specs'][case['shape']]
            root = P/'replay/tests'/case['id']
            assert sha(root/'input.elf') == case['sha256'] == sha(case['elf'])
            inputs = read(root/'inputs.json')
            assert inputs['binary'] == dict(source=case['elf'], path=str(root/'input.elf'), sha256=case['sha256'])
            assert inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files'])
            assert read(root/'command.json') == dict(command=[ledger['simv'], '-l', 'run.vcs.log', '+ntb_random_seed=1',
                '+PRELOAD='+str(root/'input.elf'), '+TESTCASE='+case['id'], '+NO_FSDB', '+COMMIT_TRACE='+str(root/'commit_trace.csv')], cwd=str(root/'work'))
            for log in (root/'console.log', root/'work/run.vcs.log'):
                text = log.read_text(); checker.console_gate(text, spec)
                assert not re.search(r'first[ _-]?(?:error|failure)|\b(?:TIMEOUT|CANCELLED|FATAL)\b', text, re.I)
            observer = Observer(spec)
            with (root/'commit_trace.csv').open(newline='') as stream:
                strict = checker.retirement(observer.rows(csv.DictReader(stream)), spec)
            generic = observer.finish()
            generated = dict(generic=generic, strict=strict, csv_sha256=pins[str(root/'commit_trace.csv')])
            assert json.loads(json.dumps(generated)) == read(root/'strict_original.json')
            assert dict(generic, status='VALID') == read(root/'trace_summary.json')
            result = dict(shape=shape, status='INDEPENDENT_SINGLE_ACCEPTED_PENDING_BATCH_PIN_RECHECK',
                generated=generated, observer=observer.evidence(), csv_parses=1,
                source_scope='one canonical reduced single; all3360 fixture rows read, not3360 targets',
                limitation=LIMITATION, elf_sha256=case['sha256'])
            save(target/(shape+'.json'), result)
            results.append(result)
            print('RECONSTRUCTED', shape, strict['retired_rows'], flush=True)
        verify(pins)
        assert sha(P/'complete.json') == args.complete_sha256
        assert [r['shape'] for r in results] == SHAPES and len(results) == 9
        save(target/'verified_pins.json', pins)
        save(target/'result.json', dict(status='INDEPENDENT_M6_REMAINING9_SINGLES1296_ACCEPTED_NOT_FULL_PARENTS',
            accepted=True, plan_sha256=PLAN_SHA, image_sha256=IMAGE_SHA, complete_sha256=args.complete_sha256,
            prepared_sha256=args.prepared_sha256, shapes=SHAPES, geometry=geometry,
            results={r['shape']: dict(path=str(target/(r['shape']+'.json')), sha256=sha(target/(r['shape']+'.json'))) for r in results},
            pins_pre_post_unchanged=True, pins_verified=len(pins), full_plan_pins=1352, evidence_pins=75,
            total_csv_parses=9, total_oracle_bytes=1296, total_fixture_field_reads=60480, target_calls=9,
            post_restore_csr_state_directly_measured=False, limitation=LIMITATION,
            outer_service_terminal_observed=False, outer_service_returncode=None, outer_service_result=None,
            full_parents_accepted=False, all11_accepted=False, no_guest_execution=True,
            audit_seconds=time.monotonic()-started))
    except BaseException as error:
        save(target/'not_accepted.json', dict(status='NOT_ACCEPTED', accepted=False,
            error=repr(error), reconstructed_shapes=[r['shape'] for r in results],
            plan_sha256=PLAN_SHA, complete_sha256=args.complete_sha256))
        raise


def main():
    assert __debug__, 'Do not use python -O: assertion gates are required'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'terminal'])
    parser.add_argument('--authorize-terminal-audit', action='store_true')
    parser.add_argument('--complete-sha256')
    parser.add_argument('--prepared-sha256')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.mode == 'prepare':
        assert not any((args.authorize_terminal_audit, args.complete_sha256, args.prepared_sha256, args.out))
        prepare()
    else:
        assert args.out is not None
        terminal_audit(args)


if __name__ == '__main__': main()
