"""Read-only scale stimulus triage: exact741 serialized union plus admitted742 singleton."""
import json
import re
from pathlib import Path
import targeted_toggle_evidence_v2 as t

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
BASE = OUT / 'gap113-full8-cached-offline-admitted-742-agent-20261007-01'
BASE_SHA = 'f07f7ccdcfc7257faad21aabdc45a48008658c70ee26abda275065f1e204a730'
RANK = OUT / 'toggle741-capacity-ranking-agent-20261007-01.json'


def scalar_shape(definition, width):
    result, offset = [], 0
    for n in definition.find('tglshape'):
        if n.tag == 'arrays':
            continue  # Interval objects are not binary instance_data positions.
        t.require(n.tag in ('node', 'vectornode'), 'Unknown shape object')
        size = 1 if n.tag == 'node' else abs(int(n.get('left')) - int(n.get('right'))) + 1
        result.append(dict(signal=n.get('name'), attributes=dict(n.attrib),
                           raw_offset=offset, width=size))
        offset += 2 * size
    t.require(offset == width, 'Complete scalar shape width differs')
    return result


def collect():
    t.require(t.digest(BASE / 'admission-manifest.json') == BASE_SHA, 'Formal742 drift')
    formal = json.loads((BASE / 'admission-manifest.json').read_bytes())
    rank = json.loads(RANK.read_bytes())
    t.require(rank['tests'] == 741, 'Not741 union')
    pins = {str(BASE / 'admission-manifest.json'): BASE_SHA, str(RANK): t.digest(RANK)}
    pins.update(rank['input_pins'])
    ledger = (BASE / 'combined-inputs.txt').read_text().splitlines()
    old = Path(next(p for p in rank['input_pins'] if p.endswith('/inputs.txt'))).read_text().splitlines()
    t.require(len(ledger) == 743 and ledger[:-1] == old and len(set(ledger)) == 743,
              'Exact741 prefix + singleton required')
    pins[str(BASE / 'combined-inputs.txt')] = t.digest(BASE / 'combined-inputs.txt')
    db = Path(ledger[0]) / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'shape/tgl.verilog.info.xml',
             db / 'shape/tgl.verilog.shape.xml']
    scopes = [s for s in rank['instances'] if s.endswith(
        ('.i_payload_buffer', '.i_profile_engine_int', '.i_fp_accumulator'))]
    checks, definitions = t.definitions(*(t.xml(p) for p in paths), scopes)
    pins.update({str(p): t.digest(p) for p in paths})
    files = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    t.require(len(files) == 1, 'Ambiguous742 Toggle singleton')
    sample, sha = t.rows(files[0], scopes)
    pins[str(files[0])] = sha
    targets = []
    for s in scopes:
        b = rank['instances'][s]
        v = sample[s]
        t.require(b['checksum'] == checks[s] == v['checksum'] and b['width'] == v['width'],
                  'Native shape/checksum/width drift')
        bits = format(int(b['bits'], 16) | int(v['bits'], 16), '0%db' % b['width'])
        definition = __import__('xml.etree.ElementTree', fromlist=['fromstring']).fromstring(definitions[s]['shape'])
        for row in scalar_shape(definition, len(bits)):
            name = row['signal']
            if not (name in ('request_weight_d_i', 'request_activation_d_i',
                             'result_weight_d_o', 'result_activation_d_o') or
                    re.fullmatch(r'gen_side_row\[[0-3]\].gen_weight_byte\[1[23]\].newer', name) or
                    re.fullmatch(r'gen_side_row\[[0-3]\].gen_activation_byte\[[0-3]\].newer', name)):
                continue
            offset, width = row['raw_offset'], row['width']
            pairs = [bits[offset+2*i:offset+2*i+2] for i in range(width)]
            targets.append(dict(scope=s, checksum=checks[s], **row,
                pairs=pairs, zero_serialized_positions=[offset+i for i, x in enumerate(bits[offset:offset+2*width]) if x == '0'],
                both_zero_pair_indices=[i for i, p in enumerate(pairs) if p == '00'],
                bit_direction_order='NOT_CLAIMED; pair00 independent of direction/bit orientation'))
    for p, sha in pins.items():
        t.require(t.digest(Path(p)) == sha, 'Input drift: ' + p)
    return dict(status='EXACT742_SCALE_GAP_STATIC_DIAGNOSTIC_NOT_STIMULUS_PASS',
        population=742, formal_seal=BASE_SHA, targets=targets, input_pins=pins,
        omitted_internal_arrays=['weight_side_q', 'activation_side_q',
                                 'entry_scale_value_q', 'entry_work_value_q'],
        omitted_reason='No named objects in frozen tglshape; do not invent raw coordinates or interval mapping',
        side_byte_mapping='Frozen qbs_pkg: Q3 d source108/109 -> side12/13; Q8K activation d source0..3 -> side0..3',
        simulations_started=False, RTL_modified=False, coverage_admitted=False,
        official_toggle_gain=None)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    t.require(not a.output.exists(), 'Fresh output required')
    result = collect()
    with a.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(a.output), seal=t.digest(a.output),
        targets=len(result['targets']), serialized_zeros=sum(len(r['zero_serialized_positions']) for r in result['targets']))))
