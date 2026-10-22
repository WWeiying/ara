import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fpga.check_sources import CRITICAL_FILES, check_sources, main


VMFPU = "rtl/ara/hardware/src/lane/vmfpu.sv"
FENCE = "rtl/cva6/core/acc_dispatcher.sv"
OPERANDS = "rtl/cva6/core/issue_read_operands.sv"
DISPATCHER = "rtl/ara/hardware/src/ara_dispatcher.sv"
HEADER = "rtl/ara/hardware/include/ara/ara.svh"


def digest(data):
    return hashlib.sha256(data).hexdigest()


class FpgaSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix=".fpga-sources-test-", dir=Path(__file__).resolve().parents[1])
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.export = self.root / "hardware/fpga/ara_dsa_vcu118"
        self.paths = {
            VMFPU: "hardware/src/lane/vmfpu.sv",
            FENCE: "hardware/deps/cva6/core/acc_dispatcher.sv",
            OPERANDS: "hardware/deps/cva6/core/issue_read_operands.sv",
            DISPATCHER: "hardware/src/ara_dispatcher.sv",
            HEADER: "hardware/include/ara/ara.svh",
        }
        self.before = {}
        for name, source in self.paths.items():
            content = f"// fixture {source}\n".encode()
            self.write(self.root / source, content)
            self.write(self.export / name, content)
            self.before[name] = digest(content)
        self.manifest = {
            "files": [name for name in self.paths if name != HEADER],
            "include_dirs": ["rtl/ara/hardware/include"],
            "revisions": {"ara": {"commit": "historical-ara"},
                          "cva6": {"commit": "historical-cva6"}},
            "source_hashes_before_integration": [
                {"file": name, "source_sha256": value} for name, value in self.before.items()],
        }
        self.write(self.export / "scripts/sources.tcl", b"# fixture compile list\n")
        self.seal()
        self.write(self.root / ".gitignore", b"hardware/deps/\nhardware/fpga/\nreview.json\n")
        self.init_repo(self.root / "hardware/deps/cva6")
        self.init_repo(self.root)

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def git(self, root, *args):
        return subprocess.check_output(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
             "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgSign=false",
             "-C", str(root), *args], stderr=subprocess.PIPE,
            env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull},
        )

    def init_repo(self, root):
        self.git(root, "init", "-q")
        self.git(root, "add", ".")
        self.git(root, "commit", "-qm", "fixture")

    def seal(self):
        self.write(self.export / "manifest.json", json.dumps(self.manifest).encode())
        rows = []
        for path in sorted(self.export.rglob("*")):
            if path.is_file() and path.name != "SHA256SUMS":
                rows.append(f"{digest(path.read_bytes())}  {path.relative_to(self.export).as_posix()}")
        self.write(self.export / "SHA256SUMS", ("\n".join(rows) + "\n").encode())

    def audit(self, **kwargs):
        return check_sources(self.root, self.export, **kwargs)

    def record(self, result, name):
        return next(row for row in result["source_correspondence"]["files"]
                    if row["export_path"] == name)

    def exception(self, name=DISPATCHER):
        return {"export_path": name, "source_path": self.paths[name],
                "source_sha256": digest((self.root / self.paths[name]).read_bytes()),
                "export_sha256": digest((self.export / name).read_bytes()),
                "reviewed_by": "fixture reviewer", "reason": "reviewed board-only rewrite"}

    def reviews(self, entries):
        path = self.root / "review.json"
        self.write(path, json.dumps({"schema_version": 1, "exceptions": entries}).encode())
        return path

    def test_exact_export_reports_hashes_mapping_and_git(self):
        result = self.audit()
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["export_integrity"]["status"], "valid")
        self.assertEqual(result["source_correspondence"]["status"], "exact")
        self.assertNotIn("PASS", json.dumps(result))
        for name in self.paths:
            record = self.record(result, name)
            self.assertEqual(record["source_path"], self.paths[name])
            self.assertEqual(record["source_sha256"], self.before[name])
            self.assertEqual(record["export_sha256"], self.before[name])
            self.assertEqual(record["source_git"]["status"], "clean")
        self.assertEqual(self.record(result, FENCE)["source_git"]["repository"], "hardware/deps/cva6")

    def test_integrity_does_not_imply_freshness_for_all_three_fixes(self):
        for name in CRITICAL_FILES:
            with (self.root / self.paths[name]).open("ab") as stream:
                stream.write(b"// latest fix absent from export\n")
        result = self.audit()
        self.assertEqual(result["export_integrity"]["status"], "valid")
        self.assertFalse(result["accepted"])
        self.assertFalse(result["critical_fixes"]["all_byte_equal"])
        self.assertEqual(set(result["critical_fixes"]["differing_or_unresolved"]), set(CRITICAL_FILES))
        self.assertEqual(len(result["critical_fixes"]["files"]), 3)
        for name in CRITICAL_FILES:
            record = self.record(result, name)
            self.assertEqual(record["status"], "differing")
            self.assertFalse(record["source_matches_manifest"])
            self.assertEqual(record["source_git"]["status"], "dirty")

    def test_tampered_export_fails_integrity_even_if_current_bytes_match(self):
        content = b"// changed in both places\n"
        self.write(self.export / VMFPU, content)
        self.write(self.root / self.paths[VMFPU], content)
        result = self.audit()
        self.assertEqual(result["source_correspondence"]["status"], "exact")
        self.assertEqual(result["export_integrity"]["status"], "invalid")
        self.assertFalse(result["accepted"])

    def test_known_adaptation_is_not_a_filename_allowlist(self):
        self.write(self.export / DISPATCHER, b"// board layout rewrite\n")
        self.seal()
        result = self.audit()
        self.assertFalse(result["accepted"])
        record = self.record(result, DISPATCHER)
        self.assertEqual(record["status"], "adapted_unreviewed")
        self.assertIn("patch_dispatcher_layout", record["known_adaptation"])
        self.write(self.root / self.paths[DISPATCHER], b"// new upstream semantics\n")
        self.assertEqual(self.record(self.audit(), DISPATCHER)["status"], "differing")

    def test_review_accepts_only_exact_source_and_export_pair(self):
        self.write(self.export / DISPATCHER, b"// reviewed board adaptation\n")
        self.seal()
        reviews = self.reviews([self.exception()])
        result = self.audit(exceptions_path=reviews)
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["source_correspondence"]["status"], "reviewed_adaptations")
        self.assertEqual(self.record(result, DISPATCHER)["status"], "adapted_reviewed")
        self.assertFalse(self.record(result, DISPATCHER)["byte_equal"])
        for which in ("source", "export"):
            path = self.root / self.paths[DISPATCHER] if which == "source" else self.export / DISPATCHER
            original = path.read_bytes()
            self.write(path, original + b"// drift\n")
            self.seal()
            result = self.audit(exceptions_path=reviews)
            self.assertFalse(result["accepted"], which)
            self.assertTrue(any("stale" in error for error in result["source_correspondence"]["errors"]))
            self.write(path, original)
            self.seal()

    def test_missing_source_cannot_be_waived_by_manifest_hash_or_exception(self):
        self.write(self.export / DISPATCHER, b"// adaptation\n")
        self.seal()
        reviews = self.reviews([self.exception()])
        (self.root / self.paths[DISPATCHER]).unlink()
        result = self.audit(exceptions_path=reviews)
        self.assertFalse(result["accepted"])
        record = self.record(result, DISPATCHER)
        self.assertEqual(record["status"], "missing_source")
        self.assertIsNone(record["source_sha256"])

    def test_missing_dependency_never_falls_back_to_same_basename(self):
        content = (self.root / self.paths[FENCE]).read_bytes()
        (self.root / self.paths[FENCE]).unlink()
        self.write(self.root / "hardware/deps/other/core/acc_dispatcher.sv", content)
        result = self.audit()
        self.assertEqual(self.record(result, FENCE)["status"], "missing_source")
        self.assertFalse(result["accepted"])

    def test_unmatched_namespace_is_explicit_even_when_basename_exists(self):
        name = "rtl/mystery/vmfpu.sv"
        self.write(self.export / name, (self.export / VMFPU).read_bytes())
        self.manifest["source_hashes_before_integration"].append(
            {"file": name, "source_sha256": self.before[VMFPU]})
        self.seal()
        result = self.audit()
        self.assertEqual(self.record(result, name)["status"], "unmatched")
        self.assertFalse(result["accepted"])

    def test_explicit_package_root_and_duplicate_root_ambiguity(self):
        custom = self.root / "checkouts/cva6"
        custom.parent.mkdir()
        (self.root / "hardware/deps/cva6").rename(custom)
        overrides = ["cva6=checkouts/cva6"]
        result = self.audit(root_overrides=overrides)
        self.assertTrue(result["accepted"], result)
        result = self.audit(root_overrides=overrides * 2)
        self.assertFalse(result["accepted"])
        self.assertEqual(self.record(result, FENCE)["status"], "ambiguous_mapping")

    def test_export_cannot_be_its_own_source(self):
        result = self.audit(root_overrides=["cva6=hardware/fpga/ara_dsa_vcu118/rtl/cva6"])
        self.assertFalse(result["accepted"])
        self.assertEqual(self.record(result, FENCE)["status"], "unreadable_source")

    def test_duplicate_manifest_mapping_is_rejected(self):
        self.manifest["source_hashes_before_integration"].append(
            {"file": VMFPU, "source_sha256": self.before[VMFPU]})
        self.seal()
        result = self.audit()
        self.assertFalse(result["accepted"])
        self.assertEqual(self.record(result, VMFPU)["status"], "ambiguous_mapping")

    def test_required_fixes_cannot_disappear_from_resealed_manifest(self):
        for name in CRITICAL_FILES:
            self.manifest["files"].remove(name)
            self.manifest["source_hashes_before_integration"] = [
                r for r in self.manifest["source_hashes_before_integration"] if r["file"] != name]
            (self.export / name).unlink()
        self.seal()
        result = self.audit()
        self.assertEqual(result["export_integrity"]["status"], "valid")
        self.assertFalse(result["accepted"])
        for name in CRITICAL_FILES:
            self.assertEqual(self.record(result, name)["status"], "missing_export")
        self.assertEqual(sum("required fix-bearing" in e for e in
                             result["source_correspondence"]["errors"]), 3)

    def test_headers_are_audited_not_just_compilation_files(self):
        self.write(self.root / self.paths[HEADER], b"// changed header\n")
        self.assertEqual(self.record(self.audit(), HEADER)["status"], "differing")

    def test_untracked_and_staged_source_state_are_reported(self):
        self.git(self.root, "rm", "--cached", self.paths[VMFPU])
        self.write(self.root / self.paths[DISPATCHER], b"// staged\n")
        self.git(self.root, "add", self.paths[DISPATCHER])
        result = self.audit()
        self.assertEqual(self.record(result, VMFPU)["source_git"]["status"], "untracked")
        record = self.record(result, DISPATCHER)
        self.assertEqual(record["source_git"]["porcelain"], "M ")
        self.assertEqual(record["source_git"]["status"], "dirty")
        repository = result["source_repositories"]["."]
        self.assertTrue(repository["dirty"])
        self.assertIn(self.paths[VMFPU], repository["untracked_files"])

    def test_unexported_dependency_git_changes_are_visible(self):
        self.write(self.root / "hardware/deps/cva6/core/new.sv", b"// new dependency unit\n")
        result = self.audit()
        self.assertIn("core/new.sv", result["source_repositories"]["hardware/deps/cva6"]["untracked_files"])

    def test_new_first_party_source_is_unexported_with_hash_and_git_state(self):
        source = "hardware/src/new_unit.sv"
        self.write(self.root / source, b"// new unit\n")
        result = self.audit()
        self.assertFalse(result["accepted"])
        record = result["source_correspondence"]["unexported_current_sources"][0]
        self.assertEqual(record["source_path"], source)
        self.assertEqual(record["status"], "unexported")
        self.assertEqual(record["source_sha256"], digest(b"// new unit\n"))
        self.assertEqual(record["source_git"]["status"], "untracked")

    def test_known_non_fpga_source_exclusion_is_visible(self):
        self.write(self.root / "hardware/src/ara_soc.sv", b"// simulation SoC\n")
        result = self.audit()
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["source_correspondence"]["unexported_current_sources"][0]["status"], "excluded")

    def test_board_top_uses_exact_exporter_mapping(self):
        name = "rtl/board/ara_dsa_vcu118.sv"
        source = "hardware/fpga/vcu118/rtl/ara_dsa_vcu118.sv"
        self.write(self.export / name, b"// board top\n")
        self.write(self.root / source, b"// board top\n")
        self.manifest["files"].append(name)
        self.seal()
        result = self.audit()
        self.assertTrue(result["accepted"], result)
        self.assertEqual(self.record(result, name)["source_path"], source)
        self.assertEqual(self.record(result, name)["source_git"]["status"], "ignored")

    def test_missing_checksum_and_unlisted_rtl_fail_integrity(self):
        name = "rtl/ara/hardware/include/extra.svh"
        self.write(self.export / name, b"// unsealed header\n")
        result = self.audit()
        self.assertEqual(result["export_integrity"]["status"], "invalid")
        self.assertIn(f"not covered by SHA256SUMS: {name}", result["export_integrity"]["errors"])

    def test_missing_export_file_and_missing_metadata_are_json_failures(self):
        for path in (self.export / HEADER, self.export / "SHA256SUMS", self.export / "manifest.json"):
            with self.subTest(path=path):
                content = path.read_bytes()
                path.unlink()
                result = self.audit()
                self.assertFalse(result["accepted"])
                self.assertEqual(result["export_integrity"]["status"], "invalid")
                self.write(path, content)

    def test_bad_checksums_and_paths_fail_closed(self):
        sums = self.export / "SHA256SUMS"
        original = sums.read_bytes()
        for row in (b"malformed\n", f"{'0' * 64}  ../outside\n".encode(),
                    original.splitlines(keepends=True)[0],
                    f"{'0' * 64}  /absolute\n".encode()):
            with self.subTest(row=row):
                sums.write_bytes(original + row)
                self.assertFalse(self.audit()["accepted"])

    def test_symlinks_in_source_and_export_fail_closed(self):
        for path in (self.root / self.paths[VMFPU], self.export / VMFPU):
            content = path.read_bytes()
            target = self.root / "target.sv"
            self.write(target, content)
            path.unlink()
            path.symlink_to(target)
            self.assertFalse(self.audit()["accepted"])
            path.unlink()
            self.write(path, content)

    def test_nonregular_export_cannot_block_hashing(self):
        path = self.export / VMFPU
        path.unlink()
        os.mkfifo(path)
        result = self.audit()
        self.assertFalse(result["accepted"])
        self.assertTrue(any("not a regular file" in e for e in result["export_integrity"]["errors"]))

    def test_case_collisions_and_duplicate_json_keys_fail_closed(self):
        self.write(self.export / VMFPU.upper(), b"// case alias\n")
        self.seal()
        self.assertFalse(self.audit()["accepted"])
        self.write(self.export / "manifest.json", b'{"files": [], "files": []}')
        result = self.audit()
        self.assertFalse(result["accepted"])
        self.assertTrue(any("duplicate JSON key" in e for e in result["export_integrity"]["errors"]))

    def test_malformed_or_unreviewed_exceptions_fail_closed(self):
        self.write(self.export / DISPATCHER, b"// adaptation\n")
        self.seal()
        for field in ("source_sha256", "export_sha256", "reviewed_by", "reason", "source_path"):
            entry = self.exception()
            entry.pop(field)
            with self.subTest(field=field):
                self.assertFalse(self.audit(exceptions_path=self.reviews([entry]))["accepted"])
        entry = self.exception()
        self.assertFalse(self.audit(exceptions_path=self.reviews([entry, entry]))["accepted"])

    def test_unknown_git_state_fails_closed(self):
        with patch("fpga.check_sources.subprocess.check_output", side_effect=FileNotFoundError("git")):
            result = self.audit()
        self.assertFalse(result["accepted"])
        self.assertEqual(self.record(result, VMFPU)["source_git"]["status"], "unavailable")

    def test_cli_json_exit_status_and_read_only_behavior(self):
        before = {p.relative_to(self.export): p.read_bytes()
                  for p in self.export.rglob("*") if p.is_file()}
        output = io.StringIO()
        args = ["--source-root", str(self.root), "--export-root", str(self.export)]
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(args), 0)
        self.assertTrue(json.loads(output.getvalue())["accepted"])
        self.write(self.root / self.paths[VMFPU], b"// new fix\n")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(args), 1)
        self.assertFalse(json.loads(output.getvalue())["accepted"])
        self.assertEqual(before, {p.relative_to(self.export): p.read_bytes()
                                 for p in self.export.rglob("*") if p.is_file()})

    def test_output_preserves_full_json_and_refuses_existing_result(self):
        output = self.root / "reports/audit.json"
        args = ["--source-root", str(self.root), "--export-root", str(self.export),
                "--output", str(output)]
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(main(args), 0)
        original = output.read_bytes()
        self.assertEqual(json.loads(original), json.loads(stdout.getvalue()))
        self.assertTrue(json.loads(original)["critical_fixes"]["all_byte_equal"])
        with contextlib.redirect_stderr(io.StringIO()), patch("fpga.check_sources.check_sources") as audit:
            self.assertEqual(main(args), 2)
            audit.assert_not_called()
        self.assertEqual(output.read_bytes(), original)

    def test_failed_audit_is_saved_and_keeps_failure_exit_code(self):
        self.write(self.root / self.paths[VMFPU], b"// stale export\n")
        output = self.root / "failed.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--source-root", str(self.root), "--output", str(output)]), 1)
        self.assertFalse(json.loads(output.read_bytes())["accepted"])

    def test_output_cannot_modify_export_or_current_source_trees(self):
        for output in (self.export / "audit.json", self.root / "hardware/src/report.json",
                       self.root / "hardware/deps/cva6/report.json"):
            with self.subTest(output=output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--source-root", str(self.root), "--output", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_output_rejects_symlink_alias_and_dangling_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.export, target_is_directory=True)
        dangling = self.root / "dangling.json"
        dangling.symlink_to(self.root / "not-created.json")
        for output in (alias / "report.json", dangling):
            with self.subTest(output=output), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--source-root", str(self.root), "--output", str(output)]), 2)
        self.assertFalse((self.export / "report.json").exists())
        self.assertFalse((self.root / "not-created.json").exists())

    def test_output_exclusive_creation_rejects_a_racing_writer(self):
        output = self.root / "raced.json"
        real_audit = check_sources
        def raced_audit(*args, **kwargs):
            result = real_audit(*args, **kwargs)
            output.write_bytes(b"earlier result")
            return result
        with patch("fpga.check_sources.check_sources", side_effect=raced_audit), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--source-root", str(self.root), "--output", str(output)]), 2)
        self.assertEqual(output.read_bytes(), b"earlier result")

    def test_output_exclusive_creation_rejects_a_racing_symlink(self):
        output = self.root / "raced.json"
        target = self.root / "untouched.json"
        real_audit = check_sources
        def raced_audit(*args, **kwargs):
            result = real_audit(*args, **kwargs)
            output.symlink_to(target)
            return result
        with patch("fpga.check_sources.check_sources", side_effect=raced_audit), \
                contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--source-root", str(self.root), "--output", str(output)]), 2)
        self.assertTrue(output.is_symlink())
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
