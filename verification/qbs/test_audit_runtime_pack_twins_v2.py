import copy
import unittest
from audit_runtime_pack_twins_v2 import validate_binding


class BindingTest(unittest.TestCase):
    def setUp(self):
        self.pins = {"/simv": "image", "/simlib": "library"}
        self.image = dict(simv="/simv", files=dict(self.pins))
        self.result = dict(report_sha256="report", projection={"cycles": 12})
        self.entry = dict(result_sha256="report", projection={"cycles": 12})

    def test_matches(self):
        validate_binding(self.pins, self.image, self.entry, self.result)

    def test_reject_foreign_or_incomplete_image(self):
        for key, value in [("/simv", "other"), ("/simlib", "other")]:
            image = copy.deepcopy(self.image)
            image["files"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_binding(self.pins, image, self.entry, self.result)
        for image in ({}, {"files": {}}, {"simv": "/missing", "files": self.pins}):
            with self.assertRaises(ValueError):
                validate_binding(self.pins, image, self.entry, self.result)

    def test_reject_changed_saved_evidence(self):
        for entry in ({}, dict(self.entry, result_sha256="other"),
                      dict(self.entry, projection={"cycles": 13})):
            with self.assertRaises(ValueError):
                validate_binding(self.pins, self.image, entry, self.result)


if __name__ == "__main__":
    unittest.main()
