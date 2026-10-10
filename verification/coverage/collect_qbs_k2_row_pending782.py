"""One-command dimension adapter over the reviewed positive native lifecycle checker."""
import argparse
import csv
import inspect
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

import run_qbs_k2_row_pending782 as runner
import qualify_gap110_native_v2 as native
import qualify_qbs_payload_matrix4_uart as matrix
import targeted_toggle_evidence as toggle
sys.path.insert(0,str(runner.life.ROOT/'verification/tests'))
import build_qbs_k2_row_pending781 as recipe

life,require=runner.life,native.require
WORD=recipe.WORD
NATIVE_SHA='a721d950834d863b069c78ded382b3ae6e36a8e0841f201c850a6bd20699c691'
SCOPE='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine.i_block_adapter_bank0.i_payload_buffer'


def observer_pins():
    pins=matrix.source_observer_contract()['pins']
    book=life.read_bound(native.BUILD,native.BUILD_SHA)
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    require(book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]==native.DISPATCHER_SHA,'Frozen dispatcher book')
    pins=life.merge_pins(pins,{str(dispatcher):native.DISPATCHER_SHA})
    for name in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
        path=life.ROOT/name;pins=life.merge_pins(pins,{str(path):book[str(path)]})
    return pins


def software(log):
    text=log.read_text();lines=text.splitlines()
    require(lines.count('QBS_PENDING checks=6 errors=0')==1 and
        lines.count('PASSED: qbs_k2_row_pending781 commands=1 errors=0')==1,'Full software check labels')
    require(text.count('Core Test *** SUCCESS ***')==1 and not native.support.check_contract_log(log),'TB contract/success')
    require(not re.search(r'FAILED|\bFAIL\b|Error:|Fatal:|Exception|invalid instructions',text),'Unexpected diagnostic')
    for severity in ('UVM_ERROR','UVM_FATAL','UVM_WARNING'):
        require(re.findall(r'^\s*'+severity+r'\s*:\s*(\d+)\s*$',text,re.M)==['0'],'UVM summary '+severity)
        require(not re.search(r'^'+severity+r'\s+(?!:)',text,re.M),'UVM message '+severity)
    contracts=[native.support.parse_contract_summary(s) for s in lines if '[ARA_CONTRACT]' in s]
    require(len(contracts)==1 and contracts[0] is not None,'Unique terminal contract')
    c=contracts[0]
    require(c['requests']==c['responses'] and c['requests']>0 and
        all(c[k]==0 for k in ('exceptions','protocol_errors','outstanding','req_stalled','resp_stalled')),'Clean positive contract')
    return c


def elf_view():
    meta=json.loads((runner.PRE/'dut.metadata.log').read_bytes())[0];symbols={}
    for row in meta['Symbols']:
        s=row['Symbol'];name=s['Name']['Name']
        if name and not name.startswith('$'):
            require(name not in symbols,'Duplicate ELF symbol');symbols[name]=(s['Value'],s['Size'])
    blob=runner.ELF.read_bytes()
    def data(address,size):
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=address and address+size<=r['Section']['Address']+r['Section']['Size']]
        require(len(sections)==1,'Unique ELF bytes');s=sections[0];offset=s['Offset']+address-s['Address']
        raw=blob[offset:offset+size];require(len(raw)==size,'Truncated ELF');return raw
    w,a,gold,dots=recipe.fixture()
    for name,value in [('weight',w),('activation',a),('gold',gold),('seed',recipe.seed_bytes()),
        ('weight_expected',w),('activation_expected',a)]:
        address,size=symbols[name];require(size==len(value) and data(address,size)==value,'ELF fixture '+name)
    address,size=symbols['matrix_exec0'];raw=data(address,size);pos=0;memory=[]
    while pos<size:
        width=4 if int.from_bytes(raw[pos:pos+2],'little')&3==3 else 2
        require(pos+width<=size,'Complete instruction');word=int.from_bytes(raw[pos:pos+width],'little')
        if width==4 and word&0x7f in (7,39) and word>>12&7==6:
            memory.append(dict(pc=address+pos,word=word,store=word&0x7f==39,register=word>>7&31))
        pos+=width
    require([(s['store'],s['register']) for s in memory]==[(False,r) for r in (0,8,16,24)]+[(True,r) for r in (0,8,16,24)],'Exact ordinary vle32 seed/snapshot')
    require(int.from_bytes(data(symbols['matrix_qbexec_site0'][0],4),'little')==WORD,'One M4 word')
    item=dict(n=8,result_bits=[native.integer_single(d) for d in dots],integer_dots=dots,fflags=0)
    require(all(struct.unpack_from('<I',gold,1024+128*c+4*r)[0]==item['result_bits'][8*c+r]
        for c in range(4) for r in range(8)),'Integer/ELF result equality')
    return symbols,data,[memory],[item]


