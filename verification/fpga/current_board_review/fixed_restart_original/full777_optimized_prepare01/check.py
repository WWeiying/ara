#!/usr/bin/env python3
"""Lossless scalar-retirement observer; Spike bridge is not an RVFI DUT run."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
P = HERE / 'prepared01'
REGS = ('zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6').split()
R = {x:i for i,x in enumerate(REGS)}
MASK64 = (1 << 64)-1
FIELDS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')


def require(ok, message):
    if not ok: raise AssertionError(message)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def verify():
    pins = read(P/'input_pins.json')
    for path, digest in pins.items(): require(sha(path)==digest, 'Input drift '+path)
    status = read(P/'reference01/status.json')
    require(status['actual_returncode'] == 0 and status['status']=='SPIKE_PASS_NOT_DUT', 'Reference prerequisite')
    require(sha(P/'reference01/spike.log')==status['log_sha256'], 'Reference raw hash')
    return len(pins)


class Observer:
    def __init__(self, backend):
        self.backend = backend
        self.sym = read(P/backend/'symbols.json')
        self.calls = read(P/'calls.json')
        self.identity = read(P/'code_identity.json')[backend]
        dis = (P/backend/'fixed_e8_m4_prefix777.dis').read_text()
        self.code = {int(m[1],16):(int(m[2],16),m[3].split('#')[0].strip()) for m in
                     re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+(.+)$',dis,re.M)}
        self.reg = [0]*32
        self.known = {0}
        self.shadow = {name:bytearray(n) for name,n in (('a',512),('b',512),('mask',128),('out',514))}
        self.helper = self.identity['helper24']
        self.helper_pcs = {i['pc'] for i in self.helper}
        self.init_pcs = {i['pc'] for i in self.identity['full_init']}
        self.oracle_pcs = {i['pc'] for i in self.identity['full_oracle']}
        self.n = self.hindex = self.retired = self.reads = self.total_reads = self.exits = self.targets = 0
        self.in_helper = self.pending = self.in_oracle = False
        self.init_seen = set()
        self.saved = []
        self.first_error = None
        self.returned_vstart = self.returned_sat = self.restores = self.capacities = 0
        self.contexts = []
        self.input_stores = []
        state = 0x937ad68de41c725f
        for i in range(512):
            state ^= (state<<13)&MASK64; state ^= state>>7; state ^= (state<<17)&MASK64
            self.input_stores += [('b',i,(state>>19)&255),('a',i,state&255)]
            if i%8==0: self.input_stores += [('a',i,0),('b',i,0)]
            elif i%8==1: self.input_stores += [('a',i,255),('b',i,1)]
            elif i%8==2: self.input_stores += [('a',i,128),('b',i,255)]
            elif i%8==3: self.input_stores += [('b',i,8)]
        self.input_store_count = self.mask_store_count = self.total_mask_stores = 0
        self.rvfi_checks = self.ctrl_exits = 0

    def get(self, register):
        require(register in self.known, 'Unknown scalar operand x'+str(register))
        return self.reg[register]

    def mask_stores(self):
        row=self.calls[self.n]; values=bytearray(128)
        stores=[(i,0) for i in range(128)]
        for i in range(512):
            mode=row['mask']
            if mode==0 or mode==1 and i%2 or mode==2 and i%7==2:
                values[i//8] |= 1<<(i%8)
                stores.append((i//8,values[i//8]))
        return stores

    def feed(self, pc, insn, rd, value, rvfi=None):
        self.retired += 1
        if pc < 0x80000000:
            require(self.n == 0, 'Unexpected late boot execution')
            if rd: self.reg[rd]=value; self.known.add(rd)
            return
        require(pc in self.code and self.code[pc][0]==insn, f'Actual PC/opcode mismatch {pc:x}')
        asm = self.code[pc][1]
        op = asm.split()[0]
        require(not (self.sym['op_1'] <= pc < self.sym['main']), 'Unused helper full range executed')
        require(not (self.sym['failure'] <= pc < self.sym['fixed_main']), 'Original oracle first failure')
        require(not (self.sym['trap_entry'] <= pc < self.sym['replay_exit']), 'Unexpected trap')
        if pc == self.sym['capacity']:
            require(self.capacities == 0, 'Capacity bootstrap entry')
        if op == 'vsetvli' and pc not in self.helper_pcs:
            require(self.sym['capacity'] <= pc < self.sym['op_0'] and self.get(5)==MASK64 and rd==10 and value==512, 'Capacity bootstrap result')
            self.capacities += 1
        if op.startswith('v'):
            require(pc in self.helper_pcs or self.sym['capacity'] <= pc < self.sym['op_0'], 'Extra vector execution')
        if pc == self.sym['full_init']:
            require(not self.in_helper and not self.pending and not self.in_oracle and self.n<777, 'Init ordering')
            self.init_seen=set()
        if pc == self.helper[0]['pc']:
            require(not self.in_helper and not self.pending and self.n<777 and self.init_seen==set(range(514)), 'Missing full initialization/history')
            row = self.calls[self.n]
            require([self.get(i) for i in range(10,18)] == [self.sym['a'],self.sym['b'],self.sym['out']+1,row['vl'],512,
                                       self.sym['mask'],row['vstart'],row['control']], 'Helper argument context')
            require(self.input_store_count==len(self.input_stores), 'Missing original RNG input stores')
            require(self.mask_store_count==(len(self.mask_stores()) if self.n%32==0 else 0), 'Missing/extra original128 mask setup')
            self.mask_store_count=0
            for name in ('a','b','mask'):
                require(self.shadow[name].hex()==row[name+'_hex'], 'Original full input '+name)
            require(self.shadow['out']==bytes([0x5b])*514, 'Original full oldvd/guards')
            self.in_helper=True; self.hindex=0; self.saved=[]
        if self.in_helper:
            row = self.calls[self.n]; index = self.hindex
            require(pc==self.helper[index]['pc'] and insn==self.helper[index]['insn'], 'Noncontiguous24 helper')
            if index in (0,5,21): require(rd==5 and value==(row['vl'] if index==5 else 512), 'Helper VL')
            if index==7: require(self.get(16)==row['vstart'], 'vstart setup')
            if index in (8,9):
                require(rd==(29 if index==8 else 30), 'Saved CSR destination')
                self.saved.append(value)
            if index==11: require(self.get(7)==row['vxrm'], 'vxrm setup')
            if index==13: require(self.get(7)==row['initial_vxsat'], 'vxsat setup')
            if index==14: self.targets+=1
            if index==15:
                require(rd==10 and value==0,'Returned vstart'); self.returned_vstart+=1
            if index==16:
                require(rd==6 and value==row['expected_vxsat'],'Returned vxsat'); self.returned_sat+=1
            if index in (19,20):
                require(self.get(29 if index==19 else 30)==self.saved[index-19], 'Saved CSR restore operand')
                self.restores+=1
            self.hindex+=1
            if self.hindex==24:
                self.in_helper=False; self.pending=True
        else:
            require(pc not in self.helper_pcs, 'Helper middle entry')
        if pc == self.sym['full_oracle']:
            require(self.pending and not self.in_oracle and self.get(10)==self.n, 'Full oracle call index/order')
            self.in_oracle=True; self.reads=0
        mem = re.fullmatch(r'(lbu|lhu|lw|lwu|ld|sb|sh|sw|sd)\s+(\w+),(-?(?:0x[0-9a-f]+|[0-9]+))\((\w+)\)',asm)
        if mem:
            kind, regname, offset, base = mem.groups()
            size = {'lbu':1,'lhu':2,'lw':4,'lwu':4,'ld':8,'sb':1,'sh':2,'sw':4,'sd':8}[kind]
            address = (self.get(R[base])+int(offset,0)) & MASK64
            watched = any(self.sym[name]<=address<self.sym[name]+len(data) for name,data in self.shadow.items())
            relevant = watched or address==0xd0000000
            if rvfi is not None and relevant:
                a,rm,wm,wd=(int(rvfi[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
                require(address%8+size<=8 and a==address, 'Actual RVFI memory address')
                be=((1<<size)-1)<<(address%8)
                require((rm,wm)==((0,be) if kind.startswith('s') else (be,0)), 'Actual RVFI memory byte enables')
                if kind.startswith('s'):
                    require(wd&((1<<(8*size))-1)==self.get(R[regname])&((1<<(8*size))-1), 'Actual RVFI store data')
                self.rvfi_checks+=1
            if kind.startswith('s'):
                if not relevant:
                    if rd: self.reg[rd]=value; self.known.add(rd)
                    return
                data = (self.get(R[regname]) & ((1<<(8*size))-1)).to_bytes(size,'little')
                if address==0xd0000000:
                    require(self.exits==1 and size==8 and int.from_bytes(data,'little')==0, 'Actual CTRL exit store')
                    self.ctrl_exits+=1
                for name, shadow in self.shadow.items():
                    pos = address-self.sym[name]
                    if 0<=pos<len(shadow) and self.sym['fixed_main']<=pc<self.sym['capacity']:
                        require(size==1,'Original scalar setup width')
                        if name in ('a','b'):
                            require(self.n==0 and self.input_store_count<len(self.input_stores) and
                                    (name,pos,data[0])==self.input_stores[self.input_store_count], 'Exact RNG store sequence')
                            self.input_store_count+=1
                        elif name=='mask':
                            stores=self.mask_stores()
                            require(self.n%32==0 and self.mask_store_count<len(stores) and
                                    (pos,data[0])==stores[self.mask_store_count], 'Exact original mask reset/update sequence')
                            self.mask_store_count+=1; self.total_mask_stores+=1
                    for i, byte in enumerate(data):
                        if 0<=pos+i<len(shadow):
                            shadow[pos+i]=byte
                            if name=='out' and pc in self.init_pcs: self.init_seen.add(pos+i)
            elif pc in self.oracle_pcs and self.sym['out']<=address<self.sym['out']+514:
                require(self.in_oracle and self.reads<66, 'Extra oracle read')
                offset = self.reads*8 if self.reads<64 else 512+self.reads-64
                width = 8 if self.reads<64 else 1
                require(address==self.sym['out']+offset and size==width and rd==R[regname], 'Full oracle load coverage/order')
                expected = bytes.fromhex(self.calls[self.n]['expected_hex'])
                require(value==int.from_bytes(expected[offset:offset+size],'little'),f'Original oracle call{self.n} offset{offset}')
                self.reads+=1; self.total_reads+=1
        if pc in self.oracle_pcs and op=='ret':
            require(self.in_oracle and self.reads==66 and self.get(10)==0, 'Incomplete/nonzero full oracle')
            self.contexts.append(dict(trial=self.n,reads=self.reads,saved_vxrm=self.saved[0],saved_vxsat=self.saved[1]))
            self.n+=1; self.pending=False; self.in_oracle=False
        if pc==self.sym['replay_exit']:
            require(self.n==777 and self.get(10)==0 and self.exits==0, 'Full scope normal exit')
            self.exits+=1
        if rd: self.reg[rd]=value; self.known.add(rd)

    def finish(self):
        require(self.n==self.targets==self.returned_vstart==self.returned_sat==777 and self.restores==1554 and
                self.total_reads==51282 and self.exits==1 and self.capacities==1 and
                not (self.in_helper or self.pending or self.in_oracle), 'Incomplete full777 observation')
        require(self.input_store_count==1472 and self.total_mask_stores==8758, 'Full setup store totals')
        if self.backend=='soc': require(self.ctrl_exits==1 and self.rvfi_checks>100000, 'Actual RVFI setup/oracle/exit missing')
        return dict(status='FULL777_ARCHITECTURAL_DATA_PASS',backend=self.backend,retired=self.retired,
                    calls=self.n,result_bytes=397824,guard_bytes=1554,full_oracle_loads=self.total_reads,
                    helper_instructions=24*777,original_input_bytes_per_call=512+512+128+514,
                    returned_vstart=self.returned_vstart,returned_vxsat=self.returned_sat,
                    saved_CSR_restore_operands=self.restores,unused_helpers=0,no_added_vector=True,
                    original_rng_stores=self.input_store_count,mask_stores=self.total_mask_stores,
                    rvfi_memory_checks=self.rvfi_checks,actual_CTRL_exits=self.ctrl_exits,
                    unknown_registers_assumed_zero=False,final_CSR_readback=False,original_Linux_replay=False)


def bridge():
    observer = Observer('spike')
    commit = re.compile(r'^core\s+0: 3 0x([0-9a-f]+) \(0x([0-9a-f]+)\)(.*)$')
    with (P/'reference01/spike.log').open() as stream:
        for line in stream:
            match = commit.match(line)
            if not match: continue
            rd = re.search(r'\bx(\d+)\s+0x([0-9a-f]+)',match[3])
            observer.feed(int(match[1],16),int(match[2],16),int(rd[1]) if rd else 0,int(rd[2],16) if rd else 0)
    return observer.finish()


def vector_instruction(insn):
    opcode, f = insn&127, (insn>>12)&7
    return opcode==0x57 or (opcode in (7,0x27) and f in (0,5,6,7)) or (
        opcode==0x73 and f!=0 and insn>>20 in (8,9,10,15,0xc20,0xc21,0xc22))


class Lifecycle:
    def __init__(self):
        self.arch=[]; self.requests=[]; self.retired=[]; self.pending={}; self.uops={}
        self.arch_meta={}; self.responses=self.allocations=self.done=0
        self.allocated_owners=set()

    def row(self,row):
        event=row['event']; insn=int(row['insn'],16); trans=int(row['trans_id'])
        order=int(row['order']); vid=int(row['port'])
        require(int(row['trap'],0)==0,'CVX/retire exception veto')
        if event=='retire':
            if vector_instruction(insn): self.retired.append(insn)
        elif event=='arch_start':
            require(order==len(self.arch) and vector_instruction(insn),'Architectural request sequence')
            self.arch_meta[order]=(trans,insn); self.arch.append(insn)
        elif event=='cvx_req':
            require(trans not in self.pending and len(self.requests)<len(self.arch) and
                    (trans,insn)==self.arch_meta[len(self.requests)],'CVX request ownership/order')
            self.pending[trans]=insn; self.requests.append(insn)
        elif event=='cvx_resp':
            require(trans in self.pending,'CVX response without actual request')
            del self.pending[trans]; self.responses+=1
        elif event=='uop_alloc':
            require(vid not in self.uops and self.arch_meta.get(order)==(trans,insn),'Backend allocation ownership')
            self.uops[vid]=(order,trans,insn); self.allocations+=1
            self.allocated_owners.add(order)
        elif event=='uop_done':
            require(self.uops.get(vid)==(order,trans,insn),'Backend completion ownership')
            del self.uops[vid]; self.done+=1
        else: require(False,'Unknown CSV event '+event)

    def finish(self):
        memory_owners={order for order,insn in enumerate(self.arch) if insn&127 in (7,0x27)}
        require(len(memory_owners)==777*5 and memory_owners<=self.allocated_owners,
                'Missing required full-capacity load/mask/store backend owner')
        require(self.retired==self.requests==self.arch and len(self.requests)==self.responses and
                not self.pending and not self.uops and self.allocations==self.done and self.done>=777*5,
                'Incomplete/nonmatching CVX/uop lifecycle')
        return dict(cvx_requests=len(self.requests),cvx_responses=self.responses,backend_alloc=self.allocations,
                    backend_done=self.done,required_memory_owners=len(memory_owners),
                    architectural_requests=len(self.arch),replays=0,exceptions=0)


def csv_check(path):
    observer = Observer('soc'); count=0; cycle=-1; rows=0
    life=Lifecycle()
    with Path(path).open() as stream:
        reader=csv.DictReader(stream)
        require(reader.fieldnames==FIELDS,'Exact M8 CSV header')
        for row in reader:
            rows+=1
            require(set(row)==set(FIELDS) and None not in row.values(),'Truncated/malformed row')
            require(int(row['cycle'])>=cycle,'Nonmonotonic cycle'); cycle=int(row['cycle'])
            life.row(row)
            if row['event']!='retire': continue
            require(int(row['order'])==count and int(row['trap'],0)==0,'Retire order/trap')
            count+=1
            observer.feed(int(row['pc'],16),int(row['insn'],16),int(row['rd']),int(row['rd_wdata'],16),row)
    return dict(observer.finish(), csv_rows=rows,last_cycle=cycle,lifecycle=life.finish())


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=['bridge','csv'])
    parser.add_argument('--csv',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    require(not args.out.exists(),'Exclusive output')
    before=verify()
    result=bridge() if args.mode=='bridge' else csv_check(args.csv)
    result.update(input_pins=before,pins_unchanged=(verify()==before),DUT_executed=False if args.mode=='bridge' else None)
    with args.out.open('x') as stream: json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps(result,indent=2))
