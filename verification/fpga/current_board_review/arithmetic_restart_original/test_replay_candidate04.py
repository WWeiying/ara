#!/usr/bin/env python3
"""Host-only acceptance/admission tests; never constructs a simulation runner."""
import copy
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

import replay_candidate04 as replay


class Tests(unittest.TestCase):
    def setUp(self):
        self.programs = replay.read(replay.PREPARED/'soc/programs.json')['programs']

    def valid(self, name):
        entry = dict(self.programs[name], id=name)
        text = '\n'.join(['BOARD_CASE_BEGIN '+name, *entry['pass_markers'],
                          'Core Test *** SUCCESS *** (tohost = 0)', '$finish'])+'\n'
        return entry, text

    def test_exact_five_and_counts(self):
        self.assertEqual(list(self.programs), replay.NAMES)
        self.assertEqual([x['configurations'] for x in self.programs.values()], replay.COUNTS)

    def test_all_five_valid(self):
        for name in replay.NAMES:
            entry, text = self.valid(name)
            self.assertTrue(replay.console_ok(text, entry))

    def test_raw_contradictions(self):
        entry, text = self.valid(replay.NAMES[0])
        for token in ('RVV_MATRIX_FAIL', 'RVV_MATRIX_FAILED', 'RVV_MATRIX_UNSUPPORTED_CAPACITY',
                      'BOARD_CASE_FAIL', 'BOARD_REPLAY_TRAP', 'BOARD_REPLAY_MISMATCH',
                      'BOARD_REPLAY_SERVICE_FAIL', 'BOARD_REPLAY_VLEN_FAIL',
                      'Core Test *** FAILED', 'Error-[bad]', 'Fatal: bad', 'FATAL', 'UVM_FATAL', 'SKIP'):
            with self.subTest(token=token): self.assertFalse(replay.console_ok(text+token, entry))

    def test_missing_and_duplicate(self):
        entry, text = self.valid(replay.NAMES[0])
        for line in text.splitlines():
            self.assertFalse(replay.console_ok(text.replace(line+'\n',''), entry))
        for marker in entry['pass_markers']:
            self.assertFalse(replay.console_ok(text+marker+'\n', entry))

    def test_wrong_count(self):
        entry, text = self.valid(replay.NAMES[0])
        self.assertFalse(replay.console_ok(text.replace('cases=56', 'cases=55'), entry))
        self.assertFalse(replay.console_ok(text.replace('errors=0', 'errors=1'), entry))

    def test_scope_does_not_claim_old_text(self):
        ready = replay.read(replay.HERE/'readiness01.json')
        self.assertFalse(ready['original_C_bytes_recovered'])
        self.assertEqual(ready['exact_reconstructed_original_linux_elf_count'],22)

    def test_budget_jobs2(self):
        self.assertEqual(replay.makespan(replay.TIMEOUTS),8000)
        self.assertLess(replay.makespan(replay.TIMEOUTS),10000)

    def test_reservations_before_release_blocked(self):
        live = [dict(argv=['simv',str(replay.PRIOR/'replay/tests'/str(i))]) for i in range(4)]
        report = replay.capacity(live,64*1024**3,replay.HERE/'future')
        self.assertFalse(report['passed'])
        self.assertEqual(report['total_live_reserved'],26)

    def test_after_release_reservations_still_held(self):
        report = replay.capacity([],64*1024**3,replay.HERE/'future')
        self.assertTrue(report['passed'])
        self.assertEqual(report['total_live_reserved'],22)

    def test_count_live_reserved_without_double_count(self):
        live = []
        for slots, root in replay.RESERVATIONS.values():
            live += [dict(argv=['simv'],cwd=str(root/'tests'/str(i))) for i in range(slots)]
        report = replay.capacity(live,64*1024**3,replay.HERE/'future')
        self.assertTrue(report['passed'])
        self.assertEqual(report['total_live_reserved'],22)

    def test_unknown_live_not_hidden(self):
        live = [dict(argv=['simv','/external/'+str(i)]) for i in range(3)]
        self.assertFalse(replay.capacity(live,64*1024**3,replay.HERE/'future')['passed'])

    def test_memory_floor_and_collision(self):
        out = replay.HERE/'future'
        self.assertFalse(replay.capacity([],31*1024**3,out)['passed'])
        self.assertFalse(replay.capacity([dict(argv=['simv',str(out/'replay')])],64*1024**3,out)['passed'])

    def test_predecessor_exact_terminal(self):
        names = ['old'+str(i) for i in range(38)]
        rows = [dict(name=n,status='PASS',returncode=0) for n in names]
        terminal = dict(status='PASS_38_CANDIDATE04',plan_sha256='approved',image_sha256=replay.IMAGE_SHA,
                        pins_unchanged=True,finished=1,results=rows)
        run = dict(status='COMPLETE',status_counts={'PASS':38},tests=names)
        replay.validate_terminal38(terminal,run,rows,names,'approved')
        for field, value in (('status','RUNNING'),('status','PASS_38_CANDIDATE02'),
                             ('image_sha256','old'),('plan_sha256','old'),('pins_unchanged',False)):
            bad = dict(terminal,**{field:value})
            with self.assertRaises(ValueError): replay.validate_terminal38(bad,run,rows,names,'approved')
        bad = copy.deepcopy(terminal);bad['results'][3]['returncode']=1
        with self.assertRaises(ValueError): replay.validate_terminal38(bad,run,rows,names,'approved')
        with self.assertRaises(ValueError): replay.validate_terminal38(terminal,run,rows[:-1],names,'approved')

    def test_unapproved_work_never_runs(self):
        with self.assertRaises(ValueError): replay.work(Path('/not-an-output'),None,False)

    def test_checker_io_exception_cancels(self):
        class Parent:
            def _run_test(self,test,image):
                return SimpleNamespace(status='PASS',returncode=0,artifact_dir=Path('/missing/console'))
        runner = replay.runner_class(Parent,{})()
        runner.cancel_event = threading.Event()
        with self.assertRaises(OSError): runner._run_test(None,None)
        self.assertTrue(runner.cancel_event.is_set())

    def test_failure_cancels_peers(self):
        class Parent:
            def _run_test(self,test,image): return SimpleNamespace(status='FAIL')
        runner = replay.runner_class(Parent,{})()
        runner.cancel_event = threading.Event()
        runner._run_test(None,None)
        self.assertTrue(runner.cancel_event.is_set())

    def test_raw_failure_cancels_peers(self):
        name = replay.NAMES[0];entry,text = self.valid(name)
        with tempfile.TemporaryDirectory(dir=replay.HERE) as root:
            directory = Path(root);(directory/'console.log').write_text(text+'RVV_MATRIX_FAIL\n')
            class Parent:
                def _run_test(self,test,image):
                    return SimpleNamespace(status='PASS',returncode=0,artifact_dir=directory)
            runner = replay.runner_class(Parent,{name:entry})();runner.cancel_event=threading.Event()
            self.assertEqual(runner._run_test(SimpleNamespace(name=name),None).status,'FAIL')
            self.assertTrue(runner.cancel_event.is_set())


if __name__=='__main__':
    unittest.main()
