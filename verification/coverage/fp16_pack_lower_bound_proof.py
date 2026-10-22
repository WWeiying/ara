"""Frozen two-state FP16 pack lower-bound evidence, not native qualification."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json'
BUILD_SHA = '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b'
SOURCE_SHAS = {
    'ara_pkg.sv': '49a4fd9879cad35c2c77241bd5114fb8d02ab520e833335fd916122854830971',
    'fpnew_divsqrt_th_64_multi.sv': '5436effe873707cc0ecaf60de9b5476f3739df7d8549adaabee2fbc7aab1535d',
    'fpnew_opgroup_multifmt_slice.sv': '42657b27f28cd781dd76515b15985167140fdf4abe7f52972a6dab4f1958715c',
    'fpnew_pkg.sv': 'e742515e3c26e351c3b4a6bf160bcbfb29f7d6fb989bb81b0c34adf1384cf0e1',
    'vmfpu.sv': '1f8288ed2a50f8fa59a7ea3d6f3a7e3138f5219bbb1af52e864d9dfe359d8307',
    'ct_vfdsu_ctrl.v': '52e386bf4399a5e599bfc31ac8b924d337cda9e1cb4ff2a042554315efe2aa54',
    'ct_vfdsu_double.v': '14901bd729d40dfb13c6e6130390c17786f54dc388c5fb325289c811660e3748',
    'ct_vfdsu_ff1.v': '5df80c7b5f91aec33893fe8fe1a05cdd11cfe2c92518226933cd6fcbbbc58c1b',
    'ct_vfdsu_pack.v': 'fe2cc8b2717ab39b627c67c4f9c831208216c8ac7f1c6e4b77670d114b56fc1a',
    'ct_vfdsu_prepare.v': 'e7b24e037e5ad78ec0f7201de5f4593c4edfa4384c9646391878887d67d0474f',
    'ct_vfdsu_round.v': '325b90c8d43008d905a56d32cc65d20c3f189ebe45fe37b7286591917647471a',
    'ct_vfdsu_srt.v': '1d090b2332afe2a651eeef99977ccd16bfba164c009ac42166eb2bb4ec3dc837',
    'ct_vfdsu_scalar_dp.v': 'f97cf092cf63c8f11638b344530d27767e569b447ca26460408c08add1d50e2d',
    'ct_vfdsu_top.v': '9b773bd65c105afc8a057f658da2e4ca10454e2bbc9eb7aabd3a00b19dae69a3',
    'registers.svh': '532dfd1723d2936421b921235abdafcc8ca407990224992ca13575fdb620053a',
    'gated_clk_cell.v': '22a4a5f41c7733bd4935adc8a036870a110a8e2f2a70f1f3cf64476b7a49eb9e',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_bound(path, expected, pins):
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    require(expected is None or actual == expected, 'Pin differs: ' + str(path))
    require(str(path) not in pins or pins[str(path)] == actual, 'Conflicting pin')
    pins[str(path)] = actual
    return raw


def compact(text):
    return re.sub(r'\s+', '', re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S))


def effective_exponent(payload):
    exponent, fraction = (payload >> 10) & 31, payload & 1023
    return fraction.bit_length() - 10 if exponent == 0 and fraction else exponent


def arithmetic_proof():
    effective = {effective_exponent(x) for x in range(65536)}
    require(effective == set(range(-9, 32)), 'FP16 payload domain differs')
    differences = {a - b for a in effective for b in effective | {0, 15}}
    pack = {x + 15 for x in differences} | {(x >> 1) + 15 for x in differences}
    # Reset/hold closure: zero exponent with reset format has fallback bias127.
    pack |= {0, 127}
    require(min(pack) == -25 and max(differences) < 4096, 'Signed range differs')
    require(not pack.intersection(range(-51, -25)), 'Candidate interval reachable')
    return dict(effective_exponents=[-9, 31], subtraction=[-40, 40],
                divide_pack=[-25, 55], reset_fallback=[0, 127], lower_bound=-25,
                preserved_boundary=dict(numerator='0x0001', divisor='0x7c00',
                                        exponent=-25, raw_index=56),
                assumptions=['two-state values after asynchronous reset',
                             'compiled Ara FPUSupport56 destination routing',
                             'not an X/initialization exclusion proof'])


def paired_registers(text, enable, captures):
    blocks = [compact(b) for b in re.split(r'\balways\b', text)[1:]]
    blocks = [b for b in blocks if all(signal + '<=' in b for signal in captures)]
    require(len(blocks) == 1, 'No unique shared register block')
    block = blocks[0]
    require('if(!cpurst_b)begin' in block and 'elseif(' + enable + ')begin' in block,
            'Shared register enable/reset differs')
    reset, rest = block.split('elseif(' + enable + ')begin', 1)
    capture, hold = rest.split('endelsebegin', 1)
    for signal, (initial, value) in captures.items():
        for part, expected in ((reset, initial), (capture, value), (hold, signal)):
            require(re.findall(re.escape(signal) + r'<=([^;]+);', part) == [expected],
                    'Paired register data/format differs: ' + signal)


def ff1_normalization(sources):
    text = compact(sources['ct_vfdsu_ff1.v'])
    arms = re.findall(r"52'b([01?]{52}):beginfrac_bin_val\[12:0\]=13'h([0-9a-f]+);", text)
    require(len(arms) == 53, 'FF1 case domain differs')
    for fraction in range(1, 1024):
        bits = format(fraction << 42, '052b')
        matches = [int(value, 16) for pattern, value in arms
                   if all(p == '?' or p == bit for p, bit in zip(pattern, bits))]
        require(len(matches) == 1, 'Ambiguous FF1 match')
        signed = matches[0] - 8192 if matches[0] & 4096 else matches[0]
        require(signed == fraction.bit_length() - 10, 'FF1 half normalization differs')
    prepare = compact(sources['ct_vfdsu_prepare.v'])
    for op in (0, 1):
        token = ('ct_vfdsu_ff1x_frac%d_expnt(.fanc_shift_num(ex1_oper%d_id_frac[51:0]),'
                 '.frac_bin_val(ex1_oper%d_id_expnt[12:0]),.frac_num(ex1_oper%d_frac[51:0]));')
        require(token % (op, op, op, op) in prepare, 'FF1 prepare wiring differs')
        require(('assignex1_op%d_id_nor=ex1_op%d_id;' % (op, op)) in prepare,
                'Denormal normalization selection differs')
    return [-9, 0]


def check_sources(sources):
    c = {k: compact(v) for k, v in sources.items()}
    def contains(name, token):
        require(compact(token) in c[name], 'Source contract differs: ' + name + ' ' + token)
    vm = c['vmfpu.sv']
    require(set(re.findall(r'fp_dst_fmt\s*=(?:fpnew_pkg::)?(\w+);', vm)) ==
            {'FP8', 'FP16', 'FP32', 'FP64'}, 'Unexpected destination format')
    contains('vmfpu.sv', '.dst_fmt_i(fp_dst_fmt)')
    contains('ara_pkg.sv', 'function automatic logic RVVB(fpu_support_e e); return e[1]; endfunction : RVVB')
    contains('ara_pkg.sv', 'function automatic logic RVVBA(fpu_support_e e); return e[0]; endfunction : RVVBA')
    contains('vmfpu.sv', 'EW8: if (RVVB(FPUSupport) || RVVBA(FPUSupport)) begin')
    require(56 & 3 == 0, 'Disabled FP8 bits differ')
    contains('fpnew_opgroup_multifmt_slice.sv', '(OpGroup == fpnew_pkg::DIVSQRT)')
    w = sources['fpnew_divsqrt_th_64_multi.sv']
    block = compact(w.split('begin : translate_fmt_16_bits', 1)[1].split('endcase', 1)[0])
    require(block.endswith("uniquecase(dst_fmt_q)fpnew_pkg::FP16:divsqrt_fmt=4'b0010;"
                           "fpnew_pkg::FP16ALT:divsqrt_fmt=4'b0001;default:divsqrt_fmt=4'b0010;"),
            'WIDTH16 translation differs')
    for token in ("`FFL(divsqrt_fmt_q, divsqrt_fmt, op_starting, '0)",
                  "`FFL(inp_pipe_operands_q[i+1], inp_pipe_operands_q[i], reg_ena, '0)",
                  "`FFL(inp_pipe_dst_fmt_q[i+1], inp_pipe_dst_fmt_q[i], reg_ena, fpnew_pkg::fp_format_e'(0))",
                  "`FFL(srcf0_q, operands_q[0], op_starting, '0)",
                  "`FFL(srcf1_q, operands_q[1], op_starting, '0)",
                  "`FFLARNC(func_sel, 1'b1, op_starting, func_sel, 1'b0, clk_i, rst_ni)",
                  "`FFLARNC(op_sel, 1'b1, func_sel, op_sel, 1'b0, clk_i, rst_ni)",
                  '.dp_vfdsu_ex1_pipex_sel(op_sel)',
                  '.idu_vfpu_rf_pipex_gateclk_sel(func_sel)'):
        contains('fpnew_divsqrt_th_64_multi.sv', token)
    contains('ct_vfdsu_ctrl.v', 'assign ex1_pipedown = dp_vfdsu_ex1_pipex_sel;')
    formats = ('double', 'single', 'half', 'bfloat')
    captures = {
        'vfdsu_ex2_expnt_add0[12:0]': ("13'b0", 'ex1_expnt_adder_op0[12:0]'),
        'vfdsu_ex2_expnt_add1[12:0]': ("13'b0", 'ex1_expnt_adder_op1[12:0]')}
    captures.update({'vfdsu_ex2_' + f: ("1'b0", 'ex1_' + f) for f in formats})
    paired_registers(sources['ct_vfdsu_prepare.v'], 'ex1_pipedown', captures)
    captures = {'vfdsu_ex3_half_expnt_rst[12:0]': ("13'b0", 'vfdsu_ex2_expnt_rst[12:0]'),
                'vfdsu_ex3_bfloat_expnt_rst[12:0]': ("13'b0", 'vfdsu_ex2_expnt_rst[12:0]')}
    captures.update({'vfdsu_ex3_' + f: ("1'b0", 'vfdsu_ex2_' + f) for f in formats})
    paired_registers(sources['ct_vfdsu_srt.v'], 'ex2_pipedown', captures)
    captures = {'vfdsu_ex4_expnt_rst[12:0]': ("13'b0", 'ex3_expnt_adjust_result[12:0]')}
    captures.update({'vfdsu_ex4_' + f: ("1'b0", 'vfdsu_ex3_' + f) for f in formats})
    paired_registers(sources['ct_vfdsu_round.v'], 'ex3_pipedown', captures)
    # Arithmetic format owner is the private prepare/SRT chain, not scalar_dp.EX2.
    for signal in ('vfdsu_ex2_half', 'vfdsu_ex3_half_expnt_rst', 'vfdsu_ex3_half'):
        count = c['ct_vfdsu_double.v'].count('.' + signal + '(' + signal + ')')
        require(count == 2, 'Private arithmetic net connection differs: ' + signal)
    macro = c['registers.svh'].split('`defineFFLARNC(', 1)[1].split('`define', 1)[0]
    require(macro.index('if(__clear)') < macro.index('if(__load)'), 'Macro priority differs')
    for op in (0, 1):
        contains('ct_vfdsu_prepare.v', "ex1_half ? {ex1_oper%d[9:0],42'b0}" % op)
        contains('ct_vfdsu_prepare.v', "ex1_half ? {8'b0,ex1_oper%d[14:10]}" % op)
    contains('ct_vfdsu_srt.v', 'ex2_expnt_result[12:0] = vfdsu_ex2_expnt_add0[12:0] - vfdsu_ex2_expnt_add1[12:0];')
    contains('ct_vfdsu_srt.v', 'ex2_sqrt_expnt_result[12:0] = {ex2_expnt_result[12],ex2_expnt_result[12:1]};')
    contains('ct_vfdsu_round.v', 'assign vfdsu_ex3_expnt_rst[12:0] = vfdsu_ex3_half_expnt_rst[12:0];')
    contains('ct_vfdsu_round.v', "vfdsu_ex3_half ? 13'hf : 13'h7f;")
    contains('ct_vfdsu_round.v', "assign ex3_expnt_adjst[12:0] = vfdsu_ex3_double ? 13'h3ff: vfdsu_ex3_single ? 13'h7f : vfdsu_ex3_half ? 13'hf : 13'h7f;")
    contains('ct_vfdsu_round.v', 'assign ex3_expnt_adjust_result[12:0] = vfdsu_ex3_expnt_rst[12:0] + ex3_expnt_adjst[12:0];')
    contains('ct_vfdsu_pack.v', 'case(vfdsu_ex4_expnt_rst[12:0])')
    for name, signal, capture in (
        ('ct_vfdsu_prepare.v', 'vfdsu_ex2_expnt_add0', 'ex1_expnt_adder_op0[12:0]'),
        ('ct_vfdsu_prepare.v', 'vfdsu_ex2_expnt_add1', 'ex1_expnt_adder_op1[12:0]'),
        ('ct_vfdsu_srt.v', 'vfdsu_ex3_half_expnt_rst', 'vfdsu_ex2_expnt_rst[12:0]'),
        ('ct_vfdsu_round.v', 'vfdsu_ex4_expnt_rst', 'ex3_expnt_adjust_result[12:0]')):
        values = re.findall(re.escape(signal) + r'\[12:0\]<=([^;]+);', c[name])
        require(values == ["13'b0", capture, signal + '[12:0]'], 'Reset/capture/hold differs: ' + signal)
    proof = arithmetic_proof()
    proof['ff1_half_nonzero_fraction_range'] = ff1_normalization(sources)
    proof['machine_checked_alignment'] = ['EX2 exponent addends and all four formats',
                                          'EX3 half/bfloat exponents and all four formats',
                                          'EX4 biased exponent and all four formats',
                                          'private prepare/SRT arithmetic nets, not scalar EX2',
                                          'round raw half copy and complete bias mux']
    return proof


def load_proof(pins):
    manifest = json.loads(read_bound(BUILD, BUILD_SHA, pins))
    sources = {}
    for name, sha in SOURCE_SHAS.items():
        paths = [Path(p) for p, value in manifest.items() if Path(p).name == name and value == sha]
        require(len(paths) == 1, 'Ambiguous historical source: ' + name)
        sources[name] = read_bound(paths[0], sha, pins).decode()
    return check_sources(sources), sources
