"""Frozen-source legal MFPU restart gap, exact raw768 positions; no EDA."""
import argparse
import csv
import json
from pathlib import Path
import re

import rank_ordinary_rvv_toggle766 as predecessor
import review_queue_fp_residual768 as queue
import targeted_toggle_evidence_v2 as raw
import audit_qbs_engine_residual766 as shape_helpers

ROOT, OUT = predecessor.ROOT, predecessor.OUT
DEST = OUT / 'rvv-mfpu-restart-word-boundary768-static-agent-20261007-01.json'
BOOK = queue.old.BUILD
SIM_SHA = '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3'
SOURCES = ('hardware/src/lane/lane_sequencer.sv', 'hardware/src/lane/vmfpu.sv',
           'hardware/src/lane/operand_queue.sv', 'hardware/src/lane/operand_requester.sv',
           'hardware/src/ara_dispatcher.sv', 'hardware/include/ara_pkg.sv',
           'hardware/src/ara.sv', 'hardware/src/lane/lane.sv', 'hardware/src/lane/vector_fus_stage.sv')


def frozen_sources(book):
    texts = {}; bindings = []
    for rel in SOURCES:
        original = ROOT / rel
        path = original
        if raw.digest(path) != book[str(original)]:
            path = OUT / 'old-image-source-evidence-20261006-01' / original.name
        raw.require(path.exists() and raw.digest(path) == book[str(original)], 'No exact frozen source: ' + rel)
        texts[original.name] = path.read_text()
        bindings.append(dict(original_path=str(original), evidence_path=str(path), sha256=book[str(original)],
                             working_file_is_frozen=path == original))
    return texts, bindings


def lane_start(start, lane):
    raw.require(0 <= start < 512 and 0 <= lane < 4, 'Legal e16/m8 restart domain')
    return start // 4 + int(lane < start % 4)


def source_contract(texts):
    seq = texts['lane_sequencer.sv']
    mfpu = texts['vmfpu.sv']
    for token in ('vfu_operation_d.vstart = pe_req.vstart / NrLanes;',
                  'lane_id_i < pe_req.vstart[idx_width(NrLanes)-1:0]',
                  "vfu_operation_d.vstart += 1'b1;"):
        raw.require(token in seq, 'Lane-local restart propagation changed')
    for token in ('vinsn_queue_d.vinsn[vinsn_queue_q.accept_pnt]    = vfu_operation_i;',
                  'assign vinsn_issue_d     = vinsn_queue_d.vinsn[vinsn_queue_d.issue_pnt];',
                  'active_from_vstart(vinsn_issue_q.vl - issue_cnt_q,',
                  'vinsn_issue_q.vstart,', 'mfpu_operand_ready_o = operands_ready;',
                  'vfpu_control_in = issue_be;', 'localparam VInsnQueueDepth = MfpuInsnQueueDepth;'):
        raw.require(token in mfpu, 'MFPU acceptance, prefix mask or handshake changed: ' + token)
    raw.require('localparam int unsigned MfpuInsnQueueDepth = 4;' in texts['ara_pkg.sv'], 'Queue depth changed')
    for file, module, instance in [('ara.sv','lane','i_lane'), ('lane.sv','vector_fus_stage','i_vfus'),
                                   ('vector_fus_stage.sv','vmfpu','i_vmfpu')]:
        blocks = re.findall(r'\b' + module + r'\s*#\((.*?)\)\s*' + instance + r'\s*\(', texts[file], re.S)
        raw.require(len(blocks) == 1, 'Unique frozen parameter producer')
        compact = re.sub(r'\s+', '', blocks[0])
        raw.require(all('.%s(%s)' % (p,p) in compact for p in ('NrLanes','VLEN','FPUSupport')), 'Parameter forwarding changed')
    return dict(vlen=1024, lanes=4, sew=16, lmul=8, vlmax=512, instruction_queue_depth=4,
        source_values_unrestricted=True, flags_rounding_control_protected=True)


