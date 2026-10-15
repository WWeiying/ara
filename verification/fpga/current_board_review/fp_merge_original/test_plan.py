"""Focused host-only checks; synthetic trace fixtures are not DUT evidence."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import checker
import replay as r


def fixture():
    rows = []
    def emit(pc, insn, rd=0, value=0, **extra):
        row = dict(cycle=str(len(rows)), event='retire', order=str(len(rows)), trap='0',
            pc=f'{pc:x}', insn=f'{insn:x}', rd=str(rd), rd_wdata=f'{value:x}',
            mem_addr='0', mem_rmask='00', mem_wmask='00', mem_wdata='0')
        row.update(extra)
        rows.append(row)
    seq = json.loads((checker.PREP / 'call_sequence.json').read_text())
    for expected in seq:
        ctrl = (expected['sticky'] << 32) | expected['vstart']
        for rd, value in ((11, 0x1000), (13, expected['vl']), (14, 512), (16, ctrl)):
            emit(0x80000100, 0x13 | (rd << 7), rd, value)
        for step, (pc, insn, _) in enumerate(checker.layout()):
            rd, value, extra = 0, 0, {}
            if step == 0:
                rd = 30
            elif step in (1, 6, 18):
                rd, value = 5, expected['vl'] if step == 6 else 512
            elif step == 5:
                value = 0xffffffffffff0000
                extra = dict(mem_addr='1000', mem_rmask='ff')
            elif step in (7, 9, 10):
                rd = 7
                value = expected['sticky'] if step == 7 else (ctrl << 32) & ((1 << 64) - 1) if step == 9 else expected['vstart']
            elif step == 13:
                rd = 10
            elif step in (14, 15):
                rd, value = 6, expected['sticky'] << (32 if step == 15 else 0)
            elif step == 16:
                rd, value = 10, expected['sticky'] << 32
            emit(pc, insn, rd, value, **extra)
    emit(0x80000072, 0x00a2b023, mem_addr='d0000000', mem_wmask='ff')
    return rows


class PlanTests(unittest.TestCase):
    def test_exact195_states_and_exit(self):
        self.assertEqual(checker.retirement(fixture())['calls'], 195)

    def test_state_and_instruction_corruptions(self):
        for pc, field, value in [(0x800005e6, 'insn', '5e805c57'), (0x800005e6, 'pc', '800005e8'),
                (0x800005ce, 'rd_wdata', '1'), (0x800005de, 'rd_wdata', '2'),
                (0x800005d2, 'rd_wdata', '10'), (0x800005ca, 'rd_wdata', '0'),
                (0x800005ea, 'rd_wdata', '1'), (0x800005ee, 'rd_wdata', '10')]:
            with self.subTest(pc=hex(pc), field=field):
                rows = fixture()
                next(x for x in rows if int(x['pc'], 16) == pc)[field] = value
                with self.assertRaises(ValueError):
                    checker.retirement(rows)

    def test_missing_call_exit_or_trap(self):
        for kind in ('lastcall', 'exit', 'trap', 'badexit'):
            rows = fixture()
            if kind == 'lastcall':
                rows = rows[:-26]
            elif kind == 'exit':
                rows.pop()
            elif kind == 'trap':
                rows[0]['trap'] = '1'
            else:
                rows[-1]['mem_wdata'] = '1'
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                checker.retirement(rows)

    def test_raw_markers(self):
        good = '\n'.join(r.read(r.PREP / 'programs.json')['soc']['pass_markers']) + '\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
        checker.console(good)
        for bad in (good + 'RVV_FP_MOVE_DETAIL\n', good + 'RVV_FP_MOVE_TRACE_DRAIN_FAILED\n', good.replace('cases=195', 'cases=194'),
                    good.replace('$finish', ''), good.replace('tohost = 0', 'tohost = 1'),
                    good + 'BOARD_REPLAY_PASS\n'):
            with self.assertRaises(ValueError):
                checker.console(bad)

    def test_reservation21_and_overflow(self):
        units = r.read(r.DEPENDENCY_REVIEW)['units']
        self.assertEqual(r.resource_math([], 40 * 1024**3, units)['total_live_plus_reserved'], 21)
        own = dict(pid=1, cgroup='0::/user.slice/' + r.UNIT)
        self.assertEqual(r.resource_math([own], 40 * 1024**3, units)['total_live_plus_reserved'], 21)
        with self.assertRaises(ValueError):
            r.resource_math([dict(pid=i, cgroup='0::/other') for i in range(4)], 40 * 1024**3, units)

    def test_late_abort_during_checker(self):
        abort = r.Abort()
        class Parent:
            def __init__(self):
                pass
            def _run_test(self, test, image):
                return SimpleNamespace(status='PASS', reason='', artifact_dir=Path('/not-written'))
        def check(*args):
            abort.set()
            return {}
        cls = r.runner_class(Parent, {}, abort)
        with patch.object(r, 'check_artifact', side_effect=check), patch.object(r, 'save'):
            self.assertEqual(cls()._run_test(None, None).status, 'CANCELLED')

    def test_atomic_abort_publication(self):
        with tempfile.TemporaryDirectory(dir=r.HERE) as folder:
            path = Path(folder) / 'terminal.json'
            abort = r.Abort()
            abort.set()
            self.assertFalse(abort.publish(path, dict(calls=195), True))
            self.assertEqual(r.read(path)['status'], 'NOT_PASS')

    def test_incomplete_runner_rejected(self):
        result = SimpleNamespace(name=r.NAME, status='PASS', returncode=0, reason='', artifact_dir=r.RUN / 'replay/tests' / r.NAME)
        row = dict(vars(result), artifact_dir=str(result.artifact_dir))
        with patch.object(r, 'read', side_effect=[dict(status='INTERRUPTED', status_counts={'PASS': 1}), [row]]):
            with self.assertRaises(ValueError):
                r.terminal(result, r.RUN / 'replay')


if __name__ == '__main__':
    unittest.main()
