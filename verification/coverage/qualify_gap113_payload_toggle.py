"""Offline GAP113 native/readback/lifecycle plus scoped raw Toggle; no ISA/admission claim."""
import argparse
import json
from pathlib import Path
import struct
import sys
from types import FunctionType, SimpleNamespace
import qualify_gap110_native_v2 as inherited
import run_gap113_payload_toggle as runner
import targeted_toggle_evidence_v2 as toggle

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import build_gap113_payload_toggle as recipe

life,require=runner.life,inherited.require
RUN=life.OUT/'gap113-payload-toggle-old-image-740-agent-20261007-01'
RUN_SEAL='512732741c34570c1654a0aa6856b46c8ba7453cc0994953b0efb40ddd41d8f6'
EVIDENCE_SHA='ed1e65f57321d38d52ae53a0d6525dbed8e45fd35416581f383ce5d4cffbadae'


def independent_native():
    dump=(runner.PRE/'templates.log').read_bytes();expected=b'';items=[]
    for phase,n in enumerate((7,5)):
        w,a,gold=recipe.fixtures(phase);offset=64+12*phase
        expected+=w+a+struct.pack('<%dI'%len(gold),*gold)
        sealed=json.loads((runner.PRE/('gold%d.json'%phase)).read_bytes())
        require(sealed==dict(bits=gold,flags=0),'Frozen gold differs from independent native unpack')
        dots=[-128*(-32 if r&1 else 31)*(-4 if r&2 else 3) for r in range(n)]*5
        items.append(dict(n=n,weight=w[offset:offset+880],activation=a[68:68+2336],
                          weight_image=w,activation_image=a,result_bits=gold,integer_dots=dots,fflags=0))
    require(dump==expected,'Actual host input templates/gold differ from independent recipe')
    return items


def software(log):
    contract=inherited.software(log)
    require(log.read_text().splitlines().count(
        'PASSED: qbs_gap113_payload_toggle inherited_checks=41 errors=0')==1,
        'Missing/duplicate distinct GAP113 DUT terminal check')
    return contract


def adapter():
    # Bind reused function globals privately; never mutate frozen modules/files.
    namespace=dict(vars(inherited))
    namespace['runner']=SimpleNamespace(PRE=runner.PRE,PRE_SEAL=runner.SEAL,
        ELF=runner.PRE/(runner.NAME+'.elf'))
    namespace['ABI_DEP']=recipe.APP/'../qbs_gap110_q3_r4_tail/../common/qbs_abi.h'
    namespace.update(software=software,regions=regions)
    for name in ('elf_view','abi_pins','abi_descriptor_header','runtime'):
        namespace[name]=FunctionType(getattr(inherited,name).__code__,namespace,name)
    return SimpleNamespace(**namespace)


def regions(phase,symbols,data,native):
    item=native[phase];n=item['n'];seed=inherited.seed_image(phase);actual=bytearray(seed)
    for ctx in range(5):
        for row in range(n):struct.pack_into('<I',actual,1024+128*ctx+4*row,item['result_bits'][ctx*n+row])
    before=b''.join(struct.pack('<I',0x13570000+i) for i in range(16))
    after=b''.join(struct.pack('<I',0x24680000+i) for i in range(16))
    # Runtime-initialized BSS templates are proven by pinned host dump + full DUT readbacks,
    # not misrepresented as ELF constant-section contents.
    header=adapter().abi_descriptor_header(n)
    descriptor=bytes([0xc3])*64+struct.pack('<QQ',header,symbols['weights'][0]+64+12*phase)+bytes([0xc3])*64
    csr=struct.pack('<20Q',*[0x1234567800000000+i for i in range(4)],
                    *([n,16,0,2,8,5]*2),*[0x8765432100000000+i for i in range(4)])
    values=dict(initial=before+seed+after,actual=before+actual+after,
        weights=item['weight_image'],activation=item['activation_image'],descriptor_packet=descriptor,csr_packet=csr)
    require(all(symbols[name][1]==len(blob) for name,blob in values.items()),'Complete region ELF extents differ')
    return values


def scoped_gain(sample,evidence):
    before=evidence['metrics'];after=toggle.union(before,sample);changes=toggle.gains(before,after)
    target=recipe.target(evidence);zeros=set(target['serialized_zero_coordinates'])
    return dict(baseline_population=740,coordinate_semantics=evidence['coordinate_semantics'],
        direction_binding_verified=False,scopes=changes,
        total_new_serialized_toggle_positions=sum(map(len,changes.values())),
        primary_target_hits=sorted(zeros.intersection(changes[recipe.SCOPE])),
        metric='tgl',official_percentage=False,coverage_admitted=False)


def reviewed_run():
    config=life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL)
    pre=life.read_bound(runner.PRE/'preflight-manifest.json',runner.SEAL);runner.validate(pre)
    globals_=dict(vars(runner.reused),NAME=runner.NAME,ELF=Path(pre['binary']))
    command=FunctionType(runner.reused.command.__code__,globals_)(RUN)
    require(config['case']==runner.NAME and config['preflight']==pre and config['timeout_s']==600 and
            config['command']==command and config['coverage_admitted'] is False,'Exact reviewed execution binding')
    life.check(config['pins'])
    return config