def collect():
    pins = {}
    def bind(path, expected=None):
        h = raw.digest(path)
        raw.require(expected is None or h == expected, 'Input pin drift: ' + str(path))
        pins[str(path)] = h
        return json.loads(path.read_bytes())
    config = bind(predecessor.CONFIG, predecessor.CONFIG_SHA)
    cache = bind(predecessor.CACHE, predecessor.CACHE_SHA)
    formal = bind(queue.BASE / 'admission-manifest.json', queue.BASE_SHA)
    book = bind(BOOK, queue.BUILD_SHA)
    parent = bind(OUT / 'qbs-engine-full102-residual766-static-agent-20261007-01.json',
                  'b6fefc0d350ed0ca4d3add37f3b6a43fd6cb4a79742dc2384d9f297abd5a8cca')
    parent_params = next(s['integer_parameters'] for s in parent['scope_summaries'] if s['scope'].endswith('.i_qbs_engine'))
    raw.require(parent_params['NrLanes'] == 4 and parent_params['VLEN'] == 1024, 'Frozen shared Ara parameter origin differs')
    sibling = bind(OUT / 'operand-queue-fp-residual768-static-agent-20261007-02.json',
                   '7f0b43d380871fb7986abf2c547117a6d7bf7cdefe121a32c8e6737293c98d5d')
    raw.require(sibling['source_proof']['parameter_bindings']['mfpu_a'] == 56, 'Frozen shared lane FPUSupport differs')
    texts, source_bindings = frozen_sources(book)
    pins.update({b['evidence_path']: b['sha256'] for b in source_bindings})
    domain = source_contract(texts)
    sim = BOOK.parent / 'sim/simv'
    raw.require(raw.digest(sim) == SIM_SHA, 'Frozen executable differs')
    pins[str(sim)] = SIM_SHA
    ledger_path = queue.BASE / 'combined-inputs.txt'
    raw.require(raw.digest(ledger_path) == formal['output_pins'][str(ledger_path)], 'Raw768 ledger drift')
    pins[str(ledger_path)] = raw.digest(ledger_path)
    ledger = ledger_path.read_text().splitlines()
    raw.require(len(ledger) == len(set(ledger)) == 769 and ledger[:767] == config['input_ledger'], 'Exact766+2 suffix membership')
    prior = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    raw.require(raw.digest(prior) == cache['input_pins'][str(prior)] and ledger[:742] == prior.read_text().splitlines(), 'Exact cached741 prefix')
    pins[str(prior)] = raw.digest(prior)
    scopes = [s for s in cache['instances'] if '.i_ara.gen_lanes[' in s
              and s.endswith(('.i_lane', '.i_lane_sequencer', '.i_vfus', '.i_vmfpu'))]
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for index, vdb in enumerate(ledger[742:], start=742):
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        raw.require(len(files) == 1, 'Suffix test ambiguity')
        path = files[0]
        expected = config['pins'][str(path)] if index < 767 else formal['input_pins'][str(path)]
        rows, h = raw.rows(path, scopes)
        raw.require(h == expected, 'Admitted suffix data drift')
        pins[str(path)] = h
        union = raw.union(union, rows)
    db = Path(ledger[0]) / 'snps/coverage/db'
    shape_path = db / 'shape/tgl.verilog.shape.xml'
    raw.require(raw.digest(shape_path) == config['pins'][str(shape_path)], 'Compiled shape drift')
    pins[str(shape_path)] = raw.digest(shape_path)
    shape = raw.xml(shape_path)
    targets = []; inventories = []; excluded = []
    el_path = predecessor.CONFIG.parent / 'combined.el'
    raw.require(raw.digest(el_path) == config['pins'][str(el_path)], 'Actual766 canonical drift')
    pins[str(el_path)] = raw.digest(el_path)
    scope = None; directives = {}
    for line in el_path.read_text().splitlines():
        if line.startswith('INSTANCE:'): scope = line.split(':', 1)[1].strip()
        elif line.startswith('Toggle '): directives.setdefault(scope, []).append(line)
    for scope in scopes:
        row = union[scope]
        definitions = [d for d in shape.findall('tgldef') if d.get('chksum') == row['checksum']]
        raw.require(len(definitions) == 1, 'Ambiguous actual checksum shape')
        definition = definitions[0]
        module = definition.get('name', '').split(' (')[0]
        params = shape_helpers.integer_params(definition)
        if scope.endswith('.i_vmfpu'):
            raw.require(module == 'vmfpu', 'Not actual compiled MFPU identity')
            raw.require(not params or (params['NrLanes'] == 4 and params['VLEN'] == 1024 and params['FPUSupport'] == 56), 'MFPU compiled domain differs')
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        offset = 0; all_missing = 0
        for node in definition.find('tglshape'):
            if node.tag == 'arrays': continue
            raw.require(node.tag in ('node', 'vectornode'), 'Unknown typed serialization')
            width = 1 if node.tag == 'node' else abs(int(node.get('left')) - int(node.get('right'))) + 1
            zeros = [offset + k for k, b in enumerate(binary[offset:offset + 2 * width]) if b == '0']
            all_missing += len(zeros)
            name = node.get('name', '')
            local = (module == 'vmfpu' and name.endswith('.vstart')) or name in (
                'vfu_operation.vstart', 'vfu_operation_o.vstart', 'vfu_operation_d.vstart', 'vfu_operation_q.vstart', 'vfu_operation_i.vstart')
            if local and zeros:
                raw.require(node.tag == 'vectornode' and node.get('left') == '10' and node.get('right') == '0', 'Exact local vstart shape')
                lane = int(re.search(r'gen_lanes\[(\d+)\]', scope)[1])
                possible = [lane_start(start, lane) for start in (508, 511, 0)]
                bits = [bit for bit in range(width) if any(v & (1 << bit) for v in possible)]
                positions = [p for p in zeros if (p - offset) // 2 in bits]
                if positions:
                    overlap = [line for line in directives.get(scope, []) if re.search(r'(?<!\S)' + re.escape(name) + r'(?:\s|\[)', line)]
                    item = dict(scope=scope, name=name, module=module, checksum=row['checksum'], compiled_definition=definition.get('name'),
                        attributes=dict(node.attrib), kind=node.tag, serialized_offset=offset, serialized_width=row['width'],
                        source_bits_with_missing_slots=sorted({(p - offset) // 2 for p in positions}),
                        exact_missing_serialized_positions=positions, missing_slots=len(positions),
                        slot_pairs=[dict(source_bit=b, positions=[p for p in positions if (p - offset) // 2 == b])
                                    for b in sorted({(p - offset) // 2 for p in positions})],
                        native_direction_labels_not_inferred=True, legal_lane_values=possible,
                        reachability='Actual acceptance/copies of lane-local operation metadata; observable execution requires future DUT trace',
                        existing766_canonical_overlap=overlap)
                    (excluded if overlap else targets).append(item)
            offset += 2 * width
        raw.require(offset == row['width'], 'Full serialized shape width differs')
        inventories.append(dict(scope=scope, module=module, parameters=params, checksum=row['checksum'], raw_missing=all_missing))
    modules_path = predecessor.CONFIG.parent / 'modules_applied.csv'
    pins[str(modules_path)] = raw.digest(modules_path)
    with modules_path.open(newline='') as stream:
        module_rows = [r for r in csv.DictReader(stream) if any(s['scope'] == r['Scope'] for s in inventories)]
    historical = OUT / 'repaired-aligned-600-20260930-01/results/c0221-rvv-vfp_vstart_edges-6c95205c2a1a-c5fc79178f5f'
    summary = bind(historical / 'summary.json'); audit = bind(historical / 'independent_audit.json')
    raw.require(summary[0]['status'] == audit['status'] == 'PASS', 'Prior restart fixture not PASS')
    software = ROOT / 'apps/riscv-tests/isa/rv64uv/vfp_vstart_edges.c'
    pins[str(software)] = raw.digest(software)
    starts = sorted(set(map(int, re.findall(r'li t1,\s*(\d+)', software.read_text()))))
    for p in (Path(__file__).resolve(), Path(__file__).with_name('test_review_rvv_restart_word_boundary768.py')):
        pins[str(p)] = raw.digest(p)
    for p, h in pins.items(): raw.require(raw.digest(p) == h, 'Final evidence drift')
    return dict(status='RAW768_LEGAL_MFPU_RESTART_STIMULUS_SOURCE_REVIEW_NO_EDA', population=768,
        recommendation_count=1, source_domain=domain, target_objects=len(targets),
        exact_missing_serialized_positions=sum(t['missing_slots'] for t in targets), targets=targets,
        prior_canonical_overlaps_not_recommended=excluded, scoped_raw_inventory=inventories,
        frozen766_module_metrics=module_rows, source_producer_paths=source_bindings,
        parameter_binding_authority='VMFPU tgldef has no direct param attribute; exact sibling compiled QBS shared-Ara 4/1024, reviewed shared-lane FPUSupport56, and frozen Ara->lane->vector_fus_stage->vmfpu forwarding. Not inferred from type name alone.',
        existing_PASS=dict(summary=summary, independent_audit=audit, source=str(software), immediate_vstart_values=starts,
            gap='Cached PASS exercises small FP restart values; raw768 still lacks the precise listed functional metadata positions',
            does_not_claim_historical_launcher_SHA_equals_frozen_simv=True),
        representative_case=dict(name='mfpu_e16m8_restart_last_halfword', vlen=1024, lanes=4, vl=512,
            vtype='e16,m8,tu,mu', groups=dict(v8='2.0 FP16, eight registers', v16='4.0 FP16, eight registers', v24='8.0 FP16, eight registers'),
            phases=[dict(vstart=508, repetitions=4, lane_start=[127]*4, reason='Fill all four instruction metadata slots with local bits0..6'),
                    dict(vstart=511, repetitions=4, lane_start=[128,128,128,127], reason='Carry into local bit7 in three lanes; lane3 retains valid last halfword'),
                    dict(vstart=0, repetitions=4, lane_start=[0]*4, reason='Explicit functional clearing of all copied restart metadata; both serialized slots remain a measured obligation')],
            instruction='vfmacc.vv v24,v8,v16; write vstart before each instruction', frm='RNE', flags='must be zero, no waiver',
            last_lane_word=31, first_phase_BE='0xc0', final_suffix_global_indices=[508,509,510,511],
            snapshots='After each four-instruction phase, store all512 FP16 destination elements after checking vstart==0; verify source groups unchanged',
            oracle_phase_values=[[8,40,40],[8,40,72],[40,72,104]],
            oracle_regions=['indices0..507','indices508..510','index511'], defined_destination_bytes=3072,
            probes=['vfu_operation_i.vstart and four accepted vinsn queue metadata slots', 'issue_cnt_q/issue_be/vfpu_control_in',
                    'mfpu_operand_valid_i/mfpu_operand_ready_o', 'result_queue data/be, mfpu_result_req_o/gnt_i/be_o', 'retirement vstart and fflags'],
            hypothesis='Large legal restart values reach unchanged functional metadata holes while prefix suppression writes only the last high halfword',
            distinguishing_failure='Missing metadata copy hit versus incorrect active_from_vstart BE versus undrained result/queue handshake',
            guarantee='Legally reachable metadata values, not a prediction that every copied raw position will hit'),
        excluded_stimulus_directions=['TLB/stride/randomGPR', 'already-reviewed queue312 FP constants',
            'read-request operand_payload wdata/be default zero', 'unproven queue saturation', 'blanket MFPU arithmetic/flags waiver'],
        simulator_launched=False, EDA_launched=False, coverage_admitted=False, official_denominator=None, predicted_percentage=None,
        pins=pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEST)
    destination = parser.parse_args().output
    raw.require(not destination.exists(), 'Fresh independent output required')
    result = collect()
    with destination.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(destination), sha256=raw.digest(destination), objects=result['target_objects'],
                         missing_slots=result['exact_missing_serialized_positions'])))
