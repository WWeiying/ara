"""Seal actual full native qualification, never exclusion application or admission."""
import argparse
import hashlib
import json
from pathlib import Path

import prepare_qbs_full1792_multiset_v2 as native

f = native.f
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_seal_qbs_full1792_qualified.py')
RUN = f.proof.OUT/'qbs-full1792-native-multiset-v2-agent-20261006-01'
RUN_SHA = '15511391e5bc9295eee799e20e680be7e24c1498c930d05ed4a63b0e04e1b111'
STARTUP = f.proof.OUT/'qbs-full1792-multiset-v2-actual-executable-agent-20261006-01.json'
STARTUP_SHA = '4cb1bb6bf980152c9c574cb406f16c172ca5119c9c798ea5da640368b8e5b08a'


def gate(result):
    f.require(result['status']=='FULL1792_NATIVE_MULTISET_SIGNATURE_PROTECTION_PASS_NOT_APPLICATION' and
        result['target_count']==1792 and result['protected_count']==41214 and result['five_stages_pass'] is True and
        result['application'] is False and len(result['actual_native_records'])==1792 and
        result['source_control_boundary']==f.SCOPE_BOUNDARY and result['not_arbitrary_X_or_delta_proof'] is True,
        'Exact qualification/source-control scope required')


def evidence():
    native.configure(); artifact = native.old.verify(RUN,RUN_SHA)
    f.require(f.sha(STARTUP)==STARTUP_SHA,'Independent actual executable receipt drift')
    startup=json.loads(STARTUP.read_bytes())
    f.require(startup['executable_verified'] is True and startup['plan_seal']==RUN_SHA and
        startup['actual_script']==str(native.TCL),'Actual executable/profile binding missing')
    result=native.inspect(RUN,artifact); gate(result)
    plan=json.loads((RUN/'qualification-plan.json').read_bytes()); pins=dict(plan['pins'])
    paths=[RUN/name for name in ('qualification-plan.json','selection.tcl','first.el','second.el',
        'native-qualification.tcllist','initial-empty.el','before-empty.el','reset-empty.el','final-empty.el','cleanup-empty.el',
        'DVEfiles/dve_gui.log','DVEfiles/session.tcl')]+[SCRIPT,TEST,STARTUP]
    for path in paths: pins[str(path)]=f.sha(path)
    canonical=sorted([list(r) for r in native.canonical((RUN/'first.el').read_bytes(),artifact).elements()])
    digest=hashlib.sha256(json.dumps(canonical,ensure_ascii=True,separators=(',',':')).encode('ascii')).hexdigest()
    return dict(schema='QBS_FULL1792_QUALIFIED_MANIFEST_V1',status=result['status'],pins=pins,
        execution_provenance='PARENT_AGENT_INDEPENDENT_EXECUTION',inspection_provenance='AGENT_INDEPENDENT_OFFLINE_INSPECTION',
        qualification_run=str(RUN),qualification_plan_seal=RUN_SHA,actual_executable_receipt_seal=STARTUP_SHA,
        native_qualified_within_scope=True,qualification=result,actual_annotated_native_records=canonical,
        annotated_multiset_sha256=digest,
        canonical_digest_encoding='sha256(json.dumps(sorted(list(nem_records tuples)),ensure_ascii=True,separators=(comma,colon)).encode(ascii)); multiplicity preserved',
        scope_protection=native.old.single.audit.protection(artifact),
        stages=[dict(stage=s,audited=3584,excluded=e,neighbors_excluded=0) for s,e in
            (('before',0),('selected',1792),('reset',0),('reloaded',1792),('final',0))],
        state_checks=17920,original_v1_failure_remains_HOLD=True,
        source_annotation_historical_NATIVE_HOLD_label_not_modified=True,
        source_boundary_not_extended_to_X_or_delta=True,final_application=False,final_waiver_approval=False,
        coverage_admission=False,simulations_started=False,DVE_started_by_this_tool=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','verify'));parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seal');args=parser.parse_args();output=args.output.absolute()
    f.require(output.parent==f.proof.OUT and output.resolve()==output,'Direct independent output required')
    if args.command=='prepare':
        f.require(not output.exists(),'Existing sealed evidence protected')
        record=evidence();output.mkdir();f.write(output/'qualified-manifest.json',record)
        print(json.dumps(dict(output=str(output),seal=f.sha(output/'qualified-manifest.json'),pins=len(record['pins']),final_application=False)))
    else:
        path=output/'qualified-manifest.json';f.require(f.sha(path)==args.seal,'External qualified seal drift')
        f.require(json.loads(path.read_bytes())==evidence(),'Qualified evidence reproduction differs')
        print('VERIFY_PASS_QUALIFIED_WITHIN_SOURCE_SCOPE_NOT_FINAL_APPLICATION')


if __name__=='__main__':main()
