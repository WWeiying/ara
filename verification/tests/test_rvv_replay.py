import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ara_verify.rvv_replay import _optional_vector_exit_pc, failed_random_cases


class RvvReplayDiscoveryTests(unittest.TestCase):
    def test_plain_random_elf_does_not_require_signature_exit(self):
        with patch("ara_verify.rvv_replay._vector_exit_pc", side_effect=RuntimeError(
            "ELF test.o has no vector-signature exit symbol"
        )):
            self.assertIsNone(_optional_vector_exit_pc(
                Path("test.o"), Path("readelf"), Path("objdump")
            ))

    def test_malformed_signature_exit_is_not_hidden(self):
        with patch("ara_verify.rvv_replay._vector_exit_pc", side_effect=RuntimeError(
            "cannot find vector-signature exit ecall in test.o"
        )):
            with self.assertRaisesRegex(RuntimeError, "cannot find"):
                _optional_vector_exit_pc(
                    Path("test.o"), Path("readelf"), Path("objdump")
                )

    def test_discovers_failed_random_elf_from_profile_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            (profile / "asm_test").mkdir(parents=True)
            summary = root / "campaign.json"
            summary.write_text(json.dumps({"results": [
                {
                    "profile": "profile_a",
                    "name": "profile_a_2",
                    "seed": 3,
                    "status": "RTL_STALL",
                    "artifact_dir": str(profile / "tests" / "profile_a_2"),
                },
                {
                    "class": "random",
                    "profile": "profile_a",
                    "name": "profile_a_0",
                    "seed": 1,
                    "status": "PASS",
                    "artifact_dir": str(profile / "tests" / "profile_a_0"),
                },
            ]}), encoding="utf-8")
            cases = failed_random_cases(summary)
            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].name, "profile_a_2")
            self.assertEqual(cases[0].elf, profile / "asm_test" / "profile_a_2.o")

    def test_discovers_failed_random_elf_from_list_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            (profile / "asm_test").mkdir(parents=True)
            elf = profile / "asm_test" / "profile_a_8.o"
            summary = root / "replay.json"
            summary.write_text(json.dumps([
                {
                    "name": "profile_a_8",
                    "seed": 9,
                    "status": "VECTOR_MISMATCH",
                    "artifact_dir": str(profile / "tests" / "profile_a_8"),
                    "elf": str(elf),
                }
            ]), encoding="utf-8")

            cases = failed_random_cases(summary, ["profile_a_8"])

            self.assertEqual(len(cases), 1)
            self.assertEqual(cases[0].name, "profile_a_8")
            self.assertEqual(cases[0].elf, elf)


if __name__ == "__main__":
    unittest.main()
