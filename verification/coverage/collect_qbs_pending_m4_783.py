"""Two-checkpoint native QBS architecture, full pending FIFO witness and exact783 OR."""
import argparse
from collections import deque
import csv
import inspect
import json
from pathlib import Path
import re
import struct
import subprocess
from types import FunctionType, SimpleNamespace

import run_qbs_pending_m4_783 as runner
import collect_qbs_k2_row_pending782 as core
import analyze_qbs_k2_pending782 as cycle_core
import coverage_bitmap_delta as bitmap
import targeted_toggle_evidence as toggle
import build_qbs_pending_two_phase_m4_783 as recipe

life,require=runner.life,core.require
WORD=0x06b5045b
WAVE='qbs-pending-two-phase.vpd'


def elf_view():
    meta=json.loads((runner.PRE/'dut.metadata.log').read_bytes())[0]
    symbols={}
    for row in meta['Symbols']:
        s=row['Symbol'];name=s['Name']['Name']
        if name and not name.startswith('$'):
            require(name not in symbols,'Duplicate ELF symbol');symbols[name]=(s['Value'],s['Size'])
    blob=runner.ELF.read_bytes()
    def data(address,size):
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=address and address+size<=r['Section']['Address']+r['Section']['Size']]
        require(len(sections)==1,'Unique ELF bytes');s=sections[0];offset=s['Offset']+address-s['Address']
        raw=blob[offset:offset+size];require(len(raw)==size,'Complete ELF bytes');return raw
    seed=recipe.frozen.old.seed_bytes();require(data(*symbols['seed'])==seed,'Exact initialized VRF')
    sites=[];items=[]
    for phase,(w,a,gold,dots) in enumerate(recipe.fixture()):
        for name,value in [('weight',w),('activation',a),('gold',gold),('weight_expected',w),('activation_expected',a)]:
            require(symbols[name+str(phase)][1]==len(value) and data(*symbols[name+str(phase)])==value,'ELF fixture '+name)
        for name,base,step in [('frame','frames',4224),('csr','csrs',160),('desc','descriptors',144)]:
            require(symbols[base][1]==2*step,'Both complete checkpoint objects')
            symbols[name+str(phase)]=(symbols[base][0]+phase*step,step)
        address,size=symbols['matrix_exec'+str(phase)];raw=data(address,size);pos=0;memory=[]
        while pos<size:
            width=4 if int.from_bytes(raw[pos:pos+2],'little')&3==3 else 2
            require(pos+width<=size,'Complete instruction');word=int.from_bytes(raw[pos:pos+width],'little')
            if width==4 and word&0x7f in (7,39) and word>>12&7==6:
                memory.append(dict(pc=address+pos,word=word,store=word&0x7f==39,register=word>>7&31))
            pos+=width
        require([(s['store'],s['register']) for s in memory]==[(False,r) for r in (0,8,16,24)]+[(True,r) for r in (0,8,16,24)],'Exact seed/snapshot path')
        require(data(symbols['matrix_qbexec_site'+str(phase)][0],4)==struct.pack('<I',WORD),'Legal M4 opcode')
        item=dict(n=8,result_bits=[core.native.integer_single(d) for d in dots],integer_dots=dots,fflags=0)
        require(len(dots)==32 and all(struct.unpack_from('<I',gold,1024+128*c+4*r)[0]==item['result_bits'][8*c+r]
            for c in range(4) for r in range(8)),'Independent integer/ELF result equality')
        sites.append(memory);items.append(item)
    return symbols,data,sites,items


