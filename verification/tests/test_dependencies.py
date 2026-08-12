import tempfile
import unittest
from pathlib import Path

from ara_verify.dependencies import DependencyError, locked_dependencies, locked_tools


class DependencyLockTests(unittest.TestCase):
    def test_locked_git_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: 0123abcdef\n"
                "    source:\n"
                "      Git: git@example.com:cva6.git\n"
                "    dependencies: []\n",
                encoding="utf-8",
            )
            self.assertEqual(
                locked_dependencies(lock)[0],
                locked_dependencies(lock)[0].__class__(
                    "cva6", "0123abcdef", "git@example.com:cva6.git"
                ),
            )

    def test_rejects_path_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "Bender.lock"
            lock.write_text(
                "packages:\n"
                "  cva6:\n"
                "    revision: null\n"
                "    source:\n"
                "      Path: hardware/deps/cva6\n",
                encoding="utf-8",
            )
            with self.assertRaises(DependencyError):
                locked_dependencies(lock)

    def test_locked_verification_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "toolchain.lock.json"
            lock.write_text(
                '{"schema_version":1,"tools":{"riscv-dv-rvv1":{'
                '"url":"https://example.com/riscv-dv.git",'
                '"fetch_ref":"refs/pull/1/head",'
                '"revision":"0123456789abcdef0123456789abcdef01234567",'
                '"path":"verification/tools/riscv-dv-rvv1"}}}',
                encoding="utf-8",
            )
            tool = locked_tools(lock)[0]
            self.assertEqual(tool.name, "riscv-dv-rvv1")
            self.assertEqual(tool.path, Path("verification/tools/riscv-dv-rvv1"))

    def test_rejects_tool_path_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "toolchain.lock.json"
            lock.write_text(
                '{"schema_version":1,"tools":{"bad":{'
                '"url":"https://example.com/tool.git","fetch_ref":"main",'
                '"revision":"0123456789abcdef0123456789abcdef01234567",'
                '"path":"../outside"}}}',
                encoding="utf-8",
            )
            with self.assertRaises(DependencyError):
                locked_tools(lock)
