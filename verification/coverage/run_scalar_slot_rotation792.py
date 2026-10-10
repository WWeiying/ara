"""One 120s parent-authorized frozen-image slot-rotation worker; no auto-launch."""
import argparse
import json
from pathlib import Path
import re
from types import FunctionType
import build_scalar_slot_rotation792 as oracle
import run_scalar_misalign789 as old

life, require, template, converter = old.life, old.require, old.template, old.converter
exact_fields=old.exact_fields
BASE, BASE_SHA=oracle.BASE,oracle.BASE_SHA
NAME,BUDGET='scalar_slot_rotation792',120
IMAGE_SHA=old.IMAGE_SHA
PROBE=Path(__file__).with_name('scalar_slot_rotation792_probe.tcl').resolve()
SERVICE='ara-scalar-slot-rotation792-parent-20261008-01.service'
PRE=ELF=None
PRE_SEAL=ELF_SHA=None
APPROVED_PRE=life.OUT/'scalar-slot-rotation792-preflight-parent-20261008-03'
APPROVED_PRE_SEAL='b10eb7a59693d32d997ff96ce4a0a78f95ce6496d6b1ea3e866fda4d589dd3f9'


def configure(pre,seal):
    global PRE,PRE_SEAL,ELF,ELF_SHA
    PRE=Path(pre).absolute(); PRE_SEAL=seal
    require(PRE==APPROVED_PRE and seal==APPROVED_PRE_SEAL,'Exact parent03 authority')
    m=life.read_bound(PRE/'preflight-manifest.json',seal)
    require(m['baseline_seal']==BASE_SHA and m['coverage_admitted'] is False and m['VCS_authorized'] is False,'Software-only formal792')
    life.check(m['pins']); life.check(m['output_pins'])
    ELF=PRE/'input.elf'; ELF_SHA=m['output_pins'][str(ELF)]
    return m


def reference(pre): return oracle.reference(PRE/'spike.trace',pre['symbols'])


def command(out):
    return FunctionType(old.command.__code__,dict(old.command.__globals__,ELF=ELF,NAME=NAME,PROBE=PROBE))(out)


def manifest(out,service=SERVICE):
    import collect_scalar_slot_rotation792 as collector
    out=Path(out).absolute(); require(out.parent==life.OUT and out.resolve()==out,'Canonical output')
    require(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service',service) is not None,'Service identity')
    pre=configure(PRE,PRE_SEAL); s=oracle.elf_shape(ELF)
    ledger=oracle.traps((PRE/'spike.trace').read_text(),s); ref=reference(pre)
    require(oracle.validate(ref,s,ledger)==pre['validation'],'Full12-trap independent gold')
    counts=template.reference_counts(ref,0x80000000,s['tohost'])
    counts={k:counts[k] for k in ('matched_instructions','matched_scalar_writes','matched_scalar_memory_accesses')}
    require(counts['matched_instructions']==pre['validation']['retired_instructions'] and counts['matched_scalar_memory_accesses']==pre['validation']['scalar_memory_accesses'],'Derived exact reference counts')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True,'Formal792 admitted')
    pins=life.merge_pins(pre['pins'],pre['output_pins'])
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['image'][str(life.IMAGE)]==IMAGE_SHA,'Frozen image66')
    proof=collector.source_proof()
    for more in (image['image'],image['design_files'],proof['pins'],
                 {str(PRE/'preflight-manifest.json'):PRE_SEAL,str(BASE/'admission-manifest.json'):BASE_SHA,str(life.PLAN):life.PLAN_SEAL},
                 {str(BASE/n):base['output_pins'][str(BASE/n)] for n in ('status.json','combined-inputs.txt','combined-bits.json','combined-toggle-bits.json')}):
        pins=life.merge_pins(pins,more)
    ledgerlines=(BASE/'combined-inputs.txt').read_text().splitlines()
    require(len(ledgerlines)==len(set(ledgerlines))==793 and json.loads((BASE/'status.json').read_bytes())['aggregate_passed']==792,'Exact792 membership')
    require(ELF_SHA not in set(base['input_pins'].values()),'No historical ELF hash duplicate')
    files=[Path(__file__).resolve(),PROBE,Path(collector.__file__),Path(old.__file__),Path(old.prior.__file__),Path(life.__file__),
           Path(__file__).with_name('test_scalar_slot_rotation792_runtime.py'),converter.CONVERTER,
           Path(collector.original.__file__),Path(collector.widths.__file__),Path(template.__file__),Path(template.frozen.__file__)]
    files+=list((life.ROOT/'verification/ara_verify').rglob('*.py'))
    require(life.digest(converter.CONVERTER)==converter.CONVERTER_SHA,'Converter identity')
    pins=life.merge_pins(pins,{str(f):life.digest(f) for f in files}); life.check(pins)
    return dict(case=NAME,output=str(out),pins=pins,command=command(out),timeout_s=BUDGET,
        input_elf=str(ELF),elf_sha256=ELF_SHA,input_spike_trace=str(PRE/'spike.trace'),preflight=str(PRE),preflight_seal=PRE_SEAL,
        image_sha256=IMAGE_SHA,raw_baseline=str(BASE),raw_baseline_seal=BASE_SHA,raw_baseline_population=792,
        source_contract=proof,scalar_reference_counts=counts,expected_traps=ledger,expected_slots=oracle.SLOTS,expected_checks=89,
        old_image_files_checked=66,automatic_retry=False,no_FSDB=True,focused_readonly_VPD=True,
        coverage_admitted=False,RTL_changed=False,terminal_oracle_verified=False,service=service,
        systemd_policy=dict(RuntimeMaxSec=170,TimeoutStopSec=10,KillMode='control-group'),
        authorization_source='SEPARATE_PARENT_REVIEW_REQUIRED_BEFORE_RUN')


def verify_prepared(out,record,terminal=False):
    configure(record['preflight'],record['preflight_seal'])
    require(terminal or not Path(out).exists(),'Fresh pre-run output')
    require(record==manifest(out,record['service']),'Full prepared binding drift')
    return record


def lifecycle_namespace(out,record):
    return FunctionType(old.lifecycle_namespace.__code__,dict(old.lifecycle_namespace.__globals__,PRE=PRE,ELF_SHA=ELF_SHA,IMAGE_SHA=IMAGE_SHA,BUDGET=BUDGET,NAME=NAME,command=command))(out,record)


def main():
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',required=True,type=Path); p.add_argument('--preflight',type=Path); p.add_argument('--preflight-seal')
    p.add_argument('--prepared-seal'); p.add_argument('--service',default=SERVICE); p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args(); out=a.output.absolute(); sidecar=out.with_name(out.name+'.prepared.json')
    require((a.mode=='run')==a.parent_authorized,'Explicit parent run authorization')
    if a.mode=='prepare':
        require(not out.exists() and not sidecar.exists() and a.preflight and a.preflight_seal and not a.prepared_seal,'Exclusive prepare')
        configure(a.preflight,a.preflight_seal); life.save(sidecar,manifest(out,a.service))
        print(json.dumps(dict(prepared=str(sidecar),seal=life.digest(sidecar),VCS_started=False)))
    else:
        require(a.prepared_seal and not a.preflight and not a.preflight_seal,'Prepared authority only')
        record=life.read_bound(sidecar,a.prepared_seal); verify_prepared(out,record)
        if a.mode=='run': lifecycle_namespace(out,record)['run'](out,record)
        else: print('SLOT_ROTATION792_PREPARED_VERIFY_PASS_NO_VCS')


if __name__=='__main__': main()
