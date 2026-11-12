import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import soc_build as s


class BuildPolicyTests(unittest.TestCase):
    def test_output_boundary(self):
        self.assertEqual(s.output(s.OUT/'enablement_soc_build_test'), s.OUT/'enablement_soc_build_test')
        for p in (s.OUT/'old_soc', s.OUT/'nested/enablement_soc_x', Path('/tmp/enablement_soc_x')):
            with self.assertRaises(ValueError): s.output(p)

    def test_configuration_owner_must_be_ready(self):
        with self.assertRaisesRegex(ValueError, 'sealed READY'):
            s.prepare(s.OUT/'enablement_soc_not_created', 'a'*40, False)

    def test_cpu_overlay_and_dependencies_are_historical(self):
        b = s.tools()
        self.assertEqual(b.CPU_OVERLAY['after_sha256'],
                         'ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249')
        self.assertEqual(b.CPU_OVERLAY['dependency_revision'], 'b29fd3cf906e7f4c71da4c2f46451c4c60a4487f')

    def test_service_direct_owner_and_no_simulator_launch(self):
        out = s.OUT/'enablement_soc_fake'
        class B:
            @staticmethod
            def sha(path): return 'a'*64
        with patch.object(s, 'preflight', return_value=({'python': '/usr/bin/python3.11'}, {})), patch.object(s, 'tools', return_value=B):
            cmd = s.service(out, 'a'*64)
        self.assertIn('--property=Type=exec', cmd)
        self.assertIn('--property=KillMode=control-group', cmd)
        self.assertIn(str(out/'inputs/soc_build.py'), cmd)
        self.assertNotIn('simv', cmd)
        self.assertNotIn('dc_shell', cmd)

    def test_selections_and_passive_monitors(self):
        self.assertEqual((s.CONFIG['shared_fma'], s.CONFIG['qbs_lane_multiplier'],
                          s.CONFIG['resident_qk_enabled'], s.CONFIG['resident_pv_enabled']), (1, 1, 1, 1))
        self.assertEqual(s.CONFIG['resident_capability'], 0)
        self.assertEqual(set(s.MONITORS), {'loan.sv', 'fma.sv'})

    def test_pair_only_changes_fma(self):
        baseline, candidate = s.selected_config(0), s.selected_config(1)
        self.assertEqual([k for k in baseline if baseline[k] != candidate[k]], ['shared_fma'])
        self.assertEqual(baseline['qbs_lane_multiplier'], 1)

    def test_invalid_fma_selection_rejected(self):
        for value in (-1, 2, '0', True):
            with self.assertRaises(ValueError): s.selected_config(value)


if __name__ == '__main__': unittest.main()
