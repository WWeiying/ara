"""Source-bound even-start induction plus finite hit mapping; no native approval."""
import argparse
from collections import Counter
import inspect
import json
from pathlib import Path

import classify_qbs_payload_hits762 as mapping
import prove_qbs_activation_scale_hit762 as scale

ROOT = mapping.ROOT
REPORT = scale.REPORT
REPORT_SHA = scale.REPORT_SHA


def compact_range(address, length, maxburst=256):
    """Pure read planner/response recurrence; models translation low12 identity."""
    mapping.require(address >= 0 and length > 0, 'Range domain')
    cursor, remaining, offset, out = address, length, 0, []
    while remaining:
        first = cursor % 16
        chunk = min(remaining,4096-cursor%4096,maxburst-first)
        mapping.require(chunk > 0, 'Zero chunk')
        left, response_offset = chunk, offset
        while left:
            take = min(left,16-first)
            out.append((response_offset,first,take))
            left -= take
            response_offset += take
            first = 0
        cursor += chunk
        offset += chunk
        remaining -= chunk
    return out


def even_possible(bank):
    # Two exact iteration-domain changes only; all target/profile/layout logic
    # remains the pinned previously reviewed mapping implementation.
    text = inspect.getsource(mapping.possible_hits)
    changes = {'range((4 if grouped else 1)*size)': 'range(0,(4 if grouped else 1)*size,2)',
               'range(contexts*size)': 'range(0,contexts*size,2)'}
    for before, after in changes.items():
        mapping.require(text.count(before) == 1, 'Finite-domain source anchor drift')
        text = text.replace(before,after)
    namespace = dict(vars(mapping))
    exec(compile(text,'<exact-even-start-domain>','exec'),namespace)
    return namespace['possible_hits'](bank)


def require_zero_bit(records, name, bit):
    item = records.get((name,bit))
    mapping.require(item is not None and len(item['missing_serialized_coordinates']) == 2,
                    'Observed/missing compiled bit contradicts source invariant: '+name+' bit'+str(bit))


def source_chain(pins):
    book = ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    frozen = json.loads(book.read_bytes())
    pins[str(book)] = mapping.digest(book)
    names = ('hardware/include/qbs_pkg.sv','hardware/src/vlsu/qbs/qbs_read_engine.sv',
             'hardware/src/vlsu/qbs/qbs_engine.sv','hardware/src/vlsu/qbs/qbs_activation_context.sv',
             'hardware/src/vlsu/qbs/qbs_block_adapter.sv','hardware/src/vlsu/qbs/qbs_payload_buffer.sv',
             'hardware/src/vlsu/qbs/qbs_descriptor_decoder.sv',
             'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv','hardware/src/vlsu/vlsu.sv')
    texts = {}
    for relative in names:
        path = ROOT/relative
        mapping.require(mapping.digest(path) == frozen[str(path)], 'Frozen producer source drift: '+relative)
        pins[str(path)] = frozen[str(path)]
        texts[path.name] = path.read_text()
    pkg, read, engine, context, adapter, payload, decoder, mmu, top = (texts[Path(x).name] for x in names)
    anchors = {
        'qbs_read_engine.sv': ["planner_offset_q <= '0;",'planner_offset_q <= planner_offset_q + ar_chunk_bytes_q;',
            'first_lane = unsigned\'(translated_addr[BeatOffsetWidth-1:0]);',
            'bytes_to_page = 4096 - unsigned\'(planner_cursor_q[11:0]);',
            'bytes_to_axi_limit = MaxBurstBytes - first_lane;',
            'available_bytes = BeatBytes - unsigned\'(response_head.first_lane);',
            'data_offset_o = response_head.range_offset;',
            "burst_fifo_q[burst_rd_q].first_lane <= '0;",'response_head.range_offset + beat_take_bytes;',
            "data_o = '0;", "data_strb_o = '0;"],
        'qbs_activation_context.sv': ['localparam int unsigned BeatBytes = 16;',
            "replay_offset_q <= '0;",'replay_offset_q <= 11\'(byte_offset);',
            'unsigned\'(replay_issue_beat_q) * BeatBytes;',"? 16'h000f : 16'hffff;"],
        'qbs_engine.sv': ['weight_row_bytes_q <= descriptor_k_blocks * descriptor_weight_block_bytes;',
            'activation_row_bytes_q <= descriptor_k_blocks * descriptor_activation_block_bytes;',
            'compute_activation_write_offset = read_data_offset[11:0];',
            "compute_activation_write_offset = {1'b0, context_replay_offset};",
            '.weight_write_offset_i          (read_data_offset[9:0]),',
            '.activation_write_offset_i      (compute_activation_write_offset),',
            'assert (AxiDataWidth == 128)'],
        'qbs_block_adapter.sv': ["unsigned'(weight_input.offset) + beat_byte;",
            "unsigned'(activation_input.offset) + beat_byte;",'assign weight_mask[b] = weight_target[b].valid;',
            'assign activation_mask[b] = activation_target[b].valid;',
            'weight_pending_location_q[b] <= weight_location[16+b];',
            'activation_pending_location_q[b] <= activation_location[16+b];'],
        'qbs_payload_buffer.sv': ['wire [15:0] hit = word_match &',
            'wire [31:0] hit = weight_side_row[row] & weight_side_offset[b];',
            'wire [31:0] hit = activation_side_row[row] & activation_side_offset[b];'],
        'qbs_descriptor_decoder.sv': ['QbsWeightBaseAlignmentLog2-1:0] != \'0)',
            'QbsActivationBaseAlignmentLog2-1:0] != \'0)'],
        'cva6_mmu.sv': ['lsu_vaddr_q[11:0]'],
        'vlsu.sv': ['qbs_engine #(','.AxiDataWidth(AxiDataWidth)']}
    for name, expected in anchors.items():
        mapping.require(all(x in texts[name] for x in expected), 'Producer/mask anchor drift: '+name)
    mapping.old.source_contract(adapter,payload,texts.get('qbs_compute_engine.sv',
        (ROOT/'hardware/src/vlsu/qbs/qbs_compute_engine.sv').read_text()))
    # All translations are covered by full frozen hashes, not just needles.
    # The immutable package pin binds the nine block sizes and even subtracts.
    mapping.require(mapping.digest(ROOT/'hardware/include/qbs_pkg.sv') ==
                    'f64946527f9f88608a1ab6fdfb19f9854f932ca0a84fa27f4a1aa55cece5234d', 'Package domain changed')
    mapping.require(all(x % 2 == 0 for x in mapping.SIZES), 'Odd weight block size')
    return anchors


