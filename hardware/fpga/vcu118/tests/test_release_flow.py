"""Check automatic stage handoffs without launching hardware tools."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'ethernet'


class ReleaseFlowTests(unittest.TestCase):
    def test_all_handoffs_are_ordered_and_fail_closed(self):
        text = (ROOT / 'run_release.ps1').read_text()
        stages = ["State 'synthesis'", "State 'synthesis_setup_and_reviewed_physical_gate'",
                  "State 'implementation_using_closed_reference'", "State 'routed_drc_cdc_timing_audit'",
                  "State 'review_new_cdc_rows_and_release_gates'", "State 'generate_bitstream'",
                  "State 'board_smoke_validation'", "State 'linux_boot_and_system_validation'"]
        positions = [text.index(stage) for stage in stages]
        self.assertEqual(positions, sorted(positions))
        for start, end in zip(positions, positions[1:]):
            block = text[start:end]
            self.assertTrue('throw ' in block or "Run-Tool '" in block, block)
        self.assertIn('if ($LASTEXITCODE) {throw "$mode failed;', text)

    def test_bitgen_uses_same_checkpoint_audit(self):
        text = (ROOT / 'run_release.ps1').read_text()
        self.assertIn('-AuditManifest $audits[0].FullName', text)
        self.assertIn('check_rebuild_reports.py', text)
        self.assertIn('if ($ValidateBoard)', text)
        self.assertNotIn('Stop-Process', text)

    def test_real_timing_checks_are_retained(self):
        text = (ROOT / 'rebuild_mainrtl_v3.tcl').read_text()
        self.assertIn('Synthesis setup failed; no implementation launched', text)
        self.assertIn('fpga_run::require_timing [file join $out routed_gate]', text)
        self.assertIn('read_checkpoint -incremental $reference', text)
        self.assertIn('STEPS.OPT_DESIGN.TCL.PRE $hook', text)
        self.assertIn('puts $f {set_param synth.maxThreads 1}', text)
        self.assertIn('puts $f [list source $::rebuild_opt_preflight]', text)

    def test_release_pins_reviewed_physical_successor(self):
        text = (ROOT / 'release_build.tcl').read_text()
        self.assertIn('rebuild_mainrtl_v3.tcl', text)
        self.assertIn('Missing pinned v3 implementation flow', text)
        self.assertNotIn('rebuild_mainrtl.tcl', text)
        flow = (ROOT / 'rebuild_mainrtl_v3.tcl').read_text()
        self.assertLess(flow.index('rebuild_dual_floorplan $package'),
                        flow.index('read_checkpoint -incremental $reference'))
        for name in ('dual_floorplan.tcl', 'dual_slr_locality.tcl'):
            self.assertIn(name, flow)
        self.assertIn('ethernet synth_single_pre.tcl', flow)
        hook = (ROOT / 'synth_single_pre.tcl').read_text()
        self.assertIn('scripts synth_pre.tcl', hook)
        self.assertIn('set_param general.maxThreads 1', hook)
        self.assertIn('set_param synth.maxThreads 1', hook)

    def test_prepared_resume_rechecks_actual_ip_results(self):
        text = (ROOT / 'release_build.tcl').read_text()
        prepared = text.split('if {$mode eq "prepared"}', 1)[1].split('} else {', 1)[0]
        self.assertIn('open_package_project', prepared)
        self.assertIn('fpga_run::check_ips', prepared)
        self.assertIn('close_project', prepared)
        self.assertNotIn('launch_runs', prepared)

    def test_ip_wait_is_observable_without_automatic_reset(self):
        scripts = ROOT.parent / 'scripts'
        text = (scripts / 'prepare_profile.tcl').read_text()
        self.assertNotIn('wait_on_run $run', text)
        self.assertIn('fpga_run::wait_checked $run', text)
        self.assertNotIn('reset_run ', text)
        self.assertIn('wait_progress.tcllist', (scripts / 'run_support.tcl').read_text())

    def test_synthesis_continuation_requires_accepted_evidence(self):
        text = (ROOT / 'run_release.ps1').read_text()
        self.assertIn('AcceptedSynthesis', text)
        self.assertIn('if (!$reuseSynthesis)', text)
        self.assertIn("Run-Tool 'impl_existing'", text)
        self.assertIn("'synthesis_complete_requires_physical_gate'", text)
        self.assertIn('Missing release prerequisite', text)


if __name__ == '__main__':
    unittest.main()
