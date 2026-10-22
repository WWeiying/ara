#!/usr/bin/env python3
"""Offline tests only. Temporary fixtures stay in this new helper directory."""
import argparse
import copy
import csv
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import guard
import support as s
import workflow


def fixture_context():
    qualified, targets, csr, blocks, path, pins = guard.qualify_csr()
    policy = guard.legacy.audit.jread(guard.legacy.REVIEW / "policy.json")
    audit = guard.legacy.audit.jread(guard.legacy.REVIEW / "audit.json")
    combined = copy.deepcopy(policy)
    combined["allowed_points"] += csr
    with (path.parent / "metadata.tsv").open() as stream:
        table = list(csv.DictReader(stream, delimiter="\t"))
    selection = []
    for row in table:
        if row["selected"] == "1":
            sid, vid = map(int, row["coordinate"].split(","))
            selection.append(dict(spec=sid, vector=vid, meta=row["meta"], path=row["path"]))
    context = dict(policy=combined, observers=audit["observers"], csr_blocks=blocks,
        csr_scope=qualified["validation"]["scope"], csr_checksum=["1371260681", "3035350189"],
        csr_header="".join(path.read_text().splitlines(True)[:2]), csr_selection=selection,
        csr_all_keys=[r["coordinate"] for r in table], csr_targets=targets,
        csr_native_path=str(path), csr_native_sha256=s.sha(path), design=audit["identity"]["design_vdb"],
        baseline=str(guard.OUT / "gap48-current-20261004-01"), baseline_collection_sha256="a" * 64,
        input_membership={}, pins=pins)
    for source in (guard.COVERAGE / "prepare_dve_waivers.py", guard.COVERAGE / "reviewed_20261004/prepare_native.py",
                   guard.COVERAGE / "reviewed_20261004/audit_readonly.py", HERE / "prepare_native.py",
                   HERE / "support.py", HERE / "dve_csr.tcl", guard.COVERAGE / "dve_hierarchy/export_dve_coverage.tcl"):
        context["pins"][str(source)] = s.sha(source)
    native = guard.legacy.native_points(policy).encode() + path.read_bytes()
    return context, native, table


def tamper_bundle(bundle, mode):
    manifest, hook = bundle / "snapshot.json", bundle / "dve_waivers.tcl"
    if mode in ("content", "content_and_manifest"):
        hook.write_bytes(hook.read_bytes() + b"# unreviewed fixture change\n")
    if mode == "content_and_manifest":
        hashes = s.jread(manifest)
        hashes["dve_waivers.tcl"] = s.sha(hook)
        manifest.write_text(json.dumps(hashes, indent=2) + "\n")
    elif mode == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b"\n")
    elif mode == "extra":
        (bundle / "unreviewed.txt").write_text("extra fixture\n")


def fresh_log(context):
    lines = ["CSR_RUNTIME_CHECK_OK raw", "CSR_RAW_EMPTY", "CSR_METADATA before total=626 selected=107 retained=519",
        "CSR_INCLUDED before count=626 excluded=0", "All exclusions successfully imported and applied.",
        "CSR_REVIEW_EMPTY 1", "CSR_METADATA loaded total=626 selected=107 retained=519",
        "CSR_INCLUDED loaded count=519 excluded=0"]
    lines += ["CSR_LOADED " + p["meta"] + " excluded=1" for p in context["csr_selection"]]
    lines += ["CSR_RUNTIME_CHECK_OK saved", "CSR_NATIVE_SAVED_EXACT", "CSR_INCLUDED final count=626 excluded=0",
        "CSR_RUNTIME_CHECK_OK reset", "CSR_SESSION_PROOF_DONE", "DVE_WAIVER_EXPORT_DONE", "DVE_COVERAGE_EXPORT_DONE"]
    return "\n".join(lines) + "\n"


