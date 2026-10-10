"""Read-only frozen-source and compiled-coordinate cache port1 audit; no EDA."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BUILD = OUT / 'repaired-aligned-build-20260930-01'
BASE = OUT / 'load-ni-tlb-offline-admitted-762-agent-20261007-01'
BASE_SHA = '6959f676c022f38f9ee2977252c600cfeb5b89fe50b3c4b22d08bf5de7b95cc5'
PRIOR = OUT / 'formal760-fsm-priority-parent-20261007-01.json'
PRIOR_SHA = '906d42477ac9d42d772e68f0a100ca1d154954b48391846d9f5260fb3fe253e9'
SCOPE = ('ara_tb.dut.i_ara_soc.i_system.i_ariane.gen_cache_wt.i_cache_subsystem.'
         'i_wt_dcache.gen_rd_ports[1].genblk1.i_wt_dcache_ctrl')
CORE = ROOT / 'hardware/deps/cva6/core'
CTRL = CORE / 'cache_subsystem/wt_dcache_ctrl.sv'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(path, sha):
    need(digest(path) == sha, 'Pin mismatch: ' + str(path))
    return json.loads(Path(path).read_bytes())


def check(pins):
    for path, sha in pins.items():
        need(digest(path) == sha, 'Pin mismatch: ' + path)
    return dict(checked=len(pins), mismatches=0)


def xml(path):
    data = path.read_bytes()
    return ET.fromstring(gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)


def excerpt(path, first, last):
    lines = path.read_text().splitlines()
    return dict(path=str(path), sha256=digest(path), lines=[first, last],
                text='\n'.join('%d: %s' % (i + 1, lines[i]) for i in range(first - 1, last)))


FACTS = {
    ('State', 'KILL_MISS_ACK'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [186, 201],
        'MISS_REQ && kill_req && !miss_ack_i',
        'Flush a load already in MISS_REQ while its miss is unacknowledged. load_unit flush_i sets WAIT_FLUSH; the following cycle drives kill_req. No force of internal state is required.'),
    ('State', 'REPLAY_REQ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 201],
        '(READ && tag_valid || REPLAY_READ) && !kill_req && (wr_cl_vld_i || !rd_ack_q), OR MISS_REQ && !kill_req && miss_replay_i',
        'Refill/readout collision or same-cacheline MSHR replay. Ports 0/2 can own the other outstanding read.'),
    ('State', 'REPLAY_READ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [219, 227],
        'REPLAY_REQ && !kill_req && rd_ack_i', 'A replay request obtains a normal SRAM arbitration grant.'),
    ('Transition', 'KILL_MISS_ACK->IDLE'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [230, 238],
        'miss_replay_i (or asynchronous reset)',
        'Killed pending load collided with the other outstanding MSHR; missunit detects/sticks the line collision and replays instead of allocating. Functional source assignment is line235 despite compiled label262.'),
    ('Transition', 'KILL_MISS_ACK->KILL_MISS'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [230, 238],
        '!miss_replay_i && miss_ack_i',
        'Unacknowledged killed request is later accepted; controller drains its response in KILL_MISS.'),
    ('Transition', 'MISS_REQ->IDLE'): (
        'RESET_ONLY_NORMAL_MODE_STRUCTURALLY_UNREACHABLE', [186, 201],
        '!rst_ni; no normal-mode MISS_REQ branch assigns IDLE',
        'MISS_REQ can hold, enter KILL_MISS/KILL_MISS_ACK on kill, REPLAY_REQ on replay, or MISS_WAIT on ack. Valid enum state excludes the default case. Reset line262 is the sole direct IDLE assignment for this source state. Not a disabled-configuration waiver and not globally unreachable.'),
    ('Transition', 'MISS_REQ->KILL_MISS_ACK'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [186, 201],
        'kill_req && !miss_ack_i', 'One-cycle load flush/WAIT_FLUSH with miss acceptance delayed by another MSHR or memory backpressure.'),
    ('Transition', 'MISS_REQ->REPLAY_REQ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [186, 201],
        '!kill_req && miss_replay_i',
        'Other port has an outstanding read of the same physical cacheline; port1 miss remains pending. Collision is sticky until the request drops, and missunit replays once the MSHR can clear.'),
    ('Transition', 'READ->REPLAY_REQ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 182],
        '!kill_req && tag_valid && (wr_cl_vld_i || !rd_ack_q)',
        'Another-port refill in the tag-check cycle, or delayed tag following lost speculative readout arbitration. Immediate next-cycle tag with the original grant does not alone make !rd_ack_q true.'),
    ('Transition', 'REPLAY_READ->IDLE'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 182],
        'kill_req OR (!wr_cl_vld_i && rd_ack_q && any_hit && cache_en_i && !(rd_ack_i && data_req))',
        'Replayed read hits with no next load, or a legal load flush kills it. Compiled reset-line label does not imply reset-only.'),
    ('Transition', 'REPLAY_READ->MISS_REQ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 182],
        '!kill_req && !wr_cl_vld_i && rd_ack_q && !(any_hit && cache_en_i)',
        'Replayed lookup of a different cold cacheline is a normal miss.'),
    ('Transition', 'REPLAY_READ->READ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 182],
        '!kill_req && !wr_cl_vld_i && rd_ack_q && any_hit && cache_en_i && rd_ack_i && data_req',
        'After a replay stall, load_unit WAIT_GNT holds the next independent load; the old replayed hit responds while the next load is granted. NrLoadBufEntries=2 supports this overlap.'),
    ('Transition', 'REPLAY_READ->REPLAY_REQ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [157, 182],
        '!kill_req && (wr_cl_vld_i || !rd_ack_q)',
        'A second legal refill/invalidation can collide with the replay lookup. Immediately after REPLAY_REQ grant rd_ack_q=1, so use a new wr_cl_vld_i event rather than claim a spontaneous lost previous grant.'),
    ('Transition', 'REPLAY_REQ->IDLE'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [219, 227],
        'kill_req (or asynchronous reset)',
        'Flush during the replay stall; load_unit WAIT_FLUSH asserts kill_req. Functional assignment is line224 despite compiled label262.'),
    ('Transition', 'REPLAY_REQ->REPLAY_READ'): (
        'LEGAL_CONDITIONAL_SOURCE_PATH', [219, 227],
        '!kill_req && rd_ack_i', 'Normal replay read grant after refill finishes.'),
}


def collect():
    book = bound(BASE / 'admission-manifest.json', BASE_SHA)
    checks = dict(formal762_input=check(book['input_pins']), formal762_output=check(book['output_pins']))
    srcpins_path = BUILD / 'build-source-pins.json'
    srcpins = bound(srcpins_path, book['input_pins'][str(srcpins_path)])
    source_drift = [dict(path=path, expected_sha256=sha, actual_sha256=digest(path))
                    for path, sha in srcpins.items() if digest(path) != sha]
    checks['frozen_build_sources'] = dict(checked=len(srcpins), mismatches=len(source_drift),
                                        drift=source_drift)
    need(digest(BUILD / 'sim/simv') == '2e63524b92da663fd08401e1c2414363aa3a2732735feaceef55bd8be7ea59b3', 'Image drift')
    previous = bound(PRIOR, PRIOR_SHA)
    checks['formal760_coordinate_document'] = check(previous['pins'])
    oldrow = next(r for r in previous['instances'] if r['scope'] == SCOPE)
    bitmap_path = BASE / 'combined-bits.json'
    bitmap = bound(bitmap_path, book['output_pins'][str(bitmap_path)])
    need(len(bitmap['tests']) == len(set(bitmap['tests'])) == 762, 'Not formal762')
    row = bitmap['metrics']['fsm'][SCOPE]
    need(row == dict(width=28, checksum='3476102610', bits='0xdcc5780'), 'Latest port1 bitmap changed')
    db = BUILD / 'sim/simv.vdb/snps/coverage/db'
    shape_path = db / 'shape/fsm.verilog.shape.xml'
    design_path = db / 'design/verilog.design.xml'
    for rel in ('shape/fsm.verilog.shape.xml', 'design/verilog.design.xml'):
        need(digest(db / rel) == bitmap['design'][rel], 'Compiled identity drift: ' + rel)
    definitions = [n for n in xml(shape_path).iter('fsmdef') if n.get('chksum') == row['checksum']]
    need(len(definitions) == 1 and definitions[0].get('name') == 'wt_dcache_ctrl' and definitions[0].get('file') == '460', 'Wrong FSM module')
    definition = definitions[0]
    need(SCOPE in [n.get('name') for n in definition.findall('fsminst')], 'Instance binding absent')
    machine = definition.find('fsmshape/fsmfsm')
    need(machine.attrib == dict(name='state_q', id='0', width='3', line='262', chksum='3476102610'), 'Wrong machine coordinates')
    sourceinfo_path = db / 'auxiliary/verilog.sourceinfo.xml'
    fileinfo = next(n for n in xml(sourceinfo_path).iter('fileinfo') if n.get('id') == '460')
    need(fileinfo.get('name') == str(CTRL), 'Compiled file460 differs')
    module = next(n for n in xml(design_path).iter('srcdef') if n.get('name') == 'wt_dcache_ctrl')
    inst = next(n for n in module.findall('srcinst') if n.get('name') == 'gen_rd_ports[1].genblk1.i_wt_dcache_ctrl')
    need(module.get('chksum') == '1251950563' and inst.get('id') == '-2042', 'Compiled source hierarchy differs')
    states = machine.findall('state')
    names = {n.get('id'): n.get('name') for n in states}
    bitstring = format(int(row['bits'], 16), '028b')
    table = []
    for kind, nodes in (('State', states), ('Transition', machine.findall('transition'))):
        for node in nodes:
            position = len(table)
            name = node.get('name') if kind == 'State' else names[node.get('fromid')] + '->' + names[node.get('toid')]
            table.append(dict(machine='state_q', kind=kind, name=name, source_line=node.get('line'),
                              raw_position=position, compiled=node.attrib, hit=bitstring[position] == '1'))
    need(len(table) == 28, 'Shape width differs')
    missing = [x for x in table if not x['hit']]
    need([(x['kind'], x['name'], x['source_line'], x['raw_position']) for x in missing] ==
         [(x['kind'], x['name'], x['source_line'], x['raw_position']) for x in oldrow['missing']], 'Formal760/762 missing coordinates differ')
    need({(x['kind'], x['name']) for x in missing} == set(FACTS), 'Classification not exact full missing set')
    for x in missing:
        classification, lines, guard, explanation = FACTS[x['kind'], x['name']]
        x.update(classification=classification, normal_guard=guard, integrated_path_reason=explanation,
                 source_evidence=excerpt(CTRL, *lines), disabled_configuration_waiver_supported=False,
                 native_exclusion_qualified=False)
    contexts = [excerpt(CORE / 'cva6.sv', 1386, 1414), excerpt(CORE / 'ex_stage.sv', 533, 540),
        excerpt(CORE / 'ex_stage.sv', 595, 601), excerpt(CORE / 'load_store_unit.sv', 550, 587),
        excerpt(CORE / 'cache_subsystem/wt_cache_subsystem.sv', 175, 185),
        excerpt(CORE / 'cache_subsystem/wt_dcache.sv', 203, 249),
        excerpt(CORE / 'load_unit.sv', 337, 430), excerpt(CTRL, 260, 281),
        excerpt(CORE / 'cache_subsystem/wt_dcache_mem.sv', 164, 187),
        excerpt(CORE / 'cache_subsystem/wt_dcache_missunit.sv', 225, 234),
        excerpt(CORE / 'cache_subsystem/wt_dcache_missunit.sv', 345, 360),
        excerpt(CORE / 'cache_subsystem/wt_dcache_missunit.sv', 405, 429),
        excerpt(CORE / 'cache_subsystem/wt_dcache_missunit.sv', 473, 503),
        excerpt(CORE / 'include/cv64a6_imafdcv_sv39_config_pkg.sv', 48, 78),
        excerpt(CORE / 'include/build_config_pkg.sv', 23, 28), excerpt(ROOT / 'hardware/src/ara_soc.sv', 533, 565)]
    relevant_paths = {str(CTRL)} | {item['path'] for item in contexts}
    need(relevant_paths <= set(srcpins), 'Audit source missing frozen build pin')
    checks['cache_port1_relevant_sources'] = check({path: srcpins[path] for path in relevant_paths})
    need('assign dcache_req_to_cache[1] = dcache_req_ports_ex_cache[1];' in (CORE / 'cva6.sv').read_text(), 'Port1 connection differs')
    need('.req_port_o           (dcache_req_ports_o[1])' in (CORE / 'load_store_unit.sv').read_text(), 'Load producer differs')
    miss_case = CTRL.read_text().split('      MISS_REQ: begin', 1)[1].split('      MISS_WAIT: begin', 1)[0]
    need('state_d = IDLE' not in miss_case, 'Unexpected normal MISS_REQ->IDLE assignment')
    covered_kill = next(x for x in table if x['kind'] == 'Transition' and x['name'] == 'MISS_REQ->KILL_MISS')
    need(covered_kill['hit'], 'Existing integrated kill witness absent')
    target_positions = [6, 7, 21, 23, 27]
    scenario = dict(name='OTHER_PORT_REFILL_OVERLAPS_PORT1_LOAD_TAG_CHECK',
        level='Minimal legal cache-interface cycle fragment; software timing is not certified',
        setup=['cache_en_i=1, rst_ni=1, stall_i=0; normal cacheable DRAM A and B in different 32-byte lines',
               'MSHR already owns an accepted read A from port0/PTW or port2/accelerator, NOT port1; otherwise port1 is stuck in MISS_WAIT and cannot accept B',
               'B is cold; bare-mode or warm DTLB translation, no exception/flush, and load-buffer space',
               'Return A one cycle after B obtains its port1 SRAM grant; this is legal response timing, not an internal signal/state force'],
        cycles=[dict(cycle='C0', state_q='IDLE', conditions='B data_req=1, rd_ack_i=1, wr_cl_vld_i=0',
                     next_state='READ', effect='B grant; load_unit enters SEND_TAG; rd_ack_q becomes1'),
                dict(cycle='C1', state_q='READ', conditions='B tag_valid=1, kill_req=0, A load_ack=1 -> wr_cl_vld_i=1',
                     next_state='REPLAY_REQ', effect='B tag saved; refill steals SRAM readout and rd_ack_i=0; target transition raw21'),
                dict(cycle='C2', state_q='REPLAY_REQ', conditions='refill over, kill_req=0, rd_ack_i=1',
                     next_state='REPLAY_READ', effect='Replay grants B; rd_ack_q becomes1; target transition raw27'),
                dict(cycle='C3', state_q='REPLAY_READ', conditions='kill_req=0, wr_cl_vld_i=0, rd_ack_q=1, B any_hit=0',
                     next_state='MISS_REQ', effect='Saved B address miss; target transition raw23')],
        target_coordinates=[{k: x[k] for k in ('machine', 'kind', 'name', 'raw_position')} for x in missing if x['raw_position'] in target_positions],
        missing_states=2, missing_transitions=3, missing_coordinate_count=5,
        minimality='From prepared IDLE, one grant edge reaches READ; entering both replay states and exiting to MISS_REQ then requires three ordered edges. Four edges total for these five bins, excluding MSHR/cache/translation setup and completion.',
        completion='Allow B miss request/ack/return normally; check the known B word and successful completion. Do not count a killed/stalled/failed sample as verified coverage.',
        falsifiable_signals=['state_q', 'state_d', 'req_port_i.data_req', 'req_port_i.tag_valid', 'req_port_i.kill_req',
            'rd_ack_i', 'rd_ack_q', 'wr_cl_vld_i', 'rd_hit_oh_i', 'miss_req_o', 'miss_ack_i', 'miss_replay_i',
            'miss_rtrn_vld_i', 'req_port_o.data_rvalid', 'mshr_q.miss_port_idx', 'mshr_vld_q', 'load_ack'],
        alternative_discriminator='A read arbitration stall before B is granted only keeps IDLE; a refill after B leaves READ cannot witness raw21. Capture the C1 overlap, not just a cacheline boundary in software.',
        observed=False, simulation_launched=False, software_cycle_alignment_proven=False)
    pins = {**book['input_pins'], **book['output_pins'],
            **{path: sha for path, sha in srcpins.items() if digest(path) == sha}, **previous['pins'],
            str(BASE / 'admission-manifest.json'): BASE_SHA, str(PRIOR): PRIOR_SHA,
            str(sourceinfo_path): digest(sourceinfo_path), str(Path(__file__).resolve()): digest(Path(__file__).resolve())}
    prior_attempt = OUT / 'cache-port1-offline-admitted-717-20261006-01/target-hit-audit.json'
    history = json.loads(prior_attempt.read_bytes())
    pins[str(prior_attempt)] = digest(prior_attempt)
    return dict(schema='CACHE_PORT1_FROZEN762_SOURCE_COMPILED_CONDITION_AUDIT_V1',
        status='READONLY_STATIC_AUDIT_COMPLETE_NOT_NATIVE_WAIVER_OR_MEASURED_STIMULUS', population=762,
        baseline_manifest_sha256=BASE_SHA, pin_checks=checks, scope=SCOPE, raw_bitmap=row,
        formal760_coordinates_unchanged=True, compiled_module=definition.attrib, compiled_machine=machine.attrib,
        compiled_source_module=module.attrib, compiled_source_instance=inst.attrib, compiled_fileinfo=fileinfo.attrib,
        raw_coordinate_semantics='28-bin MSB-first string: 8 XML states then 20 XML transitions; not LSB bit numbering and not an official DVE denominator',
        source_line_semantics='Compiled line262 labels several edges also reachable through functional IDLE assignments; source guards, not labels alone, determine reset-only status.',
        actual_port1_producer='CVA6 ex_stage/load_store_unit/i_load_unit; PTW is port0, not port1',
        disabled_configuration_waiver_supported=False, disabled_configuration_missing_coordinates=0,
        normally_feasible_missing_states=3, normally_feasible_missing_transitions=11,
        reset_only_missing_transitions=1, reset_only_name='MISS_REQ->IDLE',
        full_formal_reachability_proof=False,
        reachability_scope='Constructive local guards with frozen connected producer/arbiters; listed external timing/setup assumptions must be exercised by any later integrated test.',
        whole_source_tree_matches_frozen_build=not source_drift,
        source_drift_scope='All audit-relevant source pins must match; unrelated source-tree drift is recorded, not silently admitted as frozen source.',
        existing_integrated_kill_evidence=covered_kill, missing=missing, full_compiled_coordinate_table=table,
        source_bound_contexts=contexts, recommended_shortest_scenario=scenario,
        prior_attempt=dict(path=str(prior_attempt), replay_FSM_sample_observed=history['replay_FSM_sample_observed'],
                           new_targets=history['new_targets'], cycle_level_refill_cause_proven=history['cycle_level_refill_cause_proven']),
        conclusion='Reject a blanket port1 disabled waiver. Retain three states and eleven functional transitions; treat MISS_REQ->IDLE as reset-only, not unreachable across reset. Target other-port refill versus an already granted scalar-load tag-check for five gaps.',
        RTL_modified=False, sealed_tools_modified=False, EDA_launched=False, exclusions_applied=False,
        official_percentages_recomputed=False, pins=pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    need(output.parent == OUT and not output.exists(), 'Fresh independent JSON output required')
    result = collect()
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(output), sha256=digest(output), status=result['status'],
                          population=762, missing_states=3, missing_transitions=12,
                          reset_only_transitions=1, disabled_configuration_waiver_supported=False,
                          recommended_scenario_missing_coordinates=5, pin_checks=result['pin_checks'])))
