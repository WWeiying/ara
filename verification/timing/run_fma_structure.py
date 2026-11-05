#!/usr/bin/env python3
"""Read existing FMA DDC; report mapped cones without resynthesis or RTL edits."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import run_operand_ext as api


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f, delimiter='\t'))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--ppa', type=Path, required=True)
    a = p.parse_args()
    source = a.ppa.resolve()
    if api.read(source/'report.json')['state'] != 'MEASURED':
        raise ValueError('Completed paired measurement required')
    api.verify(source)
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__), out/'worker.py')
    shutil.copy2(api.HERE/'report_fma_structure.tcl', out/'report.tcl')
    inputs = [source/'shared/mapped.ddc', source/'shared/library_env.tcl',
              source/'report.json', out/'worker.py', out/'report.tcl', Path(api.__file__)]
    pins = {str(f): api.sha(f) for f in inputs}
    pins.update(api.read(source/'library-pins.json'))
    api.save(out/'source-pins.json', pins)
    api.save(out/'status.json', dict(state='REPORTING'))
    try:
        api.verify(out)
        cmd = ['docker', 'exec', '-u', f'{os.getuid()}:{os.getgid()}',
               '-e', f'HOME={Path.home()}', '-e', f'FMA_INPUT={source}/shared',
               '-w', str(out), 'synopsys_workspace', 'bash', '-lc',
               'exec timeout --signal=TERM --kill-after=30s 600 dc_shell -f report.tcl']
        api.command(cmd, out, out/'dc.log', 'FMA_STRUCTURE_REPORT_COMPLETE', seconds=660)
        cells = {r['name']: r for r in rows(out/'cells.tsv')}
        def area(names):
            return sum(float(cells[n]['area_um2']) for n in names)
        total = area(cells)
        expected = api.read(source/'report.json')['metrics']['shared']['area_um2']
        if abs(total - expected) > 0.02:
            raise ValueError(f'Leaf area does not reconcile: {total} != {expected}')
        cones = {}
        for r in rows(out/'cones.tsv'):
            key = (int(r['lane']), r['boundary'])
            if int(r['driver_pins']):
                names = {c['name'] for c in rows(out/r['file'])}
                if not names <= cells.keys():
                    raise ValueError('Unknown cone cells')
                cones[key] = {n for n in names if cells[n]['sequential'] == 'false'}
        by_lane = []
        for lane in range(4):
            prefix = f'i_addmul/gen_lane[{lane}].i_fma/'
            local = {n for n in cells if n.startswith(prefix)}
            seq = {n for n in local if cells[n]['sequential'] == 'true'}
            data = dict(lane=lane, total_area=area(local), sequential_area=area(seq))
            for boundary in ('product', 'addend_shifted', 'sum_raw', 'sum_shifted', 'mid_sum_input'):
                cone = cones.get((lane, boundary))
                data[boundary+'_cone_area'] = area(cone) if cone is not None else None
            product = cones.get((lane, 'product'))
            left = cones.get((lane, 'mantissa_a'))
            right = cones.get((lane, 'mantissa_b'))
            if product is not None and left is not None and right is not None:
                data['product_incremental_cone_area'] = area(product - left - right)
            else:
                data['product_incremental_cone_area'] = None
            groups = {}
            for name in seq:
                tail = name[len(prefix):]
                group = ('clock_gating' if '/clk_gate_' in name else
                         'input_pipeline' if tail.startswith('inp_pipe_') else
                         'middle_pipeline' if tail.startswith('mid_pipe_') else
                         'output_pipeline' if tail.startswith('out_pipe_') else 'other')
                groups.setdefault(group, set()).add(name)
            data['sequential_groups'] = {g: dict(cells=len(ns), area=area(ns)) for g, ns in groups.items()}
            by_lane.append(data)
        api.verify(out)
        api.save(out/'report.json', dict(state='REPORTED', area_um2=total, lanes=by_lane,
            note='Named combinational fanin cones can overlap; not an additive operator breakdown. '
                 'Incremental product cone subtracts operand fanin. Missing nets remain unknown.'))
        api.save(out/'status.json', dict(state='REPORTED'))
    except Exception as exc:
        api.save(out/'status.json', dict(state='FAIL', reason=str(exc)))
        raise


if __name__ == '__main__':
    main()
