import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from linux import build_userspace as builder


class LinuxUserspaceBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="userspace build ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repo"
        self.source_dir = self.repo / "verification/linux/userspace"
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "rvv_linux_smoke.c").write_text("int main(void) { return 0; }\n")
        (self.source_dir / "rvv_linux_state.S").write_text(".option arch,+v\n")
        (self.source_dir / "custom_caps.c").write_text("int custom_caps_probe(void) { return 0; }\n")
        self.base = self.repo / "base initramfs.cpio"
        self.base.write_bytes(b"trusted base archive")
        self.output = self.root / "output with spaces"
        self.cc = self.root / "riscv64-test-gcc"
        self.wrapper = self.root / "toolchain-wrapper"
        self.wrapper.write_bytes(b"compiler wrapper")
        self.wrapper.chmod(0o755)
        self.cc.symlink_to(self.wrapper.name)
        self.cpio = self.root / "cpio"
        self.cpio.write_bytes(b"cpio tool")
        self.cpio.chmod(0o755)
        self.objdump = self.root / "riscv64-test-objdump"
        self.external = self.root / "outside"
        self.external.mkdir()
        (self.external / "keep").write_bytes(b"do not modify")
        self.calls = []
        self.fail_on = None
        for patcher in (
            patch.object(builder, "REPO_ROOT", self.repo),
            patch.object(builder.shutil, "which", side_effect=self.find_tool),
            patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "123456789", "CPATH": "untrusted"}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(builder.subprocess, "run", side_effect=self.run_command)
        self.run_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def find_tool(self, name):
        if name in (str(self.cc), self.cc.name):
            return str(self.cc)
        if name == "cpio":
            return str(self.cpio)
        return None

    def run_command(self, argv, **kwargs):
        self.assertTrue(kwargs["check"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["umask"], 0o022)
        cwd = kwargs["cwd"]
        self.calls.append((argv, kwargs))
        if self.fail_on in argv:
            raise subprocess.CalledProcessError(2, argv)
        if argv[0] == str(self.cc):
            (cwd / argv[argv.index("-o") + 1]).write_bytes(b"mock ELF")
        elif argv[0] == str(self.objdump):
            kwargs["stdout"].write(b"mock disassembly\n")
        elif "--extract" in argv:
            self.assertEqual(kwargs["stdin"].read(), b"trusted base archive")
            (cwd / "usr/bin").mkdir(parents=True)
            (cwd / "bin").mkdir()
            (cwd / "bin/busybox").write_bytes(b"busybox")
            (cwd / "bin/busybox").chmod(0o755)
            (cwd / "bin/sh").symlink_to("busybox")
            (cwd / "lib").mkdir()
            (cwd / "lib/libresolv.so.2").write_bytes(b"resolver library")
            (cwd / "outside-link").symlink_to(self.external, target_is_directory=True)
            (cwd / "z file\nwith newline").write_bytes(b"unusual filename")
            # Installing over these links must not overwrite the base image.
            (cwd / "init").symlink_to(self.base)
            os.link(self.base, cwd / "usr/bin/rvv_linux_smoke")
        elif "--create" in argv:
            names = kwargs["stdin"].read()
            self.assertTrue(names.endswith(b"\0"))
            self.assertEqual(names.split(b"\0")[:-1], sorted(names.split(b"\0")[:-1]))
            for name in names.split(b"\0")[:-1]:
                self.assertEqual((cwd / os.fsdecode(name)).lstat().st_mtime, 123456789)
            kwargs["stdout"].write(b"mock newc\0" + names)
        else:
            self.fail(f"unexpected command: {argv}")
        return subprocess.CompletedProcess(argv, 0)

    def build(self, output=None):
        return builder.build_userspace(output or self.output, str(self.cc), self.base)

    def test_cli_requires_output_and_uses_repository_defaults(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised:
                builder.main([])
        self.assertEqual(raised.exception.code, 2)
        with patch.object(builder, "build_userspace") as build, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(builder.main(["--output", str(self.output)]), 0)
        build.assert_called_once_with(self.output, builder.DEFAULT_CC, builder.DEFAULT_BASE_INITRAMFS)
        self.assertEqual(
            builder.DEFAULT_CC,
            "/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/host/bin/"
            "riscv64-buildroot-linux-gnu-gcc",
        )
        self.assertEqual(
            builder.DEFAULT_BASE_INITRAMFS,
            Path(builder.__file__).resolve().parents[2]
            / "hardware/fpga/ara_dsa_vcu118/linux/artifacts/initramfs.cpio",
        )

    def test_refuses_nonempty_output_without_removing_anything(self):
        self.output.mkdir()
        sentinel = self.output / ".keep"
        sentinel.write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "empty directory"):
            self.build()
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertEqual(list(self.output.iterdir()), [sentinel])
        self.run_mock.assert_not_called()

    def test_refuses_output_file_and_symlinks(self):
        regular = self.root / "file"
        regular.write_bytes(b"keep")
        link = self.root / "link"
        link.symlink_to(self.external, target_is_directory=True)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing")
        for output in (regular, link, dangling):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.build(output)
        self.assertEqual(regular.read_bytes(), b"keep")
        self.assertTrue(link.is_symlink())
        self.assertTrue(dangling.is_symlink())
        self.run_mock.assert_not_called()

    def test_accepts_empty_output_and_refuses_reuse(self):
        self.output.mkdir()
        self.build()
        manifest = (self.output / "manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "empty directory"):
            self.build()
        self.assertEqual((self.output / "manifest.json").read_bytes(), manifest)
        self.assertEqual(self.run_mock.call_count, 3)

    def test_missing_source_base_or_tool_fails_before_creating_output(self):
        source = self.source_dir / "rvv_linux_state.S"
        for missing in (source, self.source_dir / "custom_caps.c", self.base):
            with self.subTest(missing=missing):
                original = missing.read_bytes()
                missing.unlink()
                with self.assertRaisesRegex(ValueError, "missing input file"):
                    self.build()
                missing.write_bytes(original)
        with patch.object(builder.shutil, "which", return_value=None):
            with self.assertRaisesRegex(ValueError, "executable not found"):
                self.build()
        self.assertFalse(self.output.exists())
        self.run_mock.assert_not_called()

    def test_invalid_epoch_is_rejected_before_commands(self):
        for epoch in ("bad", "-1", "4294967296"):
            with self.subTest(epoch=epoch), patch.dict(os.environ, {"SOURCE_DATE_EPOCH": epoch}):
                with self.assertRaises(ValueError):
                    self.build()
        self.assertFalse(self.output.exists())
        self.run_mock.assert_not_called()

    def test_scalar_flags_all_sources_and_wrapper_path_are_preserved(self):
        self.build()
        argv, kwargs = self.calls[0]
        self.assertEqual(argv[0], str(self.cc))
        for flag in (
            "-static", "-O2", "-Wall", "-Wextra", "-Werror",
            "-fno-tree-vectorize", "-fno-tree-slp-vectorize",
            "-march=rv64gc", "-mabi=lp64d",
        ):
            self.assertIn(flag, argv)
        self.assertIn(str(self.source_dir / "rvv_linux_smoke.c"), argv)
        self.assertIn(str(self.source_dir / "rvv_linux_state.S"), argv)
        self.assertIn(str(self.source_dir / "custom_caps.c"), argv)
        self.assertEqual([arg for arg in argv if arg.startswith("-march=")], ["-march=rv64gc"])
        self.assertEqual(kwargs["cwd"], self.output)
        self.assertEqual(kwargs["env"]["SOURCE_DATE_EPOCH"], "123456789")
        self.assertEqual(kwargs["env"]["LC_ALL"], "C")
        self.assertNotIn("CPATH", kwargs["env"])

    def test_manifest_records_input_output_hashes_and_exact_commands(self):
        manifest = self.build()
        saved = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(saved, manifest)
        self.assertEqual(saved["status"], "BUILT")
        self.assertEqual(saved["schema_version"], 1)
        self.assertEqual(
            set(saved["sources"]),
            {"rvv_linux_smoke.c", "rvv_linux_state.S", "custom_caps.c", "build_userspace.py"},
        )
        self.assertEqual(set(saved["inputs"]), {"base_initramfs", "cc", "cpio"})
        self.assertIn("initramfs.cpio", saved["outputs"])
        self.assertIn("rvv_linux_smoke", saved["outputs"])
        self.assertIn("init", saved["outputs"])
        for section in ("sources", "inputs", "outputs"):
            for record in saved[section].values():
                path = Path(record["path"])
                self.assertTrue(path.is_absolute())
                self.assertEqual(record["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual([command["argv"] for command in saved["commands"]], [call[0] for call in self.calls])
        self.assertEqual(saved["commands"][1]["stdin"], str(self.base))
        self.assertEqual(saved["commands"][-1]["stdin"], str(self.output / "cpio-files.list"))
        self.assertEqual(saved["commands"][-1]["stdout"], str(self.output / "initramfs.cpio"))
        self.assertEqual(saved["environment"], self.calls[0][1]["env"])

    def test_objdump_is_optional_and_derived_from_compiler_alias(self):
        self.objdump.write_bytes(b"objdump tool")
        self.objdump.chmod(0o755)
        manifest = self.build()
        self.assertEqual(self.calls[1][0], [str(self.objdump), "-d", "rvv_linux_smoke"])
        self.assertEqual((self.output / "rvv_linux_smoke.objdump").read_bytes(), b"mock disassembly\n")
        self.assertIn("objdump", manifest["inputs"])
        self.assertIn("rvv_linux_smoke.objdump", manifest["outputs"])

    def test_archive_is_sorted_normalized_and_does_not_follow_links(self):
        external_mtime = (self.external / "keep").stat().st_mtime_ns
        self.build()
        extract = self.calls[1][0]
        self.assertIn("--no-absolute-filenames", extract)
        self.assertIn("--no-preserve-owner", extract)
        create = self.calls[-1][0]
        for flag in ("--null", "--format=newc", "--reproducible", "--owner=0:0"):
            self.assertIn(flag, create)
        names = (self.output / "cpio-files.list").read_bytes().split(b"\0")[:-1]
        self.assertEqual(names[0], b".")
        self.assertIn(b"./z file\nwith newline", names)
        self.assertIn(b"./outside-link", names)
        self.assertNotIn(b"./outside-link/keep", names)
        self.assertEqual((self.external / "keep").stat().st_mtime_ns, external_mtime)
        self.assertEqual(self.base.read_bytes(), b"trusted base archive")
        rootfs = self.output / "rootfs"
        self.assertFalse((rootfs / "init").is_symlink())
        self.assertEqual((rootfs / "init").read_text(), builder.INIT_SCRIPT)
        self.assertEqual((rootfs / "usr/bin/rvv_linux_smoke").read_bytes(), b"mock ELF")
        self.assertEqual((rootfs / "init").stat().st_mode & 0o777, 0o755)
        self.assertEqual((rootfs / "usr/bin/rvv_linux_smoke").stat().st_mode & 0o777, 0o755)

    def test_install_rejects_parent_symlink_escaping_rootfs(self):
        rootfs = self.root / "rootfs"
        rootfs.mkdir()
        (rootfs / "usr").symlink_to(self.external, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "escapes rootfs"):
            builder.install_file(self.base, rootfs / "usr/bin/rvv_linux_smoke", rootfs)
        self.assertFalse((self.external / "bin").exists())

    def test_missing_lib64_link_is_installed_and_packaged(self):
        manifest = self.build()
        rootfs = self.output / "rootfs"
        self.assertTrue((rootfs / "lib64").is_symlink())
        self.assertEqual(os.readlink(rootfs / "lib64"), "lib")
        self.assertEqual((rootfs / "lib64/libresolv.so.2").read_bytes(), b"resolver library")
        listing = (self.output / "cpio-files.list").read_bytes()
        self.assertIn(b"./lib64", listing.split(b"\0"))
        self.assertNotIn(b"./lib64/libresolv.so.2", listing.split(b"\0"))
        self.assertEqual(
            manifest["outputs"]["cpio-files.list"]["sha256"],
            hashlib.sha256(listing).hexdigest(),
        )
        self.assertEqual(self.base.read_bytes(), b"trusted base archive")

    def test_existing_lib64_entries_are_preserved(self):
        for kind in ("directory", "link", "dangling-link", "file"):
            with self.subTest(kind=kind):
                def run_with_lib64(argv, **kwargs):
                    result = self.run_command(argv, **kwargs)
                    if "--extract" in argv:
                        lib64 = kwargs["cwd"] / "lib64"
                        if kind == "directory":
                            lib64.mkdir()
                            (lib64 / "keep").write_bytes(b"keep")
                        elif kind == "link":
                            lib64.symlink_to("lib")
                        elif kind == "dangling-link":
                            lib64.symlink_to("missing-lib")
                        else:
                            lib64.write_bytes(b"keep")
                    return result

                self.run_mock.side_effect = run_with_lib64
                output = self.root / kind
                self.build(output)
                lib64 = output / "rootfs/lib64"
                if kind == "directory":
                    self.assertFalse(lib64.is_symlink())
                    self.assertEqual((lib64 / "keep").read_bytes(), b"keep")
                elif kind in ("link", "dangling-link"):
                    self.assertEqual(os.readlink(lib64), "lib" if kind == "link" else "missing-lib")
                else:
                    self.assertFalse(lib64.is_symlink())
                    self.assertEqual(lib64.read_bytes(), b"keep")

    def test_install_directory_modes_do_not_depend_on_umask(self):
        rootfs = self.root / "rootfs"
        rootfs.mkdir()
        original_umask = os.umask(0o077)
        try:
            builder.install_file(self.base, rootfs / "usr/bin/rvv_linux_smoke", rootfs)
        finally:
            os.umask(original_umask)
        for name in ("usr", "usr/bin", "usr/bin/rvv_linux_smoke"):
            self.assertEqual((rootfs / name).stat().st_mode & 0o777, 0o755)

    def test_relative_paths_are_resolved_before_subprocess_cwd_changes(self):
        with patch.object(builder.os, "getcwd", return_value=str(self.root)):
            manifest = builder.build_userspace(Path("relative output"), self.cc.name, Path("repo") / self.base.name)
        self.assertEqual(manifest["inputs"]["base_initramfs"]["path"], str(self.base))
        self.assertEqual(self.calls[0][1]["cwd"], self.root / "relative output")
        self.assertIn(str(self.source_dir / "custom_caps.c"), self.calls[0][0])

    def test_repeated_builds_have_identical_archive_inputs(self):
        first = self.build()
        second = self.build(self.root / "second output")
        for name in ("rvv_linux_smoke", "init", "cpio-files.list", "initramfs.cpio"):
            self.assertEqual(first["outputs"][name]["sha256"], second["outputs"][name]["sha256"])

    def test_command_failure_does_not_emit_success_manifest_or_delete_evidence(self):
        for index, command in enumerate((str(self.cc), "--extract", "--create")):
            with self.subTest(command=command):
                self.fail_on = command
                output = self.root / f"failed-{index}"
                with self.assertRaises(subprocess.CalledProcessError):
                    self.build(output)
                self.assertTrue((output / "build.log").is_file())
                self.assertFalse((output / "manifest.json").exists())
        self.assertEqual(self.base.read_bytes(), b"trusted base archive")

    def test_cli_passes_overrides_and_reports_command_failure(self):
        self.fail_on = str(self.cc)
        with patch("sys.stdout", new_callable=io.StringIO) as stdout:
            status = builder.main([
                "--output", str(self.output), "--cc", self.cc.name,
                "--base-initramfs", str(self.base),
            ])
        self.assertEqual(status, 1)
        self.assertIn("error:", stdout.getvalue())
        self.assertNotIn('"status": "BUILT"', stdout.getvalue())


class LinuxUserspaceInitTests(unittest.TestCase):
    def test_init_pass_and_failure_paths_with_stubbed_guest_commands(self):
        # Only a host shell runs; all guest commands, including poweroff, are stubs.
        stubs = """
busybox() {
    case "$1" in
        mount) return "$mount_rc" ;;
        sync) echo synced ;;
        poweroff) echo "poweroff $2"; exit 0 ;;
        sleep) echo unexpected-sleep; exit 2 ;;
        *) return 0 ;;
    esac
}
smoke() { echo "smoke argc=$#"; return "$smoke_rc"; }
"""
        script = builder.INIT_SCRIPT.replace("/bin/busybox", "busybox").replace(
            "/usr/bin/rvv_linux_smoke", "smoke"
        )
        for smoke_rc, mount_rc in ((0, 0), (1, 0), (139, 0), (0, 1)):
            with self.subTest(smoke_rc=smoke_rc, mount_rc=mount_rc):
                result = subprocess.run(
                    ["/bin/sh", "-c", f"smoke_rc={smoke_rc}; mount_rc={mount_rc}\n" + stubs + script],
                    check=True, capture_output=True, text=True, timeout=5,
                )
                self.assertIn("Ara verification Linux init reached", result.stdout)
                self.assertNotIn("VCU118", result.stdout)
                passed = smoke_rc == mount_rc == 0
                self.assertEqual("ARA_LINUX_USERSPACE PASS" in result.stdout, passed)
                self.assertEqual("ARA_LINUX_USERSPACE FAIL" in result.stdout, not passed)
                self.assertEqual("smoke argc=0" in result.stdout, mount_rc == 0)
                self.assertTrue(result.stdout.endswith("synced\npoweroff -f\n"))
                self.assertNotIn("unexpected-sleep", result.stdout)


if __name__ == "__main__":
    unittest.main()
