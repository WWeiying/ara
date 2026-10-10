"""Offline adapter regressions. All mutations stay in /tmp or in memory."""
import copy
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import run_operand_native_651 as a


def new_row():
    return dict(kind=a.sealed.KIND, name=a.sealed.ROW, schema=a.sealed.SCHEMA,
        producer=str(a.RUNTIME), coverage_test=a.sealed.observed.NAME, status="PASS",
        passed_only=True, vdb_valid=True, reused=False, returncode=0, vdb="/gap65.vdb",
        vdb_files={"/gap65/data.xml": "b" * 64})


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="operand651-")
        self.addCleanup(self.temp.cleanup)
        self.listing = Path(self.temp.name) / "inputs.txt"
        self.design = Path("/compiled.vdb")
        self.old = [dict(name="ordinary%d" % i, kind="directed", vdb="/old%d.vdb" % i,
            status="PASS", passed_only=True, vdb_valid=True, vdb_rejection=None,
            reused=False, returncode=0, vdb_files={"/old%d/data.xml" % i: "a" * 64}) for i in range(650)]
        self.row = new_row()
        self.rows = self.old + [self.row]
        self.listing.write_text("\n".join([str(self.design), *[r["vdb"] for r in self.rows]]) + "\n")
        self.proof = Mock(files={"/replay/evidence": "c" * 64})
        self.proof.plan.return_value = dict(design_vdb=str(self.design), gap65_report_only=a.sealed.SCHEMA,
            baseline=str(a.BASELINE), source_selection=dict(baseline=str(a.BASELINE)), image={"simv": "hash"}, simv="simv")
        self.proof.collection.return_value = dict(status="PASS", passed=651, total=651,
            baseline_passed=650, new_passed=1, cross_image_reuse=False, excluded=[])
        self.proof.ledger.return_value = self.rows
        self.proof.pin.return_value = self.listing
        self.original = Mock(return_value=(self.old, "old-inputs", {"/old/pin": "d" * 64}))
        self.files = {"/replay/evidence": "c" * 64, "/old/pin": "d" * 64}
        self.receipt = {"/completion.json": "e" * 64, "/checkpoint.json": "f" * 64}
        p = patch.object(a.sealed.evidence, "Evidence", return_value=self.proof)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(a.sealed, "baseline_row")
        self.replay = p.start(); self.addCleanup(p.stop)

    def call(self):
        return a.admission_adapter(self.files, self.receipt, self.original)(a.RUNTIME, self.design)

    def test_exact651_and_ordinary650_are_unmodified(self):
        before = copy.deepcopy(self.rows)
        rows, listing, pins = self.call()
        self.assertEqual(rows, before)
        self.assertEqual(self.rows, before)
        self.assertNotIn("vdb_rejection", rows[-1])
        self.assertEqual(listing, self.listing)
        self.original.assert_called_once_with(a.BASELINE, self.design)
        self.replay.assert_called_once_with(self.proof, self.row, {"simv": "hash"}, "simv")
        self.proof.hashes.assert_called_once_with(self.row["vdb_files"])
        self.assertEqual(pins, self.files | self.receipt)

    def test_non651_delegation_returns_exact_legacy_result(self):
        result = a.admission_adapter(self.files, self.receipt, self.original)(a.BASELINE, self.design)
        self.assertIs(result, self.original.return_value)
        self.replay.assert_not_called()

    def test_original650_failure_is_never_suppressed(self):
        for error in (ValueError("ordinary PASS failure"), KeyError("vdb_rejection"), OSError("hash drift")):
            with self.subTest(error=error):
                self.original.side_effect = error
                with self.assertRaises(type(error)):
                    self.call()
                self.replay.assert_not_called()

    def test_wrong_versioned_identity_and_pass_types_rejected(self):
        changes = dict(kind="directed", name="other", schema="gap65-observed-v2", producer="/foreign",
            coverage_test="wrong", status="FAIL", passed_only=1, vdb_valid=1, reused=0,
            returncode=False, vdb_rejection="REJECTED")
        for key, value in changes.items():
            with self.subTest(key=key):
                original = copy.deepcopy(self.row)
                self.row[key] = value
                with self.assertRaises(ValueError): self.call()
                self.row.clear(); self.row.update(original)

    def test_650_omission_reordering_replacement_and_duplicate_rejected(self):
        variants = [self.rows[1:], list(reversed(self.old)) + [self.row],
            [dict(self.old[0], name="replacement")] + self.old[1:] + [self.row],
            self.old[:-1] + [self.row, self.row]]
        for rows in variants:
            with self.subTest(size=len(rows)):
                self.proof.ledger.return_value = rows
                with self.assertRaises(ValueError): self.call()

    def test_no_generic_missing_rejection_default_for_ordinary_row(self):
        ordinary = self.old[0]
        del ordinary["vdb_rejection"]
        # Exercise the REAL legacy loop; only filesystem readers are modeled.
        proof = Mock()
        proof.plan.return_value = dict(design_vdb=str(self.design), image={})
        proof.ledger.return_value = self.old
        listing = Mock()
        listing.read_text.return_value = "\n".join([str(self.design), *[r["vdb"] for r in self.old]])
        proof.pin.return_value = listing
        with patch.object(a.guard.csr_guard.legacy.coverage_evidence, "Evidence", return_value=proof):
            with self.assertRaises(KeyError):
                a.LEGACY_ADMISSION(a.BASELINE, self.design)

    def test_real_legacy650_predicates_and_every_vdb_hash_check_preserved(self):
        proof = Mock(files={})
        proof.plan.return_value = dict(design_vdb=str(self.design), image={})
        proof.ledger.return_value = self.old
        listing = Mock()
        listing.read_text.return_value = "\n".join([str(self.design), *[r["vdb"] for r in self.old]])
        proof.pin.return_value = listing
        with patch.object(a.guard.csr_guard.legacy.coverage_evidence, "Evidence", return_value=proof):
            a.LEGACY_ADMISSION(a.BASELINE, self.design)
            self.assertEqual(proof.hashes.call_count, 650)
            self.assertEqual([c.args[0] for c in proof.hashes.call_args_list], [r["vdb_files"] for r in self.old])
            for key, value in dict(status="FAIL", passed_only=1, vdb_valid=1,
                                   vdb_rejection="rejected", returncode=1).items():
                original = self.old[0][key]
                self.old[0][key] = value
                with self.subTest(key=key), self.assertRaises(ValueError):
                    a.LEGACY_ADMISSION(a.BASELINE, self.design)
                self.old[0][key] = original

    def test_design_ancestry_collection_and_membership_negatives(self):
        plan = self.proof.plan.return_value
        for key, value in dict(design_vdb="/foreign", gap65_report_only="wrong", baseline="/foreign",
                               source_selection={}).items():
            old = plan[key]; plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.call()
            plan[key] = old
        self.proof.collection.return_value["passed"] = 650
        with self.assertRaises(ValueError): self.call()
        self.proof.collection.return_value["passed"] = 651
        self.listing.write_text("/foreign\n")
        with self.assertRaises(ValueError): self.call()

    def test_sealed_replay_failure_and_unbound_receipt_cannot_pass(self):
        self.replay.side_effect = ValueError("full recovery replay failed")
        with self.assertRaisesRegex(ValueError, "replay failed"): self.call()
        self.replay.side_effect = None
        for path in list(self.files):
            original = self.files.pop(path)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "receipt omits"): self.call()
            self.files[path] = original
        self.receipt["/old/pin"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Contradictory"): self.call()


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="operand651-receipt-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        p = patch.object(a, "REPORTS", self.directory)
        p.start(); self.addCleanup(p.stop)
        self.complete = dict(status="PASS", schema=a.recovery.SCHEMA, source_runtime=str(a.RUNTIME),
            baseline=str(a.BASELINE), baseline_passed=650, aggregate_passed=651, simulations_started=False,
            tools_launched=False, original_evidence_modified=False, hash_stats=dict(unique_files=2, final_rehashed=2),
            files={str(a.HERE / n): a.FROZEN[n] for n in ("finalize_gap65_observed.py", "recover_gap65_report_only.py")})
        # Add every required identity/report anchor; don't bypass the gate logic.
        names = ("plan.json", "plan.sha256.json", "collection.json", "all-passed-outcomes.json",
                 "outcomes/tests.json", "combined-bits.json", "combined-inputs.txt", "combined-dve/summary.csv",
                 "combined-dve/inputs.txt", "combined-dve/selected_tests.txt", "combined-dve/waiver_status.json",
                 "observed-recovery/result.json", "observed-recovery/independent_audit.json", "rejected.json")
        self.complete["files"].update({str(a.RUNTIME / n): "a" * 64 for n in names})
        self.complete["files"].update({str(a.BASELINE / n): "b" * 64 for n in
            ("plan.json", "plan.sha256.json", "collection.json", "checkpoint.json", "all-passed-outcomes.json", "combined-dve/inputs.txt")})
        count = len(self.complete["files"])
        self.complete["hash_stats"] = dict(unique_files=count, final_rehashed=count)
        self.checkpoint = dict(status="PASS", phase="complete", coverage_status="COMPLETE", aggregate_passed=651,
            simulations_started=False, tools_launched=False, source_runtime=str(a.RUNTIME), completion_sha256=a.COMPLETION_SHA)
        self.proof = Mock()
        self.proof.pin.side_effect = lambda p, h: p
        self.proof.hashes.side_effect = lambda files: None
        def read(p):
            return copy.deepcopy(self.complete if p.name == "completion.json" else self.checkpoint)
        p = patch.object(a, "jread", side_effect=read)
        p.start(); self.addCleanup(p.stop)

    def test_completed_independent_receipt_full_hashes_required(self):
        result = a.completed_recovery(self.proof)
        self.assertEqual(result, self.complete["files"])
        self.proof.hashes.assert_called_once_with(result)
        self.assertEqual([c.args[1] for c in self.proof.pin.call_args_list], [a.COMPLETION_SHA, a.CHECKPOINT_SHA])

    def test_written_collection_is_not_completion(self):
        self.proof.pin.side_effect = FileNotFoundError("checkpoint missing")
        with self.assertRaises(FileNotFoundError): a.completed_recovery(self.proof)
        self.proof.hashes.assert_not_called()

    def test_incomplete_rehash_status_types_and_source_rejected(self):
        for doc, key, value in [(self.complete, "status", "RUNNING"), (self.complete, "schema", "foreign"),
            (self.complete, "source_runtime", "/foreign"), (self.complete, "baseline", "/foreign"),
            (self.complete, "aggregate_passed", "651"), (self.complete, "simulations_started", 0),
            (self.complete, "original_evidence_modified", True),
            (self.complete, "hash_stats", dict(unique_files=22, final_rehashed=21)),
            (self.checkpoint, "coverage_status", "RUNNING"), (self.checkpoint, "completion_sha256", "0" * 64),
            (self.checkpoint, "tools_launched", 0)]:
            old = doc[key]; doc[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): a.completed_recovery(self.proof)
            doc[key] = old

    def test_required_file_omission_and_full_hash_drift_rejected(self):
        old = self.complete["files"].pop(str(a.RUNTIME / "observed-recovery/result.json"))
        count = len(self.complete["files"])
        self.complete["hash_stats"] = dict(unique_files=count, final_rehashed=count)
        with self.assertRaises(ValueError): a.completed_recovery(self.proof)
        self.complete["files"][str(a.RUNTIME / "observed-recovery/result.json")] = old
        count += 1; self.complete["hash_stats"] = dict(unique_files=count, final_rehashed=count)
        self.proof.hashes.side_effect = ValueError("full receipt input drift")
        with self.assertRaisesRegex(ValueError, "input drift"): a.completed_recovery(self.proof)

    def test_rejection_symlink_and_wrong_root_hash_rejected(self):
        (self.directory / "rejected.json").write_text("{}")
        with self.assertRaises(ValueError): a.completed_recovery(self.proof)
        (self.directory / "rejected.json").unlink()
        self.proof.pin.side_effect = ValueError("root SHA differs")
        with self.assertRaises(ValueError): a.completed_recovery(self.proof)
        link = self.directory / "link"
        link.symlink_to(self.directory)
        with patch.object(a, "REPORTS", link), self.assertRaises(ValueError): a.completed_recovery(self.proof)


class BoundaryTests(unittest.TestCase):
    def test_importlib_hash_aliases_are_cached_and_restored(self):
        modules = (a.guard.csr, a.guard.csr_guard, a.guard.csr_guard.legacy.audit)
        before = [m.sha for m in modules]
        session = a.recovery.HashSession()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data"
            path.write_bytes(b"hash fixture")
            with a.offline_hashes(session):
                for mod in modules:
                    self.assertEqual(mod.sha(path), session.digest(path))
                self.assertEqual(len(session.entries), 1)
            self.assertEqual([m.sha for m in modules], before)
            session.reverify()
            self.assertEqual(session.reverified, 1)

    def test_scope_patch_restores_original_and_denies_every_process(self):
        original = a.guard.csr_guard.legacy.admitted_inputs
        normal = a.sealed.evidence.Evidence.baseline_row
        with a.offline_hashes(a.recovery.HashSession()):
            with self.assertRaises(RuntimeError): subprocess.Popen(["DVE_FORBIDDEN"])
            self.assertIs(a.guard.csr_guard.legacy.admitted_inputs, original)
        self.assertIs(a.guard.csr_guard.legacy.admitted_inputs, original)
        self.assertIs(a.sealed.evidence.Evidence.baseline_row, normal)

    def test_wrong651_tip_fails_before_any_hash_work(self):
        with self.assertRaises(ValueError): a.build_context(a.BASELINE)

    def test_run_adapter_gate_is_inside_unchanged_workflow_deadline(self):
        context = dict(test="fixture")
        loaded = ("out", "bundle", context, "receipt", b"receipt")
        def fake_run(*args):
            a.workflow.load_approval(*args)
            return "MOCK_NO_DVE"
        with patch.object(a.workflow, "load_approval", return_value=loaded) as loader, \
             patch.object(a.workflow, "run", side_effect=fake_run), \
             patch.object(a, "validate_adapter_context") as validate:
            self.assertEqual(a.main(["run", "/out", "--approval", "/receipt", "--approval-sha256", "hash"]), "MOCK_NO_DVE")
            validate.assert_called_once_with(context)
            loader.assert_called_once()

    def test_foreign_prepared_snapshot_rejected(self):
        with self.assertRaises(ValueError): a.validate_adapter_context({})

    def test_frozen_source_hashes_are_still_exact(self):
        for name, digest in a.FROZEN.items():
            with self.subTest(name=name): self.assertEqual(a.sha(a.HERE / name), digest)


if __name__ == "__main__":
    unittest.main()
