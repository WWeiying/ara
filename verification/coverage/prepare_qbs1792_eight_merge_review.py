"""Offline exact EL mutual/protection review only; no EL output, DVE or application."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tkinter

import seal_qbs_full1792_qualified as qualified

f=qualified.f
SCRIPT=Path(__file__).resolve()
TEST=SCRIPT.with_name('test_qbs1792_eight_merge_review.py')
EIGHT=f.proof.OUT/'eight-policy-csv-fixed-729-agent-20261006-01'
EIGHT_EL_SHA='89c1be51219024cf240bc7cee591fb11bda3c31a63040206005ac18c538d7934'


def records(raw):
    f.require(0<len(raw)<8*1024*1024,'Bounded native EL required')
    t=tkinter.Tcl();t.tk.wantobjects(False);t.eval(qualified.native.MULTISET.read_text())
    try: rows=[t.splitlist(x) for x in t.splitlist(t.call('nem_records',raw.decode('ascii')))]
    except (UnicodeError,tkinter.TclError) as exc:raise ValueError('Invalid exact native records: '+str(exc)) from exc
    f.require(all(len(r)==10 for r in rows),'Typed complete native tuples required')
    return rows


def mutual(eight,qbs):
    f.require(len(eight)==5892 and len(qbs)==1792,'Exact5892+1792 populations required')
    key=lambda r:(r[0],r[3],r[4],r[7])
    a={key(r) for r in eight};b={key(r) for r in qbs}
    f.require(len(a)==len(eight) and len(b)==len(qbs) and a.isdisjoint(b),'Native identity duplicate/overlap')
    modules={};metrics={}
    for r in eight+qbs:
        scope,module,metric,kind=r[:4]
        f.require(scope not in modules or modules[scope]==module,'Shared scope compiled module mismatch')
        modules[scope]=module
        mk=(scope,kind)
        f.require(mk not in metrics or metrics[mk]==metric,'Shared metric checksum mismatch')
        metrics[mk]=metric
    qscopes={r[0] for r in qbs}
    f.require(len(qscopes)==2 and all(r[3]=='Condition' and r[2]=='2947893042' for r in qbs), 'Exact two QBS Condition scopes required')
    f.require(not any(r[0] in qscopes and r[3]=='Condition' for r in eight),'Old eight touches QBS target/protected Condition space')
    return dict(status='OFFLINE_NATIVE_EL_DISJOINT_SHARED_SCOPE_DIFFERENT_METRIC_PASS',
        existing_records=5892,new_records=1792,expected_union_records=7684,
        native_point_identity_overlap_count=0,overlapping_native_points=[],
        shared_scopes=sorted(qscopes&{r[0] for r in eight}),
        shared_scope_populations=[dict(scope=s,existing_Branch_records=sum(r[0]==s and r[3]=='Branch' for r in eight),
            existing_Condition_records=0,new_Condition_records=sum(r[0]==s for r in qbs)) for s in sorted(qscopes)],
        shared_scope_semantics='Existing payload Branch versus new Condition; numeric IDs alone are NOT keys.',
        existing_QBS_condition_records=0,protected_QBS_condition_points=41214,
        future_combined_native_qualification='HOLD_NOT_EXECUTED',final_application=False)


def union_gate(raw,eight,qbs):
    mutual(eight,qbs);actual=records(raw)
    f.require(Counter(actual)==Counter(eight+qbs),'Exact merged identity/attribute/annotation multiset differs')
    return len(actual)


def evidence(manifest,seal):
    f.require(f.sha(manifest)==seal,'External qualified manifest seal drift')
    q=json.loads(manifest.read_bytes());f.check_pins(q['pins']);qualified.gate(q['qualification'])
    f.require(q['native_qualified_within_scope'] is True and q['final_application'] is False and
        q['source_boundary_not_extended_to_X_or_delta'] is True,'Qualification boundary/application drift')
    qraw=(qualified.RUN/'first.el').read_bytes();qrows=records(qraw)
    f.require(sorted([list(r) for r in qrows])==q['actual_annotated_native_records'],'Qualified annotated records differ')
    raw=(EIGHT/'applied.el').read_bytes();reload=(EIGHT/'reloaded.el').read_bytes()
    f.require(f.sha(EIGHT/'applied.el')==EIGHT_EL_SHA,'Actual eight EL reference drift')
    eight=records(raw);f.require(Counter(eight)==Counter(records(reload)),'Eight reference actual multiset drift')
    result=mutual(eight,qrows)
    # Do not salvage the earlier failed aggregate eight run.
    log=(EIGHT/'DVEfiles/dve_gui.log').read_text()
    f.require('EIGHT_ERROR Combined EL actual reload bytes differ' in log,'Historical eight status requires explicit re-review')
    execution=json.loads((EIGHT/'execution.json').read_bytes())
    f.require(execution['returncode']==0,'Eight reference execution changed')
    pins=dict(q['pins']);pins[str(manifest)]=seal
    for p in (SCRIPT,TEST,qualified.SCRIPT,qualified.TEST,qualified.native.MULTISET,
              EIGHT/'applied.el',EIGHT/'reloaded.el',EIGHT/'config.json',EIGHT/'status.json',
              EIGHT/'execution.json',EIGHT/'DVEfiles/dve_gui.log'):
        pins[str(p)]=f.sha(p)
    return dict(schema='QBS1792_EIGHT_NATIVE_MERGE_REVIEW_V1',pins=pins,qualified_manifest=str(manifest),qualified_seal=seal,
        disjoint_review=result,source_control_boundary=f.SCOPE_BOUNDARY,
        old_eight_reference=dict(directory=str(EIGHT),EL=str(EIGHT/'applied.el'),EL_sha=EIGHT_EL_SHA,
            population=729,aggregate_run_remains_HOLD=True,offline_reference_EL_only=True,
            not_relabelled_as735_or_latest=True,existing_eight_policies=['qbs','debug','operand','ff1','exponent','pack','lzc','snapshot']),
        future_qualification_plan=dict(status='NATIVE_HOLD_NOT_LAUNCHED',expected_records=7684,
            expected_kinds=dict(Branch=5808,Condition=1876),
            source_binding='Reuse reviewed per-policy binders and exact qualified QBS tuples; pin explicitly parent-selected current population/config, source/control contracts and protection ledgers. No automatic729->latest membership substitution.',
            stages=['initial-global-empty','before','selected','reset','reloaded','after-root-if-reporting','final','cleanup-global-empty'],
            old_eight_audit_per_stage=23666,QBS_audit_per_stage=3584,combined_audit_per_stage=27250,
            expected_selected=7684,retained_audited_neighbors=19566,
            preserved_raw_QBS_condition_complement=41214,
            target_scope_resolution='Resolve/verify native objects from actual path/meta in the fresh session; imported numeric IDs must match exact saved native tuples, never compiled XML IDs.',
            selection='Temporary import existing8 exact EL and QBS1792 exact EL in disposable session; recalculate, strict7684 global EL, all existing8 protection checks plus QBS3584 audit; no whole scope/metric/condition exclusion.',
            reset_reload='Reset global empty, reload combined exact7684 EL, repeat all stages/protections and strict annotated multiset; final/cleanup global empty mandatory.',
            root_protection='Preserve existing8 after-root audit/metric protections if producing hierarchical percentages; cannot claim rooted report qualification from this static plan.',
            scope_cross_metric_guard='Payload Branch targets are legal existing policy points; all41214 non-target payload Condition points stay protected. Reject newly excluded neighbor Condition, extra metric/scope, changed annotation/ID/checksum/width/bit/vector.',
            budget='No launch budget authorized here; existing8 workflow previously10800s, QBS1792 standalone3600s. Parent should size a single bounded successor after reviewing combined call count; no silent3600s promise or automatic retry.',
            authorization_required=True),
        merged_EL_written=False,DVE_started=False,final_waiver_approval=False,final_application=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','verify','check-union'))
    parser.add_argument('--qualified',type=Path,required=True);parser.add_argument('--qualified-seal',required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');parser.add_argument('--candidate-el',type=Path)
    args=parser.parse_args();out=args.output.absolute();manifest=args.qualified.absolute()
    f.require(out.parent==f.proof.OUT and out.resolve()==out,'Independent direct output required')
    if args.command=='prepare':
        f.require(not out.exists(),'Existing sealed evidence protected');record=evidence(manifest,args.qualified_seal)
        out.mkdir();f.write(out/'merge-review-plan.json',record)
        print(json.dumps(dict(output=str(out),seal=f.sha(out/'merge-review-plan.json'),pins=len(record['pins']),native_status='HOLD')))
    else:
        path=out/'merge-review-plan.json';f.require(f.sha(path)==args.seal,'External merge plan seal drift')
        f.require(json.loads(path.read_bytes())==evidence(manifest,args.qualified_seal),'Merge evidence reproduction differs')
        if args.command=='check-union':
            f.require(args.candidate_el is not None,'Read-only actual EL input required')
            count=union_gate(args.candidate_el.read_bytes(),records((EIGHT/'applied.el').read_bytes()),records((qualified.RUN/'first.el').read_bytes()))
            print('EXACT_NATIVE_MULTISET_PASS_'+str(count)+'_NOT_COMPLETE_NATIVE_QUALIFICATION')
        else:print('VERIFY_PASS_OFFLINE_MERGE_PLAN_NATIVE_HOLD_NO_APPLY')


if __name__=='__main__':main()
