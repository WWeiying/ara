#!/usr/bin/env python3
"""Offline failure reconstruction, not an acceptance checker or simulator runner."""
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
SEALED = OWNER / 'vcs_candidate05_plan01'
RUN = SEALED / 'prepared02'
CASE = 'd32m2_i64_fault_ov1'
ART = RUN / 'pilot/tests' / CASE
REF = OWNER / 'reference03' / CASE
sys.path.insert(0, str(SEALED))
from checker import memory_access, instructions, FIELDS


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def main():
    s = json.loads((REF / 'soc.symbols.json').read_text())
    ops = instructions((REF / 'soc.dis').read_text())
    regs = {i: 0 for i in range(32)}
    mem = {}
    traps, targets, checks, diagnostics, reloads, helpers, checkpoints = [], [], [], [], [], [], []
    pending = {}
    cap = None
    csr_names = {0x342: 'mcause', 0x341: 'mepc', 0x343: 'mtval', 8: 'vstart',
                 0xc20: 'vl', 0xc21: 'vtype', 3: 'fcsr', 15: 'vcsr'}
    order = -1
    def read(a, n=8):
        if not all(a + i in mem for i in range(n)):
            return None
        return int.from_bytes(bytes(mem[a + i] for i in range(n)), 'little')
    def named(name): return read(s[name])
    with (ART / 'commit_trace.csv').open() as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == FIELDS
        for lineno, row in enumerate(reader, 2):
            cycle = int(row['cycle'])
            op, pc = int(row['insn'], 16), int(row['pc'], 16)
            if row['event'] == 'cvx_req':
                tid = int(row['trans_id'])
                assert tid not in pending
                entry = dict(cycle=cycle, csv_line=lineno, trans_id=tid, opcode=f'{op:08x}')
                pending[tid] = entry
                if op == 0x0645f207:
                    entry['attempt'] = len(targets)
                    targets.append(entry)
                if op == 0x02057207:
                    reloads.append(dict(entry))
            if row['event'] == 'cvx_resp':
                entry = pending.pop(int(row['trans_id']))
                entry.update(response_cycle=cycle, response_csv_line=lineno, exception=int(row['trap']))
            if row['event'] != 'retire': continue
            assert int(row['order']) == order + 1
            order += 1
            assert ops[pc] == op
            rd, value = int(row['rd']), int(row['rd_wdata'], 16)
            if pc == s['gather32']:
                helpers.append(dict(cycle=cycle, csv_line=lineno,
                    args=[hex(regs[i]) for i in range(10, 14)],
                    indices=[read(s['indices'] + i * 8) for i in range(32)]))
            if pc == s['io_handler']:
                cap = dict(handler_cycle=cycle, handler_csv_line=lineno, csr={}, csr_reads=[], records=[],
                           pte_writes=[], check_calls=[], syscall_number=regs[17], mret=None)
                traps.append(cap)
            if cap and s['io_trap'] <= pc < s['main'] and op & 127 == 0x73:
                f, rs, csr = (op >> 12) & 7, (op >> 15) & 31, op >> 20
                if rd and f in (2, 3) and rs == 0 and csr in csr_names:
                    cap['csr'][csr_names[csr]] = value
                    cap['csr_reads'].append(dict(name=csr_names[csr], cycle=cycle, csv_line=lineno,
                                                 pc=hex(pc), value=hex(value)))
            if pc == s['check']:
                check = dict(cycle=cycle, csv_line=lineno, ordinal=len(checks) + 1,
                    io_checks_before=named('io_checks'), io_round=named('io_round'),
                    got=hex(regs[10]), want=hex(regs[11]), equal=regs[10] == regs[11], return_pc=hex(regs[1]))
                checks.append(check)
                if cap: cap['check_calls'].append(check)
            if pc == s['replay_mismatch']:
                diagnostics.append(dict(cycle=cycle, csv_line=lineno, pc=hex(pc),
                    trial=regs[10], index=regs[11], expected=hex(regs[12]), actual=hex(regs[13])))
            if pc == s['io_repair_sfence'] and cap:
                cap['sfence'] = dict(cycle=cycle, csv_line=lineno, va=hex(regs[(op >> 15) & 31]))
            if pc == s['io_retry_mret'] and cap:
                cap['mret'] = dict(cycle=cycle, csv_line=lineno)
                cap = None
            if pc == s['io_checkpoint']:
                checkpoints.append(dict(cycle=cycle, csv_line=lineno, round=named('io_round')))
            if not int(row['trap']):
                write = memory_access(row, regs, True)
                if write:
                    a, v, width = write
                    if cap and s['io_records'] <= a < s['io_records'] + 50 * 32 * 56:
                        cap['records'].append(dict(cycle=cycle, csv_line=lineno, address=hex(a), value=hex(v), width=width))
                    if cap and s['io_pt'] + 8192 <= a < s['io_pt'] + 12288:
                        cap['pte_writes'].append(dict(cycle=cycle, csv_line=lineno, address=hex(a), value=hex(v), width=width))
                    for i in range(width): mem[a + i] = (v >> (8 * i)) & 255
                if rd: regs[rd] = value
    faults = [t for t in traps if t['csr'].get('mcause') == 13]
    for n, fault in enumerate(faults):
        wanted = dict(mcause=13, mepc=s['overlap'], mtval=0x40000000 + ((n * 13 + 7) % 32) * 4096,
                      vstart=n, vl=32, vtype=17, fcsr=117, vcsr=5)
        fault.update(attempt=n, expected={k: hex(v) for k, v in wanted.items()},
                     mismatch_fields=[k for k, v in wanted.items() if fault['csr'].get(k) != v])
    console = (ART / 'console.log').read_text()
    capture, replay = [], []
    for lineno, line in enumerate(console.splitlines(), 1):
        match = re.search(r'\[ARA_SOURCE_(CAPTURE|REPLAY)\].* t=(\d+) lane=(\d+).* idx=(\d+)(?:/(\d+))? data=([0-9a-f]+)', line)
        if not match: continue
        kind, tick, lane, idx, last, data = match.groups()
        element = 4 * int(idx) + int(lane)
        entry = dict(console_line=lineno, reported_time=int(tick), lane=int(lane), word=int(idx),
                     global_element=element, data=hex(int(data, 16)), expected_offset=hex(((element * 13 + 7) % 32) * 4096),
                     matches_original=int(data, 16) == ((element * 13 + 7) % 32) * 4096)
        (capture if kind == 'CAPTURE' else replay).append(entry)
    ledger = dict(status='MEASURED_FIRMWARE_FAIL_NOT_CHECKER_FAILURE', case=CASE,
        raw_complete=json.loads((RUN / 'complete.json').read_text()), fault_handlers=faults,
        syscall_handlers=[t for t in traps if t['csr'].get('mcause') != 13],
        target_requests=targets, index_reload_requests=reloads, helpers=helpers, checks=checks,
        first_failed_check=next((c for c in checks if not c['equal']), None), diagnostics=diagnostics,
        checkpoints=checkpoints, final_observed_cycle=cycle, retired=order + 1,
        capture=capture, replay=replay,
        complete_initial_capture=len(capture) == 32 and all(c['matches_original'] for c in capture),
        state={k: named(k) for k in ('io_errors', 'io_checks', 'io_round', 'io_minor', 'io_maps', 'io_unmaps', 'io_target_pc')},
        controls_directory_exists=(RUN / 'controls').exists(),
        observer_file_exists=(ART / 'indexed_analysis.json').exists(),
        closed_window_marker_in_console='INDEXED_PROFILE_CLOSED_AT_1000000NS' in console,
        note='Diagnostic failure reconstruction only. No acceptance, DUT launch or frozen-file edits.')
    files = [Path(__file__), SEALED / 'checker.py', RUN / 'complete.json', RUN / 'plan.json',
             RUN / 'pilot/run.json', RUN / 'pilot/summary.json', REF / 'soc.symbols.json', REF / 'soc.dis',
             OWNER / 'reference03/fixture.c', OWNER / 'reference03/original.c', OWNER / 'reference03/runtime.c']
    files += [ART / f for f in ('input.elf', 'inputs.json', 'command.json', 'console.log', 'commit_trace.csv',
                               'work/run.vcs.log', 'work/indexed_first_round.fsdb', 'work/ucli.key')]
    ledger['evidence_pins'] = {str(p): sha(p) for p in files}
    save(HERE / 'ledger.json', ledger)
    print(json.dumps(dict(faults=len(faults), target_requests=len(targets), reloads=len(reloads),
          first_failed_check=ledger['first_failed_check'], diagnostics=diagnostics,
          fault_mismatches=[dict(attempt=f['attempt'], fields=f['mismatch_fields']) for f in faults if f['mismatch_fields']],
          captured=len(capture), replayed=len(replay), original_capture_ok=ledger['complete_initial_capture'],
          last_cycle=cycle, retired=order + 1), indent=2))


if __name__ == '__main__':
    main()
