#!/usr/bin/env python3
"""Read completed baseline CSVs; report actual trap CSR and restart evidence."""
import argparse
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import sv39_adapter as ref

CSR = {0x342:'mcause',0x341:'mepc',0x343:'mtval',0x300:'mstatus',0x180:'satp',
       0xc20:'vl',0xc21:'vtype',0x008:'vstart',0x003:'fcsr',0x00f:'vcsr'}
RECORD = list(CSR.values())+['marker','target_pte']


def analyze(directory, name):
    s = json.loads((directory/(name+'.symbols.json')).read_text())
    case = directory/name
    artifact = case/'tests'/name
    trace = artifact/'commit_trace.csv'
    report = json.loads((case/'summary.json').read_text())
    ref.require(isinstance(report,list), 'Unexpected sealed runner summary schema')
    rows = report
    result = next(row for row in rows if row.get('name') == name)
    traps, record_writes, sites, front, important_stores = [], [], [], [], []
    named_sites = {s[n]:n for n in ('mt_target','mt_recovery_load','mt_younger_store',
        'mt_ecall','mt_repair_store','mt_repair_sfence','mt_retry_mret') if n in s}
    important = {s[n]:n for n in ('mt_mask','mt_marker','mt_trap_count',
        'mt_unexpected','mt_checks','mt_errors','mt_completed')}
    important[s['mt_pages']+16392] = 'target_leaf_pte'
    values = {}
    first_trap_cycle = None
    last_cycle = 0
    with trace.open() as stream:
        for row in csv.DictReader(stream):
            ref.require(None not in row.values(), 'Truncated completed CSV row')
            cycle, insn = int(row['cycle']),int(row['insn'],16)
            last_cycle = cycle
            if row['event'] != 'retire':
                if insn == 0x00055c07 or (row['event'] == 'cvx_resp' and row['trap'] == '1'):
                    front.append(row)
                continue
            pc,rd,value = int(row['pc'],16),int(row['rd']),int(row['rd_wdata'],16)
            if pc in named_sites:
                sites.append(dict(site=named_sites[pc],cycle=cycle,pc=hex(pc),
                                  instruction=hex(insn),trap=int(row['trap'])))
            if s['mt_handler'] <= pc < s['mt_check_ecall'] and insn & 127 == 0x73 and \
                    (insn >> 12) & 7 in (2,3) and (insn >> 15) & 31 == 0 and rd:
                csr = insn >> 20
                if csr == 0x342:
                    traps.append(dict(first_csr_cycle=cycle))
                    if first_trap_cycle is None:
                        first_trap_cycle = cycle
                if csr in CSR and traps:
                    ref.require(CSR[csr] not in traps[-1],'Duplicate captured handler CSR')
                    traps[-1][CSR[csr]] = value
            addr,wmask,wdata = int(row['mem_addr'],16),int(row['mem_wmask'],16),int(row['mem_wdata'],16)
            if not wmask:
                continue
            if addr in important:
                values[important[addr]] = wdata
                if important[addr] not in ('mt_checks','mt_errors'):
                    important_stores.append(dict(name=important[addr],cycle=cycle,value=hex(wdata),wmask=hex(wmask)))
            if s['mt_records'] <= addr < s['mt_records']+192 and wmask == 255 and \
                    s['mt_handler'] <= pc < s['mt_check_ecall']:
                offset = addr-s['mt_records']
                ref.require(offset % 8 == 0,'Unaligned trap record write')
                record_writes.append(dict(record=offset//96,field=RECORD[(offset%96)//8],
                                          value=wdata,cycle=cycle,pc=hex(pc)))
    records = [{r['field']:r['value'] for r in record_writes if r['record'] == n} for n in range(len(traps))]
    for i,t in enumerate(traps):
        for field in CSR.values():
            if field in t and field in records[i]:
                ref.require(t[field] == records[i][field], 'CSR/record mismatch: '+field)
    expected_fault = dict(mcause=13,mepc=s['mt_target'],mtval=0x40001000,vl=8,vtype=8,
                          vstart=0,fcsr=117,vcsr=5)
    first_is_target_fault = bool(traps) and all(traps[0].get(k) == v for k,v in expected_fault.items()) and \
        traps[0].get('mstatus',0) & 0x8000031888 == 0x800 and \
        traps[0].get('satp',0) == (8 << 60) | ((s['mt_pages']+8192) >> 12)
    before = [v for v in important_stores if first_trap_cycle is not None and v['cycle'] < first_trap_cycle]
    setup = {v['name']:v['value'] for v in before}
    confirmed_alloff = name == 'alloff_fault' and first_is_target_fault and \
        setup.get('mt_mask') == '0x0' and setup.get('target_leaf_pte') == '0x0' and \
        records and records[0].get('marker') == 0 and records[0].get('target_pte') == 0
    if result['status'] == 'PASS':
        ref.require(values.get('mt_checks') == 709 and values.get('mt_errors') == 0 and
                    values.get('mt_completed') == ref.DONE, 'PASS missing actual software oracle completion')
        expected_causes = [13,9] if name == 'active_fault_retry' else [9]
        ref.require([t.get('mcause') for t in traps] == expected_causes, 'PASS has wrong exact trap ledger')
        ref.require(traps[-1].get('mepc') == s['mt_ecall'] and traps[-1].get('mtval') == 0,
                    'PASS missing exact terminal S-ECALL')
        if name == 'active_fault_retry':
            ref.require(first_is_target_fault and setup.get('mt_mask') == '0x1' and
                        setup.get('target_leaf_pte') == '0x0', 'Active control not the intended fault')
            ordering = [site['site'] for site in sites if site['site'] != 'mt_ecall']
            ref.require(ordering == ['mt_repair_store','mt_repair_sfence','mt_retry_mret',
                        'mt_target','mt_recovery_load','mt_younger_store'], 'Actual original-PC retry order differs')
    if confirmed_alloff:
        classification = 'CONFIRMED_ALLOFF_TARGET_PAGE_FAULT_ON_UNFIXED_FINAL04'
    elif result['status'] == 'PASS':
        classification = 'STRICT_SOFTWARE_CONTROL_PASS_ON_UNFIXED_FINAL04'
    else:
        classification = 'BASELINE_CONTROL_NOT_PASS_SEE_FIRST_EVENT'
    return dict(name=name,runner=result,classification=classification,first_target_fault=first_is_target_fault,
                trap_csr_reads=traps,trap_records=records,sites=sites,target_front_events=front,
                last_scalar_values={k:hex(v) for k,v in values.items()},setup_before_first_trap=setup,
                last_cycle=last_cycle,trace_sha256=ref.sha(trace),
                architectural_candidate_pass=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    args = p.parse_args()
    directory = ref.inside(args.run)
    ref.require((directory/'complete.json').is_file(),'Wait for completed supervisor')
    ref.require(not (directory/'analysis.json').exists(),'Do not overwrite analysis')
    results = {name:analyze(directory,name) for name in ref.NAMES}
    ref.save(directory/'analysis.json',dict(status='FINAL04_BASELINE_EVIDENCE_NOT_CANDIDATE',
         results=results,analyzer_sha256=ref.sha(Path(__file__)),
         preflight_sha256=ref.sha(directory/'preflight.json'),
         completion_sha256=ref.sha(directory/'complete.json')))
    print(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
