"""One frozen-image BTB run, hard600s; terminal capture is not qualification/admission."""
import argparse
from pathlib import Path
import build_btb_target_ring as pre

life, require = pre.life, pre.require
PROBE = Path(__file__).with_name('btb_target_ring_probe.tcl').resolve()
CASE = 'btb_target_ring_sv39'


def command(elf, out):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(elf),'+TESTCASE='+CASE,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(out/'commit_trace.csv'),'+VECTOR_TRACE='+str(out/'vector_trace.csv'),
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000',
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(out/'code.vdb'),'-cm_name',CASE,
        '-ucli','-do',str(PROBE)]


def prepare(path, seal, out):
    q=life.read_bound(path,seal)
    require(q['status']=='BTB32_SPIKE_ARCHITECTURE_PASS_NOT_RTL' and q['baseline']==777 and
            q['baseline_seal']==pre.BASE_SHA and q['checks']==2690 and q['precise_ecalls']==1 and
            q['source_executions']==96 and q['VCS_launched'] is False and q['coverage_admitted'] is False,
            'Exact real Spike preflight')
    require(path.parent/'input.elf' in [Path(p) for p in q['input_pins']] and
            q['symbols']['tohost']==0x80001000,'Bound ELF/fixed tohost')
    life.check(q['input_pins'])
    require(pre.elf_contract(path.parent/'input.elf',q['symbols'])==q['elf_proof'],'ELF layout drift')
    require(out.parent==life.OUT and out.resolve()==out and not out.exists() and
            not out.with_name(out.name+'.prepared.json').exists(),'Fresh independent run')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(image['simv']==str(life.IMAGE) and len(image['image'])==66,'Frozen66 image')
    fixed={str(path):seal,str(life.PLAN):life.PLAN_SEAL}
    for p in (PROBE,Path(__file__).resolve(),Path(__file__).with_name('test_run_btb_target_ring.py')):
        fixed[str(p)]=life.digest(p)
    pins=life.merge_pins(q['input_pins'],image['image']);pins=life.merge_pins(pins,fixed);life.check(pins)
    record=dict(schema='BTB32_FROZEN600_PREPARED_V1',case=CASE,output=str(out),
        preflight=str(path),preflight_seal=seal,baseline=777,baseline_seal=pre.BASE_SHA,
        command=command(path.parent/'input.elf',out),pins=pins,timeout_s=600,
        wave_limit_bytes=64*1024*1024,automatic_retry=False,coverage_admitted=False,
        RTL_changed=False,post_terminal_qualification_required=True)
    dest=out.with_name(out.name+'.prepared.json');life.save(dest,record)
    print('BTB_PREPARED_NO_VCS',str(dest),life.digest(dest),flush=True)


def validate_record(r):
    out=Path(r['output']);elf=Path(r['preflight']).parent/'input.elf'
    require(r['schema']=='BTB32_FROZEN600_PREPARED_V1' and r['case']==CASE and
            type(r['timeout_s']) is int and r['timeout_s']==600 and r['baseline']==777 and
            r['baseline_seal']==pre.BASE_SHA and r['command']==command(elf,out) and
            r['automatic_retry'] is False and r['coverage_admitted'] is False and r['RTL_changed'] is False and
            r['post_terminal_qualification_required'] is True and r['wave_limit_bytes']==64*1024*1024 and
            out.parent==life.OUT and out.resolve()==out,'Exact frozen one-shot command')
    return out


def run(path, seal):
    r=life.read_bound(path,seal);out=validate_record(r)
    require(not out.exists(),'No run/retry/overwrite')
    r=dict(r,pins=life.merge_pins(r['pins'],{str(path):seal}))
    life.run(out,r)
    wave=out/'btb-target-ring.vpd'
    require(wave.is_file() and 0<wave.stat().st_size<=r['wave_limit_bytes'],'Focused waveform size')
    console=(out/'console.log').read_text().splitlines()
    require(console.count('BTB_RING_READY')==1 and len([l for l in console if l.startswith('BTB_RING_OBJECT ')])==10 and
            not any(l.startswith('BTB_RING_ERROR ') for l in console),'Anchored actual probe startup')
    life.save(out/'capture-result.json',dict(status='TERMINAL_CAPTURE_PENDING_ARCHITECTURE_AND_BTB_UPDATE_QUALIFICATION',
        waveform=str(wave),waveform_sha256=life.digest(wave),preflight_seal=r['preflight_seal'],
        coverage_admitted=False,measured_toggle_gain=None,no_automatic_retry=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--input',type=Path,required=True);p.add_argument('--seal',required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.mode=='prepare':
        require(a.output is not None,'Output required');prepare(a.input.absolute(),a.seal,a.output.absolute())
    else: run(a.input.absolute(),a.seal)
