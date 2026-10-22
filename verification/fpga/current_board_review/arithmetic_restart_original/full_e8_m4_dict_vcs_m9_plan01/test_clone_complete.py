"""Focused clone isolation on the genuine first source helper, no full replay."""
import json
from pathlib import Path
import subprocess
import sys
import time
import checker as c
from host_records import Builder
from host_clone_complete import clone

def witness():
    state=c.Strict(c.specification());builder=Builder(state.spec)
    rows=0
    for row in builder.records():
        state.consume(row);rows+=1
        if state.active is not None and state.helper is None and state.active['returned_vstart']==0:break
    assert len(state.calls)==1 and state.active['original_ordinal']==1 and state.counts==[1]*13
    snapshot=clone(state);negative=clone(snapshot)
    for name in ('spec','gold','s','code','helpers','lookup'):assert getattr(state,name) is getattr(snapshot,name)
    for name in ('regs','memory','fresh','calls','counts','console','offloads'):assert getattr(state,name) is not getattr(snapshot,name)
    assert snapshot.active is snapshot.calls[0] and negative.active is negative.calls[0]
    state.counts[8]+=2;state.console.append(65)
    assert snapshot.counts[8]==negative.counts[8]==1 and snapshot.console==negative.console==bytearray()
    negative.counts[9]+=4;negative.console.append(66);negative.active['reads'].add(64)
    negative.memory[state.s['out']]=0;negative.regs[8]=999;negative.fresh['out'].add(123)
    assert snapshot.counts[9]==state.counts[9]==1 and snapshot.console==bytearray() and state.console==bytearray([65])
    assert not snapshot.active['reads'] and not state.active['reads']
    assert snapshot.memory[state.s['out']]==state.memory[state.s['out']]==91 and snapshot.regs[8]!=999
    assert 123 not in snapshot.fresh['out'] and 123 not in state.fresh['out']
    # Explicit model/spec mutation negatives must not use the shared-state clone.
    from copy import deepcopy
    bad_spec=deepcopy(state.spec);bad_spec['ctrl']=1
    try:c.Strict(bad_spec)
    except ValueError:pass
    else:raise AssertionError('Incorrect spec admitted')
    assert state.spec['ctrl']==0xd0000000
    return dict(status='PASS_COMPLETE_MUTABLE_CLONE',source_prefix_host_rows=rows,source_original_ordinal=1,
        scopes='Focused object isolation only; full4095 data proof remains actual Host03',DUT_runs=0,CSV_reads=0,
        shared_readonly=['spec','gold','s','code','helpers','lookup'],isolated_mutable=['regs','memory','fresh','calls','active.reads','counts','console','offloads'])

if __name__=='__main__':
    if sys.argv[1:]==['--child']:print(json.dumps(witness()),flush=True)
    else:
        from replay import durable
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'--child']
        pins={str(c.HERE/name):c.sha(c.HERE/name) for name in ('host_clone_complete.py','test_clone_complete.py','test_host.py','checker.py')}
        durable(c.HERE/'host_clone_command.json',dict(command=command,timeout_s=30,pins=pins))
        start=time.monotonic()
        with (c.HERE/'host_clone.log').open('x') as stream:
            child=subprocess.Popen(command,cwd=c.HERE,stdout=stream,stderr=subprocess.STDOUT)
            rc=child.wait(timeout=30)
            durable(c.HERE/'host_clone_execution.json',dict(actual_wait_returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start))
        if rc:raise SystemExit(rc)
        result=json.loads((c.HERE/'host_clone.log').read_text());result['pins']=pins
        durable(c.HERE/'host_clone_result.json',result);print(result['status'])
