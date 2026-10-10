"""Compact full8 native gold qualification, then measured predicted Toggle hits."""
import argparse
import json
from pathlib import Path
import sys
from types import FunctionType

import qualify_gap113_payload_full8 as full8
import run_qbs_payload_phase763 as runner
import targeted_toggle_evidence_v2 as toggle

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import build_qbs_payload_phase763 as recipe

life,require=runner.life,full8.require


def independent_native():
    expected=b'';items=[]
    for phase in (0,1):
        w,a,gold=recipe.fixture(phase);expected+=w+a
        start=64+recipe.ASK[phase]
        item=full8.unpack(w[64+12*phase:944+12*phase],a[start:start+2336])
        require(item['result_bits']==gold and json.loads((runner.PRE/('gold%d.json'%phase)).read_bytes())
                ==dict(bits=gold,flags=0),'Independent native gold differs')
        item.update(weight_image=w,activation_image=a);items.append(item)
    require((runner.PRE/'templates.log').read_bytes()==expected,'Complete packed source differs')
    return items


def software(log):
    result=full8.software(log)
    require(log.read_text().splitlines().count('PASSED: qbs_payload_phase763 commands=2')==1,
            'Missing/duplicate phase terminal')
    return result


def view():
    ns=dict(vars(full8),runner=runner,recipe=recipe,software=software)
    # descriptor calls adapter internally; keep both functions in the same private namespace.
    for name in ('descriptor','regions','adapter'):
        ns[name]=FunctionType(getattr(full8,name).__code__,ns,name)
    return ns['adapter']()


def measured_targets(prediction,sample):
    result=[]
    for t in prediction['targets']:
        row=sample[t['scope']]
        require(row['checksum']=='3657545390' and row['width']==66340,'Compiled hit shape differs')
        bits=int(row['bits'],16)
        coordinates=t['missing_serialized_coordinates']
        require(len(coordinates)==2 and len(set(coordinates))==2 and
                all(type(c) is int and 0<=c<row['width'] for c in coordinates),'Typed partial-bit coordinates')
        hits=[c for c in coordinates if bits>>(row['width']-1-c)&1]
        result.append(dict(scope=t['scope'],signal=t['signal'],bit=t['bit'],
                           predicted_coordinates=coordinates,measured_new_coordinates=hits))
    return result


def collect(run,seal,out):
    run=Path(run).absolute();out=Path(out).absolute()
    require(run.parent==life.OUT and out.parent==life.OUT and not out.exists() and
            run.resolve()==run and out.resolve()==out,'Independent canonical output')
    prepared=run.with_name(run.name+'.prepared.json')
    record=life.read_bound(prepared,seal)
    runner.validate(record['preflight'])
    require(record['case']==runner.NAME and record['timeout_s']==600 and
            record['old_image_files_checked']==66,'Reviewed bounded run')
    status,status_sha=full8.inherited.terminal(run)
    pins=life.merge_pins(record['pins'],{str(prepared):seal,str(status):status_sha})
    files=[run/n for n in ('manifest.json','started.json','console.log','run.vcs.log','commit_trace.csv','vector_trace.csv')]
    files += [p for p in (run/'code.vdb').rglob('*') if p.is_file()]
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in files})
    require(life.read_bound(run/'manifest.json',pins[str(run/'manifest.json')])==record,'Executed manifest differs')
    start=json.loads((run/'started.json').read_bytes())
    require(start['command']==record['command'] and start['budget_s']==600 and
            start['input_elf']==str(runner.PRE/(runner.NAME+'.elf')) and start['elf_sha256']==runner.ELF_SHA and
            start['image']==str(life.IMAGE) and start['image_sha256']==runner.reused.IMAGE_SEAL and
            type(start['pid']) is int and start['pid']>0,'Executed image/ELF differs')
    build=life.read_bound(full8.inherited.BUILD,full8.inherited.BUILD_SHA)
    for rel in ('hardware/src/vlsu/qbs/qbs_commit.sv','hardware/tb/ara_commit_monitor.sv'):
        p=life.ROOT/rel;pins=life.merge_pins(pins,{str(p):build[str(p)]})
    for module in list(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            p=Path(file).resolve()
            if p.suffix=='.py' and str(p).startswith(str(life.ROOT/'verification')+'/'):
                pins=life.merge_pins(pins,{str(p):life.digest(p)})
    life.check(pins)
    out.mkdir()
    try:
        native=independent_native();adapted=view();symbols,data,sites=adapted.elf_view()
        ns=dict(vars(full8),RUN=run)
        audit=FunctionType(full8.runtime.__code__,ns)(adapted,symbols,data,sites,native)
        prediction=life.read_bound(runner.PRE/'target-prediction.json',record['preflight']['prediction_sha256'])
        native_files=list((run/'code.vdb/snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        require(len(native_files)==1 and native_files[0].parent.name==runner.NAME,'Exact native test')
        sample,digest=toggle.rows(native_files[0],sorted({t['scope'] for t in prediction['targets']}))
        require(digest==pins[str(native_files[0])],'Toggle bytes changed')
        targets=measured_targets(prediction,sample)
        gain=sum(len(t['measured_new_coordinates']) for t in targets)
        life.check(pins)
        life.save(out/'runtime-audit.json',audit)
        life.save(out/'target-hit-audit.json',dict(baseline=763,targets=targets,
            predicted_directions=288,measured_new_raw_directions=gain,official_percentage=False))
        life.save(out/'evidence-pins.json',pins)
        outputs={str(p):life.digest(p) for p in out.iterdir() if p.is_file()}
        result=dict(status='QBS_PHASE763_FULL_NATIVE_QUALIFIED_NOT_ADMITTED',input_pins=pins,output_pins=outputs,
            native_destination_bytes=512,full_vrf_bytes=8192,source_guard_bytes=7328,csr_words=24,
            measured_predicted_new_raw_directions=gain,coverage_admitted=False,
            full_scalar_isa_verified=False,custom_spike_pass=False,simulation_rerun=False,
            qualification_scope='Independent native result/all VRF/CSR/source guards, retirement completeness and command/uop/write lifecycle; not a complete scalar ISA differential')
    except Exception as error:
        life.save(out/'qualification.json',dict(status='QBS_PHASE763_QUALIFICATION_FAILED',
            reason=type(error).__name__+': '+str(error),coverage_admitted=False));raise
    life.save(out/'qualification.json',result)
    return dict(output=str(out),seal=life.digest(out/'qualification.json'),status=result['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--prepared-seal',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(collect(a.run,a.prepared_seal,a.output)))
