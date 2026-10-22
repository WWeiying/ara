"""Frozen source induction and exact residual coordinates; no native exclusion."""
import argparse
import json
from pathlib import Path

import preflight_qbs_route770 as route
import targeted_toggle_evidence_v2 as native

ROOT, OUT = route.ROOT, route.OUT
PRIOR = OUT/'qbs-bank1-group-hit789-static-agent-20261008-01.json'
PRIOR_SHA = '1438b0ea8be8e954fda9dc5b8c0d9e65a1921eb44e46b9af2655a26c33db9809'
GAPS = OUT/'conservative-toggle785-static-agent-20261008-01.json'
GAPS_SHA = '035172c63269024e6e2171426fa8616dedaf6da442f766934806dcb181cdd1d5'
BASE = OUT/'csr-cause-wlrl-offline-admitted789-agent-20261008-02'
BASE_SHA = '810a9531e1e7a7edaece3fcec19e90e47fee3530e641f824aaed49e8deb3522d'
BOOK = OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
BOOK_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SCOPE = route.BASE+'1'
EXTRA_SOURCES = [
    'hardware/src/vlsu/vlsu.sv', 'hardware/src/ara.sv',
    'hardware/src/ara_system.sv',
    'hardware/deps/cva6/core/load_store_unit.sv',
    'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv',
    'hardware/deps/cva6/core/pmp/src/pmp_data_if.sv',
]


def target(profile, layout, offset, byte, context):
    """Valid stored tuple, or None; implements bank1 acceptance mapping."""
    if profile not in ('Q8_K', 'Q8_0'):
        return None
    config = dict(activation_profile=profile, activation_layout=layout)
    ctx, off, valid = route.activation_map(config, offset+byte, context)
    block = 292 if profile == 'Q8_K' else 34
    if valid and 4 <= ctx < 8 and 0 <= off < block:
        return ctx-4, off//16
    return None


def domain():
    result = {(row, group): set() for row in range(4) for group in range(19)}
    # Superset of every accepted beat: arbitrary strobes and all 4-aligned
    # offsets across the complete12-bit input domain, not just streamed beats.
    for profile in ('Q8_K', 'Q8_0'):
        for layout in ('ROW', 'M4', 'M8'):
            for context in range(4):
                for offset in range(0, 4096, 4):
                    for byte in range(16):
                        mapped = target(profile, layout, offset, byte, context)
                        if mapped is not None:
                            result[mapped].update((byte, 16+byte))
    return result


def qualified_hit(source_valid, target_valid, consumed, mapped, wanted):
    """Consequence of frozen per-slot consumed equation, not a DUT model."""
    return bool(source_valid and target_valid and consumed and mapped == wanted)


