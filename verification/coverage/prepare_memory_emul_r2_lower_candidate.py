"""Four exact frozen-source lower-EMUL waiver candidates; no native qualification or exclusions."""
import argparse
import json
from pathlib import Path
import re

import build_memory_emul_r2_preflight as p
from inventory_operand_debug import Design, points

life, require = p.life, p.require
PRE = life.OUT/'memory-emul-r2-preflight-721-20261006-01'
PRE_SEAL = '1f3ae5b8faf7195a6eca0f29688ed8d8b4e03c90ee09fc6f7fc806fd76514245'
SOURCE = life.OUT/'old-image-source-evidence-20261006-01/ara_dispatcher.sv'
ALLOWED = {('line',1228),('line',1311),('branch',360),('branch',414)}


def source_contract(text):
    sites=[dict(line=i,text=line.strip()) for i,line in enumerate(text.splitlines(),1)
           if re.match(r'\s*csr_vtype_d(?:\.[A-Za-z_]\w*)?\s*=(?!=)',line)]
    require([s['line'] for s in sites]==[991,1689,1691,1693,1703],'Unreviewed CSR-vtype write sites')
    fragments={84:"`FF(csr_vtype_q, csr_vtype_d, '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0})",
               991:'csr_vtype_d      = csr_vtype_q;',
               1205:'vtype        : csr_vtype_q,',
               1702:"(signed'($clog2(ELENB)) + signed'(csr_vtype_d.vlmul) < signed'(csr_vtype_d.vsew))) begin",
               1703:"csr_vtype_d = '{vill: 1'b1, vsew: EW8, vlmul: LMUL_1, default: '0};",
               1704:"csr_vl_d    = '0;",
               4213:"ara_req.emul = vlmul_e'(csr_vtype_q.vlmul + (ara_req.vtype.vsew - csr_vtype_q.vsew));",
               4477:"ara_req.emul = vlmul_e'(csr_vtype_q.vlmul + (ara_req.vtype.vsew - csr_vtype_q.vsew));",
               4235:"if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) < 0) begin",
               4499:"if (signed'(ara_req.vtype.vsew - csr_vtype_q.vsew) < 0) begin"}
    lines=text.splitlines()
    for n,fragment in fragments.items():require(fragment in lines[n-1],'Frozen source contract mismatch at '+str(n))
    return dict(csr_vtype_write_sites=sites,exact_fragments={str(n):lines[n-1] for n in fragments},
                induction='Postreset Q=(VILL,SEW8,LMUL1). Default D=Q. The only three external setters all pass vtype legality/normalization before FF update. Valid states satisfy signed_LMUL+3>=SEW_encoding; invalid states normalize to SEW8/LMUL1.',
                memory_width_rule='Load4119..4167 and store4393..4438 select EW8/16/32/64; indexed data uses csr_vtype_q.vsew; invalid-width default retains request initializer csr_vtype_q. Mask EMUL1 bypasses the generic check.',
                protected_reset_line=84, protected_hold_line=991, protected_invalid_normalization_lines=[1698,1699,1700,1702,1703,1704],
                postreset_only=True, arbitrary_forced_corrupt_or_X_states_not_proven=True)


def encoded_proof(elen=64):
    require(elen==64,'ELEN drift invalidates this proof')
    rows=[]
    for sew in range(4):
        for lm in range(-3,4):
            if lm+3<sew:continue
            for eew in range(4):
                delta=eew-sew; encoded=(lm+delta)&7
                lower=bool((lm&7)&4) and not bool(encoded&4) and delta<0
                require(not lower,'Reachable lower arm found')
                rows.append(dict(vill=False,sew_encoding=sew,lmul_signed=lm,eew_encoding=eew,
                                 delta_signed3=delta,emul_encoded3=encoded,lower_arm=lower))
    for eew in range(4):
        rows.append(dict(vill=True,sew_encoding=0,lmul_signed=0,eew_encoding=eew,
                         delta_signed3=eew,emul_encoded3=eew,lower_arm=False))
    require(len(rows)==92,'Encoded domain differs')
    return dict(ELEN=elen,width_bits=3,rows=rows,all_lower_arms_false=True,
                guards='fractional old LMUL sign1 AND new EMUL sign0 AND signed EEW-SEW<0',
                signed_difference_range=[-3,3],policy_bits_vta_vma_do_not_affect_predicate=True,
                neither_zero_coverage_nor_VILL_trap_used_as_unreachability_proof=True)


def candidate_targets(targets):
    selected=[t for t in targets if (t['metric'],t['point']['raw_index']) in ALLOWED]
    require(len(selected)==4 and {(t['metric'],t['point']['raw_index']) for t in selected}==ALLOWED,
            'Exact four candidate identities missing/duplicate')
    require(all(t['scope_status']=='HOLD_LOWER_EMUL_NOT_PROVEN_BY_VILL_CONTEXT' and not t['hit721'] for t in selected),
            'Not four lower-only zero targets')
    return selected


