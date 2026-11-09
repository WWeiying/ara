#!/usr/bin/env python3
"""Focused host ABI tests and static admission review; not RTL execution evidence."""
import copy
import importlib.util
import itertools
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASELINE = '13eb7d75b'


def load_generator():
    spec = importlib.util.spec_from_file_location('akv_abi_generator', ROOT/'scripts/gen_akv_abi.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def functions(text, language):
    if language == 'sv':
        return {m[1]: m[0] for m in re.finditer(
            r'function automatic\s+[^;]+?\b(akv_\w+)\([^;]*?\);.*?endfunction\s*:\s*\1', text, re.S)}
    result = {}
    pattern = r'static inline [^{;]+?\b(akv_\w+)\([^;]*?\)\s*\{'
    for match in re.finditer(pattern, text, re.S):
        depth, end = 1, match.end()
        while depth:
            if text[end] == '{': depth += 1
            if text[end] == '}': depth -= 1
            end += 1
        result[match[1]] = text[match.start():end]
    return result


class AbiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()
        cls.spec = cls.generator.load_spec()
        cls.first = (ROOT/'hardware/src/cva6_accel_first_pass_decoder.sv').read_text()
        cls.dispatcher = (ROOT/'hardware/src/ara_dispatcher.sv').read_text()
        cls.package = (ROOT/'hardware/include/akv_pkg.sv').read_text()
        cls.branch = cls.dispatcher.split('end else if (is_akvresidentpv) begin', 1)[1].split(
            'end else if (is_akv2column) begin', 1)[0]

    def test_generated_check(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/gen_akv_abi.py'), '--check'],
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual((ROOT/'apps/common/akv_abi.h').read_bytes(),
                         (ROOT/'software/akv/include/akv/akv_abi.h').read_bytes())

    def test_fixed_stage_a_profile_rejects_drift(self):
        self.generator.validate_spec(self.spec)
        for key, value in self.spec['resident_pv_profile'].items():
            bad = copy.deepcopy(self.spec)
            if isinstance(value, bool): replacement = not value
            elif isinstance(value, dict): replacement = dict(value, **{'96': 3})
            else: replacement = value+1
            bad['resident_pv_profile'][key] = replacement
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.generator.validate_spec(bad)

    def test_c_contract_both_generated_headers(self):
        cc = shutil.which('cc')
        self.assertIsNotNone(cc, 'Host C compiler required; no EDA tool is used')
        for directory in ('apps/common', 'software/akv/include/akv'):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as tmp:
                binary = Path(tmp)/'abi_contract'
                build = subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2',
                    '-I', str(ROOT/directory), str(HERE/'abi_contract_test.c'), '-o', str(binary)],
                    text=True, capture_output=True, timeout=30)
                self.assertEqual(build.returncode, 0, build.stdout+build.stderr)
                result = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual(result.stdout, 'ABI_PV_HOST_PASS shapes=384 controls=524288 encodings=768 capability=0\n')

    def test_existing_abi_functions_unchanged_from_pinned_baseline(self):
        for filename, language in (('apps/common/akv_abi.h', 'c'), ('hardware/include/akv_pkg.sv', 'sv')):
            old = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE+':'+filename], text=True)
            before, after = functions(old, language), functions((ROOT/filename).read_text(), language)
            self.assertGreater(len(before), 2)
            for name, body in before.items():
                with self.subTest(name=name):
                    self.assertEqual(body, after[name])

    def test_macro_default_off_and_capability_always_zero(self):
        macro = self.package.split('`ifdef ARA_AKV_RESIDENT_PV_ENABLE', 1)[1].split('`endif', 1)[0]
        self.assertIn("AkvResidentPvEnable = 1'b1", macro.split('`else')[0])
        self.assertIn("AkvResidentPvEnable = 1'b0", macro.split('`else')[1])
        self.assertIn("AkvResidentPvSupported = 1'b0", self.package)
        self.assertIn("return '0;", functions(self.package, 'sv')['akv_resident_pv_capability_word'])
        self.assertIn('akv_resident_pv_capability_word(', self.dispatcher)

    def test_exact_control_fields_and_sv_widen_before_add(self):
        constants = dict((c, value) for c, _, value in self.generator.resident_pv_constants(self.spec))
        self.assertEqual({k: constants[k] for k in ('FUNCT3', 'FUNCT7', 'CONTROL_BITS', 'TOKEN_BITS', 'HEADS_BIT', 'DIM_SHIFT', 'DIM_BITS')},
                         dict(FUNCT3=7, FUNCT7=2, CONTROL_BITS=9, TOKEN_BITS=6, HEADS_BIT=6, DIM_SHIFT=7, DIM_BITS=2))
        self.assertIn("{1'b0, control[AkvResidentPvTokenBits-1:0]} + 7'd1", self.package)
        self.assertEqual(self.spec['resident_pv_profile']['head_dim_codes'], {'64': 0, '128': 1, '96': 2})

    def test_only_funct7_two_is_removed_from_column(self):
        for source, field in ((self.first, 'instr.i_type.funct3'), (self.dispatcher, 'instr.rtype.funct3')):
            pv = re.search(r'is_akvresidentpv = '+re.escape(field)+r'(.*?);', source, re.S)[1]
            column = re.search(r'is_akv2column = '+re.escape(field)+r'(.*?);', source, re.S)[1]
            self.assertIn('AkvResidentPvFunct3', pv)
            self.assertIn('AkvResidentPvFunct7', pv)
            self.assertIn('!is_akvresidentpv', column)
            for f7 in range(128):
                is_pv = f7 == self.spec['resident_pv_profile']['funct7']
                is_column = not is_pv
                self.assertEqual((is_pv, is_column), (f7 == 2, f7 != 2))
        self.assertIn('!(akv_column_is_single || akv_column_is_panel4)', self.dispatcher)

    def test_first_pass_scalar_memory_and_fp_classification(self):
        block = self.first.split('if (is_akvresidentpv) begin', 1)[1].split('end', 1)[0]
        for name in ('is_accel_o', 'is_rs1', 'is_load', 'is_vfp'):
            self.assertRegex(block, name+r"\s*= 1'b1;")
        self.assertNotIn('is_rs2', block)
        self.assertNotIn('is_rd', block)
        self.assertIn("is_rs2   = 1'b0;", self.first)
        self.assertIn("is_rd    = 1'b0;", self.first)
        self.assertNotIn('AkvResidentPvEnable', self.first)
        self.assertIn('is_accel_o && vs_i != riscv::Off', self.first)
        self.assertIn('is_vfp && (fs_i == riscv::Off)', self.first)
        self.assertIn('instruction_o.vfp = is_vfp', self.first)

    def test_implementation_rounding_restart_and_admission_guards(self):
        support = re.search(r'akv_resident_pv_implementation_supported =\s*(.*?);', self.dispatcher, re.S)[1]
        for requirement in ('akv_v2_implementation_supported', 'AkvResidentPvEnable', 'RVVH(FPUSupport)'):
            self.assertIn(requirement, support)
        self.assertIn('AkvEnable && NrLanes == 4 && VLEN == 1024', self.dispatcher)
        for guard in ('!akv_resident_pv_implementation_supported', '!akv_resident_pv_command_is_valid(',
                      "csr_vstart_q != '0", "unsigned'(acc_req_i.frm) > 4", '!acc_req_i.acc_cons_en'):
            self.assertIn(guard, self.branch)
        self.assertIn('ara_req.fp_rm = acc_req_i.frm;', self.branch)

    def test_internal_geometry_ignores_dynamic_vl_and_vtype(self):
        for fragment in ('ara_req.op = VAKVPV;', 'ara_req.scalar_op = acc_req_i.rs1;',
            'ara_req.vs2 = instr.rtype.rs2;', "ara_req.use_vs2 = 1'b1;", 'lmul_vs2 = LMUL_8;',
            'ara_req.eew_vs2 = EW16;', 'ara_req.old_eew_vs2 = EW16;',
            'ara_req.vd = instr.rtype.rd;', "ara_req.use_vd = 1'b1;", "ara_req.vm = 1'b1;",
            'vsew: EW16, vlmul: LMUL_4', 'ara_req.vl = vlen_t\'(AkvResidentPvDestinationElements);',
            'ara_req.emul = LMUL_4;', "ignore_zero_vl_check = 1'b1;"):
            self.assertIn(fragment, self.branch)
        self.assertNotIn('csr_vl_q', self.branch)
        self.assertNotIn('csr_vtype_q', self.branch)
        self.assertNotRegex(self.branch, r'csr_(?:vl|vtype)_d\s*=')
        self.assertNotIn('acc_req_i.rs2', self.branch)
        self.assertNotIn('ara_req.use_vd_op', self.branch)

    def test_blocking_request_wait_and_terminal_flags(self):
        terminal = self.branch.index('if (ara_resp_valid && !illegal_insn) begin')
        before, after = self.branch[:terminal], self.branch[terminal:]
        self.assertIn("acc_resp_o.req_ready = 1'b0;", before)
        self.assertIn("acc_resp_o.resp_valid = 1'b0;", before)
        self.assertNotIn("acc_resp_o.req_ready = 1'b1;", before)
        self.assertIn('if (!ara_idle_i) begin', before)
        self.assertIn('state_d = WAIT_IDLE;', before)
        self.assertIn("acc_resp_o.req_ready = 1'b1;", after)
        self.assertIn("acc_resp_o.resp_valid = 1'b1;", after)
        self.assertIn('acc_resp_o.fflags |= ara_resp.fflags;', after)
        self.assertIn('acc_resp_o.fflags_valid |= ara_resp.fflags_valid;', after)
        self.assertIn('trans_id      : acc_req_i.trans_id', self.dispatcher)
        self.assertIn("if (is_vload)  illegal_insn_load  = 1'b1;", self.dispatcher)

    def test_no_destination_maintenance_or_issue_retag(self):
        self.assertIn('ara_req.use_vd && !(ara_req.op inside {VQBEXEC, VAKVPV}) &&', self.dispatcher)
        self.assertIn('!(layout_req.op inside {VQBEXEC, VAKVPV}) &&', self.dispatcher)
        terminal = self.branch.split('if (ara_resp_valid && !illegal_insn) begin', 1)[1]
        self.assertIn('if (!ara_resp.exception.valid) begin', terminal)
        self.assertIn('i < AkvResidentPvDestinationRegisters', terminal)
        self.assertIn('eew_d[instr.rtype.rd + i] = EW16;', terminal)
        self.assertNotIn('eew_d[', self.branch.split('if (!ara_resp.exception.valid) begin', 1)[0])

    def test_source_interval_and_existing_per_register_old_eew(self):
        source_interval = self.dispatcher.split('if (ara_req.op == VAKVPV) begin', 1)[1].split('\n      end', 1)[0]
        self.assertIn("vs2_reshuffle_vstart = '0;", source_interval)
        self.assertIn("vs2_reshuffle_vl = vlen_t'(AkvResidentPvSourceElements);", source_interval)
        full_group = re.search(r'reshuffle_full_vs2_group = ara_req.op inside \{([^}]+)\}', self.dispatcher)[1]
        self.assertNotIn('VAKVPV', full_group)
        request = re.search(r'reshuffle_req_d = \{\s*ara_req.use_vs1(.*?)\};', self.dispatcher, re.S)[1]
        self.assertIn('ara_req.op == VAKVPV', request)
        self.assertIn('vs2_reshuffle_vstart, vs2_reshuffle_vl', request)
        advance = self.dispatcher.split('rs_lmul_cnt_d = rs_lmul_cnt_q + 1;', 1)[1].split('default:;', 1)[0]
        self.assertIn('eew_old_buffer_d = eew_q[vs_buffer_d];', advance)
        self.assertIn('eew_new_buffer_d = reshuffle_eew_vs2_q;', advance)

    def test_mixed_eew_layout_model_read_six_reserve_eight(self):
        # Independent byte-interval model, not a simulator of RTL maintenance.
        active = [r for r in range(8) if r*128 < 384*2]
        self.assertEqual(active, list(range(6)))
        self.assertNotEqual(len(active), 256*2//128)
        for old in itertools.product((8, 16, 32, 64), repeat=8):
            after = list(old)
            for register in active:
                if old[register] != 16:
                    after[register] = 16
            self.assertEqual(after[:6], [16]*6)
            self.assertEqual(after[6:], list(old[6:]))


if __name__ == '__main__':
    unittest.main()
