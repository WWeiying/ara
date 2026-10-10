"""One-shot read-only R2 failure diagnosis; no coverage collection or admission."""
import json
import re
from pathlib import Path

import collect_memory_emul_r2_strict as frozen


def main():
    p, life, common = frozen.p, frozen.life, frozen.common
    out = life.OUT / 'memory-emul-r2-parent-failure-diagnosis-20261006-01.json'
    frozen.require(not out.exists(), 'Fresh diagnosis required')
    run = frozen.RUN
    pre = life.read_bound(frozen.runner.PRE / 'preflight-manifest.json', frozen.PRE_SEAL)
    s = pre['symbols']
    paths = [Path(__file__).resolve(), p.APP,
             life.ROOT / 'verification/tests/memory_emul_r2_reference.h',
             life.OUT / 'old-image-source-evidence-20261006-01/ara_dispatcher.sv',
             frozen.runner.PRE / 'preflight-manifest.json', frozen.runner.PRE / 'spike.trace',
             life.OUT / 'memory-emul-r2-parent-strict-candidate-722-20261006-01/failure.json']
    paths += [run / n for n in ('simulation-status.json', 'manifest.json', 'console.log',
                               'run.vcs.log', 'commit_trace.csv', 'vector_trace.csv', 'trace_hart_0.log')]
    pins = {str(path): life.digest(path) for path in paths}
    rows = common.read_csv((run / 'commit_trace.csv').read_bytes(), common.COMMIT_FIELDS)
    retired = [r for r in rows if r['event'] == 'retire']
    memory, bad_retires = {}, []
    for r in retired:
        pc, insn, addr = (int(r[k], 16) for k in ('pc', 'insn', 'mem_addr'))
        if pc in {s['gmr_bad_%02d' % n] for n in range(3)}:
            bad_retires.append(dict(pc=hex(pc), instruction=hex(insn), cycle=int(r['cycle'])))
        access = common.scalar_memory(insn)
        if access:
            kind, width = access
            value = int(r['mem_wdata' if kind == 'write' else 'rd_wdata'], 16)
            if kind == 'write' or int(r['rd']):
                memory.update({addr+i: (value >> (8*i)) & 255 for i in range(width)})

    def read(name, offset=0, width=8):
        a = s[name]+offset
        if not all(a+i in memory for i in range(width)):
            return None
        return int.from_bytes(bytes(memory[a+i] for i in range(width)), 'little')

    actual = {name: [read(name, i*8) for i in range(count)] for name, count in
              [('gmr_cfg', 9), ('gmr_legal', 9), ('gmr_ledger', 36), ('gmr_post', 27),
               ('gmr_restore', 12)]}
    actual.update(checks=read('g75_result', width=4), failed_checks=read('num_failed', width=4),
                  result_failed_checks=read('g75_result', 4, 4), traps=read('gmr_traps'),
                  tohost=read('tohost'))
    mismatches = []
    for phase in range(7):
        for reg in range(32):
            expected = b'\xa5'*8 + p.expected_register(reg, phase) + b'\xa5'*8
            for i, byte in enumerate(expected):
                addr = s['gmr_dump']+(phase*32+reg)*144+i
                if memory.get(addr) != byte:
                    mismatches.append(dict(phase=phase, reg=reg, byte=i,
                                           expected=byte, actual=memory.get(addr)))
    scalar = common.spike_trace.compare_commit_prefix(
        frozen.runner.PRE/'spike.trace', run/'commit_trace.csv', 0x80000000,
        terminal_tohost_address=0x80001000, rvfi_store_data_layout='unshifted')
    text = (run/'trace_hart_0.log').read_text()
    traps = re.findall(r'Exception @([^,]+), PC: ([0-9a-fA-F]+), Cause: ([^,]+),\s*\n\s*tval: ([0-9a-fA-F]+)', text)
    report = dict(status='R2_ACTUAL_FAIL_DIAGNOSIS_NOT_ADMITTED', pins=pins,
                  provenance='INDEPENDENT_OFFLINE_ACTUAL_TRACE_ANALYSIS',
                  diagnostic_baseline=722, future_admission_baseline=723,
                  strict_failure=json.loads(paths[6].read_text())['reason'],
                  actual_signatures=actual, actual_bad_pc_retires=bad_retires,
                  actual_traps=traps, expected_trap_pcs=[hex(s['gmr_bad_%02d'%n]) for n in range(3)],
                  scalar_comparison=scalar, full_snapshot_mismatch_bytes=len(mismatches),
                  first_snapshot_mismatches=mismatches[:32],
                  source_chain=dict(vtype_normalization=[1698,1703,1704],
                                    load_decode=[4130,4350], store_decode=[4380,4610],
                                    zero_length_noop=[5909,5912,5919]),
                  root_cause_hypothesis='Frozen dispatcher ordinary memory decode omits VILL rejection; VILL normalization sets VL0, then zero-length acknowledgement retires the two instructions without illegal traps.',
                  oracle_assessment='Both independent Spike and frozen software expect illegal traps for ordinary vtype-dependent VILL memory instructions. Two missing traps explain zero ledgers and shifted trap ordinal. No oracle relaxation justified.',
                  limitations='Static source plus architectural trace, not cycle-level internal VILL/exception waveform proof; no claim of upper coverage qualification or native identity.',
                  discriminating_signals=['csr_vtype_q.vill', 'csr_vl_q', 'is_vload', 'is_vstore',
                                          'illegal_insn_load', 'illegal_insn_store',
                                          'acc_resp_o.exception.valid', 'load_zero_vl',
                                          'store_zero_vl', 'ara_req_valid'],
                  coverage_admitted=False, simulations_started=False, rtl_changed=False)
    life.check(pins)
    life.save(out, report)
    print(json.dumps(dict(report=str(out), seal=life.digest(out), pins=len(pins),
                          actual=actual, snapshot_mismatches=len(mismatches))))


if __name__ == '__main__':
    main()
