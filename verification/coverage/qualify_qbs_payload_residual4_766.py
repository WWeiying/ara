"""Mixed-format exact native qualification and measured scoped Toggle on formal766."""
import inspect
import json
from pathlib import Path
import struct
import sys
from types import FunctionType, SimpleNamespace
import qualify_qbs_payload_matrix4_uart as frozen
import run_qbs_payload_residual4_766 as runner
import rank_qbs_payload_hits766 as ranking
sys.path.insert(0,str(runner.life.ROOT/'verification/tests'))
import build_qbs_payload_residual4_766 as builder

life,require=runner.life,frozen.require
FROZEN_SHA='e90c9f3c621b21711c86d154e06a9356073b60ce4baa75816d7ed3de607111d9'
recipe=SimpleNamespace(**dict(vars(builder),seed_bytes=builder.base.seed_bytes))


def unpack(phase,weight,activation):
    require(type(phase) is int and 0<=phase<4 and len(weight)==8*recipe.SIZE[phase] and len(activation)==2336,'Exact native extents')
    if phase in (1,2):return frozen.unpack(weight,activation)
    contexts=[]
    for ctx in range(8):
        require(struct.unpack_from('<I',activation,4*ctx)[0]==0x3f800000,'Unit Q8 scale')
        q=[int.from_bytes(activation[32+8*i+ctx:33+8*i+ctx],'little',signed=True) for i in range(256)]
        for g in range(16):require(sum(q[16*g:16*g+16])==struct.unpack_from('<h',activation,2080+16*g+2*ctx)[0],'Independent Q8 bsum')
        contexts.append(q)
    dots=[]
    for ctx in range(8):
        for row in range(8):
            b=weight[recipe.SIZE[phase]*row:recipe.SIZE[phase]*(row+1)]
            require(struct.unpack_from('<H',b,len(b)-2)[0]==0x3c00,'Unit format scale')
            if phase==3:require(struct.unpack_from('<H',b,80)[0]==0x3c00,'Unit Q2 d')
            dot=0
            for i in range(256):
                g=i//16
                if phase==0:
                    packet,lane=divmod(i,32)
                    q=(b[32+32*(packet//4)+lane]>>(2*(packet%4)))&3
                    if not (b[lane]>>packet)&1:q-=4
                    region,within=divmod(g,4)
                    scale=((b[96+(region%2)*4+within]>>(4*(region//2)))&15)|(((b[104+within]>>(2*region))&3)<<4)
                    value=q*(scale-32)
                else:
                    half,rem=divmod(i,128);group,lane=divmod(rem,16)
                    q=(b[16+32*half+16*(group&1)+lane]>>(2*(group//2)))&3
                    value=q*(b[g]&15)-(b[g]>>4)
                dot+=value*contexts[ctx][i]
                require(abs(dot)<2**23,'Exact FP32 integer intermediate')
            dots.append(dot)
    return dict(n=8,result_bits=[frozen.full8.inherited.integer_single(d) for d in dots],integer_dots=dots,fflags=0)


def adapted_function(function,changes,namespace):
    require(life.digest(Path(frozen.__file__))==FROZEN_SHA,'Frozen comparator drift')
    source=inspect.getsource(function)
    for old,new in changes:
        require(source.count(old)==1,'Exact mixed-format adaptation '+old);source=source.replace(old,new)
    ns=dict(vars(frozen));ns.update(namespace);exec(compile(source,'<exact766-software-adapter>','exec'),ns)
    return ns[function.__name__]


def runtime(run):
    ns=dict(runner=runner,recipe=recipe,unpack=unpack)
    view=adapted_function(frozen.elf_view,[('item=unpack(w[','item=unpack(phase,w['),
        ('recipe.WP[phase]+1680','recipe.WP[phase]+8*recipe.SIZE[phase]')],ns)
    regions=adapted_function(frozen.regions,[('(2<<4)','(recipe.PROFILE[phase]<<4)')],ns)
    ns.update(elf_view=view,regions=regions)
    return FunctionType(frozen.runtime.__code__,dict(vars(frozen),**ns))(run)


def collect(out,run_sha):
    require(out.parent==life.OUT and not out.exists() and out.resolve()==out,'Fresh output')
    prepared=runner.RUN.with_name(runner.RUN.name+'.prepared.json')
    record=life.read_bound(prepared,run_sha);runner.validate(record['preflight'])
    require(record['timeout_s']==600 and record['case']==runner.NAME,'Bounded case')
    status,status_sha=frozen.full8.inherited.terminal(runner.RUN)
    require(json.loads((runner.RUN/'manifest.json').read_bytes())==record,'Executed manifest differs')
    start=json.loads((runner.RUN/'started.json').read_bytes())
    require(start['command']==record['command'] and start['budget_s']==600 and
        start['elf_sha256']==runner.ELF_SHA and start['image_sha256']==runner.reused.IMAGE_SEAL and
        start['input_elf']==str(runner.PRE/(runner.NAME+'.elf')) and start['image']==str(life.IMAGE),'Execution identity')
    baseline=life.read_bound(ranking.BASE/'admission-manifest.json',ranking.BASE_SHA)
    gains_path=ranking.BASE/'scoped-toggle-gain.json'
    previous=life.read_bound(gains_path,baseline['output_pins'][str(gains_path)])
    require(previous['population']==766 and previous['total_new_raw_directions']==2561,'Actual formal766 baseline')
    before=previous['combined_rows'];scopes=sorted(before)
    files=[runner.RUN/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv','trace_hart_0.log')]
    files+=[p for p in (runner.RUN/'code.vdb').rglob('*') if p.is_file()]
    pins=life.merge_pins(record['pins'],{str(p):life.digest(p) for p in files})
    pins=life.merge_pins(pins,{str(prepared):run_sha,str(status):status_sha,
        str(ranking.BASE/'admission-manifest.json'):ranking.BASE_SHA,str(gains_path):baseline['output_pins'][str(gains_path)]})
    pins=life.merge_pins(pins,frozen.source_observer_contract()['pins'])
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file and str(Path(file).resolve()).startswith(str(life.ROOT/'verification')+'/') and Path(file).suffix=='.py':
            path=Path(file).resolve();pins=life.merge_pins(pins,{str(path):life.digest(path)})
    life.check(pins);audit=runtime(runner.RUN)
    require('Exception' not in (runner.RUN/'trace_hart_0.log').read_text(),'Unexpected hart exception')
    samples=list((runner.RUN/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    require(len(samples)==1 and samples[0].parent.name==runner.NAME,'Exact singleton Toggle')
    sample,sha=frozen.toggle.rows(samples[0],scopes);require(sha==pins[str(samples[0])],'Toggle input drift')
    after=frozen.toggle.union(before,sample);new=frozen.toggle.gains(before,after)
    prediction=life.read_bound(runner.PRE/'target-prediction.json',record['preflight']['output_pins'][str(runner.PRE/'target-prediction.json')])
    require(prediction['baseline']==766 and prediction['baseline_seal']==ranking.BASE_SHA and prediction['mapping_directions']==504,'766 prediction')
    targets=[]
    for t in prediction['targets']:
        scope=t['scope'];c=t['raw_coordinate']
        require(t['checksum']==sample[scope]['checksum'] and t['raw_width']==sample[scope]['width'],'Typed compiled target')
        require(not int(before[scope]['bits'],16)>>(before[scope]['width']-1-c)&1,'Target already hit')
        targets.append(dict(scope=scope,signal=t['signal'],bit=t['bit'],raw_coordinate=c,measured_new=c in new[scope]))
    life.check(pins);out.mkdir();life.save(out/'runtime-audit.json',audit)
    life.save(out/'toggle-gain.json',dict(baseline=766,baseline_seal=ranking.BASE_SHA,scopes=new,before_rows=before,
        single_rows=sample,combined_rows=after,total_new_raw_directions=sum(map(len,new.values())),predicted_targets=targets,
        predicted_directions=504,measured_predicted_directions=sum(t['measured_new'] for t in targets),official_percentage=False,coverage_admitted=False))
    result=dict(status='RESIDUAL4_FULL_NATIVE_QUALIFIED_NOT_ADMITTED',input_pins=pins,
        output_pins={str(p):life.digest(p) for p in out.iterdir() if p.is_file()},baseline=766,
        full_scalar_isa_verified=False,custom_spike_pass=False,coverage_admitted=False,
        full_vrf_bytes=16384,initial_vrf_bytes=16384,native_destination_bytes=1024,csr_values=48,
        source_readback_bytes=18176,commands=4,software_checks=24,
        total_new_raw_directions=sum(map(len,new.values())),measured_predicted_directions=sum(t['measured_new'] for t in targets))
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'],new_directions=result['total_new_raw_directions'])
