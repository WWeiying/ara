"""Fast read-only extraction of the accepted reference's scalar comparison ledger."""
import re
import reference as ref
from support import read
from host_csv import commits


def extract(directory):
    s=read(directory/'spike.symbols.json'); gold=read(directory/'status.json')
    regs={i:0 for i in range(32)}; state={s['nx_current']:0,s['nx_phase']:0}; result=[]
    for pc,insn,tail,trap in commits(directory/'spike.trace'):
        if pc==s['check']:
            kind,index,got,want=[regs[i] for i in range(10,14)]
            ref.base.require(got==want,'Reference firsterror')
            if kind==1 and index==1:
                names=[n for n in ('fault_0_pc','fault_1_pc','nx_ecall') if s[n]==want]
                ref.base.require(len(names)==1,'Unrecognized reference trap PC')
                want=dict(symbol=names[0])
            result.append([state[s['nx_current']],state[s['nx_phase']],kind,index,want])
        if 'mem ' in tail:
            for a,v in re.findall(r'\bmem 0x([0-9a-f]+) 0x([0-9a-f]+)',tail):
                address=int(a,16)
                if address in state: state[address]=int(v,16)
        if not trap:
            regs.update({int(r):int(v,16) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)})
    ref.base.require(len(result)==gold['checks'],'Reference ledger count differs')
    return result
