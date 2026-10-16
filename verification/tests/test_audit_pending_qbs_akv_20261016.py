"""Focused negative tests for standalone QBS/AKV current-output acceptance."""
import json
import csv
import copy
from pathlib import Path
import sys
import tempfile
import unittest
from types import FunctionType
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import audit_pending_qbs_akv_20261016 as audit


class PendingQbsAkvTests(unittest.TestCase):
    def reset_inputs(self, index=746):
        import qualify_gap113_cached_reset as epochs
        run = audit.ROOT / f'verification/out/pending-qbs-akv-audit-20261016-03/e{index:04d}/runtime'
        _, commits = epochs.read_csv(run / 'commit_trace.csv')
        _, vectors = epochs.read_csv(run / 'vector_trace.csv')
        split, _ = epochs.split_epochs(commits, vectors)
        return run, split

    def test_all_four_reset_original_event_predicates(self):
        for index in sorted(audit.RESETS):
            run, split = self.reset_inputs(index)
            with self.subTest(index=index):
                proof = audit.reset_event_predicates(run / 'run.vcs.log', run / 'vector_trace.csv', split)
                original = proof['original_uvm_checker']
                self.assertEqual(original['uvm_event_sha256'], original['contract_event_sha256'])
                self.assertEqual(original['uvm_backend_event_sha256'], original['vector_backend_event_sha256'])
                self.assertEqual([e['aborted'] for e in proof['independent_event_audit']['cvx_epochs']], [0, 0])
                self.assertTrue(proof['original_issue_allowlist_unmodified'])

    def test_reset_rejects_missing_independent_cvx_and_backend_events(self):
        run, split = self.reset_inputs()
        lines = (run / 'run.vcs.log').read_text().splitlines(keepends=True)
        for tag in ('[CVXIF/EVENT]', '[ARA_CONTRACT_TRACE]', '[VID/EVENT]'):
            index = next(i for i, line in enumerate(lines) if tag in line)
            with self.subTest(tag=tag), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'mutated.log'
                path.write_text(''.join(lines[:index] + lines[index+1:]))
                with self.assertRaises(ValueError):
                    audit.reset_event_predicates(path, run / 'vector_trace.csv', split)

    def test_reset_rejects_commit_owner_mismatch_in_each_epoch(self):
        run, split = self.reset_inputs()
        for epoch in (0, 1):
            mutated = copy.deepcopy(split)
            row = next(r for r in mutated[epoch][0] if r['event'] == 'cvx_req')
            row['trans_id'] = str(int(row['trans_id']) ^ 1)
            with self.subTest(epoch=epoch), self.assertRaisesRegex(ValueError, 'Commit/CVXIF owners differ'):
                audit.reset_event_predicates(run / 'run.vcs.log', run / 'vector_trace.csv', mutated)

    def test_reset_rejects_backend_digest_and_unallowlisted_original_issue(self):
        from ara_verify.uvm_dut import check_real_uvm_log
        run, split = self.reset_inputs()
        original = check_real_uvm_log(run / 'run.vcs.log', require_events=True, require_backend=True,
            require_axi=True, vector_trace=run / 'vector_trace.csv', reset_kind='state')
        for name, change, reason in (
            ('backend', dict(vector_backend_event_sha256='0' * 64), 'Independent UVM/vector backend trace differs'),
            ('allowlist', dict(issues=original['issues'] + ['unexpected strict checker diagnostic']),
             'Unexpected original UVM checker diagnostic'),
        ):
            with self.subTest(name=name), patch('ara_verify.uvm_dut.check_real_uvm_log', return_value=dict(original, **change)), \
                    self.assertRaisesRegex(ValueError, reason):
                audit.reset_event_predicates(run / 'run.vcs.log', run / 'vector_trace.csv', split)

    def test_reset_rejects_pending_owner_at_epoch_terminal(self):
        import qualify_qbs_affine_external_reset as q
        run, split = self.reset_inputs()
        original = audit.reset_event_predicates(run / 'run.vcs.log', run / 'vector_trace.csv', split)['original_uvm_checker']
        traffic = q.events.traffic
        for epoch in (0, 1):
            calls = []
            def pending(events):
                result = traffic(events)
                if len(calls) == epoch:
                    result = dict(result, aborted=1)
                calls.append(result)
                return result
            with self.subTest(epoch=epoch), patch.object(q.events, 'traffic', side_effect=pending), \
                    self.assertRaisesRegex(ValueError, 'Accepted CVXIF owner remained pending'):
                q.event_audit((run / 'run.vcs.log').read_text(), split, original)

    def test_scope(self):
        for name in ('qbs_affine_slot0_aux_external_reset', 'vakv_column_boundary_v2', 'akv_descriptor_entropy'):
            self.assertTrue(audit.selected(dict(status='CHECKER_REQUIRED', coverage_test=name)))
        self.assertFalse(audit.selected(dict(status='PASS', coverage_test='qbs_pending')))
        self.assertFalse(audit.selected(dict(status='CHECKER_REQUIRED', coverage_test='rvv_qbs_suffix')))

    def test_clean_exit_and_microstructure_do_not_accept_architecture(self):
        components = dict(execution=dict(status='PASS'), microstructure=dict(status='PASS'))
        self.assertEqual(audit.verdict(components, {'execution', 'architecture'}), 'CHECKER_REQUIRED')
        components['architecture'] = dict(status='FAIL')
        self.assertEqual(audit.verdict(components, {'execution', 'architecture'}), 'FAIL')

    def test_missing_required_wave_is_hold(self):
        components = dict(execution=dict(status='PASS'), architecture=dict(status='PASS'))
        self.assertEqual(audit.verdict(components, {'execution', 'architecture'}), 'PASS')
        self.assertEqual(audit.verdict(components, {'execution', 'architecture', 'microstructure'}), 'CHECKER_REQUIRED')

    def test_error_classification(self):
        with tempfile.TemporaryDirectory() as directory:
            a = object.__new__(audit.Audit)
            a.out = Path(directory)
            a.run = Path('e0000')
            a.components = {}
            def fail(error):
                raise error
            for name, error, status in (
                ('numerical', ValueError('Independent accepted VRF byte differs'), 'FAIL'),
                ('source', ValueError('Frozen comparator drift'), 'CHECKER_REQUIRED'),
                ('missing', FileNotFoundError('current vector trace missing'), 'CHECKER_REQUIRED'),
            ):
                a.check(name, lambda error=error: fail(error), 'strict original')
                self.assertEqual(a.components[name]['status'], status)
                self.assertEqual(json.loads((a.out / (name + '.json')).read_text())['status'], status)

    def test_original_qbs_readback_rejects_one_bit_corruption(self):
        import qualify_gap105_native_v5 as q
        row = dict(event='retire', cycle='1', mem_addr='80000000', mem_rmask='ff',
                   insn='00053283', pc='80000100', rd='5', trap='0', rd_wdata='0123456789abcdef')
        expected = bytes.fromhex('efcdab8967452301')
        symbols = dict(actual=(0x80000000, 8))
        q.readback([row], 0, 2, symbols, dict(actual=expected))
        row['rd_wdata'] = '0123456789abcdee'
        with self.assertRaisesRegex(ValueError, 'Readback differs'):
            q.readback([row], 0, 2, symbols, dict(actual=expected))

    def test_bind_rejects_reference_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            a = object.__new__(audit.Audit)
            a.inputs = {}
            p = Path(directory) / 'reference.json'
            p.write_text('{}')
            a.bind(p)
            p.write_text('{"changed":true}')
            with self.assertRaisesRegex(ValueError, 'Input drift'):
                a.bind(p)

    def test_sd_successor_source_contract_bound_to_current_build(self):
        import collect_akv_canonical_alias794_sd_v2 as q
        book = audit.ROOT / 'verification/out/full-regression-build-20261015-01/build-source-pins.json'
        gate = FunctionType(q.source.__code__, dict(q.source.__globals__, BOOK=book, BOOK_SHA=audit.sha(book)))
        pins = gate()
        self.assertEqual(pins[str(q.CSR)], audit.sha(q.CSR))
        self.assertEqual(pins[str(book)], audit.sha(book))

    def test_sd_successor_retains_precise_model_and_no_skips(self):
        import collect_akv_canonical_alias794_sd_v2 as q
        self.assertEqual(q.derived_status(3 << 13), (1 << 63) | (3 << 13))
        self.assertEqual(q.derived_status(1 << 63), 0)
        with self.assertRaises(ValueError):
            q.derived_status(1 << 15)

    def test_gap65_native_snapshot_corruption_and_missing_load_rejected(self):
        base = 0x80002dc0
        gold = list(range(16))
        rows = []
        for phase in (0, 1):
            for i in range(128):
                addr = base + i * 4
                value = 0x41800000 + 7919 * i if phase == 0 else (gold[(i // 32) * 4 + i % 32] if i % 32 < 4 else 0)
                rows.append(dict(event='retire', mem_rmask=f'{15 << (addr & 7):x}', mem_addr=f'{addr:x}',
                                 insn='00004384', pc='80000fc2', rd='9', trap='0', rd_wdata=f'{value:x}'))
        self.assertEqual(audit.gap65_snapshots(rows, base, gold)['actual_native_scalar_loads'], 256)
        with self.assertRaisesRegex(ValueError, 'Complete two'):
            audit.gap65_snapshots(rows[:-1], base, gold)
        for index in (0, 127, 128, 131, 132, 255):
            corrupt = list(rows)
            corrupt[index] = dict(corrupt[index], rd_wdata=f'{int(corrupt[index]["rd_wdata"], 16) ^ 1:x}')
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'snapshot mismatch'):
                audit.gap65_snapshots(corrupt, base, gold)

    def test_gap65_replay_all_native_packet_regions_and_corruption(self):
        import audit_pending_qbs_akv_gap65_replay_20261016 as replay
        proof = json.loads((audit.ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04/elf-proof.json').read_text())
        regions = replay.phase_regions(proof, 1)
        rows = []
        for name, (address, data) in regions.items():
            for offset in range(0, len(data), 8):
                rows.append(dict(event='retire', cycle='1', mem_rmask='ff', mem_addr=f'{address+offset:x}',
                    insn='00053283', rd='5', trap='0', rd_wdata=f'{int.from_bytes(data[offset:offset+8], "little"):x}'))
        self.assertEqual(replay.readback(rows, 0, 2, regions)['gap65_csrs'], 224)
        for name in ('gap65_csrs', 'gap65_trap', 'gap65_boot', 'stack_low', 'stack_high', 'tail', 'gap65_activation'):
            address = regions[name][0]
            index = next(i for i, r in enumerate(rows) if int(r['mem_addr'], 16) == address)
            mutated = list(rows)
            mutated[index] = dict(mutated[index], rd_wdata=f'{int(mutated[index]["rd_wdata"], 16) ^ 1:x}')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'byte mismatch'):
                replay.readback(mutated, 0, 2, regions)

    def test_gap65_replay_actual_vector_and_metadata_negative(self):
        import audit_pending_qbs_akv_gap65_replay_20261016 as replay
        work = audit.ROOT / 'verification/out/pending94-e0650-replay-20261016-01/work'
        proof = json.loads((audit.ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04/elf-proof.json').read_text())
        with (work / 'commit_trace.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        a = SimpleNamespace(work=work, runtime=work, bind=lambda p: p)
        self.assertEqual(replay.vectors(a, rows, proof)['recovery_write_bytes'], 512)
        with (work / 'vector_trace.csv').open() as stream:
            reader = csv.DictReader(stream)
            fields, vector = reader.fieldnames, list(reader)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'vector_trace.csv'
            index = next(i for i, r in enumerate(vector) if r['event'] == 'alloc' and r['use_vd'] == '0')
            vector[index]['vl'] = '127'
            with path.open('w') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(vector)
            a.work = Path(directory)
            with self.assertRaisesRegex(ValueError, 'M4 activity/lifecycle metadata'):
                replay.vectors(a, rows, proof)


if __name__ == '__main__':
    unittest.main()
