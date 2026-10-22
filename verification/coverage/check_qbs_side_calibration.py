"""Bind three executed VCS paths to branch vectors; no processor exclusions."""
import argparse
import hashlib
import json
from pathlib import Path
from closure_point_inventory import read_xml, points
from coverage_bitmap_delta import read_metric

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT / 'verification/out/qbs-side-path-calibration-20261006-01'
    shape = base / 'compile.vdb/snps/coverage/db/shape/branch.verilog.shape.xml'
    doc = read_xml(shape)
    paths = [shape, base / 'compile.log', Path(__file__).resolve(),
             ROOT / 'verification/tests/qbs_side_path_calibration.sv']
    result = []
    for mode, expected in ((0, '1000'), (1, '0101'), (2, '0011')):
        data = base / ('mode%d.vdb/snps/coverage/db/testdata/mode%d/branch.verilog.data.xml' % (mode, mode))
        log = base / ('mode%d.log' % mode)
        paths += [data, log]
        if log.read_text().count('CALIBRATION_PASS mode=%d ' % mode) != 1:
            raise ValueError('Missing actual successful calibration')
        row = read_metric(data)['qbs_side_path_calibration.dut']
        nodes = [n for n in doc.iter('branch_def') if n.get('chksum') == row['checksum']]
        if len(nodes) != 1 or row['width'] != 3:
            raise ValueError('Calibration shape changed')
        hit = [p for p in points('branch', nodes[0], row['width']) if
               int(row['bits'], 16) & (1 << (row['width'] - 1 - p['raw_index']))]
        if len(hit) != 1 or hit[0]['native_vector']['vector'] != expected:
            raise ValueError('Executed path did not uniquely identify expected vector')
        result.append(dict(mode=mode, meaning=('disabled', 'older_selected', 'newer_selected')[mode],
                           point=hit[0], bitmap=row))
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with args.output.open('x') as stream:
        json.dump(dict(status='VCS_PATH_ENCODING_CALIBRATED_NOT_PROCESSOR_WAIVER',
            paths=result, pins=pins, processor_coverage_added=False, native_DVE_qualified=False), stream, indent=2)
        stream.write('\n')
    print('VCS mapping: 1000=disabled, 0101=older_selected, 0011=newer_selected')


if __name__ == '__main__':
    main()
