"""Four-job native gold/readback/lifecycle audit; measured Toggle, no admission."""
import argparse
import csv
import inspect
import json
from pathlib import Path
import re
import struct
import sys
import run_qbs_payload_matrix4_uart as runner
import qualify_gap113_payload_full8 as full8
import targeted_toggle_evidence_v2 as toggle
sys.path.insert(0,str(runner.life.ROOT/'verification/tests'))
import build_qbs_payload_matrix4 as recipe

life,require=runner.life,full8.require
RUN=life.OUT/'qbs-payload-matrix4-uart-old-image-agent-20261007-01'
RUN_SHA='2e1a229bfd0ca211fba6ea45ac77613300a87774f018bb543da874c01297c469'
BASE=life.OUT/'vmfpu-ured-reset-offline-admitted-765-agent-20261007-01'
BASE_SHA='834b457b607b9b73b21e4e2c8decaf5140d8e23cd8cc04c04bc7267d592d757c'
BASE764=life.OUT/'qbs-payload-phase-offline-admitted-764-agent-20261007-01'
BASE764_SHA='167f82e2a614e34e7dd8606bdb9211370cb573ebc0ad414baa99f7da355398f1'


def software(log):
    text=log.read_text();lines=text.splitlines()
    wanted=['QBS_MATRIX phase=%d checks=%d errors=0'%(i,6*(i+1)) for i in range(4)]
    wanted+=['PASSED: qbs_payload_matrix4 commands=4 errors=0']
    require(all(lines.count(s)==1 for s in wanted), 'Missing/duplicate complete matrix software checks')
    require(text.count('Core Test *** SUCCESS ***')==1 and not full8.inherited.support.check_contract_log(log),
            'TB success/contract failed')
    require(not re.search(r'FAILED|\bFAIL\b|Error:|Fatal:|Exception|invalid instructions',text), 'Unexpected run diagnostic')
    for severity in ('UVM_ERROR','UVM_FATAL','UVM_WARNING'):
        matches=re.findall(r'^\s*'+severity+r'\s*:\s*(\d+)\s*$',text,re.M)
        require(matches==['0'], 'Missing/nonzero UVM severity summary')
        require(not re.search(r'^'+severity+r'\s+(?!:)',text,re.M), 'UVM message not just summary')
    contracts=[full8.inherited.support.parse_contract_summary(s) for s in lines if '[ARA_CONTRACT]' in s]
    require(len(contracts)==1 and contracts[0] is not None, 'Unique complete contract')
    runner.reused.exact(contracts[0],dict(requests=92,responses=92,exceptions=0,
        protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0),'Matrix terminal contract')
    return contracts[0]


