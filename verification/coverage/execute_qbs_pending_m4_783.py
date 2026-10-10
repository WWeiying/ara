"""Thin inherited foreground worker; fresh collector-ready contract, parent authorization only."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import run_qbs_pending_m4_783 as proof
import collect_qbs_pending_m4_783 as collector

life,require=proof.life,collector.require


def prepare(out):
    out,record=proof.prepare(out)
    symbols,data,sites,items=collector.elf_view()
    for phase in (0,1):collector.regions(phase,symbols,data,items)
    files=[Path(__file__),Path(collector.__file__),Path(__file__).with_name('test_qbs_pending_m4_runtime783.py')]
    extra={str(p.resolve()):life.digest(p) for p in files}
    record['pins']=life.merge_pins(record['pins'],extra)
    record.update(collector_ready=True,qualification_schema='TWO_M4_FUNCTIONAL_NATIVE_CYCLE_AND_RAW_QUALIFIED_NOT_ADMITTED',
        collector=str(Path(collector.__file__).resolve()),parent_authorization_required_for_run=True,
        worker='Sealed run_gap110_simulation.run with exact ELF/name/command callback substitutions',
        run_budget_s=600,outer_service_budget_recommended_s=660,automatic_retry=False,
        terminal_inspect_required=True,qualification_required=record['qualification_required'])
    life.check(record['pins']);return out,record


def run(out,record):
    require(record['collector_ready'] is True and record['timeout_s']==600 and
        record['command']==proof.command(out),'Exact collector-ready600 worker contract')
    template=proof.old.old
    ns=dict(vars(template),NAME=proof.NAME,ELF=proof.ELF,ELF_SEAL=proof.ELF_SHA,command=proof.command)
    FunctionType(template.run.__code__,ns)(out,record)


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal');p.add_argument('--parent-authorized',action='store_true')
    a=p.parse_args();require((a.mode!='prepare')==bool(a.prepared_seal),'Verify/run requires fixed prepared seal')
    require(a.parent_authorized==(a.mode=='run'),'Run requires explicit parent agent authorization')
    out,record=prepare(a.output);path=out.with_name(out.name+'.prepared.json')
    if a.mode=='prepare':
        life.save(path,record);print(json.dumps(dict(prepared=str(path),seal=life.digest(path),pins=len(record['pins']),collector_ready=True)));return
    require(life.read_bound(path,a.prepared_seal)==record,'Frozen new run contract drift')
    if a.mode=='verify':print('VERIFY_PASS_COLLECTOR_READY_NO_EDA');return
    run(out,record)


if __name__=='__main__':main()
