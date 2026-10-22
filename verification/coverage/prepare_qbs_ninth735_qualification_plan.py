"""Static exact735 eight-plus-QBS qualification design and bounded call budget; no launch."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tkinter

import prepare_qbs1792_eight_merge_review as merge

f=merge.f
SCRIPT=Path(__file__).resolve()
TEST=SCRIPT.with_name('test_qbs_ninth735_qualification_plan.py')
REPORT=f.proof.OUT/'eight-policy-semantic-735-agent-20261006-02'
READER=REPORT/'epoch-readiness-735-v3-plan.json'
READER_SHA='3dc96b012c734be5fd8fbed0688429f150e1a6a4933f5da517e34a5198bff35c'
QUALIFIED=f.proof.OUT/'qbs-full1792-qualified-parent-20261006-01/qualified-manifest.json'
QUALIFIED_SHA='8d495aa66f024d82ce27fcf50ecd646e91388e3c4b1474b9454301fdc0e10565'
STAGES=('before','selected','reset','reloaded','after-root','final')
POINTS=dict(qbs=4238,debug=3008,operand=3636,ff1=1728,exponent=5616,pack=1144)


def constant_selection(text,group):
    """Execute only declarations in an isolated interpreter: source/exec/file/GUI unavailable."""
    t=tkinter.Tcl();t.tk.wantobjects(False);t.eval('interp create -safe counted')
    commands=t.splitlist(t.call('interp','eval','counted','info commands'))
    for name in commands:
        if name not in ('set','array','list'):t.call('interp','hide','counted',name)
    try:
        t.call('interp','eval','counted',text)
        name='qbs_native_keys' if group=='qbs' else ('op1144_keys' if group=='operand' else 'dbg_keys')
        flat=t.splitlist(t.call('interp','eval','counted','array get '+name))
        inventory={flat[i]:t.splitlist(flat[i+1]) for i in range(0,len(flat),2)}
        if group not in ('qbs','operand'):inventory={k:v for k,v in inventory.items() if k.endswith('|branch')}
        f.require(inventory,'Missing complete native metadata inventory')
        leaves=sum(len(v) for v in inventory.values())
        parents=sum(len({x.split(',')[0] for x in v}) for v in inventory.values())
        if group=='qbs':
            audit=t.splitlist(t.call('interp','eval','counted','array get qbs_audit_keys'))
            checked=sum(len(t.splitlist(audit[i+1])) for i in range(0,len(audit),2))
        else:checked=leaves
        f.require(checked==POINTS[group] and parents>0,'Exact six-policy audit inventory differs')
        return dict(scopes=len(inventory),nonempty_parent_coordinate_count=parents,
            metadata_leaves=leaves,audited_points=checked,
            coordinate_numbers_used_for_counts_only_NOT_native_selectors=True)
    except tkinter.TclError as exc:raise ValueError('Unsafe/nonconstant selection: '+str(exc)) from exc


def lzc_counts(text):
    t=tkinter.Tcl();t.tk.wantobjects(False)
    lines=[x for x in text.splitlines() if x.startswith('set seven_rows ')]
    f.require(len(lines)==1,'Exact constant LZC rows declaration required')
    declaration=t.splitlist(lines[0]);f.require(len(declaration)==3,'LZC declaration shape differs')
    rows=[t.splitlist(x) for x in t.splitlist(declaration[2])]
    f.require(len(rows)==4200 and all(len(r)==6 and r[1] in ('branch','cond') for r in rows),'LZC row population/schema differs')
    branch=[r for r in rows if r[1]=='branch']
    return dict(branch_rows=len(branch),condition_rows=len(rows)-len(branch),
        branch_scopes=len({r[0] for r in branch}),branch_parent_count=len({(r[0],r[2]) for r in branch}))


def calls(six,lzc):
    f.require(set(six)==set(POINTS) and sum(s['audited_points'] for s in six.values())==19370,
        'Six audit population drift')
    f.require(lzc['branch_rows']==1200 and lzc['condition_rows']==3000,'Exact735 LZC population drift')
    metadata=sum(4*s['scopes']+3*s['nonempty_parent_coordinate_count']+4*s['metadata_leaves'] for s in six.values())
    branch=sum(POINTS.values())
    lzc_metadata=lzc['branch_scopes']+3*lzc['branch_parent_count']+4*lzc['branch_rows']
    low8=metadata+4*branch+8*lzc['branch_rows']+10*lzc['condition_rows']+lzc_metadata+1
    high8=metadata+5*branch+11*lzc['branch_rows']+16*lzc['condition_rows']+lzc_metadata+1
    # Snapshot36 groups: point view 7..10 calls; each vector select/query 5..8 calls.
    low8+=36*7+96*5;high8+=36*10+96*8
    low9=6*1344+6*3584+4;high9=7*1344+7*3584+4
    n=len(STAGES)
    return dict(stages=list(STAGES),stage_count=n,
        excluded_status_query_calls=dict(old8_per_stage=23666,new9_per_stage=3584,total_per_stage=27250,total_six_stages=27250*n),
        per_stage_GUI_core_calls=dict(old8_lower=low8,old8_upper=high8,new9_lower=low9,new9_upper=high9,
            combined_lower=low8+low9,combined_upper=high8+high9),
        six_stage_GUI_core_calls=dict(lower=n*(low8+low9),upper=n*(high8+high9)),
        derivation=dict(six_metadata='4S+3P+4L per policy; S scopes,P nonempty parents,L native leaves',
            six_selection='4..5 GUI calls per audited branch: flat-old, optional unselect, select, flat-readback, excluded query',
            lzc_branch='8..11 per row plus actual metadata traversal S+3P+4L once per contiguous branch scope',
            lzc_condition='10..16 per row including view, Condition and vector clear/select/readback, excluded query',
            snapshot='36 group headers7..10 each;96 vector selections/query5..8 each',
            qbs_side='1344 cond selections5..6 +1344 all-vector reads +3584 vector selections/query6..7 +4 bank-view calls'),
        assumptions=['0/1 previous singleton selection; group multi-selection initialization cleanup is extra',
            'Nonempty native parent inventory matches compiled/discovery-backed table; unexpected empty parents add traversal calls',
            'LZC branch rows are grouped by scope; extra native validation due to view/context churn adds calls'],
        not_complete_total_GUI_count=True,
        excluded_from_core=['735 database merge/load','native mapping discovery','root refresh/process-events/rooted report and CSV metrics',
            'EL imports/recalculation/native save','source/input pin IO','unexpected empty native metadata parents','initial selection cleanup'],
        new9_mapping=dict(previous_actual_roots_per_bank=6840,
            same_layout_model_range=[20628+2*13680,247768+2*13680],
            hard_traversal_caps=dict(root_per_bank=8192,nodes_per_nested_group=128,depth=8,nested_groups=448),
            conservative_bound_with_root_caps=247768+2*16384,
            model_basis='Bounded frozen qbf_scope: root scan2R; top-level group paths/metas;448 nested trees with2..128 nodes; selection/ID-display observation API. No numeric mapping inferred.'),
        budget_seconds=14400,kill_after_seconds=10,
        budget_basis='Existing8 reviewed10800s cap + standaloneQBS1792 reviewed3600s cap; six stages include after-root. Conservative proposal, NOT measured combined performance; requires explicit parent approval.',
        measured_combined_seconds=None,automatic_retry=False,timeout_result='HOLD_PRESERVE_EVIDENCE_NOT_AUTO_EXTEND')


def evidence():
    f.require(f.sha(READER)==READER_SHA,'Exact sealed735 reader plan drift')
    source=json.loads(READER.read_bytes())
    f.require(source['population']==735 and source['output']==str(REPORT) and
        (source['targets'],source['protected'],source['audited'])==(5892,17774,23666) and
        source['admission_seal']=='4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397', 'Not exact735 authority')
    review=merge.evidence(QUALIFIED,QUALIFIED_SHA);pins=dict(review['pins'])
    consumed=[]
    def pinned(path):
        path=Path(path);f.require(str(path) in source['pins'] and f.sha(path)==source['pins'][str(path)],'Consumed735 source pin drift: '+str(path))
        pins[str(path)]=source['pins'][str(path)];consumed.append(str(path));return path.read_bytes()
    six={g:constant_selection(pinned(REPORT/(g+'-selection.tcl')).decode('ascii'),g) for g in POINTS}
    lzc=lzc_counts(pinned(REPORT/'seven-selection.tcl').decode('ascii'))
    proposal=pinned(REPORT/'combined-eight.el')
    # This whitespace handling is ONLY for the manually composed proposal, never actual native evidence.
    rows=merge.records(b'\n'.join(x for x in proposal.splitlines() if x)+b'\n')
    actual=merge.records((merge.EIGHT/'applied.el').read_bytes())
    f.require(Counter(rows)==Counter(actual),'735 proposal differs from actual5892 native attributes')
    admission=Path(source['admission']);manifest=admission/'admission-manifest.json'
    f.require(f.sha(manifest)==source['admission_seal'],'735 admission seal drift')
    state=json.loads((admission/'status.json').read_bytes());bitmap=json.loads((admission/'combined-bits.json').read_bytes())
    f.require(state['aggregate_passed']==735 and state['coverage_admitted'] is True and len(bitmap['tests'])==735 and
        len(set(bitmap['tests']))==735,'Exact735 membership/status drift')
    q=json.loads(QUALIFIED.read_bytes())
    for scope,p in q['scope_protection'].items():
        row=bitmap['metrics']['cond'][scope]
        f.require(row['width']==p['width'] and str(row['checksum'])==str(p['metric_checksum']) and
            int(row['bits'],16)&int(p['target_bitmap'],16)==0,'Fresh735 exact1792 coordinates/zero bitmap differ')
    for path in (READER,SCRIPT,TEST,manifest,admission/'status.json',admission/'combined-bits.json',
        REPORT/'csv-fixed-eight-plan.json',REPORT/'runtime-plan.json',REPORT/'six-library.tcl',
        SCRIPT.with_name('six_policy_singleton_selection_v2.tcl'),SCRIPT.with_name('lzc_selector_native_product_audit_visibility.tcl'),
        SCRIPT.with_name('lzc_selector_native_product_batch.tcl'),SCRIPT.with_name('capture_lzc_batch.tcl')):
        pins[str(path)]=f.sha(path)
    return dict(schema='QBS_SIDE1792_NINTH_735_QUALIFICATION_PLAN_V1',status='STATIC735_PLAN_PREPARED_NO_DVE',pins=pins,
        parent_qualified_manifest=str(QUALIFIED),parent_qualified_seal=QUALIFIED_SHA,
        eight735_reader_plan=str(READER),eight735_reader_seal=READER_SHA,exact_population=735,admission_seal=source['admission_seal'],
        report_state='Sealed735 report PREPARATION only; no735 actual report/percentage qualification claimed.',
        inherited735_reader_fault='Independently handled; this tool does not repair/re-run735 reader or bypass its source/context/native gates. Fresh launch must use parent-reviewed repaired sealed reader/context.',
        inherited735_pin_authority=dict(sealed_pin_count=len(source['pins']),consumed_pins_checked=consumed,
            full8752ledger_rehashed_here=False,all_other_source_pins_retained_by_external_reader_seal=True),
        source_control_boundary=f.SCOPE_BOUNDARY,source735_zero_check=dict(targets=1792,still_zero=True,width_per_bank=21503),
        mutual_review=review['disjoint_review'],six_selection_inventory=six,lzc_selection_inventory=lzc,call_budget=calls(six,lzc),
        qualification_contract=dict(expected_EL_records=7684,Branch_records=5808,Condition_records=1876,
            target_checks_per_stage=7684,retained_audited_neighbors=19566,protected_payload_conditions=41214,
            all_existing8_protection_gates_retained=True,stages=list(STAGES),audit_rows_per_stage=27250,total_rows=163500,
            native_signature_binding='Exact actual native scoped kind/ID/vectorID/checksum/expression-width-bit/vector/annotation multiset. No XML ID construction.',
            imports='Separate existing8 and QBS1792 reviewed EL imports in disposable local session; strict global7684 union after recalc, reset-empty, reloaded union, after-root protection, final/cleanup empty.',
            new735_membership='Exact sealed735 test order/prefix, design/source pins and ordinary-known-controls contract; no729 test population substitution.',
            fresh_output='Parent chooses independent fresh directory; never735 prepared root or prior failed/successful directories.',
            runtime_integration='Future pinned successor callback/profile around existing8 audit and saved-EL guards; retain each per-policy source/native binder and report/root protections, add QBS1344/3584 audit for every stage. Change5892 to exact7684 at explicit union guard only; do not use nem_install hard5892.'),
        launch_ready=False,authorization_required=True,DVE_started=False,merged_EL_written=False,final_application=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('prepare','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');args=parser.parse_args();out=args.output.absolute()
    f.require(out.parent==f.proof.OUT and out.resolve()==out,'Fresh direct output required')
    if args.command=='prepare':
        f.require(not out.exists(),'Existing output protected');record=evidence();out.mkdir();f.write(out/'qualification-plan.json',record)
        print(json.dumps(dict(output=str(out),seal=f.sha(out/'qualification-plan.json'),pins=len(record['pins']),launch_ready=False)))
    else:
        path=out/'qualification-plan.json';f.require(f.sha(path)==args.seal,'External735 plan seal drift')
        f.require(json.loads(path.read_bytes())==evidence(),'Static735 qualification plan reproduction differs')
        print('VERIFY_PASS_STATIC735_NINTH_PLAN_NO_LAUNCH')


if __name__=='__main__':main()
