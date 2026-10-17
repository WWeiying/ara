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
        text = (ROOT / 'rebuild_mainrtl.tcl').read_text()
        self.assertIn('Synthesis setup failed; no implementation launched', text)
        self.assertIn('fpga_run::require_timing [file join $out routed_gate]', text)
        self.assertIn('read_checkpoint -incremental $reference', text)
        self.assertIn('STEPS.OPT_DESIGN.TCL.PRE $::rebuild_opt_preflight', text)


if __name__ == '__main__':
    unittest.main()
