import contextlib
import io
import unittest
from unittest.mock import patch

import akv_historical_budget_oracle_717 as oracle
import run_akv_historical_budget_retry_717 as run


def skew_fixture():
    sites = [{"pc": 0x80001000 + 64 * i, "phase": i + 1} for i in range(12)]
    lines, checks, traps = [], 0, 0
    for i, word in enumerate(oracle.skew.WORDS):
        fault = 4 <= i <= 6
        row = dict.fromkeys(oracle.bare_perf.PERF_KEYS, 0)
        row.update(oracle.bare_perf.expected_perf(i), busy_cycles=13)
        if i in (0, 7):
            row.update(ar=4, r_beats=31, read_outstanding_max=2)
        lines.append("[AKV_PERF] " + " ".join(f"{k}={row[k]}" for k in oracle.bare_perf.PERF_KEYS))
        lines.append(f"AKV46_CSR phase={i+1} fflags=21 vstart=0")
        if fault:
            pc = sites[i]["pc"]
            lines.append(f"AKV46_TRAP phase={i+1} cause=2 pc={pc:x} expected={pc:x} tval=0")
        checks += 269 + 3 * fault
        traps += fault
        lines.append(f"AKV46_PHASE phase={i+1} word={word:08x} traps={traps} checks={checks} errors=0")
    lines.append("PASSED: akv_gap46_skew_context checks=3237 errors=0")
    return "\n".join(lines) + "\n", {"sites": sites}


class BudgetTests(unittest.TestCase):
    def test_exact_budgets_and_counts(self):
        self.assertEqual(run.CASES[oracle.DESCRIPTOR][1:3], (300, 1800))
        self.assertEqual(run.CASES[oracle.SKEW][1:3], (600, 3000))
        self.assertEqual(oracle.CHECKS, {oracle.DESCRIPTOR: 6751, oracle.SKEW: 3237})

    def test_carry_rejected_before_execution(self):
        with patch.object(run.subprocess, "Popen", side_effect=AssertionError("No EDA")):
            with self.assertRaisesRegex(ValueError, "not eligible"):
                run.prepare("vgap35_carry_illegal", run.OUT / "not-created-carry")

    def test_only_fresh_artifact_paths_change(self):
        original = [str(run.IMAGE), "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
                    "+PRELOAD=/old/input.elf", "+TESTCASE=" + oracle.DESCRIPTOR,
                    "+COMMIT_TRACE=/old/trace.csv", "-cm", "line+cond+fsm+tgl+branch",
                    "-cm_dir", "/old/code.vdb", "-cm_name", oracle.DESCRIPTOR]
        command = run.command_for(original, run.OUT / "new-only-paths", oracle.DESCRIPTOR)
        self.assertEqual([i for i, (a, b) in enumerate(zip(original, command)) if a != b], [5, 7, 11])
        self.assertEqual(command[4], "+ntb_random_seed=1")

    def test_extra_option_rejected(self):
        with self.assertRaises(ValueError):
            run.command_for([str(run.IMAGE), "+TESTCASE=" + oracle.SKEW], run.OUT / "fresh", oracle.SKEW)

    def test_descriptor_all_checks(self):
        self.assertEqual(oracle.descriptor_log("PASSED: akv_gap35_descriptor checks=6751 errors=0\n")["checks"], 6751)
        with self.assertRaises(ValueError):
            oracle.descriptor_log("PASSED: akv_gap35_descriptor checks=6750 errors=0\n")

    def test_descriptor_duplicate_or_fail_rejected(self):
        good = "PASSED: akv_gap35_descriptor checks=6751 errors=0\n"
        for log in (good + good, "FAIL trap count check=4\n" + good):
            with self.assertRaises(ValueError):
                oracle.descriptor_log(log)

    def test_skew_full_checks_bare_perf_without_mutating_frozen_helpers(self):
        log, elf = skew_fixture()
        original = oracle.skew.perf_records
        proof = oracle.skew_log(log, elf)
        self.assertEqual(proof["checks"], 3237)
        self.assertEqual(len(proof["phases"]), 12)
        self.assertIs(oracle.skew.perf_records, original)
        with self.assertRaises(ValueError):
            oracle.skew.validate_log(log, False, elf)

    def test_skew_reduced_checks_rejected(self):
        log, elf = skew_fixture()
        with self.assertRaises(ValueError):
            oracle.skew_log(log.replace("checks=3237", "checks=177"), elf)

    def test_skew_csr_and_translation_mutations_rejected(self):
        log, elf = skew_fixture()
        for changed in (log.replace("fflags=21", "fflags=0", 1),
                        log.replace("translations=0", "translations=4", 1)):
            with self.assertRaises(ValueError):
                oracle.skew_log(changed, elf)

    def test_real_original_elf_fit_and_privilege_static(self):
        for name, (producer, _, _, digest) in run.CASES.items():
            elf = run.OUT / producer / "results" / name / "tests" / ("app_" + name) / "input.elf"
            self.assertEqual(run.sha(elf), digest)
            proof, _ = oracle.elf_layout(elf.read_bytes(), 2097152)
            self.assertEqual(proof["main_mode"], "U")
            self.assertLess(max(s["paddr"] + s["memory_bytes"] for s in proof["segments"]), 0x80200000)
            with self.assertRaises(ValueError):
                oracle.elf_layout(elf.read_bytes(), 4096)

    def test_privilege_order_rejected(self):
        with self.assertRaises(ValueError):
            oracle.privilege_log("U 0000000080000164 0 30551073 csrw mtvec\n")

    def test_prepare_cli_never_launches(self):
        manifest = dict(status="PREPARED_PARENT_REVIEW_REQUIRED_NO_RUN", pins={}, timeout_s=1800, expected_checks=6751)
        with patch.object(run, "prepare", return_value=(run.OUT / "mock-only", manifest)), \
                patch.object(run, "save"), patch.object(run, "sha", return_value="a" * 64), \
                patch.object(run.subprocess, "Popen", side_effect=AssertionError("No EDA")), \
                patch.object(run, "run_reviewed", side_effect=AssertionError("No run")), \
                contextlib.redirect_stdout(io.StringIO()):
            run.main(["prepare", "--case", oracle.DESCRIPTOR, "--output", str(run.OUT / "mock-only")])


if __name__ == "__main__":
    unittest.main()
