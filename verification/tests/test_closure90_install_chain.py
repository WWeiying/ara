"""Small dispatch-chain regressions; installers are real, leaf audits are mocked."""
from contextlib import contextmanager, ExitStack
import importlib
import itertools
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_closure90_batch as batch


class InstallChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name) / 'producer'
        self.modules = {name: importlib.import_module(module) for name, module in batch.CATALOG.items()}
        self.name69 = 'rvv:vgap69_vf_odd_vd'
        self.module69 = self.modules[self.name69]
        self.image, self.simv = {'fixture': 'image'}, '/fixture/simv'
        self.row69 = dict(name=self.name69.split(':')[1], kind='directed',
                          vdb=str(self.output / 'results' / self.name69.split(':')[1] /
                                  'tests/app_case/work/code.vdb'))
        self.ordinary = dict(name='ordinary', kind='directed')

    @contextmanager
    def installed(self, names):
        with ExitStack() as stack:
            self.events = []
            self.normal_result = object()
            self.normal = Mock(side_effect=lambda *args: self.events.append('normal') or self.normal_result)
            self.precheck = Mock(return_value='ordinary-precheck')
            stack.enter_context(patch.object(batch.evidence.Evidence, 'baseline_row', self.normal))
            stack.enter_context(patch.object(batch.evidence, 'precheck', self.precheck))
            stack.enter_context(patch.object(batch.evidence, 'validate', Mock()))
            stack.enter_context(patch.object(batch.gap65, '_NORMAL_ROW', self.normal))
            self.gap65 = stack.enter_context(patch.object(batch.gap65, 'baseline_row',
                                                         wraps=batch.gap65.baseline_row))
            self.runtime69 = stack.enter_context(patch.object(self.module69, 'runtime_proof',
                side_effect=lambda *args: self.events.append('runtime69') or 'runtime-checked'))
            self.sealed = {}
            for name, module in self.modules.items():
                if hasattr(module, '_hooks'):
                    stack.enter_context(patch.object(module, '_hooks', None))
                else:
                    stack.enter_context(patch.object(module, '_installed', False))
                self.sealed[name] = stack.enter_context(patch.object(module, 'sealed_precheck',
                                                                    return_value=f'sealed:{name}'))
            self.proof = batch.evidence.Evidence()
            self.plan = dict(cases=[dict(source_name=self.name69)])
            self.proof.plan = Mock(return_value=self.plan)
            batch.install(dict(cases=[dict(name=name) for name in names]))
            yield

    def call_row(self, row):
        return self.proof.baseline_row(row, self.image, self.simv)

    def assert_runtime69_chain(self):
        self.assertIs(self.call_row(self.row69), self.normal_result)
        self.gap65.assert_called_once_with(self.proof, self.row69, self.image, self.simv)
        self.normal.assert_called_once_with(self.proof, self.row69, self.image, self.simv)
        self.proof.plan.assert_called_once_with(self.output)
        self.runtime69.assert_called_once_with(self.output, self.plan, self.row69, self.proof)
        self.assertEqual(self.events, ['normal', 'runtime69'])

    def test_three_case_install_orders_preserve_gap65_and_gap69_chain(self):
        for names in itertools.permutations(self.modules):
            with self.subTest(names=names), self.installed(names):
                self.assert_runtime69_chain()

    def test_single_gap69_case_preserves_historical_gap65_delegate(self):
        with self.installed([self.name69]):
            self.assert_runtime69_chain()

    def test_gap65_narrow_validation_remains_present_and_fail_closed(self):
        with self.installed(self.modules):
            row = dict(kind=batch.gap65.KIND, name='foreign', coverage_test=batch.gap65.observed.NAME)
            with self.assertRaisesRegex(ValueError, 'foreign or unverified gap65 recovery row'):
                self.call_row(row)
            self.gap65.assert_called_once_with(self.proof, row, self.image, self.simv)
            self.normal.assert_not_called()
            self.runtime69.assert_not_called()

    def test_ordinary_rows_delegate_without_gap69_audit(self):
        with self.installed(self.modules):
            self.assertIs(self.call_row(self.ordinary), self.normal_result)
            self.gap65.assert_called_once_with(self.proof, self.ordinary, self.image, self.simv)
            self.normal.assert_called_once_with(self.proof, self.ordinary, self.image, self.simv)
            self.runtime69.assert_not_called()

    def test_gap69_runtime_audit_rejection_is_not_swallowed(self):
        with self.installed(self.modules):
            self.runtime69.side_effect = ValueError('gap69 runtime evidence rejected')
            with self.assertRaisesRegex(ValueError, 'gap69 runtime evidence rejected'):
                self.call_row(self.row69)
            self.normal.assert_called_once()
            self.runtime69.assert_called_once()

    def test_prior_oracle_rejection_blocks_gap69_runtime_audit(self):
        with self.installed(self.modules):
            self.normal.side_effect = ValueError('prior independent oracle rejected')
            with self.assertRaisesRegex(ValueError, 'prior independent oracle rejected'):
                self.call_row(self.row69)
            self.runtime69.assert_not_called()

    def test_all_three_precheck_hooks_survive_every_adapter_order(self):
        for names in itertools.permutations(self.modules):
            with self.subTest(names=names), self.installed(names):
                for name in names:
                    item = dict(name=name)
                    self.assertEqual(batch.evidence.precheck(item, self.proof), f'sealed:{name}')
                    self.sealed[name].assert_called_once()
                    args = self.sealed[name].call_args.args
                    self.assertEqual(args[:2], (item, self.proof))
                    self.assertTrue(callable(args[2]))
                self.precheck.assert_not_called()

    def test_unrelated_precheck_preserves_original_delegate(self):
        with self.installed(self.modules):
            item = dict(name='rvv:ordinary')
            self.assertEqual(batch.evidence.precheck(item, self.proof), 'ordinary-precheck')
            self.precheck.assert_called_once_with(item, self.proof)
            for sealed in self.sealed.values():
                sealed.assert_not_called()

    def test_gap69_own_idempotent_install_keeps_parent_chain(self):
        with self.installed(self.modules):
            hook = batch.evidence.Evidence.baseline_row
            stored = self.module69._hooks
            self.assertIs(self.module69.install_hooks(), stored)
            self.assertIs(batch.evidence.Evidence.baseline_row, hook)
            self.assert_runtime69_chain()


if __name__ == '__main__':
    unittest.main()
