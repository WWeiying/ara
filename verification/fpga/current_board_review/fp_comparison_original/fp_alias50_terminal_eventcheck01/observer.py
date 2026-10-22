"""Immutable mature six-event transport; exact alias50 scalar oracle is sealed."""
from collections import Counter
import hashlib
import importlib.util
from pathlib import Path
import sys

TRANSPORT=Path(__file__).resolve().parents[2]/'ordered_reduction/original_remaining9_terminal_audit01/observer.py'
assert hashlib.sha256(TRANSPORT.read_bytes()).hexdigest()=='7d15ce50da9918fa9b1d3bb1cea59871b4312385576da1fd6c8d5940dbad650f'
sp=importlib.util.spec_from_file_location('alias50_lossless_transport',TRANSPORT)
transport=importlib.util.module_from_spec(sp);sys.modules[sp.name]=transport;sp.loader.exec_module(transport)

class Observer(transport.Observer):
    def __init__(self,protocol):
        self.protocol=protocol
        # Private module only: exact frozen generic instruction classification.
        transport.vector=protocol.is_vector_instruction
        self.count,self.pcs=Counter(),Counter()
        self.pending,self.uops={},{}
        self.requests,self.arch,self.retvec=[],[],[]
        self.first=self.last=-1
        self.maxcvx=self.maxuop=0
        self.before,self.after=hashlib.sha256(),hashlib.sha256()

    def retirement(self,row,cycle,insn,order):
        self.pcs[int(row['pc'],16)]+=1

    def finish(self):
        assert self.count['rows']>0 and not self.pending and not self.uops
        cvx=self.protocol._validate_retired_request_sequence(self.retvec,self.requests)
        arch=self.protocol._validate_retired_request_sequence(self.arch,self.requests)
        c=self.count
        assert c['rows']==c['unmodified_delivered_rows'] and self.before.digest()==self.after.digest()
        return dict(rows=c['rows'],first_cycle=self.first,last_cycle=self.last,retire_count=c['retire'],
            vector_retire_count=len(self.retvec),cvx_request_count=c['cvx_req'],cvx_response_count=c['cvx_resp'],
            cvx_max_inflight=self.maxcvx,cvx_replay_count=cvx,arch_request_replay_count=arch,cvx_exception_count=0,
            architecture_request_count=len(self.arch),backend_uop_alloc_count=c['uop_alloc'],
            backend_uop_done_count=c['uop_done'],backend_uop_max_inflight=self.maxuop)
