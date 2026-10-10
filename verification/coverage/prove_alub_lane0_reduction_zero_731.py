"""Exact14 compiled static candidates; native singleton qualification remains HOLD."""
import argparse
from collections import Counter
import inspect
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import prepare_pure_war_raw_gain as context
import prove_mask_store_snapshot_zero as lexical
import capture_operand_debug as native

life, require = context.life, context.require
BASE = life.OUT / 'pure-war-offline-admitted-731-parent-20261006-01'
BASE_SEAL = '79b146c964a009b7185e8f8b90616feab8ebeb8c859d08e0a782daea6e2f5641'
BUILD = life.OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
LINE_TARGETS = tuple(range(99, 107)) + (155,)
BRANCH_TARGETS = tuple(range(48, 53))
STATUS = 'ALUB_LANE0_EXACT14_STATIC_CANDIDATES_NATIVE_HOLD_NOT_APPLIED'
SOURCES = {
    'dispatcher': ('hardware/src/ara_dispatcher.sv', 'verification/out/old-image-source-evidence-20261006-01/ara_dispatcher.sv'),
    'lane': ('hardware/src/lane/lane_sequencer.sv', 'verification/out/old-image-source-evidence-20261006-01/lane_sequencer.sv'),
    'sequencer': ('hardware/src/ara_sequencer.sv', 'hardware/src/ara_sequencer.sv'),
    'requester': ('hardware/src/lane/operand_requester.sv', 'hardware/src/lane/operand_requester.sv'),
    'stage': ('hardware/src/lane/operand_queues_stage.sv', 'hardware/src/lane/operand_queues_stage.sv'),
    'queue': ('hardware/src/lane/operand_queue.sv', 'hardware/src/lane/operand_queue.sv'),
    'package': ('hardware/include/ara_pkg.sv', 'hardware/include/ara_pkg.sv'),
    'fifo': ('hardware/deps/common_cells/src/fifo_v3.sv', 'hardware/deps/common_cells/src/fifo_v3.sv'),
    'ara': ('hardware/src/ara.sv', 'hardware/src/ara.sv'),
    'lane_container': ('hardware/src/lane/lane.sv', 'hardware/src/lane/lane.sv'),
}


def lane_vl(vl, lane, lanes=4):
    require(type(vl) is int and vl >= 0 and lanes == 4 and 0 <= lane < lanes, 'Invalid frozen VL geometry')
    return vl // lanes + int(lane < vl % lanes)


def command_selector(vl, lane, reduction, incoming=0, ignore_zero=False):
    """VL-only selector model, not an ISA simulator; eight is ReductionZExt."""
    local = lane_vl(vl, lane)
    selector = 8 if local == 0 else incoming
    request_vl = 1 if reduction and local == 0 else local
    decoder_valid = vl > 0 or (ignore_zero and not reduction)
    return dict(selector=selector, request_vl=request_vl,
                command_valid=decoder_valid and request_vl > 0)


def fifo_selector_step(memory, write_pointer, push=None, flush=False, reset=False):
    """Accepted-write storage projection: flush resets pointer, never memory."""
    require(len(memory) == 4 and 0 <= write_pointer < 4, 'Bad frozen FIFO geometry')
    if reset:
        return [0] * 4, 0
    updated = list(memory)
    if push is not None:
        require(type(push) is int and 0 <= push < 10, 'Bad conversion selector')
        updated[write_pointer] = push
    return updated, 0 if flush else ((write_pointer + 1) % 4 if push is not None else write_pointer)


