"""Parse passive ROI observations; no inference from busy to useful utilization."""
from pathlib import Path
import re


def fields(text):
    result = {}
    for name, value in re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)', text):
        if name in result:
            raise ValueError('Duplicate monitor key ' + name)
        result[name] = int(value) if re.fullmatch(r'\d+',value) else value
    return result


def parse(work):
    work = Path(work)
    totals, phases = [], []
    for path in sorted(work.glob('llm_perf_report_*.log')):
        for line in path.read_text().splitlines():
            if not line.startswith('[LLM_PERF] '):
                raise ValueError('Unexpected LLM monitor record')
            value = fields(line)
            if value['phase'] == 'total':
                if value['nr_lanes'] != 4 or value['cycles'] <= 0 or \
                    value['retired_vector_inst_count'] > value['retired_inst_count'] or \
                    value['axi_r_bus_bytes'] != value['axi_r_beat_count']*16:
                    raise ValueError('LLM monitor geometry/count invariant')
                totals.append(value)
            else:
                phases.append(value)
    lanes = {i:[] for i in range(4)}
    for line in (work/'run.vcs.log').read_text(errors='strict').splitlines():
        if not line.startswith('OPERATOR_UNIT '):
            continue
        match = re.search(r'gen_lanes\[(\d+)\]', line)
        if not match or int(match[1]) not in lanes:
            raise ValueError('Unknown lane identity')
        values = fields(line)
        if any(not isinstance(v,int) for v in values.values()):
            raise ValueError('Unknown/non-numeric unit activity')
        lanes[int(match[1])].append(values)
    counts = {len(v) for v in lanes.values()}
    if len(counts) != 1:
        raise ValueError('Incomplete four-lane ROI')
    unit = []
    for i in range(len(lanes[0])):
        if len({lanes[lane][i]['cycles'] for lane in lanes}) != 1:
            raise ValueError('Four-lane ROI cycle mismatch')
        row = {key:sum(lanes[lane][i][key] for lane in lanes) for key in lanes[0][i]}
        row['cycles'] = lanes[0][i]['cycles']
        # Accepted lane requests/cycle, not fraction of pipeline stages occupied.
        row['fpu_accepted_lane_requests_per_cycle'] = (
            row['native_requests']+row['qk_requests']+row['pv_requests'])/row['cycles']
        unit.append(row)
    if unit and len(unit) != len(totals):
        raise ValueError('Unit and total ROI counts differ')
    return dict(total_roi=totals, phase_roi=phases, four_lane_unit_roi=unit,
        semantics='Native FP fires exclude Resident; private QK/PV accepted work is counted separately. '
                  'Request rates are not pipeline-occupancy or peak MAC utilization. '
                  'AXI bus bytes are shared vector-port returned beats, not logical payload or full DDR traffic.')
