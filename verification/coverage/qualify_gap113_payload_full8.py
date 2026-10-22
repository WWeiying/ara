"""Offline full8 native/VRF/CSR/lifecycle qualification and exact741 raw diagnostic."""
import argparse
import json
from pathlib import Path
import struct
import sys
from types import FunctionType, SimpleNamespace

import qualify_gap110_native_v2 as inherited
import run_gap113_payload_full8 as runner
import targeted_toggle_evidence_v2 as toggle
import coverage_bitmap_delta as bitmap

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import build_gap113_payload_full8 as recipe

life,require=runner.life,inherited.require
RUN=life.OUT/'gap113-payload-full8-old-image-741-agent-20261007-01'
RUN_SEAL='ee719b33090434bd103499b3cf88ae751fb6d88b4273acc513f29464d5c41fc1'
BASE=life.OUT/'targeted-toggle-offline-admitted-741-parent-20261007-01'
BASE_SEAL='ad53b488eb12de7c8fe1a470d72c5a36dbea5cb349383dcf9c3c8068cebfb0f1'
TOGGLE=life.OUT/'toggle741-capacity-ranking-agent-20261007-01.json'
WORD=0x0eb5045b
ROOT='ara_tb.dut.i_ara_soc.i_system.i_ara.i_vlsu.i_qbs_engine.i_compute_engine'
SCOPES=[ROOT+'.i_block_adapter_bank%d.i_payload_buffer'%b for b in (0,1)]+[ROOT+'.i_profile_engine_int']


