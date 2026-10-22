#!/usr/bin/env python3
"""P2 semantic replay regression. Synthetic capture only; no subprocesses."""
import argparse
import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

import test_operand as fixture
import operand_guard as guard
import operand_support as support
import operand_workflow as workflow

PROBES = []


class CaptureSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        context, cls.native, _ = fixture.fixture()
        cls.temporary = tempfile.TemporaryDirectory(prefix="p2-fixture-", dir=support.HERE)
        cls.base = Path(cls.temporary.name)
        cls.output, cls.bundle = cls.base / "capture", cls.base / "capture.tools"
        cls.output.mkdir()
        cls.bundle.mkdir()
        (cls.output / "DVEfiles").mkdir()
        vdb = cls.base / "fixture.vdb"
        (vdb / "snps/coverage/db/testdata/fixture_pass").mkdir(parents=True)
        cls.context = dict(context, output=str(cls.output), inputs=[context["design"], str(vdb)],
                           input_tree={str(vdb): support.tree(vdb)})
        cls.root = fixture.seal(cls.bundle, cls.context)
        receipt = dict(status="APPROVED_OPERAND_CAPTURE_SESSION_ONLY", authority="independent-parent-review",
            reviewer="SYNTHETIC UNIT FIXTURE ONLY", snapshot_sha256=cls.root,
            baseline_collection_sha256=context["baseline_collection_sha256"], allow_one_dve_session=True,
            allow_final_coverage_application=False, operand_points=1144, existing_points=94,
            csr_points=107, observers=10, dve_max_seconds=workflow.CAPTURE_DVE_MAX_SECONDS, native_capture_sha256=None)
        cls.write_json("independent-review.json", receipt)
        cls.write_json("execution.json", dict(dve_launch_count=1, returncode=0, timed_out=False,
                                             timeout_seconds=workflow.CAPTURE_DVE_MAX_SECONDS,
                                             elapsed_seconds=1, fixture_only=True))
        cls.before = dict(pins=cls.context["pins"], input_tree=cls.context["input_tree"], checked=True)
        cls.write_json("integrity-before.json", cls.before)
        cls.write_json("integrity-after.json", dict(pins=cls.context["pins"],
                       input_tree=cls.context["input_tree"], unchanged=True))
        cls.expected_test = str(vdb.with_suffix("") / "fixture_pass")
        (cls.output / "selected_tests.txt").write_text(cls.expected_test + "\n")
        for name in ("first.el", "second.el"):
            (cls.output / name).write_bytes(cls.native)
        for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
            (cls.output / name).write_bytes(b"")
        log = ["OQ_SESSION_ROOT " + cls.root, "OQ_CALLBACK raw"]
        for phase in ("before", "selected", "reset", "reloaded", "final"):
            lines = ["scope\tcoordinate\tmeta\tpath\texcluded\tproof"]
            for scope, keys in cls.context["session_keys"].items():
                if phase in ("before", "reloaded"):
                    log.append(f"OQ_INVENTORY {scope} full count={len(keys)}")
                active = phase in ("selected", "reloaded")
                wanted = set(cls.context["session_targets"][scope]) if active else set()
                log.append(f"OQ_GROUP {phase} {scope} {len(keys) - len(wanted)} excluded=0")
                for key in keys:
                    sid, vid = key.split(",")
                    meta, flag = f"Branch{sid}.{vid}", key in wanted
                    kind = "singleton" if flag else "exact_group_any_zero"
                    lines.append(f"{scope}\t{key}\t{meta}\tItem{sid}.{meta}\t{int(flag)}\t{kind}")
            (cls.output / ("states_" + phase + ".tsv")).write_text("\n".join(lines) + "\n")
            log.append("OQ_STATES " + phase)
            if phase == "selected":
                log += ["OQ_CALLBACK first", "OQ_FIRST_SHA " + support.sha(cls.output / "first.el")]
            elif phase == "reset":
                log += ["OQ_CALLBACK empty", "OQ_REVIEW_EMPTY"]
            elif phase == "reloaded":
                log += ["OQ_CALLBACK second"]
            elif phase == "final":
                log += ["OQ_CALLBACK final", "OQ_SESSION_DONE", "DVE_COVERAGE_EXPORT_DONE"]
        (cls.output / "DVEfiles/dve_gui.log").write_text("\n".join(log) + "\n")
        cls.states = support.state_proof(cls.output, cls.context, cls.root)
        cls.audit = dict(points=cls.states, count=len(cls.states))
        cls.write_json("state-audit.json", cls.audit)
        cls.certificate = cls.output / "fixture-certificate.json"
        cls.record = dict(status="NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL", operand_points=1144,
            baseline_collection_sha256=context["baseline_collection_sha256"], snapshot_sha256=cls.root,
            native_file=str(cls.output / "first.el"), native_sha256=support.sha(cls.output / "first.el"),
            independent_review_copy_sha256=support.sha(cls.output / "independent-review.json"))

    @classmethod
    def write_json(cls, name, value):
        (cls.output / name).write_text(json.dumps(value) + "\n")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def probe(self, name, artifact=None, value=None, rejection=None):
        original = (self.output / artifact).read_bytes() if artifact else None
        try:
            if artifact:
                if isinstance(value, str):
                    (self.output / artifact).write_text(value)
                else:
                    self.write_json(artifact, value)
            record = dict(self.record, files={str(p): support.sha(p) for p in self.output.rglob("*")
                          if p.is_file() and p != self.certificate})
            self.certificate.write_text(json.dumps(record))
            before = {str(p): support.sha(p) for p in self.base.rglob("*") if p.is_file()}
            directories = support.tree(self.base)
            error = None
            with patch.object(guard, "OUT", self.base), \
                 patch("subprocess.Popen", side_effect=AssertionError("NO SUBPROCESS IN SEMANTIC REPLAY")):
                try:
                    data = workflow.load_capture(self.certificate, support.sha(self.certificate), copy.deepcopy(self.context))
                    self.assertEqual(data, self.native)
                except ValueError as exc:
                    error = str(exc)
            self.assertEqual(before, {str(p): support.sha(p) for p in self.base.rglob("*") if p.is_file()})
            self.assertEqual(directories, support.tree(self.base))
            self.assertEqual(support.sha(self.bundle / "snapshot.json"), self.root)
            self.assertEqual(support.sha(self.output / "independent-review.json"), self.record["independent_review_copy_sha256"])
            if rejection:
                self.assertIsNotNone(error, name + " was incorrectly accepted")
                self.assertIn(rejection, error)
            else:
                self.assertIsNone(error)
            PROBES.append(dict(case=name, accepted=error is None, rejection=error, artifact_and_certificate_resealed=True,
                               snapshot_and_receipt_unchanged=True, replay_writes=0, subprocesses=0))
        finally:
            if artifact:
                (self.output / artifact).write_bytes(original)

    def test_intact_and_order_independent_positive(self):
        self.probe("intact_positive")
        self.probe("reordered_equivalent_state_audit", "state-audit.json",
                   dict(points=list(reversed(self.states)), count=len(self.states)))

    def test_three_independently_resealed_negatives(self):
        self.probe("wrong_selected_tests", "selected_tests.txt", "wrong_population\n", "selected PASS population")
        self.probe("empty_saved_state_audit", "state-audit.json", dict(points=[], count=0), "state audit count")
        self.probe("unchecked_before_integrity", "integrity-before.json", dict(checked=False), "before-integrity")

    def test_authorized_budget_and_capture_elapsed(self):
        self.assertEqual(workflow.run_bounds("capture"), (880, 900))
        self.assertEqual(workflow.run_bounds("report"), (880, 900))
        self.assertEqual(workflow.PREPARE_MAX_SECONDS, 300)
        execution = support.jread(self.output / "execution.json")
        self.probe("capture_600s_within_reviewed_cap", "execution.json", dict(execution, elapsed_seconds=600))
        self.probe("capture_elapsed_exceeds_cap", "execution.json", dict(execution, elapsed_seconds=884), "execution not qualified")
        self.probe("negative_capture_elapsed", "execution.json", dict(execution, elapsed_seconds=-1), "execution not qualified")
        self.probe("capture_timeout_exceeds_cap", "execution.json", dict(execution, timeout_seconds=1500), "execution not qualified")
        self.probe("capture_exceeds_actual_timeout", "execution.json",
                   dict(execution, timeout_seconds=600, elapsed_seconds=604), "execution not qualified")

    def test_early_refusal_and_receipt_budget_binding(self):
        with tempfile.TemporaryDirectory(dir=support.HERE) as temporary:
            base = Path(temporary)
            out, bundle = base / "run", base / "run.tools"
            bundle.mkdir()
            context = dict(self.context, output=str(out), pins={}, input_tree={}, image={})
            root = fixture.seal(bundle, context)
            receipt = support.jread(self.output / "independent-review.json")
            receipt["snapshot_sha256"] = root
            path = base / "review.json"
            path.write_text(json.dumps(receipt))
            with patch.object(guard, "OUT", base), patch.object(workflow, "verify_inputs"), \
                 patch.object(guard.csr_guard, "latest_corpus"), \
                 patch.object(workflow.time, "monotonic", side_effect=[0, 0, 41]), \
                 patch.object(workflow, "session", side_effect=AssertionError("must not launch")) as launch:
                with self.assertRaisesRegex(ValueError, "Prelaunch budget exceeded"):
                    workflow.run(out, path, support.sha(path))
                launch.assert_not_called()
            self.assertFalse((out / "capture-certificate.json").exists())
            (out / "rejection.json").unlink()
            for p in out.rglob("*"):
                if p.is_file():
                    p.unlink()
            for p in sorted(out.rglob("*"), reverse=True):
                p.rmdir()
            out.rmdir()
            for field, bad in (("dve_max_seconds", 1500), ("total_bound_seconds", 1620)):
                changed = dict(context, **{field: bad})
                receipt["snapshot_sha256"] = fixture.seal(bundle, changed)
                receipt["dve_max_seconds"] = changed["dve_max_seconds"]
                path.write_text(json.dumps(receipt))
                with patch.object(guard, "OUT", base):
                    with self.assertRaisesRegex(ValueError, "Prepared run budget differs"):
                        workflow.load_approval(out, path, support.sha(path))

    def test_prepare_alarm_without_admission_or_prepare(self):
        cli = support.module("operand_budget_cli_test", guard.COVERAGE / "run_reviewed_operand_dve_20261004.py")
        context = dict(self.context, retained_current_missing_count=1269, admission_elapsed_seconds=0)
        with patch.object(cli.guard, "build_context", return_value=context) as admit, \
             patch.object(cli.workflow, "snapshot", return_value=self.bundle) as prepare, \
             patch.object(cli.signal, "alarm") as alarm, contextlib.redirect_stdout(io.StringIO()):
            cli.main(["prepare", str(self.base / "not_created"), "--stage", "capture"])
        admit.assert_called_once()
        prepare.assert_called_once()
        self.assertEqual([call.args[0] for call in alarm.call_args_list], [300, 0])
        self.assertFalse((self.base / "not_created").exists())

    def test_population_proof_and_integrity_edges(self):
        self.probe("duplicate_selected_test", "selected_tests.txt", (self.expected_test + "\n") * 2, "selected PASS population")
        self.probe("missing_selected_test", "selected_tests.txt", "", "selected PASS population")
        for label, field, value in (("before_checked_integer", "checked", 1), ("before_pins_changed", "pins", {}),
                                    ("before_tree_changed", "input_tree", {})):
            self.probe(label, "integrity-before.json", dict(self.before, **{field: value}), "before-integrity")
        changed = copy.deepcopy(self.audit)
        changed["points"][0]["phases"]["before"]["excluded"] = 1
        self.probe("saved_state_contradiction", "state-audit.json", changed, "state audit proof")
        changed["points"][0]["phases"]["before"]["excluded"] = False
        self.probe("saved_state_boolean_not_integer", "state-audit.json", changed, "state audit proof")
        changed = copy.deepcopy(self.audit)
        changed["points"][-1] = changed["points"][0]
        self.probe("saved_state_duplicate_coordinate", "state-audit.json", changed, "state audit identity")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    support.require(output.parent == guard.OUT and not output.exists(), "Fresh integration out directory required")
    output.mkdir()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CaptureSemantics)
    for name in ("test_capture_required_artifact_pins", "test_approval_stage_and_bounds",
                 "test_native_dve_timeout_and_cleanup", "test_outer_run_approved_root_never_refreshes"):
        suite.addTest(fixture.Operand(name))
    started = time.monotonic()
    with patch("subprocess.Popen", side_effect=AssertionError("NO REAL SUBPROCESS IN P2 REGRESSION")):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(status="PASS" if result.wasSuccessful() else "FAIL", tests=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), elapsed_seconds=round(time.monotonic() - started, 3),
        semantic_probes=PROBES, focused_legacy_counters=fixture.COUNTS, real_subprocesses=0,
        limitation="Synthetic captures only; no native qualification, corpus admission, snapshot approval or EDA.")
    (output / "unit-results.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(not result.wasSuccessful())
