"""Single v7-reader combined735 entry; prepare/verify/inspect never launch EDA."""
import argparse
from collections import Counter
import copy
import csv
import json
from pathlib import Path
import re
import sys
import tkinter

import qbs_eight735_runtime as frozen
import eight_policy_epoch_735_report_v7 as reader

f, design, merge = frozen.f, frozen.design, frozen.merge
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_qbs_eight735_runtime_v7.py')
TCL = frozen.TCL
NAME = 'combined-runtime.json'
SCHEMA = 'QBS_EIGHT735_SINGLE_RUNTIME_V7'
BUDGET = frozen.BUDGET
ADMISSION_SHA = '4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397'
FULL = merge.qualified.native.old.full
NATIVE = merge.qualified.native.MULTISET


def merge_pins(*ledgers):
    result = {}
    for ledger in ledgers:
        for path, sha in ledger.items():
            f.require(isinstance(path, str) and isinstance(sha, str) and
                      re.fullmatch('[0-9a-f]{64}', sha) is not None, 'Malformed pin ledger')
            f.require(path not in result or result[path] == sha, 'Pin conflict: ' + path)
            result[path] = sha
    return result


def dependencies():
    return tuple(dict.fromkeys((SCRIPT, TEST, TCL, frozen.SCRIPT, frozen.TEST,
        reader.SCRIPT, reader.TEST, *reader.dependencies(), frozen.eight.SCRIPT,
        frozen.eight.TCL, design.SCRIPT, design.TEST, frozen.PROOF, NATIVE, FULL.BODY,
        Path('/usr/bin/timeout').resolve(), Path(sys.executable).resolve())))


def validate_reader(path, seal, plan):
    f.require(re.fullmatch('[0-9a-f]{64}', seal or '') is not None, 'Explicit real v7 reader seal required')
    f.require(path == reader.ROOT / reader.PLAN and path.resolve() == path,
              'Only the actual735 v7 reader plan location is accepted')
    f.require(plan['output'] == str(reader.ROOT) == str(design.REPORT) and
              plan['population'] == 735 and plan['admission_seal'] == ADMISSION_SHA and
              (plan['targets'], plan['protected'], plan['audited']) == (5892, 17774, 23666),
              'Exact735 v7 authority/counts required; no population following')
    for dep in (reader.SCRIPT, reader.TEST, reader.AUDIT, *reader.COMPILED_READS):
        f.require(str(dep) in plan['pins'], 'Missing v7 closure authority: ' + str(dep))
    f.require(set(plan['json_paths']) <= set(plan['byte_paths']) <= set(plan['pins']),
              'Unsealed reader read role')


def side_roles():
    jsons = (design.QUALIFIED, frozen.PROOF)
    byte_paths = (*jsons, NATIVE, FULL.BODY, merge.EIGHT / 'applied.el',
                  merge.qualified.RUN / 'first.el')
    return [str(p) for p in byte_paths], [str(p) for p in jsons]


def reader_context(path, seal, runtime_pins=None, generated=None):
    f.require(f.sha(path) == seal, 'Real v7 reader seal drift')
    source = json.loads(path.read_bytes())
    validate_reader(path, seal, source)
    pins = merge_pins(source['pins'], {str(path): seal}, runtime_pins or {})
    generated = generated or {}
    f.require(not set(generated) & set(pins), 'Generated evidence cannot replace source authority')
    pins = merge_pins(pins, generated)
    byte_paths = set(source['byte_paths']) | {str(path)} | set(generated)
    json_paths = set(source['json_paths']) | {str(path)} | {p for p in generated if p.endswith('.json')}
    if runtime_pins is not None:
        byte_side, json_side = side_roles()
        f.require(set(byte_side) <= set(pins), 'Missing QBS native/source roles')
        byte_paths.update(byte_side); json_paths.update(json_side)
    owner = reader.Wiring(pins, sorted(byte_paths), sorted(json_paths))
    context, config = owner.fixed.read_config(owner.Path(design.REPORT), source['fixed_seal'])
    owner.check_inputs(config)
    if runtime_pins is not None:
        # Extend the same v7 private namespace closure to the existing QBS inspector.
        owner.qbs_full = reader.PathClosure(owner).module(FULL, 'qbs_full')
    return source, owner, context, config


