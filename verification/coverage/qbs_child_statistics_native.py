"""Only15 complete child/compute/engine diagnostic statistics, no population report."""
import argparse
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import audit_qbs_child_statistics as source
import diagnostic_scope_native_744 as prior

q, life, require = prior.q, prior.life, prior.require
HERE = Path(__file__).resolve().parent
SOURCE = life.OUT / 'qbs-child-statistics-source-candidate-parent-20261007-01.json'
SOURCE_SHA = 'd986d108961f0b57e60678f7383c0d74fb7b620ce7704fc181415d56aeecd64a'
NATIVE = life.OUT / 'diagnostic-scope-native-744-agent-20261007-01'
CAPTURE_SHA = '53ec4fc3f71fd67864cc4b2ffb9457664216abfc9b7ad637b3fa47a0794aaad9'
CONFIG_SHA = '2da952d094aab65aecf170307daf09150082d17d1ad3a726196d76902f95d88c'
SCHEMA = 'QBS_CHILD_COMPLETE15_NATIVE_V1'


def reviewed_source():
    candidate = life.read_bound(SOURCE, SOURCE_SHA)
    require(candidate['status'] == 'COMPLETE_CHILD_STATISTICS_SOURCE_COMPILED_REVIEW_NATIVE_HOLD' and
            candidate['selection_independent_of_hits'] and not candidate['application_approved'] and
            (candidate['total_objects'], candidate['total_bits'], candidate['total_directions']) == (15, 399, 798),
            'Wrong whole-field source candidate')
    life.check(candidate['pins'])
    replay = source.collect()
    require(replay == candidate, 'Exact source/shape/reference replay differs')
    return candidate


def instances(candidate, config):
    design = q.Design(Path(config['design']))
    result = []
    old = {(i['scope'], s['name']) for i in config['instances'] for s in i['signals']}
    for group in candidate['groups']:
        scope = group['scope']
        require(scope in design.hierarchy, 'Missing exact compiled child')
        signals = []
        for field in group['fields']:
            node = field['compiled']
            require(node['name'] == field['name'] and (scope, field['name']) not in old and
                    (scope, field['name']) in {(source.BASE + suffix, spec[index])
                      for suffix, index in (('.i_compute_engine.i_fp_accumulator', 0),
                                             ('.i_compute_engine', 1), ('', 2))
                      for spec in source.FIELDS}, 'Foreign/previous target')
            left, right = int(node['left']), int(node['right'])
            bits = list(range(min(left, right), max(left, right) + 1))
            require(right == 0 and len(bits) == field['bits'] and field['directions'] == 2 * len(bits),
                    'Incomplete whole statistics field')
            signals.append(dict(name=field['name'], bits=bits, scalar=False, left=left, right=right,
                native_label=field['name'] + '[' + str(left) + ':' + str(right) + ']', shape=node))
        result.append(dict(scope=scope, design_module_checksum=design.hierarchy[scope].get('chksum'),
            toggle_checksum=group['toggle_checksum'], signals=signals,
            protected=group['all_other_objects_protected'],
            retained_target_signal_bits={s['name']: [] for s in signals}))
    require(len(result) == 3 and sum(len(i['signals']) for i in result) == 15 and
            len(q.bitset(dict(instances=result))) == 798, 'Exact fifteen-field set differs')
    return result


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh standalone native output required')
    candidate = reviewed_source()
    base = life.read_bound(NATIVE / 'config.json', CONFIG_SHA)
    capture = life.read_bound(NATIVE / 'capture-result.json', CAPTURE_SHA)
    require(capture['status'] == 'DIAGNOSTIC_COMPLETE_FIELDS_EXACT_NATIVE_ROUNDTRIP_PASS', 'Predecessor not qualified')
    pins = life.merge_pins(life.merge_pins(capture['pins'], candidate['pins']), {
        str(SOURCE): SOURCE_SHA, str(NATIVE / 'config.json'): CONFIG_SHA,
        str(NATIVE / 'capture-result.json'): CAPTURE_SHA})
    for path in (Path(__file__).resolve(), HERE / 'test_qbs_child_statistics_native.py',
                 Path(prior.__file__).resolve(), HERE / 'queue_constant_native.tcl'):
        pins[str(path)] = life.digest(path)
    config = dict(base, schema=SCHEMA, output=str(out), pins=pins,
        instances=instances(candidate, base), source_candidate=str(SOURCE), source_candidate_seal=SOURCE_SHA,
        source_proof=dict(kind='COMPLETE_STATISTICS_NO_PRODUCT_FEEDBACK', rationale=candidate['rationale'],
            protected=candidate['protected'], parent_range_unchanged=True),
        population_application=False, cast_scope_included=False, automatic_retry=False)
    text = q.candidate(config).replace(
        'Frozen post-reset source invariant; no X, pressure, or module waiver',
        'Complete diagnostic child statistics; actual occupancy/control/data/assertions retained')
    require(len(prior.predecessor.namespace()['parse_el'](text, config)) == 798, 'Candidate union differs')
    life.check(pins)
    out.mkdir()
    q.common.common.save(out / 'candidate.el', text)
    values = dict(qc_design=config['design'], qc_vdb=config['vdb'], qc_test=config['test'],
        qc_python=shutil.which('python3'), qc_helper=str(Path(__file__).resolve()))
    require(all(not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl path')
    selection = ''.join('set ' + k + ' {' + v + '}\n' for k, v in values.items()) + 'set qc_instances {}\n'
    for i in config['instances']:
        selection += 'lappend qc_instances [list {' + i['scope'] + '} [list ' + ' '.join(
            '{' + s['native_label'] + '}' for s in i['signals']) + ']]\n'
    q.common.common.save(out / 'selection.tcl', selection)
    for path in (out / 'candidate.el', out / 'selection.tcl'):
        pins[str(path)] = life.digest(path)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(out), seal=life.digest(out / 'config.json'),
        fields=15, bits=399, directions=798, population_application=False)), flush=True)


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    require(c['schema'] == SCHEMA and c['output'] == str(out) and c['source_candidate_seal'] == SOURCE_SHA and
            not c['population_application'] and not c['cast_scope_included'] and
            len(q.bitset(c)) == 798 and sum(len(i['signals']) for i in c['instances']) == 15,
            'Wrong standalone child statistics contract')
    life.check(c['pins'])
    return c


def verify(out, seal):
    check(out, seal)
    ns = prior.predecessor.namespace()
    proxy = SimpleNamespace(**vars(life))
    def save(path, result):
        require(path == out / 'capture-result.json', 'Unexpected result write')
        result.update(status='QBS_CHILD_COMPLETE15_EXACT_NATIVE_ROUNDTRIP_PASS',
            source_candidate_seal=SOURCE_SHA, diagnostic_statistics_only=True,
            actual_occupancy_control_retained=True, runtime_checks_disabled=False,
            cast_scope_included=False, population_application=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == result, 'Sealed result differs')
        else:
            life.save(path, result)
    proxy.save = save
    ns['life'] = proxy
    ns['verify'](out, seal)


def run(out, seal):
    check(out, seal)
    ns = prior.predecessor.namespace()
    ns['verify'] = verify
    ns['run'](out, seal)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify', 'el'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--file')
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        prepare(out)
    elif a.mode == 'el':
        c = json.loads((out / 'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(prior.predecessor.namespace()['parse_el']((out / a.file).read_text(), c)))))
    else:
        require(a.seal, 'Exact config seal required')
        (run if a.mode == 'run' else verify)(out, a.seal)
