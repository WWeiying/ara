"""Offline fixtures only: no corpus qualification, receipts or EDA."""
from contextlib import ExitStack, nullcontext
import copy
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import old_image_waiver_admission as w


class SealTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="waiver685-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "bin").mkdir()
        self.file = self.root / "header.h"
        self.file.write_bytes(b"sealed header")

    def test_literal_dot_dot_and_equal_aliases_preserved(self):
        alias = self.root / "bin/../header.h"
        digest = w.sha_bytes(self.file.read_bytes())
        seal = w.FileSeal()
        seal.hashes({str(alias): digest, str(self.file): digest})
        self.assertEqual(len(seal.files), 2)
        self.assertEqual(len(seal.canonical), 1)
        self.assertEqual(seal.aliases[str(alias)][0], str(self.file))
        seal.finish()
        self.assertTrue(seal.finished)

    def test_old_helper_still_rejects_dot_dot(self):
        from gap74_native_hash_session import absolute
        with self.assertRaisesRegex(ValueError, "dot-dot"):
            absolute(self.root / "bin/../header.h")

    def test_conflicting_alias_and_content_mutation_reject(self):
        seal = w.FileSeal()
        seal.pin(self.file)
        with self.assertRaisesRegex(ValueError, "SHA differs"):
            seal.pin(self.root / "bin/../header.h", "0" * 64)
        self.file.write_bytes(b"other content")
        with self.assertRaises(ValueError):
            seal.finish()

    def test_symlink_dot_dot_uses_actual_resolution_not_normpath(self):
        other = self.root / "other"
        (other / "child").mkdir(parents=True)
        (other / "header.h").write_bytes(b"other header")
        (self.root / "link").symlink_to(other / "child", target_is_directory=True)
        alias = self.root / "link/../header.h"
        seal = w.FileSeal()
        seal.pin(alias)
        self.assertEqual(seal.aliases[str(alias)][0], str(other / "header.h"))
        (self.root / "link").unlink()
        (self.root / "link").symlink_to(self.root / "bin", target_is_directory=True)
        with self.assertRaises(ValueError):
            seal.finish()

    def test_tree_added_member_and_symlink_reject(self):
        seal = w.FileSeal()
        seal.tree(self.root / "bin")
        (self.root / "bin/extra").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "membership"):
            seal.finish()
        (self.root / "bin/link").symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, "symlink"):
            w.FileSeal().tree(self.root / "bin")

    def test_empty_invalid_hashes_and_finished_reuse_reject(self):
        seal = w.FileSeal()
        for entries in ({}, {str(self.file): True}, {str(self.file): "invalid"}):
            with self.assertRaises(ValueError):
                seal.hashes(entries)
        seal.pin(self.file)
        seal.finish()
        with self.assertRaisesRegex(ValueError, "finished"):
            seal.pin(self.file)


def comparison():
    return (dict(status="TERMINAL_TOHOST_MATCH", mismatch=None),
            dict(status="PASS", nr_lanes=4, vlen_bits=1024, compared_bytes=8, selected_index=None, first_mismatch=None,
                 stopped_at_spike_index=None, skipped_unknown_bytes=0, non_bit_exact_instructions=0,
                 incomplete_requests=[], unretired_requests=[], trapped_requests=[]))


class ComparisonTests(unittest.TestCase):
    def test_intact_and_unknown_prefix_nonbitexact_incomplete_negatives(self):
        scalar, vector = comparison()
        w.validate_comparisons(scalar, vector)
        for key, value in (("status", "FAIL"), ("nr_lanes", 8), ("vlen_bits", 512),
                           ("compared_bytes", 0), ("compared_bytes", True),
                           ("selected_index", 1), ("first_mismatch", {}),
                           ("stopped_at_spike_index", 9), ("skipped_unknown_bytes", 1),
                           ("non_bit_exact_instructions", 1), ("incomplete_requests", [1]),
                           ("unretired_requests", [1]), ("trapped_requests", [1])):
            with self.subTest(key=key):
                changed = dict(vector, **{key: value})
                with self.assertRaises(ValueError):
                    w.validate_comparisons(scalar, changed)
        with self.assertRaises(ValueError):
            w.validate_comparisons(dict(scalar, status="PREFIX_MATCH"), vector)

    def test_truncated_or_foreign_elf_rejects_without_process(self):
        for blob in (b"", b"\x7fELF\x02\x01", b"\0" * 64):
            with self.assertRaises(ValueError):
                w.elf_symbols(blob)


