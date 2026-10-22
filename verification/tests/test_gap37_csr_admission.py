"""Admission/runtime fail-closed fixtures; no compiler, Spike, VCS or queue."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "coverage"))
import coverage_evidence as evidence
import gap37_csr_admission as csr
import run_checked_extension as checked

spec = importlib.util.spec_from_file_location("prepare_gap37_admission", Path(__file__).with_name("prepare_gap37_csr_admission.py"))
producer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(producer)

UART = csr.NAME + " phases=52 checks=626 illegal=7 legal=45 failures=0\nPASSED: " + csr.NAME + "\n"


def write(filename, value):
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(value if isinstance(value, str) else json.dumps(value))
    return filename


def sha(filename):
    return checked.full.base.sha256(filename)


class AdmissionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="gap37-admission-tests-")
        cls.root = Path(cls.temp.name)
        cls.selection = producer.create(cls.root / "prepared")
        cls.item = cls.selection["cases"][0]
        cls.proof = evidence.Evidence()
        cls.result = csr.precheck(cls.item, cls.proof)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def rebind(self, mutator):
        item = copy.deepcopy(self.item)
        record = json.loads(Path(item["precheck"]["record"]).read_text())
        mutator(item, record)
        filename = self.root / (self._testMethodName + ".json")
        write(filename, record)
        item["evidence"] = [str(filename) if p == item["precheck"]["record"] else p for p in item["evidence"]]
        item["precheck"]["record"] = str(filename)
        item["precheck"]["record_sha256"] = sha(filename)
        return item

    def test_accepted_case_and_all_checked_pins(self):
        self.assertEqual(self.result["name"], csr.TEST)
        self.assertEqual(self.result["status"], "PASS")
        for p in (*csr.OWN_SOURCES, csr.BUILDER, csr.LOG, csr.SOURCE_MANIFEST, csr.SPIKE_ELF, csr.ELF):
            self.assertIn(str(p), self.proof.files)
        self.assertEqual(self.result["checks"], 626)

    def test_new_and_implicit_old_formats_rejected_by_legacy(self):
        with self.assertRaisesRegex(ValueError, "unsupported precheck format"):
            evidence.precheck(self.item, evidence.Evidence())
        old = json.loads(csr.ORIGINAL_SELECTION.read_text())["cases"][0]
        with self.assertRaisesRegex(ValueError, "unsupported/ambiguous precheck"):
            evidence.precheck(old, evidence.Evidence())

    def test_exact_api_and_noncsr_delegation(self):
        self.assertEqual(csr.NAME, "gap37_csr_alias_tvm")
        self.assertTrue(csr.handles(self.item))
        other = {"name": "app:fence_t_gap36_smoke", "precheck": {"format": "cva6-fence-static-v1"}}
        self.assertFalse(csr.handles(other))
        token = object()
        delegate = Mock(return_value=token)
        wrapped = csr.wrap_precheck(delegate)
        proof = evidence.Evidence()
        self.assertIs(wrapped(other, proof), token)
        delegate.assert_called_once_with(other, proof)
        module = types.SimpleNamespace(precheck=delegate)
        self.assertIs(csr.install(module, wrapped), wrapped)
        self.assertIs(csr.install(module), wrapped)

    def test_counter_renamed_case_and_missing_format_rejected(self):
        for name, fmt in (("rvv:gap37_csr_counters", csr.FORMAT), ("app:" + csr.NAME, csr.FORMAT),
                          (csr.TEST, "csr-spike-v1"), (csr.TEST, None)):
            with self.subTest(name=name, fmt=fmt):
                item = copy.deepcopy(self.item)
                item["name"], item["precheck"]["format"] = name, fmt
                with self.assertRaises(ValueError):
                    csr.precheck(item, evidence.Evidence())

    def test_bad_timeout_and_binary_rejected(self):
        for value in (0, 601, True):
            item = dict(self.item, timeout_s=value)
            with self.assertRaisesRegex(ValueError, "budget"):
                csr.precheck(item, evidence.Evidence())
        with self.assertRaisesRegex(ValueError, "ELF"):
            csr.precheck(dict(self.item, binary=str(csr.SPIKE_ELF)), evidence.Evidence())

    def test_record_hash_and_identity_rejected(self):
        item = copy.deepcopy(self.item)
        item["precheck"]["record_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash differs"):
            csr.precheck(item, evidence.Evidence())
        item = self.rebind(lambda i, r: r.update(name="rvv:gap37_csr_counters"))
        with self.assertRaisesRegex(ValueError, "identity/status"):
            csr.precheck(item, evidence.Evidence())

    def test_log_drift_and_missing_evidence_pins_rejected(self):
        item = self.rebind(lambda i, r: r["files"].update({str(csr.LOG): "0" * 64}))
        with self.assertRaisesRegex(ValueError, "hash differs"):
            csr.precheck(item, evidence.Evidence())
        item = copy.deepcopy(self.item)
        item["evidence"].remove(str(csr.COMMANDS))
        with self.assertRaisesRegex(ValueError, "evidence set"):
            csr.precheck(item, evidence.Evidence())

    def test_missing_source_and_wrapper_hash_rejected(self):
        item = copy.deepcopy(self.item)
        item["sources"].remove(str(csr.BUILDER))
        with self.assertRaisesRegex(ValueError, "source set"):
            csr.precheck(item, evidence.Evidence())
        item = copy.deepcopy(self.item)
        item["source_hashes"][str(csr.SCRIPT)] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source hash manifests"):
            csr.precheck(item, evidence.Evidence())

    def test_strict_validator_replayed_and_forged_phase_rejected(self):
        item = self.rebind(lambda i, r: r["validated"]["probes"][0].update(rd=99))
        with patch.object(csr, "load_validator", wraps=csr.load_validator) as load:
            with self.assertRaisesRegex(ValueError, "strict replay"):
                csr.precheck(item, evidence.Evidence())
            load.assert_called_once()

    def runtime_fixture(self):
        output = self.root / self._testMethodName
        output.mkdir(exist_ok=True)
        target = output / "results" / csr.NAME
        artifact = target / "tests" / ("rvv_" + csr.NAME)
        case = dict(name=csr.NAME, source_name=csr.TEST, kind="directed", oracle="selfcheck+trace-audit",
                    directed_test={"kind": "rvv"}, frozen_elf=str(csr.ELF), elf_sha256=self.item["binary_sha256"])
        case["contract"] = checked.full.contract(case)
        files = [write(target / "summary.json", [dict(name=csr.TEST, status="PASS", artifact_dir=str(artifact))]),
                 write(artifact / "inputs.json", dict(binary={"sha256": case["elf_sha256"]}, simv={"image_sha256": "fixture-image"})),
                 write(artifact / "work/run.vcs.log", UART),
                 write(artifact / "commit_trace.csv", "synthetic fixture; not a DUT trace\n"),
                 write(artifact / "trace_summary.json", dict(status="VALID", retire_count=1))]
        binary = artifact / "input.elf"
        shutil.copyfile(csr.ELF, binary)
        files += [binary, write(target / "independent_audit.json", dict(status="PASS", errors=[],
            case_count=1, passed_cases=1, failed_cases=0, policy=dict(require_complete=True, require_trace=True),
            cases=[dict(name=csr.TEST, status="PASS", errors=[], artifact_dir=str(artifact))]))]
        selection = write(output / "selection.json", self.selection)
        plan = dict(checked_extension=checked.VERSION, cases=[case], wrapper_image="fixture-image",
                    source_selection={"selection": str(selection)}, files=dict(self.proof.files))
        plan["files"].update({str(selection): sha(selection), str(Path(checked.full.batch.__file__).resolve()): sha(Path(checked.full.batch.__file__))})
        row = dict(name=csr.NAME, kind="directed", status="PASS", returncode=0, passed_only=True,
                   vdb_valid=True, reused=False, elf_sha256=case["elf_sha256"], contract=case["contract"],
                   vdb=str(artifact / "work/code.vdb"), files={str(p): sha(p) for p in files})
        return output, plan, row, artifact

    def test_runtime_artifact_bound_positive_fixture(self):
        output, plan, row, artifact = self.runtime_fixture()
        result = csr.runtime_proof(output, plan, row)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["uart"]["checks"], 626)
        for suffix in ("work/run.vcs.log", "commit_trace.csv", "trace_summary.json", "input.elf"):
            self.assertIn(str(artifact / suffix), result["files"])

    def test_runtime_summary_rejected_even_after_rehash(self):
        output, plan, row, artifact = self.runtime_fixture()
        log = write(artifact / "work/run.vcs.log", UART.replace("checks=626", "checks=625"))
        row["files"][str(log)] = sha(log)
        with self.assertRaisesRegex(ValueError, "runtime summary"):
            csr.runtime_proof(output, plan, row)

    def test_runtime_requires_generic_trace_audit(self):
        output, plan, row, artifact = self.runtime_fixture()
        filename = output / "results" / csr.NAME / "independent_audit.json"
        report = json.loads(filename.read_text())
        report["policy"]["require_trace"] = False
        write(filename, report)
        row["files"][str(filename)] = sha(filename)
        with self.assertRaisesRegex(RuntimeError, "independent audit"):
            csr.runtime_proof(output, plan, row)

    def test_runtime_rejects_unfrozen_adapter(self):
        output, plan, row, _ = self.runtime_fixture()
        del plan["files"][str(csr.SCRIPT)]
        with self.assertRaisesRegex(ValueError, "not frozen"):
            csr.runtime_proof(output, plan, row)

    def test_runtime_rejects_foreign_artifact(self):
        output, plan, row, _ = self.runtime_fixture()
        filename = output / "results" / csr.NAME / "summary.json"
        write(filename, [dict(name=csr.TEST, status="PASS", artifact_dir=str(self.root))])
        row["files"][str(filename)] = sha(filename)
        with self.assertRaisesRegex(ValueError, "foreign CSR"):
            csr.runtime_proof(output, plan, row)


class RuntimeLogTest(unittest.TestCase):
    def test_runtime_uart_does_not_require_probe_lines(self):
        self.assertEqual(csr.validate_runtime_log(UART)["checks"], 626)

    def test_all_runtime_counts_and_markers_fail_closed(self):
        bad = [UART.replace(a, b) for a, b in (("phases=52", "phases=51"), ("checks=626", "checks=627"),
               ("illegal=7", "illegal=6"), ("legal=45", "legal=44"), ("failures=0", "failures=1"))]
        bad += [UART + UART, UART.splitlines()[0], "PASSED: " + csr.NAME,
                UART + "PASSED: foreign\n", UART + "FAIL: bad\n", UART + "*** FAILED ***\n",
                UART + "Fatal: bad\n", UART + "Error: bad\n"]
        for text in bad:
            with self.subTest(text=text), self.assertRaises(ValueError):
                csr.validate_runtime_log(text)


if __name__ == "__main__":
    unittest.main()
