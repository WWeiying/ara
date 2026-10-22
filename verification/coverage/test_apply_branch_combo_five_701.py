import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import apply_branch_combo_five_701 as combo


class FiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = combo.load_sealed(combo.BASE / 'config.json', combo.BASE_SEAL)
        cls.exp = combo.load_sealed(combo.EXP / 'config.json', combo.EXP_SEAL)
        cls.groups = copy.deepcopy(cls.base['groups'])
        cls.groups['exponent'] = copy.deepcopy(cls.exp)
        import capture_narrow_exponent_native1272 as exp
        cls.groups['exponent']['source_scopes'] = exp.load_plan()['scopes']
        cls.owners, cls.targets, cls.protected = combo.inventory(cls.groups)
        cls.raw = (combo.BASE / 'combined.el').read_bytes() + b'\n' + (combo.EXP / 'first.el').read_bytes()

    def test_actual_five_population_cross_protection(self):
        self.assertEqual(len(self.owners), 106)
        self.assertEqual(sum(map(len, self.targets.values())), 5600)
        self.assertEqual(sum(map(len, self.protected.values())), 12626)
        self.assertFalse(set.union(*self.targets.values()) & set.union(*self.protected.values()))

    def test_scope_overlap_rejected(self):
        groups = copy.deepcopy(self.groups)
        scope = next(iter(groups['qbs']['plan']['scopes']))
        groups['exponent']['plan']['scopes'][scope] = {}
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            combo.inventory(groups)

    def test_target_protection_duplicate_rejected(self):
        groups = copy.deepcopy(self.groups)
        rows = next(iter(groups['exponent']['plan']['scopes'].values()))['branch']
        rows[1]['point']['raw_index'] = rows[0]['point']['raw_index']
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            combo.inventory(groups)

    def test_default_or_protected_promotion_rejected(self):
        groups = copy.deepcopy(self.groups)
        row = next(r for m in groups['exponent']['plan']['scopes'].values() for r in m['branch'] if not r['target'])
        row['target'] = True
        with self.assertRaisesRegex(ValueError, 'count'):
            combo.inventory(groups)

    def test_actual_latest_source_and_bitmap(self):
        import apply_qbs_rooted_701 as q
        from inventory_operand_debug import Design
        bitmap = json.loads((q.BASE701 / 'combined-bits.json').read_bytes())
        result = combo.latest_review(self.groups, bitmap, Design(Path(self.base['inputs'][0])))
        self.assertEqual(result['unique_targets'], 5600)
        self.assertEqual(result['target_hits']['debug'], 408)
        self.assertEqual(result['cross_target_protection_conflicts'], 0)

    def test_hit_structural_target_rejected(self):
        import apply_qbs_rooted_701 as q
        from inventory_operand_debug import Design
        bitmap = json.loads((q.BASE701 / 'combined-bits.json').read_bytes())
        scope, index = next(iter(self.targets['exponent']))
        record = bitmap['metrics']['branch'][scope]
        record['bits'] = hex(int(record['bits'], 16) | (1 << (record['width'] - index - 1)))[2:]
        with self.assertRaisesRegex(ValueError, 'Hit contradicts'):
            combo.latest_review(self.groups, bitmap, Design(Path(self.base['inputs'][0])))

    def test_exact701_required(self):
        with self.assertRaisesRegex(ValueError, '701'):
            combo.latest_review(self.groups, {'tests': ['duplicate'] * 701}, None)

    def test_actual_depth_ancestors_no_virtual_generate_parent(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(q.RAW701 / 'summary.csv')
        roots, names = combo.actual_roots(self.groups, reference)
        self.assertEqual(set(roots), set(names))
        for lane in range(4):
            prefix = 'ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d]' % lane
            self.assertNotIn(prefix, roots)
            self.assertIn(prefix + '.i_lane', roots)

    def test_missing_actual_root_rejected(self):
        import apply_qbs_rooted_701 as q
        reference = q.reference_rows(q.RAW701 / 'summary.csv')
        reference.pop(next(iter(self.targets['exponent']))[0])
        with self.assertRaises(ValueError):
            combo.actual_roots(self.groups, reference)

    def test_native_five_router_and_actual_isolated_bindings(self):
        parts = combo.partition(self.raw, self.owners)
        self.assertEqual(set(parts), set(combo.GROUPS))
        for group in combo.GROUPS:
            result = combo.invoke(group, self.groups[group], parts[group])
            self.assertEqual(result['records'], combo.COUNTS[group][0])
            self.assertTrue(result['dependencies'])

    def test_missing_or_unknown_group_rejected(self):
        with self.assertRaises(ValueError):
            combo.partition((combo.BASE / 'combined.el').read_bytes(), self.owners)
        with self.assertRaises(ValueError):
            combo.partition(self.raw.replace(b'INSTANCE: ara_tb.', b'INSTANCE: unknown.', 1), self.owners)

    def test_duplicate_exponent_record_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            combo.invoke('exponent', self.groups['exponent'], (combo.EXP / 'first.el').read_bytes() * 2)

    def test_after_root_actual_exponent_audit(self):
        result = combo.invoke('exponent', self.groups['exponent'], (combo.EXP / 'first.el').read_bytes(), combo.EXP)
        self.assertEqual(result['after_root_audited'], 5616)

    def test_after_root_extra_protected_exclusion_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for stage in combo.STAGES:
                (directory / ('states_' + stage + '.tsv')).write_bytes((combo.EXP / ('states_' + stage + '.tsv')).read_bytes())
            path = directory / 'states_reloaded.tsv'
            lines = path.read_text().splitlines()
            index = next(i for i, line in enumerate(lines[1:], 1) if line.endswith('\t0'))
            lines[index] = lines[index][:-1] + '1'
            path.write_text('\n'.join(lines) + '\n')
            with self.assertRaises(subprocess.CalledProcessError):
                combo.invoke('exponent', self.groups['exponent'], (combo.EXP / 'first.el').read_bytes(), directory)

    def test_frozen_dependency_seals_unchanged(self):
        self.assertEqual(combo.sha(combo.BASE / 'config.json'), combo.BASE_SEAL)
        for path in (combo.HERE / 'apply_branch_combo_701.py', combo.HERE / 'apply_branch_combo_701_v2.py',
                     combo.HERE / 'apply_branch_combo_701.tcl', combo.HERE / 'apply_branch_combo_701_v2.tcl'):
            self.assertEqual(combo.sha(path), self.base['pins'][str(path)])

    def test_actual_result_extra_sealed_config_selection_only(self):
        saved = combo.load_sealed(combo.EXP / 'capture-result.json', combo.EXP_RESULT)
        verified = copy.deepcopy(saved)
        verified.pop('config_sha256')
        verified['files'].pop(str(combo.EXP / 'config.json'))
        verified['files'].pop(str(combo.EXP / 'selection.tcl'))
        combo.qualified_result(saved, verified)
        bad = copy.deepcopy(saved)
        bad['files'][str(combo.EXP / 'first.el')] = '0' * 64
        with self.assertRaises(ValueError):
            combo.qualified_result(bad, verified)
        bad = copy.deepcopy(saved)
        bad['files']['unexpected-file'] = '0' * 64
        with self.assertRaises(ValueError):
            combo.qualified_result(bad, verified)

    def test_tcl_full_mock_after_root_order_and_cleanup(self):
        prefix = '''
set env(DVE_COVERAGE_OUTPUT) /mock/five
set dbg_scopes {scope}
rename source unused_source
proc source {args} {}
proc qbsapp_root {} {}
proc qbs_audit {args} {}
foreach {command group} {combo_qbs_audit qbs obd_audit debug op1144_audit operand ff1_audit ff1 exp1272_audit exponent} {
    proc $command {stage active} "puts \\"AUDIT $group \\$stage \\$active\\""
}
proc qbsapp_summary {stage} {puts "SUMMARY $stage"}
proc dbg_save {name args} {puts "EXPORT $name"}
proc gui_exclusion {args} {puts RESET_EXECUTED}
proc gui_exit {args} {puts EXIT_EXECUTED}
proc qbsapp_session {} {
    qbs_audit before 0
    qbsapp_summary raw
    qbs_audit selected 1
    dbg_save applied.el
    qbsapp_summary applied
    gui_exclusion -reset
    qbs_audit reset 0
    dbg_save reset-empty.el 1
    qbsapp_summary reset
}
'''
        result = subprocess.run(['tclsh'], input=prefix + combo.TCL.read_text(), text=True, capture_output=True, check=True)
        self.assertEqual(result.stderr, '')
        text = result.stdout
        self.assertIn('FIVE_COMBO_DONE_EXACT5600', text)
        for group in combo.GROUPS:
            for stage in combo.STAGES:
                active = int(stage in ('selected', 'reloaded'))
                self.assertEqual(text.splitlines().count('AUDIT %s %s %s' % (group, stage, active)), 1)
        self.assertLess(text.index('SUMMARY applied'), text.index('AUDIT qbs reloaded 1'))
        self.assertLess(text.index('AUDIT exponent reloaded 1'), text.index('EXPORT after-root.el'))
        self.assertLess(text.index('EXPORT after-root.el'), text.index('RESET_EXECUTED'))
        self.assertIn('EXPORT final-empty.el', text)

    def test_tcl_after_root_precedes_reset_and_initialization_caught(self):
        text = combo.TCL.read_text()
        self.assertIn('catch {five_initialize; qbsapp_session}', text)
        self.assertIn('qbs_audit reloaded 1\\n    dbg_save after-root.el', text)
        self.assertIn('gui_exclusion -reset', text)
        self.assertNotIn('gui_exclude_items', text)
        self.assertNotIn('gui_exclusion -update', text)
        self.assertIn('foreach group {qbs debug operand ff1 exponent}', text)

    def test_tcl_initialization_failure_still_cleanup(self):
        # Run only Tcl orchestration with mocked helpers, never a GUI or EDA tool.
        prefix = '''
set env(DVE_COVERAGE_OUTPUT) /nonexistent/five-test
proc gui_exclusion {args} {puts RESET_EXECUTED}
proc gui_exit {args} {puts EXIT_EXECUTED}
'''
        result = subprocess.run(['tclsh'], input=prefix + combo.TCL.read_text(), text=True, capture_output=True, check=True)
        self.assertIn('RESET_EXECUTED', result.stdout)
        self.assertIn('FIVE_COMBO_FAILED', result.stdout)
        self.assertIn('EXIT_EXECUTED', result.stdout)
        self.assertNotIn('FIVE_COMBO_DONE_EXACT5600', result.stdout)

    def test_actual_frozen_tcl_libraries_initialize_without_gui(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for filename in ('root-helpers.tcl', 'capture-helpers.tcl', 'combo-library.tcl'):
                (directory / filename).write_bytes((combo.BASE / filename).read_bytes())
            marker = 'set failed [catch {qbsapp_session} message]'
            (directory / 'root-row-helpers.tcl').write_text(combo.roots_api.TCL.read_text().split(marker)[0])
            text = combo.TCL.read_text().split('set failed [catch {five_initialize; qbsapp_session} message]')[0]
            prefix = 'set env(DVE_COVERAGE_OUTPUT) {%s}\n' % directory
            result = subprocess.run(['tclsh'], input=prefix + text + '\nfive_initialize\nputs INITIALIZED_NO_GUI\n',
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stderr, '')
            self.assertEqual(result.stdout.strip(), 'INITIALIZED_NO_GUI')


if __name__ == '__main__':
    unittest.main()