def regions(phase,symbols,data,items):
    require(phase==0,'One command');w,a,gold,_=recipe.fixture()
    frame=struct.pack('<16I',*[0x13570000+i for i in range(16)])+gold+struct.pack('<16I',*[0x24680000+i for i in range(16)])
    csr=struct.pack('<20Q',*[0x1234567800000000+i for i in range(4)],*([8,16,0,2,8,5]*2),*[0x8765432100000000+i for i in range(4)])
    header=2|(7<<4)|(1<<8)|(1<<12)|(1<<16)|(7<<20)|(1<<25)
    desc=b'\xc3'*64+struct.pack('<QQ',header,symbols['weight'][0]+74)+b'\xc3'*64
    result=dict(frame=frame,csr=csr,desc=desc,weight=w,activation=a)
    require(all(symbols[n][1]==len(v) for n,v in result.items()),'Full region shapes')
    return result


def custom_expected(item):
    require(len(item['result_bits'])==32 and item['n']==8,'M4/N8 results')
    return {(8+c,b):((item['result_bits'][8*c+b//4]>>(8*(b%4)))&255) if b<32 else 0
        for c in range(4) for b in range(128)}


def activity_bytes(activity,expected,start,done,custom=False):
    native.support.activity_bytes(activity,expected,start,done)
    if custom:
        require((activity.instruction,activity.vd,activity.vl)==(WORD,8,128) and len(expected)==512,'M4 backend full group')
        observed={}
        for w in activity.writes:
            require((w.lane,w.addr) not in observed,'Duplicate native write');observed[w.lane,w.addr]=w.be
        require(observed=={(lane,4*reg+word):255 for reg in range(8,12) for word in range(4) for lane in range(4)},'M4 full masks/addresses')


def runtime(run):
    require(life.digest(Path(native.__file__))==NATIVE_SHA,'Frozen native comparator')
    source=inspect.getsource(native.runtime)
    edits=[('for phase in (0,1):','for phase in (0,):',2),('for p in (0,1)','for p in (0,)',1),
        ("symbols['gap110_qbexec_site%d'%phase]","symbols['matrix_qbexec_site%d'%phase]",1),
        ('len(selected)==18','len(selected)==9',1),
        ('starts[selected[9]][2] if phase==0 else max(int(r[\'cycle\']) for r in rows)+1',"max(int(r['cycle']) for r in rows)+1",1),
        ('sum(a.instruction==WORD for a in activities.values())==2','sum(a.instruction==WORD for a in activities.values())==1',1)]
    for old,new,count in edits:
        require(source.count(old)==count,'Exact single-command adaptation '+old);source=source.replace(old,new)
    symbols,data,sites,items=elf_view()
    ns=dict(vars(native),WORD=WORD,software=software,seed_image=lambda phase:recipe.seed_bytes(),
        regions=regions,custom_expected=custom_expected,activity_bytes=activity_bytes,
        phase_readback=lambda rows,begin,end,symbols,expected:matrix.readback(rows,begin,end,symbols,expected,data))
    exec(compile(source,'<one-M4-positive-native-adapter>','exec'),ns)
    with (run/'commit_trace.csv').open() as f:
        require(all(r['event']!='retire' or int(r['insn'],16)&0x7f!=0x2f for r in csv.DictReader(f)),'No AMO observer ambiguity')
    result=ns['runtime'](run,symbols,data,sites,items)
    require(len(result['bindings'])==1,'One native command')
    result['bindings'][0].update(backend_vl=128,native_active_write_bytes=128,native_total_write_bytes=512,preserved_vrf_bytes=3584)
    result.update(status='M4_K2_FULL_NATIVE_VRF_CSR_SOURCE_LIFECYCLE_PASS_NOT_FULL_ISA',custom_write_bytes=512,
        custom_active_bytes=128,custom_zero_tail_bytes=384,custom_preserved_vrf_bytes=3584,
        full_vrf_bytes=4096,initial_vrf_bytes=4096,csr_values=12,source_guard_bytes=4032,checks=6)
    return result


def collect(run,seal,out):
    require(out.parent==life.OUT and out.resolve()==out and not out.exists(),'Fresh qualification')
    prepared=run.with_name(run.name+'.prepared.json');record=life.read_bound(prepared,seal)
    runner.validate(record['preflight'])
    require(record['command']==runner.command(run) and record['baseline_seal']==runner.BASE_SHA and
        record['timeout_s']==600,'Exact approved execution')
    status,status_sha=native.terminal(run)
    require(json.loads((run/'manifest.json').read_bytes())==record,'Actual manifest')
    start=json.loads((run/'started.json').read_bytes())
    require(start['command']==record['command'] and start['elf_sha256']==runner.ELF_SHA and
        start['image_sha256']==runner.old.IMAGE_SEAL and start['budget_s']==600 and
        start['input_elf']==str(runner.ELF) and start['image']==str(life.IMAGE),'Actual execution identity')
    files=[run/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','trace_hart_0.log','qbs-k2-row-pending.vpd')]
    files+=[p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    pins=life.merge_pins(record['pins'],{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(prepared):seal,str(status):status_sha})
    life.check(pins);audit=runtime(run)
    require('Exception' not in (run/'trace_hart_0.log').read_text(),'Unexpected hart exception')
    console=(run/'console.log').read_text()
    require(console.splitlines().count('QBS_PENDING_PROBE_READY')==1 and
        not re.search(r'QBS_PENDING_PROBE_REJECT|UCLI_ERROR|Error-',console),'Actual focused probe')
    wave=run/'qbs-k2-row-pending.vpd'
    require(0<wave.stat().st_size<=record['wave_byte_limit'],'64MiB VPD bound')
    samples=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(samples)==1 and samples[0].parent.name==runner.NAME,'Unique native sample')
    rows,_=toggle.rows(samples[0],[SCOPE]);row=rows[SCOPE]
    require(row['width']==66340 and row['checksum']=='3657545390','Native payload identity')
    targets={str(c):bool(int(row['bits'],16)>>(row['width']-1-c)&1) for c in (21532,21533)}
    life.check(pins);out.mkdir();life.save(out/'runtime-audit.json',audit)
    result=dict(status='FUNCTIONAL_NATIVE_QUALIFIED_CYCLE_PROFILE_REVIEW_REQUIRED_NOT_ADMITTED',input_pins=pins,
        output_pins={str(out/'runtime-audit.json'):life.digest(out/'runtime-audit.json')},baseline=782,
        baseline_seal=runner.BASE_SHA,primary_target_sample=targets,conditional_prediction_directions=222,
        measured_total_gain=None,cycle_witness_verified=False,focused_vpd=str(wave),
        full_scalar_isa_verified=False,custom_spike_pass=False,coverage_admitted=False,
        note='Functional gates complete; VPD pending-owner/word arbitration must be independently inspected. Target sample alone is not fresh OR gain or a cycle proof.')
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'],primary_sample=targets)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(collect(a.run.resolve(),a.prepared_seal,a.output.resolve())),flush=True)
