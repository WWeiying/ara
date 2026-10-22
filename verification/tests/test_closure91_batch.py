"""Small independent successor fixtures. No EDA commands or invocation mocks."""
import copy
from contextlib import ExitStack
import json
import importlib
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_closure91_batch as batch
import coverage_hash_session as hashes


class Fixture(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.output = self.root / 'new-output'
        self.baseline = self.root / '654'
        self.history = self.root / '651'
        self.receipt = self.root / 'receipt'
        self.patch(batch, 'BASELINE', self.baseline)
        self.patch(batch, 'HISTORY', self.history)
        self.patch(batch, 'COMPLETION', self.receipt)
        identity = self.file('654/fixture.identity')
        self.patch(batch, 'BASELINE_IDENTITY', {'fixture.identity': hashes.RAW_SHA256(identity)})
        self.save(self.baseline / 'checkpoint.json', dict(status='PASS', phase='complete',
            coverage_status='COMPLETE', aggregate_passed=654))
        original_read = batch.evidence.full.read

        def sandbox_read(path):
            if not Path(path).resolve().is_relative_to(self.root):
                raise AssertionError('non-fixture JSON read: ' + str(path))
            return original_read(path)

        self.patch(batch.evidence.full, 'read', side_effect=sandbox_read)

    def patch(self, obj, name, *args, **kwargs):
        return self.stack.enter_context(patch.object(obj, name, *args, **kwargs))

    def save(self, path, value):
        batch.evidence.full.save(path, value)

    def file(self, name, data=b'fixture'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def read(self, path):
        return batch.evidence.full.read(path)


class AdmissionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.design = self.root / 'design.vdb'
        self.design.mkdir()
        self.rows650 = [dict(name='old%d' % i, vdb=str(self.root / ('old%d.vdb' % i)))
                        for i in range(650)]
        self.old = self.rows650 + [dict(name=batch.predecessor.gap65.ROW,
            kind='gap65-observed-v1', vdb=str(self.root / 'gap65.vdb'))]
        self.items, cases, self.outcomes = [], [], []
        files = batch.evidence.full.pins([batch.predecessor.SCRIPT, Path(hashes.__file__),
            *[batch.SCRIPT.parent / (n + '.py') for n in batch.predecessor.CATALOG.values()]])
        for i, name in enumerate(batch.predecessor.CATALOG):
            elf = self.file('elf%d' % i, ('ELF%d' % i).encode())
            stem = name.split(':')[1]
            self.items.append(dict(name=name, timeout_s=300, binary=str(elf)))
            cases.append(dict(name=stem, source_name=name, timeout_s=300,
                              elf_sha256=hashes.RAW_SHA256(elf)))
            self.outcomes.append(dict(name=stem, vdb=str(self.baseline / 'results' / stem / 'code.vdb')))
        self.selection = self.root / 'old-selection.json'
        self.save(self.selection, dict(cases=self.items))
        files.update(batch.evidence.full.pins([self.selection]))
        self.plan = dict(checked_extension=batch.checked.VERSION, workers_max=8, baseline=str(self.history),
            baseline_passed=651, source_selection=dict(baseline=str(self.history), selection=str(self.selection)),
            image={'image': 'fixture'}, simv='fixture-simv', design_vdb=str(self.design),
            design_files={}, files=files, cases=cases)
        self.collection = dict(status='PASS', passed=654, total=654, baseline_passed=651,
            new_passed=3, counts={'PASS': 3}, excluded=[], cross_image_reuse=False)
        self.rows = self.old + self.outcomes
        self.save(self.baseline / 'all-outcomes.json', self.outcomes)
        self.save(self.receipt / 'completion.json', dict(files=batch.evidence.full.pins([self.selection])))
        self.bits = dict(tests=[r['vdb'] for r in self.rows], input_hashes=files)
        self.save(self.baseline / 'combined-bits.json', self.bits)
        self.file('654/combined-dve/inputs.txt', ('\n'.join(
            [str(self.design), *self.bits['tests']]) + '\n').encode())
        self.file('654/combined-dve/selected_tests.txt', ('\n'.join(
            str(Path(r['vdb']).with_suffix('') / r.get('coverage_test', r['name']))
            for r in self.rows) + '\n').encode())
        for row in self.rows:
            row['coverage_test'] = row['name']
        self.save(self.baseline / 'all-outcomes.json', self.outcomes)
        for stage in ('prepare', 'summarize'):
            self.save(self.baseline / (stage + '-hash-session.json'), dict(status='PASS',
                finished=True, unique_files=5, final_rehashed=5))
        state = self.read(self.baseline / 'checkpoint.json')
        state.update(total=3, workers=8, cases={r['name']: dict(status='PASS', vdb_valid=True,
            reused=False, passed_only=True) for r in self.outcomes})
        self.save(self.baseline / 'checkpoint.json', state)
        self.proof = batch.evidence.Evidence()
        self.proof.plans[self.baseline] = self.plan
        self.proof.plan = Mock(return_value=self.plan)
        self.proof.collection = Mock(return_value=self.collection)
        self.proof.ledger = Mock(side_effect=lambda p, _: self.rows if p == self.baseline else
            self.old if p == self.history else self.rows650)
        self.proof.baseline_row = Mock()
        self.previous = self.patch(batch.predecessor, 'completed')
        self.selection_check = self.patch(batch.predecessor, 'check_selection')
        self.admit = self.patch(batch.checked.base.admission, 'admitted', side_effect=lambda rows, _: rows)
        self.precheck = self.patch(batch.evidence, 'precheck', side_effect=lambda item, proof:
                                  proof.pin(item['binary']))
        self.runtime = self.patch(batch, 'old_runtime')
        self.patch(batch.checked.full.base, 'inventory', return_value={})

    def run_admission(self):
        return batch.completed(self.proof)

    def test_all654_rows_admitted_and_old_runtime_replayed(self):
        rows, bits = self.run_admission()
        self.assertEqual(rows, self.rows)
        self.assertEqual(bits, self.bits)
        self.assertEqual(self.proof.baseline_row.call_count, 654)
        self.admit.assert_called_once_with(self.rows, 'fixture-simv')
        self.assertEqual(self.precheck.call_count, 3)
        self.assertEqual(self.runtime.call_count, 2)
        self.selection_check.assert_called_once()

    def test_pending_gate_precedes_old_receipt_and_audits(self):
        state = self.read(self.baseline / 'checkpoint.json'); state['coverage_status'] = 'PENDING'
        self.save(self.baseline / 'checkpoint.json', state)
        with self.assertRaisesRegex(ValueError, 'not COMPLETE'):
            self.run_admission()
        self.previous.assert_not_called()
        self.proof.baseline_row.assert_not_called()

    def test_exact_identity_pin_rejects_changed_checkpoint(self):
        self.patch(batch, 'BASELINE_IDENTITY', {'checkpoint.json': '0' * 64})
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            self.run_admission()

    def test_ledger_substitution_same_count_rejected(self):
        self.rows = copy.deepcopy(self.rows); self.rows[17]['name'] = 'forged'
        with self.assertRaisesRegex(ValueError, 'ledger differs'):
            self.run_admission()

    def test_original650_is_independent_not_count_only(self):
        self.rows650 = copy.deepcopy(self.rows650); self.rows650[8]['name'] = 'substitute'
        with self.assertRaisesRegex(ValueError, 'independent650'):
            self.run_admission()

    def test_sourceplan_foreign_baseline_rejected(self):
        self.plan['source_selection']['baseline'] = 'foreign'
        with self.assertRaisesRegex(ValueError, 'sourceplan'):
            self.run_admission()

    def test_adapter_source_must_be_bound(self):
        del self.plan['files'][str(batch.predecessor.SCRIPT)]
        with self.assertRaisesRegex(ValueError, 'unbound predecessor'):
            self.run_admission()

    def test_failed_collection_counts_rejected(self):
        self.collection['counts'] = {'PASS': 3, 'FAIL': 1}
        with self.assertRaisesRegex(ValueError, 'collection'):
            self.run_admission()

    def test_checkpoint_pass_text_does_not_override_vdb_invalid(self):
        state = self.read(self.baseline / 'checkpoint.json')
        state['cases'][self.outcomes[0]['name']]['vdb_valid'] = False
        self.save(self.baseline / 'checkpoint.json', state)
        with self.assertRaisesRegex(ValueError, 'checkpoint case'):
            self.run_admission()

    def test_one_bad_historical_row_propagates(self):
        def audit(row, *_):
            if row['name'] == 'old11': raise ValueError('historical oracle rejected')
        self.proof.baseline_row.side_effect = audit
        with self.assertRaisesRegex(ValueError, 'historical oracle'):
            self.run_admission()

    def test_new_runtime_rejection_propagates(self):
        self.runtime.side_effect = ValueError('actual runtime rejected')
        with self.assertRaisesRegex(ValueError, 'actual runtime'):
            self.run_admission()

    def test_bitmap_member_order_must_match(self):
        self.bits['tests'].reverse(); self.save(self.baseline / 'combined-bits.json', self.bits)
        with self.assertRaisesRegex(ValueError, 'bitmap membership'):
            self.run_admission()

    def test_dve_selected_members_not_pass_labels(self):
        self.file('654/combined-dve/selected_tests.txt', b'PASS 654\n')
        with self.assertRaisesRegex(ValueError, 'DVE membership'):
            self.run_admission()

    def test_final_rehash_checkpoint_required(self):
        self.save(self.baseline / 'summarize-hash-session.json', dict(status='PASS', finished=True,
            unique_files=5, final_rehashed=4))
        with self.assertRaisesRegex(ValueError, 'rehash incomplete'):
            self.run_admission()

    def test_light_composition_binds_producer_reports_without_leaf_hash_or_oracle(self):
        self.patch(batch, 'composition_producer', side_effect=lambda row:
                   self.baseline if row['name'] in {r['name'] for r in self.outcomes} else self.history)
        for row in self.rows:
            row.update(status='PASS', returncode=0, passed_only=True, vdb_valid=True, reused=False)
            producer = self.baseline if row['name'] in {r['name'] for r in self.outcomes} else self.history
            self.save(producer / 'outcomes' / (row['name'] + '.json'), row)
        self.save(self.baseline / 'all-outcomes.json', self.outcomes)
        rows, bits = batch.composition_baseline(self.proof)
        self.assertEqual(rows, self.rows); self.assertEqual(bits, self.bits)
        self.proof.baseline_row.assert_not_called(); self.admit.assert_not_called()
        self.precheck.assert_not_called(); self.runtime.assert_not_called()
        for row in rows:
            producer = self.baseline if row['name'] in {r['name'] for r in self.outcomes} else self.history
            self.assertIn(str(producer / 'outcomes' / (row['name'] + '.json')), self.proof.files)


class StageTests(Fixture):
    def setUp(self):
        super().setUp()
        self.source = self.file('old/input', b'immutable')
        self.binary = self.file('old/input.elf', b'newelf')
        self.helper = self.file('old/helper.py')
        self.adapter = ModuleType('fixture_cache'); self.adapter.__file__ = str(self.file('old/adapter.py'))
        self.adapter.sha = hashes.RAW_SHA256
        self.design = self.root / 'design.vdb'; self.design.mkdir()
        self.member = self.file('design.vdb/data.xml')
        self.testvdb = self.root / 'historical.vdb'; self.testvdb.mkdir()
        self.file('historical.vdb/data.xml')
        self.item = dict(name='rvv:vgap71_fixture', timeout_s=300, sources=[str(self.source)],
                         evidence=[str(self.source)], binary=str(self.binary))
        self.spec = dict(files=batch.evidence.full.pins([self.source]), cases=[self.item])
        self.save(self.receipt / 'completion.json', dict(files=batch.evidence.full.pins([self.source])))
        self.save(self.receipt / 'checkpoint.json', {})
        self.save(self.baseline / 'plan.json', dict(files=batch.evidence.full.pins([self.source]),
            design_vdb=str(self.design)))
        for name in ('plan.sha256.json', 'collection.json', 'all-outcomes.json', 'combined-bits.json'):
            self.save(self.baseline / name, {})
        self.save(self.baseline / 'all-passed-outcomes.json', [dict(vdb=str(self.testvdb), files={})])
        self.selection = self.root / 'selection.json'; self.save(self.selection, self.spec)
        self.patch(hashes, '__file__', str(self.helper))
        self.patch(hashes, 'verification_modules', return_value=[self.adapter, batch.evidence.full.base])
        self.original_script = batch.checked.full.SCRIPT
        self.prepare = self.patch(batch.checked, 'prepare', side_effect=self.prepare_fixture)
        self.summarize = self.patch(batch.checked, 'summarize', side_effect=self.summary_fixture)
        self.patch(batch.evidence, 'validate', batch.evidence.validate)
        self.failure = self.patch(batch.checked, 'failure', wraps=batch.checked.failure)
        self.invoke = batch.checked.full.batch.invoke; self.popen = subprocess.Popen
        self.patch(batch.checked, 'SCRIPT', batch.SCRIPT)
        batch.install_stage_cache(self.spec)

    def assert_real_scope(self):
        self.assertIsNotNone(hashes._active)
        self.assertIs(batch.checked.full.batch.invoke, self.invoke)
        self.assertIs(subprocess.Popen, self.popen)
        self.assertEqual(self.adapter.sha(self.source), self.adapter.sha(self.source))

    def prepare_fixture(self, output, selection):
        self.assert_real_scope()
        self.assertEqual(batch.checked.full.SCRIPT, batch.SCRIPT)
        output.mkdir()
        generated = output / 'writable'; generated.write_bytes(b'one')
        one = self.adapter.sha(generated); generated.write_bytes(b'two')
        self.assertNotEqual(one, self.adapter.sha(generated))
        wrapper = output / 'coverage_simv'; wrapper.write_text('python ' + str(batch.SCRIPT) + ' --coverage-exec')
        plan = dict(source_selection=dict(baseline=str(self.baseline), selection=str(selection)),
            baseline=str(self.baseline), baseline_bits=str(self.baseline / 'combined-bits.json'),
            baseline_passed=654, workers_max=8, wrapper=str(wrapper),
            cases=[dict(source_name=self.item['name'], timeout_s=300)],
            files=batch.evidence.full.pins([batch.SCRIPT, self.helper, self.source, generated, wrapper]))
        self.save(output / 'plan.json', plan)
        self.save(output / 'plan.sha256.json', batch.evidence.full.pins([output / 'plan.json']))
        self.save(output / 'checkpoint.json', dict(coverage_status='PENDING'))
        self.assertFalse((output / 'prepare-hash-session.json').exists())

    def summary_fixture(self, output, plan):
        self.assert_real_scope()
        self.save(output / 'collection.json', dict(status='PASS'))
        self.assertFalse((output / 'summarize-hash-session.json').exists())
        self.assertEqual(self.read(output / 'checkpoint.json')['coverage_status'], 'PENDING')
        return ['result']

    def prepared(self):
        batch.checked.prepare(self.output, self.selection)
        return self.read(self.output / 'plan.json')

    def test_prepare_final_rehash_publish_and_restore_successor_wrapper(self):
        plan = self.prepared()
        self.assertEqual(batch.checked.full.SCRIPT, self.original_script)
        report = self.read(self.output / 'prepare-hash-session.json')
        self.assertTrue(report['finished']); self.assertGreater(report['cache_hits'], 0)
        self.assertEqual(report['unique_files'], report['final_rehashed'])
        batch.evidence.full.check(plan['files'])
        self.assertIsNone(hashes._active)

    def test_summary_marker_only_after_scope_exit(self):
        plan = self.prepared()
        self.assertEqual(batch.checked.summarize(self.output, plan), ['result'])
        self.assertTrue(self.read(self.output / 'summarize-hash-session.json')['finished'])
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')

    def test_existing_output_unchanged_not_failure(self):
        self.output.mkdir(); sentinel = self.file('new-output/sentinel')
        with self.assertRaisesRegex(ValueError, 'new output'):
            batch.checked.prepare(self.output, self.selection)
        self.failure.assert_not_called(); self.prepare.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'fixture')

    def test_prepare_error_restores_script_records_failure(self):
        self.prepare.side_effect = RuntimeError('oracle failed')
        with self.assertRaisesRegex(RuntimeError, 'oracle failed'):
            self.prepared()
        self.assertEqual(batch.checked.full.SCRIPT, self.original_script)
        self.assertEqual(self.read(self.output / 'checked-failure.json')['status'], 'REJECTED')
        self.assertFalse((self.output / 'prepare-hash-session.json').exists())

    def test_mutation_blocks_prepare_publish(self):
        def stage(output, selection):
            self.prepare_fixture(output, selection); self.source.write_bytes(b'changed')
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            self.prepared()
        self.assertFalse((self.output / 'prepare-hash-session.json').exists())

    def test_vdb_addition_during_uncached_final_rehash_blocks(self):
        def stage(output, selection):
            self.prepare_fixture(output, selection)
            original = hashes._active.hashes.hasher
            def add(path):
                value = original(path); self.file('historical.vdb/new.xml'); return value
            hashes._active.hashes.hasher = add
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            self.prepared()
        self.assertFalse((self.output / 'prepare-hash-session.json').exists())

    def test_design_member_deletion_blocks_summary_return_and_checkpoint(self):
        plan = self.prepared()
        def summarize(output, current):
            result = self.summary_fixture(output, current); self.member.unlink(); return result
        self.summarize.side_effect = summarize
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            batch.checked.summarize(self.output, plan)
        self.assertFalse((self.output / 'summarize-hash-session.json').exists())
        self.assertEqual(self.read(self.output / 'checkpoint.json')['coverage_status'], 'PENDING')

    def test_stat_only_change_blocks_scope(self):
        def stage(output, selection):
            self.prepare_fixture(output, selection); self.source.chmod(0o700)
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            self.prepared()

    def test_selected_spec_is_exact_immutable_input_and_changes_reject(self):
        roots = batch.immutable_inputs(self.spec, self.output, selection=self.selection)
        self.assertIn(self.selection, roots)
        def stage(output, selection):
            self.prepare_fixture(output, selection)
            self.assertEqual(self.adapter.sha(selection), hashes.RAW_SHA256(selection))
            selection.write_bytes(b'changed after checked prepare')
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'membership/stat changed'):
            self.prepared()
        self.assertFalse((self.output / 'prepare-hash-session.json').exists())

    def test_post_rehash_plan_pin_change_rejected(self):
        finish = hashes.CoverageHashSession.finish
        def change(session):
            finish(session)
            plan = self.read(self.output / 'plan.json'); plan['files'][str(self.source)] = '0' * 64
            self.save(self.output / 'plan.json', plan)
        with patch.object(hashes.CoverageHashSession, 'finish', change):
            with self.assertRaisesRegex(ValueError, 'prepared plan changed'):
                self.prepared()

    def test_wrong_worker_limit_rejected_before_publication(self):
        def stage(output, selection):
            self.prepare_fixture(output, selection)
            plan = self.read(output / 'plan.json'); plan['workers_max'] = 9
            self.save(output / 'plan.json', plan)
        self.prepare.side_effect = stage
        with self.assertRaisesRegex(ValueError, 'worker/producer/budget'):
            self.prepared()

    def test_small_seal_expected_digest_not_recalculated_after_tamper(self):
        check = batch.evidence.full.check
        def tamper(files):
            report = self.output / 'prepare-hash-session.json'
            if str(report) in files:
                report.write_bytes(b'changed after expected hash capture')
            return check(files)
        with patch.object(batch.evidence.full, 'check', side_effect=tamper):
            with self.assertRaisesRegex(RuntimeError, 'frozen input changed'):
                self.prepared()
        self.failure.assert_called_once()

    def test_pending_prepare_does_not_gather_roots_or_call_prepare(self):
        self.save(self.baseline / 'checkpoint.json', dict(coverage_status='PENDING'))
        with patch.object(batch, 'immutable_inputs') as roots:
            with self.assertRaisesRegex(ValueError, 'not COMPLETE'):
                self.prepared()
        roots.assert_not_called(); self.prepare.assert_not_called()

    def test_roots_exact_files_vdb_snapshots_output_alias_excluded(self):
        self.output.mkdir(); generated = self.file('new-output/generated')
        alias = self.root / 'alias'; alias.symlink_to(generated)
        roots = batch.immutable_inputs(self.spec, self.output,
                                      dict(files=batch.evidence.full.pins([generated, alias])))
        self.assertEqual({p for p in roots if p.is_dir()}, {self.design, self.testvdb})
        self.assertNotIn(generated, roots); self.assertNotIn(alias, roots)
        self.assertNotIn(self.root, roots)

    def test_composition_roots_do_not_expand_old_receipt_leaves_or_vdb_snapshots(self):
        old650 = self.root / '650'
        self.patch(batch.predecessor.gap65, 'BASELINE', old650)
        self.patch(batch, 'composition_producer', return_value=self.baseline)
        trace = self.file('old/expensive-historical-trace', b'historical leaf')
        self.save(self.receipt / 'completion.json', dict(files=batch.evidence.full.pins([trace])))
        for producer in (self.baseline, self.history, old650):
            self.save(producer / 'plan.json', dict(files=batch.evidence.full.pins([trace])))
            self.save(producer / 'collection.json', dict(reports={}))
            self.file(str((producer / 'dve/inputs.txt').relative_to(self.root)))
        self.save(self.baseline / 'all-passed-outcomes.json', [dict(name='historic', vdb=str(self.testvdb))])
        self.save(self.baseline / 'outcomes/historic.json', {})
        roots = batch.composition_inputs(self.spec, self.output)
        self.assertNotIn(trace, roots)
        self.assertNotIn(self.design, roots); self.assertNotIn(self.testvdb, roots)
        self.assertTrue(all(p.is_file() for p in roots))


