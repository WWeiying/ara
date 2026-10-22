"""Grouped RVFI observer using actual scalar loads, never expected vector payloads."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('remaining38_oracle', HERE.parent/'checker02.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
require = o.require
FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
CSR_FIELDS = {0x342:0,0x341:1,0x343:2,0x300:3,0x180:4,0xc20:5,0xc21:6,8:7,3:8,15:9}


def memory_op(insn):
    if insn&3 != 3:
        return o.old.decoder.decode(insn)
    op, f = insn&127, (insn>>12)&7
    if op not in (3,35):
        return None
    write = op == 35
    imm = ((insn>>25)<<5)|((insn>>7)&31) if write else insn>>20
    if imm&2048:
        imm -= 4096
    return dict(kind='write' if write else 'read',size=1<<(f if write else f&3),
                base=(insn>>15)&31,register=(insn>>20)&31 if write else (insn>>7)&31,
                offset=imm,signed=not write and f<4)


def rvv(insn):
    return insn&127 == 0x57 or (insn&127 in (7,39) and (insn>>12)&7 in (0,5,6,7))


class Checker:
    def __init__(self, group):
        self.group = Path(group)
        self.s = json.loads((self.group/'soc.symbols.json').read_text())
        self.code = o.disassemble((self.group/'soc.dis').read_text())
        self.cases = [c['parameters'] for c in json.loads((self.group/'cases.json').read_text())]
        self.mem = o.elf_bytes(self.group/'soc.elf')
        self.regs = {i:0 for i in range(32)}
        self.csr = {}
        self.expected_counts, self.final_checks = o.check_counts(self.cases)
        self.helpers = {i:o.window(self.code,self.s[f'replay_{i}'],10) for i in (0,1)}
        self.capacity = o.window(self.code,self.s['capacity'],3)
        self.vector_counts = {p:0 for p,i in self.code.items() if rvv(i)}
        self.snapshot = {p for p in self.vector_counts if self.s['mx_snapshot']<=p<self.s['mx_handler']}
        self.entry = {p for p in self.vector_counts if self.s['mx_s_entry']<=p<self.s['mx_call_store']}
        self.retry = {p for p in self.vector_counts if self.s['mx_handler']<=p<self.s['mx_return_m']}
        self.restore = {p for p in self.vector_counts if self.code[p]&0xfe007fff == 0x80007057}
        known = set().union(*map(set,self.helpers.values()),set(self.capacity),self.snapshot,self.entry,self.retry,self.restore)
        require(set(self.vector_counts)<=known and len(self.snapshot)==4 and len(self.entry)==3 and
                len(self.retry)==len(self.restore)==1, 'Static RVV ownership')
        require(all(self.code[p]==0x0082f2d7 for p in self.retry), 'Retry VSET encoding')
        self.items = [dict(actions=[],helper=[],capacity=[],checkpoints=[],traps=[],mrets=[],
                           memory_reads=[],outputs=[],snapshots=[],refills=[],cvx_faults=[]) for _ in self.cases]
        self.rows = self.retired = self.checks = self.parks = 0
        self.last_cycle = -1
        self.cvx = {}
        self.ctrl = []
        self.capture = None
        self.suspended = False
        self.refill = None
        self.memory_phase = None
        self.exit_seen = False

    def u64(self, name):
        return o.readint(self.mem,self.s[name])

    def current(self):
        if not all(self.s['mx_case']+i in self.mem for i in range(8)):
            return 0
        return self.u64('mx_case')

    def forget(self, address, size):
        for i in range(size):
            self.mem.pop(address+i,None)

    def target_store(self, c):
        t = self.cases[c]
        if t['store']:
            g = o.geom(t)
            for i in g['active']:
                self.forget(self.s['mx_pages']+g['base']+i*g['stride'],2)

    def scalar(self, r, insn, trap, item):
        a,rm,wm,value = (int(r[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        if not (rm or wm):
            return
        require(not trap and not (rm and wm), 'Faulting/bidirectional scalar memory')
        d = memory_op(insn)
        require(d is not None, 'Non-scalar RVFI byte enables')
        width = d['size']
        require(width in (1,2,4,8) and a%8+width<=8, 'Scalar width/alignment')
        require(a==(self.regs[d['base']]+d['offset'])&o.U64 and
                (wm or rm)==((1<<width)-1)<<(a%8), 'Scalar address/BE')
        bits = (1<<(width*8))-1
        if wm:
            require(d['kind']=='write' and value&bits==self.regs[d['register']]&bits, 'Store source')
            value &= bits
            if self.refill is not None:
                require(width==2 and a==self.s['mx_pages']+2*self.refill and value==o.orig(self.refill),
                        'Refill actual address/value/order')
                self.refill += 1
            if a in (self.s['mx_errors'],self.s['mx_unexpected']):
                require(value==0, 'Nonzero firmware error')
            if a==0xd0000000:
                require(int(r['pc'],16)==self.s['replay_exit']+10 and width==8 and value==0 and self.u64('mx_completed')==o.DONE,
                        'Actual CTRL0/completion')
                self.ctrl.append(value)
                self.exit_seen = True
        else:
            rd,raw = int(r['rd']),int(r['rd_wdata'],16)
            require(d['kind']=='read' and rd==d['register'] and rd!=0, 'Load destination')
            value = raw&bits
            want = value|((o.U64^bits) if d.get('signed',width==4) and value>>(width*8-1) else 0)
            require(raw==want, 'Load extension')
            for j,b in enumerate(value.to_bytes(width,'little')):
                require(a+j not in self.mem or self.mem[a+j]==b, f'Actual scalar load mismatch {a+j:x}')
            if item is not None and self.memory_phase is not None and self.s['mx_pages']<=a<self.s['mx_pages']+8192:
                require(width==2,'Memory oracle width')
                item['memory_reads'].append(a)
            if item is not None and len(item['helper'])>=10 and self.s['mx_out']<=a<self.s['mx_out']+260:
                require(width==2,'Output oracle width')
                item['outputs'].append(a)
        for j,b in enumerate(value.to_bytes(width,'little')):
            self.mem[a+j] = b

    def row(self, r):
        require(set(r)==set(FIELDS) and None not in r.values(),'Malformed CSV')
        self.rows += 1
        cycle = int(r['cycle'])
        require(cycle>=self.last_cycle,'Cycle reversal')
        self.last_cycle = cycle
        event,insn = r['event'],int(r['insn'],16)
        c = self.current()
        item = self.items[c] if c<len(self.items) else None
        t = self.cases[c] if item is not None else None
        g = o.geom(t) if t else None
        if event=='cvx_req':
            tid = int(r['trans_id'])
            require(tid not in self.cvx,'Repeated CVX transaction')
            self.cvx[tid] = insn
        if event=='cvx_resp':
            tid = int(r['trans_id'])
            require(tid in self.cvx,'Unowned CVX response')
            op = self.cvx.pop(tid)
            if int(r['trap']):
                require(item is not None and g['fault'] and not item['cvx_faults'] and
                        op==self.code[self.s[f'fault_{t["store"]}_pc']], 'Wrong CVX exception')
                item['cvx_faults'].append(dict(cycle=cycle,insn=hex(op)))
                self.target_store(c)
        require(event in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'), 'Unknown event')
        if event!='retire':
            return
        require(int(r['order'])==self.retired,'Retirement order gap')
        self.retired += 1
        pc,rd,val,trap = int(r['pc'],16),int(r['rd']),int(r['rd_wdata'],16),int(r['trap'])
        require(self.code.get(pc)==insn,'Actual PC/ELF encoding')
        require(pc not in (self.s['trap_entry'],self.s['replay_mismatch']),'Default trap/mismatch')
        if self.exit_seen:
            require(pc==self.s['replay_exit']+14 and insn==0xa001 and rd==0 and not trap and
                    int(r['mem_rmask'],16)==int(r['mem_wmask'],16)==0, 'Postexit side effect')
            self.parks += 1
            return
        require(not trap or (item is not None and pc in (self.s[f'fault_{t["store"]}_pc'],self.s['mx_ecall'])),
                'Unexpected trap retirement')
        if pc in self.vector_counts:
            self.vector_counts[pc] += 1
        if self.refill is not None and not self.s['mx_refill_page']<=pc<self.s['mx_repair']:
            require(self.refill==2048 and item is not None,'Incomplete refill')
            item['refills'].append(self.refill)
            self.refill = None
        if pc==self.s['check']:
            require(self.regs[10]==self.regs[11],f'case{c} scalar comparison {self.checks+1}')
            self.checks += 1
        if pc==self.s['check_memory']:
            require(item is not None and self.regs[10]==len(item['checkpoints']),'Memory phase')
            self.memory_phase = self.regs[10]
            item['memory_reads'] = []
        if pc in self.capacity:
            require(item is not None and pc==self.capacity[len(item['capacity'])] and not item['helper'], 'Capacity order')
            if pc==self.capacity[1]:
                require(rd==10 and val==64,'Actual VLMAX64')
            item['capacity'].append(pc)
        if pc==self.s['mx_handler']:
            require(item is not None,'Handler outside cases')
            isfault = g['fault'] and not item['traps']
            require(len(item['traps'])<1+int(g['fault']),'Extra handler')
            if isfault:
                require(len(item['cvx_faults'])==1 and item['helper']==self.helpers[t['store']][:5], 'Fault position')
                self.suspended = True
            else:
                require(item['helper']==self.helpers[t['store']], 'Completion handler before helper')
            item['actions'].append('fault' if isfault else 'ecall')
            self.capture = {}
            item['traps'].append(self.capture)
        if any(pc in w for w in self.helpers.values()):
            require(item is not None and pc in self.helpers[t['store']] and not self.suspended,'Wrong helper/owner')
            w = self.helpers[t['store']]
            i = len(item['helper'])
            require(i<10 and pc==w[i] and item['capacity']==self.capacity,'Original helper order')
            if i==0:
                require(item['actions']==['checkpoint0'] and
                        [self.regs[j] for j in range(10,16)]==[o.VA+g['base'],self.s['mx_input'],self.s['mx_out']+2,self.s['mx_mask'],64,self.s['mx_stride']], 'Helper arguments/window')
            if i in (0,4,7):
                require(rd==5 and val==(8 if i==4 else 64),'Helper VSET result')
            if i==5:
                require(self.regs[10]==o.VA+g['base'] and self.regs[28]==g['stride']&o.U64 and
                        self.csr.get(0xc20)==8 and self.csr.get(0xc21)==8 and
                        self.csr.get(8)==(g['start'] if item['mrets'] else 0), 'Target original registers/CSRs')
                if trap:
                    require(g['fault'] and not item['mrets'],'Duplicate target trap')
                    return
                require(len(item['mrets'])==int(g['fault']),'Missing fault/retry')
                self.target_store(c)
                item['actions'].append('target')
            if i==6:
                require(rd==10 and val==0,'Returned vstart')
            item['helper'].append(pc)
        if insn&127==0x73 and (insn>>12)&7:
            k,f,src = insn>>20,(insn>>12)&7,(insn>>15)&31
            writing = f in (1,5) or src!=0
            if self.s['mx_trap']<=pc<self.s['main'] and k in CSR_FIELDS and rd and f==2 and src==0:
                require(self.capture is not None and CSR_FIELDS[k] not in self.capture,'Duplicate/unowned trap CSR')
                self.capture[CSR_FIELDS[k]] = val
            if not writing:
                if rd:
                    self.csr[k] = val
            else:
                value,old = src if f>=5 else self.regs[src],self.csr.get(k,0)
                self.csr[k] = value if f in (1,5) else old|value if f in (2,6) else old&~value
                require(not (k==0x341 and self.suspended),'Fault mepc overwritten')
        if insn&0x707f==0x7057:
            self.csr[0xc21] = (insn>>20)&1023 if insn>>30==3 else (insn>>20)&2047 if insn>>31==0 else self.regs[(insn>>20)&31]
            self.csr[0xc20] = val if rd else self.regs[(insn>>15)&31]
            self.csr[8] = 0
        if pc in self.retry:
            require(item is not None and g['fault'] and self.suspended and self.u64('mx_phase')==2 and
                    self.u64('mx_marker')==0 and rd==5 and val==8,'Retry VSET owner/window/result')
        if pc==self.s['mx_repair_sfence']:
            require(item is not None and item['actions'][-1:]==['checkpoint1'] and self.regs[(insn>>15)&31]==o.VA,
                    'Repair ordering/address')
            item['actions'].append('repair_sfence')
        if pc==self.s['mx_refill_page']:
            require(item is not None and t['unmapped'] and item['actions'][-1:]==['repair_sfence'],'u0/early refill')
            item['actions'].append('refill')
            self.refill = 0
        if pc==self.s['mx_trap_mret']:
            require(item is not None and self.capture is not None and len(self.capture)==10,'Incomplete trap CSR record')
            if self.u64('mx_marker')==0:
                require(g['fault'] and self.suspended and item['actions'][-1:]==['checkpoint2'],'Early retry')
                o.retry_context(self.s,t,self.regs,self.csr)
                item['mrets'].append(dict(cycle=cycle,mepc=self.csr[0x341],vstart=self.csr[8]))
                item['actions'].append('retry_mret')
                self.suspended = False
        if pc==self.s['mx_younger_store']:
            require(item is not None,'Younger store outside cases')
            item['actions'].append('younger')
        if insn&0x707f==0x5027 and pc not in (self.s['fault_0_pc'],self.s['fault_1_pc']):
            require(item is not None,'Snapshot outside cases')
            a = self.regs[(insn>>15)&31]
            valid = [self.s['mx_out']+2]+[self.s[n]+64+128*j for n in ('mx_fault','mx_result') for j in range(3)]
            require(a in valid,'Unexpected vector destination')
            self.forget(a,128)
            item['snapshots'].append(a)
        if pc==self.s['mx_checkpoint']:
            require(item is not None,'Checkpoint outside cases')
            phase = self.u64('mx_phase')
            require(phase==len(item['checkpoints'])==self.memory_phase,'Checkpoint order')
            require(item['memory_reads']==[self.s['mx_pages']+2*i for i in range(4096)],'Incomplete full memory reads')
            checked = o.compare(self.mem,self.s,t,phase,c)
            require(self.checks==self.u64('mx_checks')==self.expected_counts[c,phase],'Independent check count')
            n = 1+int(g['fault']) if phase==3 or (phase and not g['fault']) else int(phase>0)
            require(len(item['traps'])==n,'Trap count at checkpoint')
            for j in range(n):
                require(item['traps'][j]=={k:o.readint(self.mem,self.s['mx_records']+96*j+8*k) for k in range(10)},'Actual CSR reads vs stored context')
            item['checkpoints'].append(dict(phase=phase,cycle=cycle,checks=self.checks,**checked))
            item['actions'].append('checkpoint'+str(phase))
            self.memory_phase = None
        self.scalar(r,insn,trap,item)
        if rd and not trap:
            self.regs[rd] = val
        self.regs[0] = 0

    def finish(self):
        for c,t in enumerate(self.cases):
            item,g = self.items[c],o.geom(t)
            require(item['actions']==o.expected_actions(t),f'case{c} exact action sequence')
            require(item['helper']==self.helpers[t['store']] and item['capacity']==self.capacity,'Full original helper')
            require(len(item['mrets'])==len(item['cvx_faults'])==int(g['fault']),'Fault/retry count')
            require(item['refills']==([2048] if t['unmapped'] else []),'Actual refill count')
            require(item['outputs']==[self.s['mx_out']+2*i for i in list(range(1,65))+[0,65]+list(range(66,130))], 'Full64 output/guards/extra storage')
            require(len(item['checkpoints'])==4,'All phases')
        for p in self.snapshot:
            require(self.vector_counts[p]==sum(1+o.geom(t)['fault'] for t in self.cases),'Snapshot RVV count')
        for p in self.entry:
            require(self.vector_counts[p]==len(self.cases),'Entry RVV count')
        for p in self.restore:
            require(self.vector_counts[p]==1,'Restore RVV count')
        for p in self.retry:
            require(self.vector_counts[p]==sum(o.geom(t)['fault'] for t in self.cases),'Retry RVV count')
        require(self.checks==self.u64('mx_checks')==self.final_checks and self.u64('mx_completed')==o.DONE and
                self.u64('mx_cases_done')==len(self.cases) and self.u64('mx_errors')==self.u64('mx_unexpected')==0,
                'Final completion/counts/errors')
        require(self.ctrl==[0] and not self.cvx and not self.suspended and self.refill is None,'CTRL/CVX terminal')
        return dict(status='PASS_M6_NEGATIVE_STRIDE_GROUP_NOT_LINUX',cases=len(self.cases),checks=self.checks,
                    rows=self.rows,retired=self.retired,last_cycle=self.last_cycle,case_evidence=self.items,
                    ctrl=self.ctrl,vector_pc_counts={hex(p):n for p,n in self.vector_counts.items()},
                    vector_evidence='Actual scalar loads after original vector stores, not invented vector payloads')


def analyze(path, group):
    checker = Checker(group)
    with Path(path).open() as f:
        rows = csv.DictReader(f)
        require(rows.fieldnames==FIELDS,'CSV header')
        for row in rows:
            checker.row(row)
    return checker.finish()


if __name__=='__main__':
    p = argparse.ArgumentParser()
    p.add_argument('group',type=Path)
    p.add_argument('csv',type=Path)
    p.add_argument('out',type=Path)
    a = p.parse_args()
    try:
        result = analyze(a.csv,a.group)
    except Exception as e:
        result = dict(status='NOT_ACCEPTED',error=f'{type(e).__name__}: {e}')
    with a.out.open('x') as f:
        json.dump(result,f,indent=2)
        f.write('\n')
    print(result['status'])
    raise SystemExit(int(result['status']=='NOT_ACCEPTED'))
