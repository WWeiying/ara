#!/usr/bin/env python3
"""Small constructed partial EOF tests; no captured CSV/reference access."""
import copy
import io
from unittest import mock
from pathlib import Path
import json
import sys
import time
import diagnostic as d
sys.modules['checker']=d.base
records=d.load('partial_host_actual_e16sentinel_builder',d.OLD/'host_records.py')
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


b=records.Builder(spec);data=[];read0=None;endhelper=None;tail=None;entries=0
for row in b.protocol_rows(b.records()):
    data.append(row)
    if row['event']=='retire':
        pc=int(row['pc'],16)
        if pc==spec['backend']['helpers']['op_0'][9]['pc'] and endhelper is None:endhelper=len(data)
        if int(row['mem_rmask'],16) and int(row['mem_addr'],16)==spec['backend']['symbols']['out'] and read0 is None:read0=len(data)
        if int(row['mem_rmask'],16) and int(row['mem_addr'],16)==spec['backend']['symbols']['out']+1024 and tail is None:tail=len(data)
        if pc==spec['backend']['helpers']['op_0'][0]['pc']:
            entries+=1
            if entries==2:break
assert read0 and endhelper and tail
through_next=data;data=data[:tail]
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
    _,r=run(data[:endhelper]);assert r['active_phase']['helper']=='op_0' and r['active_phase']['next_helper_index']==10
    assert r['status']=='DIAGNOSTIC_ONLY_PARTIAL_EOF_NOT_PASS' and not r['architectural_acceptance']
    assert r['calls_with_all129_reads_and_vstart0']==0
check('partial_helper_is_diagnostic_not_pass',partial_helper)
def partial_reads():
    _,r=run(data[:read0]);assert r['packed_reads']==1 and r['calls_with_all129_reads_and_vstart0']==0
check('partial_oracle_not_completed',partial_reads)
def onecall():
    _,r=run(data);assert r['calls_with_all129_reads_and_vstart0']==r['completed_calls_with_data_and_owners']==1
    assert r['calls_entered']==1 and r['whole4095_accepted'] is False
check('one_full_call_not_whole_acceptance',onecall)
bad=copy.deepcopy(data[:read0]);bad[-1]['rd_wdata']=f'{int(bad[-1]["rd_wdata"],16)^1:016x}'
check('actual_numeric_guard_wrong_reject',lambda:run(bad),True)
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
        assert d.base.target_required(0x38813c57,dict(op=19,vstart=0,vl=vl))==want
    assert d.base.target_required(spec['backend']['helpers']['op_24'][8]['insn'],dict(op=24,vstart=0,vl=1))
check('exact_vi2_predicate_and_op24_retained',vi2)
def no_full_finish():
    p,_=run(data[:read0])
    try:p.state.finish()
    except ValueError:return
    raise AssertionError('Full finish accepted truncated case')
check('original_full_finish_still_rejects_partial',no_full_finish)

def renumber(rows):
    count=0;out=[]
    for r in rows:
        r=dict(r)
        if r['event']=='retire':r['order']=str(count);count+=1
        out.append(r)
    return out
initpc=spec['init_stores'][0][0]
badfresh=[r for r in data if not(r['event']=='retire' and int(r['pc'],16)==initpc and int(r['mem_wmask'],16))]
check('deleted_real_init_with_retirement_renumbered_reject',lambda:run(renumber(badfresh)),True)
badread=[r for r in through_next if not(r['event']=='retire' and int(r['mem_rmask'],16) and int(r['mem_addr'],16)==spec['backend']['symbols']['out'])]
check('missing_prior_oracle_word_cannot_be_EOF_waived',lambda:run(renumber(badread)),True)
badid=copy.deepcopy(data)
site=spec['comparator_paths'][0]['IDs'][0]
for r in badid:
    if r['event']=='retire' and int(r['pc'],16)==site['pc'] and int(r['mem_rmask'],16):
        r['rd_wdata']=f'{int(r["rd_wdata"],16)^1:016x}';break
else:raise AssertionError('No real first ID load')
check('wrong_actual_ID_scalar_read_rejected',lambda:run(badid),True)
for bit in (0,16):
    badtail=copy.deepcopy(data);badtail[-1]['rd_wdata']=f'{int(badtail[-1]["rd_wdata"],16)^(1<<bit):016x}'
    check('tail4_result_or_rear_guard_bit_'+str(bit),lambda:run(badtail),True)
badreq=copy.deepcopy(data)
for r in badreq:
    if r['event']=='cvx_req':r['insn']=f'{int(r["insn"],16)^(1<<27):08x}';break
check('prior_request_ordering_error_cannot_be_EOF_waived',lambda:run(badreq),True)
def arch_not_progress():
    p,_=run(data)
    last=p.last_progress
    extra=dict(data[-1],event='arch_start',cycle=str(int(data[-1]['cycle'])+1000),
        order=str(len(p.observer.arch)),port='-1',trans_id='1',
        insn=f'{spec["backend"]["helpers"]["op_0"][0]["insn"]:08x}',
        pc='0000000000000000',rd='0',rd_wdata='0000000000000000',
        mem_addr='0000000000000000',mem_rmask='00',mem_wmask='00',mem_wdata='0000000000000000')
    _,r=run(data+[extra])
    assert r['last_watchdog_progress']==last and r['observed_tail_since_progress_cycles']==1000
    assert r['max_watchdog_progress_gap']['cycles']<1000
check('arch_start_alone_not_watchdog_progress',arch_not_progress)
def bad_final():
    header=(','.join(d.FIELDS)+'\n').encode()
    for raw in (header+b'1,retire',header+b'1,retire\n',header+b'"\n',header+b'\xff'+b',0'*13+b'\n'):
        state=d.StreamState()
        try:list(state.lines(io.BytesIO(raw)))
        except (ValueError,UnicodeDecodeError):
            assert state.bytes==len(raw) and state.raw_preview is not None
        else:raise AssertionError('Bad final physical row was swallowed')
check('bad_final_record_no_newline_columns_ascii_rejected',bad_final)
assert not hasattr(d.Prefix,'finish') # no substitute whole-run acceptance API

for name,value in pins.items():assert d.sha(name)==value,name
d.save(d.HERE/'host.json',dict(status='HOST_ONLY_PASS',tests=len(tests),names=tests,
    elapsed_s=time.monotonic()-started,synthetic_rows=len(data),actual_csv_reads=0,pins=pins))

print('HOST_ONLY_PASS',len(tests))
