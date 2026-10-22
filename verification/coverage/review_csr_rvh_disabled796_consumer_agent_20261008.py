"""Successor offline review: disabled functionality, never a known-value proof."""
import json
from pathlib import Path
import re

import review_csr_rvh_debug796_readonly_agent_20261008 as prior

OUTPUT = prior.OUT / 'csr-rvh-disabled796-consumer-agent-20261008-01.json'
OLD_SHA = '12fc64dca0115109c0afe668e81afc03efff4b182233833c18c78d534de1e13a'
ROLE_SPANS = {
    'declaration_not_driver': [(270, 270), (283, 288)],
    'RVH_guarded_CSR_read_or_VS_alias': [(443, 451), (569, 599), (651, 653)],
    'RVH_guarded_default_feedback': [(1097, 1099), (1111, 1125)],
    'RVH_guarded_VS_interrupt_mask_write': [(1248, 1262)],
    'RVH_guarded_CSR_write': [(1450, 1475), (1504, 1527), (1702, 1704)],
    'RVH_guarded_trap_delegation_consumer': [(2060, 2070)],
    'RVH_guarded_trap_payload_writer': [(2124, 2139), (2172, 2188)],
    'RVH_parameter_mux_isolated_IRQ_output': [(2492, 2493)],
    'RVH_branch_counter_privilege_consumer': [(2503, 2564)],
    'RVH_guarded_reset_no_initialization_when_disabled': [(2873, 2885)],
    'RVH_guarded_capture_no_update_when_disabled': [(2969, 2982)],
}