def unpack(weight,activation):
    require(len(weight)==1680 and len(activation)==2336, 'Native Q6/Q8_K extents')
    contexts=[]
    for c in range(8):
        require(struct.unpack_from('<I',activation,4*c)[0]==0x3f800000, 'Unit activation scale')
        qs=[int.from_bytes(activation[32+8*i+c:33+8*i+c],'little',signed=True) for i in range(256)]
        for g in range(16):
            require(sum(qs[16*g:16*g+16])==struct.unpack_from('<h',activation,2080+16*g+2*c)[0], 'Independent bsum')
        contexts.append(qs)
    dots=[]
    for c in range(8):
        for r in range(8):
            row=weight[210*r:210*(r+1)]
            require(struct.unpack_from('<H',row,208)[0]==0x3c00, 'Unit Q6 scale')
            dot=0
            for i in range(256):
                half,rem=divmod(i,128);quarter,lane=divmod(rem,32)
                low=(row[64*half+32*(quarter&1)+lane]>>(4*(quarter//2)))&15
                high=(row[128+32*half+lane]>>(2*quarter))&3
                scale=int.from_bytes(row[192+i//16:193+i//16],'little',signed=True)
                dot+=((low|(high<<4))-32)*scale*contexts[c][i]
                require(abs(dot)<2**23, 'Exact integer FP32 intermediate bound')
            dots.append(dot)
    return dict(n=8,result_bits=[full8.inherited.integer_single(d) for d in dots],integer_dots=dots,fflags=0)


def elf_view():
    meta=json.loads((runner.PRE/'dut.metadata.log').read_bytes())[0]
    symbols={}
    for r in meta['Symbols']:
        s=r['Symbol'];name=s['Name']['Name']
        if name and not name.startswith('$'):
            require(name not in symbols,'Ambiguous ELF symbol '+name);symbols[name]=(s['Value'],s['Size'])
    blob=(runner.PRE/(runner.NAME+'.elf')).read_bytes()
    def data(address,size):
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
            r['Section']['Address']<=address and address+size<=r['Section']['Address']+r['Section']['Size']]
        require(len(sections)==1,'Unique ELF bytes');s=sections[0];offset=s['Offset']+address-s['Address']
        raw=blob[offset:offset+size];require(len(raw)==size,'Truncated ELF');return raw
    sites=[];native=[]
    for phase in range(4):
        w,a,gold=recipe.fixture(phase)
        for name,expected in [('weight%d'%phase,w),('activation%d'%phase,a),
                              ('gold%d'%phase,recipe.expected_frame(phase)),('seed',recipe.seed_bytes())]:
            address,size=symbols[name];require(size==len(expected) and data(address,size)==expected,'Frozen ELF source/gold '+name)
        item=unpack(w[64+recipe.WP[phase]:64+recipe.WP[phase]+1680],
                    a[64+recipe.AP[phase]:64+recipe.AP[phase]+2336])
        require(item['result_bits']==gold, 'Independent native unpack/logical gold differs')
        native.append(item)
        address,size=symbols['matrix_exec%d'%phase];raw=data(address,size);offset=0;memory=[]
        while offset<size:
            width=4 if int.from_bytes(raw[offset:offset+2],'little')&3==3 else 2
            require(offset+width<=size,'Complete instruction')
            word=int.from_bytes(raw[offset:offset+width],'little')
            if width==4 and word&0x7f in (7,39) and word>>12&7==6:
                memory.append(dict(pc=address+offset,word=word,store=word&0x7f==39,register=word>>7&31))
            offset+=width
        require([(s['store'],s['register']) for s in memory]==[(False,r) for r in (0,8,16,24)]+[(True,r) for r in (0,8,16,24)], 'Exact seed/snapshot ELF')
        require(int.from_bytes(data(symbols['matrix_qbexec_site%d'%phase][0],4),'little')==full8.WORD,'Exact M8 ELF opcode')
        sites.append(memory)
        for name,base_name,step,length in [('frame','frames',4224,4224),('csr','csrs',160,160),('desc','descriptors',144,144)]:
            require(symbols[base_name][1]==step*4,'Full struct population')
            symbols[name+str(phase)]=(symbols[base_name][0]+phase*step,length)
    return symbols,data,sites,native


def regions(phase,symbols,data,native):
    header=2|(2<<4)|(1<<8)|(recipe.LAYOUT[phase]<<12)|(3<<16)|(7<<20)
    desc=b'\xc3'*64+struct.pack('<QQ',header,symbols['weight%d'%phase][0]+64+recipe.WP[phase])+b'\xc3'*64
    frame=struct.pack('<16I',*[0x13570000+i for i in range(16)])+recipe.expected_frame(phase)+struct.pack('<16I',*[0x24680000+i for i in range(16)])
    csr=struct.pack('<20Q',*[0x1234567800000000+i for i in range(4)],*([8,16,0,2,8,5]*2),*[0x8765432100000000+i for i in range(4)])
    w,a,_=recipe.fixture(phase)
    return {'frame'+str(phase):frame,'csr'+str(phase):csr,'desc'+str(phase):desc,
            'weight'+str(phase):w,'activation'+str(phase):a}


def source_observer_contract():
    build=life.read_bound(full8.inherited.BUILD,full8.inherited.BUILD_SHA)
    anchors={
        'hardware/deps/cva6/core/commit_stage.sv':[
            'wdata_o[0] = (CVA6Cfg.RVA && amo_resp_i.ack) ? amo_resp_i.result[CVA6Cfg.XLEN-1:0] : commit_instr_i[0].result;',
            'wdata_o[1]          = commit_instr_i[1].result;'],
        'hardware/deps/cva6/core/cva6.sv':['.wdata_o           (wdata_commit_id)', '.wdata_i     (wdata_commit_id)'],
        'hardware/deps/cva6/core/cva6_rvfi_probes.sv':['instr.wdata = wdata_i;'],
        'hardware/deps/cva6/core/cva6_rvfi.sv':['assign wdata = instr.wdata;',
            ')) ? commit_instr_result[i] : wdata[i];','rvfi_instr_o[i].rd_addr <= commit_instr_rd[i];',
            'rvfi_instr_o[i].mem_rmask <= mem_q[commit_pointer[i]].lsu_rmask;'],
        'hardware/tb/ara_commit_monitor.sv':['rvfi_instr_i[port].rd_wdata,','rvfi_instr_i[port].mem_rmask,']}
    pins={str(full8.inherited.BUILD):full8.inherited.BUILD_SHA}
    for rel,terms in anchors.items():
        path=life.ROOT/rel;expected=build[str(path)]
        require(life.digest(path)==expected,'Frozen RVFI observer source differs')
        text=path.read_text();require(all(text.count(t)==1 for t in terms),'Exact RVFI source anchors')
        pins[str(path)]=expected
    return dict(status='FROZEN_LOAD_RESULT_OBSERVER_NOT_X0_REGISTER_STATE',pins=pins,
        semantics='CSV rd_wdata carries commit-stage result through RVFI, without rd==0 zeroing. Only exact ELF LD x0 reads of sealed source images are admitted as memory observations; never as architectural x0 writes.')


def readback(rows,begin,end,symbols,expected,data):
    normal={k:v for k,v in expected.items() if not k.startswith(('weight','activation'))}
    result=full8.inherited.readback(rows,begin,end,symbols,normal)
    sources={k:v for k,v in expected.items() if k not in normal};seen={k:set() for k in sources}
    for row in rows:
        if row['event']!='retire' or not begin<=int(row['cycle'])<end:continue
        address=int(row['mem_addr'],16);mask=int(row['mem_rmask'],16)
        if not mask:continue
        word=int(row['insn'],16);access=full8.inherited.reviewed.scalar_access(word)
        require(access is not None and access[0]=='read','Unknown source read')
        size=access[1]
        for name,blob in sources.items():
            base=symbols[name][0]
            if address+size<=base or address>=base+len(blob):continue
            fpr,rd=full8.inherited.reviewed.load_destination(word)
            require(base<=address and address+size<=base+len(blob) and not int(row['trap']) and
                address%size==0 and mask==((1<<size)-1)<<(address&7) and int(row['rd'])==rd,'Source read extent/mask/owner')
            if not fpr and rd==0:
                require(word&0x707f==0x3003 and size==8 and
                    int.from_bytes(data(int(row['pc'],16),4),'little')==word,'Only exact ELF LD x0 source observer')
            value=int(row['rd_wdata'],16)&((1<<(8*size))-1);offset=address-base
            require(value.to_bytes(size,'little')==blob[offset:offset+size],'Independent sealed source readback differs')
            seen[name].update(range(offset,offset+size))
    for name,blob in sources.items():
        require(seen[name]==set(range(len(blob))),'Incomplete source observer readback '+name)
        result[name]=len(blob)
    return result


def runtime(run):
    original=full8.inherited
    require(life.digest(Path(original.__file__))=='a721d950834d863b069c78ded382b3ae6e36a8e0841f201c850a6bd20699c691','Frozen lifecycle/readback comparator drift')
    # Exact dimension/site adaptation only. All original lifecycle and byte gates are retained.
    source=inspect.getsource(original.runtime)
    edits=[('for phase in (0,1):','for phase in range(4):',2),
           ('for p in (0,1)','for p in range(4)',1),
           ("symbols['gap110_qbexec_site%d'%phase]","symbols['matrix_qbexec_site%d'%phase]",1),
           ('len(selected)==18','len(selected)==36',1),
           ('retire_cycles[selected[8]]','retire_cycles[selected[phase*9-1]]',1),
           ('starts[selected[9]][2] if phase==0','starts[selected[(phase+1)*9]][2] if phase<3',1),
           ('sum(a.instruction==WORD for a in activities.values())==2','sum(a.instruction==WORD for a in activities.values())==4',1)]
    for old,new,count in edits:
        require(source.count(old)==count,'Exact immutable runtime adaptation anchor');source=source.replace(old,new)
    observer=source_observer_contract()
    symbols,data,sites,native=elf_view()
    ns=dict(vars(original),software=software,WORD=full8.WORD,seed_image=lambda phase:recipe.seed_bytes(),
            activity_bytes=full8.activity_bytes,custom_expected=full8.custom_expected,
            phase_readback=lambda rows,begin,end,symbols,expected:readback(rows,begin,end,symbols,expected,data),regions=regions)
    exec(compile(source,'<matrix4-exact-lifecycle-successor>','exec'),ns)
    with (run/'commit_trace.csv').open() as f:
        require(all(r['event']!='retire' or int(r['insn'],16)&0x7f!=0x2f for r in csv.DictReader(f)),
                'Source observer scope excludes AMO result multiplexing')
    result=ns['runtime'](run,symbols,data,sites,native)
    require(len(result['bindings'])==4,'Full four commands')
    for b in result['bindings']:
        b.update(backend_vl=256,native_active_write_bytes=256,native_total_write_bytes=256,preserved_vrf_bytes=3840)
    result.update(status='MATRIX4_COMPLETE_NATIVE_VRF_CSR_GUARDS_LIFECYCLE_NOT_FULL_SCALAR_ISA',
                  custom_write_bytes=1024,custom_active_bytes=1024,custom_preserved_vrf_bytes=15360,
                  full_vrf_bytes=16384,initial_vrf_bytes=16384,csr_values=48,source_guard_bytes=18176,checks=24,
                  source_observer_contract=observer)
    return result


def collect(out):
    require(out.parent==life.OUT and not out.exists() and out.resolve()==out,'Fresh qualification output')
    prepared=RUN.with_name(RUN.name+'.prepared.json');record=life.read_bound(prepared,RUN_SHA)
    runner.validate(record['preflight']);require(record['timeout_s']==600 and record['case']==runner.NAME,'Exact run')
    status,status_sha=full8.inherited.terminal(RUN)
    require(json.loads((RUN/'manifest.json').read_bytes())==record,'Executed manifest differs')
    start=json.loads((RUN/'started.json').read_bytes())
    require(start['command']==record['command'] and start['budget_s']==600 and
            start['elf_sha256']==runner.ELF_SHA and start['image_sha256']==runner.reused.IMAGE_SEAL and
            start['input_elf']==str(runner.PRE/(runner.NAME+'.elf')) and start['image']==str(life.IMAGE),'Execution identity')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    old=life.read_bound(BASE764/'admission-manifest.json',BASE764_SHA)
    require(base['baseline']==str(BASE764) and base['baseline_seal']==BASE764_SHA and base['coverage_admitted'] is True,'Exact765 predecessor')
    before=life.read_bound(BASE764/'scoped-toggle-gain.json',old['output_pins'][str(BASE764/'scoped-toggle-gain.json')])['combined_rows']
    scopes=sorted(before)
    before_bits=life.read_bound(BASE/'combined-bits.json',base['output_pins'][str(BASE/'combined-bits.json')])
    old_bits=life.read_bound(BASE764/'combined-bits.json',old['output_pins'][str(BASE764/'combined-bits.json')])
    require(before_bits['tests'][:-1]==old_bits['tests'] and len(set(before_bits['tests']))==765,'Exact765 membership')
    files=[RUN/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','trace_hart_0.log')]
    files += [p for p in (RUN/'code.vdb').rglob('*') if p.is_file()]
    suffix=list((Path(before_bits['tests'][-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(suffix)==1,'Unique765 Toggle suffix');files+=suffix
    pins=life.merge_pins(record['pins'],{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(prepared):RUN_SHA,str(status):status_sha,str(BASE/'admission-manifest.json'):BASE_SHA,
         str(BASE764/'admission-manifest.json'):BASE764_SHA})
    pins=life.merge_pins(pins,life.merge_pins(base['output_pins'],old['output_pins']))
    pins=life.merge_pins(pins,source_observer_contract()['pins'])
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and str(Path(file).resolve()).startswith(str(life.ROOT/'verification')+'/') and Path(file).suffix=='.py':
            p=Path(file).resolve();pins=life.merge_pins(pins,{str(p):life.digest(p)})
    test=Path(__file__).with_name('test_qualify_qbs_payload_matrix4_uart.py');pins[str(test)]=life.digest(test)
    life.check(pins)
    audit=runtime(RUN)
    require('Exception' not in (RUN/'trace_hart_0.log').read_text(),'Unexpected hart exception')
    sample_files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(sample_files)==1 and sample_files[0].parent.name==runner.NAME,'Exact singleton native Toggle')
    sample,sha=toggle.rows(sample_files[0],scopes);require(sha==pins[str(sample_files[0])],'Sample Toggle drift')
    extra,sha=toggle.rows(suffix[0],scopes);require(sha==pins[str(suffix[0])],'765 suffix drift')
    baseline765=toggle.union(before,extra);require(baseline765==before,'765 changed QBS Toggle baseline')
    after=toggle.union(baseline765,sample);gains=toggle.gains(baseline765,after)
    prediction=life.read_bound(runner.PRE/'target-prediction.json',record['preflight']['output_pins'][str(runner.PRE/'target-prediction.json')])
    targets=[]
    for t in prediction['targets']:
        scope=t['scope'];c=t['raw_coordinate'];require(t['checksum']==sample[scope]['checksum'] and t['raw_width']==sample[scope]['width'],'Typed target shape')
        require(not int(before[scope]['bits'],16)>>(before[scope]['width']-1-c)&1,'Predicted target not zero')
        targets.append(dict(scope=scope,signal=t['signal'],bit=t['bit'],raw_coordinate=c,measured_new=c in gains[scope]))
    life.check(pins);out.mkdir()
    life.save(out/'runtime-audit.json',audit)
    life.save(out/'toggle-gain.json',dict(baseline=765,baseline764_identical=True,scopes=gains,
        before_rows=baseline765,single_rows=sample,combined_rows=after,
        total_new_raw_directions=sum(map(len,gains.values())),predicted_targets=targets,
        predicted_directions=2320,measured_predicted_directions=sum(t['measured_new'] for t in targets),
        official_percentage=False,coverage_admitted=False))
    outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
    result=dict(status='MATRIX4_FULL_NATIVE_QUALIFIED_NOT_ADMITTED',input_pins=pins,output_pins=outputs,
        native_destination_bytes=1024,full_vrf_bytes=16384,initial_vrf_bytes=16384,
        csr_values=48,source_readback_bytes=18176,commands=4,software_checks=24,
        full_scalar_isa_verified=False,custom_spike_pass=False,coverage_admitted=False,
        total_new_raw_directions=sum(map(len,gains.values())),
        measured_predicted_directions=sum(t['measured_new'] for t in targets),simulation_rerun=False)
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(collect(a.output.absolute())),flush=True)
