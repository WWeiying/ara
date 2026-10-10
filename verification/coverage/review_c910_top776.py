"""Source-bound static classification; no native exclusion or simulation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import targeted_toggle_evidence_v2 as t

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'verification/out'
RANK = OUT / 'remaining-toggle776-typed-after775-el-agent-20261007-01.json'
RANK_SHA = 'c475eff179252e78f11f17c97c818df11854b452f668086f3ea9350d74ad0046'
CONFIG = OUT / 'native-full775-cached-parent-20261007-01/config.json'
CONFIG_SHA = '9ebd932ebdc0dfba10f12b4d6d5ddd988be7d2af067650eab91fb4f653b8286f'
FORMATS = {56: ['FP64', 'FP32', 'FP16'], 40: ['FP32', 'FP16'], 8: ['FP16']}
# Largest finite encodings include NaN boxing, with sign initially zero.
LFN = {'FP64': (0x7fefffffffffffff, 63), 'FP32': (0xffffffff7f7fffff, 31),
       'FP16': (0xffffffffffff7bff, 15), 'BF16_DEFAULT': (0xffffffffffff7f7f, 15)}


def constant_intersection(values, width):
    t.require(values and all(0 <= value < (1 << width) for value in values), 'Exact word domain')
    ones, zeros = (1 << width) - 1, (1 << width) - 1
    for value in values:
        ones &= value
        zeros &= ((1 << width) - 1) ^ value
    return ones | zeros, ones


def lfn_mask(formats, include_reset_default):
    t.require(formats and set(formats) <= {'FP16', 'FP32', 'FP64'}, 'Enabled formats only')
    values = []
    for fmt in formats + (['BF16_DEFAULT'] if include_reset_default else []):
        value, sign = LFN[fmt]
        values.extend([value, value | (1 << sign)])
    return constant_intersection(values, 64)


def logical_bit(member, coordinate):
    left, right = member['bounds']
    relative = coordinate - member['serialized_offset']
    t.require(0 <= relative < 2 * (abs(left - right) + 1), 'Exact typed coordinate')
    return left - relative // 2 if left >= right else left + relative // 2


def collect():
    pins = {}
    def read(path, sha, binary=False):
        t.require(t.digest(path) == sha, 'Source/artifact drift: ' + str(path))
        pins[str(path)] = sha
        return path.read_bytes() if binary else path.read_text()
    rank = json.loads(read(RANK, RANK_SHA))
    config = json.loads(read(CONFIG, CONFIG_SHA))
    source_names = ['fpnew_divsqrt_th_64_multi.sv', 'fpnew_opgroup_multifmt_slice.sv', 'fpnew_pkg.sv',
                    'ct_vfdsu_pack.v', 'ct_vfdsu_prepare.v', 'ct_vfdsu_ff1.v',
                    'ct_vfdsu_srt_radix16_with_sqrt.v', 'ct_vfdsu_double.v', 'ct_vfdsu_round.v']
    sources = {}
    for name in source_names:
        paths = [Path(p) for p in config['pins'] if Path(p).name == name]
        t.require(len(paths) == 1, 'Frozen source must be unique')
        sources[name] = read(paths[0], config['pins'][str(paths[0])])
    wrapper = sources['fpnew_divsqrt_th_64_multi.sv']
    t.require(re.search(r'\.vfpu_yy_xx_dqnan\s*\(\s*1\x27b0\s*\)', wrapper), 'Canonical NaN tie source')
    t.require("{ex1_oper0[22:0],29'b0}" in sources['ct_vfdsu_prepare.v'] and
              "{ex1_oper0[9:0],42'b0}" in sources['ct_vfdsu_prepare.v'], 'Fraction padding source')
    shape_path = Path(next(p for p in rank['pins'] if p.endswith('tgl.verilog.shape.xml')))
    read(shape_path, rank['pins'][str(shape_path)], binary=True)
    definitions = t.xml(shape_path)
    wrappers = {}
    for definition in definitions.findall('tgldef'):
        name = definition.get('name', '')
        if not name.startswith('fpnew_divsqrt_th_64_multi '):
            continue
        fmt = int(re.search(r'FpFmtConfig=(\d+)', name)[1])
        width = int(re.search(r'\bWIDTH=(\d+)', name)[1])
        t.require(fmt in FORMATS and width == {56: 64, 40: 32, 8: 16}[fmt], 'Exact format/width parameters')
        for instance in definition.findall('instance'):
            wrappers[instance.get('name')] = dict(formats=FORMATS[fmt], width=width,
                format_mask=fmt, toggle_checksum=definition.get('chksum'), compiled_definition=name)
    # Some VCS releases name instance entries instance_data rather than instance.
    if not wrappers:
        for definition in definitions.findall('tgldef'):
            name = definition.get('name', '')
            if not name.startswith('fpnew_divsqrt_th_64_multi '): continue
            fmt = int(re.search(r'FpFmtConfig=(\d+)', name)[1]); width = int(re.search(r'\bWIDTH=(\d+)', name)[1])
            for instance in definition:
                if instance.tag == 'tglshape': continue
                scope = instance.get('name', '')
                t.require(scope.startswith('ara_tb.'), 'Exact wrapper instance')
                wrappers[scope] = dict(formats=FORMATS[fmt], width=width, format_mask=fmt,
                    toggle_checksum=definition.get('chksum'), compiled_definition=name)
    top = []
    for group in rank['top10']:
        members = []
        for member in group['members']:
            parent = member['scope'].split('.i_ct_vfdsu_top.')[0]
            t.require(parent in wrappers, 'Exact parent format binding')
            params = wrappers[parent]; field = group['field']; mask = 0; ones = 0
            reason = 'DYNAMIC_OR_CONFIG_DEPENDENT_RETAIN_PENDING_EXACT_PROOF'
            active_mask = None
            if field == 'ex4_rst_lfn':
                active_mask, active_ones = lfn_mask(params['formats'], False)
                mask, ones = lfn_mask(params['formats'], True)
                reason = 'FORMAT_INTERSECTION_PLUS_CONSERVATIVE_RESET_DEFAULT_AND_BOTH_SIGNS'
            elif field in ('frac_num', 'fanc_shift_num'):
                padding = 52 - {64: 52, 32: 23, 16: 10}[params['width']]
                mask = (1 << padding) - 1
                reason = 'NARROW_FORMAT_LOW_PADDING_PRESERVED_BY_LEFT_NORMALIZATION'
            elif field == 'ex4_doub_rst_qnan':
                mask = ones = ((1 << 12) - 1) << 51
                reason = 'LOCAL_CONCAT_EXPONENT_AND_QUIET_BIT_ONLY_PAYLOAD_SIGN_RETAINED'
            elif field in ('qt_rt_const_shift_std', 'qt_rt_const_shift_std_next'):
                t.require(member['bounds'] == [57, 0], 'QT_WIDTH must equal58')
                allowed = set(range(54 if field.endswith('_std') else 50, -1, -4))
                mask = sum(1 << bit for bit in range(58) if bit not in allowed)
                reason = 'RESET_ZERO_INIT_ONEHOT54_SHIFT_RIGHT4_HOLD_INDUCTION'
            constants = [p for p in member['missing_coordinates'] if mask >> logical_bit(member, p) & 1]
            unknown = [p for p in member['missing_coordinates'] if p not in constants]
            members.append(dict(scope=member['scope'], native_label=member['native_label'],
                parent=parent, parameters=params, serialized_offset=member['serialized_offset'],
                constant_mask=hex(mask), constant_ones=hex(ones), constant_zero=hex(mask ^ ones),
                enabled_transaction_constant_mask=None if active_mask is None else hex(active_mask),
                missing_constant_after_775_EL=constants, missing_retained_or_unknown=unknown,
                old_EL_waived_logical_bits=member['waived_logical_bits'], reason=reason))
        top.append(dict(field=group['field'], module_family=group['module_family'], members=members,
            missing_after_775_EL=group['missing_unwaived_serialized_slots'],
            constant_subset_missing=sum(len(m['missing_constant_after_775_EL']) for m in members),
            retained_or_unknown_missing=sum(len(m['missing_retained_or_unknown']) for m in members)))
    target_fields = {'ex4_of_plus', 'vfdsu_ex4_potnt_of', 'vfdsu_ex4_of', 'vfdsu_ex4_result_lfn',
        'ex4_result_lfn', 'vfdsu_ex4_potnt_norm', 'vfdsu_ex4_potnt_uf', 'ex4_uf_plus',
        'ex4_out_expt', 'vfdsu_ex4_frac', 'ex4_single_denorm_frac', 'ex4_denorm_frac'}
    targets = [g for g in rank['all_bound_groups'] if g['module_family'] == 'ct_vfdsu_pack' and g['field'] in target_fields]
    # WIDTH16/32 children cannot consume FP64 transactions. Separate producer domains.
    for group in targets:
        for member in group['members']:
            member['parameters'] = wrappers[member['scope'].split('.i_ct_vfdsu_top.')[0]]
    pins[str(Path(__file__).resolve())] = t.digest(__file__)
    for path, sha in pins.items(): t.require(t.digest(path) == sha, 'Read-end pin drift')
    return dict(status='C910_TOP776_STATIC_SOURCE_CLASSIFICATION_NOT_WAIVER_NOT_PREFLIGHT',
        top10=top, exact_parent_instances=wrappers, source_pins=pins,
        qnan_tie_note='dqnan=0; changing NaN payload cannot make lower qnan_f dynamic. No whole-field exemption proposed; stages/initialX/sign/payload retained.',
        ff1_note='24 residual instances = four physical lanes times (one WIDTH32 plus two WIDTH16) times two operand FF1 children; WIDTH64 FF1 has no ranked residual.',
        matrix=dict(name='c910_floatedge_overflow_subnormal', formats=['FP16', 'FP32', 'FP64'],
            lmul=8, vl_per_format='VLMAX; every sublane populated, repeated complementary signs',
            rows=['normal +/-1 divided by2 (clear flags/control)',
                  '+/-maxFinite / minNormal, frm=RNE and RTZ (OF|NX, infinity versus signed maxFinite)',
                  'minNormal/2 (exact subnormal, no flags)',
                  'minSubnormal/2, frm=RNE and RUP (UF|NX, +0 versus +minSubnormal)',
                  'positive non-perfect-square normals and subnormals, vfsqrt RNE (native shift/normalization hypothesis only)'],
            oracle='Spike/independent exact IEEE reference for all defined destination bits, fflags per instruction, frm/vl/vstart, source and memory guards; no native target promise from signature.',
            sequence='normal -> boundary -> normal, positive/negative batches, read/clear fflags each instruction',
            expected_nan='canonical NaN only; arbitrary NaN payload not a target',
            preliminary_budget_seconds=600, software_preflight_required=True),
        source_bound_control_candidates=targets,
        candidate_serialized_missing_slots=sum(g['missing_unwaived_serialized_slots'] for g in targets),
        direction_note='Actual raw pairs retained. Serialization order is not independently bound to 0to1/1to0; exercise both transitions, never name a raw slot direction.',
        initial_X_or_transient_waived=False, EL_generated=False, EDA_launched=False,
        official_denominator=None, percentage_gain_prediction=None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = collect()
    with args.output.open('x') as stream: json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(dict(output=str(args.output), sha=t.digest(args.output),
        top=[(g['field'], g['constant_subset_missing'], g['retained_or_unknown_missing']) for g in result['top10']],
        control_candidate_slots=result['candidate_serialized_missing_slots'])))
