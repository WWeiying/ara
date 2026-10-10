"""Read-only DTLB attribute coordinates and deterministic software-case draft."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import build_dtlb_ppn_swap779 as prior
from rank_cva6_scalar_data767 import typed_nodes

ROOT, OUT, require, life = prior.ROOT, prior.OUT, prior.require, prior.life
ATTR = re.compile(r'content_[qn]\[(?:[0-9]|1[0-5])\]\.pte\.([vrwxugad])')
GAIN = OUT / 'dtlb-ppn-swap-offline-admitted780-agent-20261008-01'
GAIN_SEAL = '4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b'


def permission(flags, privilege, operation, *, sum_enabled=False, mxr=False):
    """Sv39 software oracle, not a model of CVA6 warm-TLB implementation."""
    require(type(flags) is int and 0 <= flags < 256 and
            privilege in ('S', 'U') and operation in ('load', 'store'), 'Invalid domain')
    v, r, w, x, u, a, d = (bool(flags & (1 << i)) for i in (0, 1, 2, 3, 4, 6, 7))
    permitted = v and not (w and not r) and a
    permitted &= (not u or sum_enabled) if privilege == 'S' else u
    permitted &= (w and d) if operation == 'store' else (r or (x and mxr))
    return 0 if permitted else 13 if operation == 'load' else 15


def cases():
    # Cold MXR=0 explicitly avoids relying on an unverified warm-hit MXR check.
    rows = [
        ('user_x_sum_mxr', 0x79, 'S', 'load', True, True, False, 0),
        ('user_x_no_sum', 0x79, 'S', 'load', False, True, False, 13),
        ('user_x_effective_u', 0x79, 'U', 'load', False, True, False, 0),
        ('user_x_no_mxr_cold', 0x79, 'S', 'load', True, False, True, 13),
        ('user_x_store', 0x79, 'S', 'store', True, True, False, 15),
        ('supervisor_effective_u', 0xc7, 'U', 'load', True, False, False, 13),
        ('supervisor_rw_store', 0xc7, 'S', 'store', False, False, False, 0),
        ('supervisor_rw_dirty0_load', 0x47, 'S', 'load', False, False, True, 0),
        ('supervisor_rw_dirty0_store', 0x47, 'S', 'store', False, False, False, 15),
    ]
    out = []
    for name, flags, priv, op, summ, mxr, cold, cause in rows:
        require(permission(flags, priv, op, sum_enabled=summ, mxr=mxr) == cause,
                'Independent permission gold mismatch')
        out.append(dict(name=name, pte_flags=flags, effective_privilege=priv,
                        operation=op, SUM=summ, MXR=mxr, cold_full_sfence=cold,
                        mcause=cause, mtval=prior.address(0) if cause else None,
                        mepc='exact labeled 32-bit ld/sd site' if cause else None,
                        fault_has_no_gpr_or_memory_result=bool(cause),
                        setup='Install requested flags; full SFENCE when flags change. For warm probes '
                              'first load legally using S/SUM/MXR appropriate to the installed page.'))
    return out


def review():
    pins = {}
    prior.bind779(pins)
    manifest = life.read_bound(GAIN / 'admission-manifest.json', GAIN_SEAL)
    pins[str(GAIN / 'admission-manifest.json')] = GAIN_SEAL
    require(manifest['coverage_admitted'] is True and manifest['baseline'] == str(prior.BASE) and
            manifest['baseline_seal'] == prior.BASE_SHA, 'Unbound PPN successor')
    gain_path = GAIN / 'dtlb-toggle-gain.json'
    pins[str(gain_path)] = manifest['output_pins'][str(gain_path)]
    gain = life.read_bound(gain_path, pins[str(gain_path)])
    require(gain['scope'] == prior.shared.SCOPE and gain['baseline'] == 779 and
            gain['official_percentage'] is False, 'Gain identity')
    require(int(gain['after']['bits'],16) ==
            (int(gain['before']['bits'],16) | int(gain['single']['bits'],16)) and
            all(gain[k]['width'] == 11852 and gain[k]['checksum'] == '817233724'
                for k in ('before', 'after', 'single')) and
            all(0 <= int(gain[k]['bits'],16) < (1 << 11852) for k in ('before', 'after', 'single')),
            'Exact PPN union dimensions/OR')
    base_ledger = (prior.BASE / 'combined-inputs.txt').read_text().splitlines()
    ledger = GAIN / 'combined-inputs.txt'
    pins[str(ledger)] = manifest['output_pins'][str(ledger)]
    require(life.digest(ledger) == pins[str(ledger)] and
            ledger.read_text().splitlines()[:-1] == base_ledger, 'Exact779 prefix')
    paths = [next(Path(x) for x in pins if x.endswith('/' + s)) for s in
             ('design/verilog.design.xml', 'shape/tgl.verilog.info.xml',
              'shape/tgl.verilog.shape.xml')]
    checks, definitions = prior.shared.native.definitions(
        *(prior.shared.native.xml(p) for p in paths), [prior.shared.SCOPE])
    require(checks[prior.shared.SCOPE] == '817233724', 'Compiled checksum')
    nodes, arrays = typed_nodes(definitions[prior.shared.SCOPE]['shape'], gain['after'])
    attributes = [n for n in nodes if ATTR.fullmatch(n['name'])]
    counts = Counter()
    for n in attributes:
        require(n['logical_width'] == 1, 'Attribute not scalar')
        counts[ATTR.fullmatch(n['name'])[1]] += n['missing_slots']
    require(dict(counts) == dict(v=32, r=32, w=32, x=26, u=54, g=62, a=32, d=32),
            'Actual attribute residual changed')
    primary = [n for n in attributes if ATTR.fullmatch(n['name'])[1] in 'xug' and n['missing_slots']]
    secondary = [n for n in attributes if ATTR.fullmatch(n['name'])[1] in 'rwd' and n['missing_slots']]
    book = life.read_bound(prior.shared.SOURCE, prior.shared.SOURCE_SHA)
    pins[str(prior.shared.SOURCE)] = prior.shared.SOURCE_SHA
    files = ('core/cva6_mmu/cva6_tlb.sv', 'core/cva6_mmu/cva6_mmu.sv',
             'core/cva6_mmu/cva6_ptw.sv', 'core/cva6_mmu/cva6_shared_tlb.sv',
             'core/csr_regfile.sv', 'core/include/cv64a6_imafdcv_sv39_config_pkg.sv')
    texts = {}
    for rel in files:
        p = ROOT / 'hardware/deps/cva6' / rel
        pins[str(p)] = book[str(p)]
        require(life.digest(p) == pins[str(p)], 'Frozen producer source drift')
        texts[p.name] = p.read_text()
    contract = prior.shared.source_contract(texts)
    for filename, fragments in {
        'cva6_tlb.sv': ('content_n[i].pte = update_i.content', '!content_q[i].pte.g'),
        'cva6_ptw.sv': ('!pte.v || (!pte.r && pte.w)', 'global_mapping_n = 1\'b1',
                        'pte.a &&', 'mxr_i ||', '(pte.w && pte.d)'),
        'cva6_mmu.sv': ('!sum_i', 'PRIV_LVL_U && !dtlb_pte_q.u', '!dtlb_pte_q.d'),
        'csr_regfile.sv': ('ld_st_priv_lvl_o = (mprv) ? mstatus_q.mpp : priv_lvl_o',
                           'assign sum_o = mstatus_q.sum', 'assign mxr_o  = mstatus_q.mxr'),
    }.items():
        require(all(x in texts[filename] for x in fragments), 'Producer landmark changed')
    app = prior.APP
    pins[str(app)] = life.digest(app)
    old_preflight = OUT / 'dtlb-ppn-swap-preflight779-agent-20261008-01/preflight.json'
    pins[str(old_preflight)] = life.digest(old_preflight)
    previous = json.loads(old_preflight.read_bytes())
    require(previous['input_pins'][str(app)] == pins[str(app)] and
            previous['baseline_seal'] == prior.BASE_SHA, 'Original matrix drift')
    for p in (Path(__file__), Path(__file__).with_name('test_review_dtlb_permissions779.py')):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    addresses = [prior.address(i) for i in range(16)]
    return dict(schema='FROZEN_DTLB_ATTRIBUTE_REACHABILITY_AND_HOST_DRAFT_V1',
        status='SOURCE_HOST_MODEL_PASS_NOT_COMPILED_OR_DUT_QUALIFIED', pins=pins,
        baseline=779, baseline_seal=prior.BASE_SHA, ppn_admitted_successor=780,
        scope=prior.shared.SCOPE, checksum='817233724', binary_width=11852,
        source_contract=contract, attributes_missing=dict(counts),
        primary_missing_coordinates=142, primary_objects=primary,
        secondary_missing_coordinates=96, secondary_objects=secondary,
        serialized_direction_labels_not_bound=True, arrays_not_flattened=len(arrays),
        measured_gain=None, official_percentage=None, waivers=[], EDA_launched=False,
        source_evidence=[
            dict(file=str(ROOT / 'hardware/deps/cva6' / files[0]),
                 lines='203;287-309;334-352', fact='G bypasses ASID; ASID-selective SFENCE preserves G; '
                 'full SFENCE invalidates all tags but does not clear content; replacements copy whole PTE.'),
            dict(file=str(ROOT / 'hardware/deps/cva6' / files[2]),
                 lines='218;402;409-411;471-488', fact='Inherited G retained. RVH0 data walk accepts '
                 'V1 A1 R0 W0 X1 with MXR1; loads need neither W nor D. Stores need W1 D1.'),
            dict(file=str(ROOT / 'hardware/deps/cva6' / files[1]),
                 lines='530-533;595;630', fact='S SUM0 U1 and U U0 fault. Warm stores enforce W/D.'),
            dict(file=str(ROOT / 'hardware/deps/cva6' / files[4]),
                 lines='2330-2340;2765;2785', fact='MPRV chooses MPP effective data privilege; '
                 'SUM/MXR are mstatus fields. M-mode instruction fetch does not add translated code pages.')],
        draft=dict(source_template=str(app), virtual_addresses=addresses,
            phase_flags=[0xc7, 0x79, 0xc7], phase_meaning=['S RW A D', 'U global X-only A', 'S RW A D'],
            physical_addresses=[prior.pa(17*i) for i in range(16)],
            page_value_gold=[prior.gold(17*i) for i in range(16)],
            address_and_ppn_repetition_not_gain=True,
            minimal_edits=['Keep root/mid/leaf placement, VA generation, fixed physical pages and read_pair.',
                'Replace phase-dependent PPN changes with fixed pa(17*i); leaf flags c7/79/c7.',
                'Clear SUM/MXR in ordinary phases; set both in X-only phase. MPRV=1 MPP=S.',
                'Full SFENCE after each PTE rewrite, then exactly two explicit loads per VA (96 total).',
                'All translated accesses are labeled assembly, restore mstatus before any C stack access.',
                'After the fill phases, run the nine listed permission probes on entry0 only.',
                'Use existing scalar trap pattern with preserved registers, MPRV clear before handler memory, '
                '32-bit access site, recorded mcause/mepc/mtval and exact one-instruction resume.'],
            mstatus_setting='(original & ~(MPRV|MPP|SUM|MXR|MIE|SIE)) | MPRV | MPP_S | phase_SUM_MXR',
            independent_pte_gold='root[vpn>>18]=pte(mid,1);mid[(vpn>>9)&511]=pte(leaf,1);'
                'leaf[vpn&511]=pte(pa(17*entry),phase_flags);other entries zero except root[2] identity cf',
            trap_permission_gold=cases(),
            extra_global_probe='In G phase, SFENCE x0,ASID=1 while running ASID=1 must retain '
                'global entry. Keep PTE unchanged; check data. Do not use an unfenced PTE edit as oracle.',
            independent_acceptance=['Full PTE images and every PTE write history; physical guard bytes unchanged '
                'except the one successful explicit store and its restore.',
                'Every legal load value and permitted store readback; exact five traps with '
                'cause/tval/site and no faulting memory/GPR result.',
                'Exact MPRV windows and no hidden translated stack access; all modified CSRs restored.',
                'Spike checks ISA gold only, not physical TLB occupancy; native replacement events and '
                'raw union must demonstrate incremental coverage before any admission.'],
            native_gain_hypothesis='All 16 replacement slots populated in each contrasting phase; '
                'content_q/n.x/u/g toggle both ways, plus r/w/d contrasts. SFENCE alone is insufficient.',
            host_obligation='Do not assert measured slot coverage from PLRU host order; verify '
                'actual native replacements on any later explicitly authorized run.',
            budget='At most96 fill loads +9 permission probes; reuse existing matrix compile/Spike '
                'preflight. Bound a later authorized VCS run at600s; no measured time claim.',
            not_targeted=['V/A falling: data fill rejects invalid or A0 PTE; no all-producer constant '
                'proof here and no waiver.', 'Warm MXR1->0 without SFENCE: frozen MMU hit path '
                'does not visibly recheck R/MXR; cold test only, no speculative bug assertion.']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    path = parser.parse_args().output.absolute()
    require(path.is_relative_to(OUT) and not path.exists(), 'Fresh verification output required')
    result = review()
    life.save(path, result)
    print('STATIC_HOST_DRAFT_PASS', path, life.digest(path), flush=True)