def fixture_elf():
    names = b"\0tohost\0g75_result\0"
    shoff, str_offset = 64, 64 + 4 * 64
    sym_offset = str_offset + len(names)
    blob = bytearray(sym_offset + 72)
    blob[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<HHIQQQIHHHHHH", blob, 16, 2, 243, 1, 0x80000000,
                     0, shoff, 0, 64, 56, 0, 64, 4, 0)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 64, 0, 3, 0, 0,
                     str_offset, len(names), 0, 0, 1, 0)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 128, 0, 2, 0, 0,
                     sym_offset, 72, 1, 0, 8, 24)
    struct.pack_into("<IIQQQQIIQQ", blob, shoff + 192, 0, 8, 3,
                     0x80001000, 0, 128, 0, 0, 8, 0)
    blob[str_offset:sym_offset] = names
    struct.pack_into("<IBBHQQ", blob, sym_offset + 24, 1, 0x11, 0, 3, 0x80001000, 8)
    struct.pack_into("<IBBHQQ", blob, sym_offset + 48, 8, 0x11, 0, 3, 0x80001040, 8)
    return bytes(blob)


class CaseTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="waiver685-case-")))
        self.name, self.directory = "vgap79_add16", self.root / "vgap79_add16"
        self.directory.mkdir()
        self.elf = self.directory / "input.elf"
        self.elf.write_bytes(fixture_elf())
        self.row = dict(status="PASS", directory=str(self.directory),
                        vdb=str(self.directory / "code.vdb"), checks=8, vector_bytes=8)
        self.plan = dict(simv="/exact/old/simv")
        source = w.ROOT / "apps/riscv-tests/isa/rv64uv/vgap79_add16.c"
        compiler = self.root / "compiler"
        compiler.write_bytes(b"fixture only, never executed")
        self.pins = {str(self.elf): w.sha_bytes(self.elf.read_bytes()), str(w.helpers.SPIKE): "a" * 64,
                     str(source): "b" * 64, str(compiler): "c" * 64}
        compile_args = [str(compiler), "--target=riscv64-unknown-elf", "-march=rv64gcv_zfh_zvfh",
            "-mabi=lp64d", "-DG75_NO_PRINT", "-D__SPIKE__", "-DVLEN=1024", "-DNR_LANES=4",
            "-fno-vectorize", "-fno-slp-vectorize", str(w.ROOT / "verification/tests/gap75_start.S"),
            str(source), "-o", str(self.elf)]
        rtl = [self.plan["simv"], "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
            "+PRELOAD=" + str(self.elf), "+TESTCASE=" + self.name, "+COMMIT_TOHOST=80001000",
            "+COMMIT_TRACE=" + str(self.directory / "commit_trace.csv"),
            "+VECTOR_TRACE=" + str(self.directory / "vector_trace.csv"), "-cm", "line+cond+fsm+tgl+branch",
            "-cm_dir", str(self.directory / "code.vdb"), "-cm_name", self.name]
        scalar, vector = comparison()
        self.scalar, self.vector = scalar, vector
        self.data = {self.directory / "audit.json": self.row,
            self.directory / "compile.command.json": dict(command=compile_args),
            self.directory / "rtl.command.json": dict(command=rtl, timeout_s=1800),
            self.directory / "spike.command.json": dict(command=[str(w.helpers.SPIKE),
                "--isa=rv64gcv_zfh_zvfh_zvl1024b", "--priv=msu", "--pmpregions=0", "-l", "--log-commits",
                str(self.elf)], timeout_s=120),
            self.directory / "scalar-comparison.json": scalar,
            self.directory / "vector-comparison.json": vector}
        (self.directory / "run.vcs.log").write_text("Core Test *** SUCCESS ***\n")
        (self.directory / "code.vdb/snps/coverage/db/testdata" / self.name).mkdir(parents=True)
        self.seal = SimpleNamespace(read=lambda p: copy.deepcopy(self.data[p]),
            pin=Mock(side_effect=lambda p, *args: p), tree=Mock(),
            files={str(self.elf): self.pins[str(self.elf)],
                   str(self.directory / "code.vdb/fixture-only.xml"): "d" * 64})
        self.commits = [SimpleNamespace(memory_accesses=[(0x80001000, 1), (0x80001040, 8), (0x80001044, 0)])]
        self.parse = self.stack.enter_context(patch.object(w.helpers, "parse_spike_commits", return_value=self.commits))
        self.scalar_hook = self.stack.enter_context(patch.object(w.helpers, "compare_commit_prefix", return_value=scalar))
        self.vector_hook = self.stack.enter_context(patch.object(w.helpers, "compare_vector_commits", return_value=vector))
        self.contract = self.stack.enter_context(patch.object(w.helpers, "check_contract_log", return_value=[]))

    def run_case(self):
        return w.audit_case(self.seal, self.directory, self.name, self.row, self.plan, self.pins)

    def test_positive_replays_both_comparisons_and_signature(self):
        row = self.run_case()
        self.assertEqual(row["checks"], 8)
        self.assertIn(str(self.elf), row["files"])
        self.assertTrue(row["vdb_files"])
        self.scalar_hook.assert_called_once()
        self.vector_hook.assert_called_once()
        self.seal.tree.assert_called_once_with(self.directory / "code.vdb")

    def test_command_image_and_spike_configuration_negatives(self):
        for filename in ("rtl.command.json", "spike.command.json", "compile.command.json"):
            p = self.directory / filename
            original = copy.deepcopy(self.data[p])
            self.data[p]["command"][0] = "/new-image-or-tool"
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                self.run_case()
            self.data[p] = original

    def test_signature_counts_contract_and_saved_comparison_negatives(self):
        original = copy.deepcopy(self.row)
        for key, value in (("status", "FAIL"), ("checks", True), ("checks", 9), ("vector_bytes", 9)):
            self.row.update(original)
            self.row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_case()
        self.row.update(original)
        self.commits[0].memory_accesses[-1] = (0x80001044, 1)
        with self.assertRaisesRegex(ValueError, "signature"):
            self.run_case()
        self.commits[0].memory_accesses[-1] = (0x80001044, 0)
        self.contract.return_value = ["failure"]
        with self.assertRaisesRegex(ValueError, "contract"):
            self.run_case()
        self.contract.return_value = []
        self.data[self.directory / "scalar-comparison.json"] = dict(self.scalar, extra="resealed")
        with self.assertRaisesRegex(ValueError, "Saved/recomputed"):
            self.run_case()

    def test_signature_storage_and_wrong_coverage_name_reject(self):
        blob = bytearray(self.elf.read_bytes())
        struct.pack_into("<Q", blob, len(blob) - 16, 0x80001004)
        with self.assertRaisesRegex(ValueError, "overlapping"):
            w.elf_symbols(blob)
        (self.directory / "code.vdb/snps/coverage/db/testdata" / self.name).rename(
            self.directory / "code.vdb/snps/coverage/db/testdata/wrong")
        with self.assertRaisesRegex(ValueError, "coverage test"):
            self.run_case()


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="waiver685-chain-")))
        self.stack.enter_context(patch.object(w, "OUT", self.root))
        self.stack.enter_context(patch.object(w.old, "CURRENT", self.root / "original654"))
        self.plan = dict(simv=str(self.root / "frozen/simv"), design_vdb=str(self.root / "design.vdb"),
                         image={str(self.root / "frozen/simv"): "a" * 64})
        self.prefix = [dict(name="old%d" % i, coverage_test="old%d" % i,
                            vdb=str(self.root / ("old%d.vdb" % i))) for i in range(654)]
        self.data = {w.old.CURRENT / "combined-bits.json": {"generation": 0}}
        parent, count = w.old.CURRENT, 654
        for gap, names, population in w.EXTENSIONS:
            d = self.root / ("gap%d-old-image-20261006-01" % gap)
            cases = {n: dict(status="FAIL" if n == "vgap76_red16" else "PASS") for n in names}
            state = dict(status="COMPLETE", phase="complete", coverage_status="COMPLETE",
                image=self.plan["simv"], live_rtl_reverted=False, baseline_passed=count,
                aggregate_passed=population, new_passed=population-count, cases=cases)
            if gap != 76:
                state["baseline_directory"] = str(parent)
            self.data[d / "status.json"] = state
            if gap == 76:
                self.data[d / "results/vgap76_red16/audit.json"] = cases["vgap76_red16"]
            self.data[d / "source-pins.json"] = {**self.plan["image"],
                str(parent / "combined-inputs.txt"): "b" * 64,
                str(parent / "combined-bits.json"): "c" * 64}
            self.data[d / "combined-bits.json"] = {"generation": gap}
            self.data[d / "raw-bitmap-delta.json"] = {"delta": gap}
            parent, count = d, population
        self.seal = SimpleNamespace(read=lambda p: copy.deepcopy(self.data[p]),
                                   hashes=Mock(), pin=Mock(side_effect=lambda p: p))
        def audit(seal, directory, name, row, plan, pins):
            return dict(name=name, coverage_test=name, vdb=str(directory / "code.vdb"))
        self.audit = self.stack.enter_context(patch.object(w, "audit_case", side_effect=audit))
        self.report = self.stack.enter_context(patch.object(w, "report"))
        self.collect = self.stack.enter_context(patch.object(w.bitmaps, "collect",
            side_effect=lambda p: {"generation": int(p.parent.name[3:5]), "input_hashes": {"x": "d" * 64}}))
        # Fixture bitmap equality, not real bitmap admission.
        for gap, _, _ in w.EXTENSIONS:
            self.data[self.root / ("gap%d-old-image-20261006-01" % gap) / "combined-bits.json"]["input_hashes"] = {"x": "d" * 64}
        self.stack.enter_context(patch.object(w.bitmaps, "delta", side_effect=lambda a, b: {"delta": b["generation"]}))

    def test_exact33_prefix_preserved_failure_excluded_every_report_checked(self):
        rows = w.extend33(self.seal, self.prefix, self.plan)
        self.assertEqual(rows[:654], self.prefix)
        self.assertEqual(len(rows), 687)
        self.assertNotIn("vgap76_red16", {r["name"] for r in rows})
        self.assertEqual(self.audit.call_count, 33)
        self.assertEqual([r["name"] for r in rows[685:]], ["vgap80_uniform16", "vgap80_uniform32"])
        self.assertEqual([call.args[2] for call in self.audit.call_args_list[-2:]],
                         ["vgap80_uniform16", "vgap80_uniform32"])
        self.assertEqual(self.report.call_count, 5)
        self.assertEqual(self.collect.call_count, 5)

    def test_missing_case_wrong_ancestor_image_completion_count_and_failure_reject(self):
        d = self.root / "gap77-old-image-20261006-01/status.json"
        original = copy.deepcopy(self.data[d])
        for key, value in (("status", "STOPPED"), ("coverage_status", "PENDING"),
                           ("image", "/repaired/simv"), ("baseline_directory", "/foreign"),
                           ("baseline_passed", True), ("aggregate_passed", 685),
                           ("new_passed", 3), ("cases", {}), ("live_rtl_reverted", True)):
            with self.subTest(key=key):
                self.data[d] = dict(original, **{key: value})
                with self.assertRaises(ValueError):
                    w.extend33(self.seal, self.prefix, self.plan)
        self.data[d] = original
        self.data[self.root / "gap76-old-image-20261006-01/status.json"]["cases"]["vgap76_red16"]["status"] = "PASS"
        with self.assertRaisesRegex(ValueError, "Known failure"):
            w.extend33(self.seal, self.prefix, self.plan)

    def test_missing_image_or_ancestor_pin_reject(self):
        p = self.root / "gap76-old-image-20261006-01/source-pins.json"
        original = dict(self.data[p])
        for key in original:
            with self.subTest(key=key):
                self.data[p] = dict(original)
                del self.data[p][key]
                with self.assertRaises(ValueError):
                    w.extend33(self.seal, self.prefix, self.plan)

    def test_runtime_audit_report_bitmap_failures_propagate(self):
        for hook in (self.audit, self.report, self.collect):
            with self.subTest(hook=hook):
                original = hook.side_effect
                hook.side_effect = ValueError("independent proof failed")
                with self.assertRaisesRegex(ValueError, "independent proof"):
                    w.extend33(self.seal, self.prefix, self.plan)
                hook.side_effect = original

    def test_gap80_pending_failed_missing_or_wrong_population_reject(self):
        p = self.root / "gap80-old-image-20261006-01/status.json"
        original = copy.deepcopy(self.data[p])
        variants = [dict(original, coverage_status="PENDING"),
                    dict(original, aggregate_passed=685), dict(original, new_passed=1),
                    dict(original, baseline_directory=str(w.old.CURRENT))]
        for name in w.EXTENSIONS[-1][1]:
            changed = copy.deepcopy(original)
            changed["cases"][name]["status"] = "FAIL"
            variants.append(changed)
            changed = copy.deepcopy(original)
            del changed["cases"][name]
            variants.append(changed)
        for index, changed in enumerate(variants):
            with self.subTest(index=index):
                self.data[p] = changed
                with self.assertRaises(ValueError):
                    w.extend33(self.seal, self.prefix, self.plan)

    def test_gap80_sourcepins_retained_and_missing_parent_pin_reject(self):
        p = self.root / "gap80-old-image-20261006-01/source-pins.json"
        original = dict(self.data[p])
        original[str(self.root / "compiler/bin/../header.h")] = "e" * 64
        self.data[p] = original
        w.extend33(self.seal, self.prefix, self.plan)
        self.assertIn(unittest.mock.call(original), self.seal.hashes.call_args_list)
        for key in tuple(original)[:3]:
            with self.subTest(key=key):
                self.data[p] = dict(original)
                del self.data[p][key]
                with self.assertRaises(ValueError):
                    w.extend33(self.seal, self.prefix, self.plan)

    def test_each_gap80_case_independent_audit_failure_rejects(self):
        audit = self.audit.side_effect
        for rejected in w.EXTENSIONS[-1][1]:
            def fail_case(*args):
                if args[2] == rejected:
                    raise ValueError("gap80 independent oracle failed")
                return audit(*args)
            self.audit.side_effect = fail_case
            with self.subTest(name=rejected), self.assertRaisesRegex(ValueError, "independent oracle"):
                w.extend33(self.seal, self.prefix, self.plan)


