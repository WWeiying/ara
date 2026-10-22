"""Conservative static view of the existing residual ranking; no EDA."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'dynamic-toggle785-static-ranking-agent-20261008-01.json'
RANK_SHA = '14fe38eb7cd5430e5167321656664d854f9056c2750a6658476b8505de9afaf4'
BOOK = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert digest(RANK) == RANK_SHA
    assert digest(BOOK) == BOOK_SHA
    original = json.loads(RANK.read_bytes())
    book = json.loads(BOOK.read_bytes())
    pins = {str(RANK): RANK_SHA, str(BOOK): BOOK_SHA}
    sources = [
        'hardware/src/ara_soc.sv', 'hardware/src/ara_system.sv',
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'hardware/deps/cva6/core/issue_read_operands.sv',
        'hardware/deps/cva6/core/load_unit.sv',
        'hardware/deps/cva6/core/store_unit.sv',
        'hardware/deps/cva6/core/cva6_mmu/cva6_ptw.sv',
    ]
    for relative in sources:
        path = ROOT / relative
        assert digest(path) == book[str(path)], 'Frozen source drift: ' + relative
        pins[str(path)] = book[str(path)]
    ranked, removed, observers = [], [], []
    for row in original['ranking']:
        if '.i_ara_cvxif_dut_bind' in row['scope']:
            observers.append(row['scope'])
            continue
        kept = []
        for obj in row['objects']:
            if obj['partial_EL_direction_binding_HOLD']:
                removed.append(dict(scope=row['scope'], name=obj['name'],
                                    upper_slots=obj['missing_binary_positions']))
            else:
                kept.append(obj)
        if kept:
            ranked.append(dict(scope=row['scope'], checksum=row['checksum'], objects=kept,
                               missing_binary_positions=sum(o['missing_binary_positions'] for o in kept)))
    ranked.sort(key=lambda row: -row['missing_binary_positions'])
    classes = [
        dict(fields=['boot_addr_i'], status='SOC_SOURCE_CONSTANT_NATIVE_HOLD',
             chain=['ara_soc.sv:84 DRAMBase=64\'h80000000',
                    'ara_soc.sv:628 system.boot_addr_i(DRAMBase)',
                    'ara_system.sv:62 input64', 'ara_system.sv:180 CVA6.boot_addr_i(boot_addr_i)'],
             boundary='Exact propagated input only; not functional PC/address signals.'),
        dict(fields=['hart_id_i'], status='SOC_SOURCE_CONSTANT_NATIVE_HOLD',
             chain=['ara_soc.sv:531 hart_id=0', 'ara_soc.sv:629 system.hart_id_i(hart_id)',
                    'ara_system.sv:132 zero extend3 to64', 'ara_system.sv:181 CVA6.hart_id_i(hart_id)'],
             boundary='Copied hartid fields require independent complete writer tracing.'),
        dict(fields=['load_unit.tinst_o', 'load_unit.hs_ld_st_inst_o', 'load_unit.hlvx_inst_o',
                     'load_unit.ex_o.tval2', 'load_unit.ex_o.tinst', 'load_unit.ex_o.gva',
                     'store_unit.hs_ld_st_inst_o', 'issue_read_operands.tinst_o'],
             status='RVH0_EXPLICIT_ZERO_OUTPUT_CANDIDATES_NATIVE_HOLD',
             chain=['config_pkg:31 HExtEn=0; :107 RVH=HExtEn',
                    'ara_soc.sv:534..565 configuration preserves RVH',
                    'load_unit.sv:192..217 explicit ternary',
                    'store_unit.sv:143 explicit ternary', 'issue_read_operands.sv:291 explicit ternary'],
             boundary='Internal unassigned/unreset tinst_q is not proven known zero.'),
        dict(fields=['shared_tlb_update_o.g_content', 'shared_tlb_update_o.vmid'],
             status='RVH0_PTW_OUTPUT_CANDIDATES_NATIVE_HOLD',
             chain=['cva6_ptw.sv:219 g_content=0', 'cva6_ptw.sv:224 vmid RVH ternary'],
             boundary='TLB copies need all reset/write paths; ordinary pte.ppn/satp/asid remain dynamic.'),
        dict(fields=['DebugEn0 families'], status='REJECT_CONFIG_PREMISE',
             chain=['config_pkg:152 DebugEn=1', 'ara_soc.sv:534..565 no DebugEn override'],
             boundary='No DebugEn0 waiver rationale for this configuration.'),
    ]
    result = dict(status='CONSERVATIVE_STATIC_RESIDUAL_NOT_DYNAMIC_GAIN_OR_NATIVE_DENOMINATOR',
                  population=785, original_ranking_sha=RANK_SHA, input_pins=pins,
                  partial_objects_removed=removed, observer_scopes_removed=observers,
                  ranking=ranked, source_constant_candidate_classes=classes,
                  arrays_and_MDA_not_counted=True, no_direction_label_inference=True,
                  no_official_percentage_projection=True, EDA_launched=False,
                  constant_candidates_applied=False,
                  remaining_obligations=['Exact compiled field/type/width/checksum binding',
                      'Actual native all-population direction evidence and existing EL difference',
                      'All writers/reset proof for each propagated copy',
                      'Preserve interfaces/dynamic addresses/PC and all complement points'])
    for path, expected in pins.items():
        assert digest(Path(path)) == expected
    target = OUT / 'conservative-toggle785-static-agent-20261008-01.json'
    with target.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(target, digest(target))
    print('REMOVED', len(removed), 'PARTIAL;', len(observers), 'OBSERVER SCOPES')
    for row in ranked[:15]:
        print(row['missing_binary_positions'], row['scope'])


if __name__ == '__main__':
    main()
