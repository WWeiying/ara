#!/usr/bin/env python3
"""Host-only successor admission and strict-checker regression tests."""
import importlib.util
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tested_stage3_boundary', Path(__file__).with_name('run_boundary.py'))
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
b = r.b
OBSOLETE_IDENTITY_TEST = 'test_cli_single_json_with_real_build_pins_and_input_hashes'


def scoped_fixture():
    r.legacy_inventory()
    search = list(sys.path)
    sys.path.insert(0, str(r.BOUNDARY))
    try:
        checked = importlib.import_module('check')
        b.require(Path(checked.__file__).resolve() == r.BOUNDARY/'check.py', 'Wrong scoped fixture import')
        return b.load(r.BOUNDARY/'test_check_vcs.py', 'unchanged_scoped_host_tests')
    finally:
        sys.path[:] = search


class BoundaryAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old, cls.checker, cls.legacy_pins = r.legacy()
        cls.sw, cls.vectors, cls.contract, cls.pins = r.software()

    def test_original_firmware_without_inherited_live_rtl(self):
        self.assertEqual(self.sw['elf_sha256'], r.ELF_SHA)
        self.assertEqual(self.sw['fault_pc'], self.contract['fault_pc'])
        self.assertFalse(any(Path(p).is_relative_to(b.ROOT/'hardware/src') for p in self.pins))
        self.assertFalse(any(Path(p).is_relative_to(b.ROOT/'hardware/include') for p in self.pins))
        self.assertEqual(b.sha(r.BUILD/'build.json'), r.ANCHORS[r.BUILD/'build.json'])
        self.assertEqual(b.sha(r.BUILD/'source-pins.json'), r.ANCHORS[r.BUILD/'source-pins.json'])

    def test_historical_failure_still_fails_unchanged_strict_checker(self):
        receipt = b.read(r.FAILED/'result.json')
        log = r.FAILED/'work/run.vcs.log'
        before = b.sha(r.FAILED/'result.json')
        b.verify({str(log): receipt['artifacts'][str(log)]})
        with self.assertRaises(ValueError):
            self.checker.old.check_log(log.read_text(), self.vectors, self.contract['fault_pc'])
        self.assertEqual(b.sha(r.FAILED/'result.json'), before)
        self.assertEqual(receipt['state'], 'FAIL')

    def test_precise_checker_inventory_excludes_unrelated_tools_and_rtl(self):
        self.assertEqual(set(self.legacy_pins), {str(b.ROOT/p) for p in r.LEGACY})
        self.assertFalse(any('/hardware/src/' in p or 'urg' in p or p.endswith('.md')
                             for p in self.legacy_pins))
        for name in ('uvm_dut.py', 'artifacts.py', 'contract.py'):
            self.assertIn(str(b.ROOT/'verification/ara_verify'/name), self.legacy_pins)
        self.assertEqual(self.checker.old.check_log.__code__.co_filename, str(r.BOUNDARY/'check.py'))
        self.assertEqual(self.old.scoped_illegals.__code__.co_filename, str(r.BOUNDARY/'run.py'))

    def test_original_elf_and_receipt_drift_fail_closed(self):
        with patch.object(r, 'ELF_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'firmware'):
                r.software()
        with patch.dict(r.ANCHORS, {r.BUILD/'build.json': '0'*64}):
            with self.assertRaisesRegex(ValueError, 'Identity'):
                r.software()

    def test_new_pairing_retains_original_elf_and_protocol_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            socdir = out/'soc'
            socdir.mkdir()
            b.save(socdir/'build.json', {'state': 'fixture-only'})
            soc = dict(simv=str(socdir/'sim/simv'), configuration=b.CONFIG,
                image_contract=b.IMAGE_CONTRACT, image_pins={'new-image': 'hash'},
                cpu_overlay=b.CPU_OVERLAY)
            plan = r.selection(out, socdir, soc, self.sw, {}, '/usr/bin/python3')
            self.assertEqual(plan['original_build'], str(r.BUILD))
            self.assertEqual(plan['image_pins'], soc['image_pins'])
            self.assertEqual(plan['cpu_overlay'], b.CPU_OVERLAY)
            self.assertIn('+PRELOAD='+self.sw['elf'], plan['commands']['simulation'])
            self.assertIn('+TESTCASE=resident_pv_soc_boundary', plan['commands']['simulation'])
            self.assertEqual(plan['commands']['simulation'][0], soc['simv'])
            for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
                self.assertIn(flag, plan['commands']['protocol'])
            self.assertEqual(plan['commands']['boundary'][2], str(out/'inputs/run_boundary.py'))
            self.assertEqual(plan['pv_attempts'], 33)

    def test_identity_adapter_calls_only_original_numeric_and_work_functions(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out/'work').mkdir()
            for name in ('run.vcs.log', 'vector_trace.csv', 'commit.csv'):
                (out/'work'/name).write_text('host fixture')
            prepared = ({}, {}, {}, self.sw, self.vectors, self.contract)
            with patch.object(r, 'verify_prepared', return_value=prepared), \
                 patch.object(r, 'legacy', return_value=(self.old, self.checker, self.legacy_pins)), \
                 patch.object(self.checker, 'verified_build', side_effect=AssertionError('obsolete identity gate')), \
                 patch.object(self.checker.old, 'check_log', return_value={'numerical_checked': True}) as numeric, \
                 patch.object(self.checker, 'check_work', return_value=({'work': 'fixture'}, {'traps': 12})) as work:
                result = r.check(out)
                numeric.assert_called_once_with('host fixture', self.vectors, self.contract['fault_pc'])
                work.assert_called_once_with(out/'work/vector_trace.csv', out/'work/commit.csv',
                                             'host fixture', self.vectors, self.contract)
                self.assertFalse(result['protocol_checked'])
                self.assertEqual(result['evidence_sha256'][str(r.BUILD/'build.json')],
                                 r.ANCHORS[r.BUILD/'build.json'])

    def test_adapter_checks_actual_scoped_fixture_without_old_cli_admission(self):
        module = scoped_fixture()
        cls = module.VcsBoundaryTests
        cls.setUpClass()
        vector, commit, text = module.fixture(self.vectors, self.contract, cls.previous)
        with tempfile.TemporaryDirectory(dir=b.OUT, prefix='stage3_boundary_host_') as directory:
            out = Path(directory)
            (out/'work').mkdir()
            (out/'work/run.vcs.log').write_text(text)
            for name, fields, rows in (('vector_trace.csv', cls.previous.VFIELDS, vector),
                                       ('commit.csv', cls.previous.CFIELDS, commit)):
                with (out/'work'/name).open('x', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            # Only image admission is a fixture. All numerical/RVFI/work
            # functions below are the unchanged, hash-checked implementations.
            prepared = ({}, {}, {}, self.sw, self.vectors, self.contract)
            with patch.object(r, 'verify_prepared', return_value=prepared):
                result = r.check(out)
                self.assertTrue(result['numerical']['numerical_checked'])
                self.assertEqual(result['trap_architecture']['real_csr_trap_groups'], 12)
                (out/'work/run.vcs.log').write_text(text.replace('guard_errors=0', 'guard_errors=1', 1))
                with self.assertRaises(ValueError):
                    r.check(out)

    def test_protocol_identity_remains_bound_to_new_image(self):
        with self.assertRaises(ValueError):
            self.old.smoke.check_protocol({'status': 'FAIL'},
                                         {'image_pins': {'design.so': 'fixture'}, 'simv': 'simv'}, self.sw,
                                         Path('/unused-log'), Path('/unused-vector'))
        with tempfile.TemporaryDirectory(dir=b.OUT, prefix='stage3_boundary_host_') as directory:
            root = Path(directory)
            simv, library, log, vector = (root/n for n in ('simv', 'design.so', 'run.log', 'vector.csv'))
            for path in (simv, library, log, vector):
                path.write_text('identity fixture '+path.name)
            image = {str(p): b.sha(p) for p in (simv, library)}
            soc = dict(simv=str(simv), image_pins=image)
            proof = dict(status='PASS', issues=[], elf_sha256=r.ELF_SHA,
                simv_sha256=b.sha(simv), sim_image_sha256=image,
                log_sha256=b.sha(log), vector_trace_sha256=b.sha(vector))
            self.old.smoke.check_protocol(proof, soc, self.sw, log, vector)
            for field, value in (('sim_image_sha256', {str(simv): b.sha(simv)}),
                                 ('elf_sha256', '0'*64), ('issues', ['protocol fault'])):
                with self.assertRaises(ValueError):
                    self.old.smoke.check_protocol(dict(proof, **{field: value}), soc, self.sw, log, vector)

    def test_failed_boundary_attempt_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            b.save(out/'source-pins.json', {'fixture': 'only'})
            b.save(out/'result.json', {'state': 'FAIL', 'keep': True})
            before = b.files(out)
            with patch.object(b, 'owner') as owner:
                with self.assertRaises(ValueError):
                    b.claim_attempt(out, b.sha(out/'source-pins.json'), 'test.service', terminal='result.json')
                owner.assert_not_called()
            self.assertEqual(b.files(out), before)


def load_tests(loader, tests, pattern):
    cls = scoped_fixture().VcsBoundaryTests
    names = loader.getTestCaseNames(cls)
    b.require(len(names) == 12 and OBSOLETE_IDENTITY_TEST in names, 'Sealed scoped test inventory drift')
    tests.addTests(cls(name) for name in names if name != OBSOLETE_IDENTITY_TEST)
    return tests


if __name__ == '__main__':
    unittest.main()
