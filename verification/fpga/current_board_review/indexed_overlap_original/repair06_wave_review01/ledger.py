#!/usr/bin/env python3
"""Bounded copied CSV/console reconstruction, not full-run acceptance."""
import csv
import json
import re
import sys
from acquire import HERE, OWNER, sha, save

sys.dont_write_bytecode = True
sys.path.insert(0, str(OWNER/'vcs_candidate05_plan01'))
from checker import memory_access, instructions, FIELDS

symbols = json.loads((OWNER/'reference03/d32m2_i64_fault_ov1/soc.symbols.json').read_text())
ops = instructions((OWNER/'reference03/d32m2_i64_fault_ov1/soc.dis').read_text())
regs, memory, pending = {i:0 for i in range(32)}, {}, {}
targets, traps, checks, helpers, reloads, allocs = [], [], [], [], [], []
current = None
csr_names = {0x342:'mcause', 0x341:'mepc', 0x343:'mtval', 8:'vstart', 0xc20:'vl', 0xc21:'vtype', 3:'fcsr', 15:'vcsr'}


def value_at(a):
    return int.from_bytes(bytes(memory[a+i] for i in range(8)), 'little') if all(a+i in memory for i in range(8)) else None


path = HERE/'inputs/commit_through_cycle600000.csv'
with path.open() as stream:
    reader = csv.DictReader(stream)
    assert reader.fieldnames == FIELDS
    retired = 0
    for line, row in enumerate(reader, 2):
        cycle, pc, insn = int(row['cycle']), int(row['pc'],16), int(row['insn'],16)
        event = row['event']
        if event == 'uop_alloc':
            allocs.append(dict(cycle=cycle, csv_line=line, order=int(row['order']), vid=int(row['port']), insn=hex(insn)))
        if event == 'cvx_req':
            tid = int(row['trans_id'])
            assert tid not in pending
            entry = dict(cycle=cycle, csv_line=line, trans_id=tid, opcode=hex(insn))
            pending[tid] = entry
            if insn == 0x0645f207:
                entry['attempt'] = len(targets)
                targets.append(entry)
            if insn == 0x02057207:
                reloads.append(entry)
        if event == 'cvx_resp':
            entry = pending.pop(int(row['trans_id']))
            entry.update(response_cycle=cycle, exception=int(row['trap']))
        if event != 'retire':
            continue
        assert int(row['order']) == retired
        retired += 1
        assert ops[pc] == insn
        rd, value = int(row['rd']), int(row['rd_wdata'],16)
        if pc == symbols['gather32']:
            helpers.append(dict(cycle=cycle, args=[hex(regs[i]) for i in range(10,14)],
                                indices=[value_at(symbols['indices']+i*8) for i in range(32)]))
        if pc == symbols['io_handler']:
            current = dict(handler_cycle=cycle, csv_line=line, csr={}, reads=[], checks=[])
            traps.append(current)
        if current and symbols['io_trap'] <= pc < symbols['main'] and insn & 127 == 0x73:
            f, rs, csr = (insn>>12)&7, (insn>>15)&31, insn>>20
            if rd and f in (2,3) and rs == 0 and csr in csr_names:
                current['csr'][csr_names[csr]] = value
                current['reads'].append(dict(name=csr_names[csr], value=hex(value), cycle=cycle, csv_line=line))
        if pc == symbols['check']:
            check = dict(cycle=cycle, csv_line=line, round=value_at(symbols['io_round']),
                         ordinal=len(checks)+1, got=hex(regs[10]), want=hex(regs[11]),
                         equal=regs[10] == regs[11], return_pc=hex(regs[1]))
            checks.append(check)
            if current is not None:
                current['checks'].append(check)
        if pc == symbols['io_retry_mret'] and current is not None:
            current['mret_cycle'] = cycle
            current = None
        if not int(row['trap']):
            write = memory_access(row, regs, True)
            if write:
                address, value_write, width = write
                for b in range(width):
                    memory[address+b] = (value_write >> (8*b)) & 255
            if rd:
                regs[rd] = value

faults = [t for t in traps if t['csr'].get('mcause') == 13]
for n, fault in enumerate(faults):
    fault['observed_fault_ordinal'] = n
    expect = dict(mcause=13, mepc=symbols['overlap'], mtval=0x40000000+((n%32*13+7)%32)*4096,
                  vstart=n%32, vl=32, vtype=17, fcsr=117, vcsr=5)
    fault['expected'] = {k:hex(v) for k,v in expect.items()}
    fault['mismatch_fields'] = [k for k,v in expect.items() if fault['csr'].get(k) != v]
events = []
console = HERE/'inputs/console_through_profile_close.log'
for line, text in enumerate(console.read_text().splitlines(), 1):
    match = re.search(r'\[ARA_SOURCE_(CAPTURE|REPLAY)\].* t=(\d+) lane=(\d+).* idx=(\d+)(?:/(\d+))? data=([0-9a-f]+)', text)
    if match:
        kind, tick, lane, word, last, data = match.groups()
        events.append(dict(kind=kind, ticks=int(tick), ns=int(tick)/10000, lane=int(lane),
            word=int(word), last=last, data=hex(int(data,16)), console_line=line))
save(HERE/'ledger.json', dict(status='BOUNDED_PREFIX_OBSERVATIONS_NOT_FULL50_ACCEPTANCE',
    targets=targets, faults=faults, checks=checks, helpers=helpers, reloads=reloads,
    allocs=allocs, debug_events=events, last_cycle=cycle, retired=retired,
    no_failed_observed_check=all(c['equal'] for c in checks),
    pins={str(p):sha(p) for p in (path, console, __import__('pathlib').Path(__file__))}))
print(json.dumps(dict(targets=len(targets), faults=len(faults), checks=len(checks),
    failed_checks=sum(not c['equal'] for c in checks), target16=targets[16], fault16=faults[16],
    relevant_debug=[e for e in events if 360000 <= e['ns'] <= 380000 and e['lane']==0 and e['word']==4]),indent=2))
