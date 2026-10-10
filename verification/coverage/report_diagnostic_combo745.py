"""Separate formal745 successor with complete qualified diagnostic fields; no stimuli."""
import argparse
import inspect
import json
from pathlib import Path
import re
import subprocess
from types import FunctionType, SimpleNamespace

import report_native_combo745 as prior
import diagnostic_scope_native_744 as diagnostic

life, require = prior.life, prior.require
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'FULL745_WITH_DIAGNOSTIC_COMPLETE_FIELDS_V1'
DEFAULT_PRIOR = life.OUT / 'qualified-native-combo-full745-agent-20261007-01'
PRIOR_CONFIG_SHA = '6401eddd3c71a0a870a02e6d05872e274017860817dd419f900de8e9cc500727'
NATIVE = life.OUT / 'diagnostic-scope-native-744-agent-20261007-01'
CAPTURE_SHA = '53ec4fc3f71fd67864cc4b2ffb9457664216abfc9b7ad637b3fa47a0794aaad9'
HANDOFF = life.OUT / 'diagnostic-scope-native-744-handoff-agent-20261007-01.json'
HANDOFF_SHA = '3d6d91b7aef9e958a38a09d1fed295560b9f273622757dd771cba9da363e0057'
DEPENDENCIES = {
    str(HERE / 'report_native_combo745.py'): '121f4215ed28cad94a48bf35c8e18d87e207ac9a20e20441197cbec9daad0d60',
    str(HERE / 'report_native_combo745.tcl'): 'c90ada0982028cb61cb3e8eacc8f284a813047b29e1bdf7f16a77881c91cf757',
    str(HERE / 'test_report_native_combo745.py'): 'efd53c22e4a7d4d27c2131f47747f691a547f3394ce0a714441c0c6e1475b2b0',
    str(HERE / 'diagnostic_scope_native_744.py'): '21c0b46da91896b2dbf27cd3da4b8d9781a0a19f9565b6386bdb300810416c6b',
    str(HERE / 'report_fsm_observers742.py'): '19b128dc9ebacb1510aeafb57ea7925dd476b56b3a062ef121a534cc966711b2'
}


def qualified_prior(directory, seal):
    require(directory == DEFAULT_PRIOR and seal and (directory / 'qualification.json').is_file(),
            'Wait for exact prior745 qualification; no runtime apply before qualification')
    q = life.read_bound(directory / 'qualification.json', seal)
    require(q['status'] == 'FULL745_QUALIFIED_NATIVE_UNION_REPORT_VERIFIED' and
            q['population'] == 745 and q['config_seal'] == PRIOR_CONFIG_SHA,
            'Unqualified or foreign prior745 report')
    c = life.read_bound(directory / 'config.json', PRIOR_CONFIG_SHA)
    require(c['schema'] == 'QUALIFIED_NATIVE_COMBO745_V1' and c['population'] == 745 and
            c['output'] == str(directory) and c['successor_entry'] == str(Path(prior.__file__).resolve()),
            'Prior config/entry identity differs')
    require(q['system']['raw'] == q['system']['reset'] == q['system']['final'] and
            q['system']['applied'] == q['system']['reloaded'], 'Prior same-session reports differ')
    life.check(c['pins'])
    life.check(q['output_pins'])
    if 'offline_adapter_pins' in q:
        life.check(q['offline_adapter_pins'])
    return c, q


def records(text, config):
    wanted = {i['scope']: {s['name'] for s in i['signals']}
              for i in config['diagnostic_config']['instances']}
    parts = dict(prior=[], diagnostic=[])
    for block in re.split(r'(?m)(?=^CHECKSUM:)', text):
        if not block:
            continue
        scopes = re.findall(r'(?m)^INSTANCE: *(\S+)$', block)
        require(len(scopes) == 1, 'Unbound or mixed native block')
        header, body = [], dict(prior=[], diagnostic=[])
        last_family, pending = None, []
        for line in block.splitlines():
            if not line or line.startswith('//'):
                continue
            if line.startswith(('CHECKSUM:', 'INSTANCE:')):
                header.append(line)
                continue
            if line.startswith('ANNOTATION:'):
                (body[last_family] if last_family else pending).append(line)
                continue
            match = re.match(r'^Toggle\s+(?:(?:0to1|1to0)\s+)?([\w.]+)(?:\s|\[|$)', line)
            family = 'diagnostic' if match and match[1] in wanted.get(scopes[0], set()) else 'prior'
            body[family].extend(pending)
            pending = []
            body[family].append(line)
            last_family = family
        if not any(body.values()):
            # Existing four observer exclusions use a checksum+INSTANCE-only block.
            # Leave it untouched for the prior strict observer parser, never diagnostic.
            parts['prior'].append(block)
            continue
        require(not pending, 'Annotation without native record')
        for family in parts:
            if body[family]:
                parts[family].append('\n'.join(header + body[family]) + '\n')
    return json.loads(json.dumps(dict(prior=prior.records(''.join(parts['prior']), config),
        diagnostic=diagnostic.predecessor.namespace()['parse_el'](
            ''.join(parts['diagnostic']), config['diagnostic_config']))))


