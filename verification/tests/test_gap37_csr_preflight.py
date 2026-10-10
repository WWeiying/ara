"""Fail-closed tests for the new independent gap37 preflight validator."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("gap37_build", Path(__file__).with_name("build_gap37_csr.py"))
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


def fixture(name):
    stub = 0x80001000
    rows = []
    for i, (priv, insn, legal, rd) in enumerate(BUILD.expected_probes(name)):
        cause = {1: 9, 3: 11}[priv] if legal else 2
        rows.append(f"PROBE phase={i} priv={priv} insn={insn:x} legal={legal} "
                    f"cause={cause:x} epc={stub + 4 * legal:x} tval={0 if legal else insn:x} rd={rd:x}")
    phases, illegal, checks = BUILD.CASES[name]
    rows += [f"{name} phases={phases} checks={checks} illegal={illegal} legal={phases-illegal} failures=0",
             "PASSED: " + name]
    return "\n".join(rows), stub


class Gap37PreflightTest(unittest.TestCase):
    def test_complete_fixtures(self):
        for name in BUILD.CASES:
            log, stub = fixture(name)
            BUILD.validate_log(name, log, stub)

    def test_each_probe_field_is_checked(self):
        name = "gap37_csr_alias_tvm"
        log, stub = fixture(name)
        for old, new in (("phase=0", "phase=1"), ("priv=3", "priv=0"),
                         ("insn=104596f3", "insn=1045a6f3"), ("legal=1", "legal=0"),
                         ("cause=b", "cause=2"), ("epc=80001004", "epc=80001008"),
                         ("tval=0", "tval=1"), ("rd=0", "rd=2")):
            self.assertIn(old, log)
            with self.subTest(field=old), self.assertRaises(ValueError):
                BUILD.validate_log(name, log.replace(old, new, 1), stub)

    def test_missing_duplicate_and_weakened_summary_rejected(self):
        name = "gap37_csr_alias_tvm"
        log, stub = fixture(name)
        for bad in (log.split("\n", 1)[1], log + "\nPASSED: " + name,
                    log.replace("checks=626", "checks=625"), log.replace("failures=0", "failures=1"),
                    log + "\nFAIL: unexpected", log + "\n" + log.splitlines()[-2]):
            with self.assertRaises(ValueError):
                BUILD.validate_log(name, bad, stub)

    def test_epc_must_match_elf_not_log_calibration(self):
        name = "gap37_csr_alias_tvm"
        log, stub = fixture(name)
        with self.assertRaises(ValueError):
            BUILD.validate_log(name, log, stub + 64)

    def test_illegal_tval_and_destination_are_exact(self):
        name = "gap37_csr_alias_tvm"
        log, stub = fixture(name)
        for old, new in (("tval=180596f3", "tval=0"),
                         ("rd=1122334455667788", "rd=0")):
            self.assertIn(old, log)
            with self.assertRaises(ValueError):
                BUILD.validate_log(name, log.replace(old, new, 1), stub)


if __name__ == "__main__":
    unittest.main()
