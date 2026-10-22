"""Source-bound unhit side-write paths; native path semantics remain unqualified."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from inventory_operand_debug import ROOT, Design
from closure_point_inventory import definition, points, read_xml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT / 'verification/out/repaired-aligned-build-20260930-01'
    build_path = base / 'build-source-pins.json'
    bitmap_path = ROOT / 'verification/out/gap83-offline-admitted-690-20261006-02/combined-bits.json'
    build = json.loads(build_path.read_bytes())
    bitmap = json.loads(bitmap_path.read_bytes())
    vdb = base / 'sim/simv.vdb'
    shape_path = vdb / 'snps/coverage/db/shape/branch.verilog.shape.xml'
    paths = [build_path, bitmap_path, shape_path,
             vdb / 'snps/coverage/db/design/verilog.design.xml', Path(__file__).resolve()]
    for name in ('qbs_payload_buffer', 'qbs_block_adapter', 'qbs_compute_engine'):
        path = ROOT / ('hardware/src/vlsu/qbs/' + name + '.sv')
        if hashlib.sha256(path.read_bytes()).hexdigest() != build[str(path)]:
            raise ValueError('Source not identical to compiled pin')
        paths.append(path)
    pins = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    if pins[str(shape_path)] != bitmap['design']['shape/branch.verilog.shape.xml']:
        raise ValueError('Shape drift')
    design, shape = Design(vdb), read_xml(shape_path)
    rows, counts = [], Counter()
    for bank in (0, 1):
        scope = ('ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.'
                 'i_compute_engine.i_block_adapter_bank%d.i_payload_buffer' % bank)
        if design.source(scope)['resolved_path'] != str(ROOT / 'hardware/src/vlsu/qbs/qbs_payload_buffer.sv'):
            raise ValueError('Wrong source owner')
        record = bitmap['metrics']['branch'][scope]
        node = definition(shape, design.hierarchy[scope], record['checksum'])
        for point in points('branch', node, record['width']):
            if point['line'] not in ('378', '403'):
                continue
            expressions = point['expressions']
            if (len(expressions) != 2 or not expressions[0]['exprstr'].endswith('.enable')
                    or not expressions[1]['exprstr'].endswith('.use_newer')):
                raise ValueError('Side-write path shape differs')
            hit = bool(int(record['bits'], 16) & (1 << (record['width'] - point['raw_index'] - 1)))
            rows.append(dict(scope=scope, metric_checksum=record['checksum'], point=point,
                hit=hit, decision='RETAIN_HIT' if hit else 'HOLD_NATIVE_PATH_SEMANTICS_REQUIRED'))
            counts['bank%d_%s' % (bank, 'hit' if hit else 'unhit')] += 1
    for path, expected in pins.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Input changed during inventory')
    with args.output.open('x') as stream:
        json.dump(dict(status='QBS_SIDE_PATH_INVENTORY_NOT_EXCLUSIONS', input_sha256=pins,
            native_qualified=False, waivers_applied=False, counts=dict(counts), points=rows), stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(counts)))


if __name__ == '__main__':
    main()