def collect():
    assert prior.digest(prior.REPORT) == OLD_SHA
    previous = json.loads(prior.REPORT.read_bytes())
    assert prior.collect() == previous
    pins = dict(previous['input_pins'])
    pins[str(prior.REPORT)] = OLD_SHA
    manifest_path = prior.BUILD / 'sim/vcs_source_manifest.json'
    manifest = json.loads(manifest_path.read_bytes())
    pins[str(manifest_path)] = prior.digest(manifest_path)
    book = json.loads((prior.BUILD / 'build-source-pins.json').read_bytes())
    corpus = [r for r in manifest['files'] if Path(r['path']).suffix in ('.sv', '.svh', '.v')]
    pattern = re.compile(r'\b(?:' + '|'.join(prior.HREGS) + r')_[qd]\b')
    drift, matches = [], []
    for record in corpus:
        path = Path(record['path'])
        actual = prior.digest(path)
        expected = book[str(path)]
        pins[str(path)] = actual
        found = [dict(line=i + 1, text=line.strip()) for i, line in enumerate(path.read_text().splitlines())
                 if pattern.search(line)]
        if actual != expected:
            drift.append(dict(path=str(path), compiled_source_sha256=expected,
                              current_sha256=actual, current_target_references=found,
                              historical_absence_proved=False))
        if found:
            matches.append(dict(path=str(path), references=found))
    assert len(corpus) == 450
    assert len(matches) == 1 and matches[0]['path'].endswith('/core/csr_regfile.sv')
    references = []
    for row in matches[0]['references']:
        roles = [role for role, spans in ROLE_SPANS.items() if any(a <= row['line'] <= b for a, b in spans)]
        assert len(roles) == 1, 'Unreviewed/ambiguous consumer reference: ' + str(row)
        references.append(dict(row, classification=roles[0]))
    additional = ('hardware/deps/cva6/core/cva6_clic_controller.sv',
                  'hardware/deps/cva6/core/include/rvfi_types.svh',
                  'hardware/deps/cva6/core/cva6_rvfi.sv',
                  'hardware/deps/cva6/core/cva6_rvfi_probes.sv',
                  'hardware/deps/cva6/core/commit_stage.sv')
    supplemental = []
    for rel in additional:
        path = prior.ROOT / rel
        if str(path) in book:
            assert prior.digest(path) == book[str(path)], 'Relevant consumer drift: ' + rel
        else:
            assert rel.endswith('/cva6_clic_controller.sv'), 'Unexpected unbound consumer'
            supplemental.append(dict(path=str(path), role='Supplemental uncompiled CLIC source only; no compiled identity claim. cva6 RVSCLIC0 generate removes instance; CSR parameter mux is independent primary isolation proof.'))
            pins[str(path)] = prior.digest(path)
    stem_consumers = {
        'hcounteren': 'CSR590; counter privilege checks2534/2537/2539/2552/2555/2557 are wholly in RVH branch2503..2564. RVH0 alternative2565 onward uses only mcounteren/scounteren.',
        'hedeleg': 'CSR572; trap delegation2063 wholly RVH block2060..2070; masked self feedback1464 and default1119 are RVH guarded.',
        'hideleg': 'CSR575; VSIE/VSIP reads447/451 and writes1251/1258 RVH guarded; trap2061 RVH guarded; irq_ctrl_o.hideleg2492 mux disconnects backing q. cva6:1223 -> irq_ctrl_csr_id -> id_stage:786 -> decoder interrupt delegation1901..1917 itself RVH guarded.',
        'hgeie': 'CSR599; output2493 parameter mux disconnects backing q. cva6:1223 -> irq_ctrl_csr_id -> CLIC1717. CLIC generated only RVSCLIC at1707 (frozen0); hgeie uses78/89/108/115 require RVXHCLIC (frozen0). Mux isolation is primary proof, not assumptions on external IRQ stimulus.',
        'htinst': 'Only functional read596; write/trap1519..1523 and2124..2137 RVH guarded. No other q consumer or d alias.',
        'htval': 'Only functional read593; write/trap1512..1516 and2124..2138 RVH guarded. No other q consumer or d alias.',
        'mtinst': 'Only functional read652; write1703 and machine-trap2172..2188 RVH guarded. No RVH0 trap payload consumer or d alias.',
    }
    objects = []
    for row in previous['disabled_uninitialized_HOLD']:
        name = row['name']
        stem = name.rsplit('_', 1)[0]
        objects.append(dict(row, source_classification='CONFIG_DISABLED_UNOBSERVABLE_STORAGE',
                            const_claim=False, source_core_consumer_chain_complete=True,
                            consumers=stem_consumers[stem],
                            compiled_population_waiver_status='HOLD' if drift else 'STATIC_ELIGIBLE_NOT_NATIVE_APPROVED'))
    assert len(objects) == 14 and sum(r['residual_count'] for r in objects) == 1792
    excerpts = {}
    for rel, spans in {
        'hardware/deps/cva6/core/csr_regfile.sv': [(338, 339), (378, 386), (440, 453), (569, 601),
            (650, 656), (1095, 1126), (1247, 1264), (1450, 1475), (1504, 1527),
            (1702, 1707), (2040, 2073), (2124, 2141), (2172, 2190), (2439, 2494),
            (2503, 2585), (2612, 2639), (2873, 2885), (2969, 2982), (3057, 3092)],
        'hardware/deps/cva6/core/cva6.sv': [(750, 789), (1155, 1164), (1204, 1225), (1707, 1741)],
        'hardware/deps/cva6/core/decoder.sv': [(1895, 1929)],
        'hardware/deps/cva6/core/cva6_clic_controller.sv': [(55, 122)],
        'hardware/deps/cva6/core/commit_stage.sv': [(210, 228), (391, 409)],
        'hardware/deps/cva6/core/include/rvfi_types.svh': [(135, 171)],
    }.items():
        lines = (prior.ROOT / rel).read_text().splitlines()
        excerpts[rel] = [dict(first=a, last=b, text='\n'.join(lines[a-1:b])) for a, b in spans]
    result = dict(status='SOURCE_CONFIG_DISABLED_CLASSIFICATION_COMPILED_POPULATION_HOLD' if drift else 'SOURCE_CONFIG_DISABLED_CLASSIFICATION_NOT_NATIVE_APPROVED',
        population=796, scope=prior.SCOPE, checksum='1176918775', objects=objects,
        config=previous['config'], compiled_parameters=previous['compiled_parameters'],
        compileparam_boundary=previous['composite_parameter_note'],
        exact_csr_addresses=dict(hcounteren='0x606', hedeleg='0x602', hgeie='0x607', hideleg='0x603',
                                 htinst='0x64a', htval='0x643', mtinst='0x34a'),
        csr_entry_proof='conv_csr_addr338 selects raw csr_addr for RVH0; no VS remapping alias. Seven CSR reads each choose read_access_exception=1 and never q; CSR write/SET/CLEAR each choose update_access_exception=1 and never d. CSR_SET/CLEAR operands are composed from guarded csr_rdata. VSIE/VSIP aliases reject too. Privilege rejection also blocks csr_we/read2478..2481; when M/debug privilege is sufficient, RVH guards independently reject unsupported addresses. Decoder need not reject CSR opcode early: unsupported-address decode is in CSR regfile.',
        exception_chain='CSR exception_ctrl2616..2632 converts read/update/privilege rejection to valid ILLEGAL_INSTR cause2. cva6:1209 forwards csr_exception_csr_commit -> commit_stage via1161. commit210..228 suppresses commit_csr/writeback/ack on exception; commit391..409 forwards exception to architectural trap. Waiver does not cover this live rejection chain.',
        noninterference='For fixed compile RVH0 and arbitrary normal inputs, replacing ANY seven q/d values (including X) cannot alter a functional output or initialized architectural state: every use is in an inactive procedural parameter branch, inactive capture/reset branch, or disconnected parameter mux. No dependence on reset making values known, zero extension, assertknown, X-to0 transitions, legal counter duration or missing coverage hits.',
        export_proof='CSR rvfi_csr_o3057..3092 and pinned RVFI_PROBES_CSR_T135..171 omit all seven objects. No active d alias beyond guarded q captures. Only IRQ exports are hideleg/hgeie, parameter-mux isolated. 450 current compiled-list HDL sources contain direct/hierarchical target identifiers only in csr_regfile;447 match original compiled pins,3 are current drift, so historical external hierarchical absence is NOT proved for them.',
        complete_local_reference_inventory=references, evidence_excerpts=excerpts,
        supplemental_not_compiled_evidence=supplemental,
        compiled_hdl_scan=dict(files=len(corpus), matching_original_build_pins=len(corpus)-len(drift),
                               reference_files=matches, source_drift_HOLD=drift),
        decision=dict(valid_source_classification_for_all_seven=True, classification='CONFIG_DISABLED_UNOBSERVABLE_STORAGE',
                      classification_is_project_proposal_not_automatic_tool_policy=True,
                      current_full_compiled_consumer_closure=not bool(drift),
                      exact_population_waiver_approved=False, new_exclusions=0,
                      potential_exact_scope_objects=14, physical_q_plus_d_bits=896, residual_unnamed_pair_slots=1792,
                      source_and_compiled_evidence_not_additive=True, existing796EL_overlap=0,
                      reason_for_population_HOLD='Recover/review three original hash-matching source bodies or existing sealed proof of no hierarchical bypass; current absence cannot substitute for historical compiled identity.' if drift else 'Separate policy/native approval required.'),
        waiver_boundaries=['Only seven exact q/d[63:0] objects in this compiled instance/checksum; no wholeCSR/wholeH unit, CSR bus, IRQ outputs, illegal-access control or functional consumers excluded.',
            'Configuration-disabled nonfunctional storage category only; not constant-zero/known-value/initialization-X waiver. Binary toggle selectors and any native X-related metric semantics require separate exact qualification.',
            'Invalid immediately for RVH1: restore all14 objects before any RVH1 build/report; re-review access, masks, trap, counters and IRQ consumers. No inheritance by signal name across compiled definitions.',
            'Any config/source/type/width/checksum/forwarding/export/hierarchical connection drift requires re-review. RVH0 cannot be inferred from opaque CVA6Cfg=-1 alone.',
            'Force/fault/backdoor access is outside normal functional proof; a supported new functional or observation export demands explicit re-review rather than silently waiving it.'],
        DCSR28_native_deferred=True, debug_other_fields_still_protected=True,
        EDA_started=False, RTL_changed=False, native_approval=False, measured_gain=None,
        input_pins=pins)
    pins[str(Path(__file__).resolve())] = prior.digest(Path(__file__).resolve())
    for path, expected in pins.items():
        assert prior.digest(Path(path)) == expected, 'Read-time drift: ' + path
    return result


if __name__ == '__main__':
    report = collect()
    with OUTPUT.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(OUTPUT, prior.digest(OUTPUT))
