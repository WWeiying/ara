"""Exact cause[62:6] static review; no EDA, RTL edits or exclusions."""
import json
from pathlib import Path
import re

import review_csr_rvh_debug796_readonly_agent_20261008 as util

OUTPUT = util.OUT / 'scoreboard-cause796-readonly-agent-20261008-01.json'
BITS = list(range(6, 63))
MASK = sum(1 << bit for bit in BITS)
CORE = 'hardware/deps/cva6/'
FILES = [CORE + name for name in (
    'core/cva6.sv', 'core/include/ariane_pkg.sv', 'core/include/riscv_pkg.sv',
    'core/include/build_config_pkg.sv', 'core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'core/scoreboard.sv', 'core/issue_stage.sv', 'core/issue_read_operands.sv',
    'core/id_stage.sv', 'core/decoder.sv', 'core/frontend/frontend.sv',
    'core/frontend/instr_queue.sv', 'core/ex_stage.sv', 'core/branch_unit.sv',
    'core/fpu_wrap.sv', 'core/load_store_unit.sv', 'core/load_unit.sv', 'core/store_unit.sv',
    'core/cva6_mmu/cva6_mmu.sv', 'core/pmp/src/pmp_data_if.sv', 'core/acc_dispatcher.sv',
    'core/cvxif_fu.sv', 'core/commit_stage.sv', 'core/csr_regfile.sv')]
FILES += ['hardware/deps/common_cells/src/shift_reg.sv',
          'hardware/deps/common_cells/src/shift_reg_gated.sv',
          'hardware/deps/common_cells/include/common_cells/registers.svh',
          'hardware/src/ara.sv', 'hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv',
          'hardware/src/ara_sequencer.sv', 'hardware/src/vlsu/addrgen.sv',
          'hardware/src/vlsu/vlsu.sv', 'hardware/src/ara_dispatcher.sv']


def independent_chain(name):
    if re.fullmatch(r'(?:ex_ex_i|ex_i)\[[123]\]\.cause', name):
        return 'PINNED_SCALAR_LSU_OR_FPU_PRODUCER'
    if name == 'ex_i.cause' or name == 'instruction_o.ex.cause':
        return 'PINNED_FETCH_DECODER_PRODUCER'
    if name.startswith(('decoded_instr_i', 'issue_instr')):
        return 'PINNED_DECODE_ISSUE_COPY'
    return None


def ownership_conflict(scope, name, record):
    if record['scope'] != scope:
        return record['directive'] == 'WHOLE_SCOPE' and scope.startswith(record['scope'] + '.')
    if record['directive'] == 'WHOLE_SCOPE':
        return True
    match = re.match(r'^Toggle(?: (?:0to1|1to0))? (\S+)', record['directive'])
    if not match:
        return False
    token = match[1]
    return token == name or name.startswith(token + '.') or token.startswith(name + '.') or name.startswith(token + '[')


