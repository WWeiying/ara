#!/usr/bin/env python3
"""Offline fixtures only; deny every subprocess except host Tcl/sha256sum."""
import copy
import csv
import hashlib
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
import operand_guard as g
import operand_workflow as w
import operand_runtime as rt
import operand_support as s
from operand_support import *

COUNTS = dict(parser_mutations=0, snapshot_mutations=0, callback_mutations=0, capture_pin_omissions=0, tcl_cases=0, DVE_launches=0)


def fixture():
    qualified, targets, csr_points, csr_blocks, path, pins = g.csr_guard.qualify_csr()
    policy = copy.deepcopy(jread(g.csr_guard.legacy.REVIEW / "policy.json"))
    policy["allowed_points"] += csr_points
    audit = jread(g.csr_guard.legacy.REVIEW / "audit.json")
    c = dict(policy=policy, observers=audit["observers"], csr_scope=qualified["validation"]["scope"],
             csr_checksum=["1371260681", "3035350189"], csr_targets=targets, csr_blocks=csr_blocks,
             csr_header="".join(path.read_text().splitlines(True)[:2]), csr_native_path=str(path),
             design=audit["identity"]["design_vdb"], tests=647, session_tests=1, stage="capture", baseline="TEST_ONLY",
             baseline_collection_sha256="b" * 64, native_capture_sha256=None, pins=pins, input_tree={}, input_membership={})
    d = g.csr_guard.legacy.audit.Design(Path(c["design"]))
    inv, _ = csr.exact_inventory(d.definition(c["csr_scope"], "branch"))
    c["csr_all_keys"] = [f"{sid},{vid}" for sid, vid in sorted(inv)]
    c["operand_targets"] = jread(g.REVIEW / "accepted-coordinates.json")["points"]
    retained = jread(g.REVIEW / "retained-and-prior.json")
    scopes, inventory, specs, masks = g.bind_operand(c, c["operand_targets"], retained)
    c.update(operand_scopes=scopes, operand_specs=specs, operand_keys=[f"{sid},{vid}" for sid, vid in sorted(inventory)],
             operand_prior16=retained["prior_reviewed"], operand_retained=retained["retained"],
             pilot18=jread(g.PILOT / "native-handoff.json")["points"],
             total_bound_seconds=w.run_bounds("capture")[1], dve_max_seconds=w.run_bounds("capture")[0])
    c["session_keys"], c["session_targets"] = g.session_population(c, "capture")
    pilot = {point_key(p): p for p in c["pilot18"]}
    native = []
    for scope in scopes:
        native += ['CHECKSUM: "1532764271 1417162425"\n', 'INSTANCE: ' + scope + '\n']
        for p in c["operand_targets"]:
            if p["scope"] != scope:
                continue
            sid, vid = csr.point_id(p["point"])
            if point_key(p) in pilot:
                directive = pilot[point_key(p)]["full_annotation_directive_block"].splitlines()[1]
            else:
                directive = f'Branch {sid} "{p["spec_checksum"]}" "{specs[str(sid)]["expression"]}" ({vid}) "SYNTHETIC_NOT_NATIVE_{sid}_{vid}"'
            native.append('ANNOTATION: "' + ANNOTATION + '"\n' + directive + '\n')
    return c, "".join(native).encode(), masks


def report_fixture(c, operand):
    c = copy.deepcopy(c)
    c["stage"] = "report"
    c["dve_max_seconds"], c["total_bound_seconds"] = w.run_bounds("report")
    c["policy"] = compose_policy(c, operand)
    c["operand_native_blocks"] = {}
    for (scope, point), b in validate_operand(operand, c).items():
        c["operand_native_blocks"].setdefault(scope, {})[point] = b["raw"]
    c["session_keys"], c["session_targets"] = g.session_population(c, "report")
    c["session_keys"] = dict(sorted(c["session_keys"].items()))
    old = dict(c["policy"], allowed_points=c["policy"]["allowed_points"][:94])
    native = g.csr_guard.legacy.native_points(old).encode() + Path(c["csr_native_path"]).read_bytes() + operand
    observers = "".join('CHECKSUM: "' + " ".join(p["checksum"]) + '"\nANNOTATION: "observer"\nINSTANCE: ' + p["scope"] + '\n' for p in c["observers"]).encode()
    return c, native, observers


def seal(bundle, c):
    (bundle / "context.json").write_text(json.dumps(c))
    (bundle / "snapshot.json").write_text(json.dumps({str(p.relative_to(bundle)): sha(p) for p in bundle.rglob("*") if p.is_file() and p.name != "snapshot.json"}))
    return sha(bundle / "snapshot.json")