def source_contract(texts):
    compact = {k: re.sub(r'\s+', '', lexical.clean(v)) for k, v in texts.items()}
    dispatch_writes = lexical.writes(texts['dispatcher'], ('ara_req',))
    vs2 = [r for r in dispatch_writes if r['lhs'] == 'ara_req.conversion_vs2']
    literal_population = dict(OpQueueConversionWideFP2=16, OpQueueConversionSExt2=14,
        OpQueueConversionZExt2=13, OpQueueAdjustFPCvt=7, OpQueueConversionSExt8=2,
        OpQueueConversionSExt4=2, OpQueueConversionZExt4=2, OpQueueConversionZExt8=1)
    require(Counter(r['rhs'] for r in vs2) == literal_population and all(r['operator'] == '=' for r in vs2),
            'VS2 assignment inventory has unknown/indirect/Reduction RHS')
    whole = [r for r in dispatch_writes if r['lhs'] == 'ara_req']
    require(len(whole) == 1 and whole[0]['operator'] == '=' and
            whole[0]['rhs'].count('conversion_vs2:') == 1 and
            'conversion_vs2:OpQueueConversionNone,' in whole[0]['rhs'], 'Whole request selector producer differs')
    require('conversion_vs2:OpQueueConversionNone,' in compact['dispatcher'], 'Dispatcher reset/default selector differs')
    checks = {
        'lane': ["vfu_operation_d.vl=pe_req.vl/NrLanes;", "lane_id_i<pe_req.vl[idx_width(NrLanes)-1:0]",
                 "conv:(vfu_operation_d.vl=='0)?OpQueueReductionZExt:pe_req.conversion_vs2,",
                 "vl:(pe_req.opinside{[VREDSUM:VWREDSUM]}&&vfu_operation_d.vl=='0)?1:vfu_operation_d.vl,",
                 "conv:OpQueueConversionNone,", "operand_request_push[AluB]=pe_req.use_vs2;"],
        'requester': ["if(operand_request_i[requester_index].vl=='0)",
                      "operand_queue_cmd_valid_o[requester_index]=1'b0;", "conv:operand_request_i[requester_index].conv,"],
        'dispatcher': ["csr_vstart_q>=csr_vl_q", "!ignore_zero_vl_check", "ara_req_valid=1'b0;"],
        'sequencer': ["conversion_vs2:ara_req_i.conversion_vs2,"],
        'stage': [".SupportReduct(1'b1)", ".CmdBufDepth(ValuInsnQueueDepth)", ".flush_i(1'b0)"],
        'package': ['ValuInsnQueueDepth=4;', 'OpQueueConversionNone,', 'OpQueueReductionZExt,'],
        'queue': ['.DEPTH(CmdBufDepth)', '.push_i(operand_queue_cmd_valid_i)',
                  "if(lane_id_i=='0)", 'OpQueueReductionZExt:begin'],
        'fifo': ["FALL_THROUGH=1'b0", "mem_q<={FifoDepth{dtype'('0)}};", 'if(push_i&&~full_o)begin'],
        'ara': ['.ara_req_o(ara_req)', '.ara_req_i(ara_req)', '.pe_req_o(pe_req)', '.pe_req_i(pe_req)'],
        'lane_container': ['assignpe_req=pe_req_i;', '.pe_req_i(pe_req)'],
    }
    for key, needles in checks.items():
        for needle in needles:
            require(needle in compact[key], 'Frozen producer/storage contract differs: ' + key + ':' + needle)
    producers = [r for r in lexical.writes(texts['lane'], ('operand_request',))
                 if r['lhs'] == 'operand_request[AluB]']
    require(len(producers) == 2 and 'conv:OpQueueConversionNone,' in producers[1]['rhs'] and
            "conv:(vfu_operation_d.vl=='0)?OpQueueReductionZExt:pe_req.conversion_vs2," in producers[0]['rhs'],
            'ALUB whole producer inventory differs')
    alub_fields = [r for r in lexical.writes(texts['lane'], ('operand_request',))
                   if r['lhs'].startswith('operand_request[AluB].')]
    require(all(r['lhs'].split('].', 1)[1] in ('vl', 'vstart', 'eew') for r in alub_fields),
            'ALUB field conversion override')
    pe_writes = lexical.writes(texts['sequencer'], ('pe_req_d',))
    pe_whole = [r for r in pe_writes if r['lhs'] == 'pe_req_d']
    require(len(pe_whole) == 4 and [r['rhs'] for r in pe_whole[:2]] == ["'0", 'pe_req_o'] and
            'conversion_vs2:ara_req_i.conversion_vs2,' in pe_whole[2]['rhs'] and
            pe_whole[3]['rhs'] == 'pe_req_o' and not any('conversion_vs2' in r['lhs'] for r in pe_writes),
            'Alternate PE selector RHS/override')
    parameters = {name: re.sub(r'\s+', '', body) for body, name in re.findall(
        r'operand_queue\s*#\s*\((.*?)\)\s*(i_operand_queue_\w+)\s*\(', lexical.clean(texts['stage']), re.S)}
    require('.SupportReduct(1\'b1)' in parameters.get('i_operand_queue_alu_b', '') and
            '.CmdBufDepth(ValuInsnQueueDepth)' in parameters['i_operand_queue_alu_b'], 'ALUB parameters differ')
    require(not lexical.writes(texts['ara'], ('pe_req',)) and
            compact['ara'].count('.pe_req_o(pe_req)') == 1, 'Alternate broadcast PE producer')
    require('[VLE:VLXE],VQBEXEC,VAKVFILL,VAKVLOAD,VAKVRELEASE:vfu=VFU_LoadUnit;' in compact['sequencer'],
            'Custom operations can enter ALU producer')
    fifo_mem = lexical.writes(texts['fifo'], ('mem_q',))
    require([(r['operator'], r['rhs']) for r in fifo_mem] ==
            [('<=', "{FifoDepth{dtype'('0)}}"), ('<=', 'mem_n')], 'FIFO memory writers differ')
    fifo_next = lexical.writes(texts['fifo'], ('mem_n',))
    require([(r['lhs'], r['operator'], r['rhs']) for r in fifo_next] ==
            [('mem_n', '=', 'mem_q'), ('mem_n[write_pointer_q]', '=', 'data_i')],
            'FIFO memory hold/accepted-write/flush contract differs')
    return dict(vs2_assignment_ledger=vs2, vs2_literal_population=literal_population,
        indirect_vs2_RHS_count=0, dispatcher_whole_request_ledger=whole,
        pe_whole_request_ledger=pe_whole, alub_whole_producers=producers, alub_field_write_ledger=alub_fields,
        lane0_positive_global_VL_implies_positive_local_VL=True,
        reduction_global_zero_dispatched=False, nonreduction_local_zero_command_muted=True,
        fifo_reset_selector='OpQueueConversionNone', fifo_depth=4, fifo_fall_through=False,
        fifo_flush_clears_memory=False, fifo_flush_retains_only_previous_accepted_nonReduction_selectors=True,
        fifo_storage_write_ledger=fifo_mem + fifo_next, alub_parameters=parameters['i_operand_queue_alu_b'],
        memory_induction=['Reset sets all four selectors to None=0.',
            'Each accepted lane0 ALUB producer has selector in {0,1,2,3,4,5,6,7,9}.',
            'Non-push holds every slot; accepted push changes only one slot to that allowed set.',
            'Flush resets pointers/count only; prior valid memory selectors remain in that same set.',
            'FALL_THROUGH=0 and DEPTH=4 read only stored selectors, including empty/stale slots.'],
        custom_QBS_AKV_path='Single dispatcher->main sequencer->broadcast->lane; custom ops classified VFU_LoadUnit, not ALUB',
        no_alternate_lane_broadcast_producer=True,
        scope='Postreset frozen build, ordinary decoded software, no force/X injection; not formal RTL theorem')


