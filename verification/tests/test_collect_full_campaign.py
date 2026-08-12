import json
import tempfile
import unittest
from pathlib import Path

from collect_full_campaign import _random_rows


class FullCampaignCollectionTests(unittest.TestCase):
    def test_newer_random_summary_overrides_older_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "old/profile"
            new = root / "new/profile"
            old.mkdir(parents=True)
            new.mkdir(parents=True)
            (old / "summary.json").write_text(json.dumps([
                {"name": "profile_0", "seed": 1, "status": "RTL_STALL"},
                {"name": "profile_1", "seed": 2, "status": "RTL_STALL"},
            ]), encoding="utf-8")
            (new / "summary.json").write_text(json.dumps([
                {"name": "profile_0", "seed": 1, "status": "PASS"},
                {"name": "profile_1", "seed": 2, "status": "PASS"},
            ]), encoding="utf-8")

            rows, metadata = _random_rows([root / "old", root / "new"], [("profile", 2)])

            self.assertEqual([row["status"] for row in rows], ["PASS", "PASS"])
            self.assertEqual(metadata["missing_by_profile"], {})
            self.assertEqual(metadata["selected_summaries"]["profile"], str(new / "summary.json"))

    def test_missing_seed_is_explicit_not_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            profile.mkdir(parents=True)
            (profile / "summary.json").write_text(json.dumps([
                {"name": "profile_0", "seed": 1, "status": "PASS"},
            ]), encoding="utf-8")

            rows, metadata = _random_rows([root], [("profile", 2)])

            self.assertEqual([row["status"] for row in rows], ["PASS", "NOT_RUN"])
            self.assertEqual(metadata["missing_by_profile"], {"profile": 1})

    def test_partial_profile_uses_case_results_and_recovers_generator_seed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "profile/tests/profile_10"
            case.mkdir(parents=True)
            (case / "result.json").write_text(json.dumps({
                "name": "profile_10",
                "seed": 3,
                "status": "RTL_STALL",
            }), encoding="utf-8")

            rows, metadata = _random_rows([root], [("profile", 12)])

            self.assertEqual(rows[10]["seed"], 11)
            self.assertEqual(rows[10]["status"], "RTL_STALL")
            self.assertEqual(metadata["missing_by_profile"], {"profile": 11})
            self.assertEqual(metadata["selected_profiles"]["profile"], str(root / "profile"))


if __name__ == "__main__":
    unittest.main()
