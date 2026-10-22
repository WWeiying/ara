"""Read-only frozen-source candidate packet; no EL generation or EDA."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import targeted_toggle_evidence_v2 as native
import rank_cva6_scalar_data767 as typed
import report_global777_compact as policy

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
REPORT = OUT / 'current-population797-inherited796-agent-20261008-01'
ADMITTED = OUT / 'vsmul-saturation-offline-admitted797-parent-20261008-01'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ariane_axi_dwc.gen_dw_upsize.i_axi_dw_upsizer'
VALUE = 0xCA11AB1EBADCAB1E
TARGETS = [
    ('', 'axi_err_resp.r.data', False),
    ('.i_axi_demux', 'mst_resps_i[1].r.data', False),
    ('.i_axi_demux.i_demux_simple', 'mst_resps_i[1].r.data', False),
    ('.i_axi_err_slv', 'err_resp.r.data', True),
    ('.i_axi_err_slv', 'slv_resp_o.r.data', False),
    ('.i_axi_err_slv.genblk1.i_atop_filter', 'mst_resp_i.r.data', True),
    ('.i_axi_err_slv.genblk1.i_atop_filter', 'slv_resp_o.r.data', False),
]


def need(condition, message):
    if not condition:
        raise ValueError(message)


def constant_bits(direct, value=VALUE, width=128):
    need(width == 128 and 0 <= value < 2**64, 'Exact unsigned64 to128 contract')
    return [b for b in range(width) if direct or not (value >> b & 1)]


def coordinates(node, bits):
    need(node['left'] == '127' and node['right'] == '0'
         and node['logical_width'] == 128, 'Exact packed128 field')
    return [node['serialized_offset'] + 2*b + slot for b in bits for slot in (0, 1)]


def zero_pairs(row, positions):
    raw = int(row['bits'], 16)
    need(all(0 <= p < row['width'] for p in positions), 'Serialized bounds')
    need(all(not (raw >> (row['width'] - 1 - p) & 1) for p in positions),
         'Full797 constant-pair zero')


def overlap(scope, name, bits, other, masks):
    ancestors = {scope[:i] for i, c in enumerate(scope) if c == '.'} | {scope}
    need(not any(r[0] in ancestors and r[3] == 'WHOLE_SCOPE' for r in other),
         'Ancestor whole-scope exclusion')
    need(not any(r[0] == scope and r[3].startswith('Toggle ') for r in other),
         'Opaque Toggle policy requires manual HOLD')
    directions = {'0to1': set(), '1to0': set()}
    for (s, checks, n, kind, decl, prefix, direction), mask in masks.items():
        if s == scope and n == name:
            need(not prefix, 'Unexpected multidimensional selector')
            directions[direction].update(b for b in bits if mask >> b & 1)
    need(not any(directions.values()), 'Existing EL overlaps candidate')
    return {d: sorted(v) for d, v in directions.items()}


def collect():
    pins = {}

    def bound(path, seal):
        data = path.read_bytes()
        need(hashlib.sha256(data).hexdigest() == seal, 'Frozen hash: ' + str(path))
        pins[str(path)] = seal
        return data

    q = json.loads(bound(REPORT / 'qualification.json',
        '1ebc05103bc71ee6ec26d97e51ed4867fed3d35a21ee38490956c3ccadf2c5c6'))
    need(q['population'] == q['actual_selected_tests'] == 797 and
         q['status'] == 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED', 'Qualified797')
    manifest = json.loads(bound(ADMITTED / 'admission-manifest.json',
        '775485fa0a5cfbb8bb1715374e60d3228d341522b2df3c666754407b30ef55f4'))
    bitmap = ADMITTED / 'combined-toggle-bits.json'
    rows = json.loads(bound(bitmap, manifest['output_pins'][str(bitmap)]))
    book_path = BUILD / 'build-source-pins.json'
    book = json.loads(bound(book_path, '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'))
    sources = {}
    for filename in ('axi_err_slv', 'axi_atop_filter', 'axi_dw_upsizer', 'axi_demux', 'axi_demux_simple'):
        path = ROOT / ('hardware/deps/axi/src/' + filename + '.sv')
        sources[filename] = bound(path, book[str(path)]).decode()
    soc = ROOT / 'hardware/src/ara_soc.sv'
    bound(soc, book[str(soc)])
    db = BUILD / 'sim/simv.vdb/snps/coverage/db'
    shape_path = db / 'shape/tgl.verilog.shape.xml'
    bound(shape_path, '243ae4d4d29b7ee2190ef35a39482f7287c78a260128315b666d500e90f18ae7')
    sourceinfo = db / 'auxiliary/verilog.sourceinfo.xml'
    bound(sourceinfo, 'bc80d4a5580cca6b8a48f6e773074b1287a6c365906f951a94dcdc1aa57041f3')
    files = {n.get('id'): n.get('name') for n in native.xml(sourceinfo).findall('fileinfo')}
    definitions = {}
    for d in native.xml(shape_path).findall('tgldef'):
        definitions.setdefault(d.get('chksum'), []).append(d)
    el = bound(REPORT / 'combined.el', '2704de24f115e289d8c1e60c3847dc39d7f7d13e955eb284ddc66f6fd42596c9')
    other, masks = policy.semantic(el.decode('ascii'))
    targets = []
    for suffix, name, direct in TARGETS:
        scope = PREFIX + suffix
        row = rows[scope]
        defs = definitions[row['checksum']]
        need(len(defs) == 1, 'Unique compiled definition')
        definition = defs[0]
        nodes, arrays = typed.typed_nodes(ET.tostring(definition, encoding='unicode'), row)
        matches = [n for n in nodes if n['name'] == name]
        need(len(matches) == 1, 'Unique exact field; array index preserved')
        node = matches[0]
        source_file = files[node['aux_file']]
        need(source_file in pins, 'Compiled auxiliary declaration source bound')
        bits = constant_bits(direct)
        positions = coordinates(node, bits)
        zero_pairs(row, positions)
        need(set(positions) <= set(node['missing_coordinates']), 'Typed residual membership')
        targets.append(dict(scope=scope, name=name, checksum=row['checksum'],
            compiled_definition=definition.attrib, direct_constant=direct,
            declaration_source=source_file, declaration_line=node['aux_line_num'],
            constant_value=hex(VALUE) if direct else '0 on selected bits only',
            constant_bits=bits, protected_data_bits=sorted(set(range(128))-set(bits)),
            unnamed_pair_coordinates=positions, candidate_slots=len(positions),
            EL_overlap=overlap(scope, name, bits, other, masks), full797_pairs_zero=True))
    err_definition = next(t['compiled_definition']['name'] for t in targets if t['name'] == 'err_resp.r.data')
    need('RespWidth=64' in err_definition and 'ATOPs=1' in err_definition, 'Compiled default shape')
    need("RespData    = 64'hCA11AB1EBADCAB1E" in sources['axi_err_slv'], 'Reviewed default constant')
    return dict(status='SOURCE_REVIEWED_CONSTANT_CANDIDATES_NOT_QUALIFIED_EL', population=797,
        pins=pins, targets=targets, candidate_slots=sum(t['candidate_slots'] for t in targets),
        protected_controls='ALL valid/id/last/resp/ready and every non-r.data field',
        source_proof=[
            'axi_err_slv:24-26 unsigned logic64 default; upsizer:185-189 does not override RespWidth/RespData/ATOPs.',
            'Compiled name explicitly records RespWidth64/ATOPs1; RespData is omitted in name, not numerically decoded. Default value is bound via frozen source and instantiation.',
            "axi_err_slv:194-197 unconditional r='0' then r.data=RespData; all other r writers target id/resp/last only. Reset changes control, not data.",
            'axi_err_slv:45-57 generated ATOP filter connects err_resp to mst_resp_i and sole external slv_resp_o writer.',
            "axi_atop_filter:260 passthrough;287 inject r='0';288-290 only id/resp/last overrides. Data value set is {RespData,0}; low64 one bits remain protected even if raw797 observed no toggles.",
            'upsizer:195 sole err_slave output drives axi_err_resp;226 packed {axi_err_resp,mst_resp_i} makes index1 error response, not normal memory data.',
            'demux:208 passes mst_resps_i unchanged to simple demux. Candidates are input aliases only, not the selected/muxed slv_resp_o.',
            'Frozen source files were manually read for all whole-response, whole-r and r.data writers. Exact file hashes guard that review; this is not a general SV reachability parser.'
        ], EDA_started=False, RTL_changed=False, EL_generated=False, applied=False,
        official_denominator=None, measured_gain=None,
        limitations=['Capacity counts repeated instrumented aliases, not unique physical bits or official DVE denominator.',
                     'Pair slots are unnamed; no native direction-ID order inferred. Both 0to1 and 1to0 require explicit selectors in any future parent-authorized local EL.',
                     'No new waiver or local EDA qualification; native selector/display checks remain pending.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    packet = collect()
    with args.output.open('x') as stream:
        stream.write(json.dumps(packet, indent=2) + '\n')
    print(json.dumps(dict(output=str(args.output), sha256=native.digest(args.output),
                          candidate_slots=packet['candidate_slots'])))