def prepare(output, reader_plan, reader_seal):
    f.require(output.parent == f.proof.OUT and output.resolve() == output and not output.exists(),
              'Fresh direct output required')
    baseline = design.evidence()
    source, _, _, config = reader_context(reader_plan, reader_seal)
    pins = merge_pins(source['pins'], baseline['pins'], {str(reader_plan): reader_seal},
                      {str(p): f.sha(p) for p in dependencies()})
    f.check_pins(pins)
    # Check the augmented closure before creating any outputs.
    reader_context(reader_plan, reader_seal, pins)
    identity = config['plan']['tool_identity']; f.tool.revalidate(identity)
    command = ['/usr/bin/timeout', '--kill-after=10s', str(BUDGET)+'s'] + f.tool.launch_command(identity, TCL)
    data = frozen.payloads(output)
    f.require(not {str(output/n) for n in data} & set(pins), 'Generated/source payload overlap')
    output.mkdir()
    for group in (*frozen.eight.frozen.GROUPS, 'lzc', 'snapshot'):
        (output / group).mkdir()
    for name, raw in data.items():
        with (output/name).open('xb') as stream: stream.write(raw)
    pins = merge_pins(pins, {str(output/n): f.sha(output/n) for n in data})
    plan = dict(schema=SCHEMA, output=str(output), population=735, reader_plan=str(reader_plan),
        reader_seal=reader_seal, pins=pins, command=command, tool_identity=identity,
        budget_seconds=BUDGET, kill_after_seconds=10, stages=list(design.STAGES), targets=7684,
        protected_audited=19566, audited=27250, payload_condition_protected=41214,
        source_control_boundary=f.SCOPE_BOUNDARY, call_budget=baseline['call_budget'],
        application_approval=False, launch_approved=False, automatic_retry=False,
        terminal_backend='V7_OWNER_BOUND_EIGHT_AND_QBS',
        parent_launch_metadata='Preserve live-identity, execution, launcher, integrity-before/after; exit0 is not qualification.')
    f.write(output/NAME, plan)
    f.write(output/'status.json', dict(status='PREPARED_NO_DVE', application_approval=False))
    return f.sha(output/NAME)


def validate_runtime(output, plan):
    f.require(plan['schema'] == SCHEMA and plan['output'] == str(output) and plan['population'] == 735 and
        plan['stages'] == list(design.STAGES) and plan['source_control_boundary'] == f.SCOPE_BOUNDARY and
        (plan['targets'], plan['protected_audited'], plan['audited'], plan['payload_condition_protected']) ==
        (7684, 19566, 27250, 41214) and plan['budget_seconds'] == BUDGET and plan['kill_after_seconds'] == 10 and
        plan['terminal_backend'] == 'V7_OWNER_BOUND_EIGHT_AND_QBS' and
        not any(plan[k] for k in ('application_approval', 'launch_approved', 'automatic_retry')),
        'Combined v7 contract drift')


def verify(output, seal):
    f.require(output.parent == f.proof.OUT and output.resolve() == output, 'Unsafe output')
    f.require(f.sha(output/NAME) == seal, 'Runtime seal drift')
    plan = json.loads((output/NAME).read_bytes()); validate_runtime(output, plan)
    f.check_pins(plan['pins'])
    source, owner, context, config = reader_context(Path(plan['reader_plan']), plan['reader_seal'], plan['pins'])
    merge_pins(plan['pins'], source['pins'])
    for path, sha in source['pins'].items():
        f.require(plan['pins'].get(path) == sha, 'Inherited source ledger omitted')
    for path in dependencies():
        f.require(plan['pins'].get(str(path)) == f.sha(path), 'Mandatory runtime dependency omitted/drifted')
    for name, raw in frozen.payloads(output).items():
        f.require(plan['pins'].get(str(output/name)) == f.sha(output/name) and
                  (output/name).read_bytes() == raw, 'Generated helper differs: '+name)
    expected = ['/usr/bin/timeout', '--kill-after=10s', str(BUDGET)+'s'] + f.tool.launch_command(config['plan']['tool_identity'], TCL)
    f.require(plan['command'] == expected and plan['tool_identity'] == config['plan']['tool_identity'],
              'Tool binding differs')
    f.tool.revalidate(plan['tool_identity'])
    derived = copy.deepcopy(config); derived.update(output=str(output), command=plan['command'], pins=plan['pins'])
    return plan, owner, context, derived


def load(owner, path):
    return owner.json.loads(owner.Path(path).read_bytes())


