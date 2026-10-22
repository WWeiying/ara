"""Source-bound finite byte/writer mapping review; not native waiver approval."""
import argparse
import ast
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import classify_qbs_payload_hits762 as m
import prove_qbs_even_start_hits762 as even

ROOT = m.ROOT
OUT = ROOT / 'verification/out'
BASE = OUT / 'dtlb-ppn-swap-offline-admitted780-agent-20261008-01'
CACHE = OUT / 'qbs-engine-full102-residual766-static-agent-20261007-01.json'
CACHE_SHA = 'b6fefc0d350ed0ca4d3add37f3b6a43fd6cb4a79742dc2384d9f297abd5a8cca'
APPROVED = OUT / 'global777-compact-parent-20261007-03'
APPROVED_SHA = 'd118e7f4559664ead1cac0bde48e04e6ad68291bbd3a35fb8a9cc49fad648092'
BASE_SHA = '4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b'


def finite(bank, interleaved_step=4):
    """Superset of legal compact beats, not a simulation of arbitration.

    All even ROW starts and all four-aligned interleaved starts are included,
    even when a particular burst cannot produce them. Missing keys therefore
    prove impossibility; present keys alone do not prove a runtime hit.
    """
    m.require(bank in (0, 1) and interleaved_step in (2, 4), 'Domain')
    keys, witnesses = set(), {}

    def add(kind, row, plane, lane, writer, witness):
        key = kind, row, plane, lane, writer
        keys.add(key)
        witnesses.setdefault(key, witness)

    for profile, size in enumerate(m.SIZES, 1):
        for grouped in (False, True):
            for start in range(0, size * (4 if grouped else 1), 2):
                for b in range(16):
                    source = start + b
                    row, offset = divmod(source, size) if grouped else (0, source)
                    if row >= 4 or offset >= size:
                        continue
                    plane, dest = m.weight_location(profile, offset)
                    for local in ((row,) if grouped else range(4)):
                        add('weight', local, plane, dest % (20 if plane == 2 else 16), b,
                            dict(profile=profile, layout='R4' if grouped else 'ROW',
                                 start=start, writer=b, block_offset=offset, destination=dest))
    for scale, quants in ((4, 256), (2, 32)):
        size = scale + quants + (32 if quants == 256 else 0)
        for contexts in (1, 4, 8):
            step = 2 if contexts == 1 else interleaved_step
            for start in range(0, contexts * size, step):
                for b in range(16):
                    source = start + b
                    if source >= contexts * size:
                        continue
                    ctx, offset = m.activation_target(source, contexts, scale, quants)
                    for local in (range(4) if contexts == 1 else (ctx - 4 * bank,)):
                        if not 0 <= local < 4:
                            continue
                        plane, dest = m.activation_location(offset, scale, quants)
                        lane = dest % 32 if plane == 0 else dest
                        if plane == 2 and lane >= 36:
                            continue
                        add('activation', local, plane, lane, b,
                            dict(scale=scale, quants=quants, contexts=contexts,
                                 start=start, writer=b, context=local + 4 * bank,
                                 block_offset=offset, destination=dest))
    return keys, witnesses


def activation_main_possible(row, lane, writer):
    return lane % 2 == writer % 2 or writer % 4 == row


def legal_activation_beats(bank=0):
    """Concrete aligned range witnesses; still not pending arbitration proof."""
    witnesses = {}
    for scale, quants in ((4, 256), (2, 32)):
        size = scale + quants + (32 if quants == 256 else 0)
        for contexts in (1, 4, 8):
            for base_low in (0, 4, 8, 12):
                for k in (0, 1):
                    # Kblocks=2, local row0; M8 enables both context banks.
                    offset = k * size * contexts if contexts != 1 else (4 * bank * 2 + k) * size
                    address = 0x80010000 + base_low + offset
                    for start, first, take in even.compact_range(address, contexts * size):
                        for b in range(take):
                            ctx, target = m.activation_target(start + b, contexts, scale, quants)
                            ctx = 4 * bank if contexts == 1 else ctx
                            if ctx != 4 * bank:
                                continue
                            plane, dest = m.activation_location(target, scale, quants)
                            if plane != 0:
                                continue
                            key = ('activation', 0, 0, dest % 32, b)
                            witnesses.setdefault(key, dict(scale=scale, quants=quants,
                                contexts=contexts, Kblocks=2, k=k, base=0x80010000 + base_low,
                                range_address=address, range_bytes=contexts * size,
                                response_offset=start, first_lane=first, take=take,
                                writer=b, context=ctx, destination=dest))
    return witnesses


