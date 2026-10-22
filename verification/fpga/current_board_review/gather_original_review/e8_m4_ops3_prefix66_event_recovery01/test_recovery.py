"""Host checks for the event-format correction; no DUT or raw CSV execution."""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'e8_m4_ops3_prefix66_vcs_m6_plan01'
TRACE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/verification/ara_verify/trace.py')
sys.path.insert(0, str(OLD))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


fixed = load(HERE / 'checker.py', 'gather_event_corrected_checker')
fixtures = load(OLD / 'test_host.py', 'gather_original_host_fixtures')
trace = load(TRACE, 'gather_frozen_event_rules')


def metadata(event, cycle=0):
    return dict(cycle=str(cycle), event=event, order='0', port='0', trans_id='0',
                pc='80000000', insn='00805073', rd='0', rd_wdata='0',
                mem_addr='0', mem_rmask='00', mem_wmask='00', mem_wdata='0', trap='0')


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = fixtures.synthetic_spec()
        cls.gold = fixed.model()

    def rows(self, fault=None):
        for event in ('arch_start', 'uop_alloc', 'uop_done'):
            yield metadata(event)
        yield from fixtures.fixture(self.spec, self.gold, fault)

    def test_complete_source_with_known_metadata(self):
        report = fixed.retirement(self.rows(), self.spec, self.gold)
        self.assertEqual((report['fullcap_checks'], report['guards']), (33792, 132))
        self.assertEqual(report['routine_retire_counts'], [66] * 13)
        self.assertEqual(report['returned_vstart_zero'], 66)

    def test_old_checker_rejects_legitimate_metadata(self):
        with self.assertRaisesRegex(ValueError, 'Cycle reversal/unknown event'):
            fixtures.c.retirement(self.rows(), self.spec, self.gold)

    def test_unknown_event_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Cycle reversal/unknown event'):
            fixed.retirement(iter([metadata('invented_event')]), self.spec, self.gold)

    def test_cycle_reversal_still_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Cycle reversal/unknown event'):
            fixed.retirement(iter([metadata('arch_start', 2), metadata('uop_alloc', 1)]), self.spec, self.gold)

    def test_original_data_and_csr_negatives(self):
        for fault in ('prestart', 'tail', 'inactive', 'guard0', 'guard1', 'vstart'):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                fixed.retirement(self.rows(fault), self.spec, self.gold)

    def protocol(self, change=None):
        rows = [metadata(event, i) for i, event in enumerate(
            ('arch_start', 'cvx_req', 'uop_alloc', 'uop_done', 'cvx_resp', 'retire'))]
        if change == 'missing_done':
            rows = [r for r in rows if r['event'] != 'uop_done']
        elif change == 'wrong_instruction':
            rows[2]['insn'] = '00000057'
        elif change == 'wrong_response':
            rows[4]['trans_id'] = '1'
        with tempfile.TemporaryDirectory(dir=HERE) as folder:
            path = Path(folder) / 'synthetic_protocol.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return trace.validate_trace(path)

    def test_frozen_generic_checks_metadata_protocol(self):
        report = self.protocol()
        self.assertEqual(report['architecture_request_count'], 1)
        self.assertEqual(report['backend_uop_alloc_count'], 1)
        self.assertEqual(report['backend_uop_done_count'], 1)

    def test_bad_metadata_protocol_still_rejected(self):
        for change in ('missing_done', 'wrong_instruction', 'wrong_response'):
            with self.subTest(change=change), self.assertRaises(trace.TraceValidationError):
                self.protocol(change)


if __name__ == '__main__':
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests))
    print(output.getvalue(), end='')
    paths = [Path(__file__), HERE / 'checker.py', OLD / 'checker.py', OLD / 'test_host.py', TRACE]
    report = dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'NOT_ACCEPTED_HOST',
                  tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  pins={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  raw_CSV_reads=0, DUT_runs=0, log=output.getvalue())
    with (HERE / 'host.json').open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
