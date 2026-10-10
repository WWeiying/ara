import json
from pathlib import Path
import shutil
import tempfile
import unittest

from verify_lzc_singleton_artifacts import verify


class SingletonArtifactsTest(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[2]
        original = root / "verification/out/lzc-native-singleton-20261006-03"
        self.candidates = root / "verification/out/gap80-old-image-20261006-01/lzc-padding-candidates-native-bound.json"
        if not original.exists() or not self.candidates.exists():
            self.skipTest("native pilot evidence unavailable")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.capture = Path(self.temp.name) / "capture"
        shutil.copytree(original, self.capture)

    def test_actual_native_roundtrip(self):
        result = verify(self.capture, self.candidates)
        self.assertEqual(len(result["native_records"]), 1)
        self.assertFalse(result["application_approval"])
        self.assertFalse(result["aggregate_exclusions_applied"])

    def test_extra_native_record_rejected(self):
        path = self.capture / "second.el"
        path.write_text(path.read_text() + path.read_text())
        with self.assertRaises(ValueError):
            verify(self.capture, self.candidates)

    def test_clear_residue_rejected(self):
        shutil.copyfile(self.capture / "first.el", self.capture / "final-empty.el")
        with self.assertRaises(ValueError):
            verify(self.capture, self.candidates)

    def test_missing_gui_state_rejected(self):
        path = self.capture / "DVEfiles/dve_gui.log"
        path.write_text(path.read_text().replace("LZC_SINGLE_STATE reset", "REMOVED reset"))
        with self.assertRaises(ValueError):
            verify(self.capture, self.candidates)

    def test_changed_pin_rejected(self):
        path = self.capture / "pins.json"
        pins = json.loads(path.read_text())
        pins[next(iter(pins))] = "0" * 64
        path.write_text(json.dumps(pins))
        with self.assertRaises(ValueError):
            verify(self.capture, self.candidates)


if __name__ == "__main__":
    unittest.main()
