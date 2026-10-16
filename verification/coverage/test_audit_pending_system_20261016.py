"""Fail-closed adapters and mutation tests using current raw evidence read-only."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import audit_pending_system_20261016 as a


class Decisions(unittest.TestCase):
    def passing(self):
        return {name: dict(status='PASS') for name in a.FUNCTIONAL_REQUIRED}

    def test_no_gates_never_pass(self):
        self.assertEqual(a.decision({}), 'CHECKER_REQUIRED')

    def test_all_mandatory_gates_required(self):
        self.assertEqual(a.decision({'execution': {'status': 'PASS'}, 'architecture': {'status': 'CHECKER_REQUIRED'}}), 'CHECKER_REQUIRED')
        self.assertEqual(a.decision({'original_architecture': {'status': 'PASS'}}), 'CHECKER_REQUIRED')
        self.assertEqual(a.decision(self.passing()), 'PASS')

    def test_missing_each_mandatory_gate_blocks_acceptance(self):
        for name in a.FUNCTIONAL_REQUIRED:
            with self.subTest(gate=name):
                gates = self.passing()
                del gates[name]
                self.assertEqual(a.decision(gates), 'CHECKER_REQUIRED')

    def test_optional_unmeasured_physical_claim_does_not_block_functional(self):
        for status in ('NOT_MEASURED', 'PASS'):
            gates = self.passing()
            gates['fault_axi_safety'] = dict(status=status, required_for_functional=False)
            self.assertEqual(a.decision(gates), 'PASS')
            self.assertNotIn('fault_axi_safety', a.functional_required(gates))

    def test_optional_physical_failure_forces_failure(self):
        gates = self.passing()
        gates['fault_axi_safety'] = dict(status='FAIL', required_for_functional=False)
        self.assertIn('fault_axi_safety', a.functional_required(gates))
        self.assertEqual(a.decision(gates), 'FAIL')

    def test_other_physical_statuses_cannot_use_optional_exemption(self):
        for status in ('CHECKER_REQUIRED', 'UNKNOWN', None, ''):
            with self.subTest(status=status):
                gates = self.passing()
                gates['fault_axi_safety'] = dict(status=status, required_for_functional=False)
                self.assertIn('fault_axi_safety', a.functional_required(gates))
                self.assertEqual(a.decision(gates), 'CHECKER_REQUIRED')

    def test_physical_claim_without_explicit_optional_flag_is_not_ignored(self):
        for flag in (None, 0, '', True):
            gates = self.passing()
            gates['fault_axi_safety'] = dict(status='NOT_MEASURED', required_for_functional=flag)
            self.assertEqual(a.decision(gates), 'CHECKER_REQUIRED')

    def test_optional_flag_cannot_waive_mandatory_failure_or_missing_proof(self):
        for name in a.FUNCTIONAL_REQUIRED:
            for status in ('FAIL', 'CHECKER_REQUIRED', 'NOT_MEASURED', 'UNKNOWN'):
                with self.subTest(gate=name, status=status):
                    gates = self.passing()
                    gates[name] = dict(status=status, required_for_functional=False)
                    gates['fault_axi_safety'] = dict(status='NOT_MEASURED', required_for_functional=False)
                    self.assertEqual(a.decision(gates), 'FAIL' if status == 'FAIL' else 'CHECKER_REQUIRED')

    def test_unknown_gate_cannot_be_excluded_by_optional_flag(self):
        gates = self.passing()
        gates['unreviewed_native_check'] = dict(status='CHECKER_REQUIRED', required_for_functional=False)
        self.assertEqual(a.decision(gates), 'CHECKER_REQUIRED')

    def test_scalar_and_vector_numerical_mismatches_cannot_be_waived(self):
        for name in ('scalar_numerical_mismatch', 'vector_numerical_mismatch'):
            gates = self.passing()
            gates[name] = dict(status='FAIL', required_for_functional=False)
            self.assertEqual(a.decision(gates), 'FAIL')

    def test_numerical_failure_overrides_adapter_hold(self):
        self.assertEqual(a.decision({'numeric': {'status': 'FAIL'}, 'adapter': {'status': 'CHECKER_REQUIRED'}}), 'FAIL')

    def test_disjoint_scope(self):
        self.assertEqual(a.CASES, (705, 707, 714, 716, 732, 734, 735, 738, 742, 768, 770, 772, 773, 778, 779, 781, 787, 793))
        self.assertEqual(set(a.ORACLES), set(a.CASES))


class Binding(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='system-auditor-test-', dir=a.ROOT / 'verification/out')
        self.root = Path(self.temp.name)
        self.audit = a.Audit(705, self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_read_atime_is_not_drift_and_sha_is_strict(self):
        p = self.root / 'input.json'
        p.write_text('{"x":1}')
        expected = a.sha(p)
        self.assertEqual(self.audit.read(p, expected), {'x': 1})
        self.audit.bind(p, expected)
        with self.assertRaisesRegex(ValueError, 'pin mismatch'):
            self.audit.bind(p, '0' * 64)

    def test_modified_input_is_rejected(self):
        p = self.root / 'input'
        p.write_text('before')
        self.audit.bind(p)
        p.write_text('after')
        with self.assertRaisesRegex(ValueError, 'drift'):
            self.audit.bind(p)

    def test_alias_is_rejected(self):
        p = self.root / 'input'
        p.write_text('evidence')
        link = self.root / 'alias'
        link.symlink_to(p)
        with self.assertRaisesRegex(ValueError, 'Aliased'):
            self.audit.bind(link)

    def test_missing_evidence_is_hold(self):
        self.audit.gate('missing', lambda: self.audit.bind(self.root / 'missing'))
        self.assertEqual(self.audit.gates['missing']['status'], 'CHECKER_REQUIRED')

    def test_adapter_exception_is_not_numeric_failure(self):
        self.audit.gate('adapter', lambda: {}['unimplemented'])
        self.assertEqual(self.audit.gates['adapter']['status'], 'CHECKER_REQUIRED')

    def test_clean_exit_does_not_accept_architecture(self):
        self.audit.plan = json.loads((self.audit.case / 'plan.json').read_text())
        result = self.audit.execution()
        self.assertTrue(result['validated'])
        self.assertEqual(self.audit.gates, {})
        expected = [self.audit.case / 'simulation-exit.json', a.BUILD / 'sim/simv']
        self.assertTrue(all(str(p) in self.audit.pins for p in expected))

    def test_receipt_command_identity_is_strict(self):
        self.audit.plan = json.loads((self.audit.case / 'plan.json').read_text())
        receipt = json.loads((self.audit.case / 'simulation-exit.json').read_text())
        receipt['command'] = ['foreign-image']
        with patch.object(self.audit, 'read', return_value=receipt):
            with self.assertRaisesRegex(ValueError, 'command/cwd/pid/time'):
                self.audit.execution()


class OriginalOracleMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import admit_gap97_offline as m
        cls.m = m
        case = a.RUNS / 'e0705'
        cls.rows = m.commit_rows(case / 'work/commit_trace.csv')
        cls.meta = m.elf_metadata((case / 'input.elf').read_bytes())

    def test_original_CSR_predicate_accepts_current_data(self):
        result = self.m.architecture_audit(self.rows, self.meta)
        self.assertEqual(result['checks'], 75)
        self.assertEqual(self.m.handshake_audit(self.rows, result)['requests'], 85)

    def test_modified_CSR_return_rejected(self):
        rows = copy.deepcopy(self.rows)
        pc = self.meta['symbols']['gap97_probe0']
        row = next(r for r in rows if r['event'] == 'retire' and r['pc'] == pc)
        row['rd_wdata'] ^= 1
        with self.assertRaises(ValueError):
            self.m.architecture_audit(rows, self.meta)

    def test_missing_CSR_phase_rejected(self):
        rows = copy.deepcopy(self.rows)
        pc = self.meta['symbols']['gap97_probe0']
        rows = [r for r in rows if not (r['event'] == 'retire' and r['pc'] == pc)]
        with self.assertRaises(ValueError):
            self.m.architecture_audit(rows, self.meta)

    def test_changed_terminal_store_rejected(self):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r['event'] == 'retire' and r['mem_wmask'] and r['mem_addr'] == self.meta['symbols']['tohost'])
        row['mem_wdata'] = 3
        with self.assertRaises(ValueError):
            self.m.architecture_audit(rows, self.meta)

    def test_orphan_CVX_response_rejected(self):
        rows = copy.deepcopy(self.rows)
        arch = self.m.architecture_audit(rows, self.meta)
        position = next(i for i, r in enumerate(rows) if r['event'] == 'cvx_resp')
        rows.insert(position, dict(rows[position]))
        with self.assertRaises(ValueError):
            self.m.handshake_audit(rows, arch)


class RuntimeEcho(unittest.TestCase):
    def test_only_exact_source_echo_removed(self):
        from ucli_runtime_log_20261015 import iter_runtime_lines
        source = 'if {1} {\n    puts "ERROR template"\n}\n'
        raw = 'ucli% ' + source + 'ERROR actual\n'
        self.assertEqual(''.join(iter_runtime_lines(raw.splitlines(True), {'frozen': source})), 'ERROR actual\n')

    def test_changed_echo_retained(self):
        from ucli_runtime_log_20261015 import iter_runtime_lines
        raw = 'ucli% puts "ERROR actual"\n'
        self.assertEqual(''.join(iter_runtime_lines(raw.splitlines(True), {'frozen': 'puts "ERROR template"\n'})), raw)


class CurrentMaskedFault(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import csv
        from ara_verify import vector_commit as vc
        work = a.RUNS / 'e0735/work'
        _, _, activities = vc._parse_vector_trace(work / 'vector_trace.csv')
        cls.activity = activities[243]
        with (work / 'vector_trace.csv').open() as stream:
            cls.rows = [r for r in csv.DictReader(stream) if int(r['arch_seq']) == 243]
        rels = ('hardware/tb/ara_commit_monitor.sv', 'hardware/src/lane/operand_requester.sv',
                'hardware/src/ara_system.sv', 'hardware/src/vlsu/vldu.sv', 'hardware/src/vlsu/addrgen.sv')
        cls.texts = {rel: (a.ROOT / rel).read_text() for rel in rels}

    def test_current_grant_visibility_not_BE_filter(self):
        result = a.current_masked_source_contract(self.texts)
        self.assertTrue(result['accepted_grants_logged_even_when_BE_zero'])
        self.assertFalse(result['actual_AXI_transactions_observed'])

    def test_changed_visibility_contract_rejected(self):
        texts = dict(self.texts)
        texts['hardware/tb/ara_commit_monitor.sv'] = texts['hardware/tb/ara_commit_monitor.sv'].replace(
            'if (wb_valid_i[lane][source])', 'if (wb_valid_i[lane][source] && |wb_be_i[lane][source])')
        with self.assertRaises(ValueError):
            a.current_masked_source_contract(texts)

    def test_actual_current_128_bytes_exact_no_load_grants(self):
        result = a.current_masked_native_identity(self.activity, self.rows)
        self.assertEqual(result['maintenance_known_bytes'], 128)
        self.assertEqual(result['accepted_VLDU_grant_rows'], 0)
        self.assertFalse(result['old_zero_BE_rows_required'])

    def test_changed_maintenance_data_rejected(self):
        activity = copy.deepcopy(self.activity)
        from dataclasses import replace
        activity.writes[0] = replace(activity.writes[0], data=activity.writes[0].data ^ 1)
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)

    def test_wrong_owner_rejected(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]['vid'] = '1'
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(self.activity, rows)

    def test_missing_completion_rejected(self):
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(self.activity, self.rows[:-1])

    def test_unknown_maintenance_byte_rejected(self):
        from dataclasses import replace
        activity = copy.deepcopy(self.activity)
        activity.writes[0] = replace(activity.writes[0], known_be=254)
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)

    def test_any_load_grant_rejected_in_completed_zero_grant_shape(self):
        from dataclasses import replace
        activity = copy.deepcopy(self.activity)
        activity.writes[0] = replace(activity.writes[0], source=4, be=0)
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)

    def test_duplicate_maintenance_byte_coverage_rejected(self):
        from dataclasses import replace
        activity = copy.deepcopy(self.activity)
        activity.writes[0] = replace(activity.writes[0], addr=activity.writes[1].addr, lane=activity.writes[1].lane)
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)

    def test_maintenance_write_outside_owner_interval_rejected(self):
        from dataclasses import replace
        activity = copy.deepcopy(self.activity)
        activity.writes[0] = replace(activity.writes[0], cycle=0)
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)

    def test_uncompleted_load_rejected(self):
        activity = copy.deepcopy(self.activity)
        activity.completions = 1
        with self.assertRaises(ValueError):
            a.current_masked_native_identity(activity, self.rows)


if __name__ == '__main__':
    unittest.main()
