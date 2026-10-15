#!/usr/bin/env python3
"""Small constructed partial EOF tests; no captured CSV/reference access."""
import copy
import json
import sys
import time
import diagnostic as d
sys.modules['checker']=d.base
records=d.load('partial_host_actual_e16m8_builder',d.OLD/'host_records.py')
spec,pins=d.inputs()
started=time.monotonic()


class Rows:
    fieldnames=d.base.mature.transport.transport.FIELDS
    def __init__(self,rows):self.data=rows
    def __iter__(self):return iter(self.data)


def run(rows):
    p=d.Prefix(spec)
    for row in p.observer.rows(Rows(rows)):p.consume(row)
    return p,p.partial()


b=records.Builder(spec);data=[];read0=None;endhelper=None
for row in b.protocol_rows(b.records()):
    data.append(row)
    if row['event']=='retire':
        pc=int(row['pc'],16)
        if pc==spec['backend']['helpers']['op_0'][9]['pc'] and endhelper is None:endhelper=len(data)
        if int(row['mem_rmask'],16) and int(row['mem_addr'],16)==spec['backend']['symbols']['out'] and read0 is None:read0=len(data)
        if int(row['mem_rmask'],16) and int(row['mem_addr'],16)==spec['backend']['symbols']['out']+1024:break
assert read0 and endhelper
tests=[]
def check(name,fn,raises=False):
    try:
        fn()
    except (ValueError,AssertionError,KeyError):
        if not raises:raise
    else:
        assert not raises,name+' accepted counterexample'
    tests.append(name)


def partial_helper():
    _,r=run(data[:endhelper]);assert r['helper']=='op_0' and r['next_helper_index']==10
    assert r['status']=='DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS' and not r['architectural_acceptance']
    assert r['calls_with_all129_reads_vstart0']==0
check('partial_helper_is_diagnostic_not_pass',partial_helper)
def partial_reads():
    _,r=run(data[:read0]);assert r['packed_reads']==1 and r['calls_with_all129_reads_vstart0']==0
check('partial_oracle_not_completed',partial_reads)
def onecall():
    _,r=run(data);assert r['calls_with_all129_reads_vstart0']==r['calls_with_checked_completed_owners']==1
    assert r['calls_entered']==1 and r['full4095_complete'] is False
check('one_full_call_not_whole_acceptance',onecall)
bad=copy.deepcopy(data[:read0]);bad[-1]['rd_wdata']=f'{int(bad[-1]["rd_wdata"],16)^1:016x}'
check('actual_numeric_guard_wrong_reject',lambda:run(bad),True)
badtyped=copy.deepcopy(data[:read0]);badtyped[-1]['rd_wdata']='5b5b5b5b5b5b5b5b'
check('e8_byte_sentinel_cannot_replace_typed005b',lambda:run(badtyped),True)
badtail=copy.deepcopy(data);badtail[-1]['rd_wdata']=f'{int(badtail[-1]["rd_wdata"],16)^(1<<16):016x}'
check('tail4_upper_guard_wrong_reject',lambda:run(badtail),True)
badwidth=copy.deepcopy(data);badwidth[-1]['mem_rmask']='03'
check('tail4_cannot_be_tail2',lambda:run(badwidth),True)
badpc=copy.deepcopy(data[:read0]);badpc[-1]['insn']='00000013'
check('actual_elf_code_wrong_reject',lambda:run(badpc),True)
firstalloc=next(r['order'] for r in data if r['event']=='uop_alloc')
deleted=[r for r in data if not(r['event'] in ('uop_alloc','uop_done') and r['order']==firstalloc)]
check('required_memory_pair_deleted_reject',lambda:run(deleted),True)
unknown=[r for r in data if not(r['event']=='uop_alloc' and r['order']==firstalloc)]
check('unknown_done_reject',lambda:run(unknown),True)
def pending():
    end=next(i+1 for i,r in enumerate(data) if r['event']=='uop_alloc')
    _,r=run(data[:end]);assert r['generic']['pending_uop'] and r['generic']['pending_cvx']
    assert not r['architectural_acceptance']
check('pending_at_eof_exposed_not_accepted',pending)
def vi2():
    for vl,want in [(0,False),(1,False),(2,False),(3,True)]:
        assert d.delta.target_required(0x38813c57,dict(op=19,vstart=0,vl=vl),spec)==want
    assert d.delta.target_required(spec['backend']['helpers']['op_24'][8]['insn'],dict(op=24,vstart=0,vl=1),spec)
check('exact_vi2_predicate_and_op24_retained',vi2)
def no_full_finish():
    p,_=run(data[:read0])
    try:p.state.finish()
    except ValueError:return
    raise AssertionError('Full finish accepted truncated case')
check('original_full_finish_still_rejects_partial',no_full_finish)
def typed_geometry():
    g=d.base.model()[0]
    assert g['raw']==bytes([91,0])*514 and len(g['a'])==len(g['b'])==1024
    assert len(g['mask'])==128 and not any(g['mask'][64:])
    assert spec['config']['cap']==512 and spec['backend']['helpers']['op_0'][0]['insn']==0x00b772d7
check('own_typed_gold_physical_group8_upper_mask',typed_geometry)
for name,value in pins.items():assert d.sha(name)==value,name
d.save(d.HERE/'host.json',dict(status='HOST_ONLY_PASS',tests=len(tests),names=tests,
    elapsed_s=time.monotonic()-started,synthetic_rows=len(data),actual_csv_reads=0,pins=pins))
print('HOST_ONLY_PASS',len(tests))
