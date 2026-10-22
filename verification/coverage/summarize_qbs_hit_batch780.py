"""Compact exact main/side zero and HOLD sets; no EL, EDA or approval."""
import argparse
from collections import Counter
import inspect
import json
from pathlib import Path

import classify_qbs_all_hits780 as q

CLASSIFIER_SHA = '8c14c79507c9a839222904509bd55e4f96b2529c2050d8b45e688edf9dd6155f'
QUAL = q.p.OUT / 'qbs-hit128-native780-bank0-p2-slot1-row0-agent-20261008-01/capture-result.json'
QUAL_SHA = 'f2de6691f6e94a08061ae97b82aeee23c4779ebbe41aa8c06fb16e75182f21a3'


def compact(records, qualified):
    groups, counts, breakdown, seen = {}, Counter(), Counter(), set()
    for item in records:
        identity = item['scope'], item['signal'], item['bit']
        q.p.m.require(identity not in seen, 'Duplicate typed coordinate')
        seen.add(identity)
        (kind, row, plane, lane, writer), slot, side = q.p.m.identity(item['signal'], item['bit'])
        coordinates = sorted(item['raw_coordinates'])
        q.p.m.require(coordinates and len(coordinates) <= 2 and len(set(coordinates)) == len(coordinates), 'Direction coordinates')
        status = item['classification']
        if status == 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED':
            q.p.m.require(len(coordinates) == 2 and coordinates[1] == coordinates[0] + 1
                          and item['mapping_witness'] is None, 'Zero proof cannot contain an observed direction')
            status = 'QUALIFIED128_NOT_APPLIED' if identity in qualified else 'NEW_ZERO_NATIVE_REQUIRED'
        else:
            q.p.m.require(identity not in qualified, 'Qualified subset contradicts proof')
            status = 'HOLD_MAPPING_NOT_RUNTIME_PROOF'
        bank = 0 if 'bank0.' in item['scope'] else 1
        key = item['scope'], item['signal'], status
        group = groups.setdefault(key, dict(scope=item['scope'], checksum=item['checksum'],
            signal=item['signal'], classification=status, bank=bank, kind=kind,
            plane=plane, row=row, byte_lane=lane, side=side, bit_missing_coordinates={},
            original_writer_slots={}))
        group['bit_missing_coordinates'][str(item['bit'])] = coordinates
        group['original_writer_slots'][str(item['bit'])] = [slot, writer]
        counts[status] += len(coordinates)
        breakdown[str((bank, 'side' if side else 'main', kind, status))] += len(coordinates)
    q.p.m.require(sum(counts.values()) == sum(len(r['raw_coordinates']) for r in records), 'Complete partition')
    return dict(counts=dict(counts), breakdown=dict(breakdown),
                target_groups=[g for g in groups.values() if g['classification'] != 'HOLD_MAPPING_NOT_RUNTIME_PROOF'],
                HOLD_groups=[g for g in groups.values() if g['classification'] == 'HOLD_MAPPING_NOT_RUNTIME_PROOF'])


def evidence():
    q.p.m.require(q.p.m.digest(Path(q.__file__)) == CLASSIFIER_SHA and
                  q.p.m.digest(Path(q.p.__file__)) == q.SOURCE_SHA, 'Frozen finite proof sources')
    raw = q.expanded_function(inspect.getsource(q.p.report))()
    qualification = json.loads(QUAL.read_bytes())
    q.p.m.require(q.p.m.digest(QUAL) == QUAL_SHA and qualification['bit_directions'] == 128
                  and qualification['physical_bits'] == 64 and qualification['population_application'] is False
                  and qualification['status'] == 'QBS_BANK0_P2_SLOT1_ROW0_EXACT128_NATIVE_NOT_APPLIED',
                  'Qualified local128 owner')
    config = json.loads(q.PENDING.read_bytes())
    q.p.m.require(q.p.m.digest(q.PENDING) == q.PENDING_SHA, 'Exact local128 config')
    qualified = {(i['scope'], s['name'], b) for i in config['instances'] for s in i['signals'] for b in s['bits']}
    result = compact(raw['records'], qualified)
    q.p.m.require(result['counts'] == dict(NEW_ZERO_NATIVE_REQUIRED=9440,
        QUALIFIED128_NOT_APPLIED=128, HOLD_MAPPING_NOT_RUNTIME_PROOF=18401), 'Exact780 partition')
    pins = dict(raw['pins'])
    for path in (Path(q.__file__), q.PENDING, QUAL, Path(__file__).resolve(),
                 Path(__file__).with_name('test_summarize_qbs_hit_batch780.py')):
        pins[str(path)] = q.p.m.digest(path)
    return dict(schema='QBS_MAIN_SIDE_EXACT_BATCH780_STATIC_V1', population=780, pins=pins,
        **result, source_proof=raw['source_proof'],
        new_target_bits=4720, new_target_objects=688,
        original_writer_domain='b0..15 preserved through pending; side bit=16*slot+b; main bit=b; no recompact.',
        legal_union='nine weight profiles ROW/R4; activation Q8K/Q8_0 ROW/M4/M8, both banks and all four local rows; DIRECT/FILL/REUSE included.',
        source_paths=['qbs_pkg ABI weight2/activation4 alignment', 'qbs_engine form_read_range',
                      'qbs_read_engine range_offset/take recurrence', 'qbs_activation_context replay beat*16',
                      'qbs_block_adapter target/location/remaining mask same-b capture',
                      'qbs_payload_buffer main word_match & byte_select; side row_mask & side_offset'],
        proof_boundary='Zero means absent in full legal mapping superset, not merely unobserved; HOLD presence does not prove pending arbitration/runtime reachability.',
        old_EL_duplicates_removed=True, retained='All other bits, data, selected[8], BE, valid, controls, interfaces and MDA.',
        no_EDA=True, aggregate_application=False, official_percentage_gain=None)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('--output', type=Path, required=True)
    a = cli.parse_args()
    result = evidence()
    with a.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True, separators=(',', ':'))
        stream.write('\n')
    print(json.dumps(dict(output=str(a.output), sha256=q.p.m.digest(a.output), counts=result['counts'])))
