"""Read-only exact raw740 toggle prefix union; no EDA or coverage exclusions."""
import argparse
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import dve_tool_identity as tools

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'verification/out/final-raw740-dve-prepared-agent-20261007-01/result.json'
RAW_SHA = '9d40c3f2fd087c7979ecf324a75094b21c516e180c225317b277ff0c1ea686bf'
ARA = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
QBS = ARA + '.i_vlsu.i_qbs_engine'


def require(value, message):
    if not value: raise ValueError(message)


def prefix(definition):
    result, offset = [], 0
    for node in definition.find('tglshape'):
        if node.tag not in ('node', 'vectornode'):
            break
        width = 1 if node.tag == 'node' else abs(int(node.get('left')) - int(node.get('right'))) + 1
        result.append(dict(signal=node.get('name'), raw_offset=offset, signal_width=width,
                           attributes=dict(node.attrib)))
        offset += 2 * width
    return result, offset


def missing(rows, bits):
    result = []
    for row in rows:
        start, width = row['raw_offset'], row['signal_width']
        require(start + 2 * width <= len(bits), 'Shape prefix exceeds actual data width')
        pairs = [bits[start + 2 * i:start + 2 * i + 2] for i in range(width)]
        zeros = [i for i, value in enumerate(pairs) if value == '00']
        if zeros and row['attributes'].get('excluded') == '0':
            result.append(dict(row, both_direction_zero_pairs=zeros, pair_values=pairs,
                fully_uncovered_vector=all(value == '00' for value in pairs),
                signal_bit_order='NOT_INFERRED_FROM_RAW_VECTOR_ORDER',
                direction_proof='00 proves neither direction observed; single-direction ordering not assumed'))
    return result


def scan():
    require(tools.seal_file(RAW)['sha256'] == RAW_SHA, 'Raw740 result drift')
    raw = json.loads(RAW.read_bytes()); pins = raw['pins']
    report = Path(raw['report'])
    inputs = (report / 'inputs.txt').read_text().splitlines()
    require(raw['tests'] == 740 and len(inputs) == len(set(inputs)) == 741, 'Exact740 required')
    db = Path(inputs[0]) / 'snps/coverage/db'
    paths = [db / 'shape/tgl.verilog.shape.xml', db / 'shape/tgl.verilog.info.xml']
    bound = {str(RAW): RAW_SHA}
    for path in paths + [report / 'inputs.txt']:
        require(tools.seal_file(path)['sha256'] == pins[str(path)], 'Pinned raw740 input drift')
        bound[str(path)] = pins[str(path)]
    definitions = {n.get('chksum'): n for n in ET.parse(gzip.open(paths[0], 'rb')).getroot().iter('tgldef')}
    infos = {n.get('name'): n.get('chksum') for n in ET.parse(gzip.open(paths[1], 'rb')).getroot().iter('instance_data')}
    scopes = [s for s in infos if (s.startswith(QBS + '.') and any(x in s for x in
        ('i_profile_engine_int', 'i_payload_buffer', 'i_profile_decoder', 'i_descriptor_decoder'))) or
        (s.startswith(ARA + '.gen_lanes[0].i_lane.i_operand_queues.') and s.count('.') < 14)]
    require(scopes, 'No exact selected toggle scopes')
    unions, checksums = {}, {}
    for i, name in enumerate(inputs[1:], 1):
        files = list((Path(name) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Missing/ambiguous native toggle data')
        path = files[0]; digest = tools.seal_file(path)['sha256']
        require(digest == pins[str(path)], 'Unpinned/changed formal740 toggle data')
        found = set()
        with gzip.open(path, 'rb') as stream:
            for _, node in ET.iterparse(stream, events=('end',)):
                if node.tag == 'instance_data' and node.get('name') in scopes:
                    scope = node.get('name'); bits = node.get('value', ''); checksum = node.get('chksum')
                    require(scope not in found and checksum == infos[scope] and bits and not set(bits) - {'0', '1'},
                            'Malformed native scope/encoding')
                    found.add(scope)
                    if scope not in unions:
                        unions[scope], checksums[scope] = bits, checksum
                    else:
                        require(len(bits) == len(unions[scope]), 'Native toggle width drift')
                        width = len(bits)
                        unions[scope] = format(int(unions[scope], 2) | int(bits, 2), '0%db' % width)
                node.clear()
        require(found == set(scopes), 'Missing native toggle scope')
        require(tools.seal_file(path)['sha256'] == digest, 'Native toggle file changed during read')
        bound[str(path)] = digest
        if i % 100 == 0: print('GAP113 readonly tgl union %d/740' % i, flush=True)
    results = {}
    for scope in scopes:
        definition = definitions[checksums[scope]]; rows, width = prefix(definition)
        results[scope] = dict(definition=dict(definition.attrib), actual_raw_width=len(unions[scope]),
            audited_prefix_width=width, prefix_union=unions[scope][:width], missing=missing(rows, unions[scope]))
    return dict(status='GAP113_READONLY_740_TOGGLE_PREFIX_EVIDENCE_NOT_STIMULUS_QUALIFICATION', population=740,
                source_raw_result=str(RAW), source_raw_seal=RAW_SHA, pins=bound, scopes=results,
                array_packing_inferred=False, EDA_launched=False, coverage_admitted=False, RTL_modified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); require(not args.output.exists(), 'Fresh output required')
    result = scan()
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), seal=tools.seal_file(args.output)['sha256'])))


if __name__ == '__main__': main()
