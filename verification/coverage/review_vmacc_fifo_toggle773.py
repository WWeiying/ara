"""Read-only773 candidate: rotate the C command FIFO across lengths256/255."""
import argparse
import json
from pathlib import Path

import rank_ordinary_rvv_toggle766 as frozen
import targeted_toggle_evidence_v2 as t

ROOT, OUT = frozen.ROOT, frozen.OUT
BASE = OUT / 'sv39-fault-alternating-offline-admitted-773-agent-20261007-01'
SEAL = '65710f130e698571f9e17800e57361b0baa2a9d407a02287409797de64f64060'
PRIOR = OUT / 'queue-remaining-vmacc-static768-agent-20261007-01.json'
AUDIT = OUT / 'toggle-outside-prepared-union770-static-agent-20261007-01.json'


def collect():
    pins = {}

    def bound(path, sha=None):
        actual = t.digest(path)
        t.require(sha is None or actual == sha, 'Input drift: ' + str(path))
        pins[str(path)] = actual
        return json.loads(path.read_bytes())

    manifest = bound(BASE / 'admission-manifest.json', SEAL)
    t.require(manifest['coverage_admitted'] is True, 'Not admitted773')
    ledger_path = BASE / 'combined-inputs.txt'
    pins[str(ledger_path)] = t.digest(ledger_path)
    t.require(pins[str(ledger_path)] == manifest['output_pins'][str(ledger_path)], 'Ledger drift')
    ledger = ledger_path.read_text().splitlines()
    t.require(len(ledger) == len(set(ledger)) == 774, 'Not exact773')
    prior = bound(PRIOR)
    for name, sha in prior['pins'].items():
        if name.startswith(('hardware/', 'verification/out/old-image-source-evidence')):
            path = ROOT / name
            t.require(t.digest(path) == sha, 'Frozen source drift')
            pins[str(path)] = sha
    book = bound(OUT / 'repaired-aligned-build-20260930-01/build-source-pins.json',
                 '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
    fifo = ROOT / 'hardware/deps/common_cells/src/fifo_v3.sv'
    t.require(t.digest(fifo) == book[str(fifo)], 'FIFO source drift')
    pins[str(fifo)] = book[str(fifo)]
    audit = bound(AUDIT, 'c6dd804cbee8e8d872c6058da0defb8e1c0facd1ca816caf8326e6b12105f036')
    selected = [s for s in audit['scopes'] if 'i_operand_queue_mfpu_c' in s['scope']
                and s['scope'].endswith(('i_operand_queue_mfpu_c', 'i_cmd_buffer'))]
    scopes = [s['scope'] for s in selected]
    t.require(len(scopes) == len(set(scopes)) == 8, 'Four C queues/four FIFOs')
    scopes += ['ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_requester' % i
               for i in range(4)]
    cache = bound(frozen.CACHE, frozen.CACHE_SHA)
    cache_ledger = next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    pins[str(cache_ledger)] = t.digest(cache_ledger)
    t.require(pins[str(cache_ledger)] == cache['input_pins'][str(cache_ledger)] and
              ledger[:742] == cache_ledger.read_text().splitlines(), '741 prefix drift')
    union = {s: {k: cache['instances'][s][k] for k in ('width', 'checksum', 'bits')} for s in scopes}
    for vdb in ledger[742:]:
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        t.require(len(files) == 1, 'One admitted native sample')
        path = files[0]
        pins[str(path)] = t.digest(path)
        t.require(pins[str(path)] == manifest['input_pins'][str(path)], 'Admitted sample drift')
        sample, sha = t.rows(path, scopes)
        t.require(sha == pins[str(path)], 'Read drift')
        union = t.union(union, sample)
    targets = []
    for scope in selected:
        row = union[scope['scope']]
        t.require(row['checksum'] == scope['checksum'], 'Typed shape checksum drift')
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        for node in scope['objects']:
            if not node['name'].endswith('.elem_count'):
                continue
            # Existing compiled serialization pairs are LSB-first, not native GUI direction IDs.
            coordinates = [i for i in node['missing_coordinates']
                           if node['serialized_offset'] + 14 <= i < node['serialized_offset'] + 18
                           and binary[i] == '0']
            if coordinates:
                targets.append(dict(scope=scope['scope'], checksum=row['checksum'],
                                    name=node['name'], logical_bits=[7, 8],
                                    serialized_offset=node['serialized_offset'], zeros=coordinates))
    for lane in range(4):
        scope = scopes[8 + lane]
        row = union[scope]
        t.require(row['checksum'] == '553408029', 'Requester checksum drift')
        binary = format(int(row['bits'], 16), '0%db' % row['width'])
        for name, pair in prior['targets_per_lane'][0]['fields_and_serialized_pairs']:
            t.require(all(binary[i] == '0' for i in pair), 'Prior C-chain target already covered')
            targets.append(dict(scope=scope, checksum=row['checksum'], name=name,
                                logical_bits=[8], zeros=pair))
    # Every ring starting pointer receives both lengths; this is a software/model proof, not DUT evidence.
    for start in range(4):
        visits = [[] for _ in range(4)]
        for index, length in enumerate([256] * 4 + [255] * 4 + [256] * 4):
            visits[(start + index) % 4].append(length)
        t.require(all(v == [256, 255, 256] for v in visits), 'FIFO phase/slot mismatch')
    pins[str(Path(__file__).resolve())] = t.digest(__file__)
    for path, sha in pins.items():
        t.require(t.digest(path) == sha, 'End-of-read drift')
    return dict(status='STATIC773_REACHABLE_C_FIFO_CANDIDATE_NOT_BUILT_NOT_RUN', population=773,
                manifest_sha256=SEAL, baseline=union, targets=targets,
                zero_slots=sum(len(r['zeros']) for r in targets), pins=pins,
                source_chain=prior['producer_chain'] + [dict(source=str(fifo), lines=[68, 75, 80, 122, 136],
                    condition='Legal push writes rotating four-slot memory; pop advances read pointer; reset clears memory, flush resets pointers/count only. C flush is tied0.')],
                case=dict(name='vmacc_C_fifo_e8m8_lengths256_255_ring',
                    commands='e8m8 tu,mu vstart0; four unmasked vmacc.vv v24,v8,v16 at VL1024, four at VL1020, then four at VL1024 again; VL4 vadd recovery.',
                    seed='Full VRF0x5a; A[i]=(i xor0xa5)&255, B[i]=(2*i+1)&255; disjoint groups v8..15/v16..23/v24..31.',
                    gold='After phase1 C=(0x5a+4*A*B)&255 all1024 bytes. After phase2 C=(0x5a+8*A*B)&255 for i<1020, final4 unchanged from phase1. After phase3 C=(0x5a+12*A*B)&255 for i<1020, final4=(0x5a+8*A*B)&255. Recovery first4 C+=1 modulo256.',
                    independent_check='Spike complete entry-tohost scalar/GPR/memory/vector differential; full4096-byte VRF after each of three phases and recovery; immutable A/B, buffer guards, VL/vtype/vstart/vxrm/vxsat/fcsr, terminal/protocol and exact thirteen vector op identities.',
                    distinguishing='C accepted commands lengths256 then255 then256 on all4 lanes; twelve valid nonfull FIFO pushes, four-slot rotation and matching pops; both directions of bits7/8 irrespective of initial write pointer; no discarded command or exception.',
                    runtime='Hard600s proposal; twelve VMACC operations/12272 active results plus recovery. Not measured; no budget extension.'),
                interpretation='This extends the old unrun48-slot proposal with actual FIFO copies. Capacity is modest, not a thousand-position/high-official-percent claim. Internal progress elem_count_d/q bit8 is excluded from gain prediction because terminal reset removes256. Bits9/10 are not stimulus targets.',
                dedup='Exact773 OR proves every listed coordinate still0, including all32 admitted suffixes after741. This is coverage-path dedup, not proof no historical ELF contains VMACC. No new ELF exists; exact ELF dedup/Spike preflight required before any proposed launch.',
                excluded_directions='Dispatcher idle/maintenance scalar/stride default mirrors, already prepared FP/LZC constant fields, full-covered numerical binary data and interface address/observer counters are not proposed. Arrays lack proven direction mapping and are not counted.',
                coordinate_semantics='Paired serialized positions, NOT native IDs or proven pair direction order; measured gain/official percent unavailable.',
                VCS_started=False, RTL_modified=False, waivers_changed=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    t.require(not args.output.exists(), 'Fresh report required')
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print('STATIC773_READY', result['zero_slots'], t.digest(args.output))
