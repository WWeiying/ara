import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import apply_branch_combo_six_717 as m


class Latest717Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = m.load_sealed(m.QUALIFIED707 / 'config.json', m.QUALIFIED_CONFIG)
        cls.groups = cls.config['groups']
        cls.bitmap = json.loads((m.LATEST / 'combined-bits.json').read_bytes())

    def test_exact_counts_and_disjoint_protection(self):
        owners, targets, protected = m.inventory(self.groups)
        self.assertEqual(len(owners), 114)
        self.assertEqual(sum(map(len, targets.values())), 5808)
        self.assertEqual(sum(map(len, protected.values())), 13562)
        self.assertFalse(set.union(*targets.values()) & set.union(*protected.values()))

    def test_actual717_source_shape_review(self):
        from inventory_operand_debug import Design
        result = m.latest_review(self.groups, self.bitmap, Design(Path(self.config['inputs'][0])), 717)
        self.assertEqual(result['tests'], 717)
        self.assertEqual(result['unique_targets'], 5808)
        self.assertTrue(all(result['target_hits'][g] == 0 for g in m.GROUPS if g != 'debug'))

    def test_older_population_rejected(self):
        with self.assertRaises(ValueError):
            m.latest_review(self.groups, self.bitmap, None, 707)

    def test_duplicate_population_rejected(self):
        bitmap = copy.deepcopy(self.bitmap)
        bitmap['tests'][-1] = bitmap['tests'][0]
        with self.assertRaises(ValueError): m.latest_review(self.groups, bitmap, None, 717)

    def test_structural_hit_rejected(self):
        from inventory_operand_debug import Design
        _, targets, _ = m.inventory(self.groups)
        scope, index = next(iter(targets['qbs']))
        bitmap = copy.deepcopy(self.bitmap)
        row = bitmap['metrics']['branch'][scope]
        row['bits'] = hex(int(row['bits'], 16) | (1 << (row['width'] - index - 1)))
        with self.assertRaises(ValueError):
            m.latest_review(self.groups, bitmap, Design(Path(self.config['inputs'][0])), 717)

    def test_changed_native_coordinate_rejected(self):
        from inventory_operand_debug import Design
        groups = copy.deepcopy(self.groups)
        row = next(iter(groups['qbs']['plan']['scopes'].values()))['branch'][0]
        row['point']['native_id'] = '999999'
        with self.assertRaises(ValueError):
            m.latest_review(groups, self.bitmap, Design(Path(self.config['inputs'][0])), 717)

    def test_actual_depth_ancestors(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(m.RAW_GEOMETRY / 'summary.csv')
        roots, names = m.actual_roots(self.groups, reference)
        self.assertEqual(set(roots), set(names))
        for lane in range(4):
            prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d]' % lane
            self.assertNotIn(prefix, roots)
            self.assertIn(prefix + '.i_lane', roots)

    def test_only_geometry_not_old_percentages(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(m.RAW_GEOMETRY / 'summary.csv')
        actual = copy.deepcopy(reference)
        actual['ara_tb']['Condition'] = '99.00%'
        m.product_geometry_match(actual, reference, self.config['reviewed_external_root'])

    def test_product_missing_rejected(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(m.RAW_GEOMETRY / 'summary.csv')
        actual = copy.deepcopy(reference)
        del actual['ara_tb.dut.i_ara_soc.i_system']
        with self.assertRaises(ValueError):
            m.product_geometry_match(actual, reference, self.config['reviewed_external_root'])

    def test_extra_root_rejected(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(m.RAW_GEOMETRY / 'summary.csv')
        actual = copy.deepcopy(reference)
        actual['extra'] = actual['ara_tb']
        with self.assertRaises(ValueError):
            m.product_geometry_match(actual, reference, self.config['reviewed_external_root'])

    def test_collapsed_depth_change_rejected(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(m.RAW_GEOMETRY / 'summary.csv')
        actual = copy.deepcopy(reference)
        actual['ara_tb.dut']['Depth'] = '2'
        with self.assertRaises(ValueError):
            m.product_geometry_match(actual, reference, self.config['reviewed_external_root'])

    def test_unsupported_baseline_before_reads(self):
        with self.assertRaises(ValueError):
            m.baseline_inputs(m.BASE, m.RAW_GEOMETRY, m.RAW_GEOMETRY_SEAL, m.EVIDENCE_SEAL, {})

    def test_known_tool_links_require_exact_pin(self):
        path = '/home/wangwy/openproject/ara/install/riscv-llvm/bin/clang'
        identity = m.tool_link_identity(path)
        pins = {}
        m.pin(pins, path, identity['sha256'])
        self.assertEqual(pins[path], pins[identity['resolved']])
        with self.assertRaises(ValueError): m.pin({}, path)
        with self.assertRaises(ValueError): m.pin({}, path, '0' * 64)

    def test_unreviewed_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / 'fake-source.sv'
            path.symlink_to('/usr/bin/python3')
            with self.assertRaises(ValueError): m.pin({}, path, m.sha(path))

    def test_tcl_libraries_initialize717_without_gui(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for filename in ('root-helpers.tcl', 'capture-helpers.tcl', 'combo-library.tcl', 'root-row-helpers.tcl'):
                (directory / filename).write_bytes((m.BASE / filename).read_bytes())
            (directory / 'population-selection.tcl').write_text('set six_expected_count 717\n')
            text = m.TCL.read_text().split('set failed [catch {six_initialize; qbsapp_session} message]')[0]
            body = 'set env(DVE_COVERAGE_OUTPUT) {%s}\n' % directory + text + '\nsix_initialize\nputs INITIALIZED717_NO_GUI\n'
            result = subprocess.run(['tclsh'], input='if {[catch {\n' + body +
                                    '\n} problem]} {puts stderr $problem; exit 1}\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertIn('SIX717_SELECTION_ADAPTER_INSTALLED', result.stdout)
            self.assertIn('INITIALIZED717_NO_GUI', result.stdout)

    def test_tcl_no_new_exclusions_or_update(self):
        text = m.TCL.read_text()
        self.assertIn('six_expected_count != 717', text)
        self.assertIn('qbs_audit reloaded 1\\n    dbg_save after-root.el', text)
        self.assertIn('gui_exclusion -reset', text)
        self.assertNotIn('gui_exclude_items', text)
        self.assertNotIn('gui_exclusion -update', text)
        self.assertIn('six2_install_selection_adapter', text)


if __name__ == '__main__':
    unittest.main()
