"""Scoped entropy adapter: exact tile traps/64-bit capture, native ISA, VRF and raw780 gain."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess
import time
from types import FunctionType
from io import BytesIO
from elftools.elf.elffile import ELFFile

import collect_akv_entropy as old
import preflight_akv_tile_range_capture as case
import audit_gap115_axi_v2 as wave

life,require=old.life,case.require
SCOPE=case.old.SCOPE
WIDTHS=dict(clk_i=1,rst_ni=1,command_fire=1,command_i=3,command_tile_start_i=64,requested_tile_start_q=64,
    fault_valid_o=1,success_valid_o=1,fault_is_validation_o=1,validation_error_o=5,context_ready_o=1,
    mmu_exception_valid_i=1,read_range_fire=1,read_range_vaddr=64,read_range_bytes=16,read_range_tag=8,
    axi_ar_valid_o=1,axi_ar_ready_i=1,**{'i_read_engine.ar_addr_q':64})


class Model(old.Model):
    def __init__(self,blob,symbols):
        table=ELFFile(BytesIO(blob)).get_section_by_name('.symtab')
        require(table is not None,'ELF symbol table')
        names={**symbols,'tile_traps':None}; found={n:[] for n in names}
        for s in table.iter_symbols():
            if s.name in found: found[s.name].append(s['st_value'])
        require(all(len(v)==1 for v in found.values()) and all(found[n][0]==v for n,v in symbols.items()),'Unique same-ELF symbol supplement')
        symbols={n:v[0] for n,v in found.items()}
        translated=dict(symbols,**{'entropy_site_'+str(i):symbols['tile_site_'+str(i)] for i in range(6)})
        scanner=FunctionType(case.old.native_sites.__code__,dict(case.old.native_sites.__globals__,WORDS=case.WORDS))
        scanner(blob,translated)
        old.isa.base.Model.__init__(self,blob,symbols)
        self.requests=[]; self.context=None

    def step(self):
        word=int.from_bytes(self.read(self.pc,4),'little')
        if word&127==0x33 and word>>25==1 and word>>12&7==0:
            require(self.pc==self.symbols['tile_handler']+0x34 and word==0x027303b3,
                    'MUL outside exact pinned handler')
            rd,rs1,rs2=word>>7&31,word>>15&31,word>>20&31
            value=mul_low64(self.gpr[rs1],self.gpr[rs2])
            effect=dict(pc=self.pc,insn=word,rd=rd,rd_wdata=value,mem_addr=0,mem_rmask=0,mem_wmask=0,trap=0)
            self.gpr[rd]=value; self.gpr[0]=0
            self.pc+=4; self.steps+=1; self.counts['integer']+=1
            return effect
        return super().step()

    def custom(self,word):
        phase=len(self.commands)
        require(phase<6 and word==case.WORDS[phase] and self.pc==self.symbols['tile_site_'+str(phase)]
                and self.counts['vload']==32 and self.counts['vstore']==phase*32
                and (self.csr[8],self.csr[0xc20],self.csr[0xc21])==(0,64,8),'Custom PC/op/state')
        a,b=self.gpr[10:12]
        require((a,b)==(self.symbols['entropy_descriptors'],case.INDICES[phase]) if phase<4 else (a,b)==(0,0),'Full64 operands')
        data=b''; error=11 if phase<3 else 0
        if phase<4:
            bases=[self.symbols['entropy_sources']+i*256+64 for i in range(3)]
            require(self.read(a,64)==case.old.descriptor(bases,128),'Valid descriptor exact')
            self.context=None if error else [self.read(base,128) for base in bases]
        elif phase==4:
            require(self.context is not None,'Recovery context')
            data=self.context[0]; self.vrf[8]=bytearray(data)
            self.vector_effects.append(dict(kind='custom',vd=8,data=data.hex(),phase=4,pc=self.pc))
        else: self.context=None
        self.commands.append(dict(phase=phase,word=word,pc=self.pc,fault=bool(error),validation_error=error,
            write_bytes=len(data),context_ready_after=self.context is not None))
        if error:
            require(self.csr[0x302]==self.csr[0x304]==0 and self.csr[0x305]==self.symbols['tile_handler'],'Exact trap environment')
            self.csr.update({0x341:self.pc,0x342:2,0x343:0})
            status=self.csr[0x300]
            self.csr[0x300]=(status&~((1<<3)|(1<<7)|(3<<11)))|((status>>3&1)<<7)|(3<<11)
            self.traps.append(dict(pc=self.pc,cause=2,tval=0,handler=self.csr[0x305]))
            return self.csr[0x305]
        self.dirty(True); return self.pc+4


def mul_low64(left,right):
    require(type(left) is int and type(right) is int and 0<=left<=old.isa.MASK and 0<=right<=old.isa.MASK,
            'Exact unsigned register bit patterns')
    return (left*right)&old.isa.MASK


def expected_regions(sym):
    regions=case.expected(sym)
    del regions['entropy_semantic_error']
    regions['g75_result']=struct.pack('<2I',case.DUT_CHECKS,0)
    regions['tile_traps']=struct.pack('<9Q',*(x for p in range(3) for x in (2,sym['tile_site_'+str(p)],0)))
    return regions


def replay(blob,symbols,rows=None):
    model=Model(blob,symbols); retires=None if rows is None else [r for r in rows if r['event']=='retire']
    if retires is not None: require(retires and [r['order'] for r in retires]==list(range(len(retires))),'Retire ordering')
    index=writes=0; deadline=time.monotonic()+120
    while not model.terminal:
        require(model.steps<300000 and time.monotonic()<deadline,'Native replay bound')
        word=int.from_bytes(model.read(model.pc,4),'little')
        if old.isa.base.native.request_instruction(word):
            model.requests.append(dict(pc=model.pc,word=word,response_value=model.csr[word>>20] if word&127==0x73 else 64 if word&127==0x57 else 0))
        effect=model.step()
        if retires is not None:
            if effect['trap']:
                require(index<len(retires) and retires[index]['pc']==model.pc,'Precise trap handler retirement'); continue
            require(index<len(retires),'Truncated scalar trace')
            old.isa.base.compare_retirement(effect,retires[index],index); writes+=bool(effect['rd']); index+=1
    if retires is not None: require(index==len(retires),'Postterminal retirements')
    require(model.counts['vload']==32 and model.counts['vstore']==192 and model.counts['vset']==7
            and model.counts['mret']==3 and len(model.traps)==3 and len(model.commands)==6
            and [c['validation_error'] for c in model.commands]==[11,11,11,0,0,0]
            and sum(c['write_bytes'] for c in model.commands)==128,'Complete workload exact')
    for name,data in expected_regions(model.symbols).items(): require(model.read(model.symbols[name],len(data))==data,'Final full oracle: '+name)
    return model,dict(status='INDEPENDENT_NATIVE_ISA_MODEL_MATCH' if rows is not None else 'DRY_NATIVE_MODEL_ONLY',
        steps=model.steps,matched_retirements=index,GPR_writes=writes,skipped_retirements=0,traps=3,
        native_Spike_comparison=False,coverage_admitted=False)


def perf(log,arch):
    lines=[l for l in log.splitlines() if l.startswith('[AKV_PERF] ')]
    require(len(lines)==6,'Six native PERF entries')
    result=[]
    for phase,line in enumerate(lines):
        fields=[re.fullmatch(r'([a-z_][a-z_0-9]*)=([0-9]+)',t) for t in line.split()[1:]]
        require(all(fields),'Malformed PERF'); row={m[1]:int(m[2]) for m in fields}
        require(len(row)==len(fields) and set(row)==set(old.isa.base.native.legacy.PERF_KEYS),'Exact PERF schema')
        bad=phase<3; good=phase==3
        expected=dict(seq=phase+1,command=[0,0,0,0,2,3][phase],success=int(not bad),fault=int(bad),
            validation_fault=int(bad),validation_error=11 if bad else 0,read_fault=0,context_ready=int(phase in (3,4)),
            full=int(phase<4),refill=0,load=int(phase==4),release=int(phase==5),v2_full=0,v2_refill=0,
            v2_row_load=0,v2_column_load=0,v2_column_panel=0,v2_logical_column=0,v2_bank_conflict_cycles=0,v2_rejected=0,
            q_external_bytes=128 if good else 0,kv_external_bytes=256 if good else 0,replay_bytes=128 if phase==4 else 0,
            read_ranges=1 if bad else 4 if good else 0,translations=0,read_payload_bytes=64 if bad else 448 if good else 0)
        require(all(row[k]==v for k,v in expected.items()) and row['busy_cycles']>0
                and row['id']==arch['allocations'][arch['commands'][phase]['seq']]['port'],'Precise PERF outcome')
        if phase>=4: require(row['ar']==row['r_beats']==0,'No LOAD/RELEASE AR')
        result.append(row)
    return result


def contract(log,requests):
    lines=[l for l in log.splitlines() if l.startswith('[ARA_CONTRACT]')]
    require(len(lines)==1 and lines[0].startswith('[ARA_CONTRACT] '),'Unique native contract')
    fields=[re.fullmatch(r'([a-z_]+)=(0|[1-9][0-9]*)',t) for t in lines[0].split()[1:]]
    require(all(fields),'Malformed native contract')
    row={m[1]:int(m[2]) for m in fields}
    require(len(row)==len(fields) and row==dict(requests=requests,responses=requests,exceptions=3,
        mmu_request_cycles=0,protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0),'Native conservation/three validation traps')
    return row


def sample_gate(samples,sym):
    phases=[]; current=None; completed=False
    for before,after in samples:
        if before['rst_ni']==0:
            require(not phases,'Unexpected later reset'); continue
        require(before['rst_ni']==1,'Unknown reset')
        for key in ('command_fire','fault_valid_o','success_valid_o','read_range_fire','axi_ar_valid_o','axi_ar_ready_i','mmu_exception_valid_i'):
            require(before[key] in (0,1),'Unknown native control: '+key)
        require(before['mmu_exception_valid_i']==0,'MMU exception cannot replace TILE_RANGE')
        if before['command_fire']:
            phase=len(phases); require(phase<6 and (current is None or completed),'Overlapping command')
            require(before['command_i']==[0,0,0,0,2,3][phase]
                    and before['command_tile_start_i']==(case.INDICES[phase] if phase<4 else 0)
                    and after['requested_tile_start_q']==before['command_tile_start_i'],'Accepted/postcapture full64 differs')
            current=dict(phase=phase,index=before['command_tile_start_i'],ranges=[],AR=[]); phases.append(current); completed=False
        if before['read_range_fire']:
            require(current is not None and not completed,'Late/foreign range')
            current['ranges'].append((before['read_range_tag']>>6,before['read_range_tag']&63,before['read_range_vaddr'],before['read_range_bytes']))
        if before['axi_ar_valid_o'] and before['axi_ar_ready_i']:
            require(current is not None and not completed and before['i_read_engine.ar_addr_q'] is not None,'Foreign/unknown AR')
            current['AR'].append(before['i_read_engine.ar_addr_q'])
        if before['fault_valid_o'] or before['success_valid_o']:
            require(current is not None and not(before['fault_valid_o'] and before['success_valid_o']),'Foreign/dual completion')
            p=current['phase']; bad=p<3
            require(before['fault_valid_o']==int(bad) and before['fault_is_validation_o']==int(bad)
                    and before['validation_error_o']==(11 if bad else 0)
                    and before['context_ready_o']==int(p in (3,4)),'Native validation/context outcome')
            completed=True
    require(len(phases)==6 and completed,'Incomplete six native commands')
    bases=[sym['entropy_sources']+s*256+64 for s in range(3)]
    for p,item in enumerate(phases):
        ranges=[(0,0,sym['entropy_descriptors'],64)] if p<4 else []
        if p==3: ranges += [(role,0,addr,size) for role,addr,size in case.old.ranges(bases,128)]
        require(item['ranges']==ranges,'Exact descriptor/payload ranges')
        if p<3: require(item['AR'] and all(sym['entropy_descriptors']<=a<sym['entropy_descriptors']+64 for a in item['AR']),'Rejected FULL payload AR')
        elif p>=4: require(not item['AR'],'Unexpected recovery LOAD/RELEASE AR')
    return dict(commands=phases,accepted64_indices=case.INDICES,validation_errors=[11,11,11],rejected_payload_AR=0,
                sampling='preedge controls/input, same-edge settled postcapture')


def native_wave(path,sym):
    parse=FunctionType(wave.vcd.__code__,dict(wave.vcd.__globals__,ROOT=SCOPE,WIDTHS=WIDTHS))
    iterator=iter(parse(path)); _,decl=next(iterator)
    require(all(decl.get(SCOPE+'.'+k,{}).get('width')==w for k,w in WIDTHS.items()),'Exact native widths')
    codes={k:decl[SCOPE+'.'+k]['code'] for k in WIDTHS}
    def value(state,code):
        bits=state.get(code,'x'); return int(bits,2) if set(bits)<=set('01') else None
    def samples():
        for _,before,after in iterator:
            if before.get(codes['clk_i'])=='0' and after.get(codes['clk_i'])=='1':
                yield ({k:value(before,c) for k,c in codes.items()},{k:value(after,c) for k,c in codes.items()})
    return sample_gate(samples(),sym)


def raw_gain(run,m,out,pins):
    base=life.read_bound(Path(m['baseline'])/'admission-manifest.json',m['baseline_sha256'])
    ledger_path=Path(m['baseline'])/'combined-inputs.txt'
    require(case.old.sha(ledger_path)==base['output_pins'][str(ledger_path)],'780 ledger hash')
    ledger=ledger_path.read_text().splitlines()
    before=life.read_bound(Path(m['baseline'])/'combined-bits.json',base['output_pins'][str(Path(m['baseline'])/'combined-bits.json')])
    require(len(ledger)==781 and before['tests']==ledger[1:] and str(run/'code.vdb') not in ledger,'Exact780 membership')
    inputs=out/'single-inputs.txt'; inputs.write_text(ledger[0]+'\n'+str(run/'code.vdb')+'\n')
    single=old.bitmap.collect(inputs); after=old.bitmap.combine(before,single); old.independent_or(before,single,after)
    require(sum(len(v) for v in before['metrics'].values())==6162,'Exact6162 universe')
    require(single['design']==before['design'],'Real compiled design/hash equality')
    for rel,h in single['design'].items(): require(base['input_pins'].get(str(Path(ledger[0])/'snps/coverage/db'/rel))==h,'Compiled design authority')
    pins=life.merge_pins(pins,single['input_hashes'])
    cachepath=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
    cache=life.read_bound(cachepath,'8c9fe15bec6ae5dcd2e5e9dee9c461047db4109464d2c568e3ca5ec9b0bf0865')
    oldledger=next(Path(p) for p in cache['input_pins'] if p.endswith('/inputs.txt'))
    require(case.old.sha(oldledger)==cache['input_pins'][str(oldledger)] and ledger[:742]==oldledger.read_text().splitlines(),'Exact741 Toggle cache prefix')
    pins=life.merge_pins(pins,{str(cachepath):case.old.sha(cachepath),str(oldledger):case.old.sha(oldledger)})
    t={SCOPE:{k:cache['instances'][SCOPE][k] for k in ('width','checksum','bits')}}
    for db in ledger[742:]:
        files=list((Path(db)/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml')); require(len(files)==1,'Unique historical Toggle')
        rows,h=case.old.toggle.rows(files[0],[SCOPE]); require(base['input_pins'].get(str(files[0]))==h,'Pinned historical Toggle')
        pins=life.merge_pins(pins,{str(files[0]):h}); t=case.old.toggle.union(t,rows)
    files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml')); require(len(files)==1,'Unique candidate Toggle')
    added,h=case.old.toggle.rows(files[0],[SCOPE]); pins=life.merge_pins(pins,{str(files[0]):h})
    union=case.old.toggle.union(t,added); b,a=t[SCOPE],union[SCOPE]
    require(b['checksum']=='4015856550' and b['width']==12374,'Exact AKV shape')
    gain=int(a['bits'],16)&~int(b['bits'],16)
    targets=[4238+2*bit+d for bit in range(64) for d in (0,1)]
    fresh=[i for i in targets if gain>>(b['width']-1-i)&1]
    diagnostic=dict(baseline=780,before=b,single=added[SCOPE],after=a,new_positions=bin(gain).count('1'),
        requested_tile_new_indices=fresh,requested_tile_new_directions=len(fresh),official_percentage_claimed=False,coverage_admitted=False)
    for name,value in [('single-bits.json',single),('combined-bits-diagnostic.json',after),('raw-delta.json',old.bitmap.delta(before,after)),('toggle-gain780.json',diagnostic)]: life.save(out/name,value)
    return pins


def collect(run,seal,out):
    import run_akv_tile_range_capture as runner
    run,out=Path(run).absolute(),Path(out).absolute()
    require(out.parent==life.OUT and not out.exists(),'Fresh output')
    m=life.read_bound(run/'manifest.json',seal)
    require(life.read_bound(run.with_name(run.name+'.prepared.json'),seal)==m and runner.prepare(run,True)[1]==m,'Reviewed/executed manifest')
    old.terminal_gate(json.loads((run/'simulation-status.json').read_bytes()),json.loads((run/'started.json').read_bytes()),m,run,life.IMAGE,runner.ELF)
    paths=[run/n for n in ('manifest.json','simulation-status.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','entropy-ranges.vpd')]
    paths += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    require((run/'code.vdb').is_dir() and all(p.is_file() and not p.is_symlink() for p in paths),'Full unaliased artifacts')
    require(0<(run/'entropy-ranges.vpd').stat().st_size<=m['wave_limit_bytes'],'Bounded actual wave')
    pins=life.merge_pins(m['pins'],{str(p):case.old.sha(p) for p in paths}); life.check(pins); out.mkdir()
    try:
        vcd=out/'tile-range.vcd'
        with (out/'conversion.log').open('x') as log: subprocess.run([str(old.CONVERTER),str(run/'entropy-ranges.vpd'),str(vcd)],stdout=log,stderr=subprocess.STDOUT,timeout=120,check=True)
        require(vcd.is_file() and vcd.stat().st_size<=256*1024*1024,'Bounded conversion')
        pins=life.merge_pins(pins,{str(vcd):case.old.sha(vcd)})
        rows=old.isa.base.native.commit_rows(run/'commit_trace.csv')
        model,scalar=replay(runner.ELF.read_bytes(),m['preflight']['symbols'],rows)
        arch=old.lifecycle(rows,model)
        vector=old.vectors(old.isa.base.native.common.read_csv(run/'vector_trace.csv',old.isa.base.native.common.VECTOR_FIELDS),model,arch)
        log=(run/'run.vcs.log').read_text()
        require(log.count('Core Test *** SUCCESS ***')==1 and not re.search(r'(?m)^.*UVM_(?:ERROR|FATAL)(?!\s*:\s*0\s*$)',log),'Runtime fatal/error')
        native_contract=contract(log,arch['requests'])
        console=(run/'console.log').read_text().splitlines()
        require(console.count('TILE_RANGE_READY')==1 and sorted(l for l in console if l.startswith('TILE_RANGE_OBJECT '))==sorted('TILE_RANGE_OBJECT '+SCOPE+'.'+k for k in WIDTHS)
                and not any(l.startswith('TILE_RANGE_ERROR ') for l in console),'Exact probe readiness')
        observed=native_wave(vcd,m['preflight']['symbols']); perf_rows=perf(log,arch)
        for name,value in [('scalar.json',scalar),('lifecycle.json',arch),('vector.json',vector),('native-capture.json',observed),('perf.json',perf_rows),('contract.json',native_contract)]: life.save(out/name,value)
        pins=raw_gain(run,m,out,pins); life.check(pins)
        life.save(out/'qualification.json',dict(status='AKV_TILE_RANGE_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED',input_pins=pins,
            output_pins={str(p):case.old.sha(p) for p in out.iterdir()},baseline_tests=780,native_Spike_comparison=False,
            scalar_model_skips=0,coverage_admitted=False))
    except Exception as exc:
        life.save(out/'failure.json',dict(reason=str(exc),coverage_admitted=False)); raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--run',type=Path,required=True); p.add_argument('--run-seal',required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); collect(a.run,a.run_seal,a.output)