def source_proof(pins):
    book = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
    m.require(m.digest(book) == '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b',
              'Frozen build source book drift')
    anchors = even.source_chain(pins)
    compute = ROOT / 'hardware/src/vlsu/qbs/qbs_compute_engine.sv'
    expected = json.loads(book.read_bytes())[str(compute)]
    m.require(m.digest(compute) == expected, 'Consumed-mask producer drift')
    pins[str(compute)] = expected
    engine = (ROOT / 'hardware/src/vlsu/qbs/qbs_engine.sv').read_text()
    context = (ROOT / 'hardware/src/vlsu/qbs/qbs_activation_context.sv').read_text()
    pkg = (ROOT / 'hardware/include/qbs_pkg.sv').read_text()
    for needle in ('address_offset = 64\'(activation_k_offset_q) * storage_m;',
                   'activation_k_offset_q <= compute_expected_k * activation_block_bytes_q;',
                   'activation_row_bytes_q <= descriptor_k_blocks * descriptor_activation_block_bytes;'):
        m.require(needle in engine, 'Interleaved address recurrence drift')
    m.require('unsigned\'(replay_issue_beat_q) * BeatBytes;' in context and
              "replay_offset_q <= 11'(byte_offset);" in context, 'Replay writer domain')
    m.require(re.search(r'QbsWeightBaseAlignmentLog2\s*=\s*1\s*;', pkg) and
              re.search(r'QbsActivationBaseAlignmentLog2\s*=\s*2\s*;', pkg), 'ABI alignment')
    # Compact read recurrence checked at every page offset, not just fixtures.
    beats = 0
    for low in range(0, 4096, 4):
        for length in (4 * 34, 8 * 34, 4 * 292, 8 * 292):
            rows = even.compact_range(low, length)
            m.require(all(o % 4 == f % 4 == t % 4 == 0 for o, f, t in rows),
                      'Four-aligned page/burst recurrence')
            beats += len(rows)
    return dict(anchors=anchors, checked_interleaved_beats=beats,
        induction=[
            'Weight base2 + even block/row/K strides => start even; ROW activation likewise even.',
            'M4/M8 base4 + K*block_bytes*storage_m => address4, length4; page4096 and burst256 preserve offset4.',
            'Context replay offset=beat_index*16; tail4 and ingress compact writer b preserve congruence.',
            'All nine weight region subtractions even => destination parity equals original writer parity.',
            'Activation ROW quant offset subtracts scale2/4; M4/M8 quant ctx modulo4 equals original writer modulo4.',
            'Pending copies target/location/data/remaining_strb at the SAME b; drain can remove bytes but cannot recompact.',
            'Reset strb=0 prevents unknown metadata hit; stale legal captured metadata is included in the union of ALL profiles/layouts.'
        ], no_initial_X_exclusion=True)