def build():
    pre=life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL);life.check(pre['pins'])
    pins=life.merge_pins(pre['pins'],{str(PRE/'preflight-manifest.json'):PRE_SEAL})
    buildpins_path=life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json'
    buildpins=json.loads(buildpins_path.read_text())
    for rel in ('hardware/include/ara_pkg.sv','hardware/include/rvv_pkg.sv'):
        path=life.ROOT/rel;require(life.digest(path)==buildpins[str(path)],'Frozen package drift')
        pins=life.merge_pins(pins,{str(path):buildpins[str(path)]})
    pins=life.merge_pins(pins,{str(Path(__file__).resolve()):life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_memory_emul_r2_lower_candidate.py')):
        life.digest(Path(__file__).with_name('test_memory_emul_r2_lower_candidate.py'))})
    require('localparam int unsigned ELEN  = 64;' in (life.ROOT/'hardware/include/ara_pkg.sv').read_text(),'ELEN64 config absent')
    require(life.digest(SOURCE)==buildpins[str(life.ROOT/'hardware/src/ara_dispatcher.sv')],'Frozen dispatcher mismatch')
    contract=source_contract(SOURCE.read_text());proof=encoded_proof()
    selected=candidate_targets(pre['targets'])
    bits=json.loads((p.BASE/'combined-bits.json').read_text());design=Design(p.old.review.VDB)
    for metric in ('line','branch'):
        r=bits['metrics'][metric][p.old.review.SCOPE]
        definition=design.definition(p.old.review.SCOPE,metric)
        require(definition.get('chksum')==r['checksum'],'Compiled checksum mismatch')
        actual={point['raw_index']:point for point in points(metric,definition,r['width'])}
        for t in selected:
            if t['metric']==metric:require(actual[t['point']['raw_index']]==t['point'],'Compiled exact point drift')
    for t in selected:
        if t['metric']=='branch':
            target_line='4235' if t['point']['raw_index']==414 else '4499'
            expressions=[e for e in t['point']['expressions'] if e['id']==target_line]
            require(len(expressions)==1 and t['point']['native_vector']['vector'][-int(expressions[0]['index'])]=='1',
                    'Exact lower true-branch signature differs')
    protection=[]
    for metric,scopes in bits['metrics'].items():
        r=scopes[p.old.review.SCOPE]
        allowed=sorted(i for m,i in ALLOWED if m==metric)
        protection.append(dict(metric=metric,scope=p.old.review.SCOPE,width=r['width'],checksum=r['checksum'],
                               candidate_raw_positions=allowed,all_other_positions_protected=True,
                               protected_positions=r['width']-len(allowed)))
    life.check(pins)
    return dict(status='SOURCE_CONFIG_UNREACHABLE_CANDIDATE_NATIVE_BINDING_HOLD_NOT_APPLIED',
                scope=p.old.review.SCOPE, baseline_tests=721,preflight_seal=PRE_SEAL,targets=selected,
                source_contract=contract,encoded_proof=proof,pins=pins,protected_metrics=protection,
                all_other_scopes_protected=True,toggle_all_protected=True,upper_targets_protected=[['line',1308],['branch',362]],
                reset_initialization_default_hold_invalid_vtype_and_reserved_memory_defaults_protected=True,
                native_qualification=dict(status='HOLD_NOT_EXECUTED',raw_indices_are_native_selectors=False,
                    compiled_only_does_not_establish_native_DVE_identity=True,
                    required='Resolve actual singleton Line/Branch objects by full hierarchy/source location/BBSIG or branch path/vector. Exact saved EL must match only these four compiled bits after reload; independently prove every other bit protected and empty-reset restores all. Separate parent review/launch authorization required.',
                    source_path=str(life.ROOT/'hardware/src/ara_dispatcher.sv'),frozen_snapshot=str(SOURCE),
                    names_or_native_id_alone_are_not_sufficient=True),
                proof_limit='Bounded encoded arithmetic + exact frozen source/config induction review; not a formal-model proof and not an applied waiver. ELEN/source/hash/schema change, pre-reset/X/corrupt states or unreviewed CSR injection invalidate use.',
                original_source_and_artifacts_modified=False,simulations_started=False,DVE_started=False,
                exclusions_generated=False,waiver_applied=False,coverage_admitted=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=('prepare','verify'))
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--seal');a=parser.parse_args()
    out=a.output.absolute();require(out.parent==life.OUT,'Direct out report required')
    if a.mode=='prepare':
        require(not a.seal and not out.exists(),'Fresh candidate required');report=build();life.save(out,report)
        print(json.dumps(dict(output=str(out),seal=life.digest(out),pins=len(report['pins']),candidates=4,native_status='HOLD')))
    else:
        require(a.seal,'Fixed seal required');report=life.read_bound(out,a.seal);life.check(report['pins'])
        require(report['source_contract']==source_contract(SOURCE.read_text()) and report['encoded_proof']==encoded_proof() and
                report['targets']==candidate_targets(life.read_bound(PRE/'preflight-manifest.json',PRE_SEAL)['targets']) and
                report['native_qualification']['status']=='HOLD_NOT_EXECUTED' and not report['waiver_applied'] and
                not report['exclusions_generated'],'Candidate proof/hold drift')
        print('VERIFY_PASS four source/config candidates NATIVE_HOLD NOT_APPLIED')


if __name__=='__main__':main()
