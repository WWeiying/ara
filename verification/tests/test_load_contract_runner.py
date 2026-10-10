"""Host-only type, path and manifest tests; never import the load checker or run EDA."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cva6 import run_load_contract as runner


def type_source():
    return "\n".join(
        f"{'parameter' if index == 0 else 'localparam'} type {name} = "
        "struct packed {\r\n  logic [CVA6Cfg.XLEN-1:0] value; // retain spacing\r\n},"
        for index, name in enumerate(runner.TYPE_NAMES))


class LoadContractRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "verification/out/baseline/package"
        self.output = self.root / "verification/out/new-load-run"
        self.patch_root = patch.object(runner, "ROOT", self.root)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)

    def put(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def package_fixture(self):
        files = {name: ("// " + name + "\n").encode() for name in runner.SOURCES + runner.EXTRA}
        files[runner.CORE + "cva6.sv"] = type_source().encode()
        files["unselected.bin"] = b"not copied or audited\x00"
        files["manifest.json"] = json.dumps({"defines": {}, "files": list(files)}).encode()
        for name, data in files.items():
            self.put(self.package / name, data)
        sums = "".join(f"{runner.digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
        self.put(self.package / "SHA256SUMS", sums)
        for name in runner.HOST_FILES:
            self.put(self.root / name, b"// host fixture bytes\r\n")
        return files, sums

    def test_exact_types_preserve_body_comments_widths_and_newlines(self):
        source = type_source()
        result = runner.extract_types(source)
        body = "struct packed {\r\n  logic [CVA6Cfg.XLEN-1:0] value; // retain spacing\r\n}"
        self.assertEqual(runner.TYPE_NAMES, ("exception_t", "lsu_ctrl_t", "dcache_req_i_t", "dcache_req_o_t"))
        for name in runner.TYPE_NAMES:
            self.assertIn(f"typedef {body} {name};", result)
        self.assertEqual(result.count("typedef "), 4)

    def test_ambiguous_missing_and_nonflat_types_fail(self):
        source = type_source()
        variants = (source + source, source.replace("exception_t", "other_t"),
                    source.replace("struct packed", "struct", 1),
                    source.replace("logic [CVA6Cfg.XLEN-1:0] value;", "struct packed { logic x; } value;", 1))
        for value in variants:
            with self.subTest(value=value[:80]), self.assertRaises(ValueError):
                runner.extract_types(value)

    def test_new_output_accepted_without_creating_it(self):
        self.assertEqual(runner.validate_output(self.output, self.package), self.output)
        self.assertFalse(self.output.exists())

    def test_outside_base_traversal_package_and_argument_aliases_rejected(self):
        for path in (self.root / "outside", self.root / "verification/out",
                     self.output / ".." / "alias", self.package / "new",
                     self.package.parent, self.output.with_name("bad+incdir"),
                     self.output.with_name("bad name")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.validate_output(path, self.package)

    def test_existing_output_file_and_directory_rejected_without_overwrite(self):
        self.put(self.output, b"keep me")
        with self.assertRaisesRegex(ValueError, "exists"):
            runner.validate_output(self.output, self.package)
        self.assertEqual(self.output.read_bytes(), b"keep me")
        with self.assertRaisesRegex(ValueError, "parent"):
            runner.validate_output(self.output / "child", self.package)
        self.output.unlink()
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "exists"):
            runner.validate_output(self.output, self.package)

    def test_linked_and_dangling_output_rejected(self):
        self.output.parent.mkdir(parents=True)
        self.output.symlink_to(self.root / "absent")
        for path in (self.output, self.output / "child"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "symlink"):
                runner.validate_output(path, self.package)

    def test_input_symlink_and_nonregular_file_rejected(self):
        target = self.root / "target"
        self.put(target, b"data")
        link = self.root / "link"
        link.symlink_to(target)
        for path in (link, self.root, self.root / "missing"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                runner.read_file(path)

    def test_checksum_text_and_binary_markers(self):
        sha = runner.digest(b"bytes")
        self.assertEqual(runner.parse_checksums(f"{sha}  rtl/a.sv\n{sha} *rtl/b.sv\n".encode()),
                         {"rtl/a.sv": sha, "rtl/b.sv": sha})

    def test_checksum_duplicates_malformed_and_unsafe_paths_rejected(self):
        sha = runner.digest(b"bytes")
        valid = f"{sha}  rtl/a.sv\n"
        invalid = [b"", b"not a checksum\n", (valid + valid).encode()]
        invalid += [f"{sha}  {name}\n".encode() for name in
                    ("/absolute", "../outside", "rtl/../a.sv", "./a.sv", "rtl//a.sv", ".", "a\\b", "a b")]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                runner.parse_checksums(data)

    def test_package_manifest_and_all_selected_files_must_be_sealed(self):
        files, sums = self.package_fixture()
        manifest, checksums = runner.package_metadata(files["manifest.json"], sums)
        self.assertEqual(manifest["defines"], {})
        self.assertEqual(checksums["manifest.json"], runner.digest(files["manifest.json"]))
        with self.assertRaisesRegex(ValueError, "manifest checksum"):
            runner.package_metadata(files["manifest.json"] + b" ", sums)
        missing = b"\n".join(line for line in sums.splitlines() if not line.endswith(b"load_unit.sv"))
        with self.assertRaisesRegex(ValueError, "missing from SHA256SUMS"):
            runner.package_metadata(files["manifest.json"], missing)

    def test_freeze_is_selective_exact_and_includes_headers_host_and_types(self):
        files, sums = self.package_fixture()
        manifest = runner.freeze_inputs(self.package, self.output)
        records = manifest["sources"]
        self.assertEqual(set(records), {"package/" + name for name in runner.SOURCES + runner.EXTRA} |
                         {"package/manifest.json", "package/SHA256SUMS", "generated/load_contract_types.svh"} |
                         set(runner.HOST_FILES))
        self.assertFalse((self.output / "inputs/package/unselected.bin").exists())
        self.assertEqual((self.output / "inputs/package/SHA256SUMS").read_bytes(), sums)
        self.assertEqual((self.output / "inputs/package/manifest.json").read_bytes(), files["manifest.json"])
        for record in records.values():
            frozen = Path(record["frozen"]).read_bytes()
            self.assertEqual(runner.digest(frozen), record["sha256"])
            self.assertEqual(len(frozen), record["size_bytes"])
            if record["path"]:
                self.assertEqual(frozen, Path(record["path"]).read_bytes())
        self.assertEqual(runner.changed_inputs(records), [])
        self.assertEqual(manifest["defines"], [])
        for name in (runner.EXECUTOR, "verification/ara_verify/dependency_patches.py",
                     "verification/patches/dependencies.json"):
            self.assertIn(name, records)
        self.assertIn("modeled translation and cache storage", manifest["scope"])
        self.assertIn("not the SoC NI map", manifest["configuration"]["unit_override"])
        self.assertEqual(manifest["configuration"]["expected"], dict(mmu=1, ni=1, load_entries=2, xlen=64))

    def test_bad_selected_source_is_not_frozen(self):
        self.package_fixture()
        self.put(self.package / runner.CORE / "load_unit.sv", b"changed bytes")
        with self.assertRaisesRegex(ValueError, "source checksum mismatch"):
            runner.freeze_inputs(self.package, self.output)
        self.assertFalse((self.output / "inputs/package" / runner.CORE / "load_unit.sv").exists())

    def test_linked_selected_source_rejected(self):
        self.package_fixture()
        source = self.package / runner.CORE / "load_unit.sv"
        source.unlink()
        source.symlink_to(self.package / runner.CORE / "lsu_bypass.sv")
        with self.assertRaisesRegex(ValueError, "symlink"):
            runner.freeze_inputs(self.package, self.output)

    def test_original_frozen_generated_and_baseline_drift_detected(self):
        self.package_fixture()
        records = runner.freeze_inputs(self.package, self.output)["sources"]
        for name, key in ((runner.RUNNER, "path"),
                          ("package/" + runner.CORE + "load_unit.sv", "frozen"),
                          ("generated/load_contract_types.svh", "frozen"),
                          ("package/SHA256SUMS", "path")):
            with self.subTest(name=name, key=key):
                path = Path(records[name][key])
                original = path.read_bytes()
                path.chmod(0o644)
                path.write_bytes(original + b"modified")
                self.assertTrue(any(name in error for error in runner.changed_inputs(records)))
                path.write_bytes(original)
                self.assertEqual(runner.changed_inputs(records), [])
        Path(records[runner.RUNNER]["frozen"]).unlink()
        self.assertTrue(any("unavailable" in error for error in runner.changed_inputs(records)))

    def test_freeze_cannot_overwrite_existing_bytes(self):
        target = self.root / "frozen"
        runner.freeze_bytes(target, b"first")
        with self.assertRaises(FileExistsError):
            runner.freeze_bytes(target, b"second")
        self.assertEqual(target.read_bytes(), b"first")

    def test_evidence_hash_describes_returned_bytes_and_detects_later_change(self):
        path = self.root / "load_trace.jsonl"
        self.put(path, b'{"cycle":1}\n')
        records = {}
        data = runner.read_evidence(path, records, "trace")
        self.put(path, b'{"cycle":2}\n')
        self.assertEqual(records["trace"]["sha256"], runner.digest(data))
        self.assertTrue(runner.changed_inputs(records))

    def test_compile_manifest_uses_only_frozen_inputs_and_fixed_bounds(self):
        self.package_fixture()
        manifest = runner.freeze_inputs(self.package, self.output)
        command = runner.compile_command(self.output, "/tools/vcs", manifest)
        self.assertEqual(command[command.index("-top") + 1], "load_unit_contract_tb")
        self.assertEqual(command[-len(runner.SOURCES)-1:],
                         [str(self.output / "inputs/package" / name) for name in runner.SOURCES] +
                         [str(self.output / "inputs" / runner.TB)])
        self.assertIn("+incdir+" + str(self.output / "inputs/package" / runner.COMMON / "include"), command)
        self.assertEqual((manifest["compile_timeout_s"], manifest["run_timeout_s"]), (180, 30))
        self.assertFalse(any("+define+SYNTHESIS" in arg or "ASSERTS_OFF" in arg for arg in command))

    def test_accelerator_define_comes_from_sealed_package(self):
        files, _ = self.package_fixture()
        name = runner.CORE + "include/ariane_pkg.sv"
        files[name] += b"`ifdef ARIANE_ACCELERATOR_PORT\n`endif\n"
        self.put(self.package / name, files[name])
        sums = "".join(f"{runner.digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
        self.put(self.package / "SHA256SUMS", sums)
        manifest = runner.freeze_inputs(self.package, self.output)
        self.assertEqual(manifest["defines"], ["+define+ARIANE_ACCELERATOR_PORT=1"])
        self.assertIn("+define+ARIANE_ACCELERATOR_PORT=1",
                      runner.compile_command(self.output, "/tools/vcs", manifest))


if __name__ == "__main__":
    unittest.main()
