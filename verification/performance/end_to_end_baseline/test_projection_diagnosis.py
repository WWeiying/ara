import copy
import unittest

from check_projection_native import check, fields
from diagnose_projection_pair import explain, WAIT
from test_projection_native import fixture


def paired_fixture():
    reports = []; raw = []
    for wide in (0, 1):
        text, golden = fixture(wide)
        if wide:
            text = text.replace('busy_cycles=10000','busy_cycles=6250').replace(
                'execution=40000','execution=25000').replace('execution=120000','execution=75000').replace(
                'region=120200','region=75200')
        measured = check(text, wide, golden)
        reports.append(dict(wide=wide, build='same', elf_sha256='same', measured=measured))
        commands = [fields(line, '[QBS_PERF]') for line in text.splitlines() if line.startswith('[QBS_PERF] ')]
        for command in commands:
            for key in ('ar','r_beats','payload_bytes','weight_bytes','activation_bytes','fp_uop_issue','accumulator_updates'):
                command[key] = 10
            command['weight_prefetch_wait_cycles'] = 346 if wide else 0
            command.update({k:0 for k in WAIT})
            if wide:
                command[WAIT[0]] = 14; command[WAIT[2]] = 332
        raw.append(commands)
    return reports, raw


class ProjectionDiagnosisTests(unittest.TestCase):
    def test_causal_accounting_and_scope(self):
        result = explain(*paired_fixture())
        self.assertEqual(result['dot_issue_cycles_saved'],98304)
        self.assertEqual(result['extra_strict_weight_wait'],8304)
        self.assertEqual(result['qbs_busy_cycles_saved'],90000)
        self.assertIn('N=128',result['not_model_fraction'])

    def test_reject_nonconserved_work_wait_and_cpu_changes(self):
        reports, raw = paired_fixture()
        changed = copy.deepcopy(raw); changed[1][0]['payload_bytes'] += 1
        with self.assertRaises(ValueError): explain(reports,changed)
        changed = copy.deepcopy(raw); changed[1][0][WAIT[2]] += 1
        with self.assertRaises(ValueError): explain(reports,changed)
        changed = copy.deepcopy(reports); changed[1]['measured']['preparation_cycles'] += 1
        with self.assertRaises(ValueError): explain(changed,raw)


if __name__ == '__main__': unittest.main()
