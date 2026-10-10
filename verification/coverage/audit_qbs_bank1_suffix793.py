"""Read-only full-field raw suffix audit; no DVE, EL creation or admission."""
import argparse
import json
from pathlib import Path

import targeted_toggle_evidence_v2 as native

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'verification/out'
BASE = OUT/'scalar-misalign-offline-admitted792-agent-20261008-01'
BASE_SHA = '0aadd9e4fa71a5a582830a043fedc67669b0f53cea866a1b8147a5526c8f81f4'
NEXT = OUT/'scalar-slot-rotation-offline-admitted793-parent-20261008-01'
LOCAL = OUT/'qbs-bank1-group-hit-native791-v2-parent-20261008-01'
LOCAL_SHA = '323b84514531645f65bb8c952cc739e9dc64bb82a026bb6a2ff74050cbaf852f'
CONFIG_SHA = 'cc7e96fd8713d7ed7a1af30486162e91c7b42ee2685a193480c78d8119f87c29'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank1'
need = native.require


def prefix(before, after):
    need(len(before) == len(set(before)) == 793 and
         len(after) == len(set(after)) == 794 and after[:793] == before,
         'Exact published792 prefix and one unique793 suffix')
    return after[-1]


def fields(nodes, row, targets):
    need(row['checksum'] == '3028946256' and type(row['width']) is int and row['width'] > 0,
         'Exact bank1 checksum/width')
    bits = int(row['bits'], 16)
    need(0 <= bits < 1 << row['width'], 'Raw bitmap overflow/nonbinary representation')
    raw = format(bits, '0%db' % row['width'])
    offset = 0; result = []; seen = set()
    for node in nodes:
        a = dict(node.attrib); name = a['name']
        need(node.tag in ('node','vectornode') and name not in seen, 'No arrays/duplicate/foreign type')
        seen.add(name)
        width = 1 if node.tag == 'node' else abs(int(a['left'])-int(a['right']))+1
        value = raw[offset:offset+2*width]
        need(len(value) == 2*width, 'Truncated full-field bitmap')
        t = targets.get(name)
        selected = []
        if t:
            need(node.tag == 'vectornode' and a == t['attributes'] and
                 a['left'] == '31' and a['right'] == '0' and a['portnode'] == '0', 'Exact target source declaration')
            selected = t['source_zero_bit_indices']
            need(selected == sorted(set(selected)) and all(type(b) is int and 0 <= b < width for b in selected)
                 and 0 < len(selected) < width, 'Exact partial bits, never whole object')
            need(t['actual_missing789_coordinates'] == [offset+2*b+d for b in selected for d in (0,1)],
                 'Source/serialized coordinate binding')
        hits = [offset+2*b+d for b in selected for d in (0,1) if value[2*b+d] == '1']
        result.append(dict(name=name, kind=node.tag, attributes=a, serialized_offset=offset,
            raw_serialized_directions=value, raw_hit_positions_count=value.count('1'),
            partial_source_zero_bits=selected, candidate_raw_hit_coordinates=hits,
            whole_object_exclusion=False))
        offset += 2*width
    need(offset == row['width'] and set(targets) <= seen, 'Complete full-field typed partition')
    return result


