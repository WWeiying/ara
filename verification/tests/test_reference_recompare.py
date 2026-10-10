import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ara_verify.plan import _audit_reference_recomparison
from ara_verify.artifacts import check_inputs, simulation_image
from ara_verify.recompare_reference import COPIED_FILES
from verify import _parser


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class ReferenceRecomparisonTests(unittest.TestCase):
    def test_random_input_audit_detects_reference_binary_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf = root / "input.elf"
            simv = root / "simv"
            spike = root / "spike"
            for path in (elf, simv, spike):
                path.write_bytes(path.name.encode())
            inputs = {
                "binary": {"path": str(elf), "sha256": _digest(elf)},
                "simv": {"path": str(simv), "image_sha256": simulation_image(simv)},
                "spike": {"path": str(spike), "sha256": _digest(spike)},
            }
            self.assertEqual(check_inputs(inputs, elf), [])
            spike.write_bytes(b"changed")
            self.assertIn("reference Spike executable changed", check_inputs(inputs, elf))

    def test_random_and_replay_require_explicit_spike(self):
        for args in (
            ["run-rvv", "--simv", "simv"],
            ["replay-failed-rvv", "--summary", "summary.json",
             "--simv", "simv", "--output", "out"],
        ):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    _parser().parse_args(args)

    def test_recomparison_hashes_source_copy_spike_and_output(self):
        self.assertIn("trace_hart_0.log", COPIED_FILES)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source" / "tests" / "case"
            case = root / "output" / "tests" / "case"
            source.mkdir(parents=True)
            case.mkdir(parents=True)
            old_elf = root / "source" / "asm_test" / "case.o"
            old_elf.parent.mkdir()
            old_elf.write_bytes(b"elf")
            (source / "ara_commit_trace.csv").write_bytes(b"ara")
            (source / "trace_hart_0.log").write_bytes(b"aligned exception")
            (case / "input.elf").write_bytes(b"elf")
            (case / "ara_commit_trace.csv").write_bytes(b"ara")
            (case / "trace_hart_0.log").write_bytes(b"aligned exception")
            (case / "spike_commit.log").write_bytes(b"spike trace")
            (case / "spike_console.log").write_bytes(b"console")
            spike = root / "spike"
            spike.write_bytes(b"reference executable")
            metadata = {"source_run": str(root / "source"),
                        "spike": {"path": str(spike), "sha256": _digest(spike)}}
            _json(case / "source_evidence.json", {
                "source_case": str(source),
                "copied_sha256": {
                    str(old_elf): _digest(old_elf),
                    str(source / "ara_commit_trace.csv"):
                        _digest(source / "ara_commit_trace.csv"),
                    str(source / "trace_hart_0.log"):
                        _digest(source / "trace_hart_0.log"),
                },
            })
            _json(case / "reference_output.json", {
                "spike_sha256": _digest(spike),
                "spike_commit_sha256": _digest(case / "spike_commit.log"),
                "spike_console_sha256": _digest(case / "spike_console.log"),
            })
            _json(case / "spike.command.json", {
                "command": [str(spike), "--log-commits", str(case / "input.elf")],
            })
            rows = [{"artifact_dir": str(case)}]
            self.assertEqual(_audit_reference_recomparison(root / "output", metadata, rows), [])
            (case / "trace_hart_0.log").write_bytes(b"changed")
            self.assertIn("source or frozen copy changed: trace_hart_0.log", " ".join(
                _audit_reference_recomparison(root / "output", metadata, rows)))
            (case / "trace_hart_0.log").write_bytes(b"aligned exception")
            (case / "spike_commit.log").write_bytes(b"changed")
            self.assertIn("Spike output identity changed", " ".join(
                _audit_reference_recomparison(root / "output", metadata, rows)))


if __name__ == "__main__":
    unittest.main()
