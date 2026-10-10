"""Qualify only the closed build04 restart window, not the running full matrix."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
from types import FunctionType

import decode_masklogical_restart_count_probe as old
import run_masklogical_same_source_repair as oracle

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'verification/out/masklogical-same-source-repair-agent-20261008-02'
OUT = ROOT / 'verification/out/masklogical-restart-build04-offline-20261008-01'


def main():
    need, sha = oracle.require, oracle.digest
    wave = RUN / 'masklogical-restart.vpd'
    before_hash = sha(wave)
    lines = (RUN / 'console.log').read_text().splitlines()
    markers = ('MASKLOGICAL_RESTART_BEGIN cycle_q=250530',
               'MASKLOGICAL_RESTART_END cycle_q=250750',
               'MASKLOGICAL_RESTART_CAPTURE_COMPLETE_CONTINUING_FULL_MATRIX')
    need(all(lines.count(m) == 1 for m in markers), 'Actual closed-window markers missing/duplicate')
    prefix = lines[:lines.index(markers[-1])+1]
    need(not any(l.startswith(('MASKLOGICAL_PROBE_REJECT ', 'Error-', 'UCLI_ERROR')) for l in prefix),
         'Actual error before waveform closure')
    OUT.mkdir(exist_ok=False)
    (OUT / 'console-through-close.log').write_text('\n'.join(prefix) + '\n')
    for name in ('started.json', 'command.json', 'source-pins.json', 'probe.tcl'):
        shutil.copyfile(RUN / name, OUT / name)
    shutil.copyfile(wave, OUT / 'restart.vpd')
    need(sha(OUT / 'restart.vpd') == before_hash == sha(wave), 'Closed wave changed during snapshot')
    with (OUT / 'conversion.log').open('x') as log:
        subprocess.run([str(old.CONVERTER), '+splitpacked', str(OUT / 'restart.vpd'), str(OUT / 'restart.vcd')],
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    parse = FunctionType(old.wave.vcd.__code__, dict(old.wave.vcd.__globals__, ROOT='ara_tb', WIDTHS={'clk': 1}))
    events = iter(parse(OUT / 'restart.vcd'))
    _, decl = next(events)
    def value(state, name):
        need(name in decl, 'Missing waveform field: ' + name)
        bits = state.get(decl[name]['code'], 'x')
        need(set(bits) <= set('01'), 'Unknown sampled field: ' + name)
        return int(bits, 2)
    rows, reqs, transfers, writes, done = [], [], [], [], []
    for stamp, before, after in events:
        # The first event initializes dump state and is not a sampled edge.
        clock = decl['ara_tb.clk']['code']
        if before.get(clock) != '0' or after.get(clock) != '1':
            continue
        cycle = value(before, old.MONITOR)
        base = old.ROOT + '.i_masku.'
        row = {'cycle': cycle}
        fields = ('issue_cnt_q', 'processing_cnt_q', 'commit_cnt_q', 'iteration_cnt_q',
                  'masku_operand_alu_valid', 'masku_operand_alu_ready',
                  'masku_operand_m_valid', 'masku_operand_m_ready',
                  'masku_operand_vd_valid', 'masku_operand_vd_ready',
                  'pe_resp_o.vinsn_done')
        row.update({n: value(before, base+n) for n in fields})
        target = (value(before, base+'vinsn_issue_valid') and
                  value(before, base+'vinsn_issue.vl') == 1024 and
                  value(before, base+'vinsn_issue.vstart') == 257)
        for lane in range(4):
            seq = old.ROOT + f'.gen_lanes[{lane}].i_lane.i_lane_sequencer.'
            valid = value(before, seq+'operand_request_valid_o')
            ready = value(before, seq+'operand_request_ready_i')
            for q, label in ((1, 'AluB'), (5, 'MaskB'), (6, 'MaskM')):
                if (valid & ready) & (1 << q):
                    reqs.append(dict(cycle=cycle, lane=lane, queue=label, **{
                        n: value(before, seq+f'operand_request_o[{q}].'+n)
                        for n in ('id', 'vs', 'vstart', 'vl')}))
            if target:
                for label in ('alu', 'm', 'vd'):
                    if (row[f'masku_operand_{label}_valid'] & row[f'masku_operand_{label}_ready']) & (1 << lane):
                        transfers.append(dict(cycle=cycle, lane=lane, source=label))
            if (value(before, base+'masku_result_req_o') & value(before, base+'masku_result_gnt_i')) & (1 << lane):
                writes.append(dict(cycle=cycle, lane=lane,
                                   addr=value(before, base+f'masku_result_addr_o[{lane}]')))
        if row['pe_resp_o.vinsn_done'] & 1:
            done.append(cycle)
        rows.append(row)
    need(len(reqs) == 12 and all(r['id'] == 0 and r['vstart'] == 0 and r['vl'] == 4 and
         r['vs'] == (16 if r['queue'] == 'MaskB' else 8) for r in reqs), 'Three aligned four-word requests missing')
    for lane in range(4):
        for label in ('alu', 'm', 'vd'):
            need(sum(t['lane'] == lane and t['source'] == label for t in transfers) == 4,
                 'Four aligned source handshakes missing')
        need([w['addr'] for w in writes if w['lane'] == lane] == [64, 65, 66, 67], 'Four result words missing')
    need(len(done) == 1, 'Expected one VID0 completion within window')
    # Snapshot a complete prefix, stopping before any concurrently appended row.
    with (RUN / 'vector_trace.csv').open() as src, (OUT / 'vector-prefix.csv').open('x') as dst:
        dst.write(next(src))
        for line in src:
            if not line.endswith('\n'):
                break
            if int(line.split(',', 1)[0]) > 250750:
                break
            dst.write(line)
    lanes, vlen, acts = oracle._parse_vector_trace(OUT / 'vector-prefix.csv')
    activity = acts[99]
    need((lanes, vlen) == (4, 1024) and activity.allocations == activity.completions == 1,
         'Native seq99 does not complete exactly once')
    need(activity.instruction == 0x6e842857 and activity.vstart == 257 and activity.vl == 1024,
         'Wrong native operation')
    actual = oracle._architectural_bytes(activity.writes, lanes, vlen)
    gold = oracle.expected(oracle.cases()[12])
    need(set(actual) == {(16, b) for b in range(128)} and
         all(actual[16, b][0] == gold[b] for b in range(128)), 'Restart/prestart VRF result mismatch')
    with (OUT / 'cycles.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    result = dict(status='RESTART_WINDOW_REPAIR_PASS_NOT_FULL_MATRIX', coverage_admitted=False,
                  full_68_pass=False, requests=reqs, operand_handshakes=transfers,
                  result_handshakes=writes, done_cycles=done,
                  native_seq99_complete=True, independent_vrf_bytes_checked=128,
                  old_request=dict(MaskM_start=1, MaskM_len=3), new_request=dict(MaskM_start=0, MaskM_len=4),
                  original_vpd_sha256=before_hash,
                  pins={str(p): sha(p) for p in (Path(__file__), Path(old.__file__), Path(oracle.__file__),
                                               Path(old.wave.__file__), old.CONVERTER)},
                  artifacts={str(p): sha(p) for p in OUT.iterdir() if p.is_file()})
    need(sha(wave) == before_hash, 'Source wave changed after decoding')
    (OUT / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
