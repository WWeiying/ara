"""Offline-only adapter negatives; fixture success is NOT corpus qualification."""
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import signal
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import gap74_native_hash_session as hashes
import run_gap74_native_offline as w


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="gap74-adapter-")))
        self.design = self.root / "design.vdb"
        self.inputs = self.root / "inputs.txt"
        self.sha = "a" * 64
        self.oldpins = {"original650": "b" * 64}
        self.rows = [dict(name="ordinary%d" % i, vdb=str(self.root / ("test%d.vdb" % i)),
            files={"row%d" % i: self.sha}, vdb_files={"vdb%d" % i: self.sha},
            status="PASS", passed_only=True, vdb_valid=True, vdb_rejection=None,
            reused=False, returncode=0) for i in range(654)]
        self.rows[650].update(kind=w.prior.sealed.KIND, name=w.prior.sealed.ROW,
            schema=w.prior.sealed.SCHEMA, producer=str(w.prior.RUNTIME),
            coverage_test=w.prior.sealed.observed.NAME)
        self.rows[650].pop("vdb_rejection")
        for row, name in zip(self.rows[651:], w.CATALOG3):
            row["name"] = name.split(":")[1]
        self.ordinary = copy.deepcopy(self.rows[:650])
        self.ancestor = copy.deepcopy(self.rows[:651])
        self.events, self.delegated, self.proofs, self.timings, self.audits = [], [], [], [], {}
        self.original = Mock(side_effect=lambda *args: (
            self.events.append("ordinary650") or (self.ordinary, self.inputs, self.oldpins)))
        self.plan = dict(design_vdb=str(self.design), image={}, simv="simv")
        self.write_inputs()
        fixture = self
        class Proof:
            def __init__(self):
                fixture.proofs.append(self)
                self.files = dict(fixture.oldpins)
                self.pin = Mock(side_effect=lambda p, *args: fixture.inputs if
                    str(p).endswith("combined-dve/inputs.txt") else Path(p))
                self.plan = Mock(return_value=fixture.plan)
                self.hashes = Mock(side_effect=lambda entries: self.files.update(entries))
            def baseline_row(self, row, image, simv):
                fixture.delegated.append(row["name"])
        self.stack.enter_context(patch.object(w.prior.sealed.evidence, "Evidence", Proof))
        self.recovery = self.stack.enter_context(patch.object(w.prior, "completed_recovery",
            side_effect=lambda *args: self.events.append("recovery")))
        self.ancestor_check = self.stack.enter_context(patch.object(w.prior.recovery,
            "validate_completed_reports", side_effect=lambda *args: ({}, self.ancestor, {})))
        self.producers = self.stack.enter_context(patch.object(w.prior.recovery, "validate_producers"))
        self.deltas = self.stack.enter_context(patch.object(w.prior.recovery, "validate_deltas"))
        self.raw = self.stack.enter_context(patch.object(w, "full_raw_reports"))
        self.runner = SimpleNamespace(completed=Mock(side_effect=self.complete))
        self.admit = w.admission654(self.runner, self.sha, self.timings, None,
                                    self.audits, original=self.original)

    def write_inputs(self):
        self.inputs.write_text("\n".join([str(self.design), *[r["vdb"] for r in self.rows]]) + "\n")

    def complete(self, proof):
        self.events.append("strict654")
        for row in self.rows:
            proof.baseline_row(row, {}, "simv")
        return self.rows, {}

    def test_original650_first_every_row_replayed_files_and_vdbs_bound(self):
        rows, inputs, pins = self.admit(w.CURRENT, self.design)
        self.assertEqual(self.events, ["ordinary650", "recovery", "strict654"])
        self.original.assert_called_once_with(w.prior.BASELINE, self.design)
        self.assertEqual(len(self.delegated), 654)
        self.assertEqual(self.proofs[0].hashes.call_count, 1308)
        self.assertEqual(pins["original650"], self.oldpins["original650"])
        self.assertNotIn("vdb_rejection", rows[650])
        self.assertEqual(inputs, self.inputs)
        self.raw.assert_called_once()
        self.assertTrue(all(t["status"] == "complete" for t in self.timings))
        self.assertEqual(self.audits["ordinary650"]["completed"], 650)

    def test_ordinary650_failure_precedes_all_654_work(self):
        self.original.side_effect = ValueError("ordinary oracle failed")
        with self.assertRaisesRegex(ValueError, "ordinary oracle"):
            self.admit(w.CURRENT, self.design)
        self.runner.completed.assert_not_called()
        self.recovery.assert_not_called()
        self.assertEqual(self.timings[0]["status"], "failed")

    def test_noncurrent_delegation_unchanged_but_651_forbidden(self):
        self.admit(w.prior.BASELINE, self.design)
        self.original.assert_called_once_with(w.prior.BASELINE, self.design)
        with self.assertRaisesRegex(ValueError, "Stale651"):
            self.admit(w.prior.RUNTIME, self.design)
        self.runner.completed.assert_not_called()

    def test_changed_reordered_omitted_rowfiles_and_vdb_maps_rejected(self):
        original = copy.deepcopy(self.rows)
        mutations = (lambda: self.rows[0]["files"].update(extra=self.sha),
            lambda: self.rows[0]["vdb_files"].update(extra=self.sha),
            lambda: self.rows.reverse(), lambda: self.rows.pop(0),
            lambda: self.rows[0].update(name="replacement"))
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.rows = copy.deepcopy(original)
                mutation()
                with self.assertRaises(ValueError):
                    self.admit(w.CURRENT, self.design)

    def test_exact_gap65_identity_and_independent_types_required(self):
        for key, value in (("kind", "foreign"), ("producer", "/foreign"),
                           ("schema", "foreign"), ("coverage_test", "foreign"),
                           ("reused", True), ("returncode", False), ("vdb_rejection", "bad")):
            original = copy.deepcopy(self.rows[650])
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.rows[650][key] = value
                self.admit(w.CURRENT, self.design)
            self.rows[650] = original

    def test_new_three_names_vdb_uniqueness_and_types_required(self):
        for key, value in (("name", "foreign"), ("status", "FAIL"), ("passed_only", 1),
                           ("vdb_valid", 1), ("reused", 0), ("returncode", False),
                           ("vdb_rejection", "rejected"), ("vdb", self.rows[0]["vdb"]),
                           ("kind", w.prior.sealed.KIND)):
            original = copy.deepcopy(self.rows[651])
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.rows[651][key] = value
                self.admit(w.CURRENT, self.design)
            self.rows[651] = original
        self.rows[651].pop("vdb_rejection")
        with self.assertRaises(KeyError):
            self.admit(w.CURRENT, self.design)

    def test_full_recovery_receipt_and_654_runtime_failure_propagate(self):
        self.recovery.side_effect = ValueError("not COMPLETE/fullreceipt")
        with self.assertRaisesRegex(ValueError, "fullreceipt"):
            self.admit(w.CURRENT, self.design)
        self.runner.completed.assert_not_called()
        self.recovery.side_effect = None
        self.runner.completed.side_effect = ValueError("byte audit failed")
        with self.assertRaisesRegex(ValueError, "byte audit"):
            self.admit(w.CURRENT, self.design)

    def test_omitted_independent_replay_rejected(self):
        self.runner.completed.side_effect = lambda proof: (self.rows, {})
        with self.assertRaisesRegex(ValueError, "replay was omitted"):
            self.admit(w.CURRENT, self.design)

    def test_prior_success_diagnostics_cannot_substitute_for_new_replay(self):
        self.admit(w.CURRENT, self.design)
        self.runner.completed.side_effect = lambda proof: (self.rows, {})
        with self.assertRaisesRegex(ValueError, "replay was omitted"):
            self.admit(w.CURRENT, self.design)

    def test_compiled_design_and_ordered_inputs_required(self):
        self.plan["design_vdb"] = "/foreign"
        with self.assertRaisesRegex(ValueError, "compiled design"):
            self.admit(w.CURRENT, self.design)
        self.plan["design_vdb"] = str(self.design)
        self.inputs.write_text("\n".join(reversed(self.inputs.read_text().splitlines())) + "\n")
        with self.assertRaisesRegex(ValueError, "ordered native VDB"):
            self.admit(w.CURRENT, self.design)

    def test_original_pins_cannot_be_dropped_or_contradicted(self):
        def bad(proof):
            result = self.complete(proof)
            proof.files.clear()
            return result
        self.runner.completed.side_effect = bad
        with self.assertRaisesRegex(ValueError, "omits or contradicts"):
            self.admit(w.CURRENT, self.design)
        self.runner.completed.side_effect = self.complete
        self.rows[0]["files"]["original650"] = "c" * 64
        self.ordinary = copy.deepcopy(self.rows[:650])
        with self.assertRaisesRegex(ValueError, "omits or contradicts"):
            self.admit(w.CURRENT, self.design)

    def test_ancestor_producers_deltas_and_raw_report_never_skipped(self):
        self.ancestor[0]["files"]["extra"] = self.sha
        with self.assertRaisesRegex(ValueError, "completed651 prefix"):
            self.admit(w.CURRENT, self.design)
        self.ancestor = copy.deepcopy(self.rows[:651])
        for function in (self.producers, self.deltas, self.raw):
            with self.subTest(function=function):
                function.side_effect = ValueError("proof failure")
                with self.assertRaisesRegex(ValueError, "proof failure"):
                    self.admit(w.CURRENT, self.design)
                function.side_effect = None

    def test_repeated_row_oracles_are_not_cached(self):
        proof = w.prior.sealed.evidence.Evidence()
        with w.row_costs(self.audits):
            proof.baseline_row(self.rows[0], {}, "simv")
            proof.baseline_row(self.rows[0], {}, "simv")
        self.assertEqual(self.delegated, [self.rows[0]["name"]] * 2)
        self.assertEqual(self.audits["ordinary650"]["calls"], 2)


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="gap74-boundary-")))

    def runner(self):
        return w.bind_runner(hashlib.sha256(w.RUNNER.read_bytes()).hexdigest())

    def test_source_binding_requires_explicit_exact_sha(self):
        for sha in (None, "short", "g" * 64, "0" * 64):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                w.bind_runner(sha)
        self.assertEqual(self.runner().BASELINE, w.CURRENT)
        with patch.object(w, "CURRENT", self.root), self.assertRaisesRegex(ValueError, "identity"):
            self.runner()

    def test_real_original650_loop_keeps_legacy_checks(self):
        original = w.prior.LEGACY_ADMISSION
        evidence = w.prior.guard.csr_guard.legacy.coverage_evidence
        inputs = self.root / "inputs"
        rows = [dict(status="PASS", passed_only=True, vdb_valid=True,
            vdb_rejection=None, returncode=0, vdb="vdb%d" % i,
            vdb_files={"file%d" % i: "a" * 64}) for i in range(650)]
        inputs.write_text("\n".join([str(self.root), *[r["vdb"] for r in rows]]) + "\n")
        proof = Mock(files={"bound": "a" * 64})
        proof.plan.return_value = dict(design_vdb=str(self.root), image={})
        proof.ledger.return_value = rows
        proof.pin.return_value = inputs
        with patch.object(evidence, "Evidence", return_value=proof):
            self.assertEqual(len(original(w.prior.BASELINE, self.root)[0]), 650)
            self.assertEqual(proof.hashes.call_count, 650)
            for key, value in (("status", "FAIL"), ("passed_only", 1),
                               ("vdb_valid", 1), ("vdb_rejection", "bad"), ("returncode", 1)):
                old = rows[0][key]
                rows[0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    original(w.prior.BASELINE, self.root)
                rows[0][key] = old
            del rows[0]["vdb_rejection"]
            with self.assertRaises(KeyError):
                original(w.prior.BASELINE, self.root)
            rows[0]["vdb_rejection"] = None
            proof.hashes.side_effect = ValueError("VDB SHA differs")
            with self.assertRaisesRegex(ValueError, "VDB SHA"):
                original(w.prior.BASELINE, self.root)

    def test_full_three_hook_chain_restored_and_hashes_do_not_replace_oracle(self):
        runner = self.runner()
        evidence = w.prior.sealed.evidence
        row, precheck, validate = evidence.Evidence.baseline_row, evidence.precheck, evidence.validate
        with patch.object(runner.predecessor, "install", wraps=runner.predecessor.install) as install:
            with w.installed_hooks(runner):
                install.assert_called_once_with(dict(cases=[dict(name=n) for n in w.CATALOG3]))
                installed = evidence.Evidence.baseline_row
                raw = w.prior.recovery.RAW_SHA256
                with w.hash_reads_only(SimpleNamespace(digest=Mock())):
                    self.assertIs(evidence.Evidence.baseline_row, installed)
                    self.assertIs(w.prior.recovery.RAW_SHA256, raw)
                self.assertIs(evidence.Evidence.baseline_row, installed)
        self.assertIs(evidence.Evidence.baseline_row, row)
        self.assertIs(evidence.precheck, precheck)
        self.assertIs(evidence.validate, validate)

    def test_gap65_only_install_is_rejected_not_silently_accepted(self):
        runner = self.runner()
        row = w.prior.sealed.evidence.Evidence.baseline_row
        with patch.object(runner.predecessor, "install", side_effect=lambda spec:
                          runner.predecessor.gap65.install_hooks()), \
             self.assertRaisesRegex(ValueError, "clobbered"):
            with w.installed_hooks(runner):
                self.fail("gap65-only install was admitted")
        self.assertIs(w.prior.sealed.evidence.Evidence.baseline_row, row)

    def test_actual_gap69_hook_propagates_runtime_byte_failure(self):
        runner = self.runner()
        import run_gap69_vf_checked_extension as gap69
        name = w.CATALOG3[1].split(":")[1]
        vdb = self.root / "results" / name / "artifact/work/test.vdb"
        proof = w.prior.sealed.evidence.Evidence()
        with patch.object(w.prior.sealed, "_NORMAL_ROW", return_value=None), \
             patch.object(proof, "plan", return_value={}), \
             patch.object(gap69, "runtime_proof", side_effect=ValueError("independent VRF byte mismatch")) as audit:
            with w.installed_hooks(runner), self.assertRaisesRegex(ValueError, "VRF byte mismatch"):
                proof.baseline_row(dict(name=name, vdb=str(vdb)), {}, "simv")
        audit.assert_called_once()

    def test_offline_scope_refuses_processes(self):
        with w.no_tools():
            for call in (lambda: subprocess.Popen(["false"]), lambda: w.os.system("false"),
                         lambda: w.prior.sealed.full.batch.invoke("anything")):
                with self.assertRaisesRegex(RuntimeError, "forbids processes"):
                    call()

    def test_full_raw_membership_union_and_delta_are_recomputed(self):
        inputs = self.root / "inputs"
        inputs.write_text("design\ntest\n")
        bits = dict(input_hashes={"raw": "a" * 64}, metrics={})
        proof = Mock()
        proof.pin.return_value = inputs
        proof.read.side_effect = lambda path: {"old": True} if Path(path).name == "combined-bits.json" else {"delta": True}
        with patch.object(w.prior.sealed, "report_callback") as reports, \
             patch.object(w.prior.sealed.targeted.bitmaps, "collect", return_value=bits) as collect, \
             patch.object(w.prior.sealed.targeted.bitmaps, "delta", return_value={"delta": True}):
            w.full_raw_reports(proof, dict(design_vdb="design"), [dict(vdb="test")], bits)
            reports.assert_called_once()
            collect.assert_called_once_with(inputs)
            proof.hashes.assert_called_once_with(bits["input_hashes"])
            with self.assertRaisesRegex(ValueError, "union differs"):
                w.full_raw_reports(proof, dict(design_vdb="design"), [dict(vdb="test")], {})
            proof.read.side_effect = lambda path: {}
            with self.assertRaisesRegex(ValueError, "delta differs"):
                w.full_raw_reports(proof, dict(design_vdb="design"), [dict(vdb="test")], bits)
            inputs.write_text("test\ndesign\n")
            with self.assertRaisesRegex(ValueError, "membership differs"):
                w.full_raw_reports(proof, dict(design_vdb="design"), [dict(vdb="test")], bits)

    def test_frozen_sources_unchanged(self):
        for name, sha in w.PROTECTED.items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((w.HERE / name).read_bytes()).hexdigest(), sha)

    def test_merge_rejects_contradictory_evidence(self):
        with self.assertRaisesRegex(ValueError, "Contradictory"):
            w.merge_pins({"same": "a"}, {"same": "b"})


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.sha = "a" * 64
        self.required = w.merge_pins({str(w.HERE / n): h for n, h in w.PROTECTED.items()},
            {str(w.CURRENT / n): h for n, h in w.IDENTITY.items()},
            {str(w.RUNNER): self.sha,
             str(w.prior.REPORTS / "completion.json"): w.prior.COMPLETION_SHA,
             str(w.prior.REPORTS / "checkpoint.json"): w.prior.CHECKPOINT_SHA})
        self.context = dict(tests=654, baseline=str(w.CURRENT),
            baseline_collection_sha256=w.IDENTITY["collection.json"],
            policy=dict(allowed_points=list(range(201))), operand_targets=list(range(1144)),
            observers=list(range(10)), pins={})
        session = SimpleNamespace(digest=lambda p: self.required.get(str(p), "d" * 64),
                                  stats=lambda: {})
        with redirect_stderr(io.StringIO()), patch.object(w.prior.guard, "build_context", return_value=self.context), \
             patch.object(w.prior.guard, "verify_inputs") as verify:
            w.context654(object(), self.sha, [], session, {})
            verify.assert_called_once_with(self.context)

    def test_context_binds_all_protected_files_and_formal654_recovery_roots(self):
        w.validate_context(self.context, self.sha)
        for path, digest in self.required.items():
            self.assertEqual(self.context["pins"][path], digest)
        self.assertIn(str(w.HERE / "test_operand_native_651.py"), self.context["pins"])

    def test_missing_or_changed_any_required_context_pin_rejected(self):
        for path in self.required:
            for value in (None, "0" * 64):
                context = copy.deepcopy(self.context)
                if value is None:
                    del context["pins"][path]
                else:
                    context["pins"][path] = value
                with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                    w.validate_context(context, self.sha)

    def test_context_cannot_change_population_identity_or_claim_authority(self):
        for key, value in (("tests", 651), ("tests", 654.0), ("baseline", str(w.prior.RUNTIME)),
                           ("baseline_collection_sha256", "0" * 64)):
            context = copy.deepcopy(self.context)
            context[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                w.validate_context(context, self.sha)
        for key in ("operand_targets", "observers"):
            context = copy.deepcopy(self.context)
            context[key].pop()
            with self.subTest(key=key), self.assertRaises(ValueError):
                w.validate_context(context, self.sha)
        for key in self.context["gap74_offline"]:
            context = copy.deepcopy(self.context)
            record = context["gap74_offline"]
            record[key] = True if record[key] is False else "foreign"
            with self.subTest(key=key), self.assertRaises(ValueError):
                w.validate_context(context, self.sha)

    def test_context_cannot_overwrite_preexisting_contradictory_pin(self):
        context = copy.deepcopy(self.context)
        context["pins"][str(w.RUNNER)] = "0" * 64
        session = SimpleNamespace(digest=lambda p: self.required.get(str(p), "d" * 64),
                                  stats=lambda: {})
        with redirect_stderr(io.StringIO()), patch.object(w.prior.guard, "build_context", return_value=context), \
             self.assertRaisesRegex(ValueError, "Contradictory"):
            w.context654(object(), self.sha, [], session, {})


class PublicationTests(unittest.TestCase):
    """Only the hash helper is real; all corpus admission is an explicit fixture."""
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(redirect_stderr(io.StringIO()))
        self.stack.enter_context(redirect_stdout(io.StringIO()))
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="gap74-publish-")))
        self.current = self.root / "current654"
        self.current.mkdir()
        self.output = self.root / "capture"
        self.bundle = Path(str(self.output) + ".tools")
        self.evidence = Path(str(self.output) + ".offline")
        self.source = self.root / "immutable"
        self.source.write_bytes(b"original")
        self.sha = hashlib.sha256(b"original").hexdigest()
        self.session = hashes.NativeHashSession([self.output, self.bundle, self.evidence],
                                                immutable_files=[self.source])
        self.files = {str(self.source): self.sha}
        self.plan = dict(design_vdb=str(self.root), image={})
        self.context = dict(pins={}, tests=654)
        for target, name, value in ((w, "CURRENT", self.current),
            (w.prior.workflow.guard, "OUT", self.root),
            (w, "bind_runner", Mock(return_value=object())),
            (w.prior, "jread", Mock(return_value=self.plan)),
            (w, "read_seed", Mock(return_value=(self.files, self.plan, []))),
            (w, "make_session", Mock(return_value=(self.session, {}, []))),
            (w, "installed_hooks", Mock(side_effect=lambda *args: nullcontext())),
            (w, "hash_reads_only", Mock(side_effect=lambda *args: nullcontext())),
            (w, "context654", Mock(return_value=self.context)),
            (w.prior.guard.csr_guard, "latest_corpus", Mock(return_value=(None, {}))),
            (w.prior, "sha", Mock(return_value=self.sha))):
            self.stack.enter_context(patch.object(target, name, value))
        self.snapshot = self.stack.enter_context(patch.object(w.prior.workflow, "snapshot",
                                                            side_effect=self.write_snapshot))
    def write_snapshot(self, *args):
        self.bundle.mkdir()
        (self.bundle / "snapshot.json").write_text('{"fixture": true}\n')

    def run_prepare(self):
        return w.main(["prepare", str(self.output), "--closure91-sha256", self.sha])

    def test_cold_final_hash_failure_invalidates_snapshot_and_retains_failure(self):
        def corrupted_snapshot(*args):
            self.write_snapshot()
            stat = self.source.stat()
            identity = self.session.entries[str(self.source)][0]
            self.source.write_bytes(b"tampered")
            # Stat spoofing ensures SHA content, not metadata, is what rejects.
            self.stack.enter_context(patch.object(hashes, "file_identity", return_value=identity))
            self.stack.enter_context(patch.object(hashes.os, "fstat", return_value=stat))
        self.snapshot.side_effect = corrupted_snapshot
        with self.assertRaisesRegex(ValueError, "uncached content SHA differs"):
            self.run_prepare()
        self.assertFalse(self.output.exists())
        self.assertFalse((self.bundle / "snapshot.json").exists())
        self.assertTrue((self.bundle / "unqualified-snapshot.json").is_file())
        self.assertFalse((self.evidence / "result.json").exists())
        rejected = json.loads((self.evidence / "rejected.json").read_text())
        self.assertFalse(rejected["native1345_qualified"])
        self.assertEqual(rejected["stage_timings"][-1]["stage"], "final_uncached_all_content_and_membership")
        self.assertEqual(rejected["stage_timings"][-1]["status"], "failed")
        self.assertFalse(self.session.finished)

    def test_snapshot_writer_partial_failure_also_invalidates_manifest(self):
        def partial(*args):
            self.write_snapshot()
            raise ValueError("partial snapshot failed")
        self.snapshot.side_effect = partial
        with self.assertRaisesRegex(ValueError, "partial snapshot"):
            self.run_prepare()
        self.assertFalse((self.bundle / "snapshot.json").exists())
        self.assertTrue((self.bundle / "unqualified-snapshot.json").exists())

    def test_latest_tip_changes_after_cold_rehash_rejects(self):
        w.prior.guard.csr_guard.latest_corpus.side_effect = [(None, {}), ValueError("latest tip changed")]
        with self.assertRaisesRegex(ValueError, "latest tip"):
            self.run_prepare()
        self.assertTrue(self.session.finished)
        self.assertFalse((self.bundle / "snapshot.json").exists())
        self.assertFalse((self.evidence / "result.json").exists())

    def test_runner_changes_after_cold_rehash_rejects(self):
        w.prior.sha.return_value = "0" * 64
        with self.assertRaisesRegex(ValueError, "Runner changed"):
            self.run_prepare()
        self.assertTrue(self.session.finished)
        self.assertFalse((self.bundle / "snapshot.json").exists())

    def test_corpus_census_change_after_cold_rehash_rejects(self):
        w.prior.guard.csr_guard.latest_corpus.side_effect = [(None, {}), (None, {"new-tip": self.sha})]
        with self.assertRaisesRegex(ValueError, "Corpus census"):
            self.run_prepare()
        self.assertFalse((self.bundle / "snapshot.json").exists())

    def test_incomplete_tail_never_publishes_result(self):
        with patch.object(self.session, "reverify", return_value=None), \
             self.assertRaisesRegex(ValueError, "Final hash incomplete"):
            self.run_prepare()
        self.assertFalse((self.bundle / "snapshot.json").exists())
        self.assertFalse((self.evidence / "result.json").exists())

    def test_frozen_timeout_is_preserved_and_no_retry(self):
        with patch.object(self.session, "reverify", side_effect=TimeoutError("Frozen300s")), \
             self.assertRaisesRegex(TimeoutError, "Frozen300s"):
            self.run_prepare()
        self.assertFalse((self.bundle / "snapshot.json").exists())
        with self.assertRaisesRegex(ValueError, "Fresh output"):
            self.run_prepare()

    def test_publication_requires_finished_count_and_keeps_frozen300_bound(self):
        original_handler = signal.getsignal(signal.SIGALRM)
        with patch.object(w.signal, "alarm", wraps=signal.alarm) as alarm:
            result = self.run_prepare()
        self.assertEqual(alarm.call_args_list[0].args, (300,))
        self.assertEqual(alarm.call_args_list[-1].args, (0,))
        self.assertIs(signal.getsignal(signal.SIGALRM), original_handler)
        self.assertEqual(result["hash_stats"]["final_rehashed"], 1)
        self.assertEqual(result["status"], "PREPARED_CAPTURE654_NOT_RUN")
        self.assertFalse(result["native1345_qualified"])
        self.assertFalse(result["exclusions_applied"])
        self.assertFalse(result["tools_launched"])
        with self.assertRaisesRegex(ValueError, "Fresh output"):
            self.run_prepare()

    def test_old651_rejected_before_hash_work_or_output_creation(self):
        with self.assertRaisesRegex(ValueError, "stale651"):
            w.main(["prepare", str(self.output), "--baseline", str(w.prior.RUNTIME),
                    "--closure91-sha256", self.sha])
        self.assertFalse(self.evidence.exists())
        w.bind_runner.assert_not_called()
        w.make_session.assert_not_called()


if __name__ == "__main__":
    unittest.main()
