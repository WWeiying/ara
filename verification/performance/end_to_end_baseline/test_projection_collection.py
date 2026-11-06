import json
from pathlib import Path
import tempfile
import unittest

from check_projection_native import check
from collect_projection_native import activity, paired, PHASES, COUNTERS
from test_projection_native import fixture
from watch_projection_pair import terminal


def complete_activity(wide):
    text, golden = fixture(wide)
    lines = []
    for line in text.splitlines():
        if line.startswith('[QBS_PERF] '):
            existing = {word.split('=')[0] for word in line.split()[1:]}
            for key in COUNTERS:
                if key not in existing: line += ' '+key+'=0'
            for phase in PHASES: line += f' phase_{phase}_cycles={10000 if phase == "compute" else 0}'
        lines.append(line)
    return '\n'.join(lines)+'\n', golden


class ProjectionCollectionTests(unittest.TestCase):
    def test_activity_and_same_work_pair(self):
        reports = []
        for wide in (0, 1):
            log, golden = complete_activity(wide); measured = check(log, wide, golden)
            grouped = activity(log, measured)
            self.assertEqual(len(grouped), 6)
            self.assertEqual(grouped[0]['counters']['busy_cycles'], 40000)
            reports.append(dict(wide=wide, build='same', elf_sha256='same', measured=measured))
        self.assertEqual(paired(*reports)['region_ratio'], 1)
        reports[1]['elf_sha256'] = 'different'
        with self.assertRaises(ValueError): paired(*reports)

    def test_activity_rejects_inconsistent_phases(self):
        log, golden = complete_activity(0)
        measured = check(log, 0, golden)
        with self.assertRaises(ValueError):
            activity(log.replace('phase_compute_cycles=10000', 'phase_compute_cycles=10001', 1), measured)

    def test_waiter_distinguishes_pending_pass_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); path = root/'result.json'
            self.assertFalse(terminal(root))
            path.write_text(json.dumps(dict(state='PASS')))
            self.assertTrue(terminal(root))
            for state in ('FAIL', 'PREFLIGHT_NOT_RUN'):
                path.write_text(json.dumps(dict(state=state)))
                with self.assertRaises(ValueError): terminal(root)


if __name__ == '__main__': unittest.main()
