"""Small exact789 residual check using sealed785 coordinates plus four suffixes."""
import hashlib
import json
from pathlib import Path
import re
import targeted_toggle_evidence_v2 as toggle

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'conservative-toggle785-static-agent-20261008-01.json'
RANK_SHA = '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'
BASE = OUT / 'csr-cause-wlrl-offline-admitted789-agent-20261008-02'
BASE_SHA = '810a9531e1e7a7edaece3fcec19e90e47fee3530e641f824aaed49e8deb3522d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(RANK) == RANK_SHA
    assert sha(BASE / 'admission-manifest.json') == BASE_SHA
    rank = json.loads(RANK.read_bytes())
    base = json.loads((BASE / 'admission-manifest.json').read_bytes())
    assert base['coverage_admitted'] is True
    authority = dict(base['input_pins'], **base['output_pins'])
    ledger = BASE / 'combined-inputs.txt'
    assert sha(ledger) == authority[str(ledger)]
    inputs = ledger.read_text().splitlines()
    prefix_path = OUT / 'valu-restart-offline-admitted785-agent-20261008-01/combined-inputs.txt'
    assert sha(prefix_path) == authority[str(prefix_path)]
    assert len(inputs) == len(set(inputs)) == 790
    assert inputs[:786] == prefix_path.read_text().splitlines()
    selected = []
    for row in rank['ranking']:
        scope = row['scope']
        for obj in row['objects']:
            group = None
            if scope.endswith('.lsu_i') and obj['name'] in (
                'cva6_misaligned_exception.tval', 'misaligned_exception.tval',
                'load_exception_o.tval', 'store_exception_o.tval', 'ld_ex.tval'):
                group = 'SCALAR_MISALIGN_TVAL_PRODUCER_AND_RETURN'
            elif scope.endswith('.i_scoreboard') and re.match(r'^(?:mem_[qn]|fwd_o.sbe|commit_instr_o)\[\d+\].*(?:\.ex\.tval)$', obj['name']):
                group = 'SCOREBOARD_TVAL_GENERIC_DYNAMIC_NOT_ALL_SLOTS_GUARANTEED'
            elif scope.endswith('.i_itlb') and re.match(r'^content_[qn]\[\d+\]\.pte\.ppn$', obj['name']):
                group = 'ITLB_NORMAL_PPN_PHYSICAL_RANGE_BOUND'
            if group:
                assert not obj['partial_EL_direction_binding_HOLD']
                selected.append(dict(scope=scope, checksum=row['checksum'], group=group,
                    name=obj['name'], width=obj['width'], coordinates=obj['coordinates']))
    scopes = set(o['scope'] for o in selected)
    pins = {str(RANK): RANK_SHA, str(BASE / 'admission-manifest.json'): BASE_SHA,
            str(ledger): sha(ledger), str(prefix_path): sha(prefix_path)}
    suffix = []
    for path in inputs[786:]:
        files = list((Path(path) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        assert len(files) == 1
        rows, seal = toggle.rows(files[0], scopes)
        assert seal == authority[str(files[0])]
        pins[str(files[0])] = seal
        suffix.append(rows)
    families = {}
    for obj in selected:
        remaining = obj['coordinates'][:]
        for rows in suffix:
            row = rows[obj['scope']]
            assert row['checksum'] == obj['checksum']
            remaining = [c for c in remaining if not (int(row['bits'],16) >> (row['width']-1-c)) & 1]
        if remaining:
            record = dict(scope=obj['scope'], name=obj['name'], checksum=obj['checksum'],
                          logical_width=obj['width'], remaining_serialized_slots=len(remaining),
                          coordinates=remaining)
            families.setdefault(obj['group'], []).append(record)
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    assert sha(book_path) == authority[str(book_path)]
    book = json.loads(book_path.read_bytes()); pins[str(book_path)] = sha(book_path)
    source_files = ['hardware/deps/cva6/core/load_store_unit.sv',
        'hardware/deps/cva6/core/load_unit.sv', 'hardware/deps/cva6/core/store_unit.sv',
        'hardware/deps/cva6/core/scoreboard.sv', 'hardware/deps/cva6/core/cva6_mmu/cva6_tlb.sv',
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'apps/riscv-tests/isa/rv64uv/vitlb_asid_exec_matrix_bulk.c',
        'apps/riscv-tests/isa/rv64uv/vsv39_fault_address_alternating.c',
        'apps/riscv-tests/isa/rv64uv/csr_cause_wlrl788.c']
    for relative in source_files:
        path = ROOT / relative
        expected = book.get(str(path), authority.get(str(path)))
        assert expected and sha(path) == expected, relative
        pins[str(path)] = expected
    result = dict(status='STATIC_SOURCE_BOUND_DYNAMIC789_CANDIDATE_NO_EDA', baseline=789,
        baseline_seal=BASE_SHA, input_pins=pins,
        families=[dict(name=name, objects=objects,
            residual_serialized_slots=sum(o['remaining_serialized_slots'] for o in objects))
            for name,objects in families.items()],
        already_covered_or_not_repeated=[
            '789 cause928: source writes mcause/scause storage only; all four suffix VDBs ORed into target coordinates; no cause fields counted.',
            '774 ITLB:16 executable physical pages, complementary canonical VPNs and 0x5555/0xaaaa ASIDs,48 S-ecalls; do not repeat VA/ASID matrix.',
            '773 fault: vector VL1 load/store cause13/15 at low/high canonical addresses; does not establish scalar LOAD/STORE misalign producer coverage.',
        ],
        preferred_stimulus=dict(
            kind='Scalar LD/SD misalignment, not vector fault and not AMO',
            addresses=['0x0000002555555003', '0xffffffdaaaaaa003'],
            sequence='Bare M-mode, each address LD then SD, then repeat first address; aligned ordinary L2 load/store recovery.',
            causes=[4,6,4,6,4,6],
            source='load_store_unit:710..721 detects LD/SD low3!=0; :749..767 valid/cause/tval from full64 lsu_ctrl.vaddr (VLEN64,TvalEn1); exception arbitration :421/:483; scoreboard:257 ex.valid writes owning slot.',
            falsifiable='Actual scalar LOAD/STORE owner produces exact tval and cause before memory request; no transaction for rejected instruction, no fault-store effect; scoreboard trans_id and trap PC pair exact.',
            oracle='Pinned Spike entry-to-unique-tohost full scalar/GPR/memory; exact6 trap PCs/cause/tval; handler mepc+4/mret; immutable source/full page guards and CSR restore; unexpected trap or Spike misalignment emulation is HOLD.',
            estimate='Small six-fault scalar representative <=600s; software preflight not yet built.',
        ),
        itlb_decision='DEFER: normal PPN remaining slots mostly physical highbits; frozen2MiB L2 only permits low9 page-index variation. Need exact compiled serializer-to-logical-bit binding and prior16page PPN witness before estimating reachable gain or building a new exec matrix.',
        historical_dedup_limit='Reviewed exact admitted source contracts and ORed actual789 suffix coverage. Full historical scalar misalign trace/opcode+address inventory not yet complete; no claim of unique new ELF until preflight/dedup.',
        exclusion_limit='Exact785 approved EL used as filter; no partial objects/observer scopes or known guest zero candidates included. Later EL changes require fresh subtraction.',
        official_percentage_claim=False, EDA_launched=False, RTL_changed=False)
    for path, expected in pins.items():
        assert sha(Path(path)) == expected
    path = OUT / 'scalar-fault-itlb789-static-agent-20261008-01.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(path, sha(path))
    print([(f['name'],len(f['objects']),f['residual_serialized_slots']) for f in result['families']])


if __name__ == '__main__':
    main()