def records(owner, raw):
    f.require(0 < len(raw) < 8*1024*1024, 'Bounded native EL required')
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    t.eval(owner.Path(NATIVE).read_text())
    try: result = [t.splitlist(row) for row in t.splitlist(t.call('nem_records', raw.decode('ascii')))]
    except (UnicodeError, tkinter.TclError) as exc: raise ValueError('Invalid native multiset') from exc
    f.require(all(len(r) == 10 for r in result), 'Complete native attributes required')
    return result


def union_checker(owner):
    expected = records(owner, owner.Path(merge.EIGHT/'applied.el').read_bytes()) + \
               records(owner, owner.Path(merge.qualified.RUN/'first.el').read_bytes())
    f.require(len(expected) == 7684 and len({(r[0], r[3], r[4], r[7]) for r in expected}) == 7684,
              'Exact disjoint7684 native identities required')
    def check(raw):
        actual = records(owner, raw)
        f.require(Counter(actual) == Counter(expected), 'Exact7684 identity/attribute/annotation union differs')
        return 7684
    return check


def old_eight_verifier(owner, context, runtime, plan, union):
    backend = owner.fixed.eight
    sources = dict(six=owner.Path(Path(runtime['six_output'])/'combined.el').read_bytes(),
        lzc=(backend.SOURCE_PROOF/'candidate60.el').read_bytes(), snapshot=backend.MASK_EL.read_bytes())
    oldkeys = {key for data in sources.values() for key, _ in backend.metric.blocks(data)}
    def bind(raw, cfg, states=None):
        union(raw)
        fragment = b''.join(chunk for key, chunk in backend.metric.blocks(raw) if key in oldkeys)
        return backend.split_bind(fragment, cfg, sources, runtime['snapshot_candidates'], states)
    scopes = {r['scope'] for r in plan['condition_native_records']} | \
             {r['scope'] for r in runtime['snapshot_candidates']} | set(load(owner, design.QUALIFIED)['scope_protection'])
    namespace = dict(context.namespace(), bindings=bind, TIMEOUT=BUDGET,
        log_adapter=lambda path: owner.Path(path/'DVEfiles/dve_gui.log').read_text().splitlines().count(
            'SIX_POPULATION_SELECTION_ADAPTER_INSTALLED') == 1)
    return backend.prior.seven_verifier(namespace,
        lambda s, m, a: backend.prior.change_allowed(s, m, a, scopes))


def qbs_rows(owner, raw):
    t = tkinter.Tcl(); t.tk.wantobjects(False)
    f.require(0 < len(raw) < 32*1024*1024 and raw.endswith(b'\n'), 'Invalid QBS evidence size/termination')
    rows = [t.splitlist(line) for line in raw.decode('ascii').splitlines()]
    end = next((i for i, r in enumerate(rows) if r and r[0] == 'audit'), None)
    f.require(end is not None, 'Missing QBS stages')
    artifact = load(owner, frozen.PROOF)
    owner.qbs_full.inspect_rows(b'\n'.join(raw.splitlines()[:end]) +
        b'\ncomplete 1344 448 FULL1792_NATIVE_HOLD\n', artifact)
    metas = {(r[1], r[2]): r[6] for r in rows[:end] if r[0] == 'object'}
    wanted = []
    for stage in design.STAGES:
        active = stage in ('selected', 'reloaded', 'after-root')
        for g in owner.qbs_full.groups(artifact):
            for vector in g['names']:
                wanted.append(('audit', stage, g['scope'], g['expression'], metas[g['scope'], g['expression']],
                               vector, str(int(active and vector in g['targets']))))
        wanted.append(('stage', stage, '3584', str(1792*int(active))))
    f.require(rows[end:] == wanted + [('terminal', '0', '', '')], 'QBS six-stage target/protection/terminal differs')
    f.require(load(owner, design.QUALIFIED)['qualification']['protected_count'] == 41214, 'QBS complement differs')
    return 21504


