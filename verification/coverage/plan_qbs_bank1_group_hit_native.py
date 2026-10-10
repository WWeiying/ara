"""Prepare-only exact source-bit contract; not a native parser or launcher."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import review_qbs_bank1_group_hit789_all_cycle as source

REVIEW = source.OUT / 'qbs-bank1-group-hit789-all-cycle-source-review-agent-20261008-01.json'
REVIEW_SHA = 'c0a3fcb41c57747fb5455586941c08d56bb27272edaa5443f5da292e86d07c98'
STAGES = ('before', 'selected', 'reset', 'reloaded', 'final')
CURRENT = source.OUT / 'akv-canonical-kfault-offline-admitted791-agent-20261008-01'
CURRENT_SHA = '8b732015035c1f716940598f05d8a8063e4b4829eb5cd67cfebcbb2728ee2b30'
require = source.native.require


def intervals(bits):
    result = []
    for bit in sorted(bits):
        if result and result[-1][1] + 1 == bit:
            result[-1][1] = bit
        else:
            result.append([bit, bit])
    return result


def atoms(plan):
    return {(plan['scope'], name, bit, direction)
            for name, bits in plan['target_bits'].items() for bit in bits
            for direction in ('0to1', '1to0')}


def check_stages(plan, captured):
    """Host semantic contract AFTER an independently checked native decoder.

    Rows are keyed by complete compiled scope, name, bit and direction. They
    carry an excluded boolean, not serialized-position or display-order IDs.
    This function alone cannot establish native decoding or qualification.
    """
    require(set(captured) == set(STAGES), 'All five stages required')
    expected = set()
    for scope, nodes in plan['protected_scopes'].items():
        for node in nodes:
            a = node['attributes']
            if node['tag'] == 'arrays':
                expected.add((scope, a['name'], 'array', 'whole-protected'))
                continue
            lo, hi = sorted((int(a.get('left', '0')), int(a.get('right', '0'))))
            expected.update((scope, a['name'], bit, d)
                            for bit in range(lo, hi + 1) for d in ('0to1', '1to0'))
    selected = atoms(plan)
    require(len(selected) == 3232 and selected < expected, 'Partial exact targets only')
    for stage in STAGES:
        rows = captured[stage]
        require(len(rows) == len(expected), 'Complete semantic inventory required')
        got = {}
        for key, excluded in rows:
            key = tuple(key)
            require(key in expected and key not in got, 'Foreign/duplicate semantic atom')
            require(type(excluded) is bool, 'Strict excluded boolean')
            got[key] = excluded
        require(set(got) == expected, 'Missing semantic atom')
        wanted = selected if stage in ('selected', 'reloaded') else set()
        require({k for k, v in got.items() if v} == wanted, 'Target/protected/reset mask differs')
    return {'five_stage_semantic_masks': True, 'native_qualified': False}


def collect():
    require(source.native.digest(REVIEW) == REVIEW_SHA, 'Frozen source review seal')
    review = json.loads(REVIEW.read_bytes())
    require(review == source.collect(), 'Full source/prefix/suffix replay differs')
    manifest = json.loads((source.BASE / 'admission-manifest.json').read_bytes())
    authority = dict(manifest['input_pins'], **manifest['output_pins'])
    ledger = (source.BASE / 'combined-inputs.txt').read_text().splitlines()
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml',
             db / 'shape/tgl.verilog.shape.xml']
    pins = dict(review['input_pins'], **{str(REVIEW): REVIEW_SHA})
    for p in paths:
        require(str(p) in authority and source.native.digest(p) == authority[str(p)],
                'Compiled source/info/shape not authority-pinned')
        pins[str(p)] = authority[str(p)]
    design, info, shape = [source.native.xml(p) for p in paths]
    scopes = sorted(n.get('name') for n in info.iter('instance_data')
                    if n.get('name') == source.SCOPE or
                    n.get('name', '').startswith(source.SCOPE + '.'))
    require(len(scopes) == len(set(scopes)) and source.SCOPE in scopes, 'Exact subtree scope inventory')
    # Parameter-merged definitions use their source-definition id, not a
    # shortened module name. Keep the full compiled parameter display string.
    instances = {n.get('id'): (n, m) for m in design.findall('srcdef')
                 for n in m.findall('srcinst')}
    require(len(instances) == sum(len(m.findall('srcinst')) for m in design.findall('srcdef')),
            'Duplicate compiled instance id')
    def full_path(key, seen=()):
        require(key not in seen, 'Hierarchy cycle')
        n, _ = instances[key]
        pid = n.get('pid')
        return (full_path(pid, seen+(key,)) + '.' if pid in instances else '') + n.get('name')
    hierarchy = {full_path(k): m for k, (_, m) in instances.items()}
    require(len(hierarchy) == len(instances), 'Duplicate compiled scope')
    checks = {n.get('name'): n.get('chksum') for n in info.iter('instance_data')
              if n.get('name') in scopes}
    definitions = {}
    for scope in scopes:
        module = hierarchy[scope]
        matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checks[scope]
                   and (d.get('id') == module.get('id') if d.get('id') is not None
                        else d.get('name') == module.get('name'))]
        require(len(matches) == 1, 'Exact source-definition id/checksum binding')
        definitions[scope] = dict(module=dict(module.attrib),
                                 shape=ET.tostring(matches[0], encoding='unicode'))
    protected = {}
    for scope, definition in definitions.items():
        nodes = list(ET.fromstring(definition['shape']).find('tglshape'))
        require(all(n.tag in ('node', 'vectornode', 'arrays') for n in nodes), 'Unknown compiled type')
        require(len(nodes) == len({n.get('name') for n in nodes}), 'Duplicate compiled object')
        protected[scope] = [dict(tag=n.tag, attributes=dict(n.attrib),
                                 complete_xml=ET.tostring(n, encoding='unicode')) for n in nodes]
    parent = {n['attributes']['name']: n for n in protected[source.SCOPE]}
    target_bits = {}
    for t in review['source_targets']:
        require(parent[t['name']]['attributes'] == t['attributes'], 'Exact source/shape target binding')
        target_bits[t['name']] = t['source_zero_bit_indices']
    require(len(parent) == 3286 and len(target_bits) == 72 and
            sum(map(len, target_bits.values())) == 1616, 'Exact parent partition')
    current_path = CURRENT / 'admission-manifest.json'
    require(source.native.digest(current_path) == CURRENT_SHA, 'Formal791 seal')
    current = json.loads(current_path.read_bytes())
    require(current['coverage_admitted'] is True, 'Formal791 not admitted')
    pins[str(current_path)] = CURRENT_SHA
    current_authority = dict(current['input_pins'], **current['output_pins'])
    current_ledger = CURRENT / 'combined-inputs.txt'
    require(source.native.digest(current_ledger) == current_authority[str(current_ledger)], '791 ledger pin')
    pins[str(current_ledger)] = current_authority[str(current_ledger)]
    members = current_ledger.read_text().splitlines()
    require(len(members) == len(set(members)) == 792 and members[:790] == ledger, 'Exact789 prefix in791')
    suffix = 0
    for member in members[790:]:
        files = list((Path(member)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Exact790/791 testdata')
        rows, sha = source.native.rows(files[0], [source.SCOPE])
        require(sha == current_authority[str(files[0])] and
                (rows[source.SCOPE]['checksum'], rows[source.SCOPE]['width']) == ('3028946256', 26222),
                '791 actual bitmap/checksum pin')
        pins[str(files[0])] = sha
        suffix |= int(rows[source.SCOPE]['bits'], 16)
    gap = json.loads(source.GAPS.read_bytes())
    rank = next(r for r in gap['ranking'] if r['scope'] == source.SCOPE)
    activation = [pos for f in rank['objects'] if 'gen_activation' in f['name'] and
                  f['name'].endswith('.group_hit') for pos in f['coordinates']]
    target_coords = [pos for t in review['source_targets'] for pos in t['actual_missing789_coordinates']]
    activation_gain = sum(bool(suffix >> (26221-pos) & 1) for pos in activation)
    target_gain = sum(bool(suffix >> (26221-pos) & 1) for pos in target_coords)
    require(len(activation) == 3936 and target_gain == 0, 'Actual791 candidate hit contradicts proof')
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_plan_qbs_bank1_group_hit_native.py')):
        pins[str(path)] = source.native.digest(path)
    for path, sha in pins.items():
        require(source.native.digest(Path(path)) == sha, 'End-of-plan pin drift')
    return dict(status='STATIC_PREPARE_ONLY_FRESH_NATIVE_BINDING_REQUIRED', scope=source.SCOPE,
        source_review_sha256=REVIEW_SHA, source_population=789,
        measured_population=791, formal791_manifest_sha256=CURRENT_SHA,
        actual790_791_activation_group_hit_new_directions=activation_gain,
        actual791_activation_group_hit_missing_directions=3936-activation_gain,
        actual790_791_target_new_directions=target_gain,
        target_bits=target_bits, source_bit_intervals={n: intervals(b) for n, b in target_bits.items()},
        protected_scopes=protected, compiled_checksums=checks,
        compiled_module_identities={s: d['module'] for s, d in definitions.items()},
        parent_objects=3286, parent_non_target_objects=3214,
        target_vector_retained_bits=688, parent_protected_directions=22990,
        target_directions=3232, mapping_permitted_missing_coordinates_protected=704,
        child_scope_count=len(scopes)-1, native_label=None, native_qualified=False,
        required_native_gates=[
            'One admitted compatible sample and frozen simv/tool identity, complete pins before launch.',
            'Fresh before capture: exact scope/module/checksum, every typed object and all child scopes; no guessed labels.',
            'Bind actual native direction and range records to source declaration bit indices, not serialized-position order.',
            'Save only partial target bits in both directions; reject whole object, whole scope, foreign metrics, duplicates and overlaps.',
            'Five actual complete inventory and typed EL stages: before/selected/reset/reloaded/final; semantic set comparison, independent order.',
            'Selected/reloaded exclude exactly target atoms. Every other bit, object, child and output port stays excluded0. Reset/final globally empty.',
            'Strict integer terminal0, no timeout, one actual DVE executable/cwd; pin immutable captures after launcher completion.',
        ],
        source_boundary_notes=[
            'Reset/clear invalidate FIFO and pending before unreset target storage can become consumed.',
            'Push and pop preserve occupied-entry membership; pending copies the same byte index and only removes strobes.',
            'Per-slot consumed implies corresponding source_valid AND target.valid; opposite active slot cannot unmask stale metadata.',
            'Fault disables fresh ingress; accepted pre-fault tuples retain mapping while draining; FAULT_CLEAR gates both slots.',
            'Source host mapper is invoked only for legal ROW/M4/M8 enums. Its unsupported-layout API is not an RTL oracle.',
            'Before-reset arbitrary state/startup X is outside the invariant; no X-startup exclusion.',
        ], input_pins=pins, EL_created=False, EDA_launched=False,
        sealed791_modified=False, official_percentage=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args()
    require(a.output.parent.resolve() == source.OUT and not a.output.exists(), 'Fresh verification/out file only')
    result = collect()
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(dict(output=str(a.output), sha256=source.native.digest(a.output),
                         child_scopes=result['child_scope_count'], native_qualified=False)))
