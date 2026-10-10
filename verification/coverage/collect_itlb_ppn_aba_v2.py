"""Offline CSR-aware console successor; unchanged full scalar/trap/AXI/slot/gain gates."""
import argparse
import csv
from pathlib import Path
import re
from types import FunctionType, SimpleNamespace

import collect_itlb_ppn_aba as old

life,require=old.life,old.require
ORIGINAL_SHA='1fd703e7df46fc5fd8bacfa903ffd81b5ec649bedd53a4f909d9752694c2bcd9'
PREPARED_SHA='ee90d67c0e880ee590d822e6b1131ee8154962ca5f4c926149e75b8ac199bd12'
WORDS=[0x00802773,0x00f024f3]*3
SUMMARY_FIELDS=('requests','responses','exceptions','mmu_request_cycles','protocol_errors',
                'outstanding','req_stalled','resp_stalled')


def console_gate(text,rows,reference,vector):
    lines=text.splitlines()
    require(lines.count('Core Test *** SUCCESS ***')==1,'Exact terminal software success required')
    require(not any(re.match(r'^\s*(?:UVM_ERROR|UVM_FATAL|Error-|Fatal:|Exception @)',line)
                    for line in lines),'Actual console error/exception')
    summaries=[line for line in lines if line.startswith('[ARA_CONTRACT]')]
    pattern=r'\[ARA_CONTRACT\] '+' '.join(name+r'=(\d+)' for name in SUMMARY_FIELDS)
    require(len(summaries)==1 and re.fullmatch(pattern,summaries[0]) is not None,
            'One complete exact eight-field terminal contract required')
    values=tuple(int(x) for x in re.fullmatch(pattern,summaries[0]).groups())
    require(values==(6,6,0,0,0,0,0,0),'Declared six readonly CSR requests/responses or errors differ')
    lifecycle=old.csr_lifecycle(rows,reference)
    requests=[row for row in rows if row['event']=='cvx_req']
    require([int(row['insn'],16) for row in requests]==WORDS,'Exact three vstart/vcsr pairs required')
    expected=[(int(row['trans_id']),int(row['insn'],16)) for row in requests]
    trace_pattern=(r'\[ARA_CONTRACT_TRACE\] sample=pre_edge cycle=(\d+) req=1/1 fire=1 id=(\d+) '
        r'insn=([0-9a-fA-F]{8}) resp=1/1 fire=1 id=(\d+) exc=0 pending=00 stalled=([01]{2}) errors=0000000')
    traces=[line for line in lines if line.startswith('[ARA_CONTRACT_TRACE]')]
    parsed=[re.fullmatch(trace_pattern,line) for line in traces]
    require(len(parsed)==6 and all(parsed),'Exact six independent pre-edge handshake records required')
    require([(int(p[2]),int(p[3],16)) for p in parsed]==expected and
            all(p[2]==p[4] for p in parsed) and
            all(int(a[1])<int(b[1]) for a,b in zip(parsed,parsed[1:])),
            'Console req/resp identity/order differs from CSR CSV')
    # UVM monitor and commit monitor have distinct cycle counters: bind command
    # identity/order, retaining rather than equating their cycle coordinates.
    events=[line for line in lines if '[CVXIF/EVENT]' in line]
    event_pattern=(r'.*\[CVXIF/EVENT\] cycle=(\d+) req_fire=1 req_id=(\d+) '
                   r'insn=([0-9a-fA-F]{8}) resp_fire=1 resp_id=(\d+) exc=0')
    monitored=[re.fullmatch(event_pattern,line) for line in events]
    require(len(monitored)==6 and all(monitored) and
            [(int(p[2]),int(p[3],16)) for p in monitored]==expected and
            all(p[2]==p[4] for p in monitored),'Independent monitor six-command conservation differs')
    require(len(vector)==1 and vector[0]['event']=='config' and
            int(vector[0]['nr_lanes'])==4 and int(vector[0]['vlen_bits'])==1024 and
            int(vector[0]['be'],16)==0 and int(vector[0]['wdata'],16)==0 and
            int(vector[0]['insn'],16)==0,'No vector instructions/writeback permitted')
    return dict(status='SIX_READONLY_CSR_CONSOLE_CSV_MONITOR_EXACT_ZERO_VECTOR_WRITES',
        summary=dict(zip(SUMMARY_FIELDS,values)),lifecycle=lifecycle,
        boundary_cycles=[int(p[1]) for p in parsed],monitor_cycles=[int(p[1]) for p in monitored],
        different_cycle_counters_not_equated=True,zero_vector_writes=True,
        UVM_final_summary_claimed=False)


def collect(prepared,seal,output):
    require(seal==PREPARED_SHA and life.digest(Path(old.__file__).resolve())==ORIGINAL_SHA,
            'Exact frozen original collector/prepared configuration required')
    record=life.read_bound(prepared,seal)
    run=Path(record['output'])
    failure=run.with_name(run.name+'-qualified')/'failure.json'
    require(failure.is_file(),'Original failed qualification must be preserved')
    fail=life.read_bound(failure,life.digest(failure))
    require(fail['reason']=='Zero-vector contract differs' and fail['coverage_admitted'] is False,
            'Exact original CSR-versus-zero-contract rejection required')
    extra=old.axi.csr.source_pins()
    for path in (Path(__file__).resolve(),Path(__file__).with_name('test_collect_itlb_ppn_aba_v2.py').resolve(),failure):
        extra=life.merge_pins(extra,{str(path):life.digest(path)})
    receipt={}
    def markers(text):
        with (run/'commit_trace.csv').open() as f:rows=list(csv.DictReader(f))
        with (run/'vector_trace.csv').open() as f:vector=list(csv.DictReader(f))
        pre=life.read_bound(Path(record['preflight']),record['preflight_seal'])
        reference=old.pre.reference(Path(record['preflight']).parent/'spike.trace',pre['symbols'])
        receipt.update(console_gate(text,rows,reference,vector))
        clone=FunctionType(old.original.markers.__code__,dict(old.original.markers.__globals__,
            reference=SimpleNamespace(console_gate=lambda actual:require(actual==text,'Foreign console text'))))
        clone(text)  # Unchanged exact13 observation paths/READY/no ERROR checks.
    def save(path,value):
        if path.name=='evidence-pins.json':
            value=life.merge_pins(value,extra);life.check(value)
        elif path.name=='qualification.json':
            require(receipt,'Console/CSR gate did not execute')
            life.save(output/'console-csr-contract.json',receipt)
            value=dict(value,input_pins=life.merge_pins(value['input_pins'],extra),
                output_pins=life.merge_pins(value['output_pins'],
                    {str(output/'console-csr-contract.json'):life.digest(output/'console-csr-contract.json')}),
                offline_successor='Exact six readonly CSR requests; zero vector writeback; all original ISA/trap/AXI/PPN gates retained',
                original_failure_preserved=True,original_collector_sha256=ORIGINAL_SHA)
            life.check(value['input_pins'])
        return life.save(path,value)
    private_life=SimpleNamespace(**dict(life.__dict__,save=save))
    private_original=SimpleNamespace(**dict(old.original.__dict__,markers=markers))
    fn=FunctionType(old.collect.__code__,dict(old.collect.__globals__,life=private_life,original=private_original))
    fn(prepared,seal,output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--seal',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    collect(a.prepared.absolute(),a.seal,a.output.absolute())