def inspect(output, seal):
    p, _, _, config = verify(output, seal)
    produced = {}
    for path in output.rglob('*'):
        if path.is_file() and str(path) not in p['pins']:
            f.require(not path.is_symlink() and path.resolve() == path, 'Aliased generated evidence')
            produced[str(path)] = f.sha(path)
    _, owner, context, _ = reader_context(Path(p['reader_plan']), p['reader_seal'], p['pins'], produced)
    backend = owner.fixed.eight
    runtime = load(owner, design.REPORT/'runtime-plan.json')
    plan = load(owner, Path(runtime['seven_output'])/'application-plan.json')
    union = union_checker(owner)
    result = old_eight_verifier(owner, context, runtime, plan, union)(owner.Path(output), config)
    log = owner.Path(output/'DVEfiles/dve_gui.log').read_text()
    f.require(not re.search(r'(?:QBS_EIGHT|EIGHT|SEVEN)_(?:HOLD|FAILED|ERROR)', log), 'Combined GUI failed')
    for marker in ('QBS_EIGHT_RUNTIME_INSTALLED', 'QBS_EIGHT_RELOAD_MULTISET_EXACT7684',
                   'QBS_EIGHT_COMPLETE7684_NOT_APPLICATION', 'EIGHT_CSV_WRITER_INSTALLED'):
        f.require(log.splitlines().count(marker) == 1, 'Missing exact completion: '+marker)
    files = {}
    for stage in design.STAGES:
        active = stage in ('selected', 'reloaded', 'after-root')
        path = owner.Path(output/'lzc'/('states_'+stage+'.tsv'))
        backend.prior.read_lzc_states(path, plan, active); files[str(path)] = owner.phase.sha(path)
        path = owner.Path(output/'snapshot'/('states_'+stage+'.csv'))
        with path.open(newline='') as stream:
            r = csv.DictReader(stream); rows = list(r)
            f.require(r.fieldnames == backend.mask.native.AUDIT_COLUMNS, 'Snapshot schema differs')
        wanted = [dict(zip(backend.mask.native.AUDIT_COLUMNS, [stage, g['scope'], g['expression'], ' '.join(g['names']),
            ' '.join(g['targets']), ' '.join(g['retained']), str(len(g['targets']) if active else 0), '0']))
            for g in runtime['snapshot_groups']]
        f.require(rows == wanted, 'Snapshot protection differs'); files[str(path)] = owner.phase.sha(path)
        for marker in ('SEVEN_LZC_AUDIT %s 4200'%stage, 'EIGHT_FULL_AUDIT %s 23666'%stage,
                       'QBS_EIGHT_FULL_AUDIT %s 27250'%stage):
            f.require(log.splitlines().count(marker) == 1, 'Missing complete stage: '+marker)
    for name in ('applied.el', 'reloaded.el', 'after-root.el'):
        path = owner.Path(output/name); union(path.read_bytes()); files[str(path)] = owner.phase.sha(path)
    for name in ('initial-empty.el', 'reset-empty.el', 'session-final-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        path = owner.Path(output/name); f.require(path.read_bytes() == b'', 'Global empty/reset differs')
        files[str(path)] = owner.phase.sha(path)
    path = owner.Path(output/'native-qualification.tcllist'); qbs_rows(owner, path.read_bytes())
    files[str(path)] = owner.phase.sha(path)
    result.update(status='FRESH735_EIGHT_PLUS_QBS1792_V7_QUALIFIED_NOT_APPLICATION', records=7684,
        audited=27250, state_checks=163500, payload_condition_protected=41214, application_approval=False,
        source_control_boundary=f.SCOPE_BOUNDARY, not_arbitrary_X_or_delta_proof=True,
        terminal_backend='V7_OWNER_BOUND_EIGHT_AND_QBS')
    result['files'].update(files)
    owner.phase.check_pins(merge_pins(p['pins'], produced))
    result['generated_evidence_pins'] = produced
    result['epoch'] = owner.phase.finish()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify', 'inspect'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    parser.add_argument('--reader-plan', type=Path); parser.add_argument('--reader-seal')
    args = parser.parse_args(); output = args.output.absolute()
    if args.mode == 'prepare':
        f.require(args.reader_plan and args.reader_seal and not args.seal, 'Actual sealed v7 reader required')
        print(json.dumps(dict(seal=prepare(output, args.reader_plan.absolute(), args.reader_seal),
                              output=str(output), DVE_started=False)))
    else:
        f.require(args.seal and not args.reader_plan and not args.reader_seal, 'Sealed runtime only')
        if args.mode == 'verify':
            p, _, _, _ = verify(output, args.seal)
            print(json.dumps(dict(status='VERIFY_PASS_NOT_LAUNCHED', command=p['command'], budget_seconds=BUDGET)))
        else: print(json.dumps(inspect(output, args.seal)))


if __name__ == '__main__': main()
