"""Host-only synthetic RVFI, actual SoC specs and full original model counts."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
import checker as c
import replay as r


def records(spec, gold, mutation=None):
    s, code = spec['backend']['symbols'], {int(k): v for k, v in spec['backend']['code'].items()}
    helper_pcs = {x['pc'] for rows in spec['backend']['helpers'].values() for x in rows}
    width = spec['config']['sew'] // 8
    assignments = {}
    stores, loads, candidates = {}, {}, []
    for pc, insn in code.items():
        if pc in helper_pcs or pc in (s['_start'], s['main'], s['failure']):
            continue
        if insn & 3 == 3 and insn & 127 in (0x13, 0x1b, 0x17, 0x37, 0x33, 0x3b):
            assignments.setdefault((insn >> 7) & 31, pc)
        d = c.memory_op(insn)
        if pc >= s['selected'] and d and d['base'] != d['register'] and d['base'] and d['register']:
            candidates.append((pc, d))
    for pc, d in candidates:
        if d['base'] in assignments and d['register'] in assignments:
            (stores if d['kind'] == 'write' else loads).setdefault(d['size'], (pc, d))
    order = 0
    cached = {}
    def row(pc, rd=0, value=0, addr=0, rm=0, wm=0, data=0):
        nonlocal order
        out = dict(cycle=str(order + 1), event='retire', order=str(order), port='0', trans_id='-1',
                   pc=f'{pc:016x}', insn=f'{code[pc]:08x}', rd=str(rd), rd_wdata=f'{value & c.MASK64:016x}',
                   mem_addr=f'{addr:016x}', mem_rmask=f'{rm:02x}', mem_wmask=f'{wm:02x}',
                   mem_wdata=f'{data & c.MASK64:016x}', trap='0')
        order += 1
        return out
    def setreg(reg, value):
        return row(assignments[reg], reg, value)
    def write(addr, value, size, pc=None, desc=None):
        # Host fixture optimization only: every call still checks every setup byte.
        if 0x80000000 <= addr < 0x90000000:
            data = [(value >> (8 * j)) & 255 for j in range(size)]
            if all(cached.get(addr + j) == byte for j, byte in enumerate(data)):
                return
            cached.update({addr + j: byte for j, byte in enumerate(data)})
        pc, d = (pc, desc) if pc is not None else stores[size]
        yield setreg(d['base'], addr - d['offset'])
        if d['register']:
            yield setreg(d['register'], value)
        yield row(pc, addr=addr, wm=((1 << size) - 1) << (addr % 8), data=value)
    def text(text):
        for byte in text.encode('ascii'):
            yield from write(spec['uart'], byte, 1)
    yield row(s['_start'], 3, 0)
    for pc in spec['csr_prelude'][:5]:
        yield row(pc)
    yield setreg(6, s['__bss_end'])
    for addr in range(s['__bss_start'], s['__bss_end'], 8):
        yield setreg(5, addr)
        yield row(spec['bss_store'], addr=addr, wm=255, data=0)
    yield row(s['main'])
    pc = spec['csr_prelude'][5]
    yield row(pc, (code[pc] >> 7) & 31, 128)
    yield from text('BOARD_CASE_BEGIN ' + spec['config']['id'] + '\n')
    for i, x in enumerate(spec['backend']['helpers']['capacity']):
        yield row(x['pc'], 5 if i == 0 else 10 if i == 1 else 0, c.MASK64 if i == 0 else 16 if i == 1 else 0)
    for ordinal, g in enumerate(gold):
        for name, values, size in (('a', g['a'], width), ('b', g['b'], width), ('mask', g['mask'], 1), ('out', [91] * 18, width)):
            for j, value in enumerate(values):
                if mutation == 'fp_setup' and g['op'] == 25 and name == 'a' and j == 0:
                    value ^= 1
                yield from write(s[name] + j * size, value, size)
        args = [s['a'], s['b'], s['out'] + width, g['vl'], 16, s['mask'], g['vstart']]
        if mutation == 'args' and ordinal == 0:
            args[1] += width
        for reg, value in enumerate(args, 10):
            yield setreg(reg, value)
        window = spec['backend']['helpers'][f'op_{g["op"]}']
        for i, x in enumerate(window):
            rd, val = 0, 0
            if i in (0, 5, 10):
                rd, val = 5, g['vl'] if i == 5 else 16
            if i == 6:
                rd, val = 28, 7
            if i == 9:
                rd, val = 10, 1 if mutation == 'vstart' and ordinal == 0 else 0
            item = row(x['pc'], rd, val)
            if mutation == 'encoding' and ordinal == 0 and i == 8:
                item['insn'] = 'deadbeef'
            if mutation == 'duplicate_window' and ordinal == 0 and i == 12:
                yield row(window[8]['pc'])
            yield item
        if mutation == 'early_end' and ordinal == 0:
            return
        pc, d = loads[width]
        for element in range(18):
            expected = 91 if element in (0, 17) else g['expected'][element - 1]
            lane = element - 1
            if 0 <= lane < 16 and g['op'] == 0:
                active = g['vstart'] <= lane < g['vl'] and (g['mask'][lane // 8] >> (lane % 8)) & 1
                inactive = g['vstart'] <= lane < g['vl'] and not (g['mask'][lane // 8] >> (lane % 8)) & 1
                if ((mutation == 'active' and active) or (mutation == 'inactive' and inactive) or
                        (mutation == 'prestart' and lane < g['vstart']) or (mutation == 'tail' and lane >= g['vl'])):
                    expected ^= 1
            if mutation == 'result' and ordinal == 0 and element == 1:
                expected ^= 1
            if mutation == 'guard' and ordinal == 0 and element == 17:
                expected ^= 1
            if mutation == 'last_guard' and ordinal == len(gold) - 1 and element == 17:
                expected ^= 1
            if mutation == 'missing_tail' and ordinal == 0 and element == 16:
                continue
            address = s['out'] + element * width
            yield setreg(d['base'], address - d['offset'])
            value = c.loaded_value(expected, width, d['signed'])
            item = row(pc, d['register'], value, addr=address, rm=((1 << width) - 1) << (address % 8))
            if mutation == 'wrong_rmask' and ordinal == 0 and element == 1:
                item['mem_rmask'] = 'ff'
            if mutation == 'wrong_sign' and ordinal == 0 and element == 1:
                item['rd_wdata'] = f'{value | (1 << 63):016x}'
            yield item
    for name, value in (('checks', len(gold)), ('elements', 16 * len(gold)), ('errors', 0)):
        yield from write(s[name], value, 8)
    yield from text(c.marker(spec['config']) + '\nARITHMETIC_FULL_PASS ' + spec['config']['id'] + '\nBOARD_REPLAY_PASS\n')
    pc = spec['exit_store']
    yield from write(spec['ctrl'], 1 if mutation == 'htif1' else 0, 8, pc, c.memory_op(code[pc]))
    yield row(spec['park'])


class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.specs = {s: c.specification(s) for s in c.SHAPES}
        cls.gold = {s: c.read(c.REF / s / 'model.json') for s in c.SHAPES}
        cls.positives = []

    def run_scope(self, shape, mutation=None):
        state = c.Strict(self.specs[shape], self.gold[shape])
        for row in records(self.specs[shape], self.gold[shape], mutation):
            state.consume(row)
        return state.finish()

    def test_full_positive_e8(self):
        result = self.run_scope(c.SHAPES[0])
        self.assertEqual((result['calls'], result['results'], result['guards']), (4095, 65520, 8190))
        self.positives.append(c.SHAPES[0])

    def test_full_positive_e32(self):
        result = self.run_scope(c.SHAPES[1])
        self.assertEqual((result['calls'], result['results'], result['guards']), (5985, 95760, 11970))
        self.positives.append(c.SHAPES[1])

    def test_full_scope_negatives(self):
        for mutation in ('args', 'encoding', 'duplicate_window', 'vstart', 'result', 'guard', 'missing_tail',
                         'wrong_rmask', 'wrong_sign', 'early_end', 'active', 'inactive', 'prestart', 'tail'):
            with self.subTest(mutation=mutation):
                with self.assertRaises(ValueError):
                    self.run_scope(c.SHAPES[0], mutation)

    def test_fp_transition(self):
        with self.assertRaisesRegex(ValueError, 'FP transition'):
            self.run_scope(c.SHAPES[1], 'fp_setup')

    def test_last_full_guard(self):
        with self.assertRaisesRegex(ValueError, 'guard mismatch'):
            self.run_scope(c.SHAPES[1], 'last_guard')

    def test_signed_load_contract(self):
        self.assertEqual(c.loaded_value(0x80000000, 4, True), 0xffffffff80000000)
        self.assertEqual(c.loaded_value(0x80000000, 4, False), 0x80000000)
        self.assertEqual(c.loaded_value(0xff, 1, False), 255)
        self.assertNotEqual(c.loaded_value(0xff, 1, True), 255)

    def test_ctrl_not_htif(self):
        with self.assertRaisesRegex(ValueError, 'CTRL raw0'):
            self.run_scope(c.SHAPES[0], 'htif1')

    def test_markers(self):
        p = self.specs[c.SHAPES[0]]['config']
        text = 'BOARD_CASE_BEGIN ' + p['id'] + '\n' + c.marker(p) + '\nARITHMETIC_FULL_PASS ' + p['id'] + '\nBOARD_REPLAY_PASS\n' + c.common.SUCCESS + '\n$finish'
        c.console_gate(text, p)
        for bad in (text.replace(c.marker(p), ''), text + '\nRVV_MATRIX_DETAIL index=1', text.replace('4095', '56')):
            with self.assertRaises(ValueError):
                c.console_gate(bad, p)

    def test_actual_partial_detail_monitor(self):
        # Real frozen monitor, one scalar Host process, no simulator/reference.
        ledger, repo, _ = c.common.image_context(r.IMAGE)
        import ara_verify.runner as engine
        previous = engine.FAIL_RE
        engine.FAIL_RE = c.VETO
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cmd = [sys.executable, '-c', 'import sys,time;sys.stdout.write("RVV_MATRIX_DETAIL index=1");sys.stdout.flush();time.sleep(10)']
                rc, elapsed, timed, failed = engine._run_monitored(cmd, root, root / 'console', 3, threading.Event())
                self.assertTrue(failed)
                self.assertFalse(timed)
                self.assertLess(elapsed, 3)
        finally:
            engine.FAIL_RE = previous

    def test_outcome_survives_checker_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = dict(command=['simv', '+TESTCASE=arithmetic_full_e8_mf8'], cwd=str(root / 'work'))
            r.durable(root / 'command.json', command)
            abort = threading.Event()
            monitored = r.monitored_with_outcome(lambda *a: (0, 1.25, False, False), abort)
            self.assertEqual(monitored(command['command'], root / 'work', root / 'console.log', 10800)[0], 0)
            try:
                raise ValueError('Intentional postcheck exception')
            except ValueError:
                pass
            out = c.read(root / 'child_outcome.unvalidated.json')
            self.assertEqual(out['returncode'], 0)
            self.assertFalse(out['architectural_acceptance'])
            self.assertEqual(out['command'], command['command'])

    def test_late_abort_and_checkerthrow(self):
        for throwing in (False, True):
            abort = threading.Event()
            result = SimpleNamespace(status='PASS', returncode=0, reason='')
            class Parent:
                def __init__(self): pass
                def _run_test(self, *a): return result
            def check(_):
                abort.set()
                if throwing:
                    raise ValueError('postcheck')
            cls = r.checked_runner(Parent, abort, check, lambda n: None)
            actual = cls()._run_test(SimpleNamespace(name='test'), None)
            self.assertNotEqual(actual.status, 'PASS')
            self.assertEqual(actual.returncode, 0)
            self.assertTrue(abort.is_set())

    def test_missing_admission(self):
        with self.assertRaises(ValueError):
            r.reviews({}, 'sha', None, None, None, None)

    def test_late_disk_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            r.durable(root / 'plan.json', {})
            with self.assertRaisesRegex(ValueError, 'Late disk plan drift'):
                r.terminal_disk_gate(root, 'wrong', r.IMAGE)

    def test_bounds_owner(self):
        props = dict(Id=r.UNIT, LoadState='loaded', ActiveState='active', SubState='running', MainPID='7',
                     ControlGroup='/owned/' + r.UNIT, RuntimeMaxUSec='3h 40min', KillMode='control-group', Restart='no')
        r.owner_gate(props, '0::/owned/' + r.UNIT, 7)
        for key, value in (('RuntimeMaxUSec', '4h'), ('MainPID', '8'), ('KillMode', 'process')):
            with self.assertRaises(ValueError):
                r.owner_gate(dict(props, **{key: value}), '0::/owned/' + r.UNIT, 7)
        self.assertEqual((r.JOBS, r.CASE_BOUND, r.WORKER_BOUND, r.OUTER), (2, 10800, 12000, 13200))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Host))
    pins = {str(c.HERE / name): c.sha(c.HERE / name) for name in ('checker.py', 'replay.py', 'test_host.py')}
    r.durable(c.HERE / 'host03.json', dict(status='PASS_HOST_ONLY' if result.wasSuccessful() else 'FAIL_HOST_ONLY',
              tests=result.testsRun, failures=len(result.failures) + len(result.errors),
              full_positive_shapes=[s for s in c.SHAPES if s in Host.positives], pins=pins))
    raise SystemExit(not result.wasSuccessful())
