"""Static disabled-storage versus constant-output review; no native approval."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'repaired-aligned-build-20260930-01'
RANK = OUT / 'conservative-toggle785-static-agent-20261008-01.json'
RANK_SHA = '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'
REGS = ('vsscratch', 'vsepc', 'vscause', 'vstval', 'vsatp', 'htval')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(RANK) == RANK_SHA
    rank = json.loads(RANK.read_bytes())
    book_path = BASE / 'build-source-pins.json'
    assert sha(book_path) == rank['input_pins'][str(book_path)]
    book = json.loads(book_path.read_bytes())
    pins = {str(RANK): RANK_SHA, str(book_path): sha(book_path)}
    texts = {}
    for relative in (
        'hardware/deps/cva6/core/csr_regfile.sv',
        'hardware/deps/cva6/core/cva6.sv',
        'hardware/deps/cva6/core/scoreboard.sv',
        'hardware/deps/cva6/core/acc_dispatcher.sv',
        'hardware/deps/cva6/core/include/build_config_pkg.sv',
        'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
        'hardware/src/ara.sv', 'hardware/src/ara_soc.sv', 'hardware/Makefile',
    ):
        path = ROOT / relative
        assert sha(path) == book[str(path)], 'Source drift: ' + relative
        pins[str(path)] = book[str(path)]
        texts[relative] = path.read_text()
    command_path = BASE / 'compile.command.json'
    command = json.loads(command_path.read_bytes())['command']
    assert 'store_b_ab_baseline=0' in command
    pins[str(command_path)] = sha(command_path)
    csr = texts['hardware/deps/cva6/core/csr_regfile.sv'].splitlines()
    row = next(r for r in rank['ranking'] if r['scope'].endswith('.csr_regfile_i'))
    objects = [dict(name=o['name'], width=o['width'], missing_binary_positions=o['missing_binary_positions'])
               for o in row['objects'] if re.match(r'^(?:'+'|'.join(REGS)+r')_[qd](?:\.|$)', o['name'])]
    assert len(objects) == 16 and sum(o['missing_binary_positions'] for o in objects) == 1536
    references = {reg: [dict(line=i+1, text=line.strip()) for i, line in enumerate(csr)
                       if re.search(r'\b'+reg+r'_[qd]\b', line)] for reg in REGS}
    result = dict(
        status='STATIC_DISABLED_STORAGE_POLICY_AND_NATIVE_HOLD', population=785,
        input_pins=pins, scope=row['scope'], compiled_checksum=row['checksum'],
        exact_objects=objects, residual_serialized_positions=1536,
        known_zero_claim=False, source_reference_inventory=references,
        source_review=dict(
            config='HExtEn=0 -> RVH=0; SoC configuration preserves RVH',
            csr_reads=':460..479 / :592..594 gated by RVH, false branch signals illegal CSR access',
            csr_writes=':1278..1310 / :1511..1518 gated by RVH, false branch signals illegal CSR access',
            combinational_hold=':1111..1126 q-to-d defaults only under RVH; disabled d may be unassigned',
            sequential=':2873..2893 reset and :2968..2990 q-to-d updates both only under RVH',
            trap_writers=':2080..2099 guest trap requires RVH && trap_to_v; :2124..2140 HTVAL writer requires RVH',
            consumers='Guest return/translation/CSR-read consumers RVH-gated; :2756 vsatp_ppn_o and :2763 vs_asid_o explicit zero outputs',
            additional_dependencies='RVXHCLIC configuration and vscause consumer :2412 remain separately required in a complete consumer proof',
        ),
        required_before_any_exclusion=[
            'Policy approval specifically for configuration-disabled/unobservable storage, not known-zero or trusted whole CSR unit',
            'Complete writer/consumer guard proof including RVXHCLIC and every alias; reference inventory is evidence, not an SV control-flow parser',
            'Exact native typed object/bitmask bijection and existing EL difference; preserve all other CSR values and illegal-access control',
            'Five-stage full complement readback/save/reload/reset; no exclusion of initialization X transitions by zero rationale',
        ],
        preview=dict(
            status='ACTIVE_ACCELERATOR_PREVIEW_NOT_DISABLED',
            chain=['config RVV=1; build_config_pkg:23 EnableAccelerator=RVV',
                   'cva6:1608..1611 accelerator branch takes actual preview response',
                   'acc_dispatcher:330..337 req_valid enabled when ARA_STORE_B_AB_BASELINE is absent',
                   'compile.command store_b_ab_baseline=0; Makefile:197..198 only defines macro for1',
                   'ara:71..81 vsetvl_preview drives valid/vl response',
                   'scoreboard:128..134 only accepts still-issued ACCEL owner; :340..343 forwards preview data'],
            CvxifEn0_does_not_disable_ACCEL=True,
            preview_data_high_bits='May be bounded by legal VL, but requires separate algorithm/config bit proof; not a whole-object exclusion',
            rs2='vset_preview_req initialized0 and rs2 never overridden in its always_comb; exact field only is a separate constant candidate',
        ),
        EDA_launched=False, RTL_changed=False, exclusions_approved=False,
        official_denominator_or_percentage_claim=False,
    )
    for path, expected in pins.items():
        assert sha(Path(path)) == expected
    path = OUT / 'disabled-csr-preview785-static-agent-20261008-01.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(path, sha(path), 'STATIC_HOLD_16_OBJECTS_1536_SLOTS_PREVIEW_ACTIVE')


if __name__ == '__main__':
    main()
