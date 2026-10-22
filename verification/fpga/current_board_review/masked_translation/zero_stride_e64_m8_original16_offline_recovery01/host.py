"""Focused real-bootstrap and unknown-CSR Host, no raw full parse."""
import sys
from pathlib import Path
sys.dont_write_bytecode=True
WORKER=Path(__file__).resolve().parent.parent/'zero_stride_e64_m8_original16_vcs_m7_plan01'
sys.path.insert(0,str(WORKER))
import checker as c
import csv_check_successor as cc
from reset_profile import *
def main():
    spec=c.specification();q=cc.Checker(spec)
    c.require(q.csrs=={0x300:0xa00000000},'Only proved CSR initialized')
    q.regs[5]=0x6600
    fields=cc.FIELDS
    r={k:'0' for k in fields};r.update(cycle='115',event='retire',order='0',port='0',trans_id='-1',
       pc='0000000080000026',insn='3002a073',rd='0',rd_wdata='0000000a00000000',mem_rmask='00',mem_wmask='00')
    q.row(r);c.require(q.csrs[0x300]==0x8000000a00006600,'Image-bound bootstrap + derived SD')
    negatives=[]
    for name,f in [('unknownCSRnot0',lambda: unknown(spec,r)),
      ('dirtySDmissing',lambda:check_mstatus_read(0xa00006600)),
      ('cleanSDset',lambda:check_mstatus_read(0x8000000a00000000)),
      ('unknown_GPR_not_default0',lambda:unknown_gpr(spec)),
      ('wrongSXL',lambda:check_mstatus_read(0x8000000900006600))]:
        try:f()
        except (ValueError,KeyError):negatives.append(name)
        else:raise ValueError('Accepted '+name)
    c.common.save(Path(__file__).parent/'host.json',dict(status='HOST_PASS_NOT_DUT',positive_bootstrap_mstatus=hex(q.csrs[0x300]),negative=negatives))
    print('HOST_PASS',negatives)
def unknown_gpr(spec):
    q=cc.Checker(spec);q.regs[2]=0x800ffff0
    pc=spec['symbols']['main']+4
    r={k:'0' for k in cc.FIELDS};r.update(pc=hex(pc)[2:],insn=hex(q.code[pc])[2:],mem_addr='800fffe0',mem_rmask='00',mem_wmask='ff',mem_wdata='0')
    # An unobserved address/base is still not allowed; no default GPR substitution.
    del q.regs[2];q.scalar(r,q.code[pc],0)
def unknown(spec,r):
    q=cc.Checker(spec);q.csrs.clear();q.regs[5]=0x6600;q.row(r)
if __name__=='__main__':main()




