import copy
import unittest
from unittest.mock import patch
import run_gap71_canonical_qbs_positive779 as r


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = r.life.read_bound(r.PRE, r.PRE_SHA)

    def test_actual_preflight(self):
        r.validate(self.pre)

    def test_negative_fixture(self):
        for key, value in [('family', 'akv'), ('window', r.p.WINDOWS['negative']),
                           ('fault_address', 0x40002080), ('formal_population', 778),
                           ('custom_instruction_execution_verified', True), ('internal_drain_verified', True)]:
            bad = copy.deepcopy(self.pre); bad[key] = value
            with self.assertRaises(Exception): r.validate(bad)

    def test_native_not_fallback(self):
        bad = copy.deepcopy(self.pre); bad['artifacts']['dut'] = bad['artifacts']['reference']
        with self.assertRaises(Exception): r.validate(bad)

    def test_command(self):
        cmd = r.command(r.life.OUT / 'canonical-command-test')
        self.assertEqual(cmd.count('+QBS_PERF'), 1)
        self.assertIn('+COMMIT_TOHOST=80001000', cmd)
        self.assertIn('+NO_FSDB', cmd)
        self.assertNotIn('+QBS_ROOT_TRACE', cmd)
        self.assertEqual(cmd.count('+PRELOAD=' + str(r.ELF)), 1)
        self.assertEqual(r.BUDGET, 600)
        self.assertEqual(cmd[-3:], ['-ucli', '-do', str(r.PROBE)])

    def test_prepare_no_launch(self):
        with patch.object(r.inherited.worker, 'run', side_effect=AssertionError('No VCS')):
            manifest = r.prepare(r.life.OUT / 'gap71-canonical-qbs-positive779-test-only')
        self.assertFalse(manifest['coverage_admitted'])
        self.assertEqual(manifest['baseline'], 779)
        self.assertEqual(manifest['pins'][str(r.BOOK)], r.BOOK_SHA)
        self.assertEqual(manifest['pins'][str(r.ELF)], r.ELF_SHA)
        self.assertTrue(manifest['probes']['qualification_required'])

    def test_drift_rejected(self):
        with patch.object(r.life, 'check', side_effect=RuntimeError('Pin drift')):
            with self.assertRaises(RuntimeError): r.prepare(r.life.OUT / 'canonical-drift-test')

    def test_no_premature_oracle(self):
        contract = r.probe_contract()
        self.assertIn('REQUIRES_PRIVATE_RECOVERY_ADAPTER', contract['collector_status'])
        self.assertIn('Cycle probe required', contract['PMA'])
        self.assertIn('not custom native', contract['reference_policy'])

    def test_focused_exact_objects(self):
        import subprocess
        script = r.PROBE.read_text()
        # Execute the actual entry in ordinary Tcl with fail-closed UCLI stubs.
        stub = '''set objects {}; set steps 0
proc dump {args} {if {[lindex $args 0] eq "-add"} {lappend ::objects [lindex $args 1]}; return 1}
proc show {args} {}
proc run {args} {incr ::steps; if {$::steps == 2} {error "MOCK_TERMINAL"}}
proc exit {code} {puts "MOCK_EXIT $code"}
'''
        result = subprocess.run(['tclsh'], input=stub + script + '\nputs "OBJECTS $objects"\n',
            text=True, capture_output=True, check=True)
        row = next(x for x in result.stdout.splitlines() if x.startswith('OBJECTS '))
        expected = [r.probe_contract()['scope'] + '.' + n for n in r.PROBE_NAMES]
        self.assertEqual(row.split()[1:], expected)
        self.assertEqual(len(expected), len(set(expected)))
        self.assertIn('CANONICAL_QBS_PROBE_READY', result.stdout)
        self.assertNotIn('force ', script)
        self.assertIn('66060288', script)
        self.assertEqual(r.probe_contract()['maximum_wave_bytes'], 67108864)

    def test_missing_object_fails_before_run(self):
        import subprocess
        stub = '''proc dump {args} {return 0}
proc show {args} {}
proc run {args} {error "MUST_NOT_RUN"}
proc exit {code} {puts "MOCK_EXIT $code"}
'''
        result = subprocess.run(['tclsh'], input=stub+r.PROBE.read_text(), text=True,
            capture_output=True, check=True)
        self.assertNotIn('CANONICAL_QBS_PROBE_READY', result.stdout)
        self.assertIn('Missing exact object', result.stderr)
        self.assertNotIn('MUST_NOT_RUN', result.stderr)

    def test_capacity_boundary_rejects(self):
        import subprocess
        stub = '''set steps 0
proc dump {args} {return 1}
proc show {args} {}
proc run {args} {incr ::steps}
rename file real_file
proc file {args} {if {[lindex $args 0] eq "exists"} {return 1}; if {[lindex $args 0] eq "size"} {return 66060288}; error "Unexpected file operation"}
proc exit {code} {puts "MOCK_EXIT $code"}
'''
        result = subprocess.run(['tclsh'], input=stub+r.PROBE.read_text()+'\nputs "STEPS $steps"\n',
            text=True, capture_output=True, check=True, timeout=5)
        self.assertIn('capacity boundary; incomplete capture rejected', result.stderr)
        self.assertIn('STEPS 1', result.stdout)
        self.assertIn('MOCK_EXIT 1', result.stdout)


if __name__ == '__main__': unittest.main()
