"""Reject stale QEMU executables and model source/build receipts."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "qbs/run_ggml_segmented.py"
SPEC = importlib.util.spec_from_file_location("ggml_segmented_receipt", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeBuildReceipt(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.qemu = root / "build/qemu-system-riscv64"
        self.qemu.parent.mkdir()
        self.qemu.write_bytes(b"fixture executable")
        self.model = root / "qemu-10.2.0/target/riscv"
        self.model.mkdir(parents=True)
        sources = {}
        for name in ("qbs_abi.h", "qbs_ref.h", "qbs_ref.c", "qbs_helper.c"):
            path = self.model / name
            path.write_text(name)
            sources[str(path)] = MODULE.digest(path)
        self.config = self.qemu.parent / "config-host.mak"
        self.config.write_text(f"SRC_PATH={root / 'qemu-10.2.0'}\n")
        self.ninja = self.qemu.parent / "build.ninja"
        self.ninja.write_text("".join(f"build libqemu-riscv64-softmmu.a.p/target_riscv_{name}.o: c_COMPILER ../qemu-10.2.0/target/riscv/{name}\n"
                                     for name in ("qbs_helper.c", "qbs_ref.c")))
        sources.update({str(p): MODULE.digest(p) for p in (self.config, self.ninja)})
        self.log = self.qemu.parent / "native-model-build.log"
        self.log.write_text("fixture build complete\n")
        self.receipt = self.qemu.parent / "native-model-manifest.json"
        self.data = {"state": "PASS", "executable": str(self.qemu),
                     "executable_sha256": MODULE.digest(self.qemu),
                     "source_sha256": sources, "build_log_sha256": MODULE.digest(self.log)}
        self.save()

    def save(self):
        self.receipt.write_text(json.dumps(self.data))

    def test_valid(self):
        self.assertIn(self.receipt, MODULE.verify_native_build(self.qemu))

    def test_binary_changed(self):
        self.qemu.write_bytes(b"stale executable")
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_model_changed(self):
        (self.model / "qbs_ref.c").write_text("new reference, old binary")
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_omitted_model(self):
        del self.data["source_sha256"][str(self.model / "qbs_helper.c")]
        self.save()
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_build_log_changed(self):
        self.log.write_text("different build")
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_wrong_executable_path(self):
        self.data["executable"] = "/different/qemu-system-riscv64"
        self.save()
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_attested_wrong_source_tree(self):
        self.config.write_text("SRC_PATH=/different/qemu-10.2.0\n")
        self.data["source_sha256"][str(self.config)] = MODULE.digest(self.config)
        self.save()
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)

    def test_attested_wrong_compile_input(self):
        self.ninja.write_text(self.ninja.read_text().replace("../qemu-10.2.0/", "../other-qemu/"))
        self.data["source_sha256"][str(self.ninja)] = MODULE.digest(self.ninja)
        self.save()
        with self.assertRaises(RuntimeError):
            MODULE.verify_native_build(self.qemu)


if __name__ == "__main__":
    unittest.main()
