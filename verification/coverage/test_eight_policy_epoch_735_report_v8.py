"""Real fixed worker IPC and immutable source boundary; no DVE."""
import json
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import apply_branch_combo_six_latest as worker
import apply_branch_combo_six_717 as sealed
import eight_policy_epoch_735_report_v8 as r


class WorkerBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = r.prior.source_plan()
        cls.config_path = sealed.QUALIFIED707 / 'config.json'
        cls.raw_path = sealed.QUALIFIED707 / 'combined.el'

    def fixture(self):
        source = self.source
        config = json.loads(self.config_path.read_bytes())
        names = {str(self.config_path), str(self.raw_path), str(worker.SCRIPT),
                 str(Path(worker.sys.executable))}
        names.update(config['pins'])
        for result in config['bindings'].values():
            names.update(result['dependencies'])
        self.assertFalse(names - set(source['pins']))
        pins = {name: source['pins'][name] for name in names}
        return r.DiagnosticWiring(pins, [str(self.config_path), str(self.raw_path)],
                                  [str(self.config_path)])

    def test_real_six_workers_exact_bindings_and_no_source_write(self):
        owner = self.fixture()
        config = owner.phase.load_sealed(self.config_path, sealed.QUALIFIED_CONFIG)
        raw = owner.Path(self.raw_path).read_bytes()
        result = owner.frozen.sealed_core.bindings(raw, config)
        self.assertEqual(sum(item['records'] for item in result.values()), 5808)
        self.assertEqual(len(owner.worker_ipc_boundaries), 6)
        for group, item in result.items():
            self.assertEqual(item['binding_sha256'], config['bindings'][group]['binding_sha256'])
            self.assertEqual(item['dependencies'], config['bindings'][group]['dependencies'])
        self.assertTrue(all(not item['child_reads_captured'] for item in owner.worker_ipc_boundaries))
        self.assertIs(worker.invoke.__globals__['Path'], Path)
        with self.assertRaisesRegex(Exception, 'only read'):
            owner.Path(self.config_path).open('w')

    def test_missing_worker_pin_rejected_before_subprocess(self):
        owner = self.fixture()
        del owner.phase.pins[str(worker.SCRIPT)]
        with patch.object(worker.subprocess, 'run') as run:
            with self.assertRaisesRegex(Exception, 'Unbound fixed worker'):
                r.fixed_invoke(owner, worker.invoke)('pack', {}, b'')
            run.assert_not_called()

    def test_real_nested_tool_revalidate_has_only_fixed_roles(self):
        owner = self.fixture()
        config = json.loads(self.config_path.read_bytes())
        owner.eight.prior.lifecycle.tool.revalidate(config['plan']['tool_identity'])
        self.assertTrue(set(r.TOOL_READS) <= owner.phase.read_endpoints)
        self.assertTrue(set(owner.phase.consumed) <= set(r.TOOL_READS))
        bad = dict(owner.phase.pins)
        bad[next(iter(r.TOOL_READS))] = '0' * 64
        with self.assertRaisesRegex(Exception, 'sealed tool role'):
            r.tool_roles(bad, [])

    def test_foreign_dependency_rejected_and_temporary_files_cleaned(self):
        owner = self.fixture()
        config = json.loads(self.config_path.read_bytes())
        result = dict(config['bindings']['pack'], audited=0, after_root_audited=0)
        result['dependencies'] = dict(result['dependencies'], **{'/tmp/foreign-worker-source': '0' * 64})
        directories = []

        def output(command, **kwargs):
            directory = Path(command[command.index('--native') + 1]).parent
            directories.append(directory)
            self.assertEqual(set(p.name for p in directory.iterdir()), {'config.json', 'native.el'})
            return SimpleNamespace(stdout=json.dumps(result))

        with patch.object(worker.subprocess, 'run', side_effect=output):
            with self.assertRaisesRegex(Exception, 'unbound/conflicting dependencies'):
                r.fixed_invoke(owner, worker.invoke)('pack', config['groups']['pack'], b'')
        self.assertTrue(directories)
        self.assertTrue(all(not directory.exists() for directory in directories))


class TailHash(unittest.TestCase):
    def test_fresh_tail_hash_deduplicates_endpoint_and_rejects_cached_sha_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ordinary').mkdir()
            path = root / 'data'
            path.write_bytes(b'fresh-tail-check')
            alias = str(root / 'ordinary' / '..' / 'data')
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            pins = {str(path): expected, alias: expected}
            phase = r.base.CapturePhase(pins, [], [], {})
            phase.check_pins(pins)
            original_open = r.os.open
            with patch.object(r.os, 'open', wraps=original_open) as opened:
                result = r.finish_phase(phase)
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(result['fresh_tail_endpoint_hashes'], 1)
            self.assertEqual(result['fresh_tail_bytes'], len(b'fresh-tail-check'))
            self.assertEqual(phase.visited, set(pins))
            with self.assertRaisesRegex(Exception, 'only once'):
                r.finish_phase(phase)
            # Initial cached SHA remains correct; a fresh tail mismatch must reject.
            phase = r.base.CapturePhase(pins, [], [], {})
            phase.check_pins(pins)
            fake = unittest.mock.Mock()
            fake.hexdigest.return_value = '0' * 64
            with patch.object(r.hashlib, 'sha256', return_value=fake):
                with self.assertRaisesRegex(Exception, 'Fresh tail SHA differs'):
                    r.finish_phase(phase)
            self.assertTrue(phase.failed)


if __name__ == '__main__':
    unittest.main()
