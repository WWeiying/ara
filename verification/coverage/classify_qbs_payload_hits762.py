"""Finite mapping overapproximation of exact payload hit bits; no EL or EDA."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import prepare_qbs_payload_side1792_732 as old

ROOT = old.ROOT
STATIC = ROOT / 'verification/out/qbs-payload-data-toggle-static762-agent-20261007-01.json'
CACHE = ROOT / 'verification/out/toggle741-capacity-ranking-agent-20261007-01.json'
SIZES = (144, 176, 210, 110, 34, 18, 84, 22, 18)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def weight_location(profile, offset):
    require(type(profile) is int and 1 <= profile <= 9 and
            type(offset) is int and 0 <= offset < SIZES[profile-1], 'Weight domain')
    p, o = 2, offset
    if profile == 1 and offset >= 16: p, o = 0, offset-16
    elif profile == 2:
        if offset >= 48: p, o = 0, offset-48
        elif offset >= 16: p, o = 1, offset-16
    elif profile == 3:
        if offset < 128: p = 0
        elif offset < 192: p, o = 1, offset-128
        else: o = offset-192
    elif profile == 4:
        if offset < 32: p = 1
        elif offset < 96: p, o = 0, offset-32
        else: o = offset-96
    elif profile == 7:
        if offset >= 80: o = offset-64
        elif offset >= 16: p, o = 0, offset-16
    elif profile == 8 and offset >= 6: p, o = 0, offset-6
    elif profile in (5, 6, 9) and offset >= 2: p, o = 0, offset-2
    return p, o & 255


def activation_target(index, contexts, scale, quants):
    size = scale + quants + (32 if quants == 256 else 0)
    require(contexts in (1, 4, 8) and 0 <= index < contexts*size, 'Activation domain')
    if contexts == 1:
        return 0, index
    if index < contexts*scale:
        return divmod(index, scale)
    relative = index-contexts*scale
    if relative < contexts*quants:
        return relative % contexts, scale+relative//contexts
    relative -= contexts*quants
    return (relative//2) % contexts, scale+quants+(relative//(2*contexts))*2+relative % 2


def activation_location(offset, scale, quants):
    if offset >= scale+quants: return 2, (offset-quants) & 255
    if offset >= scale: return 0, (offset-scale) & 255
    return 2, offset & 255


def possible_hits(bank):
    """Superset: arbitrary legal beat start, row count, strb, and selected word.

    Every pending byte retains its original writer index/target/location. Dropping
    drain and arbitration constraints only enlarges this set, so absence is a
    necessary mapping impossibility, not a timing assumption.
    """
    possible, witnesses = set(), {}

    def add(kind, row, plane, lane, writer, witness):
        key = kind, row, plane, lane, writer
        possible.add(key)
        witnesses.setdefault(key, witness)

    for profile, size in enumerate(SIZES, 1):
        for grouped in (False, True):
            for start in range((4 if grouped else 1)*size):
                for writer in range(16):
                    source = start+writer
                    row, offset = divmod(source, size) if grouped else (0, source)
                    if row >= 4 or offset >= size: continue
                    plane, destination = weight_location(profile, offset)
                    rows = (row,) if grouped else range(4)
                    for r in rows:
                        # Both banks have local four-row weight windows.
                        lane = destination % (16 if plane != 2 else 20)
                        add('weight', r, plane, lane, writer,
                            dict(profile=profile, grouped=grouped, start=start,
                                 row=r, block_offset=offset, destination=destination))
    for scale, quants in ((4, 256), (2, 32)):
        size = scale+quants+(32 if quants == 256 else 0)
        for contexts in (1, 4, 8):
            for start in range(contexts*size):
                for writer in range(16):
                    source = start+writer
                    if source >= contexts*size: continue
                    ctx, offset = activation_target(source, contexts, scale, quants)
                    # Row-major context is explicitly carried by the request.
                    ctxs = range(4) if contexts == 1 else (ctx,)
                    for c in ctxs:
                        base = 4*bank
                        if contexts == 1: local = c
                        elif base <= c < base+4: local = c-base
                        else: continue
                        plane, destination = activation_location(offset, scale, quants)
                        lane = destination % 32 if plane == 0 else destination
                        if plane == 2 and lane >= 36: continue
                        add('activation', local, plane, lane, writer,
                            dict(scale=scale, quants=quants, contexts=contexts,
                                 start=start, context=c, block_offset=offset,
                                 destination=destination))
    return possible, witnesses


def identity(name, bit):
    m = re.fullmatch(r'gen_write_merge\[([01])\]\.gen_bank_plane\[([0-2])\]'
                     r'\.gen_bank_row\[([0-3])\]\.gen_byte_merge\[([0-9]+)\]\.hit', name)
    if m:
        slot, plane, row, lane = map(int, m.groups())
        require(0 <= bit < 16 and lane < (32 if plane == 2 else 16), 'Main hit range')
        return ('activation' if plane == 2 else 'weight', row,
                0 if plane == 2 else plane, lane, bit), slot, False
    m = re.fullmatch(r'gen_side_row\[([0-3])\]\.gen_(weight|activation)_byte\[([0-9]+)\]\.hit', name)
    require(m is not None and 0 <= bit < 32, 'Unknown hit shape')
    row, kind, lane = m.groups()
    require(int(lane) < (20 if kind == 'weight' else 36), 'Side hit lane')
    return (kind, int(row), 2, int(lane), bit % 16), bit//16, True


def classify(name, bit, possible, witnesses):
    key, slot, side = identity(name, bit)
    if side and slot == 0:
        return 'OLD1792_INVARIANT_PROJECTION', None
    if key not in possible:
        return 'FINITE_MAPPING_IMPOSSIBLE_CANDIDATE', None
    if slot == 0:
        return 'HOLD_PENDING_DRAIN_OWNERSHIP', witnesses[key]
    return 'MAPPING_FEASIBLE_HOLD_PRODUCER_ARBITRATION', witnesses[key]


def build_report():
    evidence = json.loads(STATIC.read_bytes())
    require(evidence['baseline'] == 762 and evidence['cache_prefix_verified'], 'Baseline')
    pins = dict(evidence['pins'])
    # Consume only the scoped source/shape/suffix pins; historical cache is
    # explicitly a sealed prior OR, not a fresh historical input re-audit.
    for path, sha in pins.items():
        require(digest(path) == sha, 'Changed scoped pin: '+path)
    cache = json.loads(CACHE.read_bytes())
    payload = ROOT/'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'
    adapter = payload.with_name('qbs_block_adapter.sv')
    engine = payload.with_name('qbs_compute_engine.sv')
    old.source_contract(adapter.read_text(), payload.read_text(), engine.read_text())
    induction = old.induction_check()
    # Bind finite function translations to the exact frozen package identity.
    package = ROOT/'hardware/include/qbs_pkg.sv'
    require(digest(package) == 'f64946527f9f88608a1ab6fdfb19f9854f932ca0a84fa27f4a1aa55cece5234d', 'Package translation drift')
    pins[str(Path(__file__).resolve())] = digest(__file__)
    for extra in (Path(__file__).with_name('test_classify_qbs_payload_hits762.py'), Path(old.__file__), STATIC):
        pins[str(extra)] = digest(extra)
    shape_path = next(Path(p) for p in pins if p.endswith('/shape/tgl.verilog.shape.xml'))
    root = ET.fromstring(gzip.open(shape_path, 'rb').read())
    defs = [x for x in root.iter('tgldef') if x.get('name') == 'qbs_payload_buffer']
    require(len(defs) == 1 and defs[0].get('chksum') == '3657545390', 'Definition')
    nodes = []
    offset = 0
    for node in defs[0].find('tglshape'):
        require(node.tag in ('node', 'vectornode'), 'Unknown serialized shape node')
        width = abs(int(node.get('left'))-int(node.get('right')))+1 if node.tag == 'vectornode' else 1
        nodes.append((node, offset, width))
        offset += 2*width
    require(offset == 66340, 'Full shape width')
    output = {}
    for scope, summary in evidence['scopes'].items():
        bank = int(re.search(r'bank([01])\.', scope)[1])
        bits = int(cache['instances'][scope]['bits'], 16)
        for path in pins:
            if not path.endswith('/tgl.verilog.data.xml'): continue
            tree = ET.fromstring(gzip.open(path, 'rb').read())
            matches = [x for x in tree.iter('instance_data') if x.get('name') == scope]
            require(len(matches) == 1, 'Missing/duplicate native scope')
            row = matches[0]
            value = row.get('value')
            require(row.get('chksum') == '3657545390' and len(value) == offset and set(value) <= {'0','1'}, 'Native data shape')
            bits |= int(value, 2)
        require(offset-bin(bits).count('1') == summary['raw762_missing'], 'Scoped union mismatch')
        possible, witnesses = possible_hits(bank)
        records, counts = [], Counter()
        for node, start, width in nodes:
            if not node.get('name').endswith('.hit'): continue
            require(node.tag == 'vectornode' and int(node.get('right')) == 0 and
                    width in (16,32) and node.get('line_num') in ('269','355','381'), 'Hit declaration layout')
            for bit in range(width):
                status, witness = classify(node.get('name'), bit, possible, witnesses)
                coords = [start+2*bit+d for d in (0,1)]
                missing = [c for c in coords if not bits >> (offset-1-c) & 1]
                if status.endswith('CANDIDATE') or status == 'OLD1792_INVARIANT_PROJECTION':
                    require(len(missing) == 2, 'Observed hit contradicts mapping/projection: '+node.get('name'))
                if not missing: continue
                counts[status] += len(missing)
                records.append(dict(signal=node.get('name'), declaration_line=node.get('line_num'),
                    left=width-1, right=0, bit=bit, raw_offset=start,
                    missing_serialized_coordinates=missing, classification=status,
                    mapping_witness=witness))
        require(sum(counts.values()) == summary['missing_by_field']['hit'], 'Missing hit accounting')
        output[scope] = dict(checksum='3657545390', raw_width=offset,
                            missing_directions_by_class=dict(counts), records=records)
    return dict(schema='QBS_HIT_FINITE_MAPPING_762_STATIC_REVIEW_V1', baseline=762,
        source_pins=pins, induction=induction, scopes=output,
        no_EDA=True, exclusions_approved=False,
        protected='ALL selected[8], byte_valid, BE, consumed, source_valid and observed hit directions; no EL emitted',
        layout='Compiled right=0 ascending bit pair positions; direction labels not inferred. Native bit-level qualification still required.',
        domain='All nine weight profiles; row-major/R4, all four local rows; both activation profiles, row-major/M4/M8, banks0/1, writers0..15. All beat starts, superset of ABI-aligned starts.',
        ABI='Weight base multiple2, activation base multiple4. No new constant proof relies on restricting beat starts to these residues; upstream split/drain may change start.',
        ownership='Pending retains writer and captured target/location; side-plane consumed immediately. Other pending feasibility HOLD until leftover mask/drain history proved.',
        limitations='Mapping witnesses are not architectural producer or cycle witnesses. Selection of a word/byte and dynamic profiles need native qualification. Cache741 reused, not whole historical chain rehashed.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = build_report()
    with args.output.open('x') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(path=str(args.output), sha256=digest(args.output),
        counts={s:r['missing_directions_by_class'] for s,r in record['scopes'].items()})))


if __name__ == '__main__': main()
