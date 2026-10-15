"""Small exact-entry gates; constructed tests are not a full raw proof."""
from collections import Counter
import re
from context import *
ABI=['zero','ra','sp','gp','tp','t0','t1','t2','s0','s1']+['a'+str(i) for i in range(8)]+['s'+str(i) for i in range(2,12)]+['t'+str(i) for i in range(3,7)]
class Capacity:
    def __init__(self,helpers):
        self.rows=helpers['capacity'];self.step=0;self.counts=[0,0,0];self.last=None
        require([r['insn'] for r in self.rows]==[0x52fd,0x0032f557,0x8082],'Actual e8 capacity3 machine code')
    def observe(self,pc,insn,retired,regs,csrs,rd,changes,rest):
        pcs=[r['pc'] for r in self.rows]
        if 0<self.step<3:require(pc==pcs[self.step] and retired==self.last+1,'Capacity3 continuous retirement')
        if pc not in pcs:return
        j=pcs.index(pc)
        require(j==self.step and insn==self.rows[j]['insn'],'Capacity3 exact once/code/order')
        require(not re.search(r'\b(?:mem|v\s*\d+)\b',rest),'No capacity memory/vector data effects')
        if j==0:require(rd==(5,MASK64),'Actual li t0,-1')
        elif j==1:
            require(regs.get(5)==MASK64 and rd==(10,1024),'Actual capacity vsetvli input/return')
            require(changes.get('vl')==1024 and changes.get('vtype')==3 and changes.get('vstart',csrs.get('vstart'))==0,'Actual capacity VL1024/vtype3 and known/reset vstart')
        else:
            require(rd is None and not re.search(r'\bc\d+_',rest),'Capacity ret no extra effects')
            require(regs.get(5)==MASK64 and regs.get(10)==1024 and csrs.get('vl')==1024 and csrs.get('vtype')==3,'Capacity ret actual known state')
        self.counts[j]+=1;self.step+=1;self.last=retired
    def finish(self):
        require(self.step==3 and self.counts==[1,1,1],'Complete actual capacity3')
class Comparator:
    def __init__(self,machine):
        names=[n for n in machine.functions if n.startswith('packed_mismatch')]
        require(len(names)==1,'Exact linked comparator function')
        self.code={x['pc']:x for x in machine.functions[names[0]]}
        self.entry=min(self.code);self.next=None;self.calls=0;self.visits=Counter()
    def observe(self,pc,insn,regs,call_ordinal):
        if self.next is None:
            if pc not in self.code:return
            require(pc==self.entry and call_ordinal==self.calls+1 and regs.get(10)==self.calls,'Actual comparator entry/ordinal')
            self.next=pc
        require(pc==self.next and pc in self.code,'Comparator drop/reorder/outside-window')
        x=self.code[pc];require(insn==x['insn'],'Actual comparator code')
        self.visits[pc]+=1;op=x['op'];args=[s.strip() for s in x['args'].split(',')]
        def reg(name):
            require(name in ABI and ABI.index(name) in regs,'Known comparator branch source')
            return regs[ABI.index(name)]
        if op=='ret':
            require(regs.get(10)==0,'Comparator mismatch/nonzero return')
            self.next=None;self.calls+=1;return
        nxt=pc+(4 if insn&3==3 else 2)
        if op=='j':nxt=int(args[0].split()[0],16)
        elif op in ('beq','bne','beqz','bnez'):
            a=reg(args[0]);b=0 if op in ('beqz','bnez') else reg(args[1])
            take=a==b if op in ('beq','beqz') else a!=b
            if take:nxt=int(args[-1].split()[0],16)
        require(nxt in self.code,'Finite comparator nextPC')
        self.next=nxt
    def finish(self,want):
        require(self.next is None and self.calls==4095,'Full4095 comparator returns')
        require(dict(self.visits)=={int(p,16):n for p,n in want.items()},'Actual comparator PC path counts incl ID0 materialization')
def within_firmware_budget(value):
    require(type(value)is int and value>0,'Actual firmware numeric count required')
    return value<=3000000
