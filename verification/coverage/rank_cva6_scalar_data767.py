"""Exact formal767 scalar-data Toggle diagnostic, not native direction approval."""
import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import targeted_toggle_evidence_v2 as t

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'qbs-payload-residual4-offline-admitted-767-agent-20261007-01'
SEAL = 'a4dac6fb073fc665cb8f274557d04c8d2bf3ad9291a70bda03bcfdce3542b405'
CACHE = OUT / 'toggle741-capacity-ranking-agent-20261007-01.json'
CACHE_SHA = '8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865'
PREFIX = 'ara_tb.dut.i_ara_soc.i_system.i_ariane'
SUFFIXES = (
    '.ex_stage_i.alu_i', '.ex_stage_i.i_mult',
    '.ex_stage_i.i_mult.i_multiplier', '.ex_stage_i.i_mult.i_div',
    '.ex_stage_i.lsu_i.i_load_unit', '.ex_stage_i.lsu_i.i_store_unit',
    '.ex_stage_i.lsu_i.i_store_unit.store_buffer_i',
    '.issue_stage_i.i_issue_read_operands', '.issue_stage_i.i_scoreboard',
    '.issue_stage_i.i_issue_read_operands.gen_asic_regfile.i_ariane_regfile')
SOURCES = ('alu.sv', 'mult.sv', 'multiplier.sv', 'serdiv.sv', 'load_unit.sv',
           'store_unit.sv', 'store_buffer.sv', 'issue_read_operands.sv',
           'scoreboard.sv', 'ariane_regfile_ff.sv', 'load_store_unit.sv')
DATA_NAMES = {'operand_a_i', 'operand_b_i', 'result_o', 'mul_result', 'div_result',
              'mult_result_d', 'mult_result_q', 'operand_a', 'operand_b',
              'fu_data_i.operand_a', 'fu_data_i.operand_b', 'operand_a_rev',
              'operand_a_rev32', 'operand_b_neg', 'adder_result',
              'adder_result_ext_o', 'shift_operand', 'shift_right_result',
              'shift_result', 'lsu_ctrl_i.data', 'st_data_q', 'st_data_n',
              'req_port_i.data_rdata', 'req_port_o.data_wdata'}


def typed_nodes(shape, row):
    width = row['width']
    value = int(row['bits'], 16)
    t.require(0 <= value < (1 << width), 'Oversize serialized value')
    offset, result, arrays = 0, [], []
    for node in ET.fromstring(shape).find('tglshape'):
        if node.tag == 'arrays':
            arrays.append(dict(node.attrib))
            continue
        t.require(node.tag in ('node', 'vectornode'), 'Unknown native shape type')
        left = int(node.get('left', '0')); right = int(node.get('right', '0'))
        size = 1 if node.tag == 'node' else abs(left - right) + 1
        missing = [offset + k for k in range(2 * size)
                   if not (value >> (width - 1 - offset - k)) & 1]
        result.append(dict(node.attrib, serialized_offset=offset, logical_width=size,
                           missing_coordinates=missing, missing_slots=len(missing)))
        offset += 2 * size
        t.require(offset <= width, 'Shape exceeds binary width')
    t.require(offset == width, 'Incomplete binary shape mapping')
    return result, arrays


def data_object(scope, name):
    if '.i_multiplier' in scope:
        return name in {'operand_a_i', 'operand_b_i', 'result_o', 'mult_result_d', 'mult_result_q'}
    if '.i_scoreboard' in scope:
        return name.endswith('.result') and (name.startswith('mem_') or name.startswith('commit_instr_o'))
    if '.i_load_unit' in scope:
        return name in {'result_o', 'req_port_i.data_rdata', 'shifted_data', 'rdata_sign_bits'}
    if '.i_issue_read_operands' in scope:
        return name.startswith(('fu_data_n[', 'fu_data_q[')) and name.endswith(('.operand_a', '.operand_b'))
    if '.i_div' in scope:
        return name in {'op_a_i', 'op_b_i', 'op_a_q', 'op_a_d', 'op_b_q', 'op_b_d', 'op_b', 'res_o'}
    if '.store_buffer_i' in scope:
        return name in {'data_i', 'req_port_o.data_wdata', 'req_port_i.data_rdata'} or (
            name.startswith(('commit_queue_', 'speculative_queue_')) and name.endswith('.data'))
    return name in DATA_NAMES or name.endswith('.data') and name.startswith(('store_', 'mem_'))


