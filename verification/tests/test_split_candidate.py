"""Host-only command parsing and generated-function guard tests."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import build_split_candidate as build


class SplitCandidateTests(unittest.TestCase):
    def test_real_record_recovers_grouping_and_only_changes_cxx_optimization(self):
        cache = build.CACHE
        original = build.parse_command((cache / "Vara_tb_verilator__verFiles.dat").read_text(),
                                       (cache / "Vara_tb_verilator.mk").read_text())
        candidate = build.candidate_args(original, cache, Path("/new/obj"), Path("/new/bender"))
        self.assertEqual(candidate.count("-O3"), 1)
        self.assertEqual(candidate[candidate.index("-CFLAGS") + 1],
                         "-O1 -march=native -DTOPLEVEL_NAME=ara_tb_verilator")
        self.assertEqual(candidate[candidate.index("--Mdir") + 1], "/new/obj")
        self.assertEqual(candidate[candidate.index("-f") + 1], "/new/bender")
        self.assertEqual(candidate[-4:], ["--output-split", "10000", "--output-split-cfuncs", "2000"])
        self.assertNotIn("--build", candidate)
        self.assertIn("-O3 -march=native -DTOPLEVEL_NAME=ara_tb_verilator", original)

    def test_command_makefile_disagreement_refuses_guessing(self):
        cache = build.CACHE
        with self.assertRaises(ValueError):
            build.parse_command((cache / "Vara_tb_verilator__verFiles.dat").read_text(),
                                (cache / "Vara_tb_verilator.mk").read_text().replace("-march=native", "-march=other"))

    def test_function_statistics_record_oversized_function(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "model.cpp"
            source.write_text("void large() {\n" + " ;\n" * 100000 + "}\n")
            def execute(argv, phase, timeout):
                tags = Path(argv[argv.index("-f") + 1])
                tags.write_text(json.dumps({"_type": "tag", "kind": "function", "name": "large",
                                           "path": str(source), "line": 1, "end": 100002}) + "\n")
            measured = build.measure(root, root, "fixture", execute)
            self.assertEqual(measured["max_function_lines"], 100002)
            self.assertEqual(len(measured["over_limit_functions"]), 1)
            self.assertEqual(measured["max_unparsed_gap_lines"], 0)

    def test_missing_function_extent_is_not_split_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "model.cpp").write_text("void missing() {}\n")
            def execute(argv, phase, timeout):
                Path(argv[argv.index("-f") + 1]).write_text(json.dumps({
                    "_type": "tag", "kind": "function", "line": 1, "name": "missing"}) + "\n")
            with self.assertRaisesRegex(RuntimeError, "complete function extent"):
                build.measure(root, root, "fixture", execute)


if __name__ == "__main__":
    unittest.main()