class BridgeTests(unittest.TestCase):
    def test_virtual_reads_exactly_scoped_and_hooks_restored(self):
        a = w.Adapter("a" * 64)
        a.rows = [dict(name="test")]
        a.plan = dict(design_vdb="design", image={})
        a.collection = dict(schema=w.SCHEMA)
        a.admission_sha256 = w.sha_bytes(w.encoded(dict(rows=a.rows, plan=a.plan, collection=a.collection)))
        guard = w.old.prior.guard.csr_guard
        reader, sha, latest, admission = guard.jread, guard.sha, guard.latest_corpus, guard.legacy.admitted_inputs
        with a.bridge():
            self.assertEqual(guard.jread(w.CURRENT / "collection.json"), a.collection)
            self.assertEqual(guard.sha(w.CURRENT / "collection.json"), w.sha_bytes(w.encoded(a.collection)))
            self.assertEqual(guard.legacy.admitted_inputs(w.CURRENT, Path("design"))[0], a.rows)
            with self.assertRaises(ValueError):
                guard.legacy.admitted_inputs(w.CURRENT, Path("foreign"))
        self.assertIs(guard.jread, reader)
        self.assertIs(guard.sha, sha)
        self.assertIs(guard.latest_corpus, latest)
        self.assertIs(guard.legacy.admitted_inputs, admission)
        a.rows.append(dict(name="mutated"))
        with self.assertRaisesRegex(ValueError, "admission changed"):
            with a.bridge():
                pass

    def test_bridge_before_admission_and_no_tools_fail_closed(self):
        with self.assertRaises(ValueError):
            with w.Adapter("a" * 64).bridge():
                pass
        import subprocess
        with w.old.no_tools(), self.assertRaisesRegex(RuntimeError, "forbids"):
            subprocess.Popen(["dve"])

    def test_capture_requires_qualified_same_context_and_never_issues_receipt(self):
        with self.assertRaisesRegex(ValueError, "same-invocation"):
            w.Adapter("a" * 64).capture_snapshot(w.CURRENT.parent / "not-created", {})


class LatestTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="waiver685-latest-")))
        self.base, self.tip = self.root / "original654", self.root / "gap80-old-image-20261006-01"
        self.stack.enter_context(patch.object(w, "OUT", self.root))
        self.stack.enter_context(patch.object(w, "CURRENT", self.tip))
        self.stack.enter_context(patch.object(w.old, "CURRENT", self.base))
        self.adapter = w.Adapter("a" * 64)
        self.adapter.plan = dict(simv="/old/simv", design_vdb="/old/design.vdb", image={"/old/simv": "b" * 64})
        self.adapter.legacy_latest = Mock(return_value=(self.base, {}))
        parent = self.base
        for gap, _, count in w.EXTENSIONS:
            d = self.root / ("gap%d-old-image-20261006-01" % gap)
            self.make(d, parent, count)
            parent = d

    def make(self, d, parent, count):
        (d / "combined-dve").mkdir(parents=True)
        (d / "combined-dve/summary.csv").write_text("raw\n")
        (d / "combined-inputs.txt").write_text("/old/design.vdb\n")
        (d / "status.json").write_text(json.dumps(dict(image="/old/simv", coverage_status="COMPLETE",
            status="COMPLETE", aggregate_passed=count, baseline_directory=str(parent))))

    def latest(self):
        return self.adapter.latest(Path("/old/design.vdb"), self.adapter.plan["image"], self.tip)

    def test_latest687_and_new_image_excluded(self):
        self.assertEqual(self.latest()[0], self.tip)
        d = self.root / "new-image-campaign"
        self.make(d, self.tip, 689)
        p = d / "status.json"
        s = json.loads(p.read_text())
        s["image"] = "/repaired/simv"
        p.write_text(json.dumps(s))
        self.assertEqual(self.latest()[0], self.tip)

    def test_old685_request_rejected_when_gap80_complete(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            self.adapter.latest(Path("/old/design.vdb"), self.adapter.plan["image"],
                                self.root / "gap79-old-image-20261006-01")

    def test_pending_successor_pass_does_not_change_fixed687(self):
        d = self.root / "pending-successor"
        d.mkdir()
        (d / "status.json").write_text(json.dumps(dict(image="/old/simv", status="RUNNING",
            coverage_status="PENDING", baseline_directory=str(self.tip), baseline_passed=687,
            new_passed=1, cases={"future-case": {"status": "PASS"}})))
        self.assertEqual(self.latest()[0], self.tip)

    def test_newer_old_tip_ambiguous_tips_and_broken_ancestry_reject(self):
        d = self.root / "successor"
        self.make(d, self.tip, 689)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.latest()
        p = d / "status.json"
        s = json.loads(p.read_text())
        s["baseline_directory"] = str(self.base)
        p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.latest()
        s["baseline_directory"] = str(self.root / "missing")
        p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError, "Broken"):
            self.latest()