class InterfaceTests(Fixture):
    def setUp(self):
        super().setUp()
        self.name = 'rvv:vgap71_fixture'
        self.module = SimpleNamespace(NAME=self.name, __file__=str(batch.SCRIPT.parent /
            'run_gap71_fixture_checked_extension.py'), install_hooks=Mock(), runtime_proof=Mock())

    def test_adapter_load_scoped_module_and_runtime_api(self):
        with patch.object(batch.importlib, 'import_module', return_value=self.module):
            self.assertEqual(batch.load_adapters({'71': 'run_gap71_fixture_checked_extension'}),
                             {self.name: self.module})

    def test_adapter_wrong_gap_or_module_or_path_rejected(self):
        for bindings in ({'74': 'x'}, {'71': '../x'}, {}):
            with self.subTest(bindings=bindings), self.assertRaises(ValueError):
                batch.load_adapters(bindings)
        self.module.__file__ = '/tmp/foreign.py'
        with patch.object(batch.importlib, 'import_module', return_value=self.module):
            with self.assertRaisesRegex(ValueError, 'foreign adapter source'):
                batch.load_adapters({'71': 'run_gap71_fixture_checked_extension'})

    def test_missing_runtime_api_rejected(self):
        self.module.runtime_proof = None
        with patch.object(batch.importlib, 'import_module', return_value=self.module):
            with self.assertRaisesRegex(ValueError, 'runtime adapter API'):
                batch.load_adapters({'71': 'run_gap71_fixture_checked_extension'})

    def test_budgets_and_case_adapter_membership(self):
        bits = dict(metrics={'line': {'ara_tb.dut.i_ara_soc.i_system.x': []}})
        case = dict(name=self.name, timeout_s=300, targets=['ara_tb.dut.i_ara_soc.i_system.x'], rationale='probe')
        batch.case_limits([case], {self.name: self.module}, bits)
        for seconds in (301, 0, -1, True, 300.0):
            with self.subTest(seconds=seconds), self.assertRaisesRegex(ValueError, '300s'):
                batch.case_limits([dict(case, timeout_s=seconds)], {self.name: self.module}, bits)

    def test_coverage_trace_for_new_cases_and_no_invoke_mock(self):
        plan = dict(cases=[dict(source_name=self.name)])
        with patch.object(batch.checked.full.batch, 'adapter_command', return_value=['simv', '-cm']) as command:
            result = batch.coverage_command({}, ['+TESTCASE=vgap71_fixture'], self.root, plan)
            self.assertEqual(result[-1], '+VECTOR_TRACE=' + str(self.root / 'vector_trace.csv'))
            command.assert_called_once()
            for args in (['+VECTOR_TRACE=x'], ['+TESTCASE=old'], ['+TESTCASE=vgap71_fixture', '+VECTOR_TRACE']):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    batch.coverage_command({}, args, self.root, plan)

    def test_pending_baseline_never_composes_or_imports_new_adapter(self):
        self.save(self.baseline / 'checkpoint.json', dict(coverage_status='PENDING'))
        with patch.object(batch, 'install') as install:
            with self.assertRaisesRegex(ValueError, 'not COMPLETE'):
                batch.compose([self.root / 'draft.json'], self.root / 'spec.json', {'71': 'future'})
            install.assert_not_called()
        self.assertFalse((self.root / 'spec.json').exists())

    def runtime_fixture(self):
        target = self.root / 'results' / self.name.split(':')[1]
        artifact = target / 'tests' / self.name.replace(':', '_')
        paths = [artifact / n for n in ('work/run.vcs.log', 'commit_trace.csv', 'input.elf', 'work/vector_trace.csv')]
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'actual runtime')
        self.save(target / 'summary.json', [dict(name=self.name, artifact_dir=str(artifact))])
        row = dict(name=target.name, files=batch.evidence.full.pins([target / 'summary.json', *paths]))
        self.runtime_plan = dict(cases=[dict(name=row['name'], source_name=self.name,
                                           elf_sha256=hashes.RAW_SHA256(paths[2]))])
        return row, paths

    def test_actual_runtime_export_replayed_with_bound_input_hashes(self):
        row, paths = self.runtime_fixture()
        result = dict(status='PASS', schema='gap71-strict-v1', checks={'traps': 2},
                      files={str(p): row['files'][str(p)] for p in paths})
        self.module.runtime_proof.return_value = result
        proof = batch.evidence.Evidence()
        self.assertEqual(batch.audit_runtime(self.module, self.root, self.runtime_plan, row, proof), result)
        self.module.runtime_proof.assert_called_once_with(self.root, self.runtime_plan, row, proof)

    def test_pass_text_or_unbound_runtime_file_rejected(self):
        row, paths = self.runtime_fixture()
        for result in ({'status': 'PASS'}, dict(status='PASS', schema='x', files={}, checks='PASS'),
                       dict(status='PASS', schema='x', checks={'done': True},
                            files={str(p): '0' * 64 for p in paths})):
            self.module.runtime_proof.return_value = result
            with self.subTest(result=result), self.assertRaises(ValueError):
                batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())

    def test_missing_actual_vector_trace_rejected_before_oracle(self):
        row, paths = self.runtime_fixture(); paths[-1].unlink()
        with self.assertRaisesRegex(ValueError, 'missing evidence'):
            batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())
        self.module.runtime_proof.assert_not_called()

    def test_case_names_and_names_support_distinct_cases(self):
        self.module.CASE_NAMES = [self.name, 'rvv:vgap71_second']
        self.module.NAMES = list(self.module.CASE_NAMES)
        with patch.object(batch.importlib, 'import_module', return_value=self.module):
            self.assertEqual(set(batch.load_adapters({'71': 'run_gap71_fixture_checked_extension'})),
                             set(self.module.CASE_NAMES))

    def test_identity_lists_are_strict_not_strings_duplicate_or_conflicting(self):
        for names in (self.name, [self.name, self.name], [], ['PASS'], [self.name, None]):
            self.module.CASE_NAMES = names
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, 'identity list'):
                batch.adapter_names(self.module)
        self.module.CASE_NAMES = [self.name]; self.module.NAMES = ['rvv:vgap71_other']
        with self.assertRaisesRegex(ValueError, 'identity list'):
            batch.adapter_names(self.module)

    def test_multi_case_runtime_requires_exact_identity_not_shared_name(self):
        row, paths = self.runtime_fixture()
        self.module.CASE_NAMES = [self.name, 'rvv:vgap71_second']
        result = dict(status='PASS', schema='strict-v1', checks={'traps': 1},
            files={str(p): row['files'][str(p)] for p in paths})
        self.module.runtime_proof.return_value = result
        for name in (None, 'rvv:vgap71_second'):
            result['name'] = name
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'exact case'):
                batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())
        result['name'] = self.name
        batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())

    def test_second_identity_is_not_audited_as_shared_legacy_name(self):
        first_row, first_paths = self.runtime_fixture()
        first_plan = self.runtime_plan
        first_name = self.name
        self.name = 'rvv:vgap71_second'
        self.module.CASE_NAMES = [first_name, self.name]
        second_row, second_paths = self.runtime_fixture()
        self.runtime_plan['cases'].extend(first_plan['cases'])
        result = dict(status='PASS', name=self.name, schema='multi-v1', checks={'traps': 1},
                      files={str(p): second_row['files'][str(p)] for p in second_paths})
        self.module.runtime_proof.return_value = result
        proof = batch.evidence.Evidence()
        batch.audit_runtime(self.module, self.root, self.runtime_plan, second_row, proof)
        self.module.runtime_proof.assert_called_once_with(self.root, self.runtime_plan, second_row, proof)
        self.assertNotIn(str(first_paths[0]), proof.files)
        self.assertEqual(self.module.NAME, first_name)

    def test_runtime_elf_must_match_exact_producer_case(self):
        row, paths = self.runtime_fixture()
        self.runtime_plan['cases'][0]['elf_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'hash differs'):
            batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())
        self.module.runtime_proof.assert_not_called()

    def test_runtime_scope_cannot_borrow_other_case_file(self):
        row, paths = self.runtime_fixture()
        foreign = self.file('other-case/commit_trace.csv')
        result = dict(status='PASS', schema='x', checks={'done': True},
            files={str(p): row['files'][str(p)] for p in paths})
        result['files'][str(foreign)] = hashes.RAW_SHA256(foreign)
        self.module.runtime_proof.return_value = result
        with self.assertRaisesRegex(ValueError, 'unbound/unchecked'):
            batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())

    def test_custom_trap_empty_vector_events_allowed_if_oracle_passes(self):
        row, paths = self.runtime_fixture(); paths[-1].write_bytes(b'')
        row['files'][str(paths[-1])] = hashes.RAW_SHA256(paths[-1])
        result = dict(status='PASS', schema='trap-v1', checks={'traps': 1},
            files={str(p): row['files'][str(p)] for p in paths})
        self.module.runtime_proof.return_value = result
        batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())

    def test_runtime_native_vdb_hash_must_be_in_this_cases_inventory(self):
        row, paths = self.runtime_fixture()
        vdb = self.root / 'results' / row['name'] / 'work/code.vdb'
        member = self.file(str((vdb / 'cond.xml').relative_to(self.root)))
        row.update(vdb=str(vdb), vdb_files=batch.evidence.full.pins([member]))
        result = dict(status='PASS', schema='native-v1', checks={'native': True},
            files={str(p): row['files'][str(p)] for p in paths})
        result['files'][str(member)] = row['vdb_files'][str(member)]
        def replay(output, plan, row, proof):
            proof.pin(member, row['vdb_files'][str(member)]); return result
        self.module.runtime_proof.side_effect = replay
        batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())
        foreign = self.file('other-vdb/cond.xml')
        row['vdb_files'][str(foreign)] = hashes.RAW_SHA256(foreign)
        result['files'][str(foreign)] = row['vdb_files'][str(foreign)]
        with self.assertRaisesRegex(ValueError, 'unbound/unchecked'):
            batch.audit_runtime(self.module, self.root, self.runtime_plan, row, batch.evidence.Evidence())

    def test_gap73_perf_profile_is_real_and_cannot_be_overridden(self):
        plan = dict(cases=[dict(source_name='app:akv_gap73_v1_onehot')])
        with patch.object(batch.checked.full.batch, 'adapter_command', return_value=['simv', '+NO_FSDB']):
            command = batch.coverage_command({}, ['+TESTCASE=akv_gap73_v1_onehot'], self.root, plan)
            self.assertEqual(command.count('+AKV_PERF'), 1)
            self.assertEqual(command.count('+NO_FSDB'), 1)
            with self.assertRaisesRegex(ValueError, 'profile override'):
                batch.coverage_command({}, ['+TESTCASE=akv_gap73_v1_onehot', '+AKV_PERF=0'], self.root, plan)

    def test_all_custom_cases_get_exact_case_local_perf_and_one_vector_trace(self):
        expected = {
            'gap71_qbs_read': '+QBS_PERF', 'gap71_qbs_fault': '+QBS_PERF',
            'gap71_akv_read': '+AKV_PERF', 'gap71_akv_fault': '+AKV_PERF',
            'qbs_gap72_fill_abort': '+QBS_PERF', 'akv_gap72_tile_range': '+AKV_PERF',
            'akv_gap73_v1_onehot': '+AKV_PERF',
        }
        vector = '+VECTOR_TRACE=' + str(self.root / 'vector_trace.csv')
        def command(config, args, cwd):
            return ['simv', *args, '-cm', 'line+cond']
        with patch.object(batch.checked.full.batch, 'adapter_command', side_effect=command):
            for name, flag in expected.items():
                plan = dict(cases=[dict(source_name='app:' + name)])
                for flags in ([], [flag], [vector], [flag, vector]):
                    with self.subTest(name=name, flags=flags):
                        actual = batch.coverage_command({}, ['+TESTCASE=' + name, *flags], self.root, plan)
                        self.assertEqual(actual.count(flag), 1)
                        self.assertEqual(actual.count(vector), 1)

    def test_custom_profile_duplicates_wrong_engine_and_foreign_trace_rejected(self):
        name = 'qbs_gap72_fill_abort'
        plan = dict(cases=[dict(source_name='app:' + name)])
        vector = '+VECTOR_TRACE=' + str(self.root / 'vector_trace.csv')
        with patch.object(batch.checked.full.batch, 'adapter_command', return_value=['simv']):
            for flags in (['+QBS_PERF', '+QBS_PERF'], ['+AKV_PERF'], ['+QBS_PERF=0'],
                          ['+QBS_PERF', '+AKV_PERF'], [vector, vector], ['+VECTOR_TRACE=other']):
                with self.subTest(flags=flags), self.assertRaises(ValueError):
                    batch.coverage_command({}, ['+TESTCASE=' + name, *flags], self.root, plan)

    def test_maximum_total_eight_cases_and_subsets(self):
        names = ['rvv:vgap71_case%d' % i for i in range(9)]
        modules = {n: self.module for n in names}
        cases = [dict(name=n, timeout_s=300, rationale='probe',
                      targets=['ara_tb.dut.i_ara_soc.i_system.x']) for n in names]
        bits = dict(metrics={'line': {'ara_tb.dut.i_ara_soc.i_system.x': []}})
        batch.case_limits(cases[:8], modules, bits)
        batch.case_limits(cases[:2], modules, bits)
        with self.assertRaisesRegex(ValueError, 'membership'):
            batch.case_limits(cases, modules, bits)


