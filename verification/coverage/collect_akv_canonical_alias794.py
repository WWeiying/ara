"""Independent native alias model and terminal collector; no custom Spike claim."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import shlex
import time
from types import FunctionType

import preflight_akv_canonical_alias794 as case
import collect_akv_entropy as old
import collect_akv_tile_range_capture as tile

life, require = old.life, case.require
SCOPE = case.old.SCOPE
WIDTHS = dict(clk_i=1, rst_ni=1, command_fire=1, command_i=3,
    command_id_i=3, command_vd_i=5, command_selector_i=64, command_descriptor_address_i=64,
    command_tile_start_i=64, fault_valid_o=1, success_valid_o=1,
    context_ready_o=1, read_range_fire=1, read_range_vaddr=64,
    read_range_bytes=16, read_range_tag=8, axi_ar_valid_o=1, axi_ar_ready_i=1)
WIDTHS.update({'i_read_engine.'+k:w for k,w in dict(en_ld_st_translation_i=1,
    mmu_req_o=1, mmu_valid_i=1, mmu_exception_valid_i=1, mmu_vaddr_o=64,
    mmu_paddr_i=56, translation_complete=1, plan_state_q=2,
    ar_addr_q=64, ar_cursor_vaddr_q=64, ar_chunk_bytes_q=16).items()})


class Model(old.isa.Model):
    def __init__(self, blob, symbols):
        old.isa.base.Model.__init__(self, blob, symbols)
        self.csr[0x180] = 0
        self.priv = 3
        self.requests = []
        self.walks = []
        for i,w in enumerate(case.WORDS):
            require(case.elf_bytes(blob, symbols['akva_site_'+str(i)], 4)==w.to_bytes(4,'little'),
                    'Exact native custom sites')

    def csr_write(self, address, value):
        if address == 0x180:
            require(value in (0,(8<<60)|(self.symbols['akva_root']>>12)), 'Exact SATP roots')
        elif address == 0x300:
            allowed = 0xa00000000 | (1<<63) | 0x6600 | 0x1800 | 0x88
            require(value & ~allowed == 0 and value & 0xa00000000 == 0xa00000000
                    and value>>11&3 in (0,1,3), 'Scoped MSTATUS legal bits')
        elif address in (0x341,0x342,0x343):
            # The pinned program saves/restores reset CSRs and records two S traps.
            require(value in (0,self.symbols['akva_s_entry'],self.symbols['akva_resume'])
                    if address == 0x341 else value == 0, 'Scoped trap CSR restore/return')
        else:
            return super().csr_write(address,value)
        self.csr[address] = value & old.isa.MASK

    def vector(self, word):
        op, reg, rs1 = word&127, word>>7&31, word>>15&31
        if op == 0x57:
            return old.isa.base.Model.vector(self, word)
        require(word & ~(31<<15|31<<7) == (0x02005007 if op==7 else 0x02005027)
                and (self.csr[8],self.csr[0xc20],self.csr[0xc21]) == (0,64,8), 'Exact vector shape')
        address = self.gpr[rs1]
        if op == 7:
            require(reg == self.counts['vload'] < 32 and
                    address == self.symbols['entropy_seed']+64+128*reg, 'Seed PC/register/address order')
            data = self.read(address,128)
            require(data == case.old.frame(0)[64+reg*128:64+(reg+1)*128], 'Independent seed bytes')
            self.vrf[reg] = bytearray(data)
            self.vector_effects.append(dict(kind='seed',vd=reg,data=data.hex(),pc=self.pc,word=word))
            self.counts['vload'] += 1
        else:
            phase, r = divmod(self.counts['vstore'],32)
            require(phase<4 and reg==r and len(self.commands)==(1,5,6,10)[phase]
                    and address==self.symbols['entropy_snapshots']+phase*4224+64+reg*128,
                    'Four full snapshot register/address/command boundaries')
            data = bytes(self.vrf[reg])
            require(data==case.frame(phase)[64+reg*128:64+(reg+1)*128], 'Full VRF oracle')
            self.write(address,data); self.counts['vstore'] += 1
        self.dirty(True)

    def custom(self, word):
        n = len(self.commands); phase, site = divmod(n,5)
        require(n<10 and self.priv==1 and word==case.WORDS[site]
                and self.pc==self.symbols['akva_site_'+str(site)]
                and (self.csr[8],self.csr[0xc20],self.csr[0xc21])==(0,64,8)
                and self.counts['vload']==32 and self.counts['vstore']==(0,32,32,32,32,64,96,96,96,96)[n],
                'Exact native custom PC/type/privilege/vector/checkpoint owner')
        a,b = self.gpr[10:12]; data=b''; vd=None
        if site==0:
            require(a==self.symbols['entropy_descriptors']+64*phase and b==0, 'FULL descriptor operands')
            bases=[v+64 for v in case.static.ALIASES[phase]]
            require(self.read(a,64)==case.old.descriptor(bases,128), 'FULL descriptor exact bytes')
            rows=[]
            for stream,va in enumerate(bases):
                pa=case.translate(self.memory,self.csr[0x180],va)
                require(pa==self.symbols['akva_pages']+4096*stream+64
                        and case.translate(self.memory,self.csr[0x180],va+127)==pa+127, 'Independent full VA/PA walk')
                rows.append(self.read(pa,128))
                self.walks.append(dict(phase=phase,stream=stream,va=va,pa=pa,size=128))
            self.context=rows
        elif site in (1,2,3):
            require(a==site-1 and self.context is not None, 'Exact LOAD selector/live context')
            vd=(8,16,24)[site-1]; data=self.context[site-1]
            self.vrf[vd]=bytearray(data)
            self.vector_effects.append(dict(kind='custom',vd=vd,data=data.hex(),phase=n,pc=self.pc,word=word))
        else:
            require(a==0 and self.context is not None, 'RELEASE operand/live context')
            self.context=None
        self.commands.append(dict(phase=n,word=word,pc=self.pc,fault=False,vd=vd,
            write_bytes=len(data),context_ready_after=self.context is not None))
        self.dirty(True)
        return self.pc+4

    def step(self):
        pc=self.pc; w=int.from_bytes(self.read(pc,4),'little')
        if self.priv==1:
            require(self.csr[0x180]==(8<<60)|(self.symbols['akva_root']>>12), 'S instruction translation active')
            require(self.read(self.symbols['akva_root']+16,8)==struct.pack('<Q',(0x80000000>>12<<10)|0xcf)
                    and 0x80000000<=pc<0x80200000, 'Identity executable S superpage')
        effect=dict(pc=pc,insn=w,rd=0,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
        if w==0x30200073:
            require(self.priv==3,'MRET requires M privilege')
            target=self.csr[0x341]; priv=self.csr[0x300]>>11&3
            require((priv,target)==((1,self.symbols['akva_s_entry']) if self.priv==3 and len(self.traps)==self.counts['mret']//2
                    else (3,self.symbols['akva_resume'])), 'Exact entry/trap-return MRET')
            s=self.csr[0x300]
            self.csr[0x300]=(s&~((1<<3)|(1<<7)|(3<<11)))|((s>>7&1)<<3)|(1<<7)
            self.priv=priv; self.pc=target; self.counts['mret']+=1
        elif w==0x00000073:
            require(self.priv==1 and pc==self.symbols['akva_ecall'] and len(self.traps)<2
                    and len(self.commands)==5*(len(self.traps)+1)
                    and self.csr[0x302]==self.csr[0x304]==0
                    and self.csr[0x305]==self.symbols['akva_handler'], 'Exact two S-ecall owners')
            self.csr.update({0x341:pc,0x342:9,0x343:0})
            s=self.csr[0x300]; self.csr[0x300]=(s&~((1<<3)|(1<<7)|(3<<11)))|((s>>3&1)<<7)|(1<<11)
            self.priv=3; self.pc=self.symbols['akva_handler']
            self.traps.append(dict(pc=pc,cause=9,tval=0)); effect['trap']=1
        elif w==0x12000073:
            require(self.priv==3, 'SFENCE privilege'); self.pc+=4; self.counts['sfence']+=1
        elif w&127==0x33 and w>>25==1 and w>>12&7==0:
            rd,rs1,rs2=w>>7&31,w>>15&31,w>>20&31
            value=tile.mul_low64(self.gpr[rs1],self.gpr[rs2]);self.gpr[rd]=value;self.gpr[0]=0
            if rd:effect.update(rd=rd,rd_wdata=value)
            self.pc+=4;self.counts['integer']+=1
        else:
            return super().step()
        self.steps+=1
        return effect


def replay(blob,symbols,rows=None):
    model=Model(blob,symbols); retires=None if rows is None else [r for r in rows if r['event']=='retire']
    if retires is not None:require(retires and [r['order'] for r in retires]==list(range(len(retires))), 'Retire order')
    index=writes=0; deadline=time.monotonic()+120
    while not model.terminal:
        require(model.steps<300000 and time.monotonic()<deadline, 'Independent replay bound')
        word=int.from_bytes(model.read(model.pc,4),'little')
        if old.isa.base.native.request_instruction(word):
            model.requests.append(dict(pc=model.pc,word=word,response_value=model.csr[word>>20]
                if word&127==0x73 else 64 if word&127==0x57 else 0))
        e=model.step()
        if retires is not None:
            if e['trap']:
                require(index<len(retires) and retires[index]['pc']==model.pc, 'Precise S exception handler entry');continue
            require(index<len(retires),'Truncated retirements')
            old.isa.base.compare_retirement(e,retires[index],index);index+=1;writes+=bool(e['rd'])
    if retires is not None:require(index==len(retires),'Postterminal retirement')
    require(len(model.commands)==10 and len(model.traps)==2 and model.counts['vload']==32
            and model.counts['vstore']==128 and model.counts['mret']==4 and model.priv==3,
            'Complete native workload')
    mappings=case.validate_memory(model.memory,model.symbols)
    require(mappings==model.walks, 'Complete independent walk ledger')
    return model,dict(status='NATIVE_INDEPENDENT_MODEL_MATCH' if rows is not None else 'DRY_NATIVE_MODEL_ONLY',
        oraclekind='BOUNDED_NATIVE_ISA_CUSTOM_INTEGER_BYTE_MODEL_NOT_CUSTOM_SPIKE',steps=model.steps,
        matched_retirements=index,GPR_writes=writes,skipped_retirements=0,commands=10,ecalls=2,VA_PA=mappings,
        native_custom_Spike=False,coverage_admitted=False)


def lifecycle(rows,model):
    starts,pending,responses,alloc,done,active={},{},{},{},{},{}
    commands=[]
    for r in rows:
        seq,event=r['order'],r['event']
        if event=='arch_start':
            i=len(starts)
            require(i<len(model.requests) and seq not in starts and r['insn']==model.requests[i]['word'], 'Exact request sequence')
            starts[seq]=dict(r,expected=model.requests[i])
        elif event=='cvx_req':
            candidates=[s for s in starts.values() if s['trans_id']==r['trans_id'] and s['insn']==r['insn']
                and s['order'] not in responses and s['order'] not in {p['order'] for p in pending.values()}]
            require(len(candidates)==1 and r['trans_id'] not in pending and candidates[0]['cycle']<=r['cycle'], 'Request owner')
            pending[r['trans_id']]=dict(candidates[0],begin=r['cycle'])
        elif event=='cvx_resp':
            require(r['trans_id'] in pending, 'Response owner'); s=pending.pop(r['trans_id']); seq=s['order']
            require(seq not in responses and s['begin']<=r['cycle'] and r['trap']==0
                    and r['rd_wdata']==s['expected']['response_value'], 'Response data/exception')
            if s['insn']&127==0x5b:
                n=len(commands); require(n<10 and s['insn']==model.commands[n]['word'], 'Custom response identity')
                commands.append(dict(model.commands[n],seq=seq,response_cycle=r['cycle']))
            responses[seq]=r
        elif event in ('uop_alloc','uop_done'):
            require(seq in starts and r['insn']==starts[seq]['insn'] and r['trans_id']==starts[seq]['trans_id']
                    and starts[seq]['cycle']<=r['cycle'] and 0<=r['port']<8 and r['rd_wdata']==0, 'Backend owner')
            if event=='uop_alloc':
                require(seq not in alloc and r['port'] not in active and r['insn']&127 in (7,0x27,0x5b), 'Backend allocation')
                alloc[seq]=r;active[r['port']]=seq
            else:
                require(seq in alloc and seq not in done and active.get(r['port'])==seq
                        and alloc[seq]['cycle']<=r['cycle'], 'Backend completion')
                done[seq]=r;del active[r['port']]
    require(len(starts)==len(responses)==len(model.requests) and not pending and not active
            and set(alloc)==set(done) and len(commands)==10
            and [r['insn'] for r in alloc.values()]==[r['word'] for r in model.requests if r['word']&127 in (7,0x27,0x5b)], 'Full request conservation')
    probes=[r for r in rows if r['event']=='retire' and r['insn']&127==0x73 and r['insn']>>20 in (1,8,0xc20,0xc21,10,9)
            and r['insn']>>12&7==2 and r['insn']>>15&31==0]
    require(len(probes)==24,'All checkpoint CSR reads')
    for p,cmd in enumerate((0,4,5,9)):
        frame=probes[p*6:p*6+6];c=commands[cmd]
        require([r['insn']>>20 for r in frame]==[1,8,0xc20,0xc21,10,9]
                and [r['rd_wdata'] for r in frame]==[21,0,64,8,2,1] and all(r['rd'] for r in frame)
                and max(c['response_cycle'],done[c['seq']]['cycle'])<=frame[0]['cycle'], 'Command/checkpoint CSR boundary')
    return dict(commands=commands,starts=starts,allocations=alloc,done=done,requests=len(starts))


def vectors(rows,model,arch):
    require(rows and rows[0]['event']=='config' and sum(r['event']=='config' for r in rows)==1
            and all(int(r['nr_lanes'])==4 and int(r['vlen_bits'])==1024 for r in rows), 'Vector config')
    require(all(int(rows[0][k],16 if k in ('insn','be','wdata') else 10)==0 for k in
        ('cycle','arch_seq','vid','lane','source','insn','use_vd','vd','eew','vl','vstart','addr','be','wdata')), 'Config side effects')
    seeds=[s for s,r in arch['allocations'].items() if r['insn']&127==7]
    require(len(seeds)==32,'All seed writers')
    expected={}
    for e in model.vector_effects:
        seq=seeds[e['vd']] if e['kind']=='seed' else arch['commands'][e['phase']]['seq']
        require(seq not in expected,'Duplicate expected writer')
        expected[seq]={(e['vd'],i):b for i,b in enumerate(bytes.fromhex(e['data']))}
    accepted={s:{} for s in expected}; meta={};mirrors=set();active={};previous=-1
    custom={c['seq']:c for c in arch['commands']}
    for r in rows[1:]:
        event,seq,cy,vid=r['event'],int(r['arch_seq']),int(r['cycle']),int(r['vid'])
        m=tuple(int(r[k]) for k in ('use_vd','vd','eew','vl','vstart'))
        require(event in ('alloc','done','write') and cy>=previous and seq in arch['allocations']
                and int(r['insn'],16)==arch['allocations'][seq]['insn'] and vid==arch['allocations'][seq]['port'], 'Native writer identity')
        previous=cy
        if event in ('alloc','done'):
            require(all(int(r[k],16 if k in ('be','wdata') else 10)==0 for k in ('lane','source','addr','be','wdata')), 'Mirror side effect')
            ref=arch['allocations'] if event=='alloc' else arch['done']
            require((event,seq) not in mirrors and cy==ref[seq]['cycle'],'Exact native lifecycle mirror');mirrors.add((event,seq))
            if event=='alloc':
                op=int(r['insn'],16)&127;use=int(custom[seq]['write_bytes']>0) if op==0x5b else int(op==7)
                vd=custom[seq]['vd'] if op==0x5b else int(r['insn'],16)>>7&31
                require(seq not in meta and vid not in active and m[0]==use and m[2:]==(1,64 if op!=0x5b or use else 1,0)
                        and (not use or m[1]==vd), 'Exact allocated vector configuration')
                meta[seq]=m;active[vid]=seq
            else:
                require(meta.get(seq)==m and active.get(vid)==seq,'Done native configuration');del active[vid]
        else:
            require(meta.get(seq)==m and seq in expected and arch['allocations'][seq]['cycle']<=cy<=arch['done'][seq]['cycle'], 'Writer lifetime')
            lane,addr,be,data=int(r['lane']),int(r['addr']),int(r['be'],16),int(r['wdata'],16)
            require(0<=lane<4 and 0<be<256 and 0<=data<=old.isa.MASK and int(r['source'])==4,'Writer source/BE')
            reg,chunk=divmod(addr,4)
            for byte in range(8):
                if be>>byte&1:
                    slot,within=divmod(byte,2);natural=((slot&1)<<1)|(slot>>1)
                    key=(reg,chunk*32+(natural*4+lane)*2+within)
                    require(key in expected[seq] and key not in accepted[seq] and data>>(8*byte)&255==expected[seq][key], 'Exact known native VRF byte')
                    accepted[seq][key]=expected[seq][key]
    require(not active and set(meta)==set(arch['allocations']) and len(mirrors)==2*len(meta) and accepted==expected,'All native effects complete')
    return dict(seed_bytes=4096,custom_bytes=768,full_frames=4,snapshot_bytes=16384,unknown_or_skipped_bytes=0)


def sample_gate(samples,sym,arch):
    phases=[];current=None;complete=False;ranges=[];translated=[]
    for before,after in samples:
        if before['rst_ni']==0:
            require(not phases,'No midrun reset');continue
        require(before['rst_ni']==1,'Known reset')
        for k in ('command_fire','fault_valid_o','success_valid_o','read_range_fire','axi_ar_valid_o','axi_ar_ready_i',
                  'i_read_engine.mmu_exception_valid_i','i_read_engine.translation_complete'):
            require(before[k] in (0,1),'Unknown active control '+k)
        require(before['fault_valid_o']==0 and before['i_read_engine.mmu_exception_valid_i']==0,'No native faults')
        if before['command_fire']:
            n=len(phases);require(n<10 and (current is None or complete) and not ranges and not translated,'Ordered command/drained boundary')
            require(before['command_i']==(0,2,2,2,3)[n%5] and before['command_tile_start_i']==0,'Accepted native command type/tile')
            command=arch['commands'][n];slot=n%5
            a=sym['entropy_descriptors']+64*(n//5) if slot==0 else slot-1 if slot in (1,2,3) else 0
            require(before['command_id_i']==arch['allocations'][command['seq']]['port']
                    and before['command_vd_i']==(command['word']>>7&31)
                    and before['command_selector_i']==before['command_descriptor_address_i']==a,
                    'Accepted engine command backend VID/rd/rs1 owner')
            current=dict(phase=n,ranges=[],translations=[],AR=[]);phases.append(current);complete=False
        if before['read_range_fire']:
            require(current is not None and not complete and current['phase']%5==0,'FULL range owner')
            n=current['phase']//5;i=len(current['ranges'])
            expected=[(0,0,sym['entropy_descriptors']+64*n,64)]+[(r+1,0,v+64,128) for r,v in enumerate(case.static.ALIASES[n])]
            r=(before['read_range_tag']>>6,before['read_range_tag']&63,before['read_range_vaddr'],before['read_range_bytes'])
            require(i<4 and r==expected[i],'Accepted descriptor/Q/K/V range identity');current['ranges'].append(r);ranges.append(r)
        if before['i_read_engine.translation_complete']:
            require(current is not None and not complete and ranges and before['i_read_engine.mmu_req_o']==1
                    and before['i_read_engine.en_ld_st_translation_i']==1 and before['i_read_engine.mmu_valid_i']==1
                    and before['i_read_engine.plan_state_q']==2,'Accepted MMU translation owner')
            role,index,va,size=ranges.pop(0)
            pa=va if role==0 else sym['akva_pages']+(role-1)*4096+64
            require(before['i_read_engine.mmu_vaddr_o']==va and before['i_read_engine.mmu_paddr_i']==pa
                    and after['i_read_engine.ar_addr_q']==pa and after['i_read_engine.ar_cursor_vaddr_q']==va
                    and after['i_read_engine.ar_chunk_bytes_q']==size,'Preaccepted VA/PA and settled AR capture')
            item=dict(va=va,pa=pa,size=size,role=role);current['translations'].append(item);translated.append(item)
        if before['axi_ar_valid_o'] and before['axi_ar_ready_i']:
            require(current is not None and not complete and translated,'Physical AR causal owner')
            item=translated.pop(0)
            require(before['i_read_engine.ar_addr_q']==item['pa'] and before['i_read_engine.ar_cursor_vaddr_q']==item['va']
                    and before['i_read_engine.ar_chunk_bytes_q']==item['size'],'Exact accepted AR from MMU')
            current['AR'].append(item)
        if before['success_valid_o']:
            require(current is not None and not complete and not ranges and not translated
                    and before['context_ready_o']==int(current['phase']%5!=4),'Exact native completion/context/drain')
            complete=True
    require(len(phases)==10 and complete and all(len(p['ranges'])==len(p['translations'])==len(p['AR'])==(4 if p['phase']%5==0 else 0) for p in phases),'Ten complete MMU/AR command owners')
    return dict(commands=phases,actual_accepted_translation_count=8,
        sampling='preedge accepted controls/VA/PA; same-edge settled AR capture',
        page_walk='Independent exact PTE oracle; native translation accepted, not a claim each lookup missed TLB')


def native_wave(path,sym,arch):
    parse=FunctionType(tile.wave.vcd.__code__,dict(tile.wave.vcd.__globals__,ROOT=SCOPE,WIDTHS=WIDTHS))
    iterator=iter(parse(path));_,decl=next(iterator)
    require(all(decl.get(SCOPE+'.'+k,{}).get('width')==w for k,w in WIDTHS.items()),'Exact native object widths')
    codes={k:decl[SCOPE+'.'+k]['code'] for k in WIDTHS}
    def value(state,code):
        bits=state.get(code,'x');return int(bits,2) if set(bits)<=set('01') else None
    return sample_gate((({k:value(b,c) for k,c in codes.items()},{k:value(a,c) for k,c in codes.items()})
        for _,b,a in iterator if b.get(codes['clk_i'])=='0' and a.get(codes['clk_i'])=='1'),sym,arch)


def perf(log,arch):
    lines=[l for l in log.splitlines() if l.startswith('[AKV_PERF] ')]
    require(len(lines)==10,'All ten PERF outcomes')
    result=[]
    for n,line in enumerate(lines):
        fields=[re.fullmatch(r'([a-z_][a-z_0-9]*)=([0-9]+)',t) for t in line.split()[1:]]
        require(all(fields),'Exact PERF tokens');row={m[1]:int(m[2]) for m in fields}
        require(len(row)==len(fields) and set(row)==set(old.isa.base.native.legacy.PERF_KEYS),'Exact PERF schema')
        slot=n%5;full=slot==0;load=slot in (1,2,3)
        expect=dict(seq=n+1,command=(0,2,2,2,3)[slot],success=1,fault=0,validation_fault=0,
            validation_error=0,read_fault=0,context_ready=int(slot!=4),full=int(full),refill=0,
            load=int(load),release=int(slot==4),v2_full=0,v2_refill=0,v2_row_load=0,v2_column_load=0,
            v2_column_panel=0,v2_logical_column=0,v2_bank_conflict_cycles=0,v2_rejected=0,
            q_external_bytes=128 if full else 0,kv_external_bytes=256 if full else 0,
            replay_bytes=128 if load else 0,read_ranges=4 if full else 0,
            translations=4 if full else 0,read_payload_bytes=448 if full else 0)
        require(all(row[k]==v for k,v in expect.items()) and row['busy_cycles']>0
                and row['id']==arch['allocations'][arch['commands'][n]['seq']]['port'], 'Exact native PERF owner/outcome')
        require((row['ar'],row['r_beats'])==((4,28) if full else (0,0)), 'Exact descriptor/payload AXI conservation')
        result.append(row)
    return result


def contract(log,requests):
    lines=[l for l in log.splitlines() if l.startswith('[ARA_CONTRACT]')]
    require(len(lines)==1 and lines[0].startswith('[ARA_CONTRACT] '),'Unique strict contract')
    fields=[re.fullmatch(r'([a-z_]+)=(0|[1-9][0-9]*)',t) for t in lines[0].split()[1:]]
    require(all(fields),'Contract tokens');row={m[1]:int(m[2]) for m in fields}
    expected=dict(requests=requests,responses=requests,exceptions=0,protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0)
    require(len(row)==len(fields) and set(row)==set(expected)|{'mmu_request_cycles'}
            and all(row[k]==v for k,v in expected.items()) and row['mmu_request_cycles']>0,
            'Strict accelerator contract; S-ecalls separately checked, not CVX exceptions')
    return row


def native_identity(sim,args,run,command,compile_vdb):
    require(sim.tag=='test' and len(sim.findall('srctest'))==1,'One completed native test')
    r=sim.find('srctest')
    require(shlex.split(r.get('cmdline',''))==command and r.get('workdir')==str(run)
            and r.get('seed')=='1' and r.get('teststatus')=='unknown'
            and re.fullmatch(r'[0-9]+',r.get('starttime','')) and re.fullmatch(r'[0-9]+',r.get('finishtime',''))
            and 0<int(r.get('starttime'))<int(r.get('finishtime')), 'Actual cmd/cwd/completion')
    require(args.tag=='vcm_args' and args.get('compvdbpath')==compile_vdb
            and sorted(n.get('vcm_opt') for n in args.findall('vcm_arg_data') if n.get('vcm_opt'))==
            ['-cm branch','-cm cond','-cm fsm','-cm line','-cm tgl'], 'Native compatible five metrics')
    return dict(workdir=str(run),command=command,starttime=r.get('starttime'),finishtime=r.get('finishtime'),
        compile_vdb=compile_vdb,XML_status_not_functional_PASS=True)


def raw_gain(run,m,out,pins):
    basepath=case.static.BASE;base=life.read_bound(basepath/'admission-manifest.json',case.static.BASE_SHA)
    ledgerpath=basepath/'combined-inputs.txt';bitpath=basepath/'combined-bits.json';tglpath=basepath/'combined-toggle-bits.json'
    pins=life.merge_pins(pins,{str(p):base['output_pins'][str(p)] for p in (ledgerpath,bitpath,tglpath)})
    life.check(pins);ledger=ledgerpath.read_text().splitlines();before=life.read_bound(bitpath,pins[str(bitpath)])
    require(len(ledger)==len(set(ledger))==795 and before['tests']==ledger[1:] and str(run/'code.vdb') not in ledger,'Exact794 raw prefix')
    folders=list((run/'code.vdb/snps/coverage/db/testdata').iterdir())
    require(len(folders)==1 and folders[0].name=='akv_canonical_alias794','Exact single native test')
    identity=native_identity(case.static.shape.xml(folders[0]/'siminfo.xml'),
        case.static.shape.xml(folders[0]/'vcmArguments.xml'),run,m['command'],ledger[0])
    for p in (folders[0]/'siminfo.xml',folders[0]/'vcmArguments.xml'):
        require(pins.get(str(p))==case.sha(p),'Native identity XML pin')
    life.save(out/'native-vdb-identity.json',identity)
    inputs=out/'single-inputs.txt';inputs.write_text(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
    single=old.bitmap.collect(inputs);after=old.bitmap.combine(before,single);old.independent_or(before,single,after)
    require(single['design']==before['design'] and sum(len(r) for r in before['metrics'].values())==6162,'Full6162 design/shape universe')
    for rel,h in single['design'].items():
        require(base['input_pins'].get(str(Path(ledger[0])/'snps/coverage/db'/rel))==h,'Compiled design hash authority')
    pins=life.merge_pins(pins,single['input_hashes'])
    beforetgl=life.read_bound(tglpath,pins[str(tglpath)])
    require(len(beforetgl)==2989,'Complete raw2989 Toggle universe')
    files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(files)==1,'Unique candidate Toggle')
    add,h=case.old.toggle.rows(files[0],list(beforetgl));aftertgl=case.old.toggle.union(beforetgl,add)
    pins=life.merge_pins(pins,{str(files[0]):h});gains=case.old.toggle.gains(beforetgl,aftertgl)
    targets=[]
    for f in m['targets']['fields']:
        positions=sorted(set(gains[f['scope']])&set(f['full_coordinates']))
        targets.append(dict(scope=f['scope'],name=f['name'],new_positions=positions,new_directions=len(positions)))
    diagnostic=dict(baseline=794,system_new_directions=sum(map(len,gains.values())),target_fields=targets,
        target_new_directions=sum(t['new_directions'] for t in targets),official_percentage_claimed=False,
        future_admission_requires_latest_rebase=True,coverage_admitted=False)
    for name,obj in [('single-bits.json',single),('combined-bits-diagnostic.json',after),
                     ('raw-delta.json',old.bitmap.delta(before,after)),('single-toggle-bits.json',add),
                     ('combined-toggle-diagnostic.json',aftertgl),('toggle-gain794.json',diagnostic)]:life.save(out/name,obj)
    return pins


def terminal(status,started,m,run,elf):
    require(type(status.get('returncode')) is int and status==dict(status='SIMULATION_EXITED_NOT_ADMITTED',
        returncode=0,timeout=False,pid=started.get('pid'),coverage_admitted=False)
        and type(status['pid']) is int and status['pid']>0 and type(status['timeout']) is bool
        and type(status['coverage_admitted']) is bool,'Strict successful terminal')
    require(started.get('live_identity_verified') is True and started.get('exe')==str(life.IMAGE)
        and started.get('cwd')==str(run) and type(started.get('starttime')) is int and started['starttime']>0
        and started.get('executable_sha256')==m['pins'][str(life.IMAGE)]
        and started.get('command')==m['command'] and started.get('input_elf')==str(elf)
        and started.get('elf_sha256')==m['pins'][str(elf)] and type(started.get('budget_s')) is int
        and started['budget_s']==m['timeout_s']==900,'Exact actual image/ELF/command/budget identity')


def collect(run,seal,out):
    import run_akv_canonical_alias794 as runner
    run,out=Path(run).absolute(),Path(out).absolute()
    require(out.parent==life.OUT and not out.exists(),'Fresh qualification')
    m=runner.verify(run,seal);terminal(json.loads((run/'simulation-status.json').read_bytes()),
        json.loads((run/'started.json').read_bytes()),m,run,runner.ELF)
    paths=[run/n for n in ('manifest.json','simulation-status.json','started.json','console.log','run.vcs.log',
        'commit_trace.csv','vector_trace.csv','entropy-ranges.vpd')]+[p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require((run/'code.vdb').is_dir() and all(p.is_file() and not p.is_symlink() for p in paths),'Full unaliased run artifacts')
    require(0<(run/'entropy-ranges.vpd').stat().st_size<=m['wave_limit_bytes'],'Actual64MiB wave bound')
    pins=life.merge_pins(m['pins'],{str(p):case.sha(p) for p in paths});life.check(pins);out.mkdir()
    try:
        vcd=out/'akv-alias.vcd'
        with (out/'conversion.log').open('x') as log:
            subprocess.run([str(old.CONVERTER),str(run/'entropy-ranges.vpd'),str(vcd)],stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
        require(vcd.is_file() and vcd.stat().st_size<=256*1024*1024,'Bounded converted wave');pins=life.merge_pins(pins,{str(vcd):case.sha(vcd)})
        rows=old.isa.base.native.commit_rows(run/'commit_trace.csv');model,scalar=replay(runner.ELF.read_bytes(),m['preflight']['symbols'],rows)
        arch=lifecycle(rows,model);vector=vectors(old.isa.base.native.common.read_csv(run/'vector_trace.csv',old.isa.base.native.common.VECTOR_FIELDS),model,arch)
        log=(run/'run.vcs.log').read_text()
        require(log.count('Core Test *** SUCCESS ***')==1 and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)',log),'Runtime software/fatal gate')
        console=(run/'console.log').read_text().splitlines()
        require(console.count('AKV_ALIAS_READY')==1 and sorted(l for l in console if l.startswith('AKV_ALIAS_OBJECT '))
                ==sorted('AKV_ALIAS_OBJECT '+SCOPE+'.'+k for k in WIDTHS)
                and not any(re.match(r'^\s*(?:AKV_ALIAS_ERROR\b|UCLI_ERROR\b|Error-)',l) for l in console),'Actual probe inventory/readiness')
        native=native_wave(vcd,m['preflight']['symbols'],arch)
        for name,obj in [('scalar.json',scalar),('lifecycle.json',arch),('vector.json',vector),('native-capture.json',native),
            ('perf.json',perf(log,arch)),('contract.json',contract(log,arch['requests']))]:life.save(out/name,obj)
        pins=raw_gain(run,m,out,pins);life.check(pins)
        life.save(out/'qualification.json',dict(status='AKV_CANONICAL_ALIAS_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED',
            input_pins=pins,output_pins={str(p):case.sha(p) for p in out.iterdir()},baseline_tests=794,
            native_custom_Spike=False,oraclekind=scalar['oraclekind'],scalar_model_skips=0,
            coverage_admitted=False,future_admission_requires_latest_rebase=True))
    except Exception as exc:
        life.save(out/'failure.json',dict(status='QUALIFICATION_HOLD',reason=str(exc),coverage_admitted=False));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--run-seal',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();collect(a.run,a.run_seal,a.output)
