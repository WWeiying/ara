"""Compact RVH-disabled family assessment; native/policy qualification pending."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'conservative-toggle785-static-agent-20261008-01.json'
SHA = '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'
REGS = ('mtinst', 'mtval2', 'hedeleg', 'hideleg', 'hcounteren', 'hgeie',
        'htinst', 'htval', 'vstvec', 'vsscratch', 'vsepc', 'vscause', 'vstval',
        'vsatp', 'hgatp', 'hstatus', 'vsstatus', 'en_ld_st_g_translation')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert sha(RANK) == SHA
    rank = json.loads(RANK.read_bytes())
    book_path = OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json'
    assert sha(book_path) == rank['input_pins'][str(book_path)]
    book = json.loads(book_path.read_bytes())
    pins = {str(RANK): SHA, str(book_path): sha(book_path)}
    sources = {}
    for name in ('csr_regfile.sv', 'cva6_tlb.sv', 'cva6_ptw.sv', 'cva6_shared_tlb.sv',
                 'cv64a6_imafdcv_sv39_config_pkg.sv', 'ara_soc.sv'):
        matches = [Path(p) for p in book if Path(p).name == name]
        assert len(matches) == 1
        path = matches[0]
        assert sha(path) == book[str(path)]
        pins[str(path)] = book[str(path)]
        sources[name] = path.read_text().splitlines()
    families = []
    for row in rank['ranking']:
        scope = row['scope']
        if scope.endswith('.csr_regfile_i'):
            objects = [o for o in row['objects'] if re.match(
                r'^(?:'+'|'.join(REGS)+r')_[qd](?:\.|$)', o['name'])]
            family, rationale = 'CSR_DISABLED_GUEST_STORAGE', 'Unreset q and potentially undriven d; inactive/unobservable rationale only, never known-zero.'
        elif scope.endswith(('.i_itlb', '.i_dtlb')):
            objects = [o for o in row['objects'] if o['name'].startswith('lu_g_content_o.')]
            family, rationale = 'TLB_EXPLICIT_ZERO_GUEST_LOOKUP_OUTPUT', 'Lookup output default0; all guest overrides inside RVH block. Incoming update.g_content is NOT constant.'
        elif scope.endswith('.i_ptw'):
            objects = [o for o in row['objects'] if o['name'].startswith('shared_tlb_update_o.g_content.')]
            family, rationale = 'PTW_EXPLICIT_ZERO_GUEST_UPDATE_OUTPUT', 'PTW producer else branch0; shared-TLB cache-hit outputs are separate and may alias normal PTE.'
        else:
            continue
        if objects:
            assert all(not o['partial_EL_direction_binding_HOLD'] for o in objects)
            families.append(dict(family=family, scope=scope, checksum=row['checksum'],
                residual_serialized_slots=sum(o['missing_binary_positions'] for o in objects),
                objects=[dict(name=o['name'], width=o['width'], missing=o['missing_binary_positions']) for o in objects],
                rationale=rationale, status='SOURCE_REVIEWED_CANDIDATE_NATIVE_POLICY_HOLD'))
    assert len(families) == 4
    csr = next(f for f in families if f['family'] == 'CSR_DISABLED_GUEST_STORAGE')
    assert len(csr['objects']) == 128 and csr['residual_serialized_slots'] == 4356
    refs = {reg: [i+1 for i,line in enumerate(sources['csr_regfile.sv'])
                  if re.search(r'\b'+reg+r'_[qd]\b', line)] for reg in REGS}
    result = dict(status='GROUPED_SOURCE_REVIEW_NATIVE_POLICY_HOLD', population=785,
        input_pins=pins, families=families,
        total_residual_serialized_slots=sum(f['residual_serialized_slots'] for f in families),
        csr_reference_lines_complete_text_inventory=refs,
        csr_gate_audit=[
            'CSR reads/writes each guest/hypervisor selector requires RVH; RVH0 returns read/update access exception, not guest register value.',
            'Guest defaults, reset, q update and trap writes: :1067..1125, :1230..1545, :1703..1706, :1980..2003, :2060..2195, :2873..2893, :2968..2990; RVH conditional blocks.',
            'Translation/return/interrupt consumers: :2289..2342, :2380..2415, :2486..2494, :2670, :2705, :2756..2799 require RVH or use explicit RVH0 alternative.',
            'Counter privilege consumers of hcounteren at :2534..2557 are inside :2504 if(RVH); no unguarded active consumer claim.',
            'vsstatus_extended can be a local intermediate; its CSR consumer :443 is gated. Automatic vsatp/hgatp locals are initialized only inside :1015 if(RVH).',
            'Combinational self references do not establish known-zero. Native zero hits do not substitute for inactive consumer proof.',
        ],
        rejected_broad_family=dict(
            names=['shared_tlb.itlb_update_o.g_content.*', 'shared_tlb.dtlb_update_o.g_content.*',
                   'itlb.update_i.g_content.*', 'dtlb.update_i.g_content.*'],
            reason='shared_tlb:321/330 cache-hit path assigns pte[i][HYP_EXT] without RVH gate. HYP_EXT=0 aliases live ordinary PTE. Preserve these data inputs/outputs.',
            protected=['normal content_q/n.pte.*', 'normal satp/asid/ppn', 'tval/cause',
                       'all exception copies not individually producer-proven', 'CSR illegal access and all interface controls']),
        native_binding_plan=[
            'Bind current admitted population and sourcebook/config pins; this numerical inventory is exact785 only, not an assertion of latest suffix applicability.',
            'Use actual GUI Toggle full name/path/meta plus compiled checksum/type/width; flatten struct leaves exactly. Do not guess XML position as GUI ID.',
            'Existing EL difference by exact scope/field/bit/direction; reject partial masks or ambiguous metadata. No whole CSR/TLB exclusions.',
            'Load only the approved typed point set into an initially empty local session; save/reload exact semantic direction multiset and prove every scope complement excluded flag unchanged.',
            'Reset and final empty stages restore all coverage; exact source rationale annotations distinguish disabled/unobservable storage from explicit constant outputs.',
            'Host negatives must reject RVH1, disabled-storage relabelled zero, extra normal PTE/cause/tval field, wrong scope/checksum/width, partial bitmask, and alias g_content counterexample before launch.',
        ],
        policy_limit='Disabled/unobservable storage requires explicit applicable policy approval; static review does not approve exclusions or X-to0 initialization removal.',
        all_writer_consumer_machine_proof=False,
        official_percentage_projection=False, EDA_launched=False, RTL_changed=False)
    for path, expected in pins.items():
        assert sha(Path(path)) == expected
    path = OUT / 'rvh-disabled-families785-compact-agent-20261008-01.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(path, sha(path))
    print([(f['family'],len(f['objects']),f['residual_serialized_slots']) for f in families])


if __name__ == '__main__':
    main()
