import unittest

from audit_refill_integration import order_events
from run_refill_attention_soc import check_log
from run_refill_overlap_probe import PERF_FIELDS, SUMMARY_FIELDS, COUNTERS


def good_log():
    row = dict.fromkeys(SUMMARY_FIELDS, 0)
    row.update(records=774, success_records=774, v2_full=2, v2_refill=2,
               release=2, v2_column_load=512, v2_row_load=256,
               q_external_bytes=3072, kv_external_bytes=131072,
               replay_bytes=131072, read_ranges=526, read_payload_bytes=134272)
    lines = []
    for i in range(1, 775):
        record = dict.fromkeys(PERF_FIELDS, 0)
        record.update(seq=i, success=1)
        if i == 1:
            record.update({k: row[k] for k in COUNTERS})
        lines.append("[AKV_PERF] " + " ".join(f"{k}={v}" for k, v in record.items()))
    lines.append("[AKV_PERF_SUMMARY] " + " ".join(f"{k}={v}" for k, v in row.items()))
    lines.extend(("AKV_REFILL_ATTENTION overlap=1 native=1 kv=128 outputs=1536 "
                  "cycles=123456 fcsr=1 vcsr=5 checksum=0123456789abcdef errors=0",
                  "Core Test *** SUCCESS"))
    return "\n".join(lines)


class AcceptanceTests(unittest.TestCase):
    def test_good_shape(self):
        self.assertEqual(check_log(good_log(), 1)["cycles"], 123456)

    def test_reject_changed_outcome_or_work(self):
        for old, new in (("native=1", "native=0"), ("errors=0", "errors=1"),
                         ("vcsr=5", "vcsr=4"), ("fcsr=1 ", "fcsr=32 "),
                         ("v2_refill=2", "v2_refill=1"),
                         ("read_payload_bytes=134272", "read_payload_bytes=134271"),
                         ("seq=1 ", "seq=2 "), ("success=1", "success=0")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                check_log(good_log().replace(old, new, 1), 1)

    def test_reject_duplicate_or_wrong_schedule(self):
        with self.assertRaises(ValueError):
            check_log(good_log(), 0)
        with self.assertRaises(ValueError):
            check_log(good_log() + "\n" + good_log(), 1)

    def test_order_identity_and_completeness(self):
        text = "\n".join(f"[AKV_REFILL_ORDER] event={event} cycle={cycle} "
                         f"ordinal={ordinal} arch={ordinal+4} vid=1"
                         for ordinal in (1, 2)
                         for event, cycle in (("start", 10), ("first_ar", 12), ("terminal", 20)))
        self.assertEqual(order_events(text)[1]["first_ar"]["cycle"], 12)
        for bad in (text.replace("event=first_ar", "event=start", 1),
                    text.replace("arch=5", "arch=6", 1), text.split("\n", 1)[1]):
            with self.assertRaises(ValueError):
                order_events(bad)


if __name__ == "__main__":
    unittest.main()
