"""Read-only serialized Toggle capacity ranking; not DVE score denominators."""
import csv
import gzip
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from targeted_toggle_evidence import digest, require


def collect():
    out = Path(__file__).resolve().parents[1] / 'out'
    audit_path = out / 'raw741-post-export-audit-20261007-01.json'
    audit = json.loads(audit_path.read_bytes())
    require(audit['status'] == 'RAW741_POST_EXPORT_IDENTITY_WAIVER_AUDIT_PASS' and
            audit['selected_count'] == 741 and audit['exclusions'] == [], 'Not raw741')
    report = Path(audit['report'])
    inputs, summary = report / 'inputs.txt', report / 'summary.csv'
    pins = {str(audit_path): digest(audit_path)}
    for p in (inputs, summary):
        require(digest(p) == audit['report_pins'][str(p)], 'Report drift')
        pins[str(p)] = digest(p)
    ledger = inputs.read_text().splitlines()
    require(len(ledger) == 742 and len(set(ledger)) == 742, 'Population differs')
    metrics = {}
    selected = []
    for index, vdb in enumerate(ledger[1:], 1):
        files = list((Path(vdb) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(files) == 1, 'Ambiguous native test')
        p = files[0]
        sha = digest(p)
        require(sha == audit['source_pins'][str(p)], 'Native Toggle pin drift')
        pins[str(p)] = sha
        selected.append(str(p))
        seen = set()
        with gzip.open(p, 'rb') as stream:
            for _, node in ET.iterparse(stream, events=('end',)):
                if node.tag != 'instance_data':
                    continue
                name, value, checksum = node.get('name'), node.get('value'), node.get('chksum')
                require(name not in seen and value and not set(value) - {'0', '1'} and
                        checksum is not None, 'Invalid native row')
                seen.add(name)
                width, bits = len(value), int(value, 2)
                if index == 1:
                    metrics[name] = [width, checksum, bits]
                else:
                    require(name in metrics and metrics[name][:2] == [width, checksum],
                            'Native width/checksum drift')
                    metrics[name][2] |= bits
                node.clear()
        require(seen == set(metrics), 'Native scope universe differs')
        require(digest(p) == sha, 'Native data changed during read')
        if index % 100 == 0:
            print('Readonly Toggle union %d/741' % index, flush=True)
    percentages, stack = {}, []
    with summary.open() as stream:
        for row in csv.DictReader(stream):
            depth = int(row['Depth'])
            stack = stack[:depth]
            stack.append(row['Name'])
            percentages['.'.join(stack)] = row['Toggle']
    require(set(percentages) == set(metrics), 'CSV/native hierarchy differs')
    local = {s: dict(width=w, checksum=c, hit=bin(b).count('1'),
                     missing=w - bin(b).count('1'), bits=hex(b),
                     dve_toggle_percent=percentages[s]) for s, (w, c, b) in metrics.items()}
    roots = ['ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine',
             'ara_tb.dut.i_ara_soc.i_system.i_cva6.i_ptw']
    roots += [s for s in metrics if s.endswith(('.operand_queues', '.i_operand_queues', '.i_vrf'))]
    roots += [s for s in metrics if s.endswith('.i_ptw') and s not in roots]
    ranked = []
    for root in roots:
        children = [v for s, v in local.items() if s == root or s.startswith(root + '.')]
        if not children:
            continue
        ranked.append(dict(scope=root, instances=len(children),
                           serialized_capacity=sum(v['width'] for v in children),
                           serialized_missing=sum(v['missing'] for v in children),
                           dve_toggle_percent=percentages[root]))
    ranked.sort(key=lambda r: r['serialized_missing'], reverse=True)
    for p, sha in pins.items():
        require(digest(p) == sha, 'Phase-end pin drift')
    return dict(schema='RAW741_TOGGLE_SERIALIZED_CAPACITY_V1', tests=741,
                semantics='Serialized instance direction positions; NOT official DVE score denominator. '
                          'Parent rows aggregate descendants; do not add overlapping ranked rows.',
                official_denominator_available=False, ranking=ranked, instances=local,
                input_pins=pins, simulations_started=False, DVE_started=False)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'Fresh output required')
    result = collect()
    with args.output.open('x') as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write('\n')
    print(json.dumps(result['ranking'], indent=2))
