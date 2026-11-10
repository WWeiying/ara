#!/usr/bin/env python3
"""Strict successor ABI/source checks, not RTL or production capability evidence."""
from __future__ import annotations

import ast
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
BASELINE = '7543bbec0e2e4acd407ae47f4c54c4bb19f5fde4'
PATHS = {
    'dispatch': 'hardware/src/ara_dispatcher.sv',
    'seq': 'hardware/src/ara_sequencer.sv',
    'lane': 'hardware/src/lane/lane_sequencer.sv',
    'first': 'hardware/src/cva6_accel_first_pass_decoder.sv',
    'ara': 'hardware/include/ara_pkg.sv',
    'akv': 'hardware/include/akv_pkg.sv',
}


def without_comments(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def between(text, start, end):
    assert text.count(start) == 1, start
    return text.split(start, 1)[1].split(end, 1)[0]


def function(text, name):
    match = re.search(r'function automatic\b[^;]*?\b' + re.escape(name) +
                      r'\(.*?endfunction\b[^\n]*', text, re.S)
    assert match, name
    return match[0]


def assignment(text, name):
    matches = re.findall(r'\b' + re.escape(name) + r'\s*=\s*([^;]+);', text)
    assert matches, name
    return matches[-1].strip()


def boolean(expression, values):
    """Evaluate only the small source-expression subset used by admission guards."""
    expression = re.sub(r"(?:7|unsigned)'\(([^()]*)\)", r'\1', expression)
    expression = expression.replace("1'b0", '0').replace("1'b1", '1')
    for key in sorted(values, key=len, reverse=True):
        expression = expression.replace(key, str(int(values[key])))
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    expression = re.sub(r'!(?!=)', ' not ', expression)
    tree = ast.parse(' '.join(expression.split()), mode='eval')
    allowed = (ast.Expression, ast.BoolOp, ast.UnaryOp, ast.Compare, ast.Constant,
               ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Lt, ast.Gt,
               ast.LtE, ast.GtE)
    assert all(isinstance(node, allowed) for node in ast.walk(tree)), expression
    return bool(eval(compile(tree, '<source-admission-expression>', 'eval'), {'__builtins__': {}}))


def package_enables(text, defines):
    """Interpret package enable declarations, including their actual ifdef branches."""
    active = [True]
    conditions = []
    values = {}
    for line in without_comments(text).splitlines():
        if line.startswith('`ifdef '):
            condition = line.split()[1] in defines
            conditions.append(condition)
            active.append(active[-1] and condition)
        elif line.startswith('`else'):
            active[-1] = active[-2] and not conditions[-1]
        elif line.startswith('`endif'):
            active.pop()
            conditions.pop()
        elif active[-1]:
            match = re.fullmatch(r'\s*localparam bit (\w+Enable) = (.*);', line)
            if match:
                values[match[1]] = boolean(match[2], values)
    assert len(active) == 1
    return values


def require(text, *fragments):
    for fragment in fragments:
        assert fragment in text, fragment


def integration_contract(sources):
    d, seq, lane = (without_comments(sources[k]) for k in ('dispatch', 'seq', 'lane'))
    qk = between(d, 'end else if (is_akvresidentqk) begin', 'end else if (is_akv2column) begin')
    for field, expected in {
        'op': 'VAKVQK', 'scalar_op': 'acc_req_i.rs1', 'use_scalar_op': "1'b0",
        'use_vs1': "1'b0", 'use_vs2': "1'b0", 'use_vd_op': "1'b0",
        'vd': 'instr.rtype.rd', 'use_vd': "1'b1", 'vm': "1'b1",
        'eew_vd_op': 'EW32', 'vstart': "'0", 'emul': 'LMUL_4',
        'vl': "vlen_t'(AkvResidentQkDestinationElements)", 'fp_rm': 'acc_req_i.frm',
        'akv_v2': "1'b1",
    }.items():
        assert assignment(qk, 'ara_req.' + field) == expected, field
    require(qk, 'vsew: EW32, vlmul: LMUL_4', "vill: 1'b0", "ignore_zero_vl_check = 1'b1;",
            "is_vload = 1'b1;", 'if (!ara_idle_i) begin', 'state_d = WAIT_IDLE;',
            'if (ara_resp_valid && !illegal_insn) begin',
            '!akv_resident_qk_implementation_supported',
            "!akv_resident_qk_command_is_valid(64'(acc_req_i.rs1),",
            "unsigned'(instr.rtype.rd), unsigned'(instr.rtype.rs2))",
            "csr_vstart_q != '0", "unsigned'(acc_req_i.frm) > 4", '!acc_req_i.acc_cons_en')
    assert not re.search(r'csr_\w+_d\s*=', qk)
    assert 'acc_req_i.rs2' not in qk
    assert not re.search(r'ara_req\.(?:vs1|vs2|eew_vs[12]|old_eew_vs[12])\s*=', qk)
    before, terminal = qk.split('if (ara_resp_valid && !illegal_insn) begin', 1)
    require(before, "acc_resp_o.req_ready = 1'b0;", "acc_resp_o.resp_valid = 1'b0;")
    assert "acc_resp_o.req_ready = 1'b1;" not in before
    assert "acc_resp_o.resp_valid = 1'b1;" not in before
    require(terminal, "acc_resp_o.req_ready = 1'b1;", "acc_resp_o.resp_valid = 1'b1;",
            'acc_resp_o.exception = ara_resp.exception;', 'acc_resp_o.fflags |= ara_resp.fflags;',
            'acc_resp_o.fflags_valid |= ara_resp.fflags_valid;')
    precommit, commit = terminal.split('if (!ara_resp.exception.valid) begin', 1)
    assert 'eew_d[' not in before + precommit
    require(commit, 'i < AkvResidentQkDestinationRegisters',
            'eew_d[instr.rtype.rd + i] = EW32;', "eew_valid_d[instr.rtype.rd + i] = 1'b1;")
    require(d, 'ara_req.use_vd && !(ara_req.op inside {VQBEXEC, VAKVPV, VAKVQK}) &&',
            '!(layout_req.op inside {VQBEXEC, VAKVPV, VAKVQK}) &&',
            'ara_req.op inside {VAKVPV, VAKVQK} && ara_resp_valid &&',
            "if (is_vload)  illegal_insn_load  = 1'b1;")
    for name in ('vfu', 'target_vfus'):
        require(function(seq, name), 'VAKVRELEASE, VAKVPV, VAKVQK:', 'VFU_LoadUnit')
    no_src = function(seq, 'no_src_vrf')
    require(no_src, 'VAKVQK')
    assert 'VAKVPV' not in no_src
    require(seq, '{VIOTA, VID, VCOMPRESS, VAKVPV, VAKVQK}',
            '{VSLIDEUP, VSLIDEDOWN, VAKVPV, VAKVQK}',
            '(!(pe_req_o.op inside {VAKVPV, VAKVQK}) || memory_load_completed_d) &&',
            'if (pe_req_o.op inside {VQBEXEC, VAKVPV, VAKVQK}) begin',
            'ara_resp_o.fflags = qbs_fflags_i;', 'ara_resp_o.fflags_valid = qbs_fflags_valid_i;')
    require(lane, "if (pe_req.op inside {VAKVPV, VAKVQK}) vfu_operation_valid_d = 1'b0;",
            'if (pe_req.op == VAKVPV && pe_req.use_vs2) begin')
    assert lane.count('VAKVQK') == 1, 'QK leaked into lane source handling'
    assert 'VAKVQK' not in function(seq, 'source_register_count')


class QkAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('qk_generator', ROOT/'scripts/gen_akv_abi.py')
        cls.generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.generator)
        cls.spec = cls.generator.load_spec()
        cls.sources = {key: (ROOT/path).read_text() for key, path in PATHS.items()}
        cls.old = {key: subprocess.check_output(['git', 'show', BASELINE+':'+path],
                                              cwd=ROOT, text=True) for key, path in PATHS.items()}

    def test_generated_outputs_current(self):
        result = subprocess.run([sys.executable, '-B', 'scripts/gen_akv_abi.py', '--check'],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outputs = self.generator.generated_outputs(self.spec)
        for path, expected in outputs.items():
            self.assertEqual(path.read_text(), expected)

    def test_qk_spec_rejects_every_field_drift_and_type_alias(self):
        self.generator.validate_spec(self.spec)
        for key, value in self.spec['resident_qk_profile'].items():
            for replacement in ((not value, 0) if isinstance(value, bool) else (value+1, float(value))):
                bad = copy.deepcopy(self.spec)
                bad['resident_qk_profile'][key] = replacement
                with self.subTest(key=key, replacement=replacement), self.assertRaises(ValueError):
                    self.generator.validate_spec(bad)
        bad = copy.deepcopy(self.spec)
        bad['resident_qk_profile']['extra'] = 1
        with self.assertRaises(ValueError):
            self.generator.validate_spec(bad)

    def test_old_spec_unchanged(self):
        import json
        old = json.loads(subprocess.check_output(['git', 'show', BASELINE+':config/akv_abi.json'], cwd=ROOT))
        self.assertEqual({k: v for k, v in self.spec.items() if k != 'resident_qk_profile'}, old)

    def test_old_generated_functions_and_constants_unchanged(self):
        for path, language in (('hardware/include/akv_pkg.sv', 'sv'), ('apps/common/akv_abi.h', 'c')):
            old = subprocess.check_output(['git', 'show', BASELINE+':'+path], cwd=ROOT, text=True)
            new = (ROOT/path).read_text()
            if language == 'sv':
                bodies = re.findall(r'function automatic\b.*?endfunction[^\n]*', old, re.S)
                constants = re.findall(r'localparam\b[^;]+;', old)
            else:
                bodies = re.findall(r'static inline\b.*?^}', old, re.S | re.M)
                constants = re.findall(r'^#define AKV_\w+ [^\n]+', old, re.M)
            self.assertGreater(len(bodies), 10)
            for fragment in bodies + constants:
                self.assertIn(fragment, new)

    def test_old_enum_numbers_preserved(self):
        def operations(source):
            body = re.search(r'typedef enum logic \[7:0\] \{(.*?)\} ara_op_e;',
                             without_comments(source), re.S)[1]
            return [s.strip() for s in body.split(',')]
        self.assertEqual(operations(self.sources['ara']), operations(self.old['ara']) + ['VAKVQK'])
        self.assertIn('VAKVQK', function(self.sources['ara'], 'is_load'))
        self.assertNotIn('VAKVQK', function(self.sources['ara'], 'is_store'))

    def test_exhaustive_host_c_contract_both_headers(self):
        cc = shutil.which('cc')
        self.assertIsNotNone(cc)
        for directory, enabled in itertools.product(('apps/common', 'software/akv/include/akv'), (False, True)):
            with self.subTest(directory=directory, experimental_enable=enabled), tempfile.TemporaryDirectory(prefix='qk-abi-host-') as tmp:
                binary = str(Path(tmp)/'contract')
                defines = ['-D'+name+'=1' for name in (
                    'ARA_AKV_ENABLE', 'ARA_AKV_V2_ENABLE', 'ARA_AKV_RESIDENT_PV_ENABLE',
                    'ARA_AKV_RESIDENT_QK_ENABLE')] if enabled else []
                command = [cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', *defines,
                           '-I', str(ROOT/directory), str(HERE/'abi_contract_test.c'), '-o', binary]
                build = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                run = subprocess.run([binary], capture_output=True, text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                self.assertEqual(run.stdout, 'QK_ABI_HOST_PASS shapes=2880 controls=4194304 encodings=256 capability=0\n')

    def test_original_pv_c_contract_unmodified(self):
        cc = shutil.which('cc')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory(prefix='qk-pv-compat-host-') as tmp:
            binary = str(Path(tmp)/'pv-contract')
            command = [cc, '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-I', str(ROOT/'apps/common'),
                       str(HERE.parent/'soc_admission/abi_contract_test.c'), '-o', binary]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
            run = subprocess.run([binary], check=True, capture_output=True, text=True, timeout=30)
            self.assertIn('ABI_PV_HOST_PASS shapes=384 controls=524288 encodings=768 capability=0', run.stdout)

    def test_flag_support_truth_table(self):
        flags = ('ARA_AKV_ENABLE', 'ARA_AKV_V2_ENABLE', 'ARA_AKV_RESIDENT_PV_ENABLE', 'ARA_AKV_RESIDENT_QK_ENABLE')
        d = self.sources['dispatch']
        support = {name: assignment(d, name) for name in (
            'akv_implementation_supported', 'akv_v2_implementation_supported',
            'akv_resident_pv_implementation_supported', 'akv_resident_qk_implementation_supported')}
        for switches in itertools.product((False, True), repeat=4):
            enables = package_enables(self.sources['akv'], {k for k, v in zip(flags, switches) if v})
            self.assertEqual(enables['AkvResidentQkEnable'], switches[2] and switches[3])
            for lanes, vlen, half, single in itertools.product((2, 4, 8), (512, 1024, 2048), (False, True), (False, True)):
                values = dict(enables, NrLanes=lanes, VLEN=vlen)
                values.update({'RVVH(FPUSupport)': half, 'RVVF(FPUSupport)': single})
                for name, expression in support.items():
                    values[name] = boolean(expression, values)
                self.assertEqual(values['akv_resident_qk_implementation_supported'],
                                 all(switches) and lanes == 4 and vlen == 1024 and half and single)
                self.assertEqual(values['akv_resident_pv_implementation_supported'],
                                 all(switches[:3]) and lanes == 4 and vlen == 1024 and half)

    def test_both_decode_stages_exact_funct_classification(self):
        for key, f3field, f7field in (('first', 'instr.i_type.funct3', 'instruction_i[31:25]'),
                                     ('dispatch', 'instr.rtype.funct3', 'instr.rtype.funct7')):
            src = self.sources[key]
            decode = {name: assignment(src, name) for name in (
                'is_akvresidentpv', 'is_akvresidentqk', 'is_akv2column')}
            for f3, f7 in itertools.product(range(8), range(128)):
                values = {f3field: f3, f7field: f7, 'AkvResidentPvFunct3': 7,
                          'AkvResidentPvFunct7': 2, 'AkvResidentQkFunct3': 7,
                          'AkvResidentQkFunct7': 3, 'AkvV2ColumnLoadFunct3': 7}
                for name, expression in decode.items():
                    values[name] = boolean(expression, values)
                self.assertEqual(tuple(values[k] for k in ('is_akvresidentpv', 'is_akvresidentqk', 'is_akv2column')),
                                 (f3 == 7 and f7 == 2, f3 == 7 and f7 == 3, f3 == 7 and f7 not in (2, 3)))

    def test_first_pass_fp_scalar_and_load_contract(self):
        src = self.sources['first']
        branch = between(src, 'if (is_akvresidentpv || is_akvresidentqk) begin', '\n        end')
        for signal in ('is_accel_o', 'is_rs1', 'is_vfp', 'is_load'):
            self.assertEqual(assignment(branch, signal), "1'b1")
        for signal in ('is_rd', 'is_rs2', 'is_fs1', 'is_fs2', 'is_fd'):
            self.assertNotIn(signal, branch)
            self.assertRegex(src, signal+r"\s*= 1'b0;")
        self.assertNotIn('AkvResidentQkEnable', src)
        self.assertNotIn('AkvResidentPvEnable', src)
        require(src, 'is_accel_o && vs_i != riscv::Off', 'is_vfp && (fs_i == riscv::Off)',
                'instruction_o.vfp = is_vfp', 'instruction_o.op = ACCEL_OP_LOAD')

    def test_first_pass_fs_vs_state_matrix(self):
        src = self.sources['first']
        vs_gate = re.search(r'if \((is_accel_o[^\n]+)\) begin', src)[1]
        fs_gate = re.search(r'illegal_instr_o = \((.*?)\) \?', src)[1]
        for fs, vs in itertools.product(range(4), repeat=2):
            values = {'is_accel_o': 1, 'is_vfp': 1, 'fs_i': fs, 'vs_i': vs, 'riscv::Off': 0}
            legal = boolean(vs_gate, values) and not boolean(fs_gate, values)
            self.assertEqual(legal, fs != 0 and vs != 0)

    def test_expression_evaluator_rejects_unknown_syntax(self):
        self.assertTrue(boolean('a &&\n !b', {'a': 1, 'b': 0}))
        with self.assertRaises(AssertionError):
            boolean('unknown_signal', {})
        with self.assertRaises(AssertionError):
            boolean('unknown_function()', {})

    def test_dispatch_legality_truth_table(self):
        branch = between(self.sources['dispatch'], 'end else if (is_akvresidentqk) begin',
                         'end else if (is_akv2column) begin')
        guard = re.search(r'if \((!akv_resident_qk_implementation_supported.*?)\)\s*illegal_insn', branch, re.S)[1]
        call = "akv_resident_qk_command_is_valid(64'(acc_req_i.rs1),\n                      unsigned'(instr.rtype.rd), unsigned'(instr.rtype.rs2))"
        self.assertIn(call, guard)
        guard = guard.replace(call, 'fields_valid')
        for supported, fields_valid, vstart, frm, committed in itertools.product((0, 1), (0, 1), (0, 1, 255), range(8), (0, 1)):
            values = {'akv_resident_qk_implementation_supported': supported, 'fields_valid': fields_valid,
                      'csr_vstart_q': vstart, 'acc_req_i.frm': frm, 'acc_req_i.acc_cons_en': committed}
            self.assertEqual(boolean(guard.replace("'0", '0'), values),
                             not (supported and fields_valid and vstart == 0 and frm <= 4 and committed))

    def test_no_vrf_sources_atomic_tags_terminal_flags(self):
        integration_contract(self.sources)

    def test_pv_source_paths_and_decode_unchanged(self):
        for key, start, end in (
            ('dispatch', 'end else if (is_akvresidentpv) begin', 'end else if ('),
            ('dispatch', 'if (ara_req.op == VAKVPV) begin', '\n      end'),
            ('lane', 'if (pe_req.op == VAKVPV && pe_req.use_vs2) begin', '\n          end'),
            ('lane', 'VFU_LoadUnit: begin', '\n        end'),
        ):
            self.assertEqual(between(self.sources[key], start, end), between(self.old[key], start, end))
        self.assertEqual(function(self.sources['seq'], 'source_register_count'),
                         function(self.old['seq'], 'source_register_count'))
        require(self.sources['seq'], '{VRGATHER, VRGATHEREI16, VCOMPRESS, VAKVPV}')
        require(self.sources['dispatch'], 'ara_req.op == VAKVPV ||')

    def test_sv_widths_query_overflow_and_unadvertised_capability(self):
        src = self.sources['akv']
        require(function(src, 'akv_resident_pv_tokens'), "{1'b0, control[AkvResidentPvTokenBits-1:0]} + 7'd1")
        require(function(src, 'akv_resident_qk_command_is_valid'),
                '(control >> AkvResidentQkControlBits) == 0 && rs2 == 0',
                "int'(akv_resident_qk_query_base(control))", "int'(akv_resident_pv_heads(control))",
                'akv_resident_pv_head_dim(control) != 0')
        for prefix in ('pv', 'qk'):
            require(function(src, 'akv_resident_'+prefix+'_capability_word'), "return '0;")
        require(src, "AkvResidentQkSupported = 1'b0;", 'AkvResidentQkDestinationElements = 128;',
                'AkvResidentQkDestinationRegisters = 4;')

    def test_mutations_fail_closed(self):
        mutations = (
            ('dispatch', "ara_req.op = VAKVQK;", 'ara_req.op = VAKVPV;'),
            ('dispatch', "ara_req.use_vs2 = 1'b0;\n              ara_req.use_vd_op", "ara_req.use_vs2 = 1'b1;\n              ara_req.use_vd_op"),
            ('dispatch', 'vsew: EW32, vlmul: LMUL_4', 'vsew: EW16, vlmul: LMUL_4'),
            ('dispatch', '!(layout_req.op inside {VQBEXEC, VAKVPV, VAKVQK})', '!(layout_req.op inside {VQBEXEC, VAKVPV})'),
            ('dispatch', 'i < AkvResidentQkDestinationRegisters', 'i < 1'),
            ('seq', 'VAKVRELEASE, VAKVQK\n', 'VAKVRELEASE\n'),
            ('seq', '(!(pe_req_o.op inside {VAKVPV, VAKVQK}) || memory_load_completed_d)', '1'),
            ('seq', '{VQBEXEC, VAKVPV, VAKVQK}', '{VQBEXEC, VAKVPV}'),
            ('lane', 'if (pe_req.op == VAKVPV && pe_req.use_vs2)', 'if (pe_req.op inside {VAKVPV, VAKVQK} && pe_req.use_vs2)'),
            ('lane', "if (pe_req.op inside {VAKVPV, VAKVQK}) vfu_operation_valid_d = 1'b0;", ''),
        )
        for key, old, new in mutations:
            with self.subTest(file=key, mutation=old):
                self.assertIn(old, self.sources[key])
                bad = dict(self.sources)
                bad[key] = bad[key].replace(old, new)
                with self.assertRaises(AssertionError):
                    integration_contract(bad)


if __name__ == '__main__':
    unittest.main(verbosity=2)