class Operand(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c, cls.native, cls.masks = fixture()
        cls.report, cls.union, cls.observers = report_fixture(cls.c, cls.native)

    def test_exact_population_and_composition(self):
        self.assertEqual(len(validate_operand(self.native, self.c)), 1144)
        self.assertEqual(len(validate_composed(self.union, self.report, g.csr_guard.legacy.audit, False)), 1345)
        self.assertEqual(len(validate_composed(self.union + self.observers, self.report, g.csr_guard.legacy.audit, True)), 1355)
        self.assertEqual(sum(map(len, self.c["session_keys"].values())), 3636)
        self.assertEqual(sum(map(len, self.report["session_keys"].values())), 4262)
        self.assertEqual(sum(map(len, self.report["session_targets"].values())), 1267)
        self.assertEqual(len(self.c["operand_retained"]), 1269)

    def test_all1144_record_corruption_and_missing(self):
        records = blocks(self.native)
        canonical = "".join(r["raw"] for r in records.values()).encode()
        for p in self.c["operand_targets"]:
            k = point_key(p)
            block = records[k]["raw"].encode()
            with self.assertRaises(ValueError):
                validate_operand(canonical.replace(block, b"", 1), self.c)
            with self.assertRaises(ValueError):
                equal_records(records, validate_operand(canonical.replace(block, block[:-2] + b'_MUTATION"\n', 1), self.c))
            COUNTS["parser_mutations"] += 2

    def test_semantic_order_and_opaque_syntax(self):
        reverse = "".join(row["raw"] for row in reversed(list(blocks(self.native).values()))).encode()
        pair(self.native, reverse, self.c)
        for bad in (self.native + b'// opaque\n', self.native + b'ATTRIBUTES: filter\n', self.native + self.native,
                    self.native.replace(b'gen_lanes[0]', b'gen_lanes[9]'), self.native.replace(b'1417162425', b'1417162424'),
                    self.native.replace(b'(4)', b'(0-4)', 1), self.native.replace(b'Branch ', b'Module ', 1),
                    self.native.replace(b'Operand parameter native discovery', b'arbitrary approval', 1)):
            with self.assertRaises(ValueError):
                validate_operand(bad, self.c)
            COUNTS["parser_mutations"] += 1
        with self.assertRaises(ValueError):
            validate_composed(self.union + self.observers + self.observers, self.report, g.csr_guard.legacy.audit, True)

    def test_union_operand_signature_cannot_float(self):
        p = self.c["operand_targets"][-1]
        raw = blocks(self.native)[point_key(p)]["block"].encode()
        with self.assertRaises(ValueError):
            validate_composed((self.union + self.observers).replace(raw, raw[:-2] + b'_BAD"\n'), self.report, g.csr_guard.legacy.audit, True)
        bad = copy.deepcopy(self.c)
        bad["policy"]["allowed_points"][0].update(scope=p["scope"], point=p["point"])
        with self.assertRaises(ValueError):
            compose_policy(bad, self.native)

    def test_raw36_hit_width_duplicate_and_mapping(self):
        raw = '<root>' + ''.join(f'<instance_data name="{scope}" value="' + '0' * 101 + '"/>' for scope in self.masks) + '</root>'
        self.assertEqual(len(scan_raw(raw.encode(), self.masks, self.masks)), 36)
        p = self.c["operand_targets"][0]
        n = ["0"] * 101
        n[p["raw_index"]] = "1"
        bad = raw.replace(f'name="{p["scope"]}" value="' + "0" * 101, f'name="{p["scope"]}" value="' + "".join(n))
        for text in (bad, raw.replace("0" * 101, "0" * 100, 1), raw.replace('</root>', raw[len('<root>'):])):
            with self.assertRaises(ValueError):
                scan_raw(text.encode(), self.masks, self.masks)
        inv, width = csr.exact_inventory(ET.fromstring('<branch_def><branch_spec id="8"><branch_vector id="42" vector="10"/><branch_vector id="9" vector="01"/></branch_spec></branch_def>'))
        self.assertEqual((width, inv[8, 42]["raw_index"], inv[8, 9]["raw_index"]), (2, 1, 0))

    def test_approval_stage_and_bounds(self):
        good = dict(status="APPROVED_OPERAND_CAPTURE_SESSION_ONLY", authority="independent-parent-review", reviewer="unit-only",
                    snapshot_sha256="a" * 64, baseline_collection_sha256="b" * 64, allow_one_dve_session=True,
                    allow_final_coverage_application=False, operand_points=1144, existing_points=94, csr_points=107,
                    observers=10, dve_max_seconds=w.CAPTURE_DVE_MAX_SECONDS, native_capture_sha256=None)
        approval(good, "a" * 64, self.c)
        for name, value in (("operand_points", 18), ("dve_max_seconds", 900), ("snapshot_sha256", "c" * 64),
                            ("allow_final_coverage_application", True), ("status", "APPROVED_OPERAND_REPORT_SESSION_ONLY")):
            with self.assertRaises(ValueError):
                approval(dict(good, **{name: value}), "a" * 64, self.c)
        with self.assertRaises(ValueError):
            w.load_capture(g.PILOT / "audit.json", sha(g.PILOT / "audit.json"), self.c)
        self.assertEqual(g.csr_guard.latest_tip({"645": {"parent": None}, "647": {"parent": "645"}, "648": {"parent": "647"}}), "648")

    def test_snapshot_and_callback_pin_mutations(self):
        for stage in ("raw", "first", "empty", "second", "final"):
            for mode in ("content", "manifest", "content_and_manifest", "extra", "directory", "missing", "symlink"):
                with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                    bundle = Path(tmp)
                    (bundle / "hook.tcl").write_text("reviewed")
                    c = dict(self.c, output=str(bundle))
                    root = seal(bundle, c)
                    if mode in ("content", "content_and_manifest"):
                        (bundle / "hook.tcl").write_text("unreviewed")
                    if mode == "manifest":
                        (bundle / "snapshot.json").write_text((bundle / "snapshot.json").read_text() + "\n")
                    elif mode == "content_and_manifest":
                        seal(bundle, c)
                    elif mode == "extra":
                        (bundle / "extra").write_text("x")
                    elif mode == "directory":
                        (bundle / "extra").mkdir()
                    elif mode == "missing":
                        (bundle / "hook.tcl").unlink()
                    elif mode == "symlink":
                        (bundle / "hook.tcl").unlink()
                        (bundle / "hook.tcl").symlink_to(HERE / "dve_operand.tcl")
                    with patch.object(rt, "HERE", bundle), patch.object(rt, "callback", side_effect=AssertionError("must reject before callback")):
                        with self.assertRaises(ValueError):
                            rt.main(["--snapshot-sha256", root, "--output", str(bundle), "--session", stage])
                    COUNTS["snapshot_mutations"] += 1
                    COUNTS["callback_mutations"] += 1

    def test_capture_required_artifact_pins(self):
        required = {"first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el",
                    "execution.json", "independent-review.json", "integrity-before.json", "integrity-after.json",
                    "selected_tests.txt", "DVEfiles/dve_gui.log", "state-audit.json"}
        required.update("states_" + phase + ".tsv" for phase in ("before", "selected", "reset", "reloaded", "final"))
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root = Path(tmp)
            record = dict(status="NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL", operand_points=1144,
                          baseline_collection_sha256=self.c["baseline_collection_sha256"], native_file=str(root / "first.el"))
            certificate = root / "certificate.json"
            for omitted in required:
                record["files"] = {str(root / name): "a" * 64 for name in required if name != omitted}
                certificate.write_text(json.dumps(record))
                with patch.object(g, "OUT", root.parent), patch.object(w, "verify_snapshot", side_effect=AssertionError("reject omitted pins first")):
                    with self.assertRaisesRegex(ValueError, "omits required artifact pins"):
                        w.load_capture(certificate, sha(certificate), self.c)
                COUNTS["capture_pin_omissions"] += 1

    def test_native_dve_timeout_and_cleanup(self):
        process = Mock(pid=987654321)
        process.wait.side_effect = [subprocess.TimeoutExpired("MOCK_NO_DVE", 1), 0]
        with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(w, "verify_snapshot", return_value=self.c), \
             patch.object(w.subprocess, "Popen", return_value=process) as launch, patch.object(w.os, "killpg") as kill:
            with self.assertRaisesRegex(ValueError, "no retries"):
                w.session(["MOCK_NO_DVE"], Path(tmp), dict(OPERAND_BUNDLE=tmp, OPERAND_SNAPSHOT_SHA256="a" * 64), 1)
            self.assertEqual(launch.call_count, 1)
            kill.assert_called_once()

    def test_outer_run_approved_root_never_refreshes(self):
        for boundary in ("prelaunch", "post_session", "prepublish"):
            for change in ("content", "content_and_manifest", "manifest", "extra"):
                with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                    rootdir = Path(tmp)
                    output, bundle = rootdir / "result", rootdir / "result.tools"
                    bundle.mkdir()
                    c = dict(self.c, output=str(output), pins={}, inputs=["unit-design"], input_tree={}, image={})
                    (bundle / "hook.tcl").write_text("reviewed")
                    digest = seal(bundle, c)
                    receipt = dict(status="APPROVED_OPERAND_CAPTURE_SESSION_ONLY", authority="independent-parent-review", reviewer="unit-only",
                        snapshot_sha256=digest, baseline_collection_sha256="b" * 64, allow_one_dve_session=True,
                        allow_final_coverage_application=False, operand_points=1144, existing_points=94, csr_points=107,
                        observers=10, dve_max_seconds=w.CAPTURE_DVE_MAX_SECONDS, native_capture_sha256=None)
                    path = rootdir / "approval.json"
                    path.write_text(json.dumps(receipt))
                    calls = [0]
                    def mutate():
                        if change in ("content", "content_and_manifest"):
                            (bundle / "hook.tcl").write_text("unreviewed")
                        if change == "content_and_manifest":
                            seal(bundle, c)
                        elif change == "manifest":
                            (bundle / "snapshot.json").write_text((bundle / "snapshot.json").read_text() + "\n")
                        elif change == "extra":
                            (bundle / "extra").write_text("hidden")
                    def inputs(context):
                        calls[0] += 1
                        if (boundary == "prelaunch" and calls[0] == 1) or (boundary == "prepublish" and calls[0] == 3):
                            mutate()
                    def session(*args):
                        if boundary == "post_session":
                            mutate()
                    fake_runtime = Mock()
                    fake_runtime.finish.return_value = dict(status="UNIT_ONLY")
                    with patch.object(g, "OUT", rootdir), patch.object(w, "verify_inputs", side_effect=inputs), \
                         patch.object(g.csr_guard, "latest_corpus"), patch.object(w, "session", side_effect=session) as launched, \
                         patch.object(w, "module", return_value=fake_runtime):
                        with self.assertRaises(ValueError):
                            w.run(output, path, sha(path))
                        self.assertEqual(launched.call_count, 0 if boundary == "prelaunch" else 1)
                    self.assertFalse((output / "capture-certificate.json").exists())
                    COUNTS["snapshot_mutations"] += 1

    def test_full_tcl_flows(self):
        source = (HERE / "dve_operand.tcl").read_text()
        self.assertNotRegex(source, r'\b(dict|lassign|lmap|try|tailcall|yield|lreverse|eval|uplevel)\b')
        self.assertNotIn('{*}', source)
        self.assertNotRegex(source, re.compile(r'^proc (?!oq_|apply_reviewed_waivers)\w+', re.M))
        cases = {"ok": None, "missing_leaf": "Full XML branch inventory differs", "bad_parent": "Leaf/parent identity differs",
                 "selection_extra": "Operand exact selection differs", "initial_dirty": "Retained/reset group contains exclusion",
                 "load_missing": "Exact target not excluded", "load_neighbor": "Retained/reset group contains exclusion",
                 "review_pending": "Initial selection needs review", "signature_changed": "Full native record mismatch",
                 "helper_collision": "Operand helper command collision"}
        for stage in ("capture", "report"):
            c = self.c if stage == "capture" else self.report
            native = self.native if stage == "capture" else self.union + self.observers
            for name, failure in cases.items():
                with tempfile.TemporaryDirectory(dir=HERE) as tmp:
                    out = Path(tmp)
                    (out / "selection.tcl").write_text(w.selection(c))
                    (out / "fixture.native").write_bytes(native)
                    result = subprocess.run(["tclsh", str(HERE / "mock_session.tcl"), str(HERE), name], cwd=out,
                                            text=True, capture_output=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    if failure:
                        self.assertIn("MOCK_FAILED " + failure, result.stdout)
                        self.assertNotIn("OQ_SESSION_DONE", result.stdout)
                    else:
                        self.assertNotIn("MOCK_FAILED", result.stdout)
                        (out / "DVEfiles").mkdir()
                        (out / "DVEfiles/dve_gui.log").write_text(result.stdout)
                        states = state_proof(out, c)
                        self.assertEqual(len(states), 3636 if stage == "capture" else 4262)
                        p = out / "states_reloaded.tsv"
                        p.write_text(p.read_text().replace("\t0\texact_group_any_zero", "\t1\texact_group_any_zero", 1))
                        with self.assertRaises(ValueError):
                            state_proof(out, c)
                    COUNTS["tcl_cases"] += 1


if __name__ == "__main__":
    real_popen = subprocess.Popen
    def deny_tools(command, *args, **kwargs):
        require(isinstance(command, list) and command[0] == "tclsh", "REAL TOOL LAUNCH FORBIDDEN IN UNIT TESTS")
        return real_popen(command, *args, **kwargs)
    started = time.monotonic()
    with patch.object(subprocess, "Popen", side_effect=deny_tools):
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Operand))
    report = dict(status="PASS" if result.wasSuccessful() else "FAIL", tests=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), elapsed_seconds=round(time.monotonic() - started, 3), counts=COUNTS,
                  limitation="Synthetic full1144 native fixtures, never real signatures beyond the separately pinned pilot18; Tcl API model only.")
    (HERE / "test-results.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(not result.wasSuccessful())
