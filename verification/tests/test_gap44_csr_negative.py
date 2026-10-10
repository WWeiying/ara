"""Independent fail-closed mutations of real sealed Spike evidence; no simulation."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification/coverage"))
import coverage_evidence as evidence
import gap44_csr_admission as csr
import gap44_csr_oracle as oracle
import run_gap44_csr_checked_extension as wrapper

spec = importlib.util.spec_from_file_location("gap44_prepare", Path(__file__).with_name("prepare_gap44_csr_admission.py"))
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)
LOG = csr.LOG.read_text()
STUB = 0x80003e00
UART = ("HPM_GUARD profile=dut-rw writable=1 seed_a=13579bdf2468ace0 "
        "seed_b=fedcba9876543210 stable=fedcba9876543210 after=fedcba9876543210 event=0\n"
        "csr_gap44_absent phases=52 checks=1290 illegal=50 legal=2 failures=0\nPASSED: csr_gap44_absent\n")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return path


class OracleTest(unittest.TestCase):
    def test_actual_elf_and_exact_recovery_sequence(self):
        self.assertEqual(oracle.stub_address(csr.SPIKE_ELF.read_bytes()), STUB)
        result = oracle.validate_log(LOG, True, STUB)
        self.assertEqual((result["phases"], result["illegal"], result["checks"]), (52, 50, 1290))
        self.assertEqual(result["probes"][0]["insn"], 0x340596f3)
        self.assertEqual(result["probes"][-1]["insn"], 0x340026f3)
        self.assertEqual([p["insn"] for p in result["probes"][48:51]], [0xb83026f3, 0xb83596f3, 0xc83026f3])
        self.assertFalse(result["hpm_nonzero_preservation"])

    def test_every_field_of_every_probe_is_independent(self):
        lines = LOG.splitlines()
        for pos, line in enumerate(lines):
            if not line.startswith("PROBE "):
                continue
            words = line.split()
            for field in range(1, 9):
                key, value = words[field].split("=")
                base = 10 if key in ("phase", "priv", "legal") else 16
                changed = words[:]
                number = int(value, base) + 1
                changed[field] = key + "=" + (str(number) if base == 10 else f"{number:x}")
                bad = lines[:]
                bad[pos] = " ".join(changed)
                with self.subTest(probe=words[1], field=key), self.assertRaises(ValueError):
                    oracle.validate_log("\n".join(bad), True, STUB)

    def test_csr_and_tval_cannot_be_recalibrated_together(self):
        bad = LOG.replace("200026f3", "201026f3")
        with self.assertRaises(ValueError):
            oracle.validate_log(bad, True, STUB)
        with self.assertRaises(ValueError):
            oracle.validate_log(LOG, True, STUB + 64)

    def test_missing_duplicate_malformed_probes(self):
        probe = next(s for s in LOG.splitlines() if s.startswith("PROBE "))
        for bad in (LOG.replace(probe + "\n", "", 1), LOG + probe + "\n", LOG + "PROBE bad\n",
                    LOG.replace("priv=3", "priv=1"), LOG.replace("priv=3", "priv=0")):
            with self.assertRaises(ValueError):
                oracle.validate_log(bad, True, STUB)

    def test_counts_and_pass_are_not_sufficient(self):
        for old, new in (("phases=52", "phases=51"), ("checks=1290", "checks=1289"),
                         ("illegal=50", "illegal=49"), ("legal=2", "legal=3"), ("failures=0", "failures=1")):
            with self.assertRaises(ValueError):
                oracle.validate_log(LOG.replace(old, new), True, STUB)
        for bad in (LOG + "PASSED: foreign\n", LOG + "FAIL: late\n", LOG + "*** FAILED ***\n", UART):
            with self.assertRaises(ValueError):
                oracle.validate_log(bad, True, STUB)

    def test_dut_requires_real_nonzero_writable_stable_counter(self):
        self.assertTrue(oracle.validate_log(UART, False)["hpm_nonzero_preservation"])
        for old, new in (("dut-rw", "spike-raz"), ("writable=1", "writable=0"),
                         ("seed_a=13579bdf2468ace0", "seed_a=0"),
                         ("seed_b=fedcba9876543210", "seed_b=0"),
                         ("stable=fedcba9876543210", "stable=fedcba9876543211"),
                         ("after=fedcba9876543210", "after=0"), ("event=0", "event=1")):
            with self.subTest(field=old), self.assertRaises(ValueError):
                oracle.validate_log(UART.replace(old, new), False)
        with self.assertRaises(ValueError):
            oracle.validate_log(LOG, False)

    def test_capability_must_match_original_raz_observation(self):
        log = (csr.BUILD / "hpm-capability.spike.log").read_text()
        self.assertFalse(oracle.validate_capability(log)["writable"])
        with self.assertRaises(ValueError):
            oracle.validate_capability(log.replace("read=0", "read=1"))

    def test_elf_machine_stub_name_alignment_and_size(self):
        original = csr.SPIKE_ELF.read_bytes()
        bad = bytearray(original)
        struct.pack_into("<H", bad, 18, 62)
        for data in (bytes(bad), original.replace(b"csr_gap35_stub\0", b"csr_gap35_fake\0"), original[:64]):
            with self.assertRaises((ValueError, struct.error)):
                oracle.stub_address(data)

    def test_json_roundtrip_is_exact_without_normalization(self):
        for result in (oracle.validate_log(LOG, True, STUB), oracle.validate_log(UART, False)):
            self.assertEqual(result, json.loads(json.dumps(result)))


class AdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT / "verification/out", prefix="gap44-review-tests-")
        cls.root = Path(cls.temp.name)
        cls.selection = producer.create(cls.root / "admission")
        cls.item = cls.selection["cases"][0]
        cls.proof = evidence.Evidence()
        cls.result = csr.precheck(cls.item, cls.proof)
        # The real binding above hashes every immutable input. Structural
        # mutations below are fixtures, not repeated multi-GiB toolchain audits.
        verified = dict(cls.proof.files)
        stamps = {p: (Path(p).stat().st_ino, Path(p).stat().st_size, Path(p).stat().st_mtime_ns)
                  for p in verified}
        real = evidence.Evidence

        class FixtureEvidence(real):
            def pin(self, path, expected=None):
                path = evidence.full.absolute(path).absolute()
                key = str(path)
                if key not in verified:
                    return super().pin(path, expected)
                stat = path.stat()
                if (stat.st_ino, stat.st_size, stat.st_mtime_ns) != stamps[key]:
                    raise ValueError("immutable test input changed")
                sha = verified[key]
                if expected is not None and expected != sha:
                    raise ValueError("evidence hash differs: " + key)
                if key in self.files and self.files[key] != sha:
                    raise ValueError("evidence changed: " + key)
                self.files[key] = sha
                return path

        cls.fixture_patch = patch.object(evidence, "Evidence", FixtureEvidence)
        cls.fixture_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.fixture_patch.stop()
        cls.temp.cleanup()

    def test_real_precheck_and_shared_batch_proof(self):
        proof = evidence.Evidence()
        proof.pin(ROOT / "AGENTS.md")
        self.assertEqual(csr.precheck(self.item, proof), self.result)
        self.assertIn(str(ROOT / "AGENTS.md"), proof.files)
        self.assertTrue(self.result["hpm_dut_preservation_pending"])

    def test_identity_budget_and_old_format_rejected(self):
        for fields in (dict(name="rvv:csr_gap35_permissions"), dict(timeout_s=301), dict(timeout_s=True),
                       dict(binary=str(csr.SPIKE_ELF)), dict(runtime_contract="status-only")):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                csr.precheck(dict(self.item, **fields), evidence.Evidence())
        with self.assertRaises(ValueError):
            evidence.precheck(self.item, evidence.Evidence())

    def test_missing_sources_evidence_and_bad_record_hash(self):
        for key in ("sources", "evidence"):
            item = copy.deepcopy(self.item)
            item[key].pop()
            with self.assertRaises(ValueError):
                csr.precheck(item, evidence.Evidence())
        item = copy.deepcopy(self.item)
        item["precheck"]["record_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            csr.precheck(item, evidence.Evidence())

    def test_rehashed_admission_cannot_omit_original_or_forge_probes(self):
        for n, mutation in enumerate((lambda r: r["files"].pop(str(csr.LOG)),
                                      lambda r: r["validated"]["probes"][1].update(rd=0),
                                      lambda r: r.update(hpm_dut_preservation_pending=False))):
            item = copy.deepcopy(self.item)
            record = json.loads(Path(item["precheck"]["record"]).read_text())
            mutation(record)
            path = write(self.root / f"altered-{n}.json", record)
            item["evidence"] = [str(path) if p == item["precheck"]["record"] else p for p in item["evidence"]]
            item["precheck"].update(record=str(path), record_sha256=producer.digest(path))
            with self.assertRaises(ValueError):
                csr.precheck(item, evidence.Evidence())

    def runtime_fixture(self):
        output = self.root / self._testMethodName
        output.mkdir(exist_ok=True)
        target = output / "results" / csr.NAME
        artifact = target / "tests" / ("rvv_" + csr.NAME)
        case = dict(name=csr.NAME, source_name=csr.TEST, kind="directed", oracle="selfcheck+trace-audit",
                    directed_test={"kind": "rvv"}, frozen_elf=str(csr.ELF), elf_sha256=self.item["binary_sha256"])
        case["contract"] = wrapper.full.contract(case)
        files = [write(target / "summary.json", [dict(name=csr.TEST, status="PASS", artifact_dir=str(artifact))]),
                 write(artifact / "inputs.json", dict(binary={"sha256": case["elf_sha256"]}, simv={"image_sha256": "fixture-image"})),
                 write(artifact / "work/run.vcs.log", UART),
                 write(artifact / "commit_trace.csv", "synthetic unit fixture, not a DUT trace\n"),
                 write(artifact / "trace_summary.json", dict(status="VALID", retire_count=1))]
        binary = artifact / "input.elf"
        shutil.copyfile(csr.ELF, binary)
        files += [binary, write(target / "independent_audit.json", dict(status="PASS", errors=[],
            case_count=1, passed_cases=1, failed_cases=0, policy=dict(require_complete=True, require_trace=True),
            cases=[dict(name=csr.TEST, status="PASS", errors=[], artifact_dir=str(artifact))]))]
        selection = write(output / "selection.json", self.selection)
        audit = json.loads(csr.AUDIT.read_text())
        plan = dict(checked_extension=wrapper.checked.VERSION, cases=[case], wrapper_image="fixture-image",
                    source_selection={"selection": str(selection)}, files=dict(self.proof.files),
                    design_vdb=str(Path(audit["compiled_manifest"]).parent / "simv.vdb"))
        checker = Path(wrapper.full.batch.__file__).resolve()
        plan["files"].update({str(selection): producer.digest(selection), str(checker): producer.digest(checker)})
        row = dict(name=csr.NAME, kind="directed", status="PASS", returncode=0, passed_only=True,
                   vdb_valid=True, reused=False, elf_sha256=case["elf_sha256"], contract=case["contract"],
                   vdb=str(artifact / "work/code.vdb"), files={str(p): producer.digest(p) for p in files})
        return output, plan, row, artifact

    def test_runtime_positive_json_roundtrip(self):
        output, plan, row, _ = self.runtime_fixture()
        proof = csr.runtime_proof(output, plan, row)
        self.assertEqual(proof, json.loads(json.dumps(proof)))
        self.assertTrue(proof["uart"]["hpm_nonzero_preservation"])

    def test_runtime_missing_csv_pin_and_log_drift(self):
        output, plan, row, artifact = self.runtime_fixture()
        altered = copy.deepcopy(row)
        del altered["files"][str(artifact / "commit_trace.csv")]
        with self.assertRaisesRegex(ValueError, "unbound runtime"):
            csr.runtime_proof(output, plan, altered)
        write(artifact / "work/run.vcs.log", UART + "FAIL: changed\n")
        with self.assertRaisesRegex(ValueError, "hash differs"):
            csr.runtime_proof(output, plan, row)

    def test_rehashed_zero_hpm_guard_still_rejected(self):
        output, plan, row, artifact = self.runtime_fixture()
        log = write(artifact / "work/run.vcs.log", UART.replace("after=fedcba9876543210", "after=0"))
        row["files"][str(log)] = producer.digest(log)
        with self.assertRaisesRegex(ValueError, "HPM guard"):
            csr.runtime_proof(output, plan, row)

    def test_runtime_generic_audit_and_plan_binding_required(self):
        output, plan, row, _ = self.runtime_fixture()
        missing = copy.deepcopy(plan)
        del missing["files"][str(csr.SCRIPT)]
        with self.assertRaisesRegex(ValueError, "not frozen"):
            csr.runtime_proof(output, missing, row)
        path = output / "results" / csr.NAME / "independent_audit.json"
        value = json.loads(path.read_text()); value["policy"]["require_trace"] = False
        write(path, value); row["files"][str(path)] = producer.digest(path)
        with self.assertRaisesRegex(RuntimeError, "independent audit"):
            csr.runtime_proof(output, plan, row)

    def summary_fixture(self):
        output, plan, row, artifact = self.runtime_fixture()
        proof = csr.runtime_proof(output, plan, row)
        report = output / "results" / csr.NAME / "csr_gap44_runtime_audit.json"
        write(report, proof)
        row["files"].update(proof["files"])
        row["files"][str(report)] = producer.digest(report)
        write(output / "outcomes" / (csr.NAME + ".json"), row)
        return output, plan, row, report, proof, artifact

    def test_summary_accepts_saved_json_and_delegates(self):
        output, plan, _, _, _, _ = self.summary_fixture()
        delegate = Mock(return_value="delegated")
        with patch.object(wrapper.checked, "frozen", return_value=plan):
            self.assertEqual(wrapper.summarize(output, plan, delegate), "delegated")
        delegate.assert_called_once_with(output, plan)

    def test_summary_cannot_omit_required_file_even_after_rehash(self):
        output, plan, row, report, proof, artifact = self.summary_fixture()
        del proof["files"][str(artifact / "commit_trace.csv")]
        write(report, proof); row["files"][str(report)] = producer.digest(report)
        write(output / "outcomes" / (csr.NAME + ".json"), row)
        delegate = Mock()
        with patch.object(wrapper.checked, "frozen", return_value=plan), self.assertRaisesRegex(ValueError, "replay differs"):
            wrapper.summarize(output, plan, delegate)
        delegate.assert_not_called()

    def test_summary_status_only_cannot_pass(self):
        output, plan, row, report, _, _ = self.summary_fixture()
        write(report, dict(status="PASS", schema=oracle.RUNTIME_FORMAT))
        row["files"][str(report)] = producer.digest(report)
        write(output / "outcomes" / (csr.NAME + ".json"), row)
        with patch.object(wrapper.checked, "frozen", return_value=plan), self.assertRaisesRegex(ValueError, "strict gap44"):
            wrapper.summarize(output, plan, Mock())


class HooksTest(unittest.TestCase):
    def test_missing_digest_never_disables_expected_hash_check(self):
        for key in ("record_sha256", "source_hashes_sha256"):
            for value in (None, "", True, "0"):
                schema = dict(format=csr.FORMAT, record_sha256="0" * 64, source_hashes_sha256="0" * 64)
                schema[key] = value
                item = dict(name=csr.TEST, timeout_s=300, runtime_contract=oracle.RUNTIME_FORMAT, precheck=schema)
                with patch.object(csr, "frozen_inputs") as frozen, self.assertRaisesRegex(ValueError, "SHA256"):
                    csr.precheck(item, evidence.Evidence())
                frozen.assert_not_called()

    def test_install_preserves_parent_script_delegates_and_is_idempotent(self):
        precheck, worker, summary = Mock(return_value="other-precheck"), Mock(return_value=7), Mock(return_value="other-summary")
        parent_script = ROOT / "verification/coverage/parent-fixture.py"
        with patch.object(wrapper, "_HOOKS", None), patch.object(wrapper.checked, "SCRIPT", parent_script), \
             patch.object(wrapper.checked.evidence, "precheck", precheck), patch.object(wrapper.full, "worker", worker), \
             patch.object(wrapper.checked, "summarize", summary), patch.object(wrapper.checked, "frozen", return_value={"cases": []}):
            hooks = csr.install_hooks()
            self.assertEqual(wrapper.checked.SCRIPT, parent_script)
            self.assertIs(csr.install_hooks(), hooks)
            item, proof = {"name": "rvv:gap47_other"}, evidence.Evidence()
            self.assertEqual(wrapper.checked.evidence.precheck(item, proof), "other-precheck")
            precheck.assert_called_once_with(item, proof)
            self.assertEqual(wrapper.full.worker(ROOT, "gap45_other"), 7)
            worker.assert_called_once_with(ROOT, "gap45_other")
            self.assertEqual(wrapper.checked.summarize(ROOT, {"cases": []}), "other-summary")
            summary.assert_called_once_with(ROOT, {"cases": []})
            later = Mock(wraps=wrapper.checked.evidence.precheck)
            wrapper.checked.evidence.precheck = later
            csr.install_hooks()
            self.assertIs(wrapper.checked.evidence.precheck, later)


if __name__ == "__main__":
    unittest.main()
