import unittest

from run_refill_attention_abba import check_log
from run_refill_overlap_probe import numeric_fields, PERF_FIELDS, SUMMARY_FIELDS, COUNTERS
from test_refill_attention_soc import good_log


def evidence():
    result, records = [], []
    for trial, mode in enumerate((0, 1, 1, 0)):
        result.append(f"AKV_REFILL_TRIAL_BEGIN trial={trial} overlap={mode}")
        for line in good_log().splitlines():
            if line.startswith("[AKV_PERF] "):
                row = numeric_fields(line.removeprefix("[AKV_PERF] "), PERF_FIELDS)
                row["seq"] += 774 * trial
                records.append(row)
                result.append("[AKV_PERF] " + " ".join(f"{k}={v}" for k,v in row.items()))
            elif line.startswith("AKV_REFILL_ATTENTION "):
                result.append(line.replace("overlap=1", f"overlap={mode}").replace(
                    "cycles=123456", f"cycles={100 if mode == 0 else 90}"))
    total = {k: (max(r[k] for r in records) if k == "read_outstanding_max" else
                 sum(r[k] for r in records)) for k in COUNTERS}
    total.update(records=3096, success_records=3096, fault_records=0, validation_fault_records=0)
    result.extend(("AKV_REFILL_ABBA_PASS trials=4 outputs_per_trial=1536",
        "[AKV_PERF_SUMMARY] " + " ".join(f"{k}={v}" for k,v in total.items()),
        "Core Test *** SUCCESS"))
    return "\n".join(result)


class AbbaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.good = evidence()

    def test_good(self):
        report = check_log(self.good)
        self.assertEqual(report["sums"], {"0": 200, "1": 180})

    def test_reject_wrong_order_truncated_or_accounting(self):
        for old, new in (("trial=1 overlap=1", "trial=1 overlap=0"),
                         ("seq=775 ", "seq=776 "), ("records=3096", "records=3095"),
                         ("Core Test *** SUCCESS", ""), ("errors=0", "errors=1")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                check_log(self.good.replace(old, new, 1))

    def test_reject_changed_flags_and_bytes(self):
        for old, new in (("fcsr=1 vcsr", "fcsr=3 vcsr"),
                         ("checksum=0123456789abcdef", "checksum=1123456789abcdef")):
            with self.assertRaises(ValueError): check_log(self.good.replace(old, new, 1))


if __name__ == "__main__": unittest.main()
