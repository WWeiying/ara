"""Synthetic host-only artifacts. Never opens the current simulation output."""
import json
from pathlib import Path
import tempfile
import unittest

import check_terminal as checker


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


class TerminalAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='alias-terminal-host-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'output'
        snapshot = self.base / 'snapshot'
        save(snapshot / 'snapshot.json', {'synthetic': True})
        image = self.base / 'image'
        image.mkdir()
        simv = image / 'simv'
        simv.write_bytes(b'not executable: host fixture only')
        image_files = {str(simv): checker.sha(simv)}
        image_ledger = dict(simv=str(simv), files=image_files, snapshot=str(snapshot),
                            snapshot_sha256=checker.sha(snapshot / 'snapshot.json'))
        save(image / 'image.json', image_ledger)
        prepared = self.base / 'prepared'
        prepared.mkdir()
        (prepared / 'source.c').write_text('/* synthetic */')
        save(prepared / 'provenance.json', dict(files={'source.c': checker.sha(prepared / 'source.c')}))
        programs_dir = self.base / 'soc'
        programs_dir.mkdir()
        entries, stages = {}, []
        for stage in ('tuple', 'prefix'):
            names, results = [], []
            for shape, sew, prefix_count in checker.SHAPES:
                name = f'rvv_masks_alias_restart_{shape}_{stage}'
                count = 1 if stage == 'tuple' else prefix_count
                names.append(name)
                elf = programs_dir / (name + '.elf')
                elf.write_bytes(b'synthetic ELF ' + name.encode())
                digest = checker.sha(elf)
                entries[name] = dict(path=str(elf), sha256=digest, cases=[name], configurations=count)
                artifact = self.root / stage / 'tests' / name
                artifact.mkdir(parents=True)
                private = artifact / 'input.elf'
                private.write_bytes(elf.read_bytes())
                save(artifact / 'inputs.json', dict(binary=dict(source=str(elf), path=str(private), sha256=digest),
                                                    simv=dict(path=str(simv), image_sha256=image_files)))
                save(artifact / 'command.json', dict(command=[str(simv), '+PRELOAD=' + str(private), '+TESTCASE=' + name],
                                                     cwd=str(artifact / 'work')))
                (artifact / 'console.log').write_text(
                    f'BOARD_CASE_BEGIN {name}\nRVV_MASK_TRIAL vl=512 vstart=256\n'
                    f'RVV_MASK_PASS sew={sew} cases={count} errors=0\n'
                    f'BOARD_CASE_PASS {name}\nBOARD_REPLAY_PASS\n'
                    'Core Test *** SUCCESS *** (tohost = 0)\n')
                results.append(dict(name=name, status='PASS', returncode=0, reason='', artifact_dir=str(artifact)))
            save(self.root / stage / 'run.json', dict(status='COMPLETE', completed_at='synthetic',
                                                     tests=names, status_counts={'PASS': 3}, simv=str(simv)))
            save(self.root / stage / 'summary.json', results)
            stages.append(dict(stage=stage, passed=True, returncode=0, results=results))
        save(programs_dir / 'programs.json', dict(backend='vcs-soc', programs=entries, prepared=str(prepared),
                                                 provenance_sha256=checker.sha(prepared / 'provenance.json')))
        save(self.root / 'plan.json', dict(jobs=1, phases=['tuple', 'prefix'], prefix_requires_all_three_tuples_PASS=True,
                                          programs=str(programs_dir), image=str(image), simv=str(simv), pins=image_files))
        plan_hash = checker.sha(self.root / 'plan.json')
        save(self.root / 'launch.json', dict(returncode=0, plan_sha256=plan_hash))
        save(self.root / 'complete.json', dict(status=checker.COMPLETE, finished=1, plan_sha256=plan_hash, stages=stages))
        self.anchors = dict(programs_sha256=checker.sha(programs_dir / 'programs.json'),
                            image_sha256=checker.sha(image / 'image.json'))
        self.artifact = self.root / 'tuple/tests/rvv_masks_alias_restart_e8_m4_tuple'

    def check(self):
        return checker.check(self.root, **self.anchors)

    def test_valid_and_read_only(self):
        before = {str(p): checker.sha(p) for p in self.base.rglob('*') if p.is_file()}
        result = self.check()
        self.assertEqual(len(result['results']), 6)
        self.assertTrue(result['read_only'])
        self.assertEqual(before, {str(p): checker.sha(p) for p in self.base.rglob('*') if p.is_file()})

    def test_contradictory_success_and_failure(self):
        log = self.artifact / 'console.log'
        valid = log.read_text()
        for failure in ('RVV_MASK_FAIL sew=8 cases=1 errors=1', 'BOARD_CASE_FAIL original',
                        'BOARD_REPLAY_TRAP case=1', 'BOARD_REPLAY_SERVICE_FAIL',
                        'Core Test *** FAILED ***', 'Fatal: assertion failed', 'UVM_FATAL bad', 'FAILED.'):
            with self.subTest(failure=failure):
                log.write_text(valid + failure + '\n')
                with self.assertRaisesRegex(checker.Rejected, 'failure marker veto'):
                    self.check()

    def test_incomplete_campaign(self):
        (self.root / 'complete.json').unlink()
        with self.assertRaises(checker.Incomplete):
            self.check()

    def test_incomplete_runner_even_with_success_markers(self):
        path = self.root / 'prefix/run.json'
        record = checker.read(path)
        record['status'] = 'RUNNING'
        save(path, record)
        with self.assertRaises(checker.Incomplete):
            self.check()

    def test_wrong_count(self):
        path = self.artifact / 'console.log'
        path.write_text(path.read_text().replace('cases=1 ', 'cases=98 '))
        with self.assertRaisesRegex(checker.Rejected, 'oracle count'):
            self.check()

    def test_input_drift(self):
        (self.artifact / 'input.elf').write_bytes(b'wrong input')
        with self.assertRaisesRegex(checker.Rejected, 'private ELF differs'):
            self.check()

    def test_unsuccessful_exit(self):
        path = self.artifact / 'console.log'
        path.write_text(path.read_text().replace('tohost = 0', 'tohost = 1'))
        with self.assertRaisesRegex(checker.Rejected, 'firmware exit'):
            self.check()

    def test_runner_returncode(self):
        path = self.root / 'tuple/summary.json'
        results = checker.read(path)
        results[0]['returncode'] = 1
        save(path, results)
        terminal = checker.read(self.root / 'complete.json')
        terminal['stages'][0]['results'] = results
        save(self.root / 'complete.json', terminal)
        with self.assertRaisesRegex(checker.Rejected, 'unsuccessful runner'):
            self.check()

    def test_extra_result(self):
        path = self.root / 'tuple/summary.json'
        results = checker.read(path)
        save(path, results + [results[0]])
        with self.assertRaisesRegex(checker.Rejected, 'duplicate/missing/extra'):
            self.check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