def scope(lane, queue):
    return f'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[{lane}].i_lane.i_operand_queues.i_operand_queue_alu_{queue}'


def inventory(bits):
    design = context.compiled.Design(context.DESIGN)
    rows, definitions = {}, {}
    for lane in range(4):
        for queue in ('a', 'b'):
            s = scope(lane, queue); source = design.source(s)
            require(source['resolved_path'] == str(life.ROOT / SOURCES['queue'][0]), 'Wrong compiled queue owner')
            rows[s] = {}
            for metric in ('line', 'branch'):
                record = bits['metrics'][metric][s]; node = design.definition(s, metric)
                require(record['checksum'] == node.get('chksum'), 'Definition checksum differs')
                expected_shape = (181, '3998926456') if metric == 'line' else (101, '1417162425')
                require((record['width'], record['checksum']) == expected_shape, 'Queue metric shape differs')
                key = metric + ':' + record['checksum']
                definitions[key] = dict(checksum=record['checksum'], xml=ET.tostring(node, encoding='unicode'))
                tab = []
                for p in context.compiled.points(metric, node, record['width']):
                    selected = s == scope(0, 'b') and p['raw_index'] in (LINE_TARGETS if metric == 'line' else BRANCH_TARGETS)
                    hit = bool(int(record['bits'], 16) & (1 << (record['width'] - 1 - p['raw_index'])))
                    require(not selected or not hit, 'Candidate already hit')
                    tab.append(dict(point=p, coordinate=native.coordinate(p, metric), target=selected,
                        width=record['width'], module_checksum=source['definition_checksum'],
                        metric_checksum=record['checksum'], source=source, hit731=hit,
                        decision='STATIC_CANDIDATE_NATIVE_HOLD' if selected else 'PROTECTED'))
                rows[s][metric] = tab
    selected = [r for tab in rows.values() for rs in tab.values() for r in rs if r['target']]
    require(len(selected) == 14 and len({(r['source']['resolved_path'], r['coordinate'], r['metric_checksum']) for r in selected}) == 14,
            'Exact14 population differs')
    for r in rows[scope(0, 'b')]['branch']:
        if r['target']:
            p = r['point']; vector = p['native_vector']['vector']
            require(p['native_id'] == '5' and p['vector'] == str(76 - p['raw_index']) and
                    vector[-37] == vector[-38] == '1' and p['attributes']['chksum'] == '718333796',
                    'Reduction branch identity differs')
    for lane in (1, 2, 3):
        branch = next(r for r in rows[scope(lane, 'b')]['branch'] if r['point']['raw_index'] == 48)
        require(branch['hit731'] and not branch['target'], 'Real neutral lane must remain protected')
    return rows, definitions


