"""Replay actual logs and reject independently corrupted acceptance evidence."""
import json
from pathlib import Path
import struct
import sys
import unittest

sys.dont_write_bytecode = True
from check import check, matrix

OUT = Path(__file__).resolve().parents[5] / "verification/out/m4-stride-expanded-20261027-01"


class CheckerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.log = (OUT / "Q4_K/qemu.log").read_text()
        cls.cases = [c for c in matrix() if c["type"] == "Q4_K"]

    def reject(self, predicate, change):
        lines = self.log.splitlines()
        index = next(i for i, line in enumerate(lines) if predicate(line))
        lines[index] = change(lines[index])
        with self.assertRaises((ValueError, KeyError)):
            check("\n".join(lines), self.cases)

    def test_actual_replay(self):
        for typ in ("Q4_K", "Q6_K", "Q4_0", "Q8_0"):
            result = check((OUT / typ / "qemu.log").read_text(), [c for c in matrix() if c["type"] == typ])
            # JSON normalizes integer mapping keys, so compare serialized forms.
            self.assertEqual(json.loads(json.dumps(result)), json.loads((OUT / typ / "comparison.json").read_text()))

    def test_single_bit_mismatch(self):
        def corrupt(line):
            parts = line.split()
            bits = next(p.split("=")[1] for p in parts if p.startswith("got_bits="))
            new_bits = f"{int(bits, 16) ^ 1:08x}"
            value = struct.unpack("!f", bytes.fromhex(new_bits))[0]
            return " ".join("got_bits=" + new_bits if p.startswith("got_bits=") else
                            "got=" + format(value, ".9g") if p.startswith("got=") else p for p in parts)
        self.reject(lambda l: l.startswith("XS_VALUE "), corrupt)

    def test_nonfinite(self):
        self.reject(lambda l: l.startswith("XS_VALUE "), lambda l: " ".join(
            "got_bits=7f800000" if p.startswith("got_bits=") else "got=inf" if p.startswith("got=") else p
            for p in l.split()))

    def test_missing_call(self):
        self.reject(lambda l: l.startswith("GGML_RISCV_QBS_CALL "), lambda _: "")

    def test_missing_output(self):
        self.reject(lambda l: l.startswith("XS_VALUE "), lambda _: "")

    def test_hidden_contiguization(self):
        self.reject(lambda l: l.startswith("XS_OBSERVE ") and "side=1" in l, lambda l: l.replace("same_data=1", "same_data=0"))

    def test_wrong_stride(self):
        self.reject(lambda l: l.startswith("XS_OBSERVE ") and "nb0=8" in l, lambda l: l.replace("nb0=8", "nb0=4"))

    def test_ignored_wide_flag(self):
        self.reject(lambda l: l.startswith("XS_PLAN ") and "wide=1" in l, lambda l: l.replace("wide=1", "wide=0"))

    def test_native_count(self):
        self.reject(lambda l: l.startswith("GGML_RISCV_QBS_EXEC "), lambda l: " ".join(
            "native_qbexec=0" if p.startswith("native_qbexec=") else p for p in l.split()))

    def test_missing_block_preparation(self):
        self.reject(lambda l: l.startswith("GGML_RISCV_QBS_Q8K_M4_PREPARE "), lambda _: "")

    def test_failed_integrity(self):
        self.reject(lambda l: l.startswith("XS_CASE "), lambda l: l.replace("weight_integrity=1", "weight_integrity=0"))

    def test_missing_guest_exit(self):
        self.reject(lambda l: l.startswith("GUEST_TEST_EXIT="), lambda _: "")


if __name__ == "__main__":
    unittest.main()