def unpack(weight,activation):
    require(len(weight)==880 and len(activation)==2336,'Full native extents')
    contexts=[]
    for c in range(8):
        require(struct.unpack_from('<I',activation,4*c)[0]==0x3f800000,'Unit activation scale')
        qs=[struct.unpack('b',activation[32+8*i+c:33+8*i+c])[0] for i in range(256)]
        for g in range(16):
            require(sum(qs[16*g:16*g+16])==struct.unpack_from('<h',activation,2080+16*g+2*c)[0],
                    'Independent bsum differs')
        contexts.append(qs)
    dots=[]
    for c in range(8):
        for r in range(8):
            b=weight[110*r:110*(r+1)]
            require(struct.unpack_from('<H',b,108)[0]==0x3c00,'Unit Q3 scale')
            dot=0
            for i in range(256):
                section,slot=divmod(i//16,4)
                scale=((b[96+(section%2)*4+slot]>>(4*(section//2)))&15)|(((b[104+slot]>>(2*section))&3)<<4)
                packet,lane=divmod(i,32)
                quant=(b[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                if not (b[lane]>>packet)&1:quant-=4
                dot+=(scale-32)*quant*contexts[c][i]
                require(abs(dot)<2**23,'Bounded exact integer intermediate')
            dots.append(dot)
    return dict(n=8,result_bits=[inherited.integer_single(d) for d in dots],integer_dots=dots,fflags=0)


def independent_native():
    expected=b'';items=[]
    for phase in (0,1):
        w,a,gold=recipe.fixture(phase);expected+=w+a
        item=unpack(w[64+12*phase:944+12*phase],a[68:2404])
        require(item['result_bits']==gold and json.loads((runner.PRE/('gold%d.json'%phase)).read_bytes())
                ==dict(bits=gold,flags=0),'Independent unpack/frozen gold differs')
        item.update(weight_image=w,activation_image=a);items.append(item)
    require((runner.PRE/'templates.log').read_bytes()==expected,'Host packed template differs')
    return items


def descriptor(n):
    require(type(n) is int and n==8,'Only N8')
    # Validate the frozen ABI enums/packer through its audited N7 path, then replace only N-1.
    header=adapter().abi_descriptor_header(7)
    return (header & ~(31<<20)) | (7<<20)


def regions(phase,symbols,data,native):
    item=native[phase];seed=inherited.seed_image(phase);actual=bytearray(seed)
    for c in range(8):
        for r in range(8):struct.pack_into('<I',actual,1024+128*c+4*r,item['result_bits'][8*c+r])
    before=b''.join(struct.pack('<I',0x13570000+i) for i in range(16))
    after=b''.join(struct.pack('<I',0x24680000+i) for i in range(16))
    desc=bytes([0xc3])*64+struct.pack('<QQ',descriptor(8),symbols['weights'][0]+64+12*phase)+bytes([0xc3])*64
    csr=struct.pack('<20Q',*[0x1234567800000000+i for i in range(4)],
                    *([8,16,0,2,8,5]*2),*[0x8765432100000000+i for i in range(4)])
    result=dict(initial=before+seed+after,actual=before+actual+after,weights=item['weight_image'],
                activation=item['activation_image'],descriptor_packet=desc,csr_packet=csr)
    require(all(symbols[k][1]==len(v) for k,v in result.items()),'Complete ELF region extents differ')
    return result


def custom_expected(item):
    require(item['n']==8 and len(item['result_bits'])==64,'Exact full8 result shape')
    return {(8+c,4*r+b):(item['result_bits'][8*c+r]>>(8*b))&255
            for c in range(8) for r in range(8) for b in range(4)}


def activity_bytes(activity,expected,start,done,custom=False):
    inherited.support.activity_bytes(activity,expected,start,done)
    require(len({(w.arch_seq,w.vid) for w in activity.writes})<=1,'Write owner/VID drift')
    if custom:
        require((activity.instruction,activity.vd,activity.vl)==(WORD,8,256) and len(expected)==256,
                'Exact M8/backend VL256/256 active bytes')
        observed={}
        for w in activity.writes:
            require((w.lane,w.addr) not in observed,'Duplicate native lane/address')
            observed[w.lane,w.addr]=w.be
        require(observed=={(lane,(8+c)*4):255 for c in range(8) for lane in range(4)},
                'Exact full8 masks/addresses differ')


def software(log):
    result=inherited.software(log)
    require(log.read_text().splitlines().count(
        'PASSED: qbs_gap113_payload_full8 inherited_checks=41 errors=0')==1,'Full8 terminal label')
    return result


def adapter():
    namespace=dict(vars(inherited),WORD=WORD,software=software,regions=regions,
                   custom_expected=custom_expected,activity_bytes=activity_bytes)
    namespace['runner']=SimpleNamespace(PRE=runner.PRE,PRE_SEAL=runner.SEAL,ELF=runner.PRE/(runner.NAME+'.elf'))
    namespace['ABI_DEP']=recipe.APP/'../qbs_gap110_q3_r4_tail/../common/qbs_abi.h'
    for name in ('elf_view','abi_pins','abi_descriptor_header','runtime'):
        namespace[name]=FunctionType(getattr(inherited,name).__code__,namespace,name)
    return SimpleNamespace(**namespace)


def runtime(view,symbols,data,sites,native):
    result=view.runtime(RUN,symbols,data,sites,native)
    # Only inherited descriptive M5 counters are replaced; all lifecycle gates remain unchanged.
    require(len(result['bindings'])==2 and result['custom_write_bytes']==240 and
            result['full_vrf_bytes']==8192,'Unexpected inherited audit schema')
    for binding in result['bindings']:
        require(binding['software_vl']==8 and binding['backend_vl']==160 and
                binding['native_active_write_bytes']==160,'Unexpected inherited shape labels')
        binding.update(backend_vl=256,native_active_write_bytes=256,native_total_write_bytes=256,
                       preserved_vrf_bytes=3840)
    result.update(status='FULL8_COMPLETE_NATIVE_VRF_CSR_LIFECYCLE_PASS_NOT_FULL_SCALAR_ISA',
                  custom_write_bytes=512,custom_active_bytes=512,custom_preserved_vrf_bytes=7680)
    return result


def prepare():
    reviewed=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL)
    require(reviewed['case']==runner.NAME and reviewed['timeout_s']==600 and
            reviewed['preflight']==life.read_bound(runner.PRE/'preflight-manifest.json',runner.SEAL),
            'Reviewed full8 run differs')
    runner.validate(reviewed['preflight'])
    manifest=life.read_bound(BASE/'admission-manifest.json',BASE_SEAL)
    before=life.read_bound(BASE/'combined-bits.json',manifest['output_pins'][str(BASE/'combined-bits.json')])
    require(len(before['tests'])==len(set(before['tests']))==741 and str(RUN/'code.vdb') not in before['tests'],
            'Exact741/unique candidate required')
    toggle_before=json.loads(TOGGLE.read_bytes())
    require(toggle_before['tests']==741 and toggle_before['schema']=='RAW741_TOGGLE_SERIALIZED_CAPACITY_V1',
            'Wrong Toggle baseline')
    pins=life.merge_pins(reviewed['pins'],manifest['output_pins'])
    pins=life.merge_pins(pins,before['input_hashes'])
    pins=life.merge_pins(pins,toggle_before['input_pins'])
    pins=life.merge_pins(pins,{str(BASE/'admission-manifest.json'):BASE_SEAL,
        str(TOGGLE):life.digest(TOGGLE),str(RUN.with_name(RUN.name+'.prepared.json')):RUN_SEAL,
        str(inherited.BUILD):inherited.BUILD_SHA})
    build=life.read_bound(inherited.BUILD,inherited.BUILD_SHA)
    for rel in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
        path=life.ROOT/rel;pins=life.merge_pins(pins,{str(path):build[str(path)]})
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            p=Path(file).resolve()
            if p.suffix=='.py' and str(p).startswith(str(life.ROOT/'verification')+'/'):
                pins=life.merge_pins(pins,{str(p):life.digest(p)})
    test=Path(__file__).with_name('test_qualify_gap113_payload_full8.py')
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    require(life.digest(Path(inherited.__file__))=='a721d950834d863b069c78ded382b3ae6e36a8e0841f201c850a6bd20699c691',
            'Inherited qualifier drift')
    life.check(pins);native=independent_native();view=adapter();symbols,data,sites=view.elf_view()
    for phase in (0,1):regions(phase,symbols,data,native)
    return dict(status='FULL8_OFFLINE_PREPARED_NOT_COLLECTED',run=str(RUN),pins=pins,baseline=str(BASE),
                baseline_seal=BASE_SEAL,scopes=SCOPES,coverage_admitted=False,
                toggle_array_interval_decode='HOLD_NOT_INTERPRETED; binary prefix gain is not full Toggle denominator')


def collect(config,out):
    require(not out.exists() and out.parent==life.OUT,'Fresh output')
    status,sha=inherited.terminal(RUN)
    pins=life.merge_pins(config['pins'],{str(status):sha})
    files=[RUN/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv')]
    files += [p for p in (RUN/'code.vdb').rglob('*') if p.is_file()]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files});life.check(pins)
    require(json.loads((RUN/'manifest.json').read_bytes())==life.read_bound(
        RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL),'Actual run manifest differs')
    start=json.loads((RUN/'started.json').read_bytes());reviewed=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL)
    require(start['command']==reviewed['command'] and start['budget_s']==600 and
            start['input_elf']==str(runner.PRE/(runner.NAME+'.elf')) and start['elf_sha256']==runner.ELF_SHA and
            start['image']==str(life.IMAGE) and start['image_sha256']==runner.reused.IMAGE_SEAL and
            type(start['pid']) is int and start['pid']>0,'Actual ELF/image execution differs')
    out.mkdir();life.save(out/'evidence-pins.json',pins)
    try:
        native=independent_native();view=adapter();symbols,data,sites=view.elf_view()
        audit=runtime(view,symbols,data,sites,native)
        native_files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(native_files)==1 and native_files[0].parent.name==runner.NAME,'Native test identity')
        sample,digest=toggle.rows(native_files[0],SCOPES)
        require(digest==pins[str(native_files[0])],'Toggle input drift')
        baseline=json.loads(TOGGLE.read_bytes())
        before={s:{k:baseline['instances'][s][k] for k in ('width','checksum','bits')} for s in SCOPES}
        gains=toggle.gains(before,toggle.union(before,sample))
        design=life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb'
        (out/'single-inputs.txt').write_text(str(design)+'\n'+str(RUN/'code.vdb')+'\n')
        single=bitmap.collect(out/'single-inputs.txt')
        before_bits=json.loads((BASE/'combined-bits.json').read_bytes())
        require(single['tests']==[str(RUN/'code.vdb')] and all(pins.get(p)==h for p,h in single['input_hashes'].items()),
                'Candidate bitmap input drift/identity')
        after=bitmap.combine(before_bits,single)
        require(after['tests']==before_bits['tests']+[str(RUN/'code.vdb')],'Exact741 prefix differs')
        delta=bitmap.delta(before_bits,after)
        life.check(pins)
        for name,value in [('runtime-audit.json',audit),('single-bits.json',single),('raw-delta.json',delta),
            ('toggle-gain.json',dict(baseline_population=741,scopes=gains,
                total_new_serialized_toggle_positions=sum(map(len,gains.values())),
                semantics='Only binary instance_data directions; packed-array instance_intervaldata remains HOLD',
                direction_binding_verified=False,official_percentage=False,coverage_admitted=False))]:
            life.save(out/name,value)
        outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        result=dict(status='FULL8_NATIVE_QUALIFIED_RAW741_DIAGNOSTIC_NOT_ADMITTED',output_pins=outputs,
            coverage_admitted=False,rtl_changed=False,simulation_rerun=False,full_scalar_isa_verified=False,
            toggle_binary_prefix_gain=sum(map(len,gains.values())),raw_four_metric_delta=delta['metrics'],
            full_toggle_interval_gain_qualified=False)
    except Exception as error:
        life.save(out/'qualification.json',dict(status='FULL8_QUALIFICATION_FAIL_NOT_ADMITTED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False));raise
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','collect'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--config-seal');a=p.parse_args()
    require((a.mode=='collect')==bool(a.config_seal),'Collect requires reviewed plan seal')
    config=prepare();out=a.output.absolute();record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not record.exists() and not out.exists(),'Preserve plan/output');life.save(record,config)
        print(json.dumps(dict(plan=str(record),seal=life.digest(record),pins=len(config['pins']))))
    else:
        require(life.read_bound(record,a.config_seal)==config,'Prepared plan drift')
        config['pins']=life.merge_pins(config['pins'],{str(record):a.config_seal})
        print(json.dumps(collect(config,out)))
