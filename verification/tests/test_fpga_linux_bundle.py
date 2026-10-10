"""Isolated bundle fixtures; no SDK build, board access, or live payload inputs."""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fpga import prepare_linux_bundle as bundle


ELF_TEXT = """ELF Header:
  Class: ELF64
  Data: 2's complement, little endian
  Type: EXEC (Executable file)
  Machine: RISC-V
  Entry point address: 0x80000000
Program Headers:
  LOAD 0x001000 0x80000000 0x80000000 0x000200 0x000300 R E 0x1000
Symbol table '.symtab':
  1: 0000000080000080 0 NOTYPE GLOBAL DEFAULT 1 fw_fdt_bin
  2: 0000000080000040 0 NOTYPE LOCAL DEFAULT 1 _jump_addr
"""


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / "sdk"
        self.source = self.sdk / "buildroot/output/build/opensbi-1.7"
        self.output = self.root / "verification/out/bundle"
        self.initramfs = self.write(bundle.CHECKED_INITRAMFS, b"checked rootfs bytes" * 16)
        self.write("sdk/install64_qemu/Image", b"unchanged kernel")
        self.write(bundle.EXPORT / "linux/ara_vcu118.dts.in",
                   b"start=<0 __INITRD_START__>; end=<0 __INITRD_END__>;")
        self.write(bundle.EXPORT / "linux/build_linux_bringup.sh", b"original builder")
        for name in ("Makefile", "platform/generic/configs/defconfig", "firmware/fw_base.S"):
            self.write(self.source / name, b"source input")
        self.write(self.source / "scripts/script.sh", b"#!/bin/sh\n").chmod(0o755)
        self.write(self.source / "include/sbi/sbi_version.h",
                   b"#define OPENSBI_VERSION_MAJOR 1\n#define OPENSBI_VERSION_MINOR 7\n")
        self.write(self.source / "build/old.elf", b"old SDK build, must remain unchanged")
        self.preparer = self.write("prepare.py", b"fixture preparer")
        self.bin = self.root / "bin"
        for name in ("make", "dtc", "fdtget", "fdtput", "python3", "cc1"):
            self.write(self.bin / name, b"#!/bin/sh\nexit 99\n").chmod(0o755)
        self.prefix = str(self.sdk / "buildroot/output/host/bin/riscv64-buildroot-linux-gnu-")
        for name in ("gcc.br_real", "as", "ld", "ar", "objcopy", "readelf", "strip"):
            self.write(Path(self.prefix + name), b"#!/bin/sh\nexit 99\n").chmod(0o755)
        wrapper = self.write(Path(self.prefix).parent / "toolchain-wrapper", b"#!/bin/sh\nexit 99\n")
        wrapper.chmod(0o755)
        Path(self.prefix + "gcc").symlink_to("toolchain-wrapper")
        self.mutate = None
        self.bad_embedded = False
        self.bad_endpoint = False
        self.bad_readelf = False
        self.sim_ram_mib = 2048
        self.quiet_opensbi = False

    def write(self, path, data):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def native_fixture(self, runner, argv, cwd, label, timeout=300):
        self.assertIsInstance(argv, list)
        self.assertTrue(all(isinstance(arg, str) for arg in argv))
        self.assertTrue(cwd.is_relative_to(self.output))
        result = ""
        if label == "dtc":
            self.assertEqual(argv, [str(self.bin / "dtc"), "-I", "dts", "-O", "dtb", "-o",
                                    str(self.output / "ara_vcu118.dtb"), str(self.output / "ara_vcu118.dts")])
            (self.output / "ara_vcu118.dtb").write_bytes(b"fixture compiled DTB")
        elif label == "fdtput":
            self.assertEqual(argv, [str(self.bin / "fdtput"), "-t", "x",
                                    str(self.output / "ara_vcu118.dtb"), "/memory@80000000",
                                    "reg", "0", "80000000", "0", f"{self.sim_ram_mib * 1024 * 1024:x}"])
            (self.output / "ara_vcu118.dtb").write_bytes(b"fixture compiled DTB with reduced RAM")
        elif label == "fdtget":
            self.assertEqual(argv[:4], [str(self.bin / "fdtget"), "-t", "x", str(self.output / "ara_vcu118.dtb")])
            if argv[5] == "reg":
                self.assertEqual(argv[4], "/memory@80000000")
                result = f"0 80000000 0 {self.sim_ram_mib * 1024 * 1024:x}\n"
            else:
                self.assertEqual(argv[4], "/chosen")
                size = self.initramfs.stat().st_size
                value = bundle.INITRD_ADDR if argv[5] == "linux,initrd-start" else bundle.INITRD_ADDR + size
                result = f"0 {value + int(self.bad_endpoint):x}\n"
        elif label == "compiler-backend":
            self.assertEqual(argv, [self.prefix + "gcc", "-print-prog-name=cc1"])
            result = str(self.bin / "cc1") + "\n"
        elif label == "opensbi":
            expected = [str(self.bin / "make"), "-C", str(self.output / "inputs/opensbi-1.7"),
                                    "-j4", f"O={self.output}/opensbi-build", "PLATFORM=generic",
                                    "PLATFORM_RISCV_XLEN=64", f"CROSS_COMPILE={self.prefix}",
                                    f"DTC={self.bin}/dtc", "FW_TEXT_START=0x80000000",
                                    f"FW_FDT_PATH={self.output}/ara_vcu118.dtb", "FW_JUMP=y",
                                    "FW_DYNAMIC=n", "FW_PAYLOAD=n", "FW_JUMP_ADDR=0x80200000",
                                    "FW_JUMP_FDT_ADDR=0x80100000"]
            self.assertEqual(argv, [*expected, *(["FW_OPTIONS=0x1"] if self.quiet_opensbi else []), "all"])
            data = bytearray(0x1200)
            data[:4] = b"\x7fELF"
            data[0x1040:0x1048] = bundle.KERNEL_ADDR.to_bytes(8, "little")
            dtb = (self.output / "ara_vcu118.dtb").read_bytes()
            data[0x1080:0x1080 + len(dtb)] = b"X" * len(dtb) if self.bad_embedded else dtb
            self.write(self.output / "opensbi-build/platform/generic/firmware/fw_jump.elf", data)
            if self.mutate:
                self.mutate()
        elif label == "strip":
            self.assertEqual(argv, [self.prefix + "strip", "--strip-debug", str(self.output / "fw_jump.elf")])
        elif label == "readelf":
            self.assertEqual(argv, [self.prefix + "readelf", "-h", "-lW", "-sW", str(self.output / "fw_jump.elf")])
            result = ELF_TEXT.replace("0x001000", "0x000fff") if self.bad_readelf else ELF_TEXT
        else:
            self.fail(f"unexpected native helper: {label}: {argv}")
        stdout = runner.output / "logs" / f"{len(runner.commands):03d}-{label}.stdout"
        stdout.write_text(result)
        runner.commands.append({"argv": argv, "cwd": str(cwd), "stdout": str(stdout), "returncode": 0})
        return result

    def prepare(self):
        expected = bundle.file_record(self.initramfs)["sha256"]
        fixture = self.native_fixture
        with patch.dict(os.environ, {"PATH": str(self.bin)}), \
                patch.object(bundle, "HOST_PATH", str(self.bin)), \
                patch.object(bundle, "CHECKED_SHA256", expected), \
                patch.object(bundle, "__file__", str(self.preparer)), \
                patch.object(bundle.NativeRunner, "run", lambda runner, *args, **kw: fixture(runner, *args, **kw)):
            return bundle.prepare_bundle(self.output, root=self.root, sdk=self.sdk,
                                         sim_ram_mib=self.sim_ram_mib,
                                         quiet_opensbi=self.quiet_opensbi)

    def test_full_bundle_exact_native_argv_and_preserved_inputs(self):
        original = bundle.tree_records(self.source, exclude_build=False)
        kernel = bundle.file_record(self.sdk / "install64_qemu/Image")
        result = self.prepare()
        self.assertEqual(result["status"], "PREPARED_NOT_BOOTED")
        self.assertEqual(result["board_boot"], "NOT_RUN")
        self.assertEqual(result["custom_compute"], "NOT_VALIDATED")
        self.assertEqual((self.output / "initramfs.cpio").read_bytes(), self.initramfs.read_bytes())
        self.assertEqual(bundle.tree_records(self.source, exclude_build=False), original)
        bundle.unchanged(kernel)
        self.assertFalse((self.output / "inputs/opensbi-1.7/build").exists())
        self.assertIn("opensbi-build/platform/generic/firmware/fw_jump.elf", result["files"])
        self.assertEqual(result["embedded_dtb"]["dtb_sha256"], bundle.file_record(self.output / "ara_vcu118.dtb")["sha256"])
        for row in result["files"].values():
            self.assertEqual(row["sha256"], bundle.file_record(Path(row["path"]))["sha256"])

    def test_simulation_256_mib_bundle_has_matching_external_and_embedded_dtb(self):
        self.sim_ram_mib = 256
        result = self.prepare()
        self.assertEqual(result["sim_ram_mib"], 256)
        self.assertEqual(result["dtb_properties"]["/memory@80000000/reg"],
                         [0, bundle.FW_ADDR, 0, 256 * 1024 * 1024])
        self.assertEqual(result["embedded_dtb"]["dtb_sha256"],
                         bundle.file_record(self.output / "ara_vcu118.dtb")["sha256"])

    def test_quiet_boot_is_explicit_and_frozen_in_build_command(self):
        self.quiet_opensbi = True
        result = self.prepare()
        self.assertTrue(result["quiet_opensbi"])
        opensbi = next(row for row in result["commands"] if row["argv"][-1] == "all")
        self.assertIn("FW_OPTIONS=0x1", opensbi["argv"])

    def test_empty_directory_accepted_nonempty_rejected(self):
        self.output.mkdir(parents=True)
        self.prepare()
        manifest = (self.output / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            self.prepare()
        self.assertEqual((self.output / "manifest.json").read_bytes(), manifest)

    def test_missing_input_rejected_before_output(self):
        (self.sdk / "install64_qemu/Image").unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_checked_hash_rejected_before_native_execution(self):
        with patch.object(bundle, "__file__", str(self.preparer)):
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                bundle.prepare_bundle(self.output, root=self.root, sdk=self.sdk)
        self.assertFalse(self.output.exists())

    def test_missing_tool_rejected_without_output(self):
        (self.bin / "fdtget").unlink()
        with self.assertRaisesRegex(ValueError, "missing executable"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_output_parent_symlink_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.root / "verification/out/link").symlink_to(outside, target_is_directory=True)
        self.output = self.root / "verification/out/link/bundle"
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_sdk_output_and_source_reuse_refused(self):
        for path in (self.sdk / "new", self.source / "new", self.root / EXPORT_PATH):
            self.output = path
            with self.assertRaises(ValueError):
                self.prepare()

    def test_symlink_input_and_source_refused(self):
        copy = self.write("cpio", self.initramfs.read_bytes())
        self.initramfs.unlink()
        self.initramfs.symlink_to(copy)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.prepare()
        self.initramfs.unlink()
        self.initramfs.write_bytes(copy.read_bytes())
        (self.source / "firmware/escape.S").symlink_to(copy)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_mismatch_and_misalignment_never_publish_success(self):
        for attribute, message in (("bad_endpoint", "DTB"), ("bad_embedded", "embedded DTB"), ("bad_readelf", "misaligned")):
            with self.subTest(attribute=attribute):
                self.output = self.root / "verification/out" / attribute
                setattr(self, attribute, True)
                with self.assertRaisesRegex(ValueError, message):
                    self.prepare()
                self.assertFalse((self.output / "manifest.json").exists())
                self.assertEqual(json.loads((self.output / "failure.json").read_text())["status"], "FAILED")
                setattr(self, attribute, False)

    def test_changed_source_input_and_snapshot_refused(self):
        for kind in ("source", "kernel", "snapshot", "dtb", "copied_kernel"):
            with self.subTest(kind=kind):
                self.output = self.root / "verification/out" / kind
                targets = {"source": self.source / "Makefile", "kernel": self.sdk / "install64_qemu/Image",
                           "snapshot": self.output / "inputs/opensbi-1.7/Makefile", "dtb": self.output / "ara_vcu118.dtb",
                           "copied_kernel": self.output / "Image"}
                self.mutate = lambda: targets[kind].write_bytes(f"changed during build: {kind}".encode())
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.prepare()
                self.assertFalse((self.output / "manifest.json").exists())

    def test_wrapper_argv0_not_resolved_to_toolchain_wrapper(self):
        tool = bundle.native_tool(self.prefix + "gcc")
        self.assertEqual(tool["argv0"], self.prefix + "gcc")
        self.assertTrue(tool["resolved"]["path"].endswith("toolchain-wrapper"))


EXPORT_PATH = bundle.EXPORT / "linux/new-output"


class GeometryTests(unittest.TestCase):
    def test_template_and_fdt_cells_strict(self):
        template = "__INITRD_START__ __INITRD_END__"
        self.assertEqual(bundle.render_dts(template, 3183104), "0x88000000 0x88309200")
        for text in ("missing", template + " __INITRD_START__"):
            with self.assertRaises(ValueError):
                bundle.render_dts(text, 10)
        for size in (0, -1, 0x80000000):
            with self.assertRaises(ValueError):
                bundle.render_dts(template, size)
        for text in ("", "88000000", "0 88000000 extra", "0 100000000", "oops 0"):
            with self.assertRaises(ValueError):
                bundle.cells(text, 2)

    def test_readelf_rejects_missing_wrong_truncated_or_overlapping_loads(self):
        self.assertEqual(bundle.parse_readelf(ELF_TEXT, 0x1200)["entry"], bundle.FW_ADDR)
        for text, size in ((ELF_TEXT.replace("LOAD", "NONE"), 0x1200),
                           (ELF_TEXT.replace("ELF64", "ELF32"), 0x1200),
                           (ELF_TEXT.replace("RISC-V", "X86-64"), 0x1200),
                           (ELF_TEXT.replace("0x80000000", "0x80000001"), 0x1200),
                           (ELF_TEXT.replace("0x000300", "0x000100"), 0x1200),
                           (ELF_TEXT, 0x1100),
                           (ELF_TEXT.replace("0x000300", "0x200000"), 0x1200),
                           (ELF_TEXT.replace("0x1000\n", "0x1001\n"), 0x1200),
                           (ELF_TEXT.replace("fw_fdt_bin", "missing"), 0x1200),
                           (ELF_TEXT + "LOAD 0x001000 0x80000000 0x80000000 0x200 0x300 R 0x1000\n", 0x1200)):
            with self.subTest(text=text, size=size), self.assertRaises(ValueError):
                bundle.parse_readelf(text, size)

    def test_loadmap_bounds_and_overlap(self):
        valid = [{"address": 0x80000000, "size_bytes": 4096}, {"address": 0x80001000, "size_bytes": 4096}]
        bundle.nonoverlap(valid)
        for address, size in ((0x80000001, 4096), (0x7fffffff, 1), (0xffffffff, 2), (0x88000000, 0)):
            with self.assertRaises(ValueError):
                bundle.nonoverlap([valid[0], {"address": address, "size_bytes": size}])

    def test_make_recipe_unsafe_paths_rejected(self):
        for value in ("relative", "/tmp/with space", "/tmp/$(touch)/build", "/tmp/a;true", "/tmp/a\n"):
            with self.assertRaises(ValueError):
                bundle.make_path(value)


class NativeRunnerTests(unittest.TestCase):
    def test_argv_is_not_shell_string_and_payload_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = []
            runner = bundle.NativeRunner(root, {"PATH": os.defpath}, commands)
            args = [sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", "one two", "$(never executed)", "--flag=value"]
            self.assertEqual(json.loads(runner.run(args, root, "argv")), args[3:])
            self.assertEqual(commands[0]["argv"], args)
            with self.assertRaises(ValueError):
                runner.run("echo unsafe", root, "bad")

    def test_nonzero_and_timeout_fail_and_reap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commands = []
            runner = bundle.NativeRunner(root, {"PATH": os.defpath}, commands)
            with self.assertRaisesRegex(ValueError, "native helper failed"):
                runner.run([sys.executable, "-c", "raise SystemExit(3)"], root, "failure")
            with self.assertRaises(bundle.subprocess.TimeoutExpired):
                runner.run([sys.executable, "-c", "import time; time.sleep(30)"], root, "timeout", timeout=0.05)
            self.assertTrue(all(command["returncode"] is not None for command in commands))


if __name__ == "__main__":
    unittest.main()
