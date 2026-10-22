#!/usr/bin/env python3
"""Offline Spike-to-scalar-RVFI checker exercise, never DUT evidence or a launch."""
import argparse
import copy
import re
from pathlib import Path
import sys
sys.dont_write_bytecode=True
import reference as ref
import csv_oracle as oracle
from support import read,save

COMMIT=re.compile(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$')


def commits(path):
    pending=None
    with Path(path).open() as stream:
        for line in stream:
            m=COMMIT.match(line)
            if m:
                if pending: yield pending
                pending=[int(m[2],16),int(m[3],16),m[4],0]
            elif 'exception ' in line and pending:
                pending[3]=1
        if pending: yield pending


def rows(path,s):
    order=0
    for pc,insn,tail,trap in commits(path):
        writes=re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)
        ref.base.require(len(writes)<=1,'Multiple scalar GPR writes in reference')
        rd,value=(int(writes[0][0]),int(writes[0][1],16)) if writes else (0,0)
        mem=[(int(a,16),int(v,16) if v else None)
             for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
        d=ref.base.compressed_memory(insn) if insn&3!=3 else None
        scalar=d is not None or insn&127 in (3,0x23)
        address=rmask=wmask=data=0
        if scalar and mem and not trap:
            ref.base.require(len(mem)==1,'Multiple scalar accesses')
            address,data=mem[0]
            width=d['size'] if d else 1<<(((insn>>12)&7)&3)
            if data is None: rmask=((1<<width)-1)<<(address%8); data=0
            else: wmask=((1<<width)-1)<<(address%8)
        if address==s['tohost']:
            ref.base.require(data==1,'Reference HTIF failure')
            # Replace only the HTIF termination shim with an explicit CTRL shim.
            for newinsn,newrd,newvalue in [(0xd00002b7,5,0xffffffffd0000000),
                                          (0x02029293,5,0xd000000000000000),
                                          (0x0202d293,5,0xd0000000),(0x00000513,10,0)]:
                yield row(order,0x90000000+order*4,newinsn,newrd,newvalue)
                order+=1
            yield row(order,0x90000000+order*4,0x00a2b023,0,0,0xd0000000,0,255,0)
            return
        yield row(order,pc,insn,rd,value,address,rmask,wmask,data,trap)
        order+=1


def row(order,pc,insn,rd=0,value=0,address=0,rmask=0,wmask=0,data=0,trap=0):
    return dict(cycle=str(order+1),event='retire',order=str(order),port='0',trans_id='-1',
                pc=f'{pc:016x}',insn=f'{insn:08x}',rd=str(rd),rd_wdata=f'{value:016x}',
                mem_addr=f'{address:016x}',mem_rmask=f'{rmask:02x}',mem_wmask=f'{wmask:02x}',
                mem_wdata=f'{data:016x}',trap=str(trap))


def extract_ledger(directory):
    s=read(directory/'spike.symbols.json'); gold=read(directory/'status.json')
    regs={i:0 for i in range(32)}; state={s['ix_current']:0,s['ix_phase']:0}; result=[]
    for r in rows(directory/'spike.trace',s):
        pc=int(r['pc'],16)
        if pc==s['check']:
            kind,index,got,want=[regs[i] for i in range(10,14)]
            ref.base.require(got==want,'Reference contains firsterror')
            if kind==1 and index==1:
                names=[n for n in ('fault_0_pc','fault_1_pc','ix_ecall') if s[n]==want]
                ref.base.require(len(names)==1,'Unrecognized trap PC')
                want=dict(symbol=names[0])
            result.append([state[s['ix_current']],state[s['ix_phase']],kind,index,want])
        if int(r['mem_wmask'],16):
            a=int(r['mem_addr'],16)
            if a in state: state[a]=int(r['mem_wdata'],16)
        rd=int(r['rd'])
        if rd and not int(r['trap']): regs[rd]=int(r['rd_wdata'],16)
    ref.base.require(len(result)==gold['checks'],'Extracted ledger count differs')
    return result


def exercise(directory,out):
    ref.base.require(not out.exists(),'Fresh host output required')
    out.mkdir()
    s=read(directory/'spike.symbols.json'); cases=read(directory/'cases.json'); gold=read(directory/'status.json')
    ledger=extract_ledger(directory); save(out/'ledger.json',ledger)
    checker=oracle.Checker(s,cases,gold,ledger)
    negatives=[]; last_checkpoint=None; check_state=None
    for r in rows(directory/'spike.trace',s):
        if int(r['pc'],16)==s['ix_checkpoint']:
            last_checkpoint=(copy.deepcopy(checker),dict(r))
        if check_state is None and int(r['pc'],16)==s['check']:
            check_state=copy.deepcopy(checker)
        try: checker.row(r)
        except Exception as error:
            save(out/'failure.json',dict(row=r,analysis=checker.failure(error)))
            raise
    positive=checker.finish()
    def reject(name,fn):
        try: fn()
        except (ValueError,KeyError): negatives.append(name)
        else: raise ValueError('Accepted negative: '+name)
    for name,addr in [('fractional_upper_tail',s['ix_result']+64+2*128+31*4),
                      ('output_guard',s['ix_output']),('outside_data',s['ix_pages']),
                      ('PTE',s['ix_pages']+16384+8),('wrong_vstart',s['ix_records']+56),
                      ('invalid_tval',s['ix_records']+16),('mask_byte',s['ix_mask']),
                      ('index_buffer',s['ix_indices'])]:
        c,r=copy.deepcopy(last_checkpoint); c.mem[addr]^=1
        reject(name,lambda: c.row(r))
    for name,symbol in [('missing_magic','ix_completed'),('error','ix_errors'),('casecount','ix_cases_done')]:
        c=copy.deepcopy(checker); c.mem[s[symbol]]^=1
        reject(name,c.finish)
    c=copy.deepcopy(checker); c.actions[cases[-1]['trial']].remove('target')
    reject('missing_target',c.finish)
    c=copy.deepcopy(checker); c.calls-=1
    reject('missing_comparison',c.finish)
    c=copy.deepcopy(check_state); c.regs[12]^=1
    reject('first_mismatch',c.compare_call)
    c=copy.deepcopy(check_state); c.regs[12]^=1; c.regs[13]^=1
    reject('equal_but_wrong_reference_want',c.compare_call)
    save(out/'status.json',dict(status='HOST_SPIKE_DERIVED_CSV_CHECKER_PASS_NOT_DUT',positive=positive,
             negatives_rejected=negatives,reference=str(directory),reference_sha256=ref.base.sha(directory/'status.json'),
             pins={str(p):ref.base.sha(p) for p in [Path(__file__),Path(oracle.__file__),Path(ref.__file__)]}))
    print('HOST_SPIKE_DERIVED_CSV_CHECKER_PASS_NOT_DUT',positive['checks'],len(negatives),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); exercise(a.reference.resolve(),a.out.resolve())