def regions(phase,symbols,data,items):
    require(phase in (0,1),'Exact two phases');fixtures=recipe.fixture();w,a,gold,_=fixtures[phase]
    frame=struct.pack('<16I',*[0x13570000+i for i in range(16)])+gold+struct.pack('<16I',*[0x24680000+i for i in range(16)])
    csr=struct.pack('<20Q',*[0x1234567800000000+i for i in range(4)],*([8,16,0,2,8,5]*2),*[0x8765432100000000+i for i in range(4)])
    # Bind ABI values, including its non-sequential Q2 code7/Q6 code2.
    abi=life.ROOT/'apps/common/qbs_abi.h'
    text=abi.read_text()
    version=int(re.search(r'#define\s+QBS_DESCRIPTOR_VERSION\s+(\d+)u\b',text)[1])
    wp=int(re.search(r'QBS_WEIGHT_PROFILE_'+('Q6_K' if phase else 'Q2_K')+r'\s*=\s*(\d+)',text)[1])
    ap=int(re.search(r'QBS_ACTIVATION_PROFILE_Q8_K\s*=\s*(\d+)',text)[1])
    require(version==2 and wp==(2 if phase else 7) and ap==1,'Exact corrected ABI profile/version')
    header=version|(wp<<4)|(ap<<8)|(1<<12)|(1<<16)|(7<<20)|(1<<25)
    desc=b'\xc3'*64+struct.pack('<QQ',header,symbols['weight'+str(phase)][0]+74)+b'\xc3'*64
    result={'frame'+str(phase):frame,'csr'+str(phase):csr,'desc'+str(phase):desc}
    for p,(w,a,_,_) in enumerate(fixtures):result.update({f'weight{p}':w,f'activation{p}':a})
    require(all(symbols[name][1]==len(value) for name,value in result.items()),'Full checkpoint/guard region extents')
    return result


def software(log):
    source=inspect.getsource(core.software)
    old="lines.count('QBS_PENDING checks=6 errors=0')==1 and\n        lines.count('PASSED: qbs_k2_row_pending781 commands=1 errors=0')==1"
    new="lines.count('QBS_TWO_PHASE phase=0 checks=6 errors=0')==1 and lines.count('QBS_TWO_PHASE phase=1 checks=12 errors=0')==1 and lines.count('PASSED: qbs_pending_two_phase783 commands=2 errors=0')==1"
    require(source.count(old)==1,'Exact terminal label adaptation');source=source.replace(old,new)
    ns=dict(vars(core));exec(compile(source,'<two-M4-terminal>','exec'),ns);return ns['software'](log)


def runtime(run):
    require(life.digest(Path(core.native.__file__))==core.NATIVE_SHA,'Frozen lifecycle comparator')
    symbols,data,sites,items=elf_view();source=inspect.getsource(core.native.runtime)
    old="symbols['gap110_qbexec_site%d'%phase]";new="symbols['matrix_qbexec_site%d'%phase]"
    require(source.count(old)==1,'Exact two-site adaptation');source=source.replace(old,new)
    ns=dict(vars(core.native),WORD=WORD,software=software,seed_image=lambda phase:recipe.frozen.old.seed_bytes(),
        regions=regions,custom_expected=core.custom_expected,activity_bytes=core.activity_bytes,
        phase_readback=lambda rows,begin,end,symbols,expected:core.matrix.readback(rows,begin,end,symbols,expected,data))
    exec(compile(source,'<two-M4-all18-lifecycle>','exec'),ns)
    with (run/'commit_trace.csv').open() as stream:
        require(all(r['event']!='retire' or int(r['insn'],16)&0x7f!=0x2f for r in csv.DictReader(stream)),'No AMO ambiguity')
    result=ns['runtime'](run,symbols,data,sites,items)
    require(len(result['bindings'])==2,'Two complete native owners')
    for binding in result['bindings']:
        binding.update(backend_vl=128,native_active_write_bytes=128,native_total_write_bytes=512,preserved_vrf_bytes=3584)
        counts=binding['readback_bytes']
        require(sum(v for k,v in counts.items() if k.startswith(('weight','activation')))==12416,'All sources read at each checkpoint')
    result.update(status='TWO_M4_NATIVE_VRF_CSR_ALL_SOURCE_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA',
        custom_write_bytes=1024,custom_active_bytes=256,custom_zero_tail_bytes=768,
        custom_preserved_vrf_bytes=7168,full_vrf_bytes=8192,initial_vrf_bytes=8192,
        csr_values=24,source_guard_bytes=24832,checks=12)
    return result


