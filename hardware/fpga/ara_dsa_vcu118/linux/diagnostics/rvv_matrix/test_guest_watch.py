import copy
import unittest
from audit import audit
from guest_watch import Watch, no_retirement


RUN_ID = '0123456789abcdef'


def samples(progress=False):
    a = dict(identity=dict(frequency_hz=50), core=dict(cycles=100, retired=7,
             trap_count=2, last_pc=10, head_pc=14), watchdog_snapshot=False,
             live=dict(flags=0))
    b = copy.deepcopy(a)
    b['core']['cycles'] = 301
    if progress:
        b['core']['retired'] += 1
    return [a, b]


class WatchTests(unittest.TestCase):
    def watch(self, snapshot=lambda: samples()):
        m = dict(archive_sha256='a'*64, cases=[dict(name='case_0',
                 sha256='b'*64, pass_marker='PASS', timeout_seconds=300)])
        return Watch(m, RUN_ID, 0, snapshot)

    def start(self, watch):
        watch.feed(f'RVVB:{RUN_ID}:PREP:0:case_0\nRVVB:{RUN_ID}:START:0:case_0\n'.encode(), 5)

    def test_live_stall_is_preserved(self):
        w = self.watch()
        self.start(w)
        w.tick(125)
        self.assertTrue(w.terminal)
        self.assertEqual(w.report['results'][0]['status'], 'stalled')
        self.assertTrue(w.report['progress_diagnosis']['stalled'])
        self.assertFalse(audit(w.parser.manifest, w.report)['complete'])

    def test_short_case_samples_before_expiry_without_changing_deadline(self):
        for progress in (False, True):
            w = self.watch(lambda: samples(progress))
            w.parser.manifest['cases'][0]['timeout_seconds'] = 30
            self.start(w)
            w.tick(34)
            self.assertFalse(w.checked)
            w.tick(35)
            self.assertTrue(w.terminal)
            self.assertEqual(w.report['results'][0]['status'], 'incomplete' if progress else 'stalled')
            self.assertEqual(w.report['progress_diagnosis']['stalled'], not progress)
            self.assertEqual(w.parser.manifest['cases'][0]['timeout_seconds'], 30)

    def test_progress_then_timeout_is_not_confirmed_stall(self):
        w = self.watch(lambda: samples(True))
        self.start(w)
        w.tick(125)
        self.assertFalse(w.terminal)
        w.tick(305)
        self.assertEqual(w.report['results'][0]['status'], 'incomplete')
        self.assertFalse(w.report['progress_diagnosis']['stalled'])

    def test_telemetry_error_preserves_incomplete(self):
        def broken():
            raise TimeoutError('JTAG unavailable')
        w = self.watch(broken)
        self.start(w)
        w.tick(125)
        self.assertEqual(w.report['results'][0]['status'], 'incomplete')
        self.assertNotIn('progress_diagnosis', w.report)

    def test_preparation_timeout_does_not_attempt_case(self):
        w = self.watch()
        w.tick(60)
        self.assertTrue(w.terminal)
        self.assertEqual(w.report['results'], [])

    def test_completed_case_and_split_utf8(self):
        w = self.watch()
        self.start(w)
        data=('diagnostic \u03bb\nPASS cases=3\n'+f'RVVB:{RUN_ID}:END:0:case_0:0\nRVVB:{RUN_ID}:DONE:1\n').encode()
        for byte in data:
            w.feed(bytes([byte]), 8)
        self.assertEqual(w.report['results'][0]['seconds'], 3)
        self.assertIn('\u03bb', w.report['results'][0]['output'])
        self.assertTrue(audit(w.parser.manifest, w.report)['passed'])

    def test_panic_and_bad_protocol_stop(self):
        for text in ('Kernel panic: failure\n', f'RVVB:{RUN_ID}:END:9:case_0:0\n'):
            w = self.watch()
            self.start(w)
            w.feed(text.encode(), 7)
            self.assertTrue(w.terminal)
            self.assertEqual(w.report['results'][0]['status'], 'incomplete')

    def test_halted_or_trapping_core_is_not_live_stall(self):
        for kind in ('watchdog', 'flags', 'trap', 'short'):
            pair = samples()
            if kind == 'watchdog': pair[1]['watchdog_snapshot'] = True
            if kind == 'flags': pair[1]['live']['flags'] = 1
            if kind == 'trap': pair[1]['core']['trap_count'] += 1
            if kind == 'short': pair[1]['core']['cycles'] = 150
            self.assertFalse(no_retirement(pair))

    def test_completion_buffered_during_snapshot_is_not_stall(self):
        w = self.watch()
        self.start(w)
        w.drain = lambda watch: watch.feed(
            f'PASS cases=3\nRVVB:{RUN_ID}:END:0:case_0:0\nRVVB:{RUN_ID}:DONE:1\n'.encode(), 130)
        w.tick(125)
        self.assertTrue(audit(w.parser.manifest, w.report)['passed'])
        self.assertNotIn('progress_diagnosis', w.report)
        self.assertTrue(w.report['diagnostic_history'][0]['stale_case'])

    def test_next_case_does_not_inherit_previous_case_snapshot(self):
        m = dict(archive_sha256='a'*64, cases=[dict(name=f'case_{i}',
                 sha256='b'*64, pass_marker='PASS', timeout_seconds=300) for i in (0, 1)])
        w = Watch(m, RUN_ID, 0, lambda: samples())
        self.start(w)
        w.drain = lambda watch: watch.feed(
            f'PASS cases=3\nRVVB:{RUN_ID}:END:0:case_0:0\nRVVB:{RUN_ID}:PREP:1:case_1\nRVVB:{RUN_ID}:START:1:case_1\n'.encode(), 130)
        w.tick(125)
        self.assertFalse(w.terminal)
        self.assertEqual(w.report['results'][-1]['status'], 'running')
        self.assertFalse(w.checked)
        self.assertNotIn('progress_diagnosis', w.report)


if __name__ == '__main__':
    unittest.main()
