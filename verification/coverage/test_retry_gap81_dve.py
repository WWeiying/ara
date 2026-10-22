"""No tools launched; controlled-entry environment regression."""
import unittest
from unittest.mock import patch
import retry_gap81_dve as r


class EnvironmentTests(unittest.TestCase):
    def test_wrapper_derives_dve_without_external_override(self):
        identity = dict(roles=dict(launcher="/sealed/vcs/bin/dve"))
        controlled = dict(DVE="/sealed/vcs/gui/dve",VCS_HOME="/sealed/vcs",VCS_TARGET_ARCH="linux64",PATH="/unsafe")
        with patch.object(r.old.tools,"controlled_environment",return_value=controlled):
            env = r.launcher_environment(identity,{"DVE":"/foreign"})
        self.assertNotIn("DVE",env)
        self.assertEqual(env["VCS_HOME"],"/sealed/vcs")
        self.assertEqual(env["VCS_TARGET_ARCH"],"linux64")
        self.assertEqual(env["PATH"],"/sealed/vcs/bin:/usr/bin:/bin")
        self.assertEqual(env["DVE_WAIVERS"],"off")
        self.assertEqual(env["DVE_COVERAGE_TIMEOUT"],"1200")

    def test_existing_identity_failure_is_not_suppressed(self):
        with patch.object(r.old.tools,"controlled_environment",side_effect=ValueError("identity drift")), \
             self.assertRaisesRegex(ValueError,"identity drift"):
            r.launcher_environment({}, {})


if __name__ == "__main__":
    unittest.main()
