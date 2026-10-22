#!/usr/bin/env python3
"""Read the one closed batch; preserve its TB ERROR, never rerun a simulator."""
import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / 'successor01/measurement01'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    out = HERE / 'closed_audit01'
    out.mkdir(exist_ok=False)
    result = dict(status='NOT_ACCEPTED', original_batch_status='ERROR', simulation_rerun=False)
    try:
        pins = json.loads((RUN / 'input_pins.json').read_text())
        pins.update({str(RUN / 'frozen' / p): h for p, h in
                     json.loads((RUN / 'frozen_pins.json').read_text()).items()})
        evidence = ('cycles.csv', 'run.log', 'result.json', 'child.json', 'process_exit.json',
                    'input_pins.json', 'frozen_pins.json', 'compile_command.json', 'run_command.json')
        pins.update({str(RUN / p): sha(RUN / p) for p in evidence})
        pins[str(Path(__file__).resolve())] = sha(Path(__file__).resolve())
        assert all(sha(Path(p)) == h for p, h in pins.items()), 'Pre-pin mismatch'
        metadata = json.loads((RUN / 'result.json').read_text())
        assert metadata['state'] == 'ERROR' and metadata['compile_returncode'] == 0
        assert metadata['run_returncode'] == 0 and metadata['error'] == "AssertionError('Batch not complete')"
        assert json.loads((RUN / 'process_exit.json').read_text())['returncode'] == 0
        log = (RUN / 'run.log').read_text()
        assert log.count('Fatal:') == 1 and 'INCOMPLETE_HANDSHAKES accepted=1 resp=1 ack=1 AR=2 R=2 pop=2' in log
        assert log.count('CONTROL_COMPLETED stride=8 AR=2 R=2 descpop=2 bytes=16 done_cycle=15 idle=1') == 1
        assert 'HYPOTHESIS_FALSIFIED' not in log
        tb = (RUN / 'frozen/probe_tb.sv').read_text()
        assert 'ars==2 && rs==2 && pops==2 && reads.size()==0 && addr_idle)' in tb
        ag = (RUN / 'frozen/hardware/src/vlsu/addrgen.sv').read_text()
        assert 'axi_addrgen_queue_empty && !idx_vaddr_valid_q &&\n                  !(|vinsn_running_q)' in ag
        with (RUN / 'cycles.csv').open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 502 and all(None not in r and all(v is not None for v in r.values()) for r in rows)
        summaries = []
        for case, stride in ((0, 8), (1, 4)):
            rr = [r for r in rows if int(r['case']) == case]
            assert [int(r['cycle']) for r in rr] == list(range(5, 256))
            bycycle = {int(r['cycle']): r for r in rr}
            handshakes = lambda a, b: [r for r in rr if r[a] == r[b] == '1']
            ars = handshakes('ar_valid', 'ar_ready')
            reads = handshakes('r_valid', 'r_ready')
            pops = handshakes('desc_valid', 'desc_pop')
            assert len(ars) == len(reads) == len(pops) == 2
            assert [int(r['cycle']) for r in ars] == [9, 10]
            assert [int(r['cycle']) for r in reads] == [11, 12]
            assert [int(r['cycle']) for r in pops] == [11, 12]
            assert [int(r['ar_addr'], 16) for r in ars] == [0x80010000, 0x80010000+stride]
            assert [int(r['desc_addr'], 16) for r in pops] == [0x80010000, 0x80010000+stride]
            assert all(r['ar_len'] == '0' and r['ar_size'] == '3' for r in ars)
            assert all(r['desc_len'] == '0' and r['desc_size'] == '3' and
                       r['desc_exception'] == r['desc_skip'] == '0' for r in pops)
            assert all(r['r_last'] == '1' for r in reads)
            assert [int(r['cycle']) for r in rr if r['desc_push'] == '1'] == [9, 10]
            assert [int(r['cycle']) for r in rr if r['ack'] == '1'] == [10]
            assert [int(r['cycle']) for r in rr if r['response'] == '1'] == [10]
            assert all(r['exception'] == r['early_ld'] == r['early_st'] == '0' for r in rr)
            request = bycycle[7]
            assert request['broadcast'] == request['ld_ready'] == request['vm'] == '1'
            assert request['vl'] == '2' and request['vstart'] == '0' and int(request['pe_stride']) == stride
            pattern = lambda a: (0xa6 ^ ((a & 255)*37)) & 255
            bytes_per_r = []
            for a, r in zip(ars, reads):
                addr = int(a['ar_addr'], 16)
                lower = addr % 16
                upper = (addr & ~7) + 7 - (addr & ~15)
                bytes_per_r.append(upper-lower+1)
                expected = sum(pattern((addr & ~15)+b) << (8*b) for b in range(16))
                assert int(r['r_data'], 16) == expected, 'AXI data not backing-memory pattern'
            assert bytes_per_r == ([8, 8] if case == 0 else [8, 4])
            pending = {}
            written = {}
            for r in rr:
                grants = int(r['final_gnt'], 2)
                for lane in range(4):
                    if grants >> lane & 1:
                        addr, data, be = pending.pop(lane)
                        assert addr == 96
                        for b in range(8):
                            if be >> b & 1:
                                idx = lane*8+b
                                assert idx not in written and idx < 16
                                assert (data >> (b*8)) & 255 == pattern(0x80010000+idx)
                                written[idx] = (data >> (b*8)) & 255
                accepts = int(r['result_req'], 2) & int(r['result_gnt'], 2)
                for lane in range(4):
                    if accepts >> lane & 1:
                        assert lane not in pending
                        pending[lane] = ((int(r['result_addr'], 16) >> (16*lane)) & 65535,
                                         (int(r['result_data'], 16) >> (64*lane)) & ((1 << 64)-1),
                                         (int(r['result_be'], 16) >> (8*lane)) & 255)
            assert not pending
            assert sorted(written) == (list(range(16)) if case == 0 else [])
            assert bycycle[12]['vrf_count'] == bycycle[12]['vrf_ptr'] == '8'
            if case == 0:
                assert [int(r['cycle']) for r in rr if int(r['done'], 2)] == [15]
                assert [int(r['cycle']) for r in rr if r['load_complete'] == '1'] == [14]
                assert all(r['global_idle'] == '1' for r in rr if int(r['cycle']) >= 16)
                assert all(r['issue_bytes'] == r['commit_bytes'] == '0' for r in rr if int(r['cycle']) >= 15)
            else:
                assert all(int(r['done'], 2) == 0 and r['load_complete'] == '0' for r in rr)
                for r in rr:
                    if int(r['cycle']) >= 13:
                        assert r['vrf_count'] == r['vrf_ptr'] == '12'
                        assert r['issue_bytes'] == r['commit_bytes'] == '16'
                        assert r['global_idle'] == r['ld_idle'] == r['ag_idle'] == '0'
                        assert r['ag_axi_state'] == r['r_ptr'] == '0'
                        assert r['ar_valid'] == r['r_valid'] == r['desc_valid'] == r['desc_push'] == '0'
                        assert int(r['result_req'], 2) == int(r['final_gnt'], 2) == 0
            summaries.append(dict(case=case, stride=stride, rows=len(rr), ar_cycles=[9, 10],
                                  r_and_pop_cycles=[11, 12], r_valid_bytes=bytes_per_r,
                                  written_bytes=len(written), final=rr[-1]))
        assert all(sha(Path(p)) == h for p, h in pins.items()), 'Post-pin mismatch'
        result.update(status='CLOSED_CYCLE_EVIDENCE_ACCEPTED_P1_REPRODUCED_NOT_ARCH_PASS',
                      csv_rows=len(rows), cases=summaries, pins_checked=len(pins), pins_unchanged=True,
                      simulator_numeric_returncode=0, simulator_fatal=True,
                      harness_failure='Terminal addr_idle requirement wrongly applied to deliberately stuck case; real idle includes instruction-running state.',
                      original_metadata_unchanged=True, csv_sha256=sha(RUN / 'cycles.csv'))
        with (out / 'pins.json').open('x') as f:
            json.dump(pins, f, indent=2)
    except Exception as e:
        result['error'] = repr(e)
    with (out / 'result.json').open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps(result, indent=2))
    return int(result['status'] != 'CLOSED_CYCLE_EVIDENCE_ACCEPTED_P1_REPRODUCED_NOT_ARCH_PASS')


if __name__ == '__main__':
    raise SystemExit(main())