def prepare(run,seal):
    require(Path(run).absolute()==RUN and seal==RUN_SEAL,'Only exact reviewed GAP113 run')
    runtime=reviewed_run()
    pins=life.merge_pins(runtime['pins'],{str(RUN.with_name(RUN.name+'.prepared.json')):seal,
        str(recipe.EVIDENCE):EVIDENCE_SHA,str(inherited.BUILD):inherited.BUILD_SHA})
    build=life.read_bound(inherited.BUILD,inherited.BUILD_SHA)
    for rel in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
        path=life.ROOT/rel;pins=life.merge_pins(pins,{str(path):build[str(path)]})
    evidence=life.read_bound(recipe.EVIDENCE,EVIDENCE_SHA);recipe.target(evidence)
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve()
        if path.suffix=='.py' and str(path).startswith(str(life.ROOT/'verification')+'/'):
            pins=life.merge_pins(pins,{str(path):life.digest(path)})
    test=Path(__file__).with_name('test_qualify_gap113_payload_toggle.py')
    pins=life.merge_pins(pins,{str(test):life.digest(test)})
    require(life.digest(Path(inherited.__file__))=='a721d950834d863b069c78ded382b3ae6e36a8e0841f201c850a6bd20699c691',
            'Reviewed inherited qualifier identity differs')
    life.check(pins);independent_native();view=adapter();symbols,data,sites=view.elf_view()
    for phase in (0,1):regions(phase,symbols,data,independent_native())
    return dict(status='GAP113_OFFLINE_QUALIFIER_PREPARED_NOT_COLLECTED',run=str(RUN),pins=pins,
        run_prepared_seal=seal,scopes=sorted(evidence['metrics']),software_checks=41,
        expected_commands=2,full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False)


def collect(config,out):
    require(not out.exists() and out.parent==life.OUT,'Fresh qualification output')
    status_path,status_sha=inherited.terminal(RUN)
    pins=life.merge_pins(config['pins'],{str(status_path):status_sha})
    files=[RUN/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv')]
    files+=[p for p in (RUN/'code.vdb').rglob('*') if p.is_file()]
    for p in files:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    require(json.loads((RUN/'manifest.json').read_bytes())==life.read_bound(
        RUN.with_name(RUN.name+'.prepared.json'),RUN_SEAL),'Actual runtime manifest differs')
    start=json.loads((RUN/'started.json').read_bytes())
    reviewed=reviewed_run()
    require(start['command']==reviewed['command'] and start['budget_s']==600 and
        start['input_elf']==str(runner.PRE/(runner.NAME+'.elf')) and start['elf_sha256']==runner.ELF_SHA and
        start['image']==str(life.IMAGE) and start['image_sha256']==runner.reused.IMAGE_SEAL and
        type(start['pid']) is int and start['pid']>0,'Actual execution identity differs')
    out.mkdir();life.save(out/'evidence-pins.json',pins)
    try:
        view=adapter();symbols,data,sites=view.elf_view()
        audit=view.runtime(RUN,symbols,data,sites,independent_native())
        native_files=list((RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(native_files)==1 and native_files[0].parent.name==runner.NAME,'Exact candidate Toggle test identity')
        sample,digest=toggle.rows(native_files[0],config['scopes'])
        require(pins[str(native_files[0])]==digest,'Candidate Toggle pin differs')
        evidence=life.read_bound(recipe.EVIDENCE,EVIDENCE_SHA);gain=scoped_gain(sample,evidence)
        life.check(pins);life.save(out/'runtime-audit.json',audit);life.save(out/'toggle-gain.json',gain)
        result=dict(status='GAP113_NATIVE_PASS_POSITIVE_SCOPED_TOGGLE_GAIN_NOT_ADMITTED' if
            gain['total_new_serialized_toggle_positions']>0 else 'GAP113_NATIVE_PASS_ZERO_TOGGLE_GAIN_NOT_ADMITTED',
            output_pins={str(out/n):life.digest(out/n) for n in ('runtime-audit.json','toggle-gain.json','evidence-pins.json')},
            full_scalar_isa_verified=False,spike_custom_isa_pass=False,coverage_admitted=False,
            fresh_latest_baseline_gain_required_before_admission=True,simulation_rerun=False,rtl_changed=False)
    except Exception as error:
        result=dict(status='GAP113_QUALIFICATION_FAIL_NOT_ADMITTED',reason=type(error).__name__+': '+str(error),coverage_admitted=False)
        life.save(out/'qualification.json',result);raise
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','collect'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--config-seal');a=p.parse_args()
    require((a.mode=='collect')==bool(a.config_seal),'Collect requires reviewed offline plan seal')
    config=prepare(RUN,RUN_SEAL);out=a.output.absolute();record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        require(not record.exists() and not out.exists(),'Preserve existing output/plan');life.save(record,config)
        print(json.dumps(dict(plan=str(record),seal=life.digest(record),pins=len(config['pins']))))
    else:
        require(life.read_bound(record,a.config_seal)==config,'Reviewed qualification plan differs')
        config['pins']=life.merge_pins(config['pins'],{str(record):a.config_seal})
        print(json.dumps(collect(config,out)))
