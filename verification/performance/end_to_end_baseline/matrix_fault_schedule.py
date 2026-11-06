"""Prove fault/replay event order without removing the overlap requirement."""
import re

from audit import require
from projection_resources import geometry


def prefix(text,count=2):
    shapes=geometry(text);require(count<=len(shapes),'Insufficient context prefix')
    lines=[f'QBSCMD1 {count}'];current=None
    for line in text.splitlines()[1:]:
        words=line.split()
        if words and words[0]=='CMD':current=int(words[1])
        if current is not None and current<count:lines.append(line)
        if words and words[0]=='END':current=None
    result='\n'.join(lines)+'\n';require(len(geometry(result))==count,'Incomplete prefix')
    return result


def probe_bench(text):
    old='  initial $display("MATRIX_ENGINE_CONFIG wide=%0d", Wide);'
    require(text.count(old)==1,'Probe insertion anchor')
    text=text.replace(old,old+'\n  `include "matrix_replay_probe.svh"',1)
    old='      else if (axi_r_valid && axi_r_ready) response_delay <= response_gap;'
    new='''      else if (axi_r_valid && axi_r_ready)
        // Only injected-error traffic uses the optional fast drain. Ordinary
        // DIRECT/FILL/REUSE timing retains the selected response_gap.
        response_delay <= $test$plusargs("MATRIX_FAST_FAULT_DRAIN") &&
            inject_axi_fault && activation_access inside {
                QBS_ACTIVATION_ACCESS_REUSE, QBS_ACTIVATION_ACCESS_RELEASE}
            ? 0 : response_gap;'''
    require(text.count(old)==1,'Slave schedule anchor')
    return text.replace(old,new,1)


def late_fault_proof(text):
    require(text.splitlines().count('MATRIX_FAULT_SCHEDULE fast=0')==1,'Not passive schedule')
    require(text.count('wide context fault did not interrupt active replay')==1,'Wrong original failure')
    require(len(re.findall(r'^Fatal:',text,re.M))==1 and not re.search(r'^Error:',text,re.M),
            'Unexpected additional failure')
    events=[(int(c),event,int(m),int(access),int(busy),int(offset)) for c,event,m,access,busy,offset in
            re.findall(r'^MATRIX_REPLAY_EVENT cycle=(\d+) event=(\w+) m=(\d+) access=(\d+) '
                       r'busy=([01]) offset=(\d+)$',text,re.M)]
    target=[e for e in events if e[2:4]==(4,2)]
    errors=[e for e in target if e[1]=='AXI_ERROR']
    faults=[e for e in target if e[1]=='READ_FAULT']
    require(len(errors)==len(faults)==1,'Fault identity/quantity differs')
    start=[e for e in target if e[1]=='START'];last=[e for e in target if e[1]=='REPLAY_LAST']
    idle=[e for e in target if e[1]=='REPLAY_IDLE'];axi_last=[e for e in target if e[1]=='AXI_LAST' and e[0]>errors[0][0]]
    require(len(start)==len(last)==len(idle)==1 and axi_last,'Missing replay/drain events')
    require(start[0][0]<errors[0][0]<last[0][0]<idle[0][0]<faults[0][0] and faults[0][4]==0 and
            last[0][0]<max(e[0] for e in axi_last)<faults[0][0],
            'Fault-before-replay-drain hypothesis disproven')
    return dict(state='LATE_FAULT_COVERAGE_PRECONDITION_PROVED',events=target,
                note='Original required overlap was absent; no RTL numerical/cancellation failure established')
