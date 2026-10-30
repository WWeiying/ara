"""Host-only contract/inventory tests. Fake RTL/tool files are never executed."""
import hashlib
import json
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest
from unittest import mock

import compose_canonical_standalone as composer
import run_canonical_standalone as runner
import prepare_canonical_standalone_fixture as layout

ROOT = runner.HERE.parents[2]


class CanonicalStandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "tree"
        for name in ("Bender.yml", "Bender.lock", "hardware/Makefile", "config/default.mk", "config/sram.mk"):
            self.write(self.root / name, "host fixture\n")
        self.include = self.root / "hardware/include"
        self.write(self.include / "shared_reader_types.svh", "// host inventory fixture\n")
        self.sources = []
        for kind in ("qbs", "akv"):
            path = self.root / f"hardware/src/vlsu/{kind}/{kind}_engine.sv"
            self.write(path, f"module {kind}_engine #(parameter type reader_req_t=logic,\n"
                       "parameter type reader_rsp_t=logic) (output reader_req_t reader_req_o,\n"
                       "input reader_rsp_t reader_rsp_i);\n" +
                       ("akv_unified_context i_unified_context ();\n" if kind == "akv" else "") + "endmodule\n")
            self.sources.append(path)
        for name in ("qbs/qbs_read_engine.sv", "qbs_akv_shared_reader.sv", "akv/akv_unified_context.sv",
                     "akv/akv_q_store.sv", "akv/akv_legacy_repacker.sv", "akv/akv_v2_context.sv"):
            path = self.root / "hardware/src/vlsu" / name
            self.write(path, "// Host inventory placeholder; not executable RTL.\n")
            self.sources.append(path)
        self.filelist = self.base / "sources.f"
        self.tool = self.base / "tools/bin/vcs"
        self.write(self.tool, "host tool identity fixture; never run\n")
        self.write(self.base / "tools/linux64/bin/vcs1", "host compiler identity fixture; never run\n")
        self.write_filelist("bender")

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def bench(self, kind):
        return ROOT / f"verification/{kind}/{kind}_engine_tb.sv"

    def write_filelist(self, style):
        if style == "bender":
            prefix = ["+define+TARGET_RTL", "+define+COMMON_CELLS_ASSERTS_OFF",
                      "+define+VLEN=1024", "+incdir+" + str(self.include), "+define+TARGET_RTL"]
        else:
            prefix = ["// Flattened manual QBS-style list", "+incdir+" + str(self.include), ""]
        self.filelist.write_text("\n".join(prefix + list(map(str, self.sources))) + "\n")

    def prepared(self, kind="qbs", name="prepared"):
        out = self.base / name
        vectors = ROOT / "verification/qbs/qbs_command_vectors.txt" if kind == "qbs" else None
        with mock.patch.object(runner.shutil, "which", return_value=str(self.tool)), \
             mock.patch.object(runner.subprocess, "Popen", side_effect=AssertionError("No EDA in host tests")):
            sha = runner.prepare(self.root, self.filelist, kind, self.bench(kind), vectors, out)
        return out, sha, json.loads((out / "manifest.json").read_text())

    def test_archived_headers_reproduce_accepted_wrappers(self):
        for kind in ("qbs", "akv"):
            entry, header = composer.contract(kind)
            wrapper = composer.compose(kind)
            self.assertNotIn("endmodule", header)
            self.assertEqual(hashlib.sha256(wrapper.encode()).hexdigest(), entry["origin_wrapper_sha256"])
            self.assertIn("owner_q ? observed_read_range_count_o : i_shared_reader.reader_rsp.range_count", wrapper)

    def test_header_identity_and_path_mutations(self):
        archive = self.base / "headers"
        shutil.copytree(composer.CONTRACTS, archive)
        path = archive / "qbs_engine_legacy_header.svh"
        path.write_text(path.read_text().replace("AxiDataWidth", "ChangedWidth", 1))
        with self.assertRaises(ValueError):
            composer.compose("qbs", archive)
        manifest = json.loads((archive / "manifest.json").read_text())
        manifest["headers"]["qbs"]["file"] = "../external.svh"
        (archive / "manifest.json").write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            composer.compose("qbs", archive)

    def test_original_tb_inverse_exact_and_mutation_rejected(self):
        for kind in ("qbs", "akv"):
            original = self.bench(kind).read_text()
            changed = composer.adapt_tb(original, kind)
            self.assertEqual(changed.replace("dut.i_engine.", "dut.").replace(
                f"  {kind}_engine_composed #(\n", f"  {kind}_engine #(\n", 1), original)
            with self.assertRaises(ValueError):
                composer.adapt_tb(original.replace("$fatal", "$display", 1), kind)

    def test_both_flat_filelist_styles_and_engines(self):
        for style in ("bender", "manual"):
            self.write_filelist(style)
            for kind in ("qbs", "akv"):
                with self.subTest(style=style, kind=kind):
                    actual = runner.source_graph(self.root, self.filelist, kind, self.bench(kind))
                    self.assertEqual(actual, self.sources)
                    out, sha, manifest = self.prepared(kind, style + kind)
                    runner.validate_inputs(manifest, out, sha)
                    self.assertEqual(manifest["source_root"], str(self.root))
                    old_hardware = str(ROOT / "hardware") + "/"
                    self.assertFalse(any(p.startswith(old_hardware) for p in manifest["input_pins"]))
                    self.assertFalse(any("snapshot-03" in p for p in manifest["input_pins"]))
                    self.assertFalse(any("canonical-standalone-inventory-" in p for p in manifest["input_pins"]))

    def test_old_or_dual_reader_engine_rejected(self):
        for kind in ("qbs", "akv"):
            path = self.root / f"hardware/src/vlsu/{kind}/{kind}_engine.sv"
            initial = path.read_text()
            for text in (initial.replace("reader_req_t", "old_req_t"),
                         initial + "\nqbs_read_engine #() private_reader ();\n"):
                path.write_text(text)
                with self.subTest(kind=kind), self.assertRaises(ValueError):
                    runner.source_graph(self.root, self.filelist, kind, self.bench(kind))
            path.write_text(initial)

    def test_nested_relative_and_assertion_disabled_filelists_rejected(self):
        original = self.filelist.read_text()
        for extra in ("-f /tmp/nested.f", "+incdir+relative", "+define+SYNTHESIS",
                      "+define+SYNTHESIS=1", str(self.sources[0])):
            self.filelist.write_text(original + extra + "\n")
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runner.source_graph(self.root, self.filelist, "qbs", self.bench("qbs"))

    def test_only_exact_inherited_uart_repeat_is_admitted(self):
        uart = self.root / runner.UART_REPEAT_PATH
        uart.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / runner.UART_REPEAT_PATH, uart)
        original = self.filelist.read_text()
        self.filelist.write_text(original + str(uart) + "\n" + str(uart) + "\n")
        sources = runner.source_graph(self.root, self.filelist, "qbs", self.bench("qbs"))
        self.assertEqual(sources[-2:], [uart, uart])
        self.assertEqual(runner.admitted_repeats(self.root, sources)[str(uart)]['count'], 2)
        self.filelist.write_text(self.filelist.read_text() + str(uart) + "\n")
        with self.assertRaises(ValueError):
            runner.source_graph(self.root, self.filelist, "qbs", self.bench("qbs"))
        self.filelist.write_text(original + str(uart) + "\n" + str(uart) + "\n")
        uart.write_text(uart.read_text() + "// unreviewed change\n")
        with self.assertRaises(ValueError):
            runner.source_graph(self.root, self.filelist, "qbs", self.bench("qbs"))

    def test_source_drift_rejected_before_compiler(self):
        out, sha, _ = self.prepared()
        self.sources[0].write_text(self.sources[0].read_text() + "// drift\n")
        with mock.patch.object(runner.subprocess, "Popen") as spawn, self.assertRaises(ValueError):
            runner.execute(out, sha)
        spawn.assert_not_called()

    def test_added_header_inventory_drift(self):
        for style in ("bender", "manual"):
            self.write_filelist(style)
            out, sha, manifest = self.prepared(name=style)
            addition = self.include / "new_header.svh"
            addition.write_text("// added after preparation\n")
            with self.subTest(style=style), self.assertRaises(ValueError):
                runner.validate_inputs(manifest, out, sha)
            addition.unlink()

    def test_header_symlink_retarget_same_bytes_rejected(self):
        one, two = self.base / "one.txt", self.base / "two.txt"
        one.write_text("same bytes\n"); two.write_text("same bytes\n")
        alias = self.include / "aliased.svh"
        alias.symlink_to(one)
        out, sha, manifest = self.prepared()
        alias.unlink(); alias.symlink_to(two)
        with self.assertRaises(ValueError):
            runner.validate_inputs(manifest, out, sha)

    def test_source_local_header_inventory(self):
        out, sha, manifest = self.prepared()
        local = self.sources[0].parent / "local_only.svh"
        local.write_text("// local lookup, not an explicit incdir\n")
        with self.assertRaises(ValueError):
            runner.validate_inputs(manifest, out, sha)

    def test_review_required_and_no_terminal_rerun(self):
        out, sha, _ = self.prepared()
        with mock.patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaises(ValueError):
                runner.execute(out, "0" * 64)
            for state in ("PASS", "FAIL", "TIMEOUT", "BUILDING", "RUNNING"):
                runner.save(out / "status.json", {"state": state})
                with self.subTest(state=state), self.assertRaises(ValueError):
                    runner.execute(out, sha)
            spawn.assert_not_called()

    def test_exact_case_and_fault_evidence(self):
        lines = [f"QBS end-to-end case {i} PASS profile=host-fixture" for i in range(36)]
        lines += [f"QBS {fault} atomic-fault PASS" for fault in ("validation", "MMU", "AXI", "PMA")]
        lines.append(runner.QBS_MARKER)
        good = "\n".join(lines)
        self.assertEqual(runner.check_log(good, "qbs", 0), runner.QBS_MARKER)
        for index in range(len(lines)):
            with self.subTest(missing=index), self.assertRaises(ValueError):
                runner.check_log("\n".join(lines[:index] + lines[index+1:]), "qbs", 0)
        for bad in (good + "\n" + lines[0], good + "\n" + lines[36], good + "\n" + runner.QBS_MARKER,
                    good + "\nFatal: failed", runner.QBS_MARKER):
            with self.assertRaises(ValueError):
                runner.check_log(bad, "qbs", 0)
        self.assertEqual(runner.check_log(runner.AKV_MARKER, "akv", 0), runner.AKV_MARKER)
        for bad, code in ((runner.AKV_MARKER, 1), (runner.AKV_MARKER + "\n" + runner.AKV_MARKER, 0),
                          (runner.AKV_MARKER + "\nError: failure", 0), ("", 0)):
            with self.assertRaises(ValueError):
                runner.check_log(bad, "akv", code)

    def test_timeout_kills_group_and_clears_child(self):
        child = mock.Mock(pid=12345)
        child.wait.side_effect = [subprocess.TimeoutExpired("host-fixture", 600), 0]
        state = {"state": "BUILDING", "child_pid": None}
        with mock.patch.object(runner.subprocess, "Popen", return_value=child), \
             mock.patch.object(runner.os, "killpg") as kill:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.run(["never-executed"], self.base, "timeout-fixture", state)
        kill.assert_called_once_with(12345, signal.SIGKILL)
        self.assertIsNone(state["child_pid"])
        self.assertFalse((self.base / "timeout-fixture.exit.json").exists())

    def test_fixture_maps_exact_seven_support_files(self):
        snapshot, output = Path("/frozen/snapshot"), Path("/fresh/layout")
        original = ["+define+VLEN=1024", "+incdir+/frozen/snapshot/support",
                    "+incdir+/frozen/snapshot/source/hardware/include",
                    "/frozen/snapshot/source/hardware/src/vlsu/akv/akv_engine.sv"]
        original += [str(snapshot / "support" / name) for name in layout.MAPPING]
        changed = layout.map_filelist("\n".join(original), snapshot, output).splitlines()
        self.assertEqual(len(layout.MAPPING), 7)
        self.assertEqual(changed[:4], ["+define+VLEN=1024", "+incdir+/fresh/layout/hardware/include",
                         "+incdir+/fresh/layout/hardware/include",
                         "/fresh/layout/hardware/src/vlsu/akv/akv_engine.sv"])
        self.assertEqual(changed[4:], [str(output / p) for p in layout.MAPPING.values()])
        with self.assertRaises(ValueError):
            layout.map_filelist("/unmapped/other.sv", snapshot, output)


if __name__ == "__main__":
    unittest.main()
