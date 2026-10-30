import unittest
from check import check
from run import merge


def fixture():
    lines = [
        "RF_CONFIG qbs=0 emulate=0 prepare=0 packed=0 cache=0 context=0 wide=0 threads=1 vlen=1024 vl32=32",
        "RF_BEGIN id=0 type=Q4_K k=512 n=32 m=4 element=4 pad=16",
        "GGML_RISCV_REPACK=Q4_K_32x1_Q8_K shape=512x32",
        "GGML_RISCV_QBS_TENSOR type=q4_K k=512 rows=32 decision=runtime_disabled segmented=0",
        "RF_WEIGHT id=0 buffer=CPU_REPACK qbs_supported=0 owned=1 extra=0x100 data=0x200 captured=1",
    ]
    for side in range(3):
        for phase in ("before", "after"):
            lines.append(f"RF_OBSERVE id=0 side={side} phase={phase} nb0=4 nb1={2112 if side == 2 else 2048} "
                         f"contiguous={int(side != 2)} op=VIEW same_tensor=1 same_data=1 same_backing=1")
        lines.append("GGML_RISCV_QBS_Q8K_M4_PREPARE enabled=0 path=generic k=512")
    for i in range(128):
        bad = i == 32
        lines.append(f"RF_VALUE id=0 index={i} row={i//32} col={i%32} ref=0 control=0 got={int(bad)} "
                     f"ref_bits=00000000 control_bits=00000000 got_bits={'3f800000' if bad else '00000000'}")
        if bad:
            lines.append("RF_FIRST id=0 index=32 row=1 col=0 ref_bits=00000000 got_bits=3f800000")
    for row in range(4):
        lines.append(f"RF_ROW id=0 row={row} mismatches={int(row == 1)} outputs=32")
    lines += ["RF_CASE id=0 outputs=128 mismatches=1 control_mismatches=0 graph_status=0 complete=1 finite=1 "
              "paired_inputs=1 backing_integrity=1 weight_integrity=1 capture_integrity=1 result=FAIL",
              "RF_STOP reason=first_mismatch planned=4 completed=1 skipped=3 performance=not_measured",
              "GGML_RISCV_QBS_COVERAGE selected_tensors=0 fallback_runtime=1",
              "GUEST_TEST_EXIT=1"]
    return "\n".join(lines)


class CheckTests(unittest.TestCase):
    def test_valid_failure(self):
        report = check(fixture())
        self.assertEqual(report["cases"][0]["affected_rows"], [1])
        self.assertEqual(report["conclusion"], "CONFIRMED")

    def test_mutations_rejected(self):
        original = fixture()
        mutants = [
            original + "\nGGML_RISCV_QBS_CALL type=q4_K",
            original.replace("control_bits=00000000", "control_bits=3f800000", 1),
            original.replace("nb1=2112", "nb1=2048", 1),
            original.replace("decision=runtime_disabled", "decision=selected"),
            original.replace("GUEST_TEST_EXIT=1", "GUEST_TEST_EXIT=0"),
            original.replace("RF_FIRST id=0 index=32", "RF_FIRST id=0 index=33"),
            original.replace("same_backing=1", "same_backing=0", 1),
            original.replace("RF_VALUE id=0 index=127", "RF_VALUE id=0 index=126"),
            original + "\nRF_BEGIN id=1 type=Q4_K k=512 n=32 m=7 element=4 pad=16",
        ]
        for mutant in mutants:
            with self.subTest(mutant=mutant[-120:]), self.assertRaises(ValueError):
                check(mutant)

    def test_pin_conflict_rejected(self):
        pins = {"sealed": "old"}
        with self.assertRaises(ValueError):
            merge(pins, {"sealed": "new"})
        self.assertEqual(pins, {"sealed": "old"})


if __name__ == "__main__":
    unittest.main()
