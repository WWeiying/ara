import copy
from pathlib import Path
import unittest
import csr_satp_sepc_packed_adapter as p


def unknown_tid_parser(path):
    stream = iter(p.vcd(path)); tag, decl = next(stream); yield tag, decl
    name = p.original.CSR + '.commit_instr_i.trans_id'
    for time, before, after in stream:
        before = dict(before); before[decl[name]['code']] = 'xxx'
        yield time, before, after


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = p.source_proof()
        root = p.life.ROOT / 'hardware/deps/cva6/core'
        names = dict(cva6='cva6.sv', buffer='csr_buffer.sv', csr='csr_regfile.sv', ex='ex_stage.sv',
            ariane='include/ariane_pkg.sv', riscv='include/riscv_pkg.sv',
            config='include/cv64a6_imafdcv_sv39_config_pkg.sv', build='include/build_config_pkg.sv')
        cls.sources = {n: (root / path).read_text() for n, path in names.items()}
        cls.mapping = p.aliases(cls.proof)

    def mutate(self, source, old, new):
        sources = dict(self.sources)
        self.assertIn(old, sources[source]); sources[source] = sources[source].replace(old, new)
        with self.assertRaises(ValueError): p.derive(sources)

    def test_all_fields_derived(self):
        self.assertEqual(p.derive(self.sources)['layouts'], self.proof['layouts'])
        self.assertEqual(len(self.proof['layouts']['scoreboard_entry_t']['fields']), 20)
        self.assertEqual(self.proof['layouts']['exception_t']['width'], 203)
        self.assertEqual(self.proof['layouts']['branchpredict_sbe_t']['width'], 67)
        self.assertEqual(len(self.mapping), 7)

    def test_wrong_width(self):
        self.mutate('config', 'CVA6ConfigXlen = 64;', 'CVA6ConfigXlen = 128;')

    def test_signed_field(self):
        self.mutate('cva6', 'logic [CVA6Cfg.XLEN-1:0]          operand_a;', 'logic signed [CVA6Cfg.XLEN-1:0] operand_a;')

    def test_enum_width(self):
        self.mutate('ariane', 'typedef enum logic [3:0]', 'typedef enum logic [4:0]')

    def test_offset_reorder(self):
        self.mutate('cva6', 'operand_a;', 'temporary_swap;')

    def test_extra_field(self):
        self.mutate('cva6', 'logic is_zcmt;', 'logic added; logic is_zcmt;')

    def test_swapped_actual_operand_offsets(self):
        sources = dict(self.sources)
        sources['cva6'] = sources['cva6'].replace('operand_a;', 'placeholder;').replace('operand_b;', 'operand_a;').replace('placeholder;', 'operand_b;')
        with self.assertRaisesRegex(ValueError, 'offset'): p.derive(sources)

    def test_wrong_instance_type(self):
        self.mutate('ex', '.fu_data_t(fu_data_t)', '.fu_data_t(logic)')

    def test_missing_field(self):
        self.mutate('riscv', 'logic mprv;', 'logic changed_mprv;')

    def decl(self):
        return {v['parent']: dict(width=v['parent_width'], code=str(i), type='wire')
                for i, v in enumerate(self.mapping.values())}

    def test_missing_parent(self):
        decl = self.decl(); decl.pop(next(iter(decl)))
        with self.assertRaisesRegex(ValueError, 'parent'): p.declarations(decl, self.mapping)

    def test_wrong_native_width(self):
        decl = self.decl(); next(iter(decl.values()))['width'] -= 1
        with self.assertRaisesRegex(ValueError, 'parent'): p.declarations(decl, self.mapping)

    def test_wrong_native_type(self):
        decl = self.decl(); next(iter(decl.values()))['type'] = 'real'
        with self.assertRaisesRegex(ValueError, 'parent'): p.declarations(decl, self.mapping)

    def test_existing_leaf_ambiguous(self):
        decl = self.decl(); decl[next(iter(self.mapping))] = dict(width=3, code='extra', type='wire')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): p.declarations(decl, self.mapping)

    def test_code_collision(self):
        decl = self.decl(); decl['extra'] = dict(width=1, code='__csr_packed_0', type='wire')
        with self.assertRaisesRegex(ValueError, 'collision'): p.declarations(decl, self.mapping)

    def test_extraction_unknown_bits_retained(self):
        decl = self.decl(); output = p.declarations(decl, self.mapping)
        state = {d['code']: 'x' * d['width'] for d in decl.values()}
        expanded = p.expand(state, decl, output, self.mapping)
        for name, spec in self.mapping.items():
            self.assertEqual(expanded[output[name]['code']], 'x' * (spec['left'] - spec['right'] + 1))

    def test_extraction_exact_no_unused_x_rejection(self):
        decl = self.decl(); output = p.declarations(decl, self.mapping)
        for name, spec in self.mapping.items():
            bits = ['x'] * spec['parent_width']
            width = spec['left'] - spec['right'] + 1
            bits[spec['parent_width'] - 1 - spec['left']:spec['parent_width'] - spec['right']] = '1' * width
            expanded = p.expand({decl[spec['parent']]['code']: ''.join(bits)}, decl, output, self.mapping)
            self.assertEqual(expanded[output[name]['code']], '1' * width)


class ActualNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = p.life.read_bound(p.original.runner.PRE / 'preflight-manifest.json', p.original.runner.PRE_SEAL)
        reference = p.original.runner.reference(pre)
        rows = p.original.primitive.parse_rows(p.RUN / 'commit_trace.csv')
        cls.expected = p.original.csr_expected(reference, rows, p.original.runner.source_contract()[0]['ops'])
        cls.path = p.HOLD / 'csr-owner.vcd'

    def test_real_native_original_cycle_gate_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'owner differs'):
            p.wave_audit(self.path, self.expected)

    def test_real_native_all30_fields_diagnostic_not_qualification(self):
        result = p.native_diagnostic(self.path, self.expected)
        self.assertEqual(result['matched_owners_except_cycle'], 30)
        self.assertEqual(result['wave_minus_csv_cycle_deltas'], [-1] * 30)
        self.assertFalse(result['qualification_passed'])

    def test_actual_parent_declarations(self):
        tag, decl = next(p.vcd(self.path))
        self.assertEqual(tag, 'declarations')
        for name, spec in p.aliases(p.source_proof()).items():
            self.assertEqual(decl[spec['parent']]['width'], spec['parent_width'])
            self.assertEqual(decl[name]['width'], spec['left'] - spec['right'] + 1)

    def test_actual_unknown_active_tid_rejected(self):
        from types import FunctionType, SimpleNamespace
        audit = FunctionType(p.original.wave_audit.__code__, dict(p.original.wave_audit.__globals__, wave=SimpleNamespace(vcd=unknown_tid_parser)))
        with self.assertRaisesRegex(ValueError, 'Unknown active'): audit(self.path, self.expected)

    def test_actual_wrong_expected_owner_rejected(self):
        expected = copy.deepcopy(self.expected); expected[0]['operand'] ^= 1
        with self.assertRaisesRegex(ValueError, 'owner differs'): p.wave_audit(self.path, expected)


if __name__ == '__main__': unittest.main()
