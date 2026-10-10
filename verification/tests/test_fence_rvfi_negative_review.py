"""Review contract tests; rejected historical artifacts are fixtures, never admitted.

The rejection tests require malformed evidence to fail closed.
All trace mutations and wrapper mocks are in memory. No simulator, collector,
worker, result writer, or downstream aggregate is executed.
"""
import copy
import csv
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
import fence_rvfi_audit as audit
import run_fence_rvfi_checked_extension as wrapper

BUILD = ROOT / 'verification/out/gap36-fence-20261004-01'
FIXTURE = ROOT / 'verification/out/gap36-fence-current-20261004-02'
ARTIFACT = (FIXTURE / 'results/fence_t_gap36_smoke/tests/'
            'app_fence_t_gap36_smoke')
HEX_FIELDS = {'pc', 'insn', 'rd_wdata', 'mem_addr', 'mem_rmask',
              'mem_wmask', 'mem_wdata'}


def serialize(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=audit.FIELDS, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: format(value, 'x') if key in HEX_FIELDS else value
                         for key, value in row.items()})
    return stream.getvalue()


class FenceRvfiNegativeReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metadata = wrapper.full.read(BUILD / 'elf_metadata.json')[0]
        cls.blob = (BUILD / 'fence_t_gap36_smoke.elf').read_bytes()
        cls.sites = wrapper.full.read(BUILD / 'precheck.json')['elf_audit']['sites']
        cls.rows = audit.parse_trace((ARTIFACT / 'commit_trace.csv').read_text())
        cls.fences = [i for i, row in enumerate(cls.rows) if row['insn'] == 0xb]

    def evaluate(self, rows):
        return audit.audit(serialize(rows), self.metadata, self.blob, self.sites)

    def test_fixture_capture_consistency_only(self):
        result = self.evaluate(self.rows)
        self.assertEqual(result['capture_stores_checked'], 130)
        self.assertFalse(wrapper.full.read(
            FIXTURE / 'outcomes/fence_t_gap36_smoke.json')['passed_only'])

    def test_reject_fence_memory_side_effects(self):
        for fence in self.fences:
            for mask in ('mem_rmask', 'mem_wmask'):
                with self.subTest(fence=fence, mask=mask):
                    rows = copy.deepcopy(self.rows)
                    rows[fence][mask] = 255
                    rows[fence]['mem_addr'] = rows[fence + 1]['mem_addr']
                    rows[fence]['mem_wdata'] = rows[fence + 1]['mem_wdata']
                    with self.assertRaises(ValueError):
                        self.evaluate(rows)

    def test_reject_fence_register_destination(self):
        for fence in self.fences:
            for index in (fence, fence + 67):
                with self.subTest(index=index):
                    rows = copy.deepcopy(self.rows)
                    rows[index].update(rd=30, rd_wdata=0xdeadbeef)
                    with self.assertRaises(ValueError):
                        self.evaluate(rows)

    def test_reject_capture_store_on_port_one(self):
        for fence in self.fences:
            with self.subTest(fence=fence):
                rows = copy.deepcopy(self.rows)
                rows[fence + 1]['port'] = 1
                with self.assertRaises(ValueError):
                    self.evaluate(rows)

    def test_reject_resume_same_cycle_as_fence(self):
        for fence in self.fences:
            with self.subTest(fence=fence):
                rows = copy.deepcopy(self.rows)
                rows[fence + 1].update(cycle=rows[fence]['cycle'], port=1)
                with self.assertRaises(ValueError):
                    self.evaluate(rows)

    def test_reject_wrong_observer_transaction_placeholder(self):
        rows = copy.deepcopy(self.rows)
        rows[self.fences[0]]['trans_id'] = 7
        with self.assertRaises(ValueError):
            self.evaluate(rows)

    def test_reject_trap_handler_pc_without_trap_bit(self):
        symbols = {item['Symbol']['Name']['Name']: item['Symbol']
                   for item in self.metadata['Symbols']}
        pc = symbols['gap36_trap']['Value']
        rows = copy.deepcopy(self.rows)
        injected = dict(rows[self.fences[0] - 1], pc=pc,
                        insn=audit.elf_instructions(self.metadata, self.blob)[pc],
                        rd=10, rd_wdata=2)
        rows.insert(self.fences[0] - 1, injected)
        for order, row in enumerate(rows):
            row.update(order=order, cycle=2 * order)
        with self.assertRaises(ValueError):
            self.evaluate(rows)


class FenceWrapperNegativeReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = wrapper.full.read(FIXTURE / 'plan.json')
        cls.outcome = wrapper.full.read(FIXTURE / 'outcomes/fence_t_gap36_smoke.json')
        selection = wrapper.full.read(Path(cls.plan['source_selection']['selection']))
        cls.item = next(item for item in selection['cases']
                        if item['name'] == 'app:' + wrapper.legacy.NAME)
        evidence = wrapper.legacy.evidence.Evidence()
        cls.precheck = wrapper.precheck(cls.item, evidence)
        # This is a synthetic in-memory wrapper fixture, not a re-frozen old run.
        cls.plan['files'].update(evidence.files)

    def test_readonly_precheck_binds_new_sources(self):
        self.assertEqual(self.precheck['runtime_contract'],
                         'fence-rvfi-elf-capture-controller-v1')
        for path in (wrapper.SCRIPT, Path(audit.__file__)):
            self.assertIn(str(path), self.plan['files'])

    def test_reject_missing_or_wrong_originating_runtime_hash(self):
        for path in (ARTIFACT / 'commit_trace.csv', ARTIFACT / 'work/run.vcs.log'):
            for missing in (True, False):
                with self.subTest(path=path.name, missing=missing):
                    row = copy.deepcopy(self.outcome)
                    if missing:
                        row['files'].pop(str(path))
                    else:
                        row['files'][str(path)] = '0' * 64
                    # Collection would create a listing, so it is always stubbed.
                    with patch.object(wrapper, 'controller_proof',
                                      return_value={'files': {}}):
                        with self.assertRaises((ValueError, RuntimeError)):
                            wrapper.runtime_proof(FIXTURE, self.plan, row)

    def test_reject_status_only_aggregate_proof(self):
        output = ROOT / 'verification/out/fence-review-not-created'
        report = output / 'results' / wrapper.legacy.NAME / 'fence_runtime_audit.json'
        row = {'status': 'PASS', 'files': {str(report): 'mocked-digest'}}

        def read(path):
            return {'status': 'PASS', 'files': {}} if Path(path) == report else row

        with patch.object(wrapper.full, 'read', side_effect=read), \
                patch.object(wrapper.full, 'check'), \
                patch.object(wrapper.legacy, 'ORIGINAL_SUMMARIZE') as downstream:
            with self.assertRaises((ValueError, RuntimeError)):
                wrapper.summarize(output, {'cases': [{'name': wrapper.legacy.NAME}]})
            downstream.assert_not_called()

    def test_reject_runtime_digest_drift_after_audit(self):
        original_pins = wrapper.full.pins
        for changed in (ARTIFACT / 'commit_trace.csv', ARTIFACT / 'work/run.vcs.log'):
            with self.subTest(path=changed.name):
                def drift(paths):
                    hashes = original_pins(paths)
                    if str(changed) in hashes:
                        hashes[str(changed)] = '0' * 64
                    return hashes

                with patch.object(wrapper, 'controller_proof',
                                  return_value={'files': {}}) as controller, \
                        patch.object(wrapper.full, 'pins', side_effect=drift):
                    with self.assertRaisesRegex(ValueError, 'runtime evidence changed after audit'):
                        wrapper.runtime_proof(FIXTURE, self.plan, self.outcome)
                    controller.assert_called_once_with(
                        FIXTURE, self.plan, self.outcome, replay=False)

    def test_reject_schema_correct_proof_missing_required_files(self):
        controller = {
            'controller_arms': dict.fromkeys((
                'IDLE_to_FLUSH_DCACHE', 'FLUSH_DCACHE_to_DRAIN_REQS',
                'DRAIN_REQS_to_PAD', 'PAD_to_RST_UARCH',
                'RST_UARCH_assert', 'RST_UARCH_counter_finish'), {}),
            'raw_fsm_bits': {}, 'baseline_fsm_bits': {}, 'files': {},
        }
        report = FIXTURE / 'results' / wrapper.legacy.NAME / 'fence_runtime_audit.json'
        outcome_path = FIXTURE / 'outcomes' / (wrapper.legacy.NAME + '.json')
        original_read, original_check = wrapper.full.read, wrapper.full.check

        # Only native collection and the virtual report/aggregate are mocked.
        # Replay still reruns the actual UART, ELF, CSV, and hash checks.
        with patch.object(wrapper, 'controller_proof',
                          side_effect=lambda *args, **kwargs: copy.deepcopy(controller)):
            canonical = wrapper.runtime_proof(FIXTURE, self.plan, self.outcome)
            row = copy.deepcopy(self.outcome)
            row.update(status='PASS', passed_only=True)
            row['files'].update(canonical['files'])
            row['files'][str(report)] = 'virtual-report-digest'
            stored = copy.deepcopy(canonical)

            def read(path):
                if Path(path) == report:
                    return stored
                if Path(path) == outcome_path:
                    return row
                return original_read(path)

            def check(files):
                original_check({path: digest for path, digest in files.items()
                                if path != str(report)})

            with patch.object(wrapper.full, 'read', side_effect=read), \
                    patch.object(wrapper.full, 'check', side_effect=check), \
                    patch.object(wrapper, 'runtime_proof', wraps=wrapper.runtime_proof) as replay, \
                    patch.object(wrapper.legacy, 'ORIGINAL_SUMMARIZE',
                                 return_value='aggregate-stub') as downstream:
                self.assertEqual(wrapper.summarize(FIXTURE, self.plan), 'aggregate-stub')
                replay.assert_called_once_with(FIXTURE, self.plan, row, replay=True)
                for missing in (ARTIFACT / 'commit_trace.csv', ARTIFACT / 'work/run.vcs.log'):
                    with self.subTest(path=missing.name):
                        stored = copy.deepcopy(canonical)
                        del stored['files'][str(missing)]
                        replay.reset_mock()
                        downstream.reset_mock()
                        with self.assertRaisesRegex(ValueError, 'FENCE.T runtime proof replay differs'):
                            wrapper.summarize(FIXTURE, self.plan)
                        replay.assert_called_once_with(FIXTURE, self.plan, row, replay=True)
                        downstream.assert_not_called()


if __name__ == '__main__':
    unittest.main()