def cycle_review(vcd):
    symbols,data,sites,items=elf_view();aliases=dict(symbols,activation=symbols['activation0'])
    oldcase=SimpleNamespace(elf_view=lambda:(aliases,data,sites,items),recipe=SimpleNamespace(fixture=lambda:recipe.fixture()[0]))
    first=FunctionType(cycle_core.cycles.__code__,dict(vars(cycle_core),case=oldcase))(vcd)
    scan=FunctionType(cycle_core.parser.vcd.__code__,dict(vars(cycle_core.parser),ROOT='ara_tb',WIDTHS={'clk':1,'rst_n':1}))
    iterator=iter(scan(vcd));_,decl=next(iterator)
    adapter=cycle_core.ADAPTER;root=cycle_core.ROOT+'.i_read_engine.'
    names=dict(clk='ara_tb.clk',reset='ara_tb.rst_n',hit=cycle_core.PAYLOAD+'.gen_write_merge[0].gen_bank_plane[2].gen_bank_row[2].gen_byte_merge[5].hit')
    for k,name in dict(valid='activation_pending_q_valid',ctx='activation_pending_q.ctx',offset='activation_pending_q.offset',
        strb='activation_pending_q.strb',data='activation_pending_q.data',source='activation_source_valid',
        remaining='activation_remaining',count='activation_ingress_count_q',push='activation_ingress_push',clear='clear_activation_i').items():names[k]=adapter+'.'+name
    for k,name in dict(cursor='response_head.cursor_vaddr',target='data_tag_o.target',kblock='data_tag_o.k_block',
        input_offset='data_offset_o',input_strb='data_strb_o',take='beat_take_bytes',dv='data_valid_o',dr='data_ready_i').items():names[k]=root+name
    require(all(n in decl for n in names.values()),'Full-wave actual typed fields')
    codes={k:decl[n]['code'] for k,n in names.items()}
    def get(s,k):
        x=s.get(codes[k],'x');require(not set(x)-set('01'),'Unknown used cycle field '+k);return int(x,2)
    fifo=deque();retained=None;mask=0;valid=0;last_hit=None;events=[];captures=[];last=None;edges=0
    for time,before,after in iterator:
        if before.get(codes['clk'])!='0' or after.get(codes['clk'])!='1':continue
        if before.get(codes['reset'])!='1':fifo.clear();retained=None;mask=valid=0;last_hit=None;continue
        edges+=1;src=get(before,'source');clear=get(before,'clear');pending=get(before,'valid')
        require(get(before,'count')==len(fifo),'Full-wave FIFO count conservation')
        require(pending==valid,'Exact pending_valid recurrence')
        if retained:
            require(get(before,'ctx')==retained['ctx'] and get(before,'offset')==retained['offset'] and
                get(before,'strb')==mask and get(before,'data')==retained['data'],'Retained pending source/metadata recurrence')
        owner=None
        if src&2:require(fifo,'No accepted source1 owner');owner=fifo.popleft()
        if get(before,'push'):
            require(get(before,'dv')==get(before,'dr')==1,'Accepted native producer')
            address=get(before,'cursor');ctx=get(before,'target');k=get(before,'kblock');offset=get(before,'input_offset');take=get(before,'take');strb=get(before,'input_strb')
            choices=[p for p in (0,1) if address==symbols['activation'+str(p)][0]+(76 if p else 64)+(2*ctx+k)*292+offset]
            require(len(choices)==1 and ctx<4 and k<2 and 0<take<=16 and strb==(1<<take)-1,'Exact phase/ctx/k/cursor owner')
            phase=choices[0];array=recipe.fixture()[phase][1];start=address-symbols['activation'+str(phase)][0]
            payload=array[start:start+take]+bytes(16-take)
            require(len(payload)==16,'Producer source extent')
            fifo.append(dict(phase=phase,ctx=ctx,k=k,offset=offset,strb=strb,data=int.from_bytes(payload,'little'),accepted_time=time))
        hit=get(before,'hit')>>13&1
        if last_hit is not None and hit!=last_hit:events.append(dict(time_100fs=time,from_value=last_hit,to_value=hit,retained_owner=retained,mask=mask))
        last_hit=hit;remaining=get(before,'remaining') if src else None
        if src&2 and remaining>>16:
            require(owner is not None and (remaining>>16)&~owner['strb']==0,'Partial pending subset of exact accepted beat')
            retained=owner;mask=remaining>>16;captures.append(dict(time_100fs=time,owner=owner,mask=mask))
        elif src==1:mask=remaining&0xffff
        if clear:valid=0;fifo.clear()
        elif src&2:valid=bool(remaining>>16)
        elif src&1:valid=bool(remaining&0xffff)
        last=dict(time_100fs=time,pending_valid=pending,source_valid=src,hit13=hit,retained_owner=retained,mask=mask)
    falls=[e for e in events if e['from_value']==1 and e['to_value']==0]
    return dict(status='TWO_PHASE_FULL_WAVE_FIFO_SOURCE_RECURRENCE_VERIFIED',first_proved_Q2_witness=first,
        checked_rising_edges=edges,transitions=events,partial_captures=captures,last_sample=last,
        phase1_different_context_partial_captured=any(c['owner']['phase']==1 and c['owner']['ctx']!=2 for c in captures),
        hit13_falling_observed=bool(falls),falling_hypothesis_not_guaranteed=True,
        boundary='Actual pending fields/FIFO producer owner. Per-byte target/location/write_req not directly captured; their overwrite is source-inferred. Not timestamp shifted.')