class Supplemental(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context, cls.native, cls.table = fixture_context()
        cls.design = guard.legacy.audit.Design(Path(cls.context["design"]))
        cls.definition = cls.design.definition(cls.context["csr_scope"], "branch")

    def test_exact_actual_vector22(self):
        points, width = s.exact_inventory(self.definition)
        self.assertEqual(width, 626)
        self.assertEqual(points[3, 22]["raw_index"], 174)
        self.assertEqual(points[3, 0]["raw_index"], 196)
        with patch.object(guard.legacy.audit.Design, "point", side_effect=AssertionError("legacy vector0 API forbidden for CSR")):
            self.assertEqual(len(s.bind_targets(self.definition, self.context["csr_targets"])), 626)

    def test_sparse_nonnumeric_order_vector_ids(self):
        root = ET.fromstring('<branch_def><branch_spec id="9" chksum="1"><branch_vector id="42" vector="100"/>'
            '<branch_vector id="7" vector="010"/><branch_vector id="99" vector="001"/></branch_spec>'
            '<branch_spec id="2" chksum="2"><branch_vector id="5" vector="1"/></branch_spec></branch_def>')
        points, width = s.exact_inventory(root)
        self.assertEqual(width, 4)
        self.assertEqual([points[9, v]["raw_index"] for v in (42, 7, 99)], [2, 1, 0])
        self.assertEqual(points[2, 5]["raw_index"], 3)
        root[0].append(copy.deepcopy(root[0][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate branch vector"):
            s.exact_inventory(root)

    def test_vector_mapping_mutations(self):
        for field, value in (("native", "Branch 3 (0)"), ("raw_index", 196), ("native", "Branch 3 (187)"),
                             ("spec_width", 2), ("metric", "line"), ("eligibility", "ACCEPT_RESET_INVARIANT")):
            with self.subTest(field=field, value=value):
                points = copy.deepcopy(self.context["csr_targets"])
                point = next(p for p in points if p["native"] == "Branch 3 (22)")
                point[field] = value
                with self.assertRaises(ValueError):
                    s.bind_targets(self.definition, points)

    def test_multivector_zero_not_two_bit_witness(self):
        bits = ["1"] * 626
        for point in self.context["csr_targets"]:
            bits[point["raw_index"]] = "0"
        s.zero_targets("".join(bits), self.context["csr_targets"])
        bits[174] = "1"
        with self.assertRaisesRegex(ValueError, "raw hit"):
            s.zero_targets("".join(bits), self.context["csr_targets"])

    def test_raw_xml_bad_scope_checksum_width_duplicate(self):
        scope = self.context["csr_scope"]
        template = '<root><instance_data name="{}" chksum="{}" value="{}"/></root>'
        good = template.format(scope, "3035350189", "0" * 626).encode()
        self.assertEqual(s.raw_csr_bits(gzip.compress(good), scope, "3035350189", 626), ("0" * 626, False))
        inherited = good.replace(b' chksum="3035350189"', b"")
        self.assertTrue(s.raw_csr_bits(inherited, scope, "3035350189", 626)[1])
        for data in (good.replace(scope.encode(), b"foreign"), good.replace(b"3035350189", b"1"),
                     template.format(scope, "3035350189", "0" * 625).encode(),
                     good.replace(b"</root>", good[len(b"<root>"):]), good.replace(b' value="0', b' value="x')):
            with self.subTest(data=s.hashlib.sha256(data).hexdigest()):
                with self.assertRaises(ValueError):
                    s.raw_csr_bits(data, scope, "3035350189", 626)

    def test_raw_hit_and_hash_drift_in_pass_vdb(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            path = Path(tmp) / "code.vdb/snps/coverage/db/testdata/mock/branch.verilog.data.xml"
            path.parent.mkdir(parents=True)
            def put(bits):
                path.write_text('<root><instance_data name="' + self.context["csr_scope"] + '" value="' + bits + '"/></root>')
            put("0" * 626)
            row = dict(vdb=str(Path(tmp) / "code.vdb"), vdb_files={str(path): s.sha(path)})
            result = guard.raw_zero_scan([row], self.context["csr_targets"], self.context["csr_scope"], "3035350189")
            self.assertEqual(result["selected_hits"], 0)
            bits = list("0" * 626)
            bits[174] = "1"
            put("".join(bits))
            with self.assertRaisesRegex(ValueError, "not bound"):
                guard.raw_zero_scan([row], self.context["csr_targets"], self.context["csr_scope"], "3035350189")
            row["vdb_files"][str(path)] = s.sha(path)
            with self.assertRaisesRegex(ValueError, "raw hit"):
                guard.raw_zero_scan([row], self.context["csr_targets"], self.context["csr_scope"], "3035350189")

    def test_union_exact201_plus10(self):
        self.assertEqual(s.validate_union(self.native, self.context, guard.legacy.audit, False), 201)
        observers = "".join('CHECKSUM: "' + " ".join(p["checksum"]) + '"\nANNOTATION: "observer"\nINSTANCE:' + p["scope"] + '\n'
                            for p in self.context["observers"]).encode()
        self.assertEqual(s.validate_union(self.native + observers, self.context, guard.legacy.audit, True), 211)
        with self.assertRaises(ValueError):
            s.validate_union(self.native, self.context, guard.legacy.audit, True)

    def test_union_complete_record_order_only(self):
        original = Path(self.context["csr_native_path"]).read_bytes()
        roundtrip = Path(self.context["csr_native_path"]).with_name("branches.roundtrip.el").read_bytes()
        self.assertNotEqual(original, roundtrip)
        combined = self.native[:-len(original)] + roundtrip
        self.assertEqual(s.validate_union(combined, self.context, guard.legacy.audit, False), 201)

    def test_union_identity_and_annotation_negatives(self):
        csr = Path(self.context["csr_native_path"]).read_bytes()
        old = self.native[:-len(csr)]
        mutations = [csr.replace(b"(22)", b"(23)", 1), csr.replace(b"(22)", b"(187)", 1),
            csr.replace(b'"1804293586"', b'"0"', 1), csr.replace(b"pending independent", b"approved independent", 1),
            csr.replace(b"csr_read 1,", b"csr_read 0,", 1), csr.replace(b"INSTANCE: ", b"INSTANCE:", 1),
            csr + csr, csr + b"// ignored line\n", csr + b"ATTRIBUTES: hidden\n",
            csr + b'ANNOTATION: "orphan"\n', csr + b'CHECKSUM: "1"\n',
            csr.replace(b"\nBranch ", b"\n Branch ", 1), csr.rstrip(b"\n")]
        for data in mutations:
            with self.subTest(sha=s.hashlib.sha256(data).hexdigest()):
                with self.assertRaises(ValueError):
                    s.validate_union(old + data, self.context, guard.legacy.audit, False)
        with self.assertRaises(ValueError):
            s.validate_union(old, self.context, guard.legacy.audit, False)

    def test_latest_lineage_and_forks(self):
        self.assertEqual(guard.latest_tip({"old": {"parent": None}, "new": {"parent": "old"}}), "new")
        for records in ({}, {"a": {"parent": "b"}, "b": {"parent": "a"}},
                        {"a": {"parent": None}, "b": {"parent": "a"}, "c": {"parent": "a"}}):
            with self.assertRaises(ValueError):
                guard.latest_tip(records)

    def test_stale_and_incomplete_corpus(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root = Path(tmp)
            image = {"simv": "image"}
            design = root / "compile.vdb"
            for name, parent, status in (("old", None, "PASS"), ("new", str(root / "old"), "PASS"),
                                         ("pending", str(root / "new"), "RUNNING")):
                directory = root / name
                (directory / "combined-dve").mkdir(parents=True)
                report = directory / "combined-dve/summary.csv"
                report.write_text("raw")
                (directory / "collection.json").write_text(json.dumps(dict(status=status, image=image, passed=1,
                    reports={str(report): s.sha(report)})))
                (directory / "plan.json").write_text(json.dumps(dict(image=image, design_vdb=str(design), source_selection=dict(baseline=parent))))
            with patch.object(guard, "OUT", root):
                self.assertEqual(guard.latest_corpus(design, image)[0], root / "new")
                with self.assertRaisesRegex(ValueError, "stale"):
                    guard.latest_corpus(design, image, root / "old")

    def test_review_is_not_gap50_identity_status(self):
        receipt = dict(status="APPROVED_SUPPLEMENTAL_CSR_REPORT_ONLY", authority="independent-parent-review",
            reviewer="UNIT TEST ONLY", snapshot_sha256="a" * 64, baseline_collection_sha256="b" * 64,
            allow_one_dve_session=True, allow_final_coverage_application=False,
            existing_points=94, csr_points=107, observers=10, blocks_added=0)
        s.approval(receipt, "a" * 64, "b" * 64)
        for key, value in (("status", "PASS_SCOPED_SEMANTIC_ROUNDTRIP_NOT_APPLICATION_AUTHORIZATION"),
                           ("snapshot_sha256", "c" * 64), ("baseline_collection_sha256", "c" * 64),
                           ("reviewer", ""), ("allow_final_coverage_application", True),
                           ("allow_one_dve_session", False), ("csr_points", 108), ("blocks_added", 1)):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    s.approval(dict(receipt, **{key: value}), "a" * 64, "b" * 64)

    def test_no_launch_without_review(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(workflow, "OUT", Path(tmp)), \
                patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")) as launch:
            with self.assertRaises(ValueError):
                workflow.load_snapshot(Path(tmp) / "report", Path(tmp) / "absent.json", "")
            launch.assert_not_called()

    def test_timeout_bound_before_launch(self):
        with patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")) as launch:
            with self.assertRaises(ValueError):
                workflow.session([], HERE, {}, 181)
            launch.assert_not_called()

    def test_process_group_cleanup_on_all_exits(self):
        for outcome in (0, 7, subprocess.TimeoutExpired("MOCK_NO_DVE", 1), TimeoutError("outer budget")):
            with self.subTest(outcome=str(outcome)), tempfile.TemporaryDirectory(dir=HERE) as tmp:
                process = Mock(pid=987654321)
                process.wait.side_effect = [outcome, -9]
                with patch.object(workflow.subprocess, "Popen", return_value=process) as launch, \
                        patch.object(workflow.os, "killpg") as kill, patch.object(workflow, "verify_snapshot"):
                    env = {"CSR_REVIEW_BUNDLE": tmp, "CSR_SNAPSHOT_SHA256": "a" * 64}
                    if outcome == 0:
                        workflow.session(["MOCK_NO_DVE"], Path(tmp), env, 1)
                    else:
                        with self.assertRaises((ValueError, TimeoutError)):
                            workflow.session(["MOCK_NO_DVE"], Path(tmp), env, 1)
                    self.assertTrue(launch.call_args.kwargs["start_new_session"])
                    kill.assert_called_once_with(process.pid, workflow.signal.SIGKILL)
                    self.assertEqual(process.wait.call_args.kwargs["timeout"], 3)
                    self.assertEqual(s.jread(Path(tmp) / "execution.json")["dve_launch_count"], 1)

    def test_output_cannot_be_inside_frozen_evidence(self):
        with self.assertRaisesRegex(ValueError, "direct child"):
            workflow.locations(guard.OUT / "gap50-csr-roundtrip-review-20261004-01/new-report")

    def test_snapshot_does_not_launch_and_copies_csr_bytes(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(workflow, "OUT", Path(tmp)), \
                patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")) as launch:
            output = Path(tmp) / "report"
            bundle = workflow.snapshot(output, self.context)
            self.assertFalse(output.exists())
            self.assertEqual((bundle / "csr107.original.el").read_bytes(), Path(self.context["csr_native_path"]).read_bytes())
            self.assertEqual((bundle / "waivers/operand_flush.el").read_bytes(), self.native)
            manifest = s.jread(bundle / "snapshot.json")
            s.verify_hashes({str(bundle / p): h for p, h in manifest.items()})
            with self.assertRaises(ValueError):
                workflow.snapshot(output, self.context)
            launch.assert_not_called()

    def test_snapshot_and_review_drift_fail_before_launch(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(workflow, "OUT", Path(tmp)), \
                patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")) as launch:
            output = Path(tmp) / "report"
            bundle = workflow.snapshot(output, self.context)
            receipt = dict(status="APPROVED_SUPPLEMENTAL_CSR_REPORT_ONLY", authority="independent-parent-review",
                reviewer="TRANSIENT UNIT FIXTURE ONLY", snapshot_sha256=s.sha(bundle / "snapshot.json"),
                baseline_collection_sha256=self.context["baseline_collection_sha256"], allow_one_dve_session=True,
                allow_final_coverage_application=False, existing_points=94, csr_points=107, observers=10, blocks_added=0)
            review = Path(tmp) / "fixture-review.json"
            review.write_text(json.dumps(receipt))
            digest = s.sha(review)
            workflow.load_snapshot(output, review, digest)
            with self.assertRaisesRegex(ValueError, "Approval hash"):
                workflow.load_snapshot(output, review, "0" * 64)
            extra = bundle / "unexpected.txt"
            extra.write_text("fixture")
            with self.assertRaisesRegex(ValueError, "Unexpected snapshot"):
                workflow.load_snapshot(output, review, digest)
            extra.unlink()
            native = bundle / "waivers/operand_flush.el"
            native.write_bytes(native.read_bytes() + b'ANNOTATION: "fixture"\n')
            with self.assertRaisesRegex(ValueError, "hash drift"):
                workflow.load_snapshot(output, review, digest)
            launch.assert_not_called()

    def test_snapshot_adapter_stages_only_exact_union(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp, patch.object(workflow, "OUT", Path(tmp)), \
                patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")) as launch:
            output = Path(tmp) / "report"
            context = copy.deepcopy(self.context)
            context["shape_files"] = {p.name: s.sha(p) for p in
                sorted((Path(context["design"]) / "snps/coverage/db/shape").iterdir()) if p.is_file()}
            bundle = workflow.snapshot(output, context)
            output.mkdir()
            adapter = guard.module("csr_test_snapshot_adapter", bundle / "prepare_dve_waivers.py")
            with patch("sys.stdout", new_callable=io.StringIO):
                adapter.main(["--design", context["design"], "--output", str(output),
                              "--snapshot-sha256", s.sha(bundle / "snapshot.json")])
            self.assertEqual((output / "points.el").read_bytes(), self.native)
            self.assertEqual(s.jread(output / "waiver_status.json")["status"], "PREPARED")
            plan = (output / "waiver_plan.tcl").read_text()
            for observer in context["observers"]:
                self.assertEqual(plan.count("{" + observer["scope"] + "}"), 1)
            self.assertFalse((output / "exclusions.el").exists())
            launch.assert_not_called()

    def test_reviewed_root_and_exact_snapshot_membership(self):
        modes = ("content_and_manifest", "manifest", "content", "extra", "empty_directory", "missing", "symlink")
        for mode in modes:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=HERE) as tmp, \
                    patch.object(workflow, "OUT", Path(tmp)):
                bundle = workflow.snapshot(Path(tmp) / "report", self.context)
                root = s.sha(bundle / "snapshot.json")
                s.verify_snapshot(bundle, root)
                if mode == "empty_directory":
                    (bundle / "unreviewed").mkdir()
                elif mode == "missing":
                    (bundle / "csr_selection.tcl").unlink()
                elif mode == "symlink":
                    target = bundle / "csr_selection.tcl"
                    copy_path = Path(tmp) / "same-bytes.tcl"
                    copy_path.write_bytes(target.read_bytes())
                    target.unlink()
                    target.symlink_to(copy_path)
                else:
                    tamper_bundle(bundle, mode)
                with self.assertRaises(ValueError):
                    s.verify_snapshot(bundle, root)

    def test_runtime_callbacks_refuse_resealed_or_changed_bundle(self):
        for stage in ("raw", "saved", "reset"):
            for mode in ("content_and_manifest", "manifest", "content", "extra"):
                with self.subTest(stage=stage, mode=mode), tempfile.TemporaryDirectory(dir=HERE) as tmp, \
                        patch.object(workflow, "OUT", Path(tmp)), patch("subprocess.Popen", side_effect=AssertionError("DVE forbidden")):
                    output = Path(tmp) / "report"
                    bundle = workflow.snapshot(output, self.context)
                    root = s.sha(bundle / "snapshot.json")
                    adapter = guard.module("csr_tamper_callback", bundle / "prepare_dve_waivers.py")
                    tamper_bundle(bundle, mode)
                    with patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                            self.assertRaisesRegex(ValueError, "snapshot|Snapshot"):
                        adapter.main(["--design", self.context["design"], "--output", str(output),
                                      "--snapshot-sha256", root, "--session", stage])
                    self.assertNotIn("CSR_RUNTIME_CHECK_OK", stdout.getvalue())

    def test_run_binds_reviewed_root_at_every_boundary(self):
        cases = [(stage, mode) for stage in ("prelaunch", "callback", "post_session", "prepublish")
                 for mode in ("content_and_manifest", "manifest", "content", "extra")] + [("unchanged", None)]
        for stage, mode in cases:
            with self.subTest(stage=stage, mode=mode), tempfile.TemporaryDirectory(dir=HERE) as tmp, \
                    patch.object(workflow, "OUT", Path(tmp)):
                output = Path(tmp) / "report"
                context = copy.deepcopy(self.context)
                context["pins"] = {p: h for p, h in context["pins"].items() if Path(p).is_relative_to(guard.COVERAGE)}
                raw = Path(tmp) / "raw-fixture.xml"
                raw.write_text("0" * 626)
                context["pins"][str(raw)] = s.sha(raw)
                context.update(tests=1, inputs=[context["design"], "unused-fixture.vdb"], image={},
                    csr_raw_audit=dict(samples=1, selected_hits=0, bits="0" * 626,
                        files=[dict(path=str(raw), sha256=s.sha(raw))]))
                bundle = workflow.snapshot(output, context)
                root = s.sha(bundle / "snapshot.json")
                review = Path(tmp) / "unit-review.json"
                review.write_text(json.dumps(dict(status="APPROVED_SUPPLEMENTAL_CSR_REPORT_ONLY",
                    authority="independent-parent-review", reviewer="TRANSIENT TEST ONLY", snapshot_sha256=root,
                    baseline_collection_sha256=context["baseline_collection_sha256"], allow_one_dve_session=True,
                    allow_final_coverage_application=False, existing_points=94, csr_points=107, observers=10, blocks_added=0)))
                review_sha = s.sha(review)
                adapter = guard.module("csr_tamper_outer", bundle / "prepare_dve_waivers.py")
                real_main = adapter.main
                def adapter_main(argv):
                    self.assertEqual(argv[argv.index("--snapshot-sha256") + 1], root)
                    adapter.check_snapshot(root)
                    if "--finalize" in argv:
                        return dict(status="SUPPLEMENTAL_CSR_REPORT_VERIFIED_NOT_FINAL_SIGNOFF")
                    if stage == "prelaunch":
                        tamper_bundle(bundle, mode)
                latest_calls = []
                def latest(*args):
                    latest_calls.append(args)
                    if stage == "prepublish" and len(latest_calls) == 2:
                        tamper_bundle(bundle, mode)
                waits = []
                def wait(**kwargs):
                    waits.append(kwargs)
                    if len(waits) == 1:
                        (output / "DVEfiles").mkdir()
                        (output / "DVEfiles/dve_gui.log").write_text(fresh_log(context))
                        for name in ("summary.csv.partial", "summary_waived.csv.partial"):
                            (output / name).write_text("fixture\n")
                        if stage in ("callback", "post_session"):
                            tamper_bundle(bundle, mode)
                        if stage == "callback":
                            real_main(["--design", context["design"], "--output", str(output),
                                       "--snapshot-sha256", root, "--session", "raw"])
                    return 0
                process = Mock(pid=987654321)
                process.wait.side_effect = wait
                with patch.object(guard, "module", return_value=adapter), patch.object(adapter, "main", side_effect=adapter_main), \
                        patch.object(guard, "latest_corpus", side_effect=latest), \
                        patch.object(workflow.subprocess, "Popen", return_value=process) as launch, \
                        patch.object(workflow.os, "killpg") as kill, patch("sys.stdout", new_callable=io.StringIO):
                    if stage == "unchanged":
                        workflow.run(output, review, review_sha, time.monotonic())
                    else:
                        with self.assertRaisesRegex(ValueError, "snapshot|Snapshot"):
                            workflow.run(output, review, review_sha, time.monotonic())
                    if stage == "prelaunch":
                        launch.assert_not_called()
                        kill.assert_not_called()
                    else:
                        launch.assert_called_once()
                        self.assertEqual(launch.call_args.kwargs["env"]["CSR_SNAPSHOT_SHA256"], root)
                        kill.assert_called_once_with(process.pid, workflow.signal.SIGKILL)
                status = s.jread(output / "waiver_status.json")
                if stage == "unchanged":
                    self.assertEqual(status["snapshot_sha256"], root)
                    self.assertEqual(status["status"], "SUPPLEMENTAL_CSR_REPORT_VERIFIED_NOT_FINAL_SIGNOFF")
                else:
                    self.assertEqual(status["status"], "REJECTED_NO_SUCCESS_CLAIM")
                self.assertEqual(s.sha(review), review_sha)

    def test_raw_report_drift(self):
        adapter = guard.module("csr_test_runtime", HERE / "prepare_native.py")
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root = Path(tmp)
            baseline = root / "baseline.csv"
            data = "Name,Depth,Line,Condition,Branch,FSM,Toggle\nroot,0,1,2,3,4,5\n"
            baseline.write_text(data)
            (root / "summary.csv.partial").write_text(data)
            context = dict(raw_reference=str(baseline), raw_reference_sha256=s.sha(baseline))
            adapter.check_raw(root, context)
            (root / "summary.csv.partial").write_text(data.replace(",3,", ",99,"))
            with self.assertRaisesRegex(ValueError, "Raw report differs"):
                adapter.check_raw(root, context)

    def test_tcl_84_and_full_mock_flow(self):
        code = (HERE / "dve_csr.tcl").read_text()
        exporter = (guard.COVERAGE / "dve_hierarchy/export_dve_coverage.tcl").read_text()
        for source in (code, exporter, workflow.selection_tcl(self.context)):
            self.assertNotRegex(source, r"\b(?:dict|lassign|lmap|apply|try|tailcall|yield|coroutine)\b|\{\*\}|\b(?:in|ni)\b|\*\*")
        faults = {"ok": None, "raw_mismatch": "MOCK_RAW_MISMATCH", "missing_metadata": "CSR full inventory differs",
            "metadata_alias": "CSR exact metadata changed", "duplicate_metadata": "Duplicate CSR vector",
            "selection_neighbor": "CSR selection differs", "review_pending": "Native exclusions need review",
            "missing_loaded": "Exact CSR target not excluded", "neighbor_loaded": "CSR neighbor/reset exclusion at loaded",
            "native_mismatch": "MOCK_NATIVE_MISMATCH", "reset_dirty": "CSR neighbor/reset exclusion at final"}
        for case, failure in faults.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir=HERE) as tmp:
                root = Path(tmp)
                (root / "csr_selection.tcl").write_text(workflow.selection_tcl(self.context))
                observers = [p["scope"] for p in self.context["observers"]]
                plan = "set waiver_scopes {\n" + "".join("    " + workflow.literal(p) + " 1 {observer}\n" for p in observers) + "}\n"
                (root / "waiver_plan.tcl").write_text(plan)
                fixture = "set env(CSR_REVIEW_BUNDLE) " + workflow.literal(str(root)) + "\n"
                fixture += "set env(CSR_SNAPSHOT_SHA256) " + workflow.literal("a" * 64) + "\n"
                fixture += "set env(DVE_COVERAGE_OUTPUT) " + workflow.literal(str(root)) + "\nset mock_rows {\n"
                fixture += "".join("    {" + f"{r['meta']} {r['path']} {r['selected']}" + "}\n" for r in self.table)
                fixture += "}\nset mock_observers {\n" + "".join("    " + workflow.literal(p) + "\n" for p in observers) + "}\n"
                (root / "fixture.tcl").write_text(fixture)
                result = subprocess.run(["tclsh", str(HERE / "mock_session.tcl"), str(root / "fixture.tcl"),
                    str(HERE / "dve_csr.tcl"), case], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10, cwd=root)
                self.assertEqual(result.returncode, 0, result.stdout[-4000:])
                self.assertIn("MOCK_RESULT " + case + " PASS", result.stdout)
                self.assertIn("MOCK_REMOVED", result.stdout)
                self.assertFalse(list(root.glob("*.el")))
                if failure:
                    self.assertIn("MOCK_REJECTED " + failure + "\n", result.stdout)
                    self.assertNotIn("CSR_SESSION_PROOF_DONE", result.stdout)
                else:
                    self.assertEqual(s.fresh_state(result.stdout, self.context)["excluded"], 107)
                    for bad in (result.stdout.replace("CSR_REVIEW_EMPTY 1", "CSR_REVIEW_EMPTY 0"),
                                result.stdout.replace("CSR_LOADED Branch3.22 excluded=1", "CSR_LOADED Branch3.22 excluded=0"),
                                result.stdout.replace("loaded count=519 excluded=0", "loaded count=519 excluded=1"),
                                result.stdout + "CSR_LOADED Branch3.21 excluded=0\n",
                                result.stdout + "All exclusions successfully imported and applied.\n",
                                result.stdout.replace("CSR_RUNTIME_CHECK_OK saved", "CSR_RUNTIME_CHECK_OK reset", 1)):
                        with self.assertRaises(ValueError):
                            s.fresh_state(bad, self.context)


if __name__ == "__main__":
    # Preserve every pre-existing coverage file, including old helpers/proofs.
    old = {str(p): s.sha(p) for p in guard.COVERAGE.rglob("*") if p.is_file()
           and not p.is_relative_to(HERE) and p.name != "run_reviewed_csr_dve_20261004.py"}
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Supplemental))
    s.verify_hashes(old)
    report = dict(status="PASS" if result.wasSuccessful() else "FAIL", test_methods=result.testsRun,
        failures=len(result.failures), errors=len(result.errors), tcl_mock_scenarios=11,
        old_coverage_file_hashes_unchanged=old, real_dve_launches=0, simulated_runs_only=True,
        host_tcl_is_not_a_real_tcl84_interpreter=True,
        old_strict_status=s.jread(guard.OUT / "gap40-csr-native-branches-20261004-02/validation.json")["status"])
    (HERE / "test-results.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0 if result.wasSuccessful() else 1)
