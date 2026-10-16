import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import audit_valu_replay_20261015 as audit
import test_collect_valu_restart783 as fixtures


class ReplayAuditTests(unittest.TestCase):
    def test_typed_actual_terminal_and_numeric_wait(self):
        work = Path('/replay/work')
        command = ['/simv', '+NO_FSDB']
        valid = dict(executed=True, returncode=0, timed_out=False, cancelled=False,
                     command=command, cwd=str(work), elapsed_s=901.5)
        audit.terminal(valid, command, work)
        for key, value in [('executed', 1), ('returncode', False), ('returncode', '0'),
                           ('returncode', 1), ('timed_out', 0), ('timed_out', True),
                           ('cancelled', True), ('cancelled', None), ('elapsed_s', True),
                           ('elapsed_s', '900'), ('elapsed_s', float('nan')),
                           ('elapsed_s', float('inf')), ('elapsed_s', 0),
                           ('command', ['/old-image']), ('cwd', '/old-work')]:
            with self.subTest(key=key, value=value), self.assertRaises(Exception):
                audit.terminal(dict(valid, **{key: value}), command, work)

    def test_duplicate_or_missing_options_rejected(self):
        for command, name in [(['simv', '+PRELOAD=a', '+PRELOAD=b'], '+PRELOAD'),
                              (['simv', '-cm_name', 'a', '-cm_name', 'b'], '-cm_name'),
                              (['simv', '-cm_name'], '-cm_name'), (['simv'], '+PRELOAD')]:
            with self.subTest(command=command), self.assertRaises(Exception):
                audit.option(command, name)

    def test_actual_reference_binds_elf_symbols_and_spike(self):
        pre, pins = audit.reference_binding(audit.gold.OUT / 'input.elf', audit.ELF_SHA)
        self.assertEqual(pre['counts']['matched_instructions'], 170167)
        self.assertIn(str(audit.gold.OUT / 'spike.trace'), pins)
        with self.assertRaises(Exception):
            audit.reference_binding(audit.gold.OUT / 'input.elf', '0' * 64)
        with tempfile.TemporaryDirectory() as d:
            elf = Path(d) / 'wrong.elf'
            elf.write_bytes(b'not the replay ELF')
            with self.assertRaises(Exception):
                audit.reference_binding(elf, audit.ELF_SHA)

    def test_current_vdb_exact_argv_and_workdir(self):
        work = Path('/fresh/work')
        command = ['/current/simv', '-cm_name', audit.CASE]
        import shlex
        def info(argv=command, cwd=str(work), start='1', finish='2'):
            root = ET.Element('root')
            ET.SubElement(root, 'srctest', cmdline=shlex.join(argv), workdir=cwd,
                          starttime=start, finishtime=finish)
            return root
        with patch.object(audit.batch, 'valid_vdb', return_value={'checked': True}), \
                patch.object(audit.semantic.toggle, 'xml', return_value=info()):
            result = audit.vdb_identity(work, command)
            self.assertEqual(result['status'], 'PASS')
        for tree in [info(argv=['/old/simv']), info(cwd='/old/work'), info(start='0')]:
            with patch.object(audit.batch, 'valid_vdb', return_value={}), \
                    patch.object(audit.semantic.toggle, 'xml', return_value=tree), \
                    self.assertRaises(Exception):
                audit.vdb_identity(work, command)
        with patch.object(audit.batch, 'valid_vdb', side_effect=ValueError('truncated VDB')), \
                self.assertRaises(Exception):
            audit.vdb_identity(work, command)

    def test_reused_target_and_lifetime_negative_gates(self):
        rows, vectors = fixtures.lifecycle_fixture()
        audit.semantic.lifecycle(rows, vectors)
        for change in ('missing_target', 'wrong_restart', 'missing_done'):
            r, v = copy.deepcopy(rows), copy.deepcopy(vectors)
            if change == 'missing_target':
                r = [x for x in r if x['order'] != '11']
                v = [x for x in v if x['arch_seq'] != '11']
            elif change == 'wrong_restart':
                v[0]['vstart'] = '0'
            else:
                r = [x for x in r if x['event'] != 'uop_done']
            with self.subTest(change=change), self.assertRaises(Exception):
                audit.semantic.lifecycle(r, v)
        for n in range(12):
            data = fixtures.actual(n)
            audit.semantic.target_bytes(data, n)
            key = next(iter(data))
            data[key] = (data[key][0] ^ 1, None)
            with self.assertRaises(Exception):
                audit.semantic.target_bytes(data, n)

    def test_historical_trace_semantics_only_without_old_context_or_gain(self):
        pre, _ = audit.reference_binding(audit.gold.OUT / 'input.elf', audit.ELF_SHA)
        native = audit.ROOT / 'verification/out/valu-restart783-old-image-agent-20261008-01'
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(audit.semantic, 'target_gain', side_effect=AssertionError('forbidden')), \
                patch.object(audit.semantic.run, 'check', side_effect=AssertionError('forbidden')):
            result = audit.check_semantics(native, native / 'console.log', pre, Path(directory))
        self.assertEqual(result['full_scalar_retirements'], 170167)
        self.assertEqual(len(result['per_instruction_oracles']), 12)
        self.assertEqual(result['lifecycle']['requests'], 896)
        self.assertNotIn('target_raw_gain', result)

    def test_rejection_persisted_and_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            run, output = Path(directory) / 'run', Path(directory) / 'audit'
            run.mkdir()
            with patch.object(audit, 'bind_run', side_effect=ValueError('invalid receipt')), \
                    self.assertRaises(ValueError):
                audit.audit(run, output)
            before = (output / 'rejection.json').read_bytes()
            self.assertEqual(json.loads(before)['status'], 'FAIL')
            with self.assertRaises(FileExistsError):
                audit.audit(run, output)
            self.assertEqual((output / 'rejection.json').read_bytes(), before)

    def test_full_audit_orchestration_never_calls_old_collect(self):
        with tempfile.TemporaryDirectory() as directory:
            run, output = Path(directory) / 'run', Path(directory) / 'audit'
            work = run / 'work'
            work.mkdir(parents=True)
            (run / 'console.log').write_text('console')
            for name in ('run.vcs.log', 'commit_trace.csv', 'vector_trace.csv'):
                (work / name).write_text('fixture')
            with patch.object(audit, 'bind_run', return_value=({'command': ['/current']}, {}, {}, work, {})), \
                    patch.object(audit, 'vdb_identity', return_value={'status': 'PASS'}), \
                    patch.object(audit, 'check_semantics', return_value={'software_checks': 13144}), \
                    patch.object(audit.semantic, 'collect', side_effect=AssertionError('forbidden')):
                result = audit.audit(run, output)
            self.assertEqual(result['status'], 'PASS')
            self.assertFalse(result['coverage_admitted'])
            self.assertNotIn('target_raw_gain', result)
            audit.life.check(result['pins'])
            (work / 'commit_trace.csv').write_text('mutated')
            with self.assertRaises(Exception):
                audit.life.check(result['pins'])


if __name__ == '__main__':
    unittest.main()
