import copy
import unittest

from diagnose_full_projection import explain, WAIT
from full_projection import N


def fixture():
    reports = []
    keys = ('ar','r_beats','payload_bytes','weight_bytes','activation_bytes','useful_pairs','fp_uop_issue','accumulator_updates')
    for wide in (0,1):
        saved = 896 if wide else 0
        measured = dict(qbs_commands=128,useful_pairs=33554432,dot_issue_count=1024 if wide else 2048,
                        qbs_busy_cycles=5000-saved,preparation_cycles=1000,execution_cycles=8000-saved,
                        region_cycles=10000-saved,
                        parts=[dict(checksum=p,fcsr=9,vcsr=5,execution=(4000-saved if p==0 else 2000)) for p in range(3)])
        reports.append(dict(wide=wide,build='same',elf_sha256='same',measured=measured,
                            activity=[dict(counters={key:1 for key in keys}) for _ in N]))
    raw = []
    for wide in (0,1):
        row = {key:1 for key in keys};row['weight_prefetch_wait_cycles'] = wide
        for i,key in enumerate(WAIT):row[key] = wide if i==0 else 0
        raw.append([dict(row) for _ in range(128)])
    return reports,raw


class FullProjectionDiagnosisTests(unittest.TestCase):
    def test_exact_causal_identity(self):
        value = explain(*fixture())
        self.assertEqual(value['dot_issue_cycles_saved'],1024)
        self.assertEqual(value['additional_strict_weight_wait'],128)
        self.assertEqual(value['qbs_busy_cycles_saved'],896)

    def test_work_and_unexplained_cycles_cannot_be_hidden(self):
        reports,raw = fixture();raw[1][0]['r_beats'] += 1
        with self.assertRaises(ValueError):explain(reports,raw)
        reports,raw = fixture();reports[1]['measured']['region_cycles'] += 1
        with self.assertRaises(ValueError):explain(reports,raw)
        reports,raw = fixture();raw[1][0][WAIT[0]] += 1
        with self.assertRaises(ValueError):explain(reports,raw)


if __name__ == '__main__':unittest.main()
