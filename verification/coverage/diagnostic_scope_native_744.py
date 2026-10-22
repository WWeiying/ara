"""Exact complete diagnostic fields; reuse qualified queue native lifecycle, no report."""
import argparse
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import queue_constant_native_v2 as predecessor

q = predecessor.old
life, require = q.life, q.require
HERE = Path(__file__).resolve().parent
AUDIT = life.OUT / 'diagnostic-sink-capacity-744-agent-20261007-01.json'
AUDIT_SHA = 'ff44af1bc878bbd0d6eb7b41a0d10171cefcae220858f54c76ed0ae54717de58'
REVIEW = life.OUT / 'diagnostic-sink-review-744-agent-20261007-01.json'
REVIEW_SHA = 'd12685abefaa762fe59a1b92e434b82242a852f09e95437686a2b4668c35df61'
OLD = life.OUT / 'queue-constant-native-744-agent-20261007-03'
OLD_CONFIG_SHA = 'b2d53834d046de0a722342dfdce8dbdacc7c3898c2abb21e9618d8adae0dd7a6'
OLD_CAPTURE_SHA = '15dcd0fc0a923f0ea8d49ef0a6edd3c89d711cee7ff546edf1ede125347daa87'


def targets(audit, config):
    base = Path(config['design']) / 'snps/coverage/db'
    shapes = q.toggle.xml(base / 'shape/tgl.verilog.shape.xml')
    definitions = {n.get('chksum'): n for n in shapes.findall('tgldef')}
    requested = {}
    for group in audit['groups']:
        if not group['fields']:
            continue
        require(group['status'] in ('SOURCE_REVIEW_ELIGIBLE_NATIVE_REQUIRED',
                'SOURCE_REVIEW_CANDIDATE_NATIVE_REQUIRED'), 'Unreviewed group')
        scope = group['scope']
        instance = requested.setdefault(scope, dict(scope=scope,
            design_module_checksum=group['module_checksum'], toggle_checksum=group['toggle_checksum'], signals=[]))
        require(instance['toggle_checksum'] == group['toggle_checksum'] and
                instance['design_module_checksum'] == group['module_checksum'], 'Scope checksum disagreement')
        for field in group['fields']:
            name, node = field['name'], field['compiled']
            require(node['name'] == name and not any(s['name'] == name for s in instance['signals']),
                    'Duplicate/misbound source field')
            scalar = 'left' not in node
            left, right = int(node.get('left', '0')), int(node.get('right', '0'))
            bits = list(range(min(left, right), max(left, right) + 1))
            require(len(bits) == field['bits'] and field['directions'] == 2 * len(bits), 'Incomplete whole field')
            instance['signals'].append(dict(name=name, bits=bits, scalar=scalar, left=left, right=right,
                native_label=name if scalar or left == right == 0 else name + '[' + str(left) + ':' + str(right) + ']',
                shape=node))
    result = []
    for scope, instance in sorted(requested.items()):
        nodes = {n.get('name'): n for n in definitions[instance['toggle_checksum']].iter()
                 if n.tag in ('node', 'vectornode')}
        names = {s['name'] for s in instance['signals']}
        require(all(dict(nodes[s['name']].attrib) == s['shape'] for s in instance['signals']), 'Compiled field drift')
        instance['protected'] = [dict(n.attrib) for name, n in nodes.items() if name not in names]
        instance['retained_target_signal_bits'] = {name: [] for name in names}
        result.append(instance)
    require(sum(len(i['signals']) for i in result) == 224 and
            len(q.bitset(dict(instances=result))) == 11038, 'Reviewed whole-field universe differs')
    return result