def evidence():
    manifest = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    life.check(manifest['output_pins'])
    require(manifest['output'] == str(BASE) and all(Path(p).parent == BASE for p in manifest['output_pins']), 'Baseline alias')
    bits = json.loads((BASE / 'combined-bits.json').read_bytes()); state = json.loads((BASE / 'status.json').read_bytes())
    require(state['aggregate_passed'] == 731 and state['coverage_admitted'] is True and
            state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and
            len(bits['tests']) == len(set(bits['tests'])) == 731 and
            (BASE / 'combined-inputs.txt').read_text().splitlines() == [str(context.DESIGN), *bits['tests']], 'Exact formal731 differs')
    formalpins = json.loads((BASE / 'evidence-pins.json').read_bytes())
    require(formalpins[str(life.IMAGE)] == context.q.runner.original.IMAGE_SEAL, 'Formal frozen image differs')
    pins = life.merge_pins(manifest['output_pins'], {str(BASE / 'admission-manifest.json'): BASE_SEAL,
        str(BUILD): formalpins[str(BUILD)], str(life.IMAGE): formalpins[str(life.IMAGE)]})
    life.check(pins)
    build = json.loads(BUILD.read_bytes()); texts, sources = {}, {}
    for key, (original, captured) in SOURCES.items():
        original, captured = life.ROOT / original, life.ROOT / captured
        wanted = build[str(original)]; require(life.digest(captured) == wanted, 'Frozen source differs: ' + key)
        pins = life.merge_pins(pins, {str(captured): wanted}); texts[key] = captured.read_text()
        sources[key] = dict(original=str(original), captured=str(captured), sha256=wanted,
                            snapshot_used=original != captured)
    db = context.DESIGN / 'snps/coverage/db'
    for rel, seal in bits['design'].items(): pins = life.merge_pins(pins, {str(db / rel): seal})
    for rel in ('auxiliary/verilog.sourceinfo.xml', 'shape/line.verilog.info.xml', 'shape/branch.verilog.info.xml'):
        pins = life.merge_pins(pins, {str(db / rel): life.digest(db / rel)})
    for module in (context, context.compiled, lexical, native):
        p = Path(module.__file__).resolve(); pins = life.merge_pins(pins, {str(p): life.digest(p)})
    for function in (context.compiled.Design, context.compiled.points, native.require, life.check, life.save):
        p = Path(inspect.getfile(function)).resolve(); pins = life.merge_pins(pins, {str(p): life.digest(p)})
    for name in ('prove_alub_lane0_reduction_zero_731.py', 'test_prove_alub_lane0_reduction_zero_731.py'):
        p = Path(__file__).with_name(name); pins = life.merge_pins(pins, {str(p): life.digest(p)})
    ledger = source_contract(texts); scopes, definitions = inventory(bits)
    ranges = dict(dispatcher=[(1205, 1225), (2576, 2624), (4934, 4956), (5000, 5012), (5042, 5060),
                             (5080, 5090), (5120, 5142), (5160, 5174), (5908, 5922)], lane=[(433, 538), (982, 1016)],
        sequencer=[(290, 302), (762, 771)], requester=[(450, 491), (559, 584)], stage=[(96, 125)],
        queue=[(59, 79), (393, 407), (502, 519)], package=[(153, 158), (264, 282)], fifo=[(15, 21), (64, 85), (116, 150)],
        ara=[(263, 272), (353, 375), (494, 503)], lane_container=[(272, 301)])
    excerpts = {key: [dict(first=start, last=end, text='\n'.join(texts[key].splitlines()[start-1:end]) + '\n')
                      for start, end in spans] for key, spans in ranges.items()}
    life.check(pins)
    candidates = [dict(scope=s, metric=m, **r) for s, tab in scopes.items() for m, rs in tab.items() for r in rs if r['target']]
    protected = sum(not r['target'] for tab in scopes.values() for rs in tab.values() for r in rs)
    return dict(status=STATUS, schema='ALUB_LANE0_REDUCTION_STATIC14_731_V1', baseline=str(BASE),
        baseline_seal=BASE_SEAL, baseline_tests=731, pins=pins, sources=sources,
        source_contract=ledger, source_excerpts=excerpts, compiled_definitions=definitions,
        candidates=candidates, candidate_count=14, protected_count=protected, plan=dict(scopes=scopes),
        native_qualification=dict(status='HOLD_NOT_CAPTURED', architecture='capture_operand_debug singleton Block/Branch + mask/LZC roundtrip',
            grammar=['CHECKSUM module/metric', 'INSTANCE exact scope', 'Block ID/checksum/complete bbsig',
                     'Branch ID/spec checksum/cmd.conv/captured textual branch signature'],
            compiled_coordinates_are_native_selectors=False, generated_EL=False,
            required_stages=['initial-empty', 'before', 'selected', 'first-export', 'reset-empty',
                             'import-first', 'reloaded', 'second-export', 'final-empty'],
            require_whole14_exactshape=True, require_all_protected_singleton_states=True,
            branch_text_from_actual_native_only=True, block_point_checksum_must_match=True,
            no_instance_exclusion=True, line_branch_only=True, no_launch_supported=True),
        protection=dict(all_ALUA_seed_scopes=True, all_ALUB_lane1_3=True, lane0_ALUB_complement=True,
                        condition_FSM_toggle_untouched=True, reset_default_outside_exact_targets=True,
                        parameter_false_branch_raw47_not_selected=True),
        native_qualified=False, EDA_started=False, RTL_changed=False, exclusions_applied=False,
        aggregate_application=False, waiver_approval=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'verify')); p.add_argument('--output', type=Path, required=True); p.add_argument('--seal')
    a = p.parse_args(); out = a.output.absolute()
    require(out.parent == life.OUT and out.resolve() == out, 'Independent direct out required')
    if a.mode == 'prepare':
        require(not out.exists() and not a.seal, 'Fresh candidate required'); record = evidence(); out.mkdir()
        life.save(out / 'candidate.json', record)
        print(json.dumps(dict(output=str(out), seal=life.digest(out / 'candidate.json'), candidates=14, native='HOLD')))
    else:
        require(a.seal, 'Candidate seal required'); record = life.read_bound(out / 'candidate.json', a.seal)
        life.check(record['pins']); require(record == evidence(), 'Static reproduction differs')
        print('VERIFY_PASS STATIC14 NATIVE_HOLD NO_APPLY')


if __name__ == '__main__': main()
