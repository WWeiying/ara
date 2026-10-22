"""One bounded tile-range run, reusing the frozen entropy foreground lifecycle."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import sys

import preflight_akv_tile_range_capture as case
import run_akv_entropy as old
import collect_akv_tile_range_capture as collector

life, require = old.life, case.require
PRE=life.OUT/'akv-tile-range-capture-preflight780-agent-20261008-01'
PRE_SHA='ba16e2afda7474071ba388d55d2f7ed25e499387d0b03c53cd7f2597dd073d8d'
BASE=life.OUT/'dtlb-ppn-swap-offline-admitted780-agent-20261008-01'
BASE_SHA='4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b'
ELF=PRE/'input.elf'
PROBE=Path(__file__).with_name('akv_tile_range_probe.tcl').resolve()
NAME='akv_tile_range_capture'


def command(output):
    g=dict(old.command.__globals__,ELF=ELF,PROBE=PROBE,NAME=NAME)
    return FunctionType(old.command.__code__,g)(output)


def historical(ledger,base,newhash):
    # Reuse the sealed779 ledger audit, then resolve only the admitted780 suffix.
    from admit_stride_metadata768 import dedup
    path=BASE/'elf-ledger-dedup.json'
    audit=life.read_bound(path,base['output_pins'][str(path)])
    require(audit['ledger_members']==779 and len(audit['members'])==779 and
            [m['vdb'] for m in audit['members']]==ledger[1:780], 'Exact historical779 audit prefix')
    authority=life.merge_pins(base['input_pins'],base['output_pins'])
    require(all(authority.get(p)==h for p,h in audit['pins'].items()),'Historical audit authority')
    for member in audit['members']:
        require(member['ELF_candidates'] and all(h!=newhash for h in member['ELF_candidates'].values()),'Duplicate historical ELF')
    suffix=dedup([ledger[0],ledger[780]],newhash,authority)
    require(all(authority.get(p)==h for p,h in suffix['pins'].items()),'780 suffix historical authority')
    pins=life.merge_pins(audit['pins'],suffix['pins'])
    pins=life.merge_pins(pins,{str(path):base['output_pins'][str(path)]})
    life.check(pins)
    return pins,dict(baseline=780,members=780,duplicate=False,prior_audit_sha256=base['output_pins'][str(path)],
                     suffix=suffix['members'],candidate_not_used_as_historical_owner=True)


def prepare(output,existing=False):
    output=Path(output).absolute()
    require(output.parent==life.OUT and output.resolve()==output and (output.is_dir() if existing else not output.exists()),'Fresh/direct output')
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SHA)
    require(pre['status']=='AKV_TILE_RANGE_SOFTWARE_PREFLIGHT_PASS_NOT_VCS' and pre['input_elf']==str(ELF)
            and pre['dut_checks']==3872 and pre['dut_traps']==3 and pre['dut_commands']==6
            and pre['oracle']['indices']==case.INDICES and pre['coverage_admitted'] is False,'Exact preflight')
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    require(base['coverage_admitted'] is True and base['output']==str(BASE),'Formal780 authority')
    ledger_path=BASE/'combined-inputs.txt'; bits_path=BASE/'combined-bits.json'
    require(case.old.sha(ledger_path)==base['output_pins'][str(ledger_path)],'780 ledger drift')
    ledger=ledger_path.read_text().splitlines()
    bits=life.read_bound(bits_path,base['output_pins'][str(bits_path)])
    require(len(ledger)==len(set(ledger))==781 and bits['tests']==ledger[1:],'Exact780 population')
    pins=life.merge_pins(pre['pins'],{str(PRE/'preflight-manifest.json'):PRE_SHA,str(BASE/'admission-manifest.json'):BASE_SHA,
        str(ledger_path):base['output_pins'][str(ledger_path)],str(bits_path):base['output_pins'][str(bits_path)]})
    hp,dedup=historical(ledger,base,pins[str(ELF)]); pins=life.merge_pins(pins,hp)
    image=life.read_bound(life.PLAN,life.PLAN_SEAL)
    require(len(image['image'])==66 and image['simv']==str(life.IMAGE),'Frozen66 image')
    pins=life.merge_pins(pins,image['image']); pins=life.merge_pins(pins,{str(life.PLAN):life.PLAN_SEAL})
    book=life.read_bound(case.old.BUILD/'build-source-pins.json',pins[str(case.old.BUILD/'build-source-pins.json')])
    dispatcher=life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
    pins=life.merge_pins(pins,{str(dispatcher):book[str(life.ROOT/'hardware/src/ara_dispatcher.sv')]})
    db=collector.old.isa.base.native.common.DESIGN/'snps/coverage/db'
    paths=[db/'design/verilog.design.xml',db/'auxiliary/verilog.sourceinfo.xml']
    paths += [db/('shape/'+metric+'.verilog.'+kind+'.xml') for metric in ('line','branch','tgl') for kind in ('shape','info')]
    for p in paths:
        require(str(p) in base['input_pins'],'Missing compiled authority: '+str(p))
        pins=life.merge_pins(pins,{str(p):base['input_pins'][str(p)]})
    pins,source=collector.old.isa.base.source_contract(book,pins)
    from inventory_operand_debug import Design
    module=sys.modules[Design.__module__]
    p=Path(module.__file__).resolve(); pins=life.merge_pins(pins,{str(p):case.old.sha(p)})
    for module in tuple(sys.modules.values()):
        file=getattr(module,'__file__',None)
        if file:
            p=Path(file).resolve()
            if p.suffix=='.py' and (p.parent==Path(__file__).resolve().parent or p.is_relative_to(life.ROOT/'verification/ara_verify')):
                pins=life.merge_pins(pins,{str(p):case.old.sha(p)})
    pins=life.merge_pins(pins,{str(PROBE):case.old.sha(PROBE),str(Path(__file__).with_name('test_akv_tile_range_runtime.py').resolve()):case.old.sha(Path(__file__).with_name('test_akv_tile_range_runtime.py')),
        str(collector.old.CONVERTER):collector.old.CONVERTER_SHA})
    life.check(pins)
    _,dry=collector.replay(ELF.read_bytes(),pre['symbols'])
    return output,dict(case=NAME,preflight=pre,pins=pins,command=command(output),timeout_s=600,wave_limit_bytes=64*1024*1024,
        baseline_tests=780,baseline=str(BASE),baseline_sha256=BASE_SHA,historical_ELF_dedup=dedup,
        dry_model=dry,source_proof=source,coverage_admitted=False,automatic_retry=False,EDA_launched=False,
        qualification_requires_native_capture_AR_and_ranges=True,probe_widths=collector.WIDTHS)


def run(output,manifest):
    g=dict(old.live_identity.__globals__,ELF=ELF)
    live=FunctionType(old.live_identity.__code__,g)
    g=dict(old.run.__globals__,command=command,live_identity=live)
    FunctionType(old.run.__code__,g)(output,manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--prepared-seal')
    a=p.parse_args(); require((a.mode=='run')==bool(a.prepared_seal),'Explicit run seal only')
    out,m=prepare(a.output); record=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(record,m); print(json.dumps(dict(prepared=str(record),seal=case.old.sha(record),pins=len(m['pins']))))
    else:
        require(life.read_bound(record,a.prepared_seal)==m,'Prepared contract drift'); run(out,m)
