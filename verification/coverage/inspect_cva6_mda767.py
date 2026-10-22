"""Bind native MDA dimensions and preserve interval codes without guessing them."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import targeted_toggle_evidence_v2 as t
import rank_cva6_scalar_data767 as rank

PREFIX = rank.PREFIX + '.issue_stage_i.'
SCOPES = [PREFIX + 'i_issue_read_operands', PREFIX + 'i_scoreboard',
          PREFIX + 'i_issue_read_operands.gen_asic_regfile.i_ariane_regfile']
RANK = rank.OUT / 'cva6-scalar-data-ranking767-agent-20261007-02.json'
RANK_SHA = 'a4a3f44a9c65193ca356fa81a0f724a8a71c1787a795d42d7cc51668c8c2a4be'


def dimensions(node):
    result, size = [], 1
    for key in ('packedrange', 'unpackedrange'):
        values = [int(x) for x in node.get(key, '').split()]
        t.require(len(values) % 2 == 0, 'Malformed array dimensions')
        for left, right in zip(values[::2], values[1::2]):
            result.append(dict(kind=key, left=left, right=right))
            size *= abs(left - right) + 1
    t.require(result, 'Array without dimensions')
    return result, size


def intervals(value):
    tokens = [int(x) for x in value.split()]
    t.require(tokens and tokens[-1] == -1, 'Unterminated intervals')
    groups, triples = [], []
    for token in tokens:
        if token != -1:
            triples.append(token)
            continue
        t.require(triples and len(triples) % 3 == 0, 'Incomplete interval triples')
        runs, end = [], 0
        for start, count, code in zip(triples[::3], triples[1::3], triples[2::3]):
            t.require(start == end and count > 0 and code >= 0, 'Overlapping/gapped/invalid native interval')
            runs.append(dict(start=start, count=count, raw_code=code)); end += count
        groups.append(dict(extent=end, raw_runs=runs,
                           raw_code_counts=dict(Counter({code: sum(r['count'] for r in runs if r['raw_code'] == code)
                                                         for code in {r['raw_code'] for r in runs}}))))
        triples = []
    return groups


def collect():
    pins = {}
    def checked(p, sha):
        t.require(t.digest(p) == sha, 'Frozen evidence drift: ' + str(p))
        pins[str(p)] = sha
        return p.read_bytes()
    ranking = json.loads(checked(RANK, RANK_SHA))
    manifest = json.loads(checked(rank.BASE / 'admission-manifest.json', rank.SEAL))
    ledger = rank.BASE / 'combined-inputs.txt'
    inputs = checked(ledger, manifest['output_pins'][str(ledger)]).decode().splitlines()
    t.require(len(inputs) == len(set(inputs)) == 768, 'Exact formal767 required')
    db = Path(inputs[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for p in paths:
        checked(p, manifest['input_pins'][str(p)])
    design, info, shape = [t.xml(p) for p in paths]
    checks, defs = t.definitions(design, info, shape, SCOPES[:2])
    check = [n for n in info.iter('instance_data') if n.get('name') == SCOPES[2]]
    t.require(len(check) == 1 and check[0].get('chksum') == '3675723707', 'Exact GPR checksum')
    matches = [n for n in shape.findall('tgldef') if n.get('chksum') == '3675723707' and
               n.get('name', '').split(' (')[0] == 'ariane_regfile']
    t.require(len(matches) == 1, 'Ambiguous merged GPR shape')
    checks[SCOPES[2]] = '3675723707'
    defs[SCOPES[2]] = dict(shape=ET.tostring(matches[0], encoding='unicode'))
    data = list((Path(inputs[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    t.require(len(data) == 1, 'One sealed sample required')
    checked(data[0], manifest['input_pins'][str(data[0])])
    root = t.xml(data[0]); samples = []
    for scope in SCOPES:
        nodes = [n for n in root.iter('instance_intervaldata') if n.get('name') == scope]
        t.require(len(nodes) == 1 and nodes[0].get('chksum') == checks[scope], 'Exact native interval identity')
        groups = intervals(nodes[0].get('value', ''))
        arrays = []
        for node in ET.fromstring(defs[scope]['shape']).find('tglshape'):
            if node.tag != 'arrays': continue
            dims, extent = dimensions(node)
            arrays.append(dict(node.attrib, dimensions=dims, extent=extent,
                               same_extent_groups=[i for i, g in enumerate(groups) if g['extent'] == extent]))
        t.require(len(groups) == len(arrays), 'Array/group population differs')
        samples.append(dict(scope=scope, checksum=checks[scope], arrays=arrays, interval_groups=groups,
                            group_order_to_signal_not_assumed=True))
    example = next(a for a in samples[-1]['arrays'] if a['name'] == 'mem')
    t.require(example['packedrange'].split() == ['31', '0', '63', '0'] and
              example['extent'] == 2048 and len(example['same_extent_groups']) == 1,
              'Exact unique2048 GPR mem extent required')
    reports = []
    for population, qdir, reportdir in (
        (765, 'native-batch-full765-agent-20261007-02', 'native-batch-full765-agent-20261007-02'),
        (766, 'native-batch-full766-offline-closure-parent-review-01', 'native-batch-full766-agent-20261007-01')):
        qpath = rank.OUT / qdir / 'qualification.json'; qsha = t.digest(qpath)
        q = json.loads(checked(qpath, qsha))
        t.require(q['status'] == 'SEALED_POPULATION_CANONICAL_NATIVE_UNION_REPORT_VERIFIED', 'Not qualified report')
        csvpath = rank.OUT / reportdir / 'summary.csv.partial'
        checked(csvpath, q['output_pins'][str(csvpath)])
        rows = list(csv.DictReader(csvpath.open()))
        stack, values = [], {}
        for row in rows:
            depth = int(row['Depth'])
            t.require(depth <= len(stack), 'Report depth jump')
            stack = stack[:depth] + [row['Name']]
            scope = '.'.join(stack)
            if scope in SCOPES:
                t.require(scope not in values, 'Duplicate report scope')
                values[scope] = row
        t.require(set(values) == set(SCOPES), 'Missing canonical MDA report scope')
        reports.append(dict(population=population, qualifier_sha256=qsha, rows=values,
                            stage='Saved hierarchy export, not newly rooted detail'))
    for p, sha in ranking['source_bindings'].items():
        checked(Path(sha['path']), sha['sha256'])
    for p in (Path(__file__), Path(__file__).with_name('test_inspect_cva6_mda767.py'),
              Path(__file__).with_name('probe_cva6_mda_readonly.tcl')):
        pins[str(p)] = t.digest(p)
    for p, sha in pins.items(): t.require(t.digest(p) == sha, 'End-of-read drift')
    fixed = [dict(scope=s['scope'], checksum=s['checksum'], object=n) for s in ranking['scopes']
             for n in s['data_objects'] if '.i_store_unit' in s['scope'] and n['name'] == 'req_port_i.data_rdata']
    t.require(len(fixed) == 2 and sum(n['object']['missing_slots'] for n in fixed) == 256, 'Exact two fixed objects')
    return dict(schema='CVA6_MDA767_STRUCTURAL_AND_NATIVE_REPORT_DIAGNOSTIC_V1', input_pins=pins,
        formal_population=767, sample_vdb=inputs[-1], samples=samples, unique_large_array_example=example,
        reports=reports, physical_missing_bits_not_yet_qualified=True,
        interval_code_semantics='Raw start/count/code groups only; no OR, flatten order, native directions or initial-X meaning inferred',
        read_only_probe_required=['Native mem row/bit labels with Toggle columns',
            'Raw code0/4/14 anchor to native coverage statuses on same singleton',
            'Then exact767 merged detail of mem and fwd_res, retaining x0/control/address constraints'],
        EDA_launched=False), dict(schema='STORE_READ_RETURN256_STATIC_CANDIDATES_NOT_APPROVED',
            baseline=767, source_bindings=ranking['source_bindings'], targets=fixed,
            producer=ranking['fixed_read_return_evidence'], initial_X_waiver=False,
            native_qualification=False, waiver_approved=False, EL_generated=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixed-output', type=Path, required=True)
    args = parser.parse_args()
    t.require(not args.output.exists() and not args.fixed_output.exists(), 'Fresh outputs required')
    report, fixed = collect()
    fixed['input_pins'] = report['input_pins']
    for p, obj in ((args.output, report), (args.fixed_output, fixed)):
        with p.open('x') as stream: json.dump(obj, stream, indent=2); stream.write('\n')
        print(p, t.digest(p))