class CompositionTests(Fixture):
    def setUp(self):
        super().setUp()
        self.elf = self.file('source/new.elf', b'new ELF')
        self.source = self.file('source/new.c')
        self.log = self.file('source/precheck.log')
        self.name = 'rvv:vgap71_fixture'
        self.adapter = self.file('source/run_gap71_fixture_checked_extension.py')
        self.modules = {self.name: SimpleNamespace(__file__=str(self.adapter))}
        self.item = dict(name=self.name, timeout_s=300, binary=str(self.elf),
            sources=[str(self.source)], evidence=[str(self.log)], precheck={'record': str(self.log)},
            source_audit='strict', rationale='probe', targets=['ara_tb.dut.i_ara_soc.i_system.x'])
        self.draft = self.root / 'draft.json'; self.save(self.draft, dict(cases=[self.item]))
        self.selection = self.root / 'selection.json'
        self.bindings = {'71': 'run_gap71_fixture_checked_extension'}
        self.patch(batch, 'install', return_value=self.modules)
        self.patch(batch, 'load_adapters', return_value=self.modules)
        self.bits = dict(metrics={'line': {'ara_tb.dut.i_ara_soc.i_system.x': []}})
        self.rows = [dict(name='historical', elf_sha256='0' * 64)]
        def completed(proof):
            proof.pin(self.baseline / 'checkpoint.json')
            return self.rows, self.bits
        self.full_admission = self.patch(batch, 'completed', side_effect=completed)
        self.light_seal = self.patch(batch, 'composition_baseline', side_effect=completed)
        self.full_roots = self.patch(batch, 'immutable_inputs', return_value=[self.elf, self.draft, self.source, self.log,
            self.adapter, self.baseline / 'checkpoint.json'])
        self.patch(batch, 'composition_inputs', return_value=[self.elf, self.draft, self.source, self.log,
            self.adapter, self.baseline / 'checkpoint.json'])
        self.patch(hashes, 'verification_modules', return_value=[batch.evidence.full.base])
        self.precheck = self.patch(batch.evidence, 'precheck', side_effect=lambda item, proof:
            [proof.pin(p) for p in [item['binary'], *item['sources'], *item['evidence']]])

    def compose(self):
        return batch.compose([self.draft], self.selection, self.bindings)

    def test_compose_real_scope_publish_after_uncached_final_rehash(self):
        finish = hashes.CoverageHashSession.finish
        def verified(session):
            self.assertFalse(self.selection.exists()); finish(session)
        with patch.object(hashes.CoverageHashSession, 'finish', verified):
            spec = self.compose()
        self.assertEqual(self.read(self.selection), spec)
        self.assertEqual(spec['cases'], [self.item]); self.assertFalse(spec['simulations_started'])
        self.assertTrue(spec['full_admission_deferred']); self.assertIs(spec['admission_claimed'], False)
        self.full_admission.assert_not_called(); self.full_roots.assert_not_called()
        batch.check_selection(spec, batch.evidence.Evidence())
        self.full_admission.assert_called_once()

    def test_compose_final_rehash_failure_never_publishes_spec(self):
        with patch.object(hashes.CoverageHashSession, 'finish', side_effect=ValueError('final rehash failed')):
            with self.assertRaisesRegex(ValueError, 'final rehash failed'):
                self.compose()
        self.assertFalse(self.selection.exists())

    def test_same_count_draft_mutation_rejected(self):
        spec = self.compose()
        spec['cases'][0]['timeout_s'] = 299
        with self.assertRaisesRegex(ValueError, 'sealed draft cases changed'):
            batch.check_selection(spec, batch.evidence.Evidence())

    def test_existing_historical_name_or_elf_not_rescheduled(self):
        self.rows[0]['name'] = self.name.split(':')[1]
        with self.assertRaisesRegex(ValueError, 'existing PASS'):
            self.compose()
        self.assertFalse(self.selection.exists())

    def test_source_checkpoint_binding_required(self):
        spec = self.compose(); del spec['files'][str(self.baseline / 'checkpoint.json')]
        with self.assertRaisesRegex(ValueError, 'unbound successor'):
            batch.check_selection(spec, batch.evidence.Evidence())

    def test_worker_limit_and_foreign_baseline_rejected(self):
        spec = self.compose()
        for key, value in [('maximum_concurrent_workers', 9), ('baseline', 'foreign')]:
            changed = dict(spec, **{key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'foreign successor'):
                batch.check_selection(changed, batch.evidence.Evidence())

    def test_prepare_still_calls_full_admission_not_light_identity(self):
        spec = self.compose()
        self.full_admission.assert_not_called()
        self.light_seal.reset_mock()
        def prepare(output, selection):
            batch.evidence.validate(selection)
            raise RuntimeError('stop fixture after full formal admission')
        self.patch(batch.checked, 'prepare', side_effect=prepare)
        self.patch(batch.checked, 'summarize', Mock())
        self.patch(batch.evidence, 'validate', batch.evidence.validate)
        self.patch(batch.checked, 'failure', Mock())
        batch.install_stage_cache(spec)
        with self.assertRaisesRegex(RuntimeError, 'after full formal admission'):
            batch.checked.prepare(self.output, self.selection)
        self.full_admission.assert_called_once()
        self.light_seal.assert_not_called()

    def test_spec_cannot_claim_compose_performed_formal_admission(self):
        spec = self.compose()
        for key, value in [('full_admission_deferred', False), ('admission_claimed', True)]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'foreign successor'):
                batch.check_selection(dict(spec, **{key: value}), batch.evidence.Evidence())