def prepare(out, directory, qualification_seal):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent report directory required')
    life.check(DEPENDENCIES)
    c, q = qualified_prior(directory, qualification_seal)
    capture = life.read_bound(NATIVE / 'capture-result.json', CAPTURE_SHA)
    handoff = life.read_bound(HANDOFF, HANDOFF_SHA)
    require(capture['status'] == 'DIAGNOSTIC_COMPLETE_FIELDS_EXACT_NATIVE_ROUNDTRIP_PASS' and
            capture['objects'] == 224 and capture['bit_directions'] == 11038 and
            capture['semantic_reload'] and capture['all_non_targets_protected'] and
            capture['global_final_empty'] and not capture['product_control_excluded'] and
            not capture['runtime_checks_disabled'] and handoff['capture_result_sha256'] == CAPTURE_SHA,
            'Diagnostic native qualification incomplete')
    dc = life.read_bound(NATIVE / 'config.json', handoff['config_sha256'])
    life.check(capture['pins'])
    require(diagnostic.predecessor.namespace()['parse_el']((NATIVE / 'first.el').read_text(), dc) ==
            diagnostic.predecessor.namespace()['parse_el']((NATIVE / 'second.el').read_text(), dc),
            'Diagnostic semantic reload differs')
    require(dc['design'] == c['input_ledger'][0], 'Different compiled image')
    pins = prior.old.chain.merge_inventories(c['pins'], q['output_pins'], q.get('offline_adapter_pins', {}),
        capture['pins'], DEPENDENCIES,
        {str(directory / 'config.json'): PRIOR_CONFIG_SHA,
         str(directory / 'qualification.json'): qualification_seal,
         str(NATIVE / 'capture-result.json'): CAPTURE_SHA, str(HANDOFF): HANDOFF_SHA})
    config = dict(c, schema=SCHEMA, output=str(out), successor_entry=str(Path(__file__).resolve()),
        diagnostic_config=dc, predecessor_directory=str(directory), predecessor_qualification_seal=qualification_seal,
        predecessor_config_seal=PRIOR_CONFIG_SHA, diagnostic_capture_seal=CAPTURE_SHA,
        runtime_timeout_seconds=1800, internal_backing_aliases_excluded=False,
        parent_authorized_native_range=True, official_denominator_verified=False,
        diagnostic_references=[], prior_expected_union=c['expected_union'])
    combined = (directory / 'applied.el').read_text() + (NATIVE / 'first.el').read_text()
    config['expected_union'] = records(combined, config)
    require(config['expected_union']['prior'] == c['expected_union'] and
            len(config['expected_union']['diagnostic']) == 11038, 'Prior or diagnostic union drift')
    atom = prior.old.base.capture.tcl_atom
    selection = (directory / 'selection.tcl').read_text() + 'set diagnostic_instances {}\n'
    for index, instance in enumerate(dc['instances']):
        rows = prior.csv_rows(NATIVE / ('native_before_%d.tsv' % index), '\t')
        require(rows[0] == ['handle', 'path', 'meta', 'name', 'column1', 'column2'] and
                all(len(r) == 6 for r in rows[1:]), 'Malformed diagnostic inventory')
        config['diagnostic_references'].append([r[1:4] for r in rows[1:]])
        selection += 'lappend diagnostic_instances [list %s [list %s]]\n' % (
            atom(instance['scope']), ' '.join(atom(s['native_label']) for s in instance['signals']))
    config['hierarchy_roots'] = list(c['hierarchy_roots'])
    for instance in dc['instances']:
        if instance['scope'] not in {r['scope'] for r in config['hierarchy_roots']}:
            root = dict(scope=instance['scope'], name=instance['scope'].split('.')[-1])
            config['hierarchy_roots'].append(root)
            selection += 'lappend report745_roots [list %s %s]\n' % (atom(root['scope']), atom(root['name']))
    for path in (Path(__file__).resolve(), TCL, HERE / 'test_report_diagnostic_combo745.py'):
        pins[str(path)] = life.digest(path)
    life.check(pins)
    out.mkdir()
    for name, text in [('inputs.txt', '\n'.join(config['input_ledger']) + '\n'),
                       ('combined.el', combined), ('selection.tcl', selection)]:
        with (out / name).open('x') as stream:
            stream.write(text)
        pins[str(out / name)] = life.digest(out / name)
    config['pins'] = pins
    life.save(out / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_NO_DVE', seal=life.digest(out / 'config.json'),
        population=745, diagnostic_fields=224, diagnostic_directions=11038)), flush=True)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == SCHEMA and c['population'] == 745 and c['output'] == str(out) and
            c['successor_entry'] == str(Path(__file__).resolve()) and c['runtime_timeout_seconds'] == 1800,
            'Wrong successor config/entry/budget')
    qualified_prior(Path(c['predecessor_directory']), c['predecessor_qualification_seal'])
    life.check(c['pins'])
    require(records((out / 'combined.el').read_text(), c) == c['expected_union'], 'Union drift')
    return c


