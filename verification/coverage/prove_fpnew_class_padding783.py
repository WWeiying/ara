"""Source/compiled partial-bit candidates only; no EL, DVE or application."""
import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import prove_fpnew_tied_fields781 as prior

m, rank = prior.m, prior.rank
BASE = m.OUT / 'qbs-k2-pending-offline-admitted783-agent-20261008-01'
BASE_SHA = '8d0d58bf873e0b0f4c601d1e9fb88fca74babb572f822a0580967eef9e5d23f0'
POLICY_SHA = '8a501ebe03d577ff93a84096baa63ca1d88eb0e30fb248499e5bcd60fb63fd73'
FIELDS = ('slice_vec_class_result', 'slice_class_result')


def bound_definition(module, checksum, shape):
    m.need(module.get('name') == 'fpnew_opgroup_fmt_slice', 'Foreign compiled module')
    matches = [d for d in shape.findall('tgldef') if d.get('chksum') == checksum and
               d.get('id') == module.get('id') and d.get('name').split(' (')[0] == module.get('name')]
    m.need(len(matches) == 1, 'Ambiguous/missing compiled parameter variant')
    return matches[0]


def zero_bits(p, field):
    m.need(field in FIELDS, 'Unknown field')
    width, fmt, vec, true = (p[k] for k in ('Width', 'FpFormat', 'EnableVectors', 'TrueSIMDClass'))
    m.need(width in (32, 64) and fmt in (0, 1, 2) and vec in (0, 1) and true in (0, 1),
           'Unreviewed geometry/format')
    fp = (32, 64, 16)[fmt]
    lanes = width // fp if vec else 1
    m.need(lanes > 0 and width % lanes == 0, 'Invalid lane geometry')
    slot = width // lanes
    m.need(all(p[k] == v for k, v in dict(NUM_LANES=lanes, FP_WIDTH=fp,
           SIMD_WIDTH=slot, CLASS_VEC_BITS=min(lanes * 8, width)).items()), 'Compiled derived geometry')
    active = {lane * slot + bit for lane in range(lanes) for bit in range(10)} if true and slot >= 10 else set(range(min(lanes * 8, width)))
    if field == 'slice_class_result':
        active |= set(range(10))  # Union of BOTH mux arms, regardless of current vtype.
    return set(range(width)) - active


def source_guard(text, pkg):
    compact = re.sub(r'\s+', '', re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S))
    required = [
        "if(TrueSIMDClass&&SIMD_WIDTH>=10)",
        'assignslice_vec_class_result[lane*SIMD_WIDTH+:10]=lane_class_mask[lane];',
        "assignslice_vec_class_result[(lane+1)*SIMD_WIDTH-1-:SIMD_WIDTH-10]='0;",
        'elseif((lane+1)*8<=Width)',
        'assignslice_vec_class_result[(lane+1)*8-1:lane*8]={',
        'if(!(TrueSIMDClass&&SIMD_WIDTH>=10))',
        'if(CLASS_VEC_BITS<Width)',
        "assignslice_vec_class_result[Width-1:CLASS_VEC_BITS]='0;",
        'assignslice_class_result=result_is_vector?slice_vec_class_result:lane_class_mask[0];',
        'localparamintunsignedSIMD_WIDTH=unsigned\'(Width/NUM_LANES);',
        'localparamintunsignedCLASS_VEC_BITS=(NUM_LANES*8>Width)?8*(Width/8):NUM_LANES*8;']
    m.need(all(token in compact for token in required), 'Classification driver semantics changed')
    m.need(len(re.findall(r'assignslice_vec_class_result\[', compact)) == 4 and
           compact.count('assignslice_class_result=') == 1, 'Unexpected additional driver')
    m.need('typedef enum logic [9:0]' in pkg and
           'return vec ? width / fp_width(fmt) : 1;' in pkg and
           "'{8,  23}" in pkg and "'{11, 52}" in pkg and "'{5,  10}" in pkg,
           'Class width/format/lane function changed')


