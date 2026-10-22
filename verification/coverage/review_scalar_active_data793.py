"""Focused793 residual report, deducting the unadmitted no-hold singleton separately."""
import argparse
from pathlib import Path

import collect_scalar_fpu_fma_arbiter792 as c

life,require=c.life,c.require
BASE=life.OUT/'scalar-slot-rotation-offline-admitted793-parent-20261008-01'
BASE_SHA='757513188f805841491c898584b22722df80facd8f8c9fb424564a82502f17c3'
RANK=life.OUT/'toggle792-minus-qualified791-agent-20261008-03.json'
RANK_SHA='9064aee58d9e941eb900e2ffab8a1844924ee406f3978faefa4307a53dfc7935'
QUAL=life.OUT/'scalar-fpu-fma-arbiter792-qualified-parent-20261008-01'
QSHA='0b30ba04bd032c2311b67d9babfcadd43752e911623c0a31db23a96dc3f176a6'


def report():
    base=life.read_bound(BASE/'admission-manifest.json',BASE_SHA)
    path=BASE/'combined-toggle-bits.json';rows=life.read_bound(path,base['output_pins'][str(path)])
    q=life.read_bound(QUAL/'qualification.json',QSHA)
    require(q['FMA_audit']['FMA_hold_observed'] is False,'No hold qualification')
    sp=QUAL/'single-toggle-bits.json';sample=life.read_bound(sp,q['output_pins'][str(sp)])
    compared=c.toggle.union(rows,sample)
    rank=life.read_bound(RANK,RANK_SHA)
    pins={str(BASE/'admission-manifest.json'):BASE_SHA,str(path):base['output_pins'][str(path)],
        str(QUAL/'qualification.json'):QSHA,str(sp):q['output_pins'][str(sp)],str(RANK):RANK_SHA}
    bookpath=c.oracle.old.BUILD/'build-source-pins.json'
    book=life.read_bound(bookpath,c.oracle.old.SOURCE_SHA);pins[str(bookpath)]=c.oracle.old.SOURCE_SHA
    for rel in ('hardware/deps/cva6/core/scoreboard.sv','hardware/deps/cva6/core/cva6.sv',
        'hardware/deps/cva6/core/fpu_wrap.sv','hardware/deps/fpnew/src/fpnew_noncomp.sv',
        'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_srt.v',
        'hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_round.v'):
        p=life.ROOT/rel;require(life.digest(p)==book[str(p)],'Frozen source');pins[str(p)]=book[str(p)]
    groups=dict(hold_only=[],non_scalar_preview=[],boolean_compare_not_payload=[],
        FP64_denorm_round_shift=[],ordinary_operand_result=[])
    for scope in rank['ranking']:
        name=scope['scope']
        if '.i_ariane.' not in name:continue
        for obj in scope['objects']:
            field=obj['name'];category=None
            if name.endswith('fpu_i') and field in ('fpu_gen.operand_a_q','fpu_gen.operand_b_q','fpu_gen.operand_c_q'):
                category='hold_only'
            elif name.endswith('i_scoreboard') and field in ('preview_data_q','acc_preview_data_i'):
                category='non_scalar_preview'
            elif name.endswith('i_noncomp') and field.startswith('cmp_result.'):
                category='boolean_compare_not_payload'
            elif '.fpu_gen.fpu_i.' in name and field in ('ex2_result_double_denorm_round_add_num',
                'ex2_result_denorm_round_add_num','vfdsu_ex3_result_denorm_round_add_num',
                'frac_add1_op1_with_denorm','frac_sub1_op1_with_denorm'):
                category='FP64_denorm_round_shift'
            elif (name.endswith(('i_scoreboard','i_issue_read_operands','i_alu','i_mult','fpu_i')) and
                ('operand' in field or field in ('result_o','result','rs1_res','rs2_res','wbdata_i'))):
                category='ordinary_operand_result'
            if category is None:continue
            row=compared[name];require(row['checksum']==scope['checksum'],'Exact typed checksum')
            raw=int(row['bits'],16)
            missing=[pos for pos in obj['coordinates'] if not (raw>>(row['width']-1-pos))&1]
            if missing:groups[category].append(dict(scope=name,checksum=row['checksum'],field=field,
                width=obj['width'],missing_serialized_positions=missing,capacity=len(missing)))
    pins[str(Path(__file__).resolve())]=life.digest(Path(__file__))
    life.check(pins)
    return dict(status='SOURCE_BOUND_SCALAR793_RESIDUAL_DIAGNOSTIC_NO_EDA',baseline=793,
        baseline_seal=BASE_SHA,unadmitted_functional_FPU_deducted_only_for_dedup=True,
        prior_791_EL_exact_unexcluded_binary_only=True,groups=groups,
        capacities={k:sum(o['capacity'] for o in v) for k,v in groups.items()},input_pins=pins,
        conclusions=dict(ordinary_data='No justified thousand-direction ordinary scalar operand bus target: saturated or tiny.',
            hold='Holding-register139 raw directions require measured hold; no retry proposed.',
            preview='ACCEL vset preview result, not arbitrary scalar ALU/FPU data; software VL bound applies.',
            comparison='FPNEW cmp_result is Boolean0/1, mantissa high bits are not entropy targets.',
            denorm='Potential distinct exponent-shift sweep, not holding arbitration. 53-entry onehot table '
                'in ct_vfdsu_srt lines424 onward; dynamic copies retained, no blanket waiver.'),
        proposed_case=dict(name='FP64 subnormal DIV exponent/rounding shift matrix',
            operands='A=min-normal or min-normal+min-subnormal; B=2^k, k=1..52, then signed counterparts',
            exact_gold='Exact arm magnitude=1<<(52-k) in binary64 payload, flags0. Inexact arm '
                'uses integer quotient/remainder ties-even or directed rounding; UF|NX=3 when tiny+inexact.',
            qualifier='Full Spike scalar/FP/memory, per-result bits+fflags, FCSR restore, guards. No internal force.',
            budget='About104 DIV cells plus selected signed/directed checks; preflight must establish retirement count before budget approval.',
            expected_gain='Listed capacity is an upper bound, not measured gain. Exponent-to-onehot owner '
                'and source table must be checked before implementation.',
            dedup='Distinct from ITLB and Bacon slot/permission fields; no inter-agent direct channel available.'),
        limitations=['Not official percentage','No MDA or partial-EL flatten inference',
            'No promise >1000 gain; do not launch if exact exponent-predicate intersection is too small'],EDA_started=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=report();life.save(a.output,value);print(value['capacities']);print(life.digest(a.output))