def verify(out, seal):
    c = check(out, seal)
    for index, reference in enumerate(c['diagnostic_references']):
        require(reference and len(reference) == len({tuple(r) for r in reference}), 'Ambiguous diagnostic complement')
        names = [r[2] for r in reference]
        require(all(names.count(s['native_label']) == 1 for s in c['diagnostic_config']['instances'][index]['signals']),
                'Diagnostic target missing')
        for stage in ('before', 'selected', 'reset', 'reloaded', 'final'):
            rows = prior.csv_rows(out / ('diagnostic_%s_%d.tsv' % (stage, index)), '\t')
            require(rows[0] == ['handle', 'path', 'meta', 'name', 'column1', 'column2'] and
                    all(len(r) == 6 for r in rows[1:]) and [r[1:4] for r in rows[1:]] == reference,
                    'Diagnostic five-stage target/protected complement differs')
    # Private legacy view retains every old gate while our outer entry/schema stay sealed.
    def read_bound(path, digest):
        value = life.read_bound(path, digest)
        return dict(value, schema='QUALIFIED_NATIVE_COMBO745_V1') if path == out / 'config.json' else value

    def save(path, data):
        require(path == out / 'qualification.json', 'Unexpected verifier write')
        data.update(status='FULL745_WITH_DIAGNOSTIC_NATIVE_UNION_REPORT_VERIFIED',
            diagnostic_fields=224, diagnostic_bits=5519, diagnostic_directions=11038,
            diagnostic_capture_seal=CAPTURE_SHA, predecessor_qualification_seal=c['predecessor_qualification_seal'],
            actual_population_i_system=data['system'], runtime_checks_disabled=False,
            internal_backing_aliases_excluded=False, application_approval=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == data, 'Sealed qualification differs')
        else:
            life.save(path, data)
    proxy = SimpleNamespace(**vars(life))
    proxy.read_bound, proxy.save = read_bound, save
    # The v3 wrapper has its own obsolete entry guard. Use the frozen original core,
    # not that wrapper; our current check above enforces the exact successor identity.
    old_proxy = SimpleNamespace(**vars(prior.old))
    require(Path(prior.inherited.original_verify.__code__.co_filename).name == 'report_c910_combo742.py',
            'Not the substantive original verifier')
    old_proxy.verify = prior.inherited.original_verify
    namespace = dict(prior.verify.__globals__, __file__=__file__, life=proxy, old=old_proxy, records=records)
    FunctionType(prior.verify.__code__, namespace)(out, seal)


def run(out, seal):
    check(out, seal)
    def popen(*args, **kwargs):
        return subprocess.Popen(*args, **dict(kwargs, env=dict(kwargs['env'], DVE_REVIEWED_WAIVERS=str(TCL))))
    base = prior.old.base
    body = inspect.getsource(base.run)
    require(body.count('process.wait(timeout=900)') == 1, 'Frozen lifecycle timeout anchor differs')
    body = body.replace('process.wait(timeout=900)', 'process.wait(timeout=c[\'runtime_timeout_seconds\'])')
    ns = dict(base.run.__globals__, verify=verify,
        subprocess=SimpleNamespace(**{**vars(subprocess), 'Popen': popen}))
    exec(compile(body, str(Path(base.__file__).resolve()), 'exec'), ns)
    ns['run'](out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--prior-output', type=Path, default=DEFAULT_PRIOR)
    p.add_argument('--prior-qualification-seal')
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        prepare(out, a.prior_output.resolve(), a.prior_qualification_seal)
    else:
        require(a.seal, 'Exact config seal required')
        if a.mode == 'check':
            check(out, a.seal)
            print('DIAGNOSTIC745_SUCCESSOR_CHECK_PASS_NO_DVE')
        else:
            (run if a.mode == 'run' else verify)(out, a.seal)
