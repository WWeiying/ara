from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import recover_gap65_report_only as r


class HashTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'evidence'
        self.path.write_bytes(b'original')
        self.hasher = Mock(wraps=r.RAW_SHA256)
        self.session = r.HashSession(self.hasher)

    def test_reuse_and_final_rehash_are_distinct(self):
        digest = self.session.digest(self.path)
        self.assertEqual(self.session.digest(self.path), digest)
        self.assertEqual(self.hasher.call_count, 1)
        self.session.reverify()
        self.assertEqual(self.hasher.call_count, 2)
        self.assertEqual(self.session.reverified, 1)

    def test_changed_content_and_restored_mtime_rejected(self):
        self.session.digest(self.path)
        stat = self.path.stat()
        self.path.write_bytes(b'tampered')
        os.utime(self.path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            self.session.digest(self.path)

    def test_replacement_and_deletion_rejected(self):
        self.session.digest(self.path)
        replacement = self.path.with_name('replacement')
        replacement.write_bytes(b'original')
        replacement.replace(self.path)
        with self.assertRaises(ValueError):
            self.session.digest(self.path)
        self.path.unlink()
        with self.assertRaises(OSError):
            self.session.reverify()

    def test_symlink_retarget_rejected(self):
        link = self.path.with_name('link')
        link.symlink_to(self.path)
        self.session.digest(link)
        other = self.path.with_name('other')
        other.write_bytes(b'original')
        link.unlink()
        link.symlink_to(other)
        with self.assertRaises(ValueError):
            self.session.digest(link)

    def test_final_rehash_does_not_trust_stat_or_cached_digest(self):
        self.session.digest(self.path)
        frozen_identity = r.identity(self.path)
        self.path.write_bytes(b'tampered')
        with patch.object(r, 'identity', return_value=frozen_identity):
            with self.assertRaisesRegex(ValueError, 'during final rehash'):
                self.session.reverify()
        self.assertEqual(self.hasher.call_count, 2)

    def test_mutation_during_initial_hash_rejected(self):
        def mutate(path):
            digest = r.RAW_SHA256(path)
            path.write_bytes(b'tampered')
            return digest
        with self.assertRaisesRegex(ValueError, 'while hashing'):
            r.HashSession(mutate).digest(self.path)

    def test_mutation_of_early_input_during_later_final_hash_rejected(self):
        later = self.path.with_name('later')
        later.write_bytes(b'later')
        self.session.digest(self.path)
        self.session.digest(later)
        def mutate_earlier(path):
            digest = r.RAW_SHA256(path)
            if path == later:
                self.path.write_bytes(b'tampered')
            return digest
        self.session.hasher = mutate_earlier
        with self.assertRaisesRegex(ValueError, 'before publication'):
            self.session.reverify()

    def test_conflicting_expected_digest_still_rejected(self):
        with r.report_only(self.session):
            proof = r.sealed.evidence.Evidence()
            proof.pin(self.path, r.RAW_SHA256(self.path))
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                proof.pin(self.path, '0' * 64)

    def test_scoped_aliases_cache_without_modifying_validators(self):
        original = r.full.base.sha256
        validator = r.sealed.baseline_row
        with r.report_only(self.session):
            r.full.base.sha256(self.path)
            r.sealed.observed.sha(self.path)
            r.full.check({str(self.path): r.RAW_SHA256(self.path)})
            self.assertEqual(self.hasher.call_count, 1)
            self.assertIs(r.sealed.baseline_row, validator)
            for command in (lambda: subprocess.Popen(['false']),
                            lambda: r.full.batch.invoke([], None, None),
                            lambda: os.execv('/bin/false', ['false']),
                            lambda: os.system('false')):
                with self.assertRaisesRegex(RuntimeError, 'forbids'):
                    command()
        self.assertIs(r.full.base.sha256, original)

    def test_inventory_addition_rejected(self):
        proof = Mock()
        expected = r.full.base.inventory(Path(self.temp.name))
        (self.path.parent / 'extra').write_bytes(b'new')
        with self.assertRaisesRegex(ValueError, 'inventory differs'):
            r.check_database(proof, self.path.parent, expected)


class CompletedLedgerTests(unittest.TestCase):
    def setUp(self):
        self.runtime = r.sealed.RUNTIME
        self.baseline = r.sealed.BASELINE
        self.plan = dict(gap65_report_only=r.sealed.SCHEMA, baseline=str(self.baseline),
                         baseline_passed=650, cases=[dict(name=r.sealed.ROW)],
                         files={'plan-input': 'bound'}, image={'sim': 'image'})
        self.old = [dict(name=f'old{i}', coverage_test=f'test{i}', elf_sha256=f'elf{i}',
                         vdb=f'/old{i}.vdb') for i in range(650)]
        self.new = dict(name=r.sealed.ROW, coverage_test='gap65', elf_sha256='gap65-elf', vdb='/new.vdb')
        self.collection = dict(status='PASS', total=651, passed=651, baseline_passed=650,
                               new_passed=1, cross_image_reuse=False, excluded=[], counts={'PASS': 1})
        self.documents = {self.baseline / 'checkpoint.json': {'coverage_status': 'COMPLETE'},
                          self.runtime / 'inputs/baseline-ledger.json': self.old,
                          self.runtime / 'outcomes/tests.json': self.new,
                          self.runtime / 'all-outcomes.json': [self.new]}
        self.rows = self.old + [self.new]
        self.proof = Mock()
        self.proof.plan.return_value = self.plan
        self.proof.read.side_effect = self.documents.__getitem__
        self.proof.collection.side_effect = lambda path, image: (
            dict(status='PASS', passed=650, total=650) if path == self.baseline else self.collection)
        self.proof.ledger.side_effect = lambda path, image: self.old if path == self.baseline else self.rows

    def validate(self):
        return r.validate_completed_reports(self.proof, self.runtime)

    def test_every_original_row_preserved(self):
        _, rows, old = self.validate()
        self.assertEqual(len(rows), 651)
        self.assertEqual(old, self.old)
        self.proof.hashes.assert_called_once_with(self.plan['files'])

    def test_replaced_missing_or_reordered_original_ledger_rejected(self):
        for rows in ([*self.old[:-1], self.new], [*reversed(self.old), self.new],
                     [dict(self.old[0], elf_sha256='forged'), *self.old[1:], self.new]):
            self.rows = rows
            with self.subTest(count=len(rows)), self.assertRaises(ValueError):
                self.validate()

    def test_failed_partial_or_cross_image_collection_rejected(self):
        for change in ({'status': 'FAIL'}, {'passed': 650}, {'new_passed': 0},
                       {'cross_image_reuse': True}, {'excluded': ['tests']}, {'counts': {'FAIL': 1}}):
            original = self.collection.copy()
            self.collection.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.validate()
            self.collection = original

    def test_duplicate_gap65_identity_rejected(self):
        for key in ('name', 'coverage_test', 'elf_sha256', 'vdb'):
            value = self.new[key]
            self.new[key] = self.old[0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.new[key] = value

    def test_changed_prepared_baseline_rejected(self):
        self.documents[self.runtime / 'inputs/baseline-ledger.json'] = self.old[:-1]
        with self.assertRaises(ValueError):
            self.validate()


class RowTests(unittest.TestCase):
    def test_full651_oracles_with_one_narrow_hook_no_duplicate_vdb_validation(self):
        proof = Mock()
        rows = [dict(name=f'old{i}', kind='directed', vdb=f'/old{i}', coverage_test=f'test{i}',
                     vdb_files={'x': 'hash'}) for i in range(650)]
        rows.append(dict(name='tests', kind=r.sealed.KIND, vdb='/new', vdb_files={'x': 'hash'}))
        with patch.object(r.full.batch, 'valid_vdb', return_value={'x': 'hash'}) as valid, redirect_stdout(io.StringIO()):
            r.validate_rows(proof, rows, dict(image={'sim': 'hash'}, simv='/sim'))
        self.assertEqual(proof.baseline_row.call_count, 651)
        self.assertEqual(valid.call_count, 650)
        self.assertEqual(proof.hashes.call_count, 651)

    def test_oracle_and_vdb_drift_rejected(self):
        row = dict(name='old', kind='directed', vdb='/old', coverage_test='test', vdb_files={'x': 'hash'})
        proof = Mock()
        proof.baseline_row.side_effect = ValueError('oracle failure')
        with self.assertRaisesRegex(ValueError, 'oracle failure'):
            r.validate_rows(proof, [row], dict(image={}, simv='/sim'))
        proof.baseline_row.side_effect = None
        with patch.object(r.full.batch, 'valid_vdb', return_value={'x': 'forged'}):
            with self.assertRaisesRegex(ValueError, 'VDB validity/hash differs'):
                r.validate_rows(proof, [row], dict(image={}, simv='/sim'))

    def test_narrow_hook_remains_fail_closed(self):
        with r.report_only(r.HashSession()):
            with self.assertRaises(ValueError):
                r.sealed.evidence.Evidence().baseline_row(
                    dict(kind=r.sealed.KIND, name='foreign', coverage_test='foreign'), {}, '/sim')


class RecoveryTests(unittest.TestCase):
    def test_writes_only_independent_completion_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            output = Path(temporary) / 'recovery'
            plan = dict(design_vdb='/design', design_files={'x': 'hash'})
            rows = [dict(vdb='/test', vdb_files={'x': 'hash'})]
            stack.enter_context(patch.object(r, 'validate', return_value=(plan, rows)))
            stack.enter_context(patch.object(r, 'check_database'))
            stack.enter_context(redirect_stdout(io.StringIO()))
            result = r.recover(output)
            self.assertEqual(result['aggregate_passed'], 651)
            self.assertEqual(result['hash_stats']['unique_files'], result['hash_stats']['final_rehashed'])
            checkpoint = json.loads((output / 'checkpoint.json').read_text())
            self.assertEqual(checkpoint['completion_sha256'], r.RAW_SHA256(output / 'completion.json'))
            self.assertFalse(result['tools_launched'])
            self.assertEqual(sorted(p.name for p in output.iterdir()), ['checkpoint.json', 'completion.json'])
            with self.assertRaises(ValueError):
                r.recover(output)

    def test_failed_validation_does_not_publish_completion(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(r, 'validate', side_effect=ValueError('tamper')):
            output = Path(temporary) / 'recovery'
            with self.assertRaisesRegex(ValueError, 'tamper'):
                r.recover(output)
            self.assertFalse((output / 'completion.json').exists())
            self.assertFalse((output / 'checkpoint.json').exists())
            self.assertEqual(json.loads((output / 'rejected.json').read_text())['coverage_status'], 'NOT_ADMITTED')

    def test_missing_dve_report_never_launches_a_tool(self):
        with tempfile.TemporaryDirectory() as temporary, r.report_only(r.HashSession()):
            with self.assertRaises(ValueError):
                r.sealed.report_callback(Path(temporary), {'design_vdb': '/design'}, [], r.sealed.evidence.Evidence())


class DeltaTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.runtime, self.baseline = self.root / 'runtime', self.root / 'baseline'
        self.stack.enter_context(patch.object(r.sealed, 'BASELINE', self.baseline))
        self.stack.enter_context(patch.object(r.sealed, 'report_callback'))
        self.old = [dict(vdb='/old')]
        self.rows = self.old + [dict(name='tests', vdb='/new')]
        self.plan = dict(design_vdb='/design', cases=[dict(coverage_targets=['ara_tb.dut.i_ara_soc.i_system'])])
        metric = {'ara_tb.dut.i_ara_soc.i_system': dict(width=2, checksum='same', bits='0x1')}
        self.before = dict(design={'shape': 'hash'}, tests=['/old'], input_hashes={'/old/data': 'old'},
                           metrics={'fsm': metric})
        self.fresh = dict(design={'shape': 'hash'}, tests=['/new'], input_hashes={'/new/data': 'new'},
                          metrics={'fsm': {k: dict(v, bits='0x2') for k, v in metric.items()}})
        self.merged = r.sealed.targeted.bitmaps.combine(self.before, self.fresh)
        self.gains = r.sealed.targeted.bitmaps.delta(self.before, self.merged)
        self.documents = {self.baseline / 'combined-bits.json': self.before,
                          self.runtime / 'combined-bits.json': self.merged,
                          self.runtime / 'raw-bitmap-delta.json': self.gains,
                          self.runtime / 'per-case-gains.json': [dict(name='tests', new_bits=self.gains['metrics'],
                             target_gains=self.gains['instances'], all_gains=self.gains['instances'])],
                          self.runtime / 'coverage-delta.json': {}}
        for path, content in [(self.runtime / 'combined-inputs.txt', '/design\n/old\n/new\n'),
                              (self.runtime / 'gap65-report-inputs.txt', '/design\n/old\n/new\n'),
                              (self.baseline / 'combined-dve/inputs.txt', '/design\n/old\n'),
                              (self.runtime / 'inputs/tests.vdbs.txt', '/design\n/new\n')]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        self.proof = Mock()
        self.proof.pin.side_effect = lambda path: path
        self.proof.read.side_effect = self.documents.__getitem__
        self.stack.enter_context(patch.object(r.sealed.targeted.bitmaps, 'collect', return_value=self.fresh))
        self.stack.enter_context(patch.object(r.sealed.targeted, 'hierarchy_rows', return_value={}))

    def validate(self):
        r.validate_deltas(self.proof, self.runtime, self.plan, self.rows, self.old)

    def test_existing_reports_recomputed_without_summarize(self):
        with patch.object(r.sealed.targeted, 'summarize', side_effect=AssertionError('no summarize')):
            self.validate()
        r.sealed.report_callback.assert_called_once()
        self.assertEqual(self.proof.hashes.call_count, 3)

    def test_changed_raw_union_delta_or_dve_delta_rejected(self):
        for name in ('combined-bits.json', 'raw-bitmap-delta.json', 'per-case-gains.json', 'coverage-delta.json'):
            path = self.runtime / name
            original = self.documents[path]
            self.documents[path] = {'forged': True}
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.validate()
            self.documents[path] = original

    def test_external_report_membership_drift_rejected(self):
        (self.runtime / 'combined-inputs.txt').write_text('/design\n/old\n/foreign\n')
        with self.assertRaisesRegex(ValueError, 'membership differs'):
            self.validate()


if __name__ == '__main__':
    unittest.main()