def collect():
    pins = {}

    def bound(path, sha, parse=True):
        native.require(native.digest(path) == sha, 'Pinned source/input drift: '+str(path))
        pins[str(path)] = sha
        return json.loads(path.read_text()) if parse else path.read_bytes()

    prior = bound(PRIOR, PRIOR_SHA)
    gap = bound(GAPS, GAPS_SHA)
    manifest = bound(BASE/'admission-manifest.json', BASE_SHA)
    book = bound(BOOK, BOOK_SHA)
    native.require(prior['scope'] == SCOPE and manifest['coverage_admitted'] is True,
                   'Exact prior scope and admitted789')
    for rel in route.SOURCES + EXTRA_SOURCES:
        bound(ROOT/rel, book[str(ROOT/rel)], False)
    authority = dict(manifest['input_pins'], **manifest['output_pins'])
    ledger_path = BASE/'combined-inputs.txt'
    ledger = bound(ledger_path, authority[str(ledger_path)], False).decode().splitlines()
    native.require(len(ledger) == len(set(ledger)) == 790, 'Exact789 ledger')
    config_path = OUT/'current-population785-rr190-prepared-agent-20261008-01/config.json'
    old = bound(config_path, '796fbe9f3c009b8b6aed24b840d3699a965a9e257341757e5615d6b08b997a49')
    native.require(ledger[:786] == old['input_ledger'], 'Exact formal785 prefix')
    shape_path = Path(ledger[0])/'snps/coverage/db/shape/tgl.verilog.shape.xml'
    bound(shape_path, authority[str(shape_path)], False)
    definitions = [d for d in native.xml(shape_path).findall('tgldef')
                   if d.get('chksum') == '3028946256']
    native.require(len(definitions) == 1, 'Exact compiled adapter definition')
    offsets = {}; width = 0
    for node in definitions[0].find('tglshape'):
        if node.tag == 'arrays':
            continue
        native.require(node.tag in ('node', 'vectornode'), 'Unknown shape object')
        n = 1 if node.tag == 'node' else abs(int(node.get('left'))-int(node.get('right')))+1
        offsets[node.get('name')] = (width, n, dict(node.attrib))
        width += 2*n
    native.require(width == 26222, 'Exact full scope serialized shape')
    suffix = 0
    for vdb in ledger[786:]:
        files = list((Path(vdb)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        native.require(len(files) == 1, 'Exact suffix testdata')
        path = files[0]
        native.require(str(path) in authority, 'Unpinned suffix')
        rows, sha = native.rows(path, [SCOPE])
        native.require(sha == authority[str(path)] and
                       (rows[SCOPE]['width'], rows[SCOPE]['checksum']) == (width, '3028946256'),
                       'Exact suffix bitmap shape/pin')
        pins[str(path)] = sha
        suffix |= int(rows[SCOPE]['bits'], 16)
    mapping = domain(); targets = []; total = 0
    rank = next(r for r in gap['ranking'] if r['scope'] == SCOPE)
    for field in rank['objects']:
        if 'gen_activation' not in field['name'] or not field['name'].endswith('.group_hit'):
            continue
        start, n, attrs = offsets[field['name']]
        native.require(n == 32 and attrs['portnode'] == '0' and
                       (attrs['left'], attrs['right'], attrs['file'], attrs['line_num']) ==
                       ('31', '0', '572', '753'), 'Exact internal declaration identity')
        _, role, coordinate = route.parse_node(SCOPE, field)
        row, group = coordinate(0)[2:4]
        zero_bits = sorted(set(range(32))-mapping[row, group])
        if not zero_bits:
            continue
        positions = [start+2*b+d for b in zero_bits for d in (0, 1)]
        native.require(set(positions) <= set(field['coordinates']) and
                       not any(suffix >> (width-1-i) & 1 for i in positions),
                       'Candidate source-zero coordinate hit or absent from exact residual')
        targets.append(dict(name=field['name'], attributes=attrs, serialized_offset=start,
                            source_zero_bit_indices=zero_bits,
                            source_zero_mask=hex(sum(1 << b for b in zero_bits)),
                            actual_missing789_coordinates=positions))
        total += len(positions)
    native.require(len(targets) == 72 and total == 3232, 'Exact bounded candidate set')
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_review_qbs_bank1_group_hit789_all_cycle.py')):
        pins[str(path)] = native.digest(path)
    for path, sha in pins.items():
        native.require(native.digest(path) == sha, 'End-of-review drift')
    return dict(status='POST_RESET_FROZEN_INTEGRATED_SOURCE_INDUCTION_NATIVE_BINDING_PENDING',
        scope=SCOPE, population=789, candidate_objects=72, actual_missing_serialized_positions=3232,
        native_direction_names_verified=False, native_qualified=False, source_targets=targets,
        invariant='If consumed[B]=1 then source_valid[B//16]=1 and target[B].valid=1; that stored tuple came from a qualified4-aligned acceptance at original byte B%16.',
        proof_steps=[
            'Producer: engine RUN is reachable only after descriptor_valid and context checks. Decoder rejects unsupported profile/layout/M/alignment. Invalid descriptor and descriptor/MMU/PMA failures before RUN cannot push activation bytes.',
            'Offset: DIRECT/FILL range starts are4-aligned; M8 block lengths2336/272 and all K shifts are16-aligned. Page and MaxBurst boundaries are multiples16, physical translation preserves page offset, so first_lane and every nonterminal take are multiples4. Reader range_offset starts0 and increments by take. Fault/protocol/error responses suppress data_valid. ROW context is a2-bit field; M4 contexts0..3; context replay is ROW and thus cannot create a valid bank1 tuple.',
            'Mapping: enumerate both supported profiles, all layouts, all2-bit contexts, arbitrary strobes, every4-aligned12-bit offset, and all16 byte indices. This is stronger than legal streamed beats. Invalid/default profile has block_bytes0; default/invalid layout has2-bit row context and cannot pass bank1 bounds.',
            'Ingress induction: reset/clear sets count0 and rd=wr=0. push occurs only if count<2 and !clear && !read and stores the complete tuple at wr. pop occurs only if count!=0. Push/pop with count1 switches pointers to the just-written occupied entry; count2 cannot push. Thus count!=0 never exposes an uninitialized or unoccupied tuple as an active source.',
            'Pending induction: source1 leftovers copy the same target index b and location, with strb=remaining[16+b]. Subsequent drains only remove strb bits. Reset/clear sets pending_valid0. Tuple row/offset is never reinterpreted under a later profile/layout; a new command INIT clears queue and pending state.',
            'Mask dominance: payload_buffer consumed is per-slot source_valid AND target.valid AND (bank_grant OR side-plane). bank_grant includes candidate target.valid. Consequently the adapter global OR of source_valid cannot authorize an inactive opposite slot; invalid/stale target ctx/offset is masked even when the other slot is active.',
            'Abort/error/backpressure: queued or pending pre-fault tuples retain the same membership invariant while draining, and no fresh ingress is accepted when fault disables activation_write_ready. FAULT_CLEAR immediately gates both sources and flushes count/pending. Stalls may delay or remove consumed bits but cannot change tuple membership or byte index.',
            'Therefore group_hit[row][group][B] implies B belongs to the enumerated mapping[row,group]. The complement is zero in all initialized reachable states, including reset, clear, empty, stale, blocked, and fault-drain states. No assumption that current data values are zero, no library-trust waiver, and no assumption that the software avoids an error path.'
        ],
        limits=['Static induction, not a formal model-checker result or native qualification.',
                'Unconstrained arbitrary initial state before reset is not proved; startup X is not removed or counted as a binary direction hit.',
                '704 mapping-permitted pending positions stay protected; no new waiver for active routing or whole objects.',
                'Exact native bit/range/direction binding and protected complement still required before any EL.'],
        input_pins=pins, EL_created=False, EDA_launched=False, RTL_changed=False,
        official_percentage=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native.require(not args.output.exists(), 'Fresh independent review output')
    result = collect()
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(args.output), sha256=native.digest(args.output),
                          targets=result['candidate_objects'], positions=result['actual_missing_serialized_positions'])))
