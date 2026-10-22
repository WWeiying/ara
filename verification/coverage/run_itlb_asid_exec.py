"""Single600s frozen-image execution followed automatically by offline qualification."""
import argparse
from pathlib import Path
import sys
import traceback
import build_itlb_asid_exec as pre

life,require=pre.life,pre.require
PROBE=Path(__file__).with_name('itlb_asid_exec_probe.tcl').resolve()
CASE='itlb_asid_exec_matrix'


def command(elf,output):
    return [str(life.IMAGE),'-l','run.vcs.log','+NO_FSDB','+ntb_random_seed=1',
        '+PRELOAD='+str(elf),'+TESTCASE='+CASE,'+COMMIT_TOHOST=80001000',
        '+COMMIT_TRACE='+str(output/'commit_trace.csv'),'+VECTOR_TRACE='+str(output/'vector_trace.csv'),
        '-cm','line+cond+fsm+tgl+branch','-cm_dir',str(output/'code.vdb'),'-cm_name',CASE,
        '+ARA_UVM_TRACE_LIMIT=100000','+ARA_CONTRACT_TRACE_LIMIT=100000','-ucli','-do',str(PROBE)]


def prepare(path,seal,output):
    import collect_itlb_asid_exec as collector
    q=life.read_bound(path,seal)
    require(q['status']=='ITLB_TRUE_SMODE48_SPIKE_PTE_CODE_CSR_PASS_NOT_RTL' and q['baseline']==771 and
            q['software_checks']==pre.CHECKS and q['trap_count']==48 and not q['coverage_admitted'] and
            not q['VCS_launched'],'Exact qualified preflight required')
    require(output.parent==life.OUT and output.resolve()==output and not output.exists(), 'Fresh independent run')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Frozen66 image required')
    pins=life.merge_pins(q['input_pins'],image['image'])
    pins=life.merge_pins(pins,{str(path):seal,str(life.PLAN):life.PLAN_SEAL})
    files=[Path(__file__).resolve(),Path(__file__).with_name('test_run_itlb_asid_exec.py'),
        Path(collector.__file__).resolve(),Path(__file__).with_name('test_collect_itlb_asid_exec.py'),
        PROBE,collector.CONVERTER]
    require(life.digest(collector.CONVERTER)==collector.CONVERTER_SHA,'Historical converter differs')
    for module in tuple(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and str(pre.ROOT/'verification') in f and Path(f).is_file():files.append(Path(f).resolve())
    files.extend((pre.ROOT/'verification/ara_verify').glob('*.py'))
    for p in files:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    require(str(path.parent/'input.elf') in pins and q['symbols']['tohost']==0x80001000,'Exact ELF/tohost')
    life.check(pins)
    record=dict(schema='ITLB_EXEC_FROZEN600_AUTOQUALIFY_V1',case=CASE,output=str(output),
        preflight=str(path),preflight_seal=seal,baseline=str(pre.BASE),baseline_seal=pre.BASE_SHA,
        command=command(path.parent/'input.elf',output),timeout_s=600,pins=pins,automatic_retry=False,
        coverage_admitted=False,official_percentage=False,qualification_output=str(output.with_name(output.name+'-qualified')))
    dest=output.with_name(output.name+'.prepared.json');life.save(dest,record)
    print('PREPARED',str(dest),life.digest(dest),flush=True)


def run(path,seal):
    import collect_itlb_asid_exec as collector
    r=life.read_bound(path,seal);output=Path(r['output'])
    require(r['schema']=='ITLB_EXEC_FROZEN600_AUTOQUALIFY_V1' and r['case']==CASE and r['timeout_s']==600 and
        r['baseline_seal']==pre.BASE_SHA and not r['coverage_admitted'] and not r['automatic_retry'] and
        r['command']==command(Path(r['preflight']).parent/'input.elf',output) and not output.exists(),
        'Exact authorized command required')
    r=dict(r,pins=life.merge_pins(r['pins'],{str(path):seal}))
    try:
        life.run(output,r)
        collector.collect(path,seal,Path(r['qualification_output']))
    except Exception as error:
        dest=output.with_name(output.name+'.qualification-hold.json')
        if not dest.exists():life.save(dest,dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            traceback=traceback.format_exc(),coverage_admitted=False,retry=False))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run'])
    p.add_argument('--input',type=Path,required=True);p.add_argument('--seal',required=True);p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.mode=='prepare':
        require(a.output is not None,'Output required');prepare(a.input.absolute(),a.seal,a.output.absolute())
    else:run(a.input.absolute(),a.seal)
