import copy
import unittest

from audit_runtime_pack_twins import APP, require_terminal


class RecoveryGateTest(unittest.TestCase):
    def setUp(self):
        self.parent = dict(state="FAIL", mode="vector", child_pid=None,
                           error="RuntimeError('Projection worker failed: vector, returncode=0')")
        self.child = dict(state="passed", child_pid=None, selected_cases=[APP],
                          cases={APP: dict(state="passed")})

    def test_exact_known_error(self):
        require_terminal(self.parent, self.child, "vector")

    def test_reject_other_parent_failures(self):
        for key, value in [("error", "timeout"), ("mode", "scalar"),
                           ("child_pid", 42), ("state", "running")]:
            parent = dict(self.parent, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_terminal(parent, self.child, "vector")

    def test_reject_incomplete_or_failed_child(self):
        for key, value in [("state", "failed"), ("child_pid", 42),
                           ("selected_cases", []), ("cases", {})]:
            child = dict(self.child, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                require_terminal(self.parent, child, "vector")

    def test_reject_failed_case(self):
        child = copy.deepcopy(self.child)
        child["cases"][APP]["state"] = "failed"
        with self.assertRaises(ValueError):
            require_terminal(self.parent, child, "vector")


if __name__ == "__main__":
    unittest.main()
