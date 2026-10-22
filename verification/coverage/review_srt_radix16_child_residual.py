"""Frozen radix16 child deduplication/source review; no EDA or exclusions."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
DB = BUILD / 'sim/simv.vdb/snps/coverage/db'
BASE = OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
REVIEW = OUT / 'c910-srt-datapath-scoped-review-741-agent-20261007-01.json'
REVIEW_SHA = '9a54de4896ea792ce8c6f0eec8e396b09b50d3c16009456912a4471ce1881c6f'
CACHE = OUT / 'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
MODULE = 'ct_vfdsu_srt_radix16_with_sqrt'
UPSTREAM = 'e5aa6a01b5bbe1675c3aa8872e1203413ded83d1'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, expected=None):
    if expected:
        need(digest(path) == expected, 'Pin mismatch: ' + str(path))
    return json.loads(Path(path).read_bytes())


def xml(path):
    raw = Path(path).read_bytes()
    return ET.fromstring(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)


def native_name(node):
    return node['name'] + ('[%s:%s]' % (node['left'], node['right'])
                           if node['kind'] == 'vectornode' else '')


def retain_reason(node):
    name = node['name']
    if node['portnode'] != '0':
        return 'INTERFACE_PORT_RETAIN_ALL_BITS'
    if name in ('bound_sel', 'bound_cmp_sign', 'part_rem') or name.startswith(('bound', 'digit_bound_')):
        return 'QUOTIENT_DIGIT_BOUNDARY_SELECTION_RETAIN_ALL_BITS'
    if name in ('qt_rt_const_shift_std', 'qt_rt_const_shift_std_next'):
        return 'ITERATION_POSITION_ROOT_STEP_CONTROL_RETAIN_ALL_BITS'
    need(node['kind'] == 'node', 'Unclassified internal vector: ' + name)
    return 'SCALAR_MODE_SIGN_ROUND_CLOCK_CONTROL_RETAIN'


def partition(nodes, names):
    need(len({n['name'] for n in nodes}) == len(nodes), 'Duplicate shape names')
    need(names <= {n['name'] for n in nodes}, 'Unknown approved field')
    approved, protected = [], []
    for n in nodes:
        if n['name'] in names:
            need(n['kind'] == 'vectornode' and n['portnode'] == '0', 'Port/scalar approved incorrectly')
            need(not n['name'].startswith(('bound', 'digit_bound_')) and
                 n['name'] not in ('part_rem', 'qt_rt_const_shift_std', 'qt_rt_const_shift_std_next'),
                 'Digit boundary/root-step control cannot be an arithmetic target')
            approved.append(n)
        else:
            protected.append(dict(n, retention_reason=retain_reason(n)))
    need(len(approved) == 158 and len(protected) == 52, 'Not exact158/52 partition')
    return approved, protected


def direction_missing(bits, total, node):
    start, width = node['raw_offset'], node['width']
    mask = (1 << (2 * width)) - 1
    value = (bits >> (total - start - 2 * width)) & mask
    return dict(pair_slot0=sum(not (value >> (2 * (width - 1 - i) + 1) & 1) for i in range(width)),
                pair_slot1=sum(not (value >> (2 * (width - 1 - i)) & 1) for i in range(width)),
                total=2 * width - bin(value).count('1'))


def collect():
    review = load(REVIEW, REVIEW_SHA)
    book = load(BASE / 'admission-manifest.json',
                '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5')
    ledger = BUILD / 'build-source-pins.json'
    srcpins = load(ledger, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    source = ROOT / review['source']['path']
    need(review['module'] == MODULE and digest(source) == srcpins[str(source)] == review['source']['sha256'],
         'Frozen child source drift')
    need(digest(BUILD / 'sim/simv') == '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3', 'Image drift')
    upstream = subprocess.run(['git', '-C', str(ROOT / 'hardware/deps/fpnew'), 'show',
        UPSTREAM + ':vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/' + MODULE + '.v'],
        cwd=ROOT, check=True, capture_output=True).stdout
    need(upstream == source.read_bytes(), 'Upstream arithmetic source changed')
    pins = {str(REVIEW): REVIEW_SHA, str(CACHE): CACHE_SHA,
            str(source): digest(source), str(ledger): digest(ledger),
            str(BUILD / 'sim/simv'): digest(BUILD / 'sim/simv'),
            str(BASE / 'admission-manifest.json'): digest(BASE / 'admission-manifest.json')}
    for p in review['compiled_pins']:
        path = ROOT / p['path']
        need(digest(path) == p['sha256'], 'Compiled shape drift')
        pins[str(path)] = p['sha256']
    design = xml(DB / 'design/verilog.design.xml')
    mod = next(x for x in design.iter('srcdef') if x.get('name') == MODULE)
    need(mod.get('chksum') == review['design_checksum'] == '406590228', 'Wrong compiled module')
    allinst = {n.get('id'): n for n in design.iter('srcinst')}
    def scope(node):
        parent = allinst.get(node.get('pid'))
        return (scope(parent) + '.' if parent is not None else '') + node.get('name')
    compiled_scopes = {scope(n): n.attrib for n in mod.findall('srcinst')}
    info = xml(DB / 'shape/tgl.verilog.info.xml')
    scopes = sorted(n.get('name') for n in info.iter('instance_data')
                    if n.get('chksum') == '3969040510')
    need(len(scopes) == 17 and set(scopes) == set(compiled_scopes), 'Compiled scope binding differs')
    sourceinfo = DB / 'auxiliary/verilog.sourceinfo.xml'
    filenode = next(n for n in xml(sourceinfo).iter('fileinfo') if n.get('id') == '375')
    need(filenode.get('name') == str(source), 'File375 source binding differs')
    pins[str(sourceinfo)] = digest(sourceinfo)
    defs = [n for n in xml(DB / 'shape/tgl.verilog.shape.xml').iter('tgldef') if n.get('name') == MODULE]
    need(len(defs) == 1 and defs[0].get('chksum') == '3969040510', 'Shape module mismatch')
    nodes, offset = [], 0
    lines = source.read_text().splitlines()
    for n in defs[0].find('tglshape'):
        need(n.tag in ('node', 'vectornode') and n.get('file') == '375', 'Unexpected native shape kind/source')
        width = abs(int(n.get('left')) - int(n.get('right'))) + 1 if n.tag == 'vectornode' else 1
        row = dict(kind=n.tag, **n.attrib, width=width, raw_offset=offset,
                   declaration=lines[int(n.get('line_num')) - 1])
        need(re.search(r'\b' + re.escape(n.get('name')) + r'\s*;', row['declaration']), 'Declaration name drift')
        nodes.append(row)
        offset += 2 * width
    need(len(nodes) == 210 and offset == 20656, 'Exact local shape width differs')
    names = {r[0] for r in review['signals']}
    approved, protected = partition(nodes, names)
    for name, line, width, left, right, file_id in review['signals']:
        n = next(n for n in approved if n['name'] == name)
        need((int(n['line_num']), n['width'], int(n['left']), int(n['right']), n['file']) ==
             (line, width, left, right, file_id), 'Approved full-field identity mismatch')
    prior_protected = [{k: n[k] for k in ('kind', 'name', 'file', 'line_num', 'type', 'portnode', 'excluded',
                        *(['left', 'right'] if n['kind'] == 'vectornode' else []))} for n in protected]
    need(prior_protected == review['protected_native_shape_objects'], 'Protection complement differs')
    capture_records, existing_scopes = [], set()
    for directory in ('c910-srt-native1264-recovery-agent-20261007-01',
                      'c910-fp16-additional8-native742-agent-20261007-01'):
        folder = OUT / directory
        terminal = load(folder / 'capture-result.json')
        config = load(folder / 'config.json', terminal['config_seal'])
        need(terminal['status'] == 'EXACT_C910_1264_NATIVE_ROUNDTRIP_NOT_POPULATION_APPLICATION'
             and terminal['objects'] == 1264 and terminal['non_target_exclusions'] == 0
             and terminal['both_directions'] and terminal['semantic_reload'] and terminal['finalreset'],
             'Prior native qualification not PASS')
        pins[str(folder / 'capture-result.json')] = digest(folder / 'capture-result.json')
        pins[str(folder / 'config.json')] = terminal['config_seal']
        for index, instance in enumerate(config['instances']):
            s = instance['scope']
            need(s in scopes and s not in existing_scopes and
                 {x['name'] for x in instance['signals']} == names,
                 'Prior captures overlap or target wrong module')
            existing_scopes.add(s)
            inv = folder / ('native_before_%d.tsv' % index)
            need(digest(inv) == terminal['pins'][str(inv)], 'Actual native inventory drift')
            with inv.open(newline='') as stream:
                native = list(csv.DictReader(stream, delimiter='\t'))
            native_names = [n['name'] for n in native]
            need(len(native_names) == len(set(native_names)) and
                 all(native_names.count(native_name(n)) == 1 for n in nodes), 'Incomplete/ambiguous actual native complement')
            pins[str(inv)] = digest(inv)
        capture_records.append(dict(path=str(folder), result_sha256=digest(folder / 'capture-result.json'),
                                    config_seal=terminal['config_seal'], objects=1264, scopes=[x['scope'] for x in config['instances']]))
    scalar = sorted(set(scopes) - existing_scopes)
    need(len(existing_scopes) == 16 and len(scalar) == 1 and '.i_ariane.' in scalar[0], 'Unexpected remaining scopes')
    evidence = []
    for item in review['evidence']:
        for pin in item['pins']:
            path = ROOT / pin['path']
            need(digest(path) == pin['sha256'], 'DIV/SQRT evidence drift')
            pins[str(path)] = pin['sha256']
        comparison = load(ROOT / item['directory'] / 'vector-comparison.json')
        exact = item['representative_exact_request']
        need(comparison['status'] == 'PASS' and comparison['first_mismatch'] is None and
             exact in comparison['instructions'] and exact['skipped_unknown_bytes'] == 0,
             'Exact arithmetic-write evidence absent')
        evidence.append(item)
    cache = load(CACHE, CACHE_SHA)
    need(cache['tests'] == 741 and not cache['official_denominator_available'], 'Wrong historical Toggle OR cache')
    inputpath = BASE / 'combined-inputs.txt'
    need(digest(inputpath) == book['output_pins'][str(inputpath)], 'Formal762 ledger drift')
    inputs = inputpath.read_text().splitlines()
    oldpath = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    need(digest(oldpath) == cache['input_pins'][str(oldpath)], 'Cached741 ledger drift')
    oldinputs = oldpath.read_text().splitlines()
    need(len(inputs) == len(set(inputs)) == 763 and len(oldinputs) == 742 and inputs[:742] == oldinputs,
         'Cached741 is not an exact prefix of formal762')
    pins[str(inputpath)] = digest(inputpath)
    pins[str(oldpath)] = digest(oldpath)
    union = {}
    for s in scopes:
        row = cache['instances'][s]
        need(row['width'] == offset and row['checksum'] == '3969040510', 'Cache shape differs')
        union[s] = int(row['bits'], 16)
    suffix_pins = []
    for index, vdb in enumerate(inputs[742:], 742):
        paths = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        need(len(paths) == 1, 'Ambiguous suffix native test')
        path = paths[0]
        need(str(path) in book['input_pins'] and digest(path) == book['input_pins'][str(path)], 'Suffix native pin drift')
        pins[str(path)] = digest(path)
        suffix_pins.append(str(path))
        found = {}
        for n in xml(path).iter('instance_data'):
            s = n.get('name')
            if s not in union:
                continue
            need(s not in found and n.get('chksum') == '3969040510' and
                 len(n.get('value')) == offset and set(n.get('value')) <= {'0', '1'}, 'Suffix native shape mismatch')
            found[s] = int(n.get('value'), 2)
        need(set(found) == set(scopes), 'Suffix missing exact scope')
        for s, value in found.items():
            union[s] |= value
        if (index - 741) % 7 == 0:
            print('Readonly child Toggle suffix %d/21' % (index - 741), flush=True)
    records = []
    for s in scopes:
        fields = [dict(n, missing_directions=direction_missing(union[s], offset, n),
                       classification=('EXISTING_APPROVED_ARITHMETIC_NOT_NEW_TARGET' if n['name'] in names and
                                       s in existing_scopes else 'PROTECTED_SCALAR_INSTANCE_NO_TRANSFER' if s in scalar
                                       else retain_reason(n))) for n in nodes]
        total = sum(n['missing_directions']['total'] for n in fields)
        need(total == offset - bin(union[s]).count('1'), 'Missing direction accounting differs')
        records.append(dict(scope=s, compiled_instance=compiled_scopes[s], checksum='3969040510',
            raw_width=offset, raw_bits=hex(union[s]), missing_directions=total, fields=fields,
            already_qualified_arithmetic_missing=sum(n['missing_directions']['total'] for n in fields
                if n['classification'] == 'EXISTING_APPROVED_ARITHMETIC_NOT_NEW_TARGET'),
            retained_missing=sum(n['missing_directions']['total'] for n in fields
                if n['classification'] != 'EXISTING_APPROVED_ARITHMETIC_NOT_NEW_TARGET')))
    descendants = [dict(n.attrib) for n in info.iter('instance_data')
                   if any(n.get('name', '').startswith(s + '.') for s in scopes)]
    source_parent = source.with_name('ct_vfdsu_srt.v')
    need(digest(source_parent) == srcpins[str(source_parent)], 'Parent connection source drift')
    pins[str(source_parent)] = digest(source_parent)
    pins[str(Path(__file__).resolve())] = digest(__file__)
    test = Path(__file__).with_name('test_review_srt_radix16_child_residual.py')
    pins[str(test)] = digest(test)
    return dict(schema='SRT_RADIX16_CHILD_RESIDUAL_SOURCE_REVIEW_762_V1',
        status='NO_DISJOINT_NEW_ARITHMETIC_TARGETS_EXISTING1264_ALREADY_CHILD', baseline=762,
        task_premise_correction='c910_srt_datapath_native.py approved1264 is already radix16 child, not ct_vfdsu_srt parent. Another sealed additional8 capture covers the other vector subslots.',
        frozen_source=dict(path=str(source), sha256=digest(source), upstream_commit=UPSTREAM,
                           upstream_bytes_equal=True, compiled_file=filenode.attrib),
        compiled_module=mod.attrib, toggle_definition=defs[0].attrib,
        exact_local_shape_objects=210, existing_arithmetic_fields_per_instance=158,
        retained_local_fields_per_vector_instance=52, existing_vector_instances=16,
        held_scalar_instances=scalar, arithmetic_fields=approved, protected_local_shape=protected,
        existing_native_captures=capture_records, evidence=evidence,
        evidence_limit='Representative FP32/FP64 DIV/SQRT exact writes; not exhaustive IEEE/flags/rounding verification or proof that scalar executes the same approved integration. No new FP16 approval is inferred here.',
        source_rationale=dict(arithmetic='Existing selected 158 whole nonport vectors are remainder/quotient data, shifted/multiple operands and add/sub candidates. Reused only as an existing qualification, not selected from zero-hit bits.',
            protected='All ports, reset/clocks, DIV/SQRT mode, sign, round, bound selector/comparisons, digit bounds, part_rem and root-step position registers remain protected; all bound-table and gated-clock descendants remain protected.',
            selection_boundary='case(bound_cmp_sign) selects existing numerical candidate results; digit/sign/control inputs and boundary table remain covered. No new selection-control waiver.',
            lines=dict(registers=[294,395], boundary_selection=[411,516], arithmetic=[519,859], quotient_selection=[861,1030], remainder_selection=[1032,1148])),
        latest_raw_scope_records=records, protected_descendant_instances=descendants,
        exact_successor_targets=[], exact_successor_target_count=0,
        successor_protection_complement=dict(local_scope_fields=[dict(scope=s, names=[native_name(n) for n in nodes]) for s in scopes],
            descendants=descendants, policy='Every native object is non-target for this successor; existing sealed exclusions remain untouched. All other design scopes/metrics retained.'),
        estimated_new_missing_directions=0,
        existing_qualified_arithmetic_raw_missing_directions=sum(r['already_qualified_arithmetic_missing'] for r in records),
        retained_raw_missing_directions=sum(r['retained_missing'] for r in records),
        all_local_raw_missing_directions=sum(r['missing_directions'] for r in records),
        raw_direction_semantics='Exact serialized zeros in cached741 OR pinned21 suffix (762 total); shape-order local objects, ascending bit pairs for right0. Pair-slot direction labels not inferred; not official DVE score denominators. No parent/child aggregated rows added.',
        historical_cache_rehashed=False, historical_cache_contract='Consume pinned sealed741 OR and verify exact ledger prefix; 741 historical input pins are not individually re-audited in this task.',
        suffix_native_files_verified=len(suffix_pins), native_preparation_justified=False,
        no_module_waiver=True, no_interfaces_reset_flags_control_excluded=True,
        native_qualification_started=False, RTL_modified=False, sealed_files_modified=False,
        official_percentage_recomputed=False, population_modified=False, pins=pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    need(args.output.absolute().parent == OUT and not args.output.exists(), 'Fresh independent JSON required')
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output), sha256=digest(args.output), status=result['status'],
        new_missing_directions=0, existing_arithmetic_missing=result['existing_qualified_arithmetic_raw_missing_directions'],
        retained_missing=result['retained_raw_missing_directions'])))