class InstallChainTests(Fixture):
    def setUp(self):
        super().setUp()
        self.events = []
        self.normal = self.patch(batch.evidence.Evidence, 'baseline_row', Mock(return_value='normal'))
        self.patch(batch.predecessor.gap65, '_NORMAL_ROW', self.normal)
        self.gap65 = self.patch(batch.predecessor.gap65, 'baseline_row',
                               wraps=batch.predecessor.gap65.baseline_row)
        self.patch(batch.evidence, 'precheck', Mock(return_value='standard-precheck'))
        self.patch(batch, '_installed', None)
        self.old = [importlib.import_module(n) for n in batch.predecessor.CATALOG.values()]
        self.sealed = []
        for index, module in enumerate(self.old, 68):
            self.patch(module, '_hooks' if hasattr(module, '_hooks') else '_installed',
                       None if hasattr(module, '_hooks') else False)
            self.sealed.append(self.patch(module, 'sealed_precheck', return_value='sealed%d' % index))
            install = module.install_hooks
            def record(install=install, index=index):
                self.events.append(index); return install()
            self.patch(module, 'install_hooks', side_effect=record)
        original65 = batch.predecessor.gap65.install_hooks
        self.patch(batch.predecessor.gap65, 'install_hooks',
                   side_effect=lambda: self.events.append(65) or original65())
        self.runtime69 = self.patch(self.old[1], 'runtime_proof', return_value={'status': 'PASS'})
        self.new = SimpleNamespace(NAME='rvv:vgap71_fixture',
            install_hooks=lambda: self.events.append(71), __file__='fixture.py')
        self.patch(batch, 'load_adapters', return_value={self.new.NAME: self.new})
        self.runtime71 = self.patch(batch, 'audit_runtime', return_value='strict-new-runtime')
        self.bindings = {'71': 'run_gap71_fixture_checked_extension'}
        batch.install(self.bindings)
        self.proof = batch.evidence.Evidence()
        self.plan = dict(cases=[]); self.proof.plan = Mock(return_value=self.plan)

    def row(self, name):
        return dict(name=name, kind='directed', vdb=str(self.root / 'results' / name / 'tests/x/work/code.vdb'))

    def call(self, row):
        return self.proof.baseline_row(row, {}, 'simv')

    def test_order_65_68_69_70_then_new(self):
        self.assertEqual(self.events, [65, 68, 69, 70, 71])

    def test_gap65_delegate_gap69_runtime_and_new_runtime_all_survive(self):
        row = self.row(batch.adapter_name(self.old[1]).split(':')[1])
        self.assertEqual(self.call(row), 'normal')
        self.gap65.assert_called_once(); self.runtime69.assert_called_once()
        self.runtime71.assert_not_called()
        self.assertEqual(self.call(self.row('vgap71_fixture')), 'normal')
        self.runtime71.assert_called_once()

    def test_narrow_gap65_foreign_row_still_rejects(self):
        with self.assertRaisesRegex(ValueError, 'foreign or unverified gap65'):
            self.call(dict(kind=batch.predecessor.gap65.KIND, name='foreign',
                           coverage_test=batch.predecessor.gap65.observed.NAME))
        self.normal.assert_not_called(); self.runtime69.assert_not_called()

    def test_old_precheck_chain_preserved(self):
        for i, module in enumerate(self.old):
            self.assertEqual(batch.evidence.precheck(dict(name=batch.adapter_name(module)), self.proof),
                             'sealed%d' % (i + 68))
            self.sealed[i].assert_called_once()

    def test_idempotent_install_does_not_clobber_cached69_chain(self):
        hook = batch.evidence.Evidence.baseline_row
        batch.install(self.bindings)
        self.assertIs(batch.evidence.Evidence.baseline_row, hook)
        self.assertEqual(self.events, [65, 68, 69, 70, 71])
        self.call(self.row(batch.adapter_name(self.old[1]).split(':')[1]))
        self.runtime69.assert_called_once()

    def test_different_adapter_chain_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cannot replace'):
            batch.install({'72': 'other'})

    def test_new_runtime_failure_not_swallowed(self):
        self.runtime71.side_effect = ValueError('new runtime rejected')
        with self.assertRaisesRegex(ValueError, 'new runtime rejected'):
            self.call(self.row('vgap71_fixture'))

    def test_historical_failure_blocks_new_audit(self):
        self.normal.side_effect = ValueError('historical rejected')
        with self.assertRaisesRegex(ValueError, 'historical rejected'):
            self.call(self.row('vgap71_fixture'))
        self.runtime71.assert_not_called()

    def test_multicase_adapter_installed_once_not_once_per_case(self):
        self.patch(batch, '_installed', None)
        self.events.clear()
        self.patch(batch, 'load_adapters', return_value={
            'rvv:vgap71_a': self.new, 'rvv:vgap71_b': self.new, 'rvv:vgap71_c': self.new})
        batch.install(self.bindings)
        self.assertEqual(self.events.count(71), 1)


if __name__ == '__main__':
    unittest.main()