def raw_gain(run,record):
    base=life.read_bound(runner.BASE/'admission-manifest.json',runner.BASE_SHA)
    before=life.read_bound(runner.BASE/'combined-bits.json',base['output_pins'][str(runner.BASE/'combined-bits.json')])
    ledger=(runner.BASE/'combined-inputs.txt').read_text().splitlines()
    require(ledger==[str(life.IMAGE)+'.vdb',*before['tests']] and len(before['tests'])==len(set(before['tests']))==783,'Exact783 input population')
    files=list((run/'code.vdb/snps/coverage/db/testdata').iterdir());require(len(files)==1 and files[0].name==runner.NAME,'Unique native sample')
    folder=files[0];design=Path(ledger[0])/'snps/coverage/db'
    for rel,h in before['design'].items():require(life.digest(design/rel)==h,'Compile design fingerprint')
    identity=FunctionType(runner.admission.native_identity.__code__,dict(vars(runner.admission),RUN=run))(
        toggle.xml(folder/'siminfo.xml'),toggle.xml(folder/'vcmArguments.xml'),record,ledger[0])
    single=dict(design=before['design'],tests=[str(run/'code.vdb')],input_hashes={},metrics={})
    for m in bitmap.METRICS:
        p=folder/(m+'.verilog.data.xml');single['metrics'][m]=bitmap.read_metric(p);single['input_hashes'][str(p)]=life.digest(p)
    after=bitmap.combine(before,single)
    require(sum(map(len,after['metrics'].values()))==6162 and all(len(before['metrics'][m])==runner.admission.COUNTS[m] for m in bitmap.METRICS),'Full6162 shape/OR')
    delta=bitmap.delta(before,after)
    gain_path=runner.BASE/'qbs-k2-payload-toggle-gain782.json'
    old=life.read_bound(gain_path,base['output_pins'][str(gain_path)])
    sample,_=toggle.rows(folder/'tgl.verilog.data.xml',list(old['combined_rows']))
    joined=toggle.union(old['combined_rows'],sample);gains=toggle.gains(old['combined_rows'],joined)
    return dict(baseline=783,baseline_seal=runner.BASE_SHA,native_identity=identity,single_bits=single,
        full_raw_delta=delta,scoped_payload_new_coordinates=gains,new_payload_directions=sum(map(len,gains.values())),
        source_mapping_bound_is_not_measured_gain=True,official_percentage=False)