def collect():
    rank = json.loads(util.RANK.read_bytes())
    assert rank['population'] == 796
    pins = dict(rank['pins'])
    pins[str(util.RANK)] = util.digest(util.RANK)
    book = json.loads((util.BUILD / 'build-source-pins.json').read_bytes())
    texts, drift = {}, []
    for rel in FILES:
        path = util.ROOT / rel
        actual = util.digest(path)
        expected = book[str(path)]
        pins[str(path)] = actual
        texts[rel] = path.read_text()
        if actual != expected:
            drift.append(dict(path=str(path), original_compile_sha256=expected, current_sha256=actual))
    assert [r['path'] for r in drift] == [str(util.ROOT / 'hardware/src/ara_dispatcher.sv')]
    shape = util.xml(util.BUILD / 'sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.shape.xml')
    defs = {}
    for node in shape.iter('tgldef'):
        defs.setdefault(node.get('chksum'), []).append(node)
    el = next(Path(p) for p in pins if p.endswith('/combined.el'))
    scope, directives = None, []
    for line_num, line in enumerate(el.read_text().splitlines(), 1):
        if line.startswith('INSTANCE: '):
            scope = line.split(': ', 1)[1]
        elif scope and (line.startswith('Toggle ') or line == 'WHOLE_SCOPE'):
            directives.append(dict(scope=scope, line=line_num, directive=line))
    rows = [r for r in rank['objects'] if ('scoreboard' in r['scope'] or 'issue' in r['scope'] or 'decoder' in r['scope'])
            and r['attributes']['name'].endswith('.cause')]
    eligible, hold = [], []
    for row in rows:
        name, attr = row['attributes']['name'], row['attributes']
        assert attr['left'] == '63' and attr['right'] == '0'
        definition = defs[row['checksum']]
        assert len(definition) == 1
        node = next(n for n in definition[0].find('tglshape') if n.get('name') == name)
        assert all(attr[k] == v for k, v in node.attrib.items())
        assert util.digest(Path(row['source_file'])) == row['expected_frozen_source_sha256']
        overlaps = [r for r in directives if ownership_conflict(row['scope'], name, r)]
        assert not overlaps, 'Existing field/parent ownership requires exact-mask HOLD'
        assert row['both_direction_EL_removed'] == row['single_direction_EL_HOLD'] == 0
        coords = [p for p in row['coordinates'] if 6 <= (p - attr['serialized_offset']) // 2 <= 62]
        assert len(coords) == 114
        chain = independent_chain(name)
        item = dict(scope=row['scope'], checksum=row['checksum'], name=name,
                    compiled_attributes=attr, compiled_parameters=definition[0].get('param'),
                    selected_physical_bits=BITS, physical_mask=hex(MASK), selected_residual_slots=coords,
                    selected_slots=len(coords), raw_rank_missing=row['net_missing_serialized_positions'],
                    complement_protected_bits=[0, 1, 2, 3, 4, 5, 63], existing_EL_overlaps=overlaps,
                    source_bit_pair_order_not_native_direction_order=True,
                    status='SOURCE_PROVEN_AFTER_RESET_NOT_NATIVE_APPROVED' if chain else 'HOLD_ACC_COMPILED_PRODUCER_UNBOUND',
                    chain=chain or 'Shared mem/forwarding/commit depends on ACC_WB4, or is ACC_WB4 itself; old dispatcher body unavailable.')
        (eligible if chain else hold).append(item)
    assert len(eligible) == 14 and len(hold) == 46
    assert MASK == 0x7fffffffffffffc0
    source_inventory = {}
    for rel, text in texts.items():
        source_inventory[rel] = [dict(line=i + 1, text=line.strip()) for i, line in enumerate(text.splitlines())
                                if re.search(r'cause|(?:\bex|exception|issue_[qn]|mem_[qn])[^;]*(?:<=|=(?!=))', line)]
    proofs = {
        'fetch_decoder': 'instr_queue RVC output324..327 defaults cause0 every evaluation and overrides342/344/346/366/368 with enumerated fetch faults. Non-RVC397/399 always assigns bounded code. frontend encodes MMU/cache exceptions as frontend enum; no raw cause passthrough into decoder. id_stage336 connects fetch_entry.ex. decoder1781..1782 defaults interrupt0/ex=ex_i, overrides only defined sync/debug codes0..24 or INTERRUPTS. cva6:367..378 defines standard IRQ causes=(1<<63)|IRQ1..12. RVSCLIC0 disables arbitrary clic_irq_cause input1842..1844. Result[62:6]=0 in valid AND invalid cycles.',
        'decode_issue': 'id_stage issue_n holds issue_q, loads decoded_instruction struct, only changes valid on ack/flush;459..465 resets issue_q0 and captures issue_n. scoreboard190 assigns issue_instr_o=decoded_instr_i; trans_id changes do not affect cause. issue_stage194 forwards issue_instr_sb_iro[0];227/267 connect same data to read-operands. These issue copies do NOT depend on mem_q/ACC completion.',
        'FLU0': 'branch_unit120 sets branch_exception_o.cause=INSTR_ADDR_MISALIGNED=0 on every evaluation, valid default0. ex_stage342 -> cva6 flu_exception -> WB0. ALU/CSR/mul result mux is not a cause producer. WB0 was absent from residual cause rank; do not count it as new gain.',
        'FPU3': 'fpu_wrap610 assigns {59h0, fpu_status}; valid=0 at611. Status width5, protects fflags bits4:0. Even when invalid/not selected, cause high is explicitly0; ex_stage453 -> cva6:829 FPU_WB3 -> issue ex_ex_i[3] -> scoreboard ex_i[3]. No claim about other unassigned exception payload fields.',
        'LSU1_2': 'load_store_unit705 defaults scalar misaligned exception struct0; sync constants <=23 at751..827. Shared ACC misalignment input is scalar logic: ara.sv576 from addrgen102 constant0, VLSU865..875 also selects0. When cast into exception struct atLSU453 it is whole0, not a full arbitrary exception source. MMU misaligned_ex_q748 resets0,756 captures;518 defaults lsu_exception=misaligned_ex_q, all page/guest/access overrides584..716 are constants<=23. PMP119 copies then overrides130/132 with7/5. Arbitration428 copies MMU, ACC-state465 sets scalar exception0. load_unit213 copies cause; store_unit154 copies struct. LSU599..616 shift regs; shift_reg_gated56 FFL resets full data0, Depth0 bypass. All phases bounded, regardless valid. cva6:819 STORE_WB1/:824 LOAD_WB2 -> issue -> scoreboard.',
        'ACC4_HOLD': 'acc_dispatcher387 forwards entire acc_resp_i.acc_resp.exception with no truncation; cva6:862 maps ACC_WB4. EnableAccelerator1 via RVV1; CvxifEn0 does not disable this port. Current ara_dispatcher default1100 default0;5286 generates illegal2; all other exception assignments copy Ara response. Ara sequencer529 default0 and1021 muxes addrgen q/d/input; addrgen268 default0,391/514 alignment4/6,521/535 copied MMU,562 reset0; VLSU QBS/AKV954..1003 choose MMU or illegal/access2/5 and store-B paths. HOWEVER dispatcher current SHA differs from compiled source pin. Treat ACC port full-width boundary as UNPROVEN for compiled796; current writer inventory is not old-source proof. No claim closing every terminal/store-B producer for compiled ACC.',
        'scoreboard_conditional_induction': 'Base scoreboard360 resets ALL mem_q entries to sb_mem_t0. Step204 defaults mem_n=mem_q;213 loads decoded entry;257 copies ex_i ONLY if valid;260 copies ex_i.cause for FPU even if invalid. Other writers update result/rd/bp/valid/issued/cancelled only; flush298 clears ex.valid without cause.365 captures mem_n,366 overrides rd only. If decoder and ALL FIVE WB cause highs are bounded, mem_q/n cause highs inductively0 even in stale/unissued/invalid entries. fwd339 copies mem_q.sbe; preview342/343 only valid/result. commit176 copies mem_q.sbe, only trans_id changes. ACC4 missing compiled proof prevents unconditional conclusion for all mem/fwd/commit copies.',
        'CSR_protected': 'mcause/scause are architecturally writable FULL64; no selected object is in csr_regfile scope. CSR data/result bus is not a source of pipeline exception cause. Commit exception output starts0 and merges bounded CSR error/scoreboard ex, but this does not constrain software-written mcause/scause state. bit63 is interrupt/trap discriminator, not numeric cause upper padding; flags4:0 and code5:0 all retained.',
    }
    # Text pins and explicit token checks bind the reviewed induction to actual code.
    assert "assign fpu_exception_o.cause = {59'h0, fpu_status};" in texts[CORE + 'core/fpu_wrap.sv']
    assert "mem_q            <= '{default: sb_mem_t'(0)};" in texts[CORE + 'core/scoreboard.sv']
    assert 'assign acc_exception_o = acc_resp_i.acc_resp.exception;' in texts[CORE + 'core/acc_dispatcher.sv']
    assert 'localparam CVA6ConfigSclicExtEn = 0;' in texts[CORE + 'core/include/cv64a6_imafdcv_sv39_config_pkg.sv']
    result = dict(status='EXACT_CAUSE62_6_PARTIAL_PROOF_ACC_SCOREBOARD_HOLD', population=796,
        selected_range='cause[62:6]', physical_mask=hex(MASK), bits_per_copy=57, slots_per_copy=114,
        eligible=eligible, HOLD=hold, eligible_slots=1596, HOLD_slots=5244, total_selected_rank_slots=6840,
        eligible_physical_bits=798, total_candidate_physical_bits=3420, source_proofs=proofs,
        source_reference_and_bulk_writer_inventory=source_inventory, source_drift=drift,
        protected=dict(cause_bits=[0,1,2,3,4,5,63], FPU_fflags_bits=[0,1,2,3,4],
                       CSR_mcause_scause='All64 bits always protected; software full-width writes.',
                       no_whole_exception_or_struct_waiver=True, other_payloads_and_controls=True),
        dedup=dict(existing_target_EL_overlap=0, rank_both_and_single_direction_removed=0,
                   multiple_scope_copies_distinct_physical_identity=True,
                   no_native_direction_order_inferred=True, source_and_compiled_not_additive=True),
        config_boundary='Exact pinned XLEN64/RVSCLIC0/RVXHCLIC0/CvxifEn0/EnableAccelerator1/NrWbPorts5/scoreboard8 build. RVSCLIC1 cause packs id/level/privilege into bits6..26 and INVALIDATES broad decoder/mem high-zero proof. RV32/type/width/custom interrupt or accelerator contract changes require re-review.',
        validity_boundary='Valid reset plus settled evaluation. Known-zero reset applies to id/scoreboard/MMU/pipeline storage; combinational sources have explicit default/cause assignments. No startup-X/force/fault waiver. Invalid-cycle data included; no valid-only shortcut.',
        parent_next='Source-proof review can proceed for14 independent cause leaves1596 slots. Obtain original hash-matching Ara dispatcher body and close complete ACC producer chain before accepting46 ACC-dependent leaves5244 slots. Native mask qualification/population application remain separate.',
        EDA_started=False, RTL_changed=False, exclusions_generated=False, measured_gain=None,
        official_denominator=None, DCSR_native_deferred=True, input_pins=pins)
    pins[str(Path(__file__).resolve())] = util.digest(Path(__file__).resolve())
    for path, expected in pins.items():
        assert util.digest(Path(path)) == expected, 'Evidence drift: ' + path
    return result


if __name__ == '__main__':
    result = collect()
    with OUTPUT.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(OUTPUT, util.digest(OUTPUT))
