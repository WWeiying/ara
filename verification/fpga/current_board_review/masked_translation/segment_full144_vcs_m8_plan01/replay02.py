#!/usr/bin/env python3
"""Only supersede the independently approved mutable-document pin; no oracle delta."""
from pathlib import Path
import shlex
import sys
sys.dont_write_bytecode=True
import replay as base

ADDENDUM=base.SOURCE_REVIEW/'SOURCE_ADDENDUM01.json'
ADDENDUM_SHA='67e45f87dd67f1727dff5456ea2bd855cc87d15d7dc09081e4b42a44473baa79'
BASE_PINS=dict(base.SOURCE_REVIEW_PINS)
DOC=str(base.HERE.parent/'segment_full144_main_review01.md')
OLD='f6c02707df51dcd5ff711dd5e690174ba2ad8597d417b93b2d48ce4f86f58d0d'
NEW='28c2c5904172343205b3f8a0ac10f0844182f51238aec65a1e97bee61fe04165'

def effective_binding(original,addendum):
    require=base.require
    require(addendum['decision']=='NO_BLOCKER_SOURCE_REFERENCE_DOCUMENT_PIN_SUPERSESSION_ONLY' and
            addendum['no_blocker_source_reference'] and addendum['reference_raw_review_accepted'] and
            addendum['source_READY_sha256']==base.c.READY_SHA and addendum['evidence_pins_count']==87 and
            addendum['full144_actual_contexts_checked']==144 and not addendum['worker_entry_reviewed'] and
            not addendum['DUT_authorized_by_this_review'],'Actual source addendum scope')
    replacements=addendum['superseded_pins']
    require(len(replacements)==1 and {k:replacements[0][k] for k in ('path','old_sha256','new_sha256')} ==
            dict(path=DOC,old_sha256=OLD,new_sha256=NEW),'Only exact authorized document replacement')
    require(original['hashes'][DOC]==OLD,'Original document evidence must remain bound')
    expected=dict(original['hashes']); expected[DOC]=NEW
    require(addendum['effective_hashes']==expected,'No other source/reference pin substitution')
    return expected

def source_review02():
    base.verify(BASE_PINS); base.require(base.sha(ADDENDUM)==ADDENDUM_SHA,'Addendum drift')
    a=base.read(ADDENDUM); original=base.read(base.SOURCE_REVIEW/'REVIEW.json')
    for pathkey,hashkey in (('base_review_path','base_review_sha256'),('base_report_path','base_report_sha256')):
        base.require(BASE_PINS.get(a[pathkey])==a[hashkey],'Addendum original review identity')
    pins=effective_binding(original,a)
    pins.update(BASE_PINS); pins[str(ADDENDUM)]=ADDENDUM_SHA
    for pathkey,hashkey in (('backend_focused_report','backend_focused_report_sha256'),('backend_probe','backend_probe_sha256')):
        pins[a[pathkey]]=a[hashkey]
    base.verify(pins)
    return pins

base.SOURCE_REVIEW_PINS={**BASE_PINS,str(ADDENDUM):ADDENDUM_SHA}
base.source_review=source_review02
original_validate=base.validate

def validate02(plan,image):
    original_validate(plan,image)
    base.require(plan['pins'].get(str(Path(__file__).resolve()))==base.sha(__file__),'Successor entrypoint drift')

base.validate=validate02

def numeric_monitor(original):
    def monitor(command,cwd,console_path,timeout_s,cancel_event=None):
        result=original(command,cwd,console_path,timeout_s,cancel_event)
        rc,elapsed,timed,failed=result
        # First operation on the returned tuple: durable primitives only. No
        # command hash, metadata reads or architectural decision precedes this.
        base.save(Path(console_path).parent/'monitor_numeric.unvalidated.json',
                  dict(schema='ACTUAL_MONITOR_NUMERIC_V1',architectural_acceptance=False,
                       returncode=rc,elapsed_s=elapsed,timed_out=timed,failure_seen=failed))
        return result
    return monitor

original_run=base.run

def run02(args):
    base.common.image_context(args.image)
    import ara_verify.runner as engine
    original=engine._run_monitored
    engine._run_monitored=numeric_monitor(original)
    try:return original_run(args)
    finally:engine._run_monitored=original

base.run=run02

def main():
    result=base.main()
    if sys.argv[1]=='prepare':
        out=Path(sys.argv[sys.argv.index('--out')+1]).resolve()
        ready=base.read(out/'ready.json')
        command=list(ready['command']); command[2]=str(Path(__file__).resolve())
        service=shlex.split(ready['service_command'])
        service[service.index(str(base.HERE/'replay.py'))]=str(Path(__file__).resolve())
        base.save(out/'ready02.json',dict(ready,command=command,service_command=shlex.join(service),
             authoritative_entrypoint=str(Path(__file__).resolve()),
             supersedes_ready_command_only=str(out/'ready.json'),source_addendum_sha256=ADDENDUM_SHA))
        print('AUTHORITATIVE_READY',out/'ready02.json',flush=True)
    return result

if __name__=='__main__': raise SystemExit(main())
