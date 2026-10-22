"""Focused opaque-save provenance Host; actual ELF code, no CSV reread."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'zero_stride_e64_m2_original16_vcs_m7_plan01'))
import checker as c
import csv_check_successor as cc
def row(pc,a,value):
    return dict(pc=f'{pc:016x}',mem_addr=f'{a:016x}',mem_rmask='00',mem_wmask='ff',mem_wdata=f'{value:016x}',rd='0',rd_wdata='0')
def main():
    spec=c.specification();positive=[];negative=[]
    for role in ('entry','trap'):
        q=cc.Checker(spec);q.regs[2]=0x800ffeb0
        if role=='entry':pc=q.s['main']+4
        else:
            q.case=0;q.cap=3;q.capture={}
            pc=next(p for p in sorted(q.code) if q.s['mx_handler']<=p<q.handler_save_end and q.code[p]&0x707f==0x3023 and (q.code[p]>>20)&31==31)
        d=cc.memory_op(q.code[pc],q.regs);a=q.regs[2]+d['offset']
        q.scalar(row(pc,a,0x123456789abcdef0),q.code[pc],0)
        c.require(q.regs[d['register']]==0x123456789abcdef0,'Observed opaque payload, never default zero')
        positive.append(dict(role=role,pc=hex(pc),register=d['register'],payload=hex(q.regs[d['register']])))
        for bad in ('address','owner'):
            q=cc.Checker(spec);q.regs[2]=0x800ffeb0
            if role=='trap':q.case=0;q.cap=3;q.capture=None if bad=='owner' else {}
            elif bad=='owner':q.case=0
            try:q.scalar(row(pc,a+8 if bad=='address' else a,0x123456789abcdef0),q.code[pc],0)
            except (ValueError,KeyError):negative.append(role+'_'+bad)
            else:raise ValueError('Accepted opaque-save negative '+role+'_'+bad)
    c.common.save(HERE/'opaque_policy_host.json',dict(status='HOST_PASS_NOT_DUT',positive=positive,negative=negative,
       pins={str(p):c.sha(p) for p in (Path(__file__),HERE/'csv_check_successor.py',HERE/'reset_profile.py')}))
    print('OPAQUE_POLICY_HOST_PASS',positive,negative)
if __name__=='__main__':main()

