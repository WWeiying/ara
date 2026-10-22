"""Fresh linear ITLB run, fixed600s, automatic terminal-only qualification, no admission."""
import argparse
from pathlib import Path
import sys
import traceback
import run_itlb_asid_exec as original
import collect_itlb_asid_exec_linear as collector

life,require=collector.life,collector.require
command=original.command
SCHEMA='ITLB_LINEAR_FROZEN600_AUTOQUALIFY_V1'
VARIANT='ITLB_LINEAR_SOURCE_PACKED189_CSR6'


def prepare(path,seal,output):
    require(seal==collector.PREFLIGHT_SHA,'Exact frozen linear preflight seal required')
    q=life.read_bound(path,seal)
    require(q['status']=='ITLB_TRUE_SMODE48_SPIKE_PTE_CODE_CSR_PASS_NOT_RTL' and
        q['baseline']==771 and q['software_checks']==10966 and q['trap_count']==48 and
        q['counts']['matched_instructions']==253120 and not q['coverage_admitted'] and
        not q['VCS_launched'],'Complete linear reference required')
    require(output.parent==life.OUT and output.resolve()==output and not output.exists() and
        not output.with_name(output.name+'.prepared.json').exists(),'Fresh independent output required')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Frozen66 image required')
    bits,ledger,bpins=collector.baseline()
    pins=life.merge_pins(q['input_pins'],image['image'])
    pins=life.merge_pins(pins,bpins)
    pins=life.merge_pins(pins,{str(path):seal,str(life.PLAN):life.PLAN_SEAL})
    files=[Path(__file__).resolve(),Path(__file__).with_name('test_run_itlb_asid_exec_linear.py'),
        Path(collector.__file__).resolve(),Path(__file__).with_name('test_collect_itlb_asid_exec_linear.py'),
        original.PROBE,collector.CONVERTER]
    require(life.digest(collector.CONVERTER)==collector.CONVERTER_SHA,'Converter differs')
    collector.source_layout()
    for module in tuple(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and str(collector.linear.ROOT/'verification') in f and Path(f).is_file():
            files.append(Path(f).resolve())
    files.extend((collector.linear.ROOT/'verification/ara_verify').glob('*.py'))
    for p in files:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    require(str(path.parent/'input.elf') in pins and q['symbols']['tohost']==0x80001000,'Exact ELF/tohost')
    life.check(pins)
    record=dict(schema=SCHEMA,driver_variant=VARIANT,case=original.CASE,output=str(output),
        preflight=str(path),preflight_seal=seal,preflight_static_base=771,
        baseline=str(collector.BASE),baseline_seal=collector.BASE_SHA,measurement_base=772,
        compiled_design=ledger[0],command=command(path.parent/'input.elf',output),timeout_s=600,
        pins=pins,automatic_retry=False,coverage_admitted=False,official_percentage=False,
        qualification_output=str(output.with_name(output.name+'-qualified')))
    dest=output.with_name(output.name+'.prepared.json');life.save(dest,record)
    print('PREPARED',str(dest),life.digest(dest),flush=True)


def validate_record(r):
    output=Path(r['output'])
    require(r['schema']==SCHEMA and r['driver_variant']==VARIANT and r['case']==original.CASE and
        r['timeout_s']==600 and r['baseline']==str(collector.BASE) and
        r['baseline_seal']==collector.BASE_SHA and r['measurement_base']==772 and
        r['preflight_seal']==collector.PREFLIGHT_SHA and r['preflight_static_base']==771 and
        not r['coverage_admitted'] and not r['automatic_retry'] and
        r['command']==command(Path(r['preflight']).parent/'input.elf',output) and
        output.parent==life.OUT and output.resolve()==output,'Exact fixed linear command required')
    return output


def run(path,seal):
    record=life.read_bound(path,seal);output=validate_record(record)
    require(not output.exists(),'No repeat run allowed')
    _,ledger,_=collector.baseline()
    require(record['compiled_design']==ledger[0],'Compiled design ledger differs')
    actual=dict(record,pins=life.merge_pins(record['pins'],{str(path):seal}))
    try:
        life.run(output,actual)
        collector.collect(path,seal,Path(record['qualification_output']))
    except Exception as error:
        dest=output.with_name(output.name+'.qualification-hold.json')
        if not dest.exists():life.save(dest,dict(status='HOLD_NOT_ADMITTED',reason=str(error),
            traceback=traceback.format_exc(),coverage_admitted=False,retry=False))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','run'])
    parser.add_argument('--input',type=Path,required=True);parser.add_argument('--seal',required=True)
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.mode=='prepare':
        require(args.output is not None,'Output required')
        prepare(args.input.absolute(),args.seal,args.output.absolute())
    else:run(args.input.absolute(),args.seal)
