"""Identity-only full inventory plus authoritative global partial-bit EL."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys
from types import FunctionType

import qbs_bank1_group_hit_native791 as frozen

life, tools, need = frozen.life, frozen.tools, frozen.need
HERE = Path(__file__).resolve().parent
ENTRY = HERE / 'qbs_bank1_group_hit_native791_v2.tcl'
FAILED = life.OUT / 'qbs-bank1-group-hit-native791-agent-prepared-20261008-01'
FAILED_SEAL = '3d27f35f3f03fac4eef79580941e2df3ad245fba3face4c8a9d7e1e239acac0b'
V1_SHA = 'ae5f604c775527a6eec1582a48e547e02e193227247bb4b5c7c49a6d45e78279'
STAGES, FILES = frozen.STAGES, frozen.FILES


def bound_rows(text, instance, stage):
    need(stage in STAGES, 'Exact native stage')
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    need(reader.fieldnames == ['handle', 'path', 'meta', 'name'], 'Identity-only native schema; no fabricated flags')
    rows = list(reader)
    need(len(rows) == len(instance['bindings']), 'Complete native object/array inventory')
    for key in ('handle', 'path', 'name'):
        need(all(row.get(key) for row in rows) and len({row[key] for row in rows}) == len(rows), 'Unique native '+key)
    bylabel = {label: b for b in instance['bindings'] for label in b['allowed_labels']}
    found = {}
    for row in rows:
        need(set(row) == set(reader.fieldnames) and row['handle'].isdigit() and
             row['path'] == row['meta'] == row['name'], 'Exact native identity')
        b = bylabel.get(row['name'])
        need(b is not None and b['attributes']['name'] not in found, 'Foreign/duplicate typed object')
        found[b['attributes']['name']] = dict(label=row['name'], path=row['path'], meta=row['meta'])
    need(len(found) == len(instance['bindings']), 'Complete typed bijection')
    return found


def check(out, seal):
    c = life.read_bound(out/'config.json', seal)
    life.check(c['pins'])
    need(c['schema'] == 'QBS_BANK1_NATIVE_V2_IDENTITY_EL' and c['output'] == str(out) and
         c['timeout_seconds'] == 900 and c['automatic_retry'] is False and
         c['population_application'] is False and c['inventory_excluded_flags_captured'] is False,
         'Fresh v2 exact contract')
    need(life.digest(Path(frozen.__file__)) == V1_SHA, 'Frozen v1 helper identity')
    previous = life.read_bound(FAILED/'config.json', FAILED_SEAL)
    need(c['plan'] == previous['plan'] and c['instances'] == previous['instances'] == frozen.instances(c['plan'])
         and len(c['instances']) == 26 and len(frozen.partial.primitive.bitset(frozen.target_config(c))) == 3232,
         'All prior source bits and full complements preserved')
    tools.revalidate(c['identity'])
    return c


def failure_evidence():
    old = life.read_bound(FAILED/'config.json', FAILED_SEAL)
    terminal = json.loads((FAILED/'terminal.json').read_bytes())
    reject = json.loads((FAILED/'qualification-reject.json').read_bytes())
    need(type(terminal['returncode']) is int and terminal['returncode'] == -15 and terminal['timeout'] is True
         and reject == dict(error='Strict actual terminal', native_qualified=False), 'Preserve actual v1 timeout')
    counts = {}
    pins = {str(FAILED/'config.json'): FAILED_SEAL}
    for name in ('terminal.json', 'qualification-reject.json', 'actual-binding.json',
                 'initial-empty.el', 'first.el', 'reset-empty.el', 'second.el', 'final-empty.el',
                 'DVEfiles/dve_gui.log'):
        pins[str(FAILED/name)] = life.digest(FAILED/name)
    for stage in STAGES:
        rows = []
        for index, i in enumerate(old['instances']):
            path = FAILED/('native_%s_%d.tsv' % (stage, index))
            if not path.exists(): continue
            text = path.read_text()
            count = len(text.splitlines())-1
            rows.append(dict(index=index, rows=count, expected=len(i['bindings'])))
            pins[str(path)] = life.digest(path)
            if stage != 'final' or index == 0:
                frozen.bound_rows(text, i, stage)
        counts[stage] = rows
    need(all(len(counts[s]) == 26 for s in STAGES[:4]) and
         counts['final'] == [dict(index=0, rows=3286, expected=3286), dict(index=1, rows=3045, expected=3193)],
         'Actual partial final, never fabricate completion')
    need(frozen.records((FAILED/'first.el').read_text(), old) ==
         frozen.records((FAILED/'second.el').read_text(), old), 'Actual selected/reloaded semantic union')
    return dict(status='FAILED_NOT_APPLIED', terminal_returncode=-15, timeout=True,
        stage_counts=counts, objects_per_complete_phase=6707,
        performance_cause='Each v1 row calls dw_select (clear/readback/select/readback) then gui_exclusion. Timeout occurred within final scope1, before gui_exit. Exact per-call timing was not profiled.',
        optimization='v2 keeps native handle/path/meta/name traversal and complete bijections; no row selection or excluded query. Full global saved EL owns all direction masks and protected complements.',
        native_qualified=False, population_application=False, pins=pins)


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh v2 output only')
    need(life.digest(Path(frozen.__file__)) == V1_SHA, 'Frozen v1 dependency')
    previous = frozen.check(FAILED, FAILED_SEAL)
    evidence = failure_evidence()
    # Reuse the already sealed source/config closure, not another large ranking.
    pins = dict(previous['pins'], **evidence['pins'])
    for path in (Path(__file__).resolve(), ENTRY, HERE/'test_qbs_bank1_group_hit_native791_v2.py'):
        pins[str(path)] = life.digest(path)
    c = dict(previous, schema='QBS_BANK1_NATIVE_V2_IDENTITY_EL', output=str(out), pins=pins,
             helper=str(Path(__file__).resolve()), python=sys.executable,
             inventory_excluded_flags_captured=False, protected_mask_authority='COMPLETE_GLOBAL_SAVED_EL',
             predecessor_failure=evidence)
    life.check(pins); tools.revalidate(c['identity'])
    out.mkdir()
    text = ''.join('set ::bg_'+k+' {'+c[k]+'}\n' for k in ('design', 'sample', 'test', 'python', 'helper'))
    text += 'set ::bg_scopes [list '+' '.join('{'+i['scope']+'}' for i in c['instances'])+']\n'
    for name, data in (('selection.tcl', text), (ENTRY.name, ENTRY.read_text())):
        with (out/name).open('x') as stream: stream.write(data)
        pins[str(out/name)] = life.digest(out/name)
    life.save(out/'config.json', c)
    seal = life.digest(out/'config.json'); check(out, seal)
    print(json.dumps(dict(output=str(out), seal=seal, timeout_seconds=900,
                         native_qualified=False, EDA_launched=False, v1_status='FAILED_NOT_APPLIED')))


# Private rebinding leaves the sealed v1 module untouched. Its EL parser,
# lifecycle and per-stage fresh-before comparison retain their exact gates.
_namespace = dict(vars(frozen), __file__=__file__, ENTRY=ENTRY, bound_rows=bound_rows, check=check)
for _name in ('inventory', 'target_config', 'records', 'bind', 'check_el', 'run'):
    _f = getattr(frozen, _name)
    _namespace[_name] = FunctionType(_f.__code__, _namespace, _name, _f.__defaults__, _f.__closure__)
    globals()[_name] = _namespace[_name]


def inspect(out, seal):
    c = check(out, seal)
    terminal = json.loads((out/'terminal.json').read_bytes())
    need(type(terminal['returncode']) is int and terminal['returncode'] == 0 and
         type(terminal['timeout']) is bool and terminal['timeout'] is False and
         len(terminal['actual_dve']) == 1, 'Strict actual terminal')
    actual = terminal['actual_dve'][0]
    frozen.owning_identity(actual, terminal['worker_identity'], terminal['launcher_pid'])
    need(actual['exe'] == c['identity']['executable'] and actual['cwd'] == str(out) and
         json.loads((out/'live-identity.json').read_bytes()) == terminal['actual_dve'], 'Actual executable/cwd/live proof')
    log = (out/'DVEfiles/dve_gui.log').read_text()
    need(log.splitlines().count('QBS_BANK1_GROUP_HIT_V2_NATIVE_DONE') == 1 and
         'QBS_BANK1_GROUP_HIT_V2_NATIVE_FAILED' not in log and not (out/'error.txt').exists(), 'Full five native stages')
    for name in ('launcher.log', 'DVEfiles/dve_gui.log'):
        need(not frozen.re.search(r'UCAPI-DLMA|DVCDT136|EK-CMD-|Load Failed|Error:|Fatal:', (out/name).read_text()), 'Tool rejection')
    for stage in STAGES:
        check_el(out, c, stage)
        for index in range(26): inventory(out, c, stage, index)
    need((out/'cleanup-empty.el').read_bytes() == b'', 'Cleanup empty')
    names = ['config.json', 'selection.tcl', ENTRY.name, 'actual-binding.json', 'actual-candidate.el',
             'terminal.json', 'live-identity.json', 'live-ready', 'execution.json', 'launcher.log',
             'xvfb.log', 'cleanup-empty.el'] + list(FILES.values())
    names += ['native_%s_%d.tsv' % (s,k) for s in STAGES for k in range(26)]
    paths = [out/n for n in names] + [p for p in (out/'DVEfiles').rglob('*') if p.is_file()]
    need(all(p.is_file() for p in paths), 'Full immutable native output set')
    result = dict(status='QBS_BANK1_GROUP_HIT3232_V2_NATIVE_QUALIFIED_NOT_APPLIED', config_sha256=seal,
        target_bits=1616, target_directions=3232, target_objects=72, protected_parent_objects=3214,
        retained_target_bits=688, mapping_permitted_missing704_protected=True,
        complete_native_objects_per_stage=6707, complete_native_scopes_per_stage=26,
        inventory_excluded_flags_captured=False, protected_mask_authority='COMPLETE_GLOBAL_SAVED_EL',
        source_review_sha256=c['plan']['source_review_sha256'], population_application=False,
        input_pins=c['pins'], pins={str(p):life.digest(p) for p in paths},
        mutable_wrapper_stdout_not_native_evidence=True)
    receipt = out/'qualification.json'
    if receipt.exists(): need(json.loads(receipt.read_bytes()) == result, 'Receipt differs')
    else: life.save(receipt, result)
    print(json.dumps(dict(status=result['status'], sha256=life.digest(receipt))))


_namespace['inspect'] = inspect


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=('prepare','check','bind','inventory','el','inspect','run'))
    cli.add_argument('--output', type=Path, required=True); cli.add_argument('--seal')
    cli.add_argument('--stage', choices=STAGES); cli.add_argument('--index', type=int)
    a = cli.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare': prepare(out)
    elif a.mode == 'run': run(out, a.seal)
    elif a.mode == 'inspect': inspect(out, a.seal)
    else:
        c = check(out, a.seal) if a.mode in ('check','bind') else life.read_bound(out/'config.json', a.seal)
        if a.mode == 'bind': bind(out, c)
        elif a.mode == 'inventory': inventory(out, c, a.stage, a.index)
        elif a.mode == 'el': check_el(out, c, a.stage)
        print('QBS_BANK1_V2_'+a.mode.upper()+'_PASS')
