"""Read-only cycle table from the single build03 restart diagnostic capture."""
import csv
import json
from pathlib import Path
import subprocess
from types import FunctionType

import audit_gap115_axi_v2 as wave
from run_masklogical_restart_count_probe import OUT, digest

ROOT = 'ara_tb.dut.i_ara_soc.i_system.i_ara'
MONITOR = 'ara_tb.dut.i_ara_soc.i_system.i_ara_commit_monitor.cycle_q'
CONVERTER = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/linux64/bin/vpd2vcd.exe')


def main():
    status = json.loads((OUT / 'status.json').read_text())
    # UCLI echoes the Tcl source: an error marker inside that echo is not an
    # executed error. Keep the sealed runner receipt, qualify actual whole lines.
    lines = (OUT / 'console.log').read_text().splitlines()
    markers = ('MASKLOGICAL_RESTART_PREFLIGHT_READY',
               'MASKLOGICAL_RESTART_BEGIN cycle_q=250530',
               'MASKLOGICAL_RESTART_END cycle_q=250750',
               'MASKLOGICAL_RESTART_CAPTURE_COMPLETE_NOT_ARCHITECTURAL_PASS')
    if not all(lines.count(marker) == 1 for marker in markers):
        raise ValueError('Missing/duplicate executed capture markers')
    if any(line.startswith(('MASKLOGICAL_RESTART_ERROR ', 'Error-', 'UCLI_ERROR')) for line in lines):
        raise ValueError('Actual capture error')
    if not any('V C S   S i m u l a t i o n   R e p o r t' in line for line in lines):
        raise ValueError('Missing simulator terminal report')
    report = OUT / 'decoded'
    report.mkdir(exist_ok=False)
    vpd = OUT / 'masklogical-restart.vpd'
    if 'wave_sha256' in status and digest(vpd) != status['wave_sha256']:
        raise ValueError('Closed waveform hash changed')
    vcd = report / 'restart.vcd'
    with (report / 'conversion.log').open('x') as log:
        subprocess.run([str(CONVERTER), '+splitpacked', str(vpd), str(vcd)],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    parser = FunctionType(wave.vcd.__code__, dict(wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1}))
    events = iter(parser(vcd))
    _, declarations = next(events)
    (report / 'declarations.json').write_text(json.dumps(declarations, indent=2) + '\n')

    def val(state, path):
        if path not in declarations:
            raise ValueError('Missing field: ' + path)
        bits = state.get(declarations[path]['code'], 'x')
        return int(bits, 2) if set(bits) <= set('01') else bits

    def m(state, name):
        return val(state, ROOT + '.i_masku.' + name)

    rows, requests, transfers, writes = [], [], [], []
    for stamp, before, after in events:
        if val(before, 'ara_tb.clk') != 0 or val(after, 'ara_tb.clk') != 1:
            continue
        cycle = val(before, MONITOR)
        row = {'cycle': cycle, 'time_100fs': stamp}
        for name in ('vinsn_issue_valid', 'vinsn_issue.id', 'vinsn_issue.op',
                     'vinsn_issue.vl', 'vinsn_issue.vstart', 'issue_cnt_q',
                     'processing_cnt_q', 'commit_cnt_q', 'read_cnt_q', 'iteration_cnt_q',
                     'masku_operand_alu_valid', 'masku_operand_alu_ready',
                     'masku_operand_m_valid', 'masku_operand_m_ready',
                     'masku_operand_vd_valid', 'masku_operand_vd_ready',
                     'masku_result_req_o', 'masku_result_gnt_i', 'pe_resp_o.vinsn_done'):
            row[name] = m(before, name)
        target = (row['vinsn_issue_valid'] == 1 and row['vinsn_issue.vl'] == 1024 and
                  row['vinsn_issue.vstart'] == 257)
        for lane in range(4):
            base = ROOT + f'.gen_lanes[{lane}].i_lane'
            seq = base + '.i_lane_sequencer.'
            requester = base + '.i_operand_requester.'
            valid, ready = (val(before, seq+n) for n in ('operand_request_valid_o', 'operand_request_ready_i'))
            for q, label in ((1, 'AluB'), (5, 'MaskB'), (6, 'MaskM')):
                prefix = f'lane{lane}.{label}.'
                payload = {name: val(before, seq+f'operand_request_o[{q}].'+name)
                           for name in ('id', 'vs', 'vstart', 'vl', 'eew')}
                row.update({prefix+name: value for name, value in payload.items()})
                for name in ('addr', 'len'):
                    row[prefix+'requester_'+name] = val(before, requester+f'requester_metadata_q[{q}].'+name)
                row[prefix+'valid'] = (valid >> q) & 1 if isinstance(valid, int) else valid
                row[prefix+'ready'] = (ready >> q) & 1 if isinstance(ready, int) else ready
                if row[prefix+'valid'] == row[prefix+'ready'] == 1:
                    requests.append(dict(cycle=cycle, lane=lane, queue=label, **payload))
            row[f'lane{lane}.valu_issue_cnt'] = val(before, base+'.i_vfus.i_valu.issue_cnt_q')
            if target:
                for label in ('alu', 'm', 'vd'):
                    v = row[f'masku_operand_{label}_valid']
                    r = row[f'masku_operand_{label}_ready']
                    if isinstance(v, int) and isinstance(r, int) and (v & r) & (1 << lane):
                        transfers.append(dict(cycle=cycle, lane=lane, source=label))
            req, gnt = row['masku_result_req_o'], row['masku_result_gnt_i']
            if isinstance(req, int) and isinstance(gnt, int) and (req & gnt) & (1 << lane):
                # Packed output address array is split by the pinned converter.
                writes.append(dict(cycle=cycle, lane=lane,
                                   addr=m(before, f'masku_result_addr_o[{lane}]')))
        rows.append(row)
    if not rows:
        raise ValueError('No sampled clock edges')
    with (report / 'cycles.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = dict(status='DECODED_DIAGNOSTIC_NOT_ARCHITECTURAL_PASS', sampled_cycles=len(rows),
                   original_wrapper_status=status, executed_markers=list(markers),
                   first_cycle=rows[0]['cycle'], last_cycle=rows[-1]['cycle'],
                   requests=requests, operand_handshakes=transfers, result_handshakes=writes,
                   final_state=rows[-1], pins={str(p): digest(p) for p in
                     (vpd, vcd, CONVERTER, Path(__file__), Path(wave.__file__), OUT / 'status.json')})
    (report / 'receipt.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('pins', 'final_state')}))


if __name__ == '__main__':
    main()