def collect(seal):
    pins = {}
    def bound(path, sha):
        need(path.resolve(strict=True) == path and not path.is_symlink() and native.digest(path) == sha,
             'Authority input pin: '+str(path))
        pins[str(path)] = sha
        return json.loads(path.read_bytes())
    baseline = bound(BASE/'admission-manifest.json', BASE_SHA)
    latest = bound(NEXT/'admission-manifest.json', seal)
    need(baseline['coverage_admitted'] is True and latest['coverage_admitted'] is True,
         'Publish/admit required; prepared-only is not authoritative')
    oldpins = dict(baseline['input_pins'], **baseline['output_pins'])
    authority = dict(latest['input_pins'], **latest['output_pins'])
    ledgers = []
    for directory, approved in ((BASE, oldpins),(NEXT, authority)):
        path = directory/'combined-inputs.txt'
        need(native.digest(path) == approved[str(path)], 'Published ledger seal')
        pins[str(path)] = approved[str(path)]
        ledgers.append(path.read_text().splitlines())
    sample = prefix(*ledgers)
    q = bound(LOCAL/'qualification.json', LOCAL_SHA)
    c = bound(LOCAL/'config.json', CONFIG_SHA)
    need(q['status'] == 'QBS_BANK1_GROUP_HIT3232_V2_NATIVE_QUALIFIED_NOT_APPLIED' and
         q['config_sha256'] == CONFIG_SHA and q['target_directions'] == 3232 and
         q['mapping_permitted_missing704_protected'] is True and q['population_application'] is False,
         'Exact independently accepted native qualification')
    review_path = OUT/'qbs-bank1-group-hit789-all-cycle-source-review-agent-20261008-01.json'
    review = bound(review_path, c['plan']['source_review_sha256'])
    need(review['scope'] == SCOPE, 'Source owner')
    targets = {t['name']:t for t in review['source_targets']}
    need(len(targets) == 72 and sum(len(t['source_zero_bit_indices']) for t in targets.values()) == 1616,
         'Exact72 partial candidates only')
    shape_path = Path(ledgers[1][0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    need(authority[str(shape_path)] == c['pins'][str(shape_path)] and
         native.digest(shape_path) == authority[str(shape_path)], 'Same frozen compiled shape')
    pins[str(shape_path)] = authority[str(shape_path)]
    definitions = [d for d in native.xml(shape_path).findall('tgldef')
                   if d.get('name') == 'qbs_block_adapter' and d.get('chksum') == '3028946256']
    need(len(definitions) == 1, 'Exact compiled definition')
    nodes = list(definitions[0].find('tglshape'))
    parent = next(i for i in c['instances'] if i['scope'] == SCOPE)
    need(len(nodes) == 3286 and {n.get('name'):dict(n.attrib) for n in nodes} ==
         {b['attributes']['name']:b['attributes'] for b in parent['bindings']}, 'Full native-qualified typed field set')
    files = list((Path(sample)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1, 'One suffix testdata, no partial VDB')
    rows, sha = native.rows(files[0], [SCOPE])
    need(sha == authority[str(files[0])], 'Published raw bitmap seal')
    pins[str(files[0])] = sha
    need(rows[SCOPE]['width'] == 26222, 'Complete frozen scope width')
    result = fields(nodes, rows[SCOPE], targets)
    hits = [i for field in result for i in field['candidate_raw_hit_coordinates']]
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_audit_qbs_bank1_suffix793.py')):
        pins[str(path)] = native.digest(path)
    for path, sha in pins.items(): need(native.digest(Path(path)) == sha, 'Audit end pin drift')
    return dict(status='FORMAL793_SUFFIX_SOURCE_CONSTANT_ZERO_PASS' if not hits else
                'HOLD_OBSERVED_SOURCE_CONSTANT_COUNTEREXAMPLE', population=793, prefix792_exact=True,
        sample=sample, scope=SCOPE, checksum='3028946256', serialized_width=26222, full_typed_fields=3286,
        candidate_objects=72, candidate_bits=1616, candidate_directions=3232,
        candidate_hit_coordinates=hits, suffix_candidate_zero=not hits, full_field_raw=result,
        native_direction_order_in_raw_not_inferred=True,
        counts_are_suffix_raw_not_population_incremental_gain=True,
        dynamic_bits_and704_not_waived=True, input_pins=pins,
        EDA_launched=False, EL_created=False, frozen_dependencies_modified=False,
        population_application=False, official_percentage=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--manifest-seal', required=True)
    cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args()
    need(a.output.parent.resolve() == OUT and not a.output.exists(), 'Fresh separate audit output')
    result = collect(a.manifest_seal)
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps(dict(status=result['status'], output=str(a.output), sha256=native.digest(a.output))))
