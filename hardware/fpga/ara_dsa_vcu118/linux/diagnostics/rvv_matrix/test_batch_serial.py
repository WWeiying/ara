import copy
import io
import hashlib
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from batch_serial import (command, observe, verify, save_report, cleanup_race_report,
                          collect_snapshot_pair, SnapshotCleanupRace)
from audit import audit
from guest_batch import script
from batch_width_suite import arguments

RUN_ID = '0123456789abcdef'


class Port:
    def __init__(self, chunks, clock, broken=False):
        self.chunks = iter(chunks)
        self.clock = clock
        self.sent = bytearray()
        self.broken = broken

    def write(self, data):
        self.sent.extend(data)
        return 0 if self.broken else len(data)

    def read(self, size):
        self.clock[0] += 1
        return next(self.chunks, b'')


class BatchSerialTests(unittest.TestCase):
    def test_snapshot_pair_retries_whole_pair_after_cleanup_failure(self):
        values = iter([1, SnapshotCleanupRace('cleanup'), 3, 4])
        def capture():
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return value
        self.assertEqual(collect_snapshot_pair(capture), [3, 4])

    def test_snapshot_pair_retry_is_bounded_and_other_errors_propagate(self):
        calls = []
        def cleanup_failure():
            calls.append(1)
            raise SnapshotCleanupRace('cleanup')
        with self.assertRaises(SnapshotCleanupRace):
            collect_snapshot_pair(cleanup_failure)
        self.assertEqual(len(calls), 2)
        calls.clear()
        def other_failure():
            calls.append(1)
            raise RuntimeError('connection error')
        with self.assertRaises(RuntimeError):
            collect_snapshot_pair(other_failure)
        self.assertEqual(len(calls), 1)

    def test_cleanup_retry_requires_matching_error_and_snapshot_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = dict(command='snapshot', state='failed',
                          error='Owned Vivado tree cleanup failed: child exited')
            (root/'report.json').write_text(json.dumps(report))
            self.assertFalse(cleanup_race_report(root))
            (root/'snapshot.json').write_text('{}')
            self.assertTrue(cleanup_race_report(root))
            report['error'] = 'hardware server disconnected'
            (root/'report.json').write_text(json.dumps(report))
            self.assertFalse(cleanup_race_report(root))

    def test_report_reader_lock_is_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'report.json'
            calls, delays = [], []
            def replace(source, target):
                calls.append((source, target))
                if len(calls) < 3:
                    raise PermissionError('reader lock')
                source.replace(target)
            save_report(path, {'state': 'running'}, replace, delays.append)
            self.assertEqual(json.loads(path.read_text()), {'state': 'running'})
            self.assertEqual(delays, [.1, .1])

    def test_permanent_report_failure_keeps_temporary_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'report.json'
            def replace(source, target):
                raise PermissionError('persistent failure')
            with self.assertRaises(PermissionError):
                save_report(path, {'state': 'running'}, replace, lambda _: None)
            self.assertEqual(json.loads(path.with_name('report.json.tmp').read_text()),
                             {'state': 'running'})

    def manifest(self):
        return dict(archive_sha256='a'*64, cases=[dict(name='case_0', sha256='b'*64,
            pass_marker='PASS', timeout_seconds=180), dict(name='case_1', sha256='c'*64,
            pass_marker='PASS', timeout_seconds=180)])

    def observe(self, chunks, snapshots=lambda: [], broken=False):
        clock = [0]
        port = Port(chunks, clock, broken)
        log = io.BytesIO()
        saved = []
        launch = command('/tmp/width_0123456789ab', 'd'*64)
        report = observe(port, self.manifest(), RUN_ID, launch, log,
            lambda r: saved.append(copy.deepcopy(r)), snapshots,
            now=lambda: clock[0], sleep=lambda seconds: None)
        self.assertEqual(bytes(port.sent), launch[:1] if broken else launch)
        self.assertEqual(saved[-1], report)
        return report, log.getvalue()

    def test_ordinary_failure_does_not_pause_next_case(self):
        lines = (f'RVVB:{RUN_ID}:PREP:0:case_0\nRVVB:{RUN_ID}:START:0:case_0\n'
                 f'FAIL cases=2\nRVVB:{RUN_ID}:END:0:case_0:1\n'
                 f'RVVB:{RUN_ID}:PREP:1:case_1\nRVVB:{RUN_ID}:START:1:case_1\n'
                 f'PASS cases=3\nRVVB:{RUN_ID}:END:1:case_1:0\nRVVB:{RUN_ID}:DONE:2\n').encode()
        report, raw = self.observe([bytes([b]) for b in lines])
        self.assertEqual(raw, lines)
        self.assertTrue(audit(self.manifest(), report)['complete'])
        self.assertEqual([r['status'] for r in report['results']], ['failed', 'passed'])

    def test_preparation_abort_is_not_case_execution(self):
        report, _ = self.observe([f'RVVB:{RUN_ID}:PREP:0:case_0\nRVVB:{RUN_ID}:ABORT:0:case_0:hash_mismatch\n'.encode()])
        self.assertEqual(report['results'], [])
        self.assertEqual(report['state'], 'preparation_failed')

    def test_missing_protocol_and_write_failure_do_not_reset(self):
        for broken in (True, False):
            report, _ = self.observe([], broken=broken)
            self.assertEqual(report['results'], [])
            self.assertEqual(report['state'], 'scene_preserved_incomplete')
            self.assertFalse(report['board_reset'])

    def test_unsafe_launch_rejected(self):
        for directory in ('/tmp/width_abc; reboot', '/opt/tests', '/tmp/width_0123456789ab\n'):
            with self.assertRaises(ValueError):
                command(directory, 'd'*64)
        with self.assertRaises(ValueError):
            command('/tmp/width_0123456789ab', 'd'*63)

    def test_launch_hash_gate_without_external_cut(self):
        launch = command('/tmp/width_0123456789ab', 'd'*64).decode()
        self.assertNotIn('cut', launch)
        # Override commands in the shell, without touching a guest directory.
        for digest, status, should_run in [('d'*64, 0, True),
                                          ('e'*64, 0, False),
                                          ('d'*64, 1, False),
                                          ('', 0, False)]:
            setup = ('cd() { :; }; '
                     f'sha256sum() {{ printf "%s  batch.sh\\n" "{digest}"; return {status}; }}; '
                     'sh() { printf "EXECUTED"; }; ')
            result = subprocess.run(['/bin/sh', '-c', setup + launch],
                                    capture_output=True, text=True)
            self.assertEqual(result.stdout, 'EXECUTED' if should_run else '')
            self.assertEqual(result.returncode == 0, should_run)

    def test_legacy_wrapper_arguments_keep_original_image_paths(self):
        args = arguments(['--reuse-directory', '/tmp/width_0123456789ab'], Path('/prepared/resume'))
        self.assertEqual(args.root, Path('/prepared/resume'))
        self.assertEqual(args.guest_directory, '/tmp/width_0123456789ab')
        self.assertEqual(args.port, 'COM6')
        self.assertIn('ara_dual_bitgen_20261006_01', str(args.probes))
        self.assertIn('ara_dual_linux_memory_20261006_01', str(args.host_tools))

    def test_script_manifest_and_protocol_must_agree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m = self.manifest()
            content = script(m, RUN_ID).encode()
            protocol = dict(inputs=m, run_id=RUN_ID,
                            script_sha256=hashlib.sha256(content).hexdigest())
            (root/'batch.sh').write_bytes(content)
            (root/'transfer_manifest.json').write_text(json.dumps(m))
            (root/'batch_protocol.json').write_text(json.dumps(protocol))
            self.assertEqual(verify(root), (m, protocol))
            (root/'batch.sh').write_bytes(content+b'echo altered\n')
            with self.assertRaises(ValueError):
                verify(root)
            (root/'batch.sh').write_bytes(content)
            protocol['inputs']['cases'].reverse()
            (root/'batch_protocol.json').write_text(json.dumps(protocol))
            with self.assertRaises(ValueError):
                verify(root)

    def test_live_stall_requires_two_snapshots(self):
        first = dict(identity=dict(frequency_hz=50), core=dict(cycles=100, retired=7,
                     trap_count=2, last_pc=10, head_pc=14), watchdog_snapshot=False,
                     live=dict(flags=0))
        last = copy.deepcopy(first)
        last['core']['cycles'] = 301
        report, _ = self.observe([
            f'RVVB:{RUN_ID}:PREP:0:case_0\nRVVB:{RUN_ID}:START:0:case_0\n'.encode()],
            snapshots=lambda: [first, last])
        self.assertEqual(report['results'][0]['status'], 'stalled')
        self.assertTrue(report['progress_diagnosis']['stalled'])
        self.assertFalse(report['board_reset'])


if __name__ == '__main__':
    unittest.main()