def collect():
    pins = {}
    def checked(path, expected):
        t.require(t.digest(path) == expected, 'Pin drift: ' + str(path))
        pins[str(path)] = expected
        return path.read_bytes()
    manifest = json.loads(checked(BASE / 'admission-manifest.json', SEAL))
    ledger = BASE / 'combined-inputs.txt'
    inputs = checked(ledger, manifest['output_pins'][str(ledger)]).decode().splitlines()
    t.require(len(inputs) == len(set(inputs)) == 768, 'Not exact formal767')
    cache = json.loads(checked(CACHE, CACHE_SHA))
    prior = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    t.require(inputs[:742] == checked(prior, cache['input_pins'][str(prior)]).decode().splitlines(),
              'Sealed741 prefix mismatch')
    scopes = [PREFIX + s for s in SUFFIXES]
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for vdb in inputs[742:]:
        paths = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(paths) == 1, 'Ambiguous suffix Toggle data')
        p = paths[0]
        expected = manifest['input_pins'][str(p)]
        rows, sha = t.rows(p, scopes)
        t.require(sha == expected, 'Suffix pin drift')
        pins[str(p)] = sha
        union = t.union(union, rows)
    db = Path(inputs[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml', db / 'shape/tgl.verilog.shape.xml']
    for p in paths:
        checked(p, manifest['input_pins'][str(p)])
    # The regfile tgldef merges parameter names. Do not infer parameters or MDA
    # reachability from that variant; keep it outside the binary data ranking.
    checks, definitions = t.definitions(*(t.xml(p) for p in paths), scopes[:-1])
    regfile_hold = dict(scope=scopes[-1], actual_binary_row=union[scopes[-1]],
                        status='HOLD_PARAMETER_NAME_MERGE_AND_MDA_DATA_BINDING',
                        data_missing_slots_not_estimated=True)
    source_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    source_bytes = source_path.read_bytes()
    source_sha = t.digest(source_path)
    t.require(manifest['input_pins'][str(source_path)] == source_sha, 'Build-source ledger unbound')
    pins[str(source_path)] = source_sha
    sources = json.loads(source_bytes)
    bound_sources = {}
    for filename in SOURCES:
        matches = [Path(p) for p in sources if p.endswith('/core/' + filename)]
        t.require(len(matches) == 1, 'Ambiguous frozen scalar source')
        p = matches[0]; checked(p, sources[str(p)]); bound_sources[filename] = dict(path=str(p), sha256=sources[str(p)])
    for filename in ('wt_dcache.sv', 'wt_dcache_wbuffer.sv'):
        matches = [Path(p) for p in sources if p.endswith('/cache_subsystem/' + filename)]
        t.require(len(matches) == 1, 'Ambiguous write-through cache source')
        p = matches[0]; checked(p, sources[str(p)]); bound_sources[filename] = dict(path=str(p), sha256=sources[str(p)])
    ranking = []
    for scope in scopes[:-1]:
        row = union[scope]
        t.require(row['checksum'] == checks[scope], 'Shape/data checksum differs')
        nodes, arrays = typed_nodes(definitions[scope]['shape'], row)
        selected = [n for n in nodes if data_object(scope, n['name'])]
        classification = []
        for n in selected:
            if n['missing_slots']:
                classification.append(dict(name=n['name'], coordinates=n['missing_coordinates'],
                    status='FIXED_WRITE_PORT_READ_RETURN_NOT_STIMULUS' if
                    '.i_store_unit' in scope and n['name'] == 'req_port_i.data_rdata' else
                    'REACHABILITY_REQUIRES_SOURCE_ANALYSIS'))
        ranking.append(dict(scope=scope, checksum=row['checksum'], binary_width=row['width'],
                            data_missing_slots=sum(n['missing_slots'] for n in selected),
                            data_objects=selected, arrays_separately_unbound=arrays,
                            classification=classification,
                            module=definitions[scope]['module'], actual_binary_row=row))
    for p in (Path(__file__), Path(__file__).with_name('test_rank_cva6_scalar_data767.py')):
        pins[str(p)] = t.digest(p)
    for p, h in pins.items():
        t.require(t.digest(p) == h, 'Phase-end drift')
    return dict(schema='CVA6_SCALAR_DATA767_STATIC_DIAGNOSTIC_V1', population=767, input_pins=pins,
                source_bindings=bound_sources, scopes=sorted(ranking, key=lambda r: -r['data_missing_slots']),
                regfile_data_hold=regfile_hold,
                provenance='Sealed741 cached local binary OR plus exact26 admitted suffixes; arrays not binary data.',
                excludes=['CSR', 'PMP', 'RVFI', 'counters', 'addresses', 'FPU', 'disabled bitmanip'],
                fixed_read_return_evidence=dict(producer='wt_dcache_wbuffer.sv:504',
                    assignment="assign req_port_o.data_rdata = '0;",
                    cache_write_port='wt_dcache.sv write buffer',
                    route='load_store_unit.sv:545 store_unit port2 -> store_buffer.sv',
                    waiver_approved=False),
                coordinate_semantics='Left-to-right serialized pair slots, native directional labels not bound',
                official_denominator=False, predicted_not_measured=True, VCS_launched=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    t.require(not args.output.exists(), 'Fresh output required')
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print('SCALAR_STATIC_READY', t.digest(args.output))
