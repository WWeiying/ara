"""Host schedule/mutation checks. No numerical model or simulator execution."""
from pathlib import Path
import resource
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT / "software/akv/experimental/paired_heads/dispatch.h"
SOURCE = Path(__file__).with_suffix(".c")


def no_core():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class DispatchTests(unittest.TestCase):
    def run_header(self, text):
        with tempfile.TemporaryDirectory(prefix="akv-pair-dispatch-") as temp:
            path = Path(temp)
            header = path / "dispatch.h"
            header.write_text(text)
            binary = path / "test"
            compiled = subprocess.run(
                ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
                 "-include", str(header), str(SOURCE), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            return subprocess.run([str(binary)], capture_output=True, text=True,
                                  timeout=30, preexec_fn=no_core)

    def test_original(self):
        result = self.run_header(HEADER.read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout,
                         "PAIR_DISPATCH_PASS schedules=24576 numerical_execution=0\n")

    def test_pointer_and_tail_mutations(self):
        source = HEADER.read_text()
        mutations = [
            ("head * query_stride", "head * (2 * dim)"),
            ("score + head * 64", "score + head * tokens"),
            ("accumulator + head * 256", "accumulator + head * dim"),
            ("old_scale + head", "old_scale + head * 2"),
            ("head += 2", "head += 1"),
            ("if (head < heads)", "if (0)"),
            ("if (!admitted)", "if (admitted || !admitted)"),
        ]
        for before, after in mutations:
            with self.subTest(mutation=before):
                self.assertIn(before, source)
                result = self.run_header(source.replace(before, after))
                self.assertNotEqual(result.returncode, 0,
                                    "schedule checker accepted a mutated dispatch")


if __name__ == "__main__":
    unittest.main()