class ContextTests(unittest.TestCase):
    def context(self, tests=687, points=201, operands=1144, observers=10):
        return dict(tests=tests, policy=dict(allowed_points=list(range(points))),
                    operand_targets=list(range(operands)), observers=list(range(observers)),
                    pins={"/fixture/evidence": "a" * 64}, design="/fixture/design", image={})

    def run_context(self, context):
        adapter = w.Adapter("a" * 64)
        adapter.rows = []
        adapter.seal = SimpleNamespace(finished=False, hashes=Mock(), finish=Mock())
        with patch.object(adapter, "bridge", return_value=nullcontext()), \
             patch.object(w.old.prior.guard, "build_context", return_value=context) as build, \
             patch.object(adapter, "latest", return_value=(w.CURRENT, context["pins"])):
            result = adapter.build_context()
        build.assert_called_once_with(w.CURRENT)
        return adapter, result

    def test_exact687_schema_and654_plus31_plus2_context(self):
        self.assertEqual(w.CURRENT.name, "gap80-old-image-20261006-01")
        self.assertEqual(w.SCHEMA, "old-image-waiver687-admission-v1")
        adapter, context = self.run_context(self.context())
        metadata = context["old_image_admission"]
        self.assertEqual(metadata["schema"], w.SCHEMA)
        self.assertEqual(metadata["baseline"], str(w.CURRENT))
        self.assertEqual(metadata["strict_prefix"], 654)
        self.assertEqual(metadata["independently_replayed_new_pass"], 31 + 2)
        self.assertFalse(metadata["native_qualified"])
        self.assertFalse(metadata["exclusions_applied"])
        adapter.seal.hashes.assert_called_once_with(context["pins"])
        adapter.seal.finish.assert_called_once()
        self.assertEqual(adapter.context_sha256, w.sha_bytes(w.encoded(context)))

    def test_old685_and_scope_drift_rejected(self):
        for change in (dict(tests=685), dict(points=200), dict(operands=1143), dict(observers=9)):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "scope changed"):
                self.run_context(self.context(**change))


if __name__ == "__main__":
    unittest.main()
