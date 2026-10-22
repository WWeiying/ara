"""Full reviewed union and fail-closed native qualification negatives."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import fma_expanded_native as native


class ExpandedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = native.life.read_bound(native.REVIEW, native.REVIEW_SHA)

    def candidate(self):
        lines = []
        for i in self.review['instances']:
            lines += ['CHECKSUM: "%s %s"' % (i['design_module_checksum'], i['toggle_checksum']),
                      'INSTANCE: ' + i['scope']]
            lines += ['Toggle %s "logic %s"' % (t['name'], t['native_name']) for t in i['targets']]
        return '\n'.join(lines) + '\n'

    def test_bound_review_and_full_complement(self):
        native.life.check(self.review['pins'])
        native.validate_review(self.review)
        self.assertEqual(native.life.digest(native.life.IMAGE), native.IMAGE_SHA)

    def test_exact_612_scalar_vector_arrays_struct_fields(self):
        parsed = native.parse_el(self.candidate(), self.review)
        self.assertEqual(len(parsed), 612)
        self.assertEqual(sum(p[-1] for p in parsed), 26064)
        self.assertIn('Toggle operand_a.sign "logic operand_a.sign"', self.candidate())
        self.assertIn('inp_pipe_operands_q[0:1][2:0][31:0]', self.candidate())
        self.assertIn('mid_pipe_sum_q[0:2][75:0]', self.candidate())

    def test_el_negatives(self):
        text = self.candidate()
        negatives = {
            'prior108_only': '\n'.join(l for l in text.splitlines() if not l.startswith('Toggle ') or
                                      l.startswith('Toggle product ')),
            'missing': text.replace('Toggle operand_a.sign "logic operand_a.sign"\n', '', 1),
            'duplicate': text + 'Toggle product "logic product[105:0]"\n',
            'wrong_checksum': text.replace('2431620414', '2431620415', 1),
            'scalar_scope': text.replace('i_vmfpu', 'i_scalar_fpu', 1),
            'child': text.replace('.i_fma\n', '.i_fma.i_lzc\n', 1),
            'FP16': text.replace('gen_parallel_slices[0]', 'gen_parallel_slices[2]', 1),
            'QBS': text.replace('i_vmfpu', 'i_qbs', 1),
            'wrong_type': text.replace('"logic ', '"reg ', 1),
            'qualifier': text.replace('"logic ', '"logic signed ', 1),
            'direction': text.replace('Toggle ', 'Toggle01 ', 1),
            'metric': text.replace('Toggle ', 'Line ', 1),
            'partial': text.replace('[31:0]', '[30:0]', 1),
            'array_direction': text.replace('[0:1]', '[1:0]', 1),
            'signature': text.replace('"logic operand_a.sign"', '"logic operand_b.sign"', 1),
            'port': text + 'Toggle busy_o "logic busy_o"\n',
            'rounding': text + 'Toggle pre_round_abs "logic pre_round_abs[63:0]"\n',
            'status': text + 'Toggle status_o.NV "logic status_o.NV"\n',
            'mask': text + 'Toggle mid_pipe_mask_q "logic mid_pipe_mask_q[0:2]"\n',
            'control': text + 'Toggle gen_inside_pipeline[0].reg_ena "logic gen_inside_pipeline[0].reg_ena"\n',
        }
        for name, bad in negatives.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                native.parse_el(bad, self.review)

    def test_source_union_cannot_shrink_or_expand(self):
        for change in ('remove', 'port', 'observed', 'complement'):
            review = copy.deepcopy(self.review)
            if change == 'remove':
                review['instances'][0]['targets'].pop()
            elif change == 'port':
                review['instances'][0]['targets'][0]['portnode'] = '1'
            elif change == 'observed':
                review['instances'][0]['targets'][0]['observed_native']['path'] = 'busy_o'
            else:
                review['formats'][0]['protected'].pop()
            with self.subTest(change=change), self.assertRaises(ValueError):
                native.validate_review(review)

    def stage_fixture(self, out):
        for stage in native.STAGES:
            (out / native.EL_FILES[stage]).write_text(self.candidate() if stage in ('apply', 'reload') else '')
            for index, i in enumerate(self.review['instances']):
                (out / ('native_%s_%d.tsv' % (stage, index))).write_bytes(Path(i['native_identity_source']).read_bytes())

    def test_all_five_stages_full_complement(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.stage_fixture(out)
            results = [native.check_stage(out, s, self.review) for s in native.STAGES]
            self.assertTrue(all(r['all_nontarget_objects'] > 0 for r in results))
            self.assertEqual(len({r['all_nontarget_objects'] for r in results}), 1)
            p = out / 'native_reload_0.tsv'
            p.write_text(p.read_text().replace('\tbusy_o\tbusy_o\tbusy_o', '\tbusy_x\tbusy_x\tbusy_x', 1))
            with self.assertRaises(ValueError):
                native.check_stage(out, 'reload', self.review)

    def test_reset_nonempty_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            self.stage_fixture(out)
            (out / 'reset-empty.el').write_text(self.candidate())
            with self.assertRaises(ValueError):
                native.check_stage(out, 'reset', self.review)

    def test_tcl_nested_selection_and_reject(self):
        source = (native.HERE / 'fma_expanded_native.tcl').read_text().split('if {[catch {fma_session} message]}')[0]
        body = r'''
set calls {}
set answers [list [list [list {busy_o}]] [list [list {operand_a.sign}]]]
proc gui_list_get_selected {args} {
    set answer [lindex $::answers 0]
    set ::answers [lrange $::answers 1 end]
    return $answer
}
proc gui_list_select {args} {lappend ::calls $args}
fma_select [list operand_a.sign operand_a.sign operand_a.sign]
if {[lindex $calls 0 3] ne "busy_o"} {error "Bad unselect"}
set answers [list {} [list [list busy_o]]]
if {![catch {fma_select [list operand_a.sign operand_a.sign operand_a.sign]}]} {error "Bad readback accepted"}
puts TEST_PASS
'''
        result = subprocess.run(['tclsh'], input=source + body, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, '')
        self.assertIn('TEST_PASS', result.stdout)


if __name__ == '__main__':
    unittest.main()
