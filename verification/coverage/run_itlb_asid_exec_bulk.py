"""Fresh bulk ITLB run, fixed600s, automatic terminal-only qualification, no admission."""
import argparse
from pathlib import Path
import sys
import traceback
import run_itlb_asid_exec as original
import collect_itlb_asid_exec_bulk as collector

life,require=collector.life,collector.require
command=original.command
SCHEMA='ITLB_BULK_FROZEN600_AUTOQUALIFY_V1'
VARIANT='ITLB_BULK_SOURCE_PACKED189_CSR6'


def prepare(path,seal,output):
    require(seal==collector.PREFLIGHT_SHA,'Exact frozen bulk preflight seal required')
    q=life.read_bound(path,seal)
    require(q['status']=='ITLB_TRUE_SMODE48_SPIKE_PTE_CODE_CSR_PASS_NOT_RTL' and
        q['baseline']==771 and q['software_checks']==10966 and q['trap_count']==48 and
        q['counts']['matched_instructions']==103572 and not q['coverage_admitted'] and
        not q['VCS_launched'],'Complete bulk reference required')
    require(output.parent==life.OUT and output.resolve()==output and not output.exists() and
        not output.with_name(output.name+'.prepared.json').exists(),'Fresh independent output required')
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Frozen66 image required')
    bits,ledger,bpins=collector.baseline()
    pins=life.merge_pins(q['input_pins'],image['image'])
    require(bits['design']==collector.bulk.life.read_bound(collector.bulk.old.BASE/'combined-bits.json',
        q['input_pins'][str(collector.bulk.old.BASE/'combined-bits.json')])['design'],
        'Static771 and measurement773 compiled design must match exactly')
    pins=life.merge_pins(pins,bpins)
    pins=life.merge_pins(pins,{str(path):seal,str(life.PLAN):life.PLAN_SEAL})
    files=[Path(__file__).resolve(),Path(__file__).with_name('test_run_itlb_asid_exec_bulk.py'),
        Path(collector.__file__).resolve(),Path(__file__).with_name('test_collect_itlb_asid_exec_bulk.py'),
        original.PROBE,collector.CONVERTER]
    require(life.digest(collector.CONVERTER)==collector.CONVERTER_SHA,'Converter differs')
    collector.source_layout()
    collector.bulk.source_contract()
    require(collector.bulk.elf_contract(path.parent/'input.elf')==life.read_bound(
        path.parent/'elf-preload-proof.json',q['input_pins'][str(path.parent/'elf-preload-proof.json')]),
        'Exact bulk ELF preload proof required')
    for module in tuple(sys.modules.values()):
        f=getattr(module,'__file__',None)
        if f and str(collector.bulk.ROOT/'verification') in f and Path(f).is_file():
            files.append(Path(f).resolve())
    files.extend((collector.bulk.ROOT/'verification/ara_verify').glob('*.py'))
    for p in files:pins=life.merge_pins(pins,{str(p):life.digest(p)})
    require(str(path.parent/'input.elf') in pins and q['symbols']['tohost']==0x80001000,'Exact ELF/tohost')
    life.check(pins)
    record=dict(schema=SCHEMA,driver_variant=VARIANT,case=original.CASE,output=str(output),
        preflight=str(path),preflight_seal=seal,preflight_static_base=771,
        baseline=str(collector.BASE),baseline_seal=collector.BASE_SHA,measurement_base=773,
        compiled_design=ledger[0],command=command(path.parent/'input.elf',output),timeout_s=600,
        pins=pins,automatic_retry=False,coverage_admitted=False,official_percentage=False,
        qualification_output=str(output.with_name(output.name+'-qualified')))
    dest=output.with_name(output.name+'.prepared.json');life.save(dest,record)
    print('PREPARED',str(dest),life.digest(dest),flush=True)


def validate_record(r):
    output=Path(r['output'])
    require(r['schema']==SCHEMA and r['driver_variant']==VARIANT and r['case']==original.CASE and
        r['timeout_s']==600 and r['baseline']==str(collector.BASE) and
        r['baseline_seal']==collector.BASE_SHA and r['measurement_base']==773 and
        r['preflight_seal']==collector.PREFLIGHT_SHA and r['preflight_static_base']==771 and
        not r['coverage_admitted'] and not r['automatic_retry'] and
        r['command']==command(Path(r['preflight']).parent/'input.elf',output) and
        output.parent==life.OUT and output.resolve()==output,'Exact fixed bulk command required')
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
