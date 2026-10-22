"""One600s old-image run, established lifecycle, automatic offline qualification."""
import argparse
import json
from pathlib import Path
import subprocess
from types import FunctionType
import prepare_half_fma_finite as preflight
import run_gap110_simulation as lifecycle
import run_gap115_axi_capture as focused

life, require = preflight.life, preflight.require
HERE = Path(__file__).resolve().parent
OUT = life.OUT/'half-fma-finite-old-image-agent-20261007-01'
PRE_SHA = 'a00170e78e33e9cc6a29744f00720f91844123ec89431f735dd4ea106bd7c9fb'
NAME = 'half_fma_finite_four_phase'


def scopes():
    prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_vfus.i_vmfpu.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.gen_num_lanes[%d].active_lane.lane_instance.i_fma'
    return [prefix % (lane, simd) for lane in range(4) for simd in range(4)]


def command(output):
    return [str(life.IMAGE), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD='+str(preflight.PRE/'input.elf'), '+TESTCASE='+NAME, '+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'), '+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',NAME,
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-ucli','-do',str(OUT.with_name(OUT.name+'.entry.tcl'))]


def prepare():
    require(not OUT.exists(), 'Fresh one-shot output')
    pre = life.read_bound(preflight.PRE/'preflight.json', PRE_SHA)
    require(pre['status']=='FOUR_PHASE_RATIONAL_SPIKE_FULL_VRF_CSR_PASS_NO_DUT' and
            pre['phases']==4 and pre['software_checks']==2900 and pre['full_vrf_bytes']==16384,
            'Complete preflight required')
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv']==str(life.IMAGE) and len(plan['image'])==66, 'Frozen simv66')
    pins = life.merge_pins(pre['pins'],plan['image'])
    pins = life.merge_pins(pins,{str(preflight.PRE/'preflight.json'):PRE_SHA,
        str(life.PLAN):life.PLAN_SEAL,str(focused.CONVERTER):focused.CONVERTER_SHA})
    for p in (Path(__file__),HERE/'test_run_half_fma_finite.py',HERE/'capture_half_fma_finite.tcl',
              HERE/'qualify_half_fma_finite.py',Path(lifecycle.__file__),Path(life.__file__),Path(focused.__file__)):
        pins[str(p.resolve())]=life.digest(p)
    life.check(pins)
    selection=OUT.with_name(OUT.name+'.selection.tcl')
    with selection.open('x') as f: f.write('set hfm_scopes {'+' '.join(scopes())+'}\n')
    entry=OUT.with_name(OUT.name+'.entry.tcl')
    with entry.open('x') as f:
        f.write('file copy {'+str(selection)+'} half-fma-selection.tcl\nsource {'+str(HERE/'capture_half_fma_finite.tcl')+'}\n')
    pins=life.merge_pins(pins,{str(p):life.digest(p) for p in (selection,entry)})
    record=dict(case=NAME,preflight=pre,pins=pins,command=command(OUT),timeout_s=600,
        old_image_files_checked=66,scopes=scopes(),wave_byte_limit=64*1024*1024,
        coverage_admitted=False,automatic_retry=False,rtl_modified=False)
    path=OUT.with_name(OUT.name+'.prepared.json');life.save(path,record)
    print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(pins))))


def run(seal):
    path=OUT.with_name(OUT.name+'.prepared.json');record=life.read_bound(path,seal)
    require(record['command']==command(OUT) and record['scopes']==scopes() and record['timeout_s']==600,
            'Exact single prepared command')
    require(not OUT.exists(),'No retry')
    record['pins']=life.merge_pins(record['pins'],{str(path):seal})
    namespace=dict(vars(lifecycle),NAME=NAME,ELF=preflight.PRE/'input.elf',
                   ELF_SEAL=record['preflight']['ELF_sha256'],command=command)
    FunctionType(lifecycle.run.__code__,namespace)(OUT,record)
    try:
        console=(OUT/'console.log').read_text()
        require(console.splitlines().count('HALF_FMA_16_SCOPES_READY')==1 and
                'HALF_FMA_CAPTURE_ERROR' not in console,'Actual focused object setup')
        wave=OUT/'half-fma.vpd'
        require(0 < wave.stat().st_size <= record['wave_byte_limit'],'Focused waveform bound')
        with (OUT/'conversion.log').open('x') as log:
            subprocess.run([str(focused.CONVERTER),'+splitpacked',str(wave),str(OUT/'half-fma.vcd')],
                           check=True,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        import qualify_half_fma_finite as qualifier
        qualifier.collect(OUT,record)
    except Exception as error:
        life.save(OUT/'qualification-hold.json',dict(status='HOLD_NOT_ADMITTED',reason=str(error),coverage_admitted=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'));p.add_argument('--seal')
    a=p.parse_args()
    if a.mode=='prepare':require(not a.seal,'Prepare without seal');prepare()
    else:require(a.seal,'Exact prepared seal');run(a.seal)