def prepare(out):
    require(out.parent == life.OUT and not out.exists(), 'Fresh independent native directory required')
    audit = life.read_bound(AUDIT, AUDIT_SHA)
    review = life.read_bound(REVIEW, REVIEW_SHA)
    require(review['inventory_sha256'] == AUDIT_SHA and not review['application_approval'], 'Wrong static review')
    old = life.read_bound(OLD / 'config.json', OLD_CONFIG_SHA)
    capture = life.read_bound(OLD / 'capture-result.json', OLD_CAPTURE_SHA)
    require(capture['status'] == 'QUEUE_CONSTANT_EXACT_NATIVE_BIT_DIRECTION_ROUNDTRIP_PASS', 'Predecessor not qualified')
    pins = life.merge_pins(life.merge_pins(capture['pins'], audit['pins']), {
        str(AUDIT): AUDIT_SHA, str(REVIEW): REVIEW_SHA,
        str(OLD / 'config.json'): OLD_CONFIG_SHA, str(OLD / 'capture-result.json'): OLD_CAPTURE_SHA})
    for path in (Path(__file__).resolve(), HERE / 'test_diagnostic_scope_native_744.py',
                 Path(predecessor.__file__).resolve(), HERE / 'queue_constant_native.tcl'):
        pins[str(path)] = life.digest(path)
    config = dict(old, output=str(out), pins=pins, instances=targets(audit, old),
        source_proof=dict(kind='INTEGRATION_DIAGNOSTIC_COMPLETE_FIELDS_NOT_UNREACHABILITY',
                          audit=str(AUDIT), review=str(REVIEW), protected=review['explicit_protection']),
        diagnostic_scope=True, population_application=False, automatic_retry=False)
    candidate = q.candidate(config).replace(
        'Frozen post-reset source invariant; no X, pressure, or module waiver',
        'Integration diagnostic complete fields; product control and runtime checks preserved')
    require(len(predecessor.namespace()['parse_el'](candidate, config)) == 11038, 'Candidate set differs')
    life.check(pins)
    out.mkdir()
    q.common.common.save(out / 'candidate.el', candidate)
    values = {'qc_design': config['design'], 'qc_vdb': config['vdb'], 'qc_test': config['test'],
              'qc_python': shutil.which('python3'), 'qc_helper': str(Path(__file__).resolve())}
    require(all(not any(c in v for c in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl path')
    selection = ''.join('set ' + k + ' {' + v + '}\n' for k, v in values.items()) + 'set qc_instances {}\n'
    for instance in config['instances']:
        labels = ' '.join('{' + s['native_label'] + '}' for s in instance['signals'])
        selection += 'lappend qc_instances [list {' + instance['scope'] + '} [list ' + labels + ']]\n'
    q.common.common.save(out / 'selection.tcl', selection)
    for path in (out / 'candidate.el', out / 'selection.tcl'):
        pins[str(path)] = life.digest(path)
    life.save(out / 'config.json', config)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), objects=224,
                         bit_directions=11038, scopes=len(config['instances']), EDA_started=False)))


def verify(out, seal):
    ns = predecessor.namespace()
    def save(path, result):
        require(path == out / 'capture-result.json', 'Unexpected verifier write')
        result.update(status='DIAGNOSTIC_COMPLETE_FIELDS_EXACT_NATIVE_ROUNDTRIP_PASS',
                      integration_diagnostic_scope=True, source_audit_sha256=AUDIT_SHA,
                      product_control_excluded=False, runtime_checks_disabled=False,
                      population_application=False)
        if path.exists():
            require(json.loads(path.read_bytes()) == result, 'Sealed qualification differs')
        else:
            life.save(path, result)
    ns['life'] = SimpleNamespace(**vars(life))
    ns['life'].save = save
    ns['verify'](out, seal)


def run(out, seal):
    ns = predecessor.namespace()
    ns['verify'] = verify
    ns['run'](out, seal)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'el'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--file')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'el':
        c = json.loads((out / 'config.json').read_bytes())
        print(json.dumps(dict(bit_directions=len(predecessor.namespace()['parse_el']((out / args.file).read_text(), c)))))
    elif args.mode == 'prepare':
        prepare(out)
    else:
        (run if args.mode == 'run' else verify)(out, args.seal)