def certify():
    mapping.require(mapping.digest(REPORT) == REPORT_SHA, 'Original classification drift')
    original = json.loads(REPORT.read_bytes())
    pins = dict(original['source_pins'])
    for path, sha in pins.items(): mapping.require(mapping.digest(path) == sha,'Original pin drift: '+path)
    pins[str(REPORT)] = REPORT_SHA
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_prove_qbs_even_start_hits762.py')):
        pins[str(path)] = mapping.digest(path)
    anchors = source_chain(pins)
    shape_path = next(Path(p) for p in pins if p.endswith('/shape/tgl.verilog.shape.xml'))
    tree = mapping.ET.fromstring(mapping.gzip.open(shape_path,'rb').read())
    payload = [d for d in tree.iter('tgldef') if d.get('name') == 'qbs_payload_buffer']
    info_path = shape_path.with_name('tgl.verilog.info.xml')
    pins[str(info_path)] = mapping.digest(info_path)
    info = mapping.ET.fromstring(mapping.gzip.open(info_path,'rb').read())
    read_scope = 'ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_read_engine'
    read_instances = [i for i in info.iter('instance_data') if i.get('name') == read_scope]
    mapping.require(len(read_instances) == 1 and read_instances[0].get('chksum') == '2833497324',
                    'Exact QBS read engine compiled instance')
    read_defs = [d for d in tree.iter('tgldef') if d.get('chksum') == read_instances[0].get('chksum')]
    mapping.require(len(payload) == len(read_defs) == 1, 'Unique compiled producer/payload definition')
    data_nodes = [n for n in read_defs[0].iter('vectornode') if n.get('name') == 'data_o']
    mapping.require(len(data_nodes) == 1 and data_nodes[0].get('left') == '127' and
                    data_nodes[0].get('right') == '0', 'Frozen compiled compact beat is not128bits')
    lengths = sorted({x*n for x in (*mapping.SIZES,34,292) for n in (1,2,3,4,8)})
    checks = 0
    for low in range(0,4096,2):
        for length in lengths:
            beats = compact_range(low,length)
            mapping.require(all(not (offset%2 or first%2 or take%2) for offset,first,take in beats),
                            'Read induction counterexample')
            checks += len(beats)
    result = {}
    for scope, data in original['scopes'].items():
        bank = 0 if 'bank0.i_payload_buffer' in scope else 1
        possible, witnesses = even_possible(bank)
        original_records = {(i['signal'],i['bit']):i for i in data['records']}
        # Check every compiled hit bit, not only the prior missing inventory.
        # A fully observed forbidden bit must fail, not disappear from review.
        for node in payload[0].find('tglshape'):
            name = node.get('name')
            if not name.endswith('.hit'): continue
            mapping.require(node.tag == 'vectornode' and node.get('right') == '0', 'Hit bit layout drift')
            for bit in range(int(node.get('left'))+1):
                key,slot,side = mapping.identity(name,bit)
                if (side and slot == 0) or key not in possible:
                    require_zero_bit(original_records,name,bit)
        records, counts = [], Counter()
        for item in data['records']:
            key, slot, side = mapping.identity(item['signal'],item['bit'])
            status = item['classification']
            if status not in ('OLD1792_INVARIANT_PROJECTION','FINITE_MAPPING_IMPOSSIBLE_CANDIDATE'):
                if key not in possible:
                    mapping.require(len(item['missing_serialized_coordinates']) == 2,
                                    'An observed direction contradicts even-start invariant')
                    status = 'NEW_EVEN_START_MAPPING_ZERO_NATIVE_REQUIRED'
                else:
                    status = 'HOLD_MAPPING_FEASIBLE_PENDING_OR_PRODUCER_ARBITRATION'
            record = dict(item,classification=status)
            if status == 'NEW_EVEN_START_MAPPING_ZERO_NATIVE_REQUIRED': record['mapping_witness'] = None
            elif status.startswith('HOLD'): record['mapping_witness'] = witnesses[key]
            counts[status] += len(item['missing_serialized_coordinates'])
            records.append(record)
        result[scope] = dict(checksum=data['checksum'],raw_width=data['raw_width'],
                            missing_directions_by_class=dict(counts),records=records)
    return dict(schema='QBS_EVEN_START_HIT_STATIC_762_V1',baseline=762,pins=pins,
        source_anchors=anchors,scopes=result,read_recurrence_checks=checks,
        compiled_read_scope=read_scope,compiled_read_toggle_checksum='2833497324',
        all_compiled_hit_bits_checked_for_observed_counterexamples=True,
        excluded_initial_X=False,native_qualification=False,EDA_started=False,
        invariant_chain=[
            'Validated weight base multiple2 and direct/fill activation base multiple4; all nine weight block sizes and both activation block sizes even; K products/row strides/layout multipliers and truncations preserve parity.',
            'MMU retains virtual low12. Cursor even => first_lane even; remaining bytes, page remainder4096-low12 and maxburst16*N-first_lane even; min chunk and min take even. Offset starts0 and increments chunk/take even; first_lane resets0 between beats.',
            'Compact output writer j is byte j, no rotation of writer identity. Tail strb is a prefix; clear/default removes data/strb. Context fill consumes the same compact stream; reuse/release replay offset=beat*16 and last strb000f.',
            'Engine routes read offsets to weight and direct/fill activation; context reuse routes replay offset. Ingress captures complete target/location at acceptance; pending stores same original writer j and remaining strb, never repacks it.',
            'Masks are target.valid; older includes pending.strb. Main candidate and side_row both include mask, so invalid/default metadata cannot create a known hit. Stale valid metadata from prior legal captures preserves the all-profile union invariant; initial X is not waived.',
            'Weight row/group offsets and payload-location subtracts are all even: destination parity=writer parity. Activation side scale/aux retains parity; activation quant union includes row-major dest parity and M4/M8 global-context parity. Do not apply weight half-vector rule universally to activation.'],
        limitations='Static candidate inventory only. All other bits/selected valid/BE/consumed/controls remain protected. Existing1792 projection and scale120 separated. Mapping feasibility is not runtime reachability. Native bit layout and complete complement must be requalified before EL approval.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = certify()
    with args.output.open('x') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(path=str(args.output),sha256=mapping.digest(args.output),
        counts={s:r['missing_directions_by_class'] for s,r in result['scopes'].items()})))


if __name__ == '__main__': main()