def report():
    pins = {}

    def read(path, sha=None):
        path = Path(path)
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        m.require(sha is None or actual == sha, 'Input drift: ' + str(path))
        pins[str(path)] = actual
        return data

    manifest = json.loads(read(BASE / 'admission-manifest.json', BASE_SHA))
    m.require(manifest['coverage_admitted'] is True, 'Formal780 required')
    ledger_path = BASE / 'combined-inputs.txt'
    ledger = read(ledger_path, manifest['output_pins'][str(ledger_path)]).decode().splitlines()
    m.require(len(ledger) == len(set(ledger)) == 781, 'Exact780 membership')
    cache = json.loads(read(CACHE, CACHE_SHA))
    prior = next(Path(p) for p in cache['pins'] if p.endswith('/combined-inputs.txt'))
    prefix = read(prior, cache['pins'][str(prior)]).decode().splitlines()
    m.require(len(prefix) == 767 and ledger[:767] == prefix, 'Exact766 cache prefix')
    summaries = {x['scope']: x for x in cache['scope_summaries'] if x['module'] == 'qbs_payload_buffer'}
    m.require(len(summaries) == 2, 'Both compiled banks')
    raw = {s: int(row['bits'], 16) for s, row in summaries.items()}
    for db in ledger[767:]:
        files = list((Path(db) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        m.require(len(files) == 1, 'Unique suffix Toggle file')
        tree = ET.fromstring(gzip.decompress(read(files[0], manifest['input_pins'][str(files[0])])))
        for scope in raw:
            rows = [n for n in tree.iter('instance_data') if n.get('name') == scope]
            m.require(len(rows) == 1 and rows[0].get('chksum') == '3657545390', 'Scope checksum')
            bits = rows[0].get('value')
            m.require(len(bits) == 66340 and set(bits) <= {'0', '1'}, 'Typed width')
            raw[scope] |= int(bits, 2)
    shape_path = next(Path(p) for p in cache['pins'] if p.endswith('/shape/tgl.verilog.shape.xml'))
    shape = ET.fromstring(gzip.decompress(read(shape_path, cache['pins'][str(shape_path)])))
    defs = [n for n in shape.iter('tgldef') if n.get('name') == 'qbs_payload_buffer' and n.get('chksum') == '3657545390']
    m.require(len(defs) == 1, 'Unique compiled shape')
    offsets, offset = {}, 0
    for n in defs[0].find('tglshape'):
        m.require(n.tag in ('node', 'vectornode'), 'No guessed array flattening')
        width = abs(int(n.get('left', '0')) - int(n.get('right', '0'))) + 1
        offsets[n.get('name')] = (dict(n.attrib), offset, width)
        offset += 2 * width
    m.require(offset == 66340, 'Full typed payload width')
    approved = json.loads(read(APPROVED / 'config.json', APPROVED_SHA))
    el = read(APPROVED / 'combined.el', approved['pins'][str(APPROVED / 'combined.el')]).decode()
    # Reuse exact reviewed grammar without importing global report/ELF consumers.
    parser = ROOT / 'verification/coverage/audit_remaining_toggle776.py'
    tree = ast.parse(read(parser).decode())
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('el_fields', 'excluded_bits')]
    m.require(len(functions) == 2, 'Reviewed EL grammar functions')
    ns = dict(re=re, defaultdict=defaultdict, t=SimpleNamespace(require=m.require))
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(parser), 'exec'), ns)
    el_fields, whole = ns['el_fields'](el)
    source = source_proof(pins)
    records, counts, sample = [], Counter(), None
    for scope in raw:
        bank = int(re.search(r'bank([01])\.', scope)[1])
        if bank != 0:
            continue
        m.require(scope not in whole, 'Whole payload exclusion forbidden')
        possible, witnesses = finite(bank)
        for row in range(4):
            for lane in range(32):
                for writer in range(16):
                    m.require((('activation', row, 0, lane, writer) in possible) ==
                              activation_main_possible(row, lane, writer), 'Closed-form iff disagreement')
        legal = legal_activation_beats(bank)
        for name, (attr, start, width) in offsets.items():
            if not (name.startswith('gen_write_merge[1].gen_bank_plane[2].gen_bank_row[0].')
                    and name.endswith('.hit')):
                continue
            m.require(attr.get('right') == '0' and width in (16, 32), 'Exact hit bit shape')
            removed, ambiguous = ns['excluded_bits'](el_fields.get((scope, name), []), set(range(width)))
            m.require(not ambiguous, 'One-direction EL ownership HOLD')
            for bit in range(width):
                key, slot, side = m.identity(name, bit)
                coords = [start + 2 * bit + d for d in (0, 1)]
                missing = [c for c in coords if not (raw[scope] >> (66339 - c)) & 1]
                impossible = key not in possible
                if impossible:
                    m.require(len(missing) == 2, 'Observed counterexample: ' + str((scope, name, bit)))
                if bit in removed or not missing:
                    continue
                status = 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED' if impossible else 'MAPPING_WITNESS_ARBITRATION_HOLD'
                counts[status] += len(missing)
                item = dict(scope=scope, checksum='3657545390', signal=name, bit=bit,
                            raw_coordinates=missing, slot=slot, side=side, classification=status,
                            mapping_witness=None if impossible else witnesses[key],
                            legal_compact_read_witness=legal.get(key))
                records.append(item)
                if sample is None and key in legal and not impossible and slot == 1 and not side:
                    sample = item
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prove_qbs_hit_congruence780.py'),
                 Path(m.__file__), Path(even.__file__)):
        read(path)
    return dict(schema='QBS_HIT_CONGRUENCE780_STATIC_V1', population=780, pins=pins,
        source_proof=source, residual_directions_by_class=dict(counts), records=records,
        example_missing_mapping_witness=sample,
        reviewed_subset='bank0 main plane2 slot1 row0 only; 32 byte lanes x16 original writers',
        activation_main_closed_form='possible iff lane%2==writer%2 OR writer%4==local_row (union ROW/M4/M8)',
        authority='Finite superset absence is source candidate only; witnesses do not prove word selection/pending arbitration.',
        proposed_discriminator='Use saved legal mapping witness only after reconstructing address first_lane/take and selected_word ownership; no data-only complement test.',
        retained='All other bits, selected[8], valid/BE/control/ports and all MDA; no EL emitted.',
        no_EDA=True, native_qualification=False, official_denominator=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    result = report()
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output), counts=result['residual_directions_by_class'],
                          sha256=m.digest(args.output))))
