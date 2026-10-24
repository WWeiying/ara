import unittest
from pathlib import Path
import json
from build_soc import accepted_command, mapped_command, ROOT


class BuildCommandTests(unittest.TestCase):
    def test_exact_accepted_options_and_five_mapped_extras(self):
        snapshot = ROOT / "verification/akv/shared_reader_integration/snapshot-02"
        report = json.loads((snapshot / "manifest.json").read_text())
        text = Path(report["baseline_manifest"]).with_name("comp.vcs.log").read_text()
        original = accepted_command(text)
        mapped, extras = mapped_command(original, report)
        self.assertEqual(len(extras), 5)
        self.assertEqual(sum(a != b for a, b in zip(original, mapped)), 6)
        self.assertEqual(len(original), len(mapped))
        self.assertEqual(mapped[mapped.index("-top")+1], "ara_tb")
        self.assertIn("-timescale=1ns/100fs", mapped)
        self.assertTrue(all(Path(p).is_relative_to(snapshot) for p in extras))

    def test_missing_required_flags_rejected(self):
        for text in ("vcs -full64", "Command: vcs -full64 -top wrong\n"):
            with self.assertRaises(ValueError):
                accepted_command(text)


if __name__ == "__main__":
    unittest.main()