def collect(run,seal,out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh qualification')
    prepared=run.with_name(run.name+'.prepared.json');record=life.read_bound(prepared,seal)
    runner.validate(record['preflight'])
    require(record['collector_ready'] is True and record['command']==runner.command(run) and
        record['baseline_seal']==runner.BASE_SHA and record['timeout_s']==600,'Exact new run contract')
    require(record['pins'].get(str(Path(__file__).resolve()))==life.digest(Path(__file__)),'Collector run pin')
    status,sha=core.native.terminal(run)
    require(life.read_bound(run/'manifest.json',life.digest(run/'manifest.json'))==record,'Executed exact manifest')
    started=json.loads((run/'started.json').read_text())
    require(started['command']==record['command'] and started['input_elf']==str(runner.ELF) and
        started['elf_sha256']==runner.ELF_SHA and started['image_sha256']==runner.old.old.IMAGE_SEAL and
        started['image']==str(life.IMAGE) and started['budget_s']==600 and type(started['pid']) is int,'Actual start image/ELF/budget')
    files=[run/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','trace_hart_0.log',WAVE)]
    files.extend(p for p in (run/'code.vdb').rglob('*') if p.is_file())
    require(not any(p.is_symlink() for p in (run/'code.vdb').rglob('*')),'No redirected native files')
    pins=life.merge_pins(record['pins'],{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(prepared):seal,str(status):sha});life.check(pins)
    out.mkdir();life.save(out/'evidence-pins.json',pins)
    try:
        require('Exception' not in (run/'trace_hart_0.log').read_text(),'Unexpected hart exception')
        console=(run/'console.log').read_text();require(console.splitlines().count('QBS_TWO_PHASE_PROBE_READY')==1 and
            not re.search(r'^\s*(?:QBS_TWO_PHASE_PROBE_REJECT\b|UCLI_ERROR\b|Error-)',console,re.M),'Actual probe READY/errors')
        wave=run/WAVE;require(0<wave.stat().st_size<=record['wave_byte_limit'],'64MiB VPD limit')
        audit=runtime(run);life.save(out/'runtime-audit.json',audit)
        vcd=out/'pending.vcd'
        result=subprocess.run([runner.CONVERTER,'+splitpacked',wave,vcd],capture_output=True,timeout=120)
        (out/'converter.log').write_bytes(result.stdout+result.stderr)
        require(result.returncode==0 and vcd.is_file(),'Actual VPD conversion')
        proof=cycle_review(vcd);life.save(out/'cycle-proof.json',proof)
        gain=raw_gain(run,record);life.save(out/'raw-gain.json',gain);life.check(pins)
        output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        qualified=dict(status='TWO_M4_FUNCTIONAL_NATIVE_CYCLE_AND_RAW_QUALIFIED_NOT_ADMITTED',
            input_pins=pins,output_pins=output_pins,baseline=783,baseline_seal=runner.BASE_SHA,
            actual_payload_gain=gain['new_payload_directions'],hit13_falling_observed=proof['hit13_falling_observed'],
            scalar_spike_verified=False,full_scalar_ISA_verified=False,custom_spike_pass=False,
            coverage_admitted=False,new_simulation=False,RTL_changed=False)
        life.save(out/'qualification.json',qualified)
        return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=qualified['status'],gain=gain['new_payload_directions'])
    except Exception as error:
        life.save(out/'qualification.json',dict(status='TWO_M4_QUALIFICATION_HOLD_NOT_ADMITTED',reason=type(error).__name__+': '+str(error),coverage_admitted=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(collect(a.run.resolve(),a.prepared_seal,a.output.resolve())),flush=True)