def collect():
    pins = {}
    def read(path, sha):
        path = Path(path)
        m.need(m.digest(path) == sha, 'Sealed input drift: ' + str(path))
        pins[str(path)] = sha
        return path.read_bytes()
    a = json.loads(read(BASE/'admission-manifest.json', BASE_SHA))
    m.need(a['coverage_admitted'] is True, 'Formal783 required')
    ledger = read(BASE/'combined-inputs.txt', a['output_pins'][str(BASE/'combined-inputs.txt')]).decode().splitlines()
    m.need(len(ledger) == len(set(ledger)) == 784, 'Exact783 membership')
    book = json.loads(read(prior.BOOK, prior.BOOK_SHA))
    rels = ['hardware/deps/fpnew/src/fpnew_opgroup_fmt_slice.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv']
    texts = [read(m.ROOT/r, book[str(m.ROOT/r)]).decode() for r in rels]
    source_guard(*texts)
    db = Path(ledger[0])/'snps/coverage/db'
    paths = [db/'design/verilog.design.xml', db/'shape/tgl.verilog.info.xml', db/'shape/tgl.verilog.shape.xml']
    for p in paths:
        read(p, a['input_pins'][str(p)])
    design, info, shape = (m.xml(p) for p in paths)
    nodes = {n.get('id'): (n, d) for d in design.findall('srcdef') for n in d.findall('srcinst')}
    def scope(k):
        n, _ = nodes[k]
        return (scope(n.get('pid'))+'.' if n.get('pid') in nodes else '')+n.get('name')
    modules = {scope(k): d for k, (_, d) in nodes.items()}
    scopes = [s for s, d in modules.items() if d.get('name').split(' (')[0] == 'fpnew_opgroup_fmt_slice'
              and s.startswith('ara_tb.dut.i_ara_soc.i_system.')]
    checks = {}
    for n in info.iter('instance_data'):
        if n.get('name') in scopes:
            m.need(n.get('name') not in checks and n.get('chksum') is not None, 'Unique native info')
            checks[n.get('name')] = n.get('chksum')
    m.need(set(checks) == set(scopes), 'Complete scope/info binding')
    cache = json.loads(read(rank.old.CACHE, rank.old.CACHE_SHA))
    prefix = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    m.need(ledger[:742] == read(prefix, cache['input_pins'][str(prefix)]).decode().splitlines(), 'Exact741 cached prefix')
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for vdb in ledger[742:]:
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        m.need(len(files) == 1, 'Unique Toggle sample')
        read(files[0], a['input_pins'][str(files[0])])
        rows, _ = rank.t.rows(files[0], set(scopes))
        union = rank.t.union(union, rows)
    pc = json.loads(read(rank.POLICY/'config.json', POLICY_SHA))
    ep = rank.POLICY/'combined.el'
    entries, whole = rank.old.el_fields(read(ep, pc['pins'][str(ep)]).decode())
    candidates, hold = [], []
    for s in scopes:
        d = bound_definition(modules[s], checks[s], shape)
        params = {k: int(v) for k, v in re.findall(r'\b(\w+)=(\d+)', d.get('name'))}
        row = union[s]
        m.need(row['checksum'] == checks[s], 'Native/compiled checksum')
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        offset = 0
        objects = []
        targets = []
        for n in d.find('tglshape'):
            if n.tag == 'arrays':
                objects.append(dict(kind=n.tag, attributes=dict(n.attrib), protected=True))
                continue
            m.need(n.tag in ('node', 'vectornode'), 'Unknown typed object')
            width = 1 if n.tag == 'node' else abs(int(n.get('left'))-int(n.get('right')))+1
            objects.append(dict(kind=n.tag, attributes=dict(n.attrib), raw_range=[offset, offset+2*width]))
            if n.get('name') in FIELDS:
                m.need(n.tag == 'vectornode' and n.get('left') == str(params['Width']-1) and
                       n.get('right') == '0' and n.get('portnode') == '0', 'Exact internal descending field')
                targets.append((n, offset, zero_bits(params, n.get('name'))))
            offset += 2*width
        m.need(offset == row['width'] and len(targets) == 2, 'Complete typed binding')
        for n, start, zeros in targets:
            field = n.get('name'); legal = set(range(params['Width']))
            removed, ambiguous = rank.old.excluded_bits(entries.get((s, field), []), legal)
            if ambiguous or any(s == w or s.startswith(w+'.') for w in whole) or any(
                    owner == s and field.startswith(name+'.') for owner, name in entries):
                hold.append(dict(scope=s, field=field, reason='EL_OWNER_AMBIGUOUS')); continue
            bits = zeros - removed
            # Existing bit0 native evidence uses low logical bit first, not declaration order.
            # Both members are selected; their direction labels remain unclaimed.
            coordinates = sorted(start+2*bit+direction for bit in bits for direction in (0, 1))
            m.need(all(binary[i] == '0' for i in coordinates), 'Source-proven zero contradicts actual hit')
            if bits:
                candidates.append(dict(scope=s, field=field, module_checksum=modules[s].get('chksum'),
                    toggle_checksum=checks[s], definition=dict(d.attrib), parameters=params,
                    attributes=dict(n.attrib), logical_bits=sorted(bits), protected_bits=sorted(legal-bits),
                    raw_coordinates=coordinates, preexisting_excluded_bits=sorted(removed),
                    constant_hex='0x0', full_typed_inventory=objects,
                    protection='All other objects including arrays; target complement protected_bits'))
    for p, sha in pins.items():
        m.need(m.digest(p) == sha, 'Read-end drift: '+p)
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_prove_fpnew_class_padding783.py')):
        pins[str(p)] = m.digest(p)
    for module in (prior, m, rank, rank.old, rank.t, rank.t.base):
        p = Path(module.__file__).resolve(); pins[str(p)] = m.digest(p)
    return dict(schema='FPNEW_CLASS_PADDING783_STATIC_V1', population=783, baseline781_policy_only=True,
        status='SOURCE_COMPILED_CANDIDATES_NOT_NATIVE_APPROVED', candidates=candidates, hold=hold,
        candidate_objects=len(candidates), candidate_bits=sum(len(c['logical_bits']) for c in candidates),
        candidate_directions=sum(len(c['raw_coordinates']) for c in candidates), pins=pins,
        proof='Per compiled format, vector/scalar mux union; never current-vtype width. Padding only.',
        serialized_rule='Low logical bit first, two positions per bit; direction order not inferred. Local native binding pending.',
        startup_X_not_excluded=True, EDA_started=False, EL_generated=False, applied=False,
        official_denominator=None, predicted_percentage_gain=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    m.need(out.parent == m.OUT and not out.exists(), 'Fresh own output only')
    result = collect()
    with out.open('x') as stream:
        json.dump(result, stream, separators=(',', ':')); stream.write('\n')
    print(json.dumps(dict(output=str(out), sha256=m.digest(out), objects=result['candidate_objects'],
                          bits=result['candidate_bits'], directions=result['candidate_directions'])))
