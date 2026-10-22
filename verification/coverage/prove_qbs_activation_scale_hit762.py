"""Exact source-bound bank0 scale-hit candidate certificate, not a native receipt."""
import argparse
import json
from pathlib import Path

import classify_qbs_payload_hits762 as mapping

ROOT = mapping.ROOT
REPORT = ROOT/'verification/out/qbs-payload-missing-hit-classification762-agent-20261007-01.json'
REPORT_SHA = 'd1a7b768f8dfa0979186b2a7feba0cb1e1af123c7e1cb9d91d5efb3ed3b4f07b'


def bound(row, byte):
    mapping.require(type(row) is int and type(byte) is int and
                    0 <= row < 4 and 0 <= byte < 4, 'Scale bound domain')
    return 4*row+byte


def exhaustive_bound():
    checked, feasible = 0, set()
    for scale, quants in ((4,256),(2,32)):
        size = scale+quants+(32 if quants == 256 else 0)
        for contexts in (1,4,8):
            for index in range(contexts*size):
                context, offset = mapping.activation_target(index,contexts,scale,quants)
                plane, destination = mapping.activation_location(offset,scale,quants)
                if plane != 2 or destination >= 4: continue
                # Aux starts at scale (4 for K); Q8_0 has no aux. Thus every
                # valid side byte0..3 here is a scale byte, not quant or bsum.
                mapping.require(offset < scale, 'Aux aliases scale bytes')
                rows = range(4) if contexts == 1 else (context,)
                for row in rows:
                    if row >= 4: continue
                    mapping.require(index <= bound(row,destination), 'Scale source index exceeds universal bound')
                    for writer in range(16):
                        # unsigned 12-bit source start plus writer never wraps
                        # a 32-bit unsigned int. Every accepted target requires
                        # start=index-writer >=0. Strobes only remove targets.
                        if writer <= index:
                            feasible.add((row,destination,writer))
                        checked += 1
    expected = {(r,b,w) for r in range(4) for b in range(4) for w in range(16)
                if w <= bound(r,b)}
    mapping.require(feasible == expected, 'Envelope has unexpected feasible/missing ownership')
    impossible = sorted((r,b,w) for r in range(4) for b in range(4) for w in range(16)
                        if w > bound(r,b))
    mapping.require(len(impossible) == 120, 'Expected exact120 physical bits')
    return impossible, checked


def certify():
    mapping.require(mapping.digest(REPORT) == REPORT_SHA, 'Classification report drift')
    report = json.loads(REPORT.read_bytes())
    mapping.require(report['baseline'] == 762 and not report['exclusions_approved'], 'Not scoped static report')
    pins = dict(report['source_pins'])
    for path, sha in pins.items():
        mapping.require(mapping.digest(path) == sha, 'Input pin drift: '+path)
    pins[str(REPORT)] = REPORT_SHA
    for path in (Path(__file__).resolve(), Path(__file__).with_name('test_prove_qbs_activation_scale_hit762.py')):
        pins[str(path)] = mapping.digest(path)
    impossible, checked = exhaustive_bound()
    targets = []
    counts = {}
    for scope, data in report['scopes'].items():
        counts[scope] = data['missing_directions_by_class']
        for item in data['records']:
            if item['classification'] != 'FINITE_MAPPING_IMPOSSIBLE_CANDIDATE': continue
            mapping.require('bank0.i_payload_buffer' in scope, 'Unexpected constant in bank1')
            key, slot, side = mapping.identity(item['signal'],item['bit'])
            kind, row, plane, byte, writer = key
            mapping.require(kind == 'activation' and side and slot == 1 and plane == 2 and
                            (row,byte,writer) in impossible and len(item['missing_serialized_coordinates']) == 2,
                            'Candidate is outside scale-bound invariant')
            targets.append(dict(scope=scope, signal=item['signal'], bit=item['bit'],
                left=item['left'], right=item['right'], declaration_line=item['declaration_line'],
                toggle_checksum=data['checksum'], raw_offset=item['raw_offset'],
                raw_coordinates=item['missing_serialized_coordinates'],
                source_index_max=bound(row,byte), writer=writer,
                native_directions=['0to1','1to0']))
    mapping.require(len(targets) == 120 and len({(t['scope'],t['signal'],t['bit']) for t in targets}) == 120,
                    'Candidate duplication/omission')
    return dict(schema='QBS_BANK0_ACTIVATION_SCALE_HIT120_SOURCE_CERTIFICATE_V1', baseline=762,
        status='SOURCE_PROVEN_EXACT120_BITS_NATIVE_QUALIFICATION_REQUIRED', pins=pins,
        targets=targets, direction_count=240, enumeration_checks=checked,
        universal_bound='bank0 side scale byte b at local row r: source_index <=4*r+b; writer j requires source_start+j=source_index and source_start>=0; j>4*r+b cannot hit',
        profile_layout_scope='Both activation profiles and row-major/M4/M8. Q8_K scales4, aux side starts4; Q8_0 scales2, no aux. Weight profiles cannot alter activation mapping.',
        temporal_scope='Every stored ingress target/location is captured together at acceptance; writer index is retained. Inactive stale ingress metadata from any earlier legal profile/layout satisfies the same union invariant. No assumption on valid_i or drain timing.',
        native_plan='Qualify exactly these120 bit-selects (240 directions), save/export/reset/import/export/finalreset. Bind actual declaration/net signature, design+Toggle checksum and full complement audits. Do not select entire hit vectors.',
        protected='ALL hit bits outside120, all selected[8]/newer[8]/older[8]/BE/byte_valid/consumed/ready/valid and other datapath/control signals. Old1792 projection is separate; do not silently add it.',
        missing_direction_accounting=counts, native_receipt=False, EDA_started=False,
        reachability_limit='All other mapping witnesses remain necessary conditions only; no architectural reachability approval or waiver. Pending drain and producer/arbitration HOLD remain unchanged.',
        initial_X='Normal legal post-acceptance/reset routing invariant only; no initial-X exclusion or MBIST claim.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = certify()
    with args.output.open('x') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    print(json.dumps(dict(path=str(args.output),sha256=mapping.digest(args.output),
                         targets=len(result['targets']),directions=result['direction_count'])))


if __name__ == '__main__': main()
