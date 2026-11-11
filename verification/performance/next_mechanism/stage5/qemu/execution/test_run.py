#!/usr/bin/env python3
"""Directed host mutations; synthetic logs are never guest acceptance."""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as r
c = r.c


def fixtures(kind):
    path, report, f, fixture = c.stage4(kind)
    data = (path / 'data.bin').read_bytes()
    groups, lines, fcsrs = {}, [], []
    for t, tr in enumerate(fixture['trials']):
        case = fixture['oracle']['cases'][tr['case']]
        shape, expected = case['case'], case['expected']
        rows, d = shape.get('rows', shape['heads']), shape['dimension']
        ng, n = shape['heads'] // rows, shape['heads'] * d
        fcsr = tr['frm'] * 32 | tr['initial_flags'] | expected['fflags']
        fcsrs.append(fcsr)
        lines.append('FEATURE_CALL trial=%d case=%d requested=%d frm=%d initial=%d begin=%d returned=%d end=%d '
                     'fcsr=%d vcsr=5 vstart=0 groups=%d errors=0' %
                     (t, tr['case'], tr['requested'], tr['frm'], tr['frm'] * 32 | tr['initial_flags'],
                      10 + t * 100, 20 + t * 100, 30 + t * 100, fcsr, ng))
        for g in range(ng):
            row = dict(trial=t, group=g, first=g * rows, rows=rows, q=0x80040000 + g * rows * 256,
                       k=0x80100000 + g * 65536, v=0x80200000 + g * 65536, out=0x80050000 + g * rows * 512)
            groups[t, g] = row
            lines.append('FEATURE_GROUP ' + ' '.join(k + '=' + (format(v, 'x') if k in ('q', 'k', 'v', 'out')
                                                               else str(v)) for k, v in row.items()))
        q = bytearray(b'\xa5' * 1536)
        for h, row in enumerate(shape.get('query_rows', [0, 1])):
            q[h * 256:h * 256 + d * 2] = data[row * 256:row * 256 + d * 2]
        guards = 384 + (768 - n) * 6 + (2048 - rows * d) * 2 + (8 - rows) * 268 + 32
        lines.append('FEATURE_MEMORY trial=%d query_hash=%x guard_hash=%x guard_bytes=%d' %
                     (t, f.f.fnv(q), f.f.fnv(b'\xa5' * guards), guards))
        lines += ['FEATURE_OUT trial=%d index=%d bits=%x' % (t, i, bits) for i, bits in enumerate(expected['bits'])]
    lines += ['FEATURE_DATA bytes=%d hash=%x' % (fixture['data_bytes'], fixture['data_hash']),
              'FEATURE_DONE calls=%d errors=0' % len(fixture['trials'])]
    return path, report, f, fixture, data, groups, fcsrs, '\n'.join(lines) + '\n'


def synthetic_events(bundle):
    path, report, f, fixture, data, groups, flags, text = bundle
    bound = c.binding(fixture['kind'], report)
    word_pc = {word: pc for pc, word in bound['custom'].items()}
    info_pc = next(pc for pc, w in bound['custom'].items() if w & 0xfff0707f == 0x405b)
    events, seq = [], 0
    def entry(name):
        events.append(('exec', dict(pc=bound['entries'][name]['pc'], tb='0x1')))
    for t in range(len(fixture['trials'])):
        entry('feature_full_call')
        for index in (3, 2, 1, 0):
            events += [('exec', dict(pc=info_pc, tb='0x1')), ('info', dict(index=index, result=c.INFO[index]))]
        for name, count in f.expected_entries(fixture, fixture['trials'][t]).items():
            for _ in range(count):
                entry(name)
        for op in c.schedule(fixture, t, groups, f):
            seq += 1
            pc = word_pc[op['insn']]
            events.append(('exec', dict(pc=pc, tb='0x1')))
            rs1 = 0x80060000 if op['a'] is None else op['a']
            events.append(('begin', dict(seq=seq, pc=pc, insn=op['insn'], rs1=rs1,
                          rs2=0 if op['b'] is None else op['b'], frm=op['frm'], fflags=flags[t] & 31)))
            reads = ([(rs1, 64)] if op['a'] is None else []) + op['reads']
            events += [('read', dict(seq=seq, pc=pc, address=a, bytes=n)) for a, n in reads]
            events.append(('end', dict(seq=seq, pc=pc, status=0, fflags=op['flags'],
                                      valid=op['valid'], tile=op['tile'], tokens=op['tokens'], tval=0)))
        entry('feature_terminal_marker')
    return bound, events


def as_trace(events):
    lines = []
    for tag, row in events:
        if tag == 'exec':
            lines.append('Trace 0: %s [0/%016x/0/0]' % (row['tb'], row['pc']))
        elif tag == 'trap':
            lines.append('riscv_cpu_do_interrupt: hart:0, async:0, cause:%016x, epc:0x%x, tval:0x%x, desc=test' %
                         (row['cause'], row['pc'], row['tval']))
        else:
            lines.append('akv_arch_' + tag + ' ' + ' '.join(k + '=' +
                         (hex(v) if k in c.HEX else str(v)) for k, v in row.items()))
    return '\n'.join(lines) + '\n'


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {kind: fixtures(kind) for kind in ('perf', 'functional')}
        cls.events = {kind: synthetic_events(value) for kind, value in cls.data.items()}

    def architecture(self, kind, events=None):
        _, _, f, fixture, _, groups, flags, _ = self.data[kind]
        bound, original = self.events[kind]
        return c.stage4_architecture(original if events is None else events, fixture, f, bound, groups, dict(fcsr=flags))

    def proof(self, kind):
        if kind == 'qbs':
            b = c.binding('qbs')
            return dict(state='NATIVE_ELF_ARCHITECTURE_CHECKED', kind=kind, elf_sha256=c.QBS_SHA,
                        work=c.qbs_architecture(self.qbs_events(b), b), rtl_timing=False,
                        rtl_protocol_checked=False, performance_acceptance=False,
                        qemu_image_checked=False, service_owner_checked=False)
        _, _, f, fixture, data, _, _, text = self.data[kind]
        numbers = f.numerical(text, fixture, data)
        numbers.pop('timing')
        return dict(state='NATIVE_ELF_ARCHITECTURE_CHECKED', kind=kind, elf_sha256=c.FIRMWARE[kind][2],
                    work=self.architecture(kind), numerical=numbers, rtl_timing=False,
                    rtl_protocol_checked=False, performance_acceptance=False,
                    qemu_image_checked=False, service_owner_checked=False,
                    original_numerical_checker_sha256=c.CHECK_SHA, original_fixture_sha256=c.FIXTURE_SHA,
                    target_libm_sha256=c.LIBM_SHA)

    def qbs_events(self, bound):
        points = {w: p for p, w in bound['custom'].items()}
        events = []
        for word, cause, tval in c.qbs_schedule():
            pc = points[word]
            events.append(('exec', dict(pc=pc, tb='0x1')))
            if cause:
                events.append(('trap', dict(pc=pc, cause=cause, tval=tval)))
        return events

    def test_real_frozen_firmware_and_instruction_bindings(self):
        for kind, calls, outputs in (('perf', 4, 1024), ('functional', 18, 2816)):
            _, report, _, fixture, _, _, _, _ = self.data[kind]
            b = c.binding(kind, report)
            self.assertEqual(len(fixture['trials']), calls)
            self.assertEqual(self.proof(kind)['numerical']['output_values'], outputs)
            self.assertIn(0x0605705b, b['custom'].values())
            self.assertIn(0x0485705b, b['custom'].values())
            self.assertIn('rotation_body', b['entries'])
        self.assertEqual([x['requested'] for x in self.data['perf'][3]['trials']], [0, 1, 1, 0])

    def test_schedule_matches_frozen_work_signatures_and_exact_external_bytes(self):
        for kind, bundle in self.data.items():
            _, _, f, fixture, _, groups, _, _ = bundle
            ops = [op for t in range(len(fixture['trials'])) for op in c.schedule(fixture, t, groups, f)]
            signatures = [op['insn'] for op in ops if op['insn'] not in (0x00b5605b, 0x02a0605b, 0x0000505b)]
            self.assertEqual(signatures, fixture['work']['signatures'])
            self.assertEqual(sum(n for op in ops for _, n in op['reads']),
                sum(x['q_external_bytes'] + x['kv_external_bytes'] for x in fixture['work']['legacy']))

    def test_synthetic_architecture_positive_both_fixtures(self):
        for kind in self.data:
            proof = self.proof(kind)
            r.checked_gate(proof, kind)
            self.assertGreater(proof['work']['resident_commands'], 0)

    def test_original_numerical_checker_positive_unchanged(self):
        for kind, bundle in self.data.items():
            _, _, f, fixture, data, _, _, text = bundle
            result = f.numerical(text, fixture, data)
            self.assertTrue(result['bitexact'])
            self.assertEqual(c.sha(bundle[0] / 'inputs/check.py'), c.CHECK_SHA)

    def test_original_numerical_output_flags_guard_and_completion_mutations(self):
        _, _, f, fixture, data, _, _, text = self.data['perf']
        mutations = (text.replace('bits=', 'bits=1', 1), text.replace('vcsr=5', 'vcsr=4', 1),
                     text.replace('query_hash=', 'query_hash=1', 1), text.replace('fcsr=', 'fcsr=9', 1),
                     text.replace('FEATURE_DONE', 'FEATURE_UNKNOWN'))
        for value in mutations:
            with self.assertRaises(ValueError):
                f.numerical(value, fixture, data)

    def test_control_frm_flags_and_snapshot_mutations(self):
        for tag, key, delta in (('begin', 'rs1', 1), ('begin', 'frm', 1), ('begin', 'fflags', 32),
                                ('read', 'address', 2), ('read', 'bytes', 2), ('end', 'valid', 1),
                                ('end', 'fflags', 1), ('end', 'tokens', 1)):
            ev = copy.deepcopy(self.events['functional'][1])
            next(row for name, row in ev if name == tag)[key] ^= delta
            with self.subTest(tag=tag, key=key), self.assertRaises(ValueError):
                self.architecture('functional', ev)

    def test_missing_extra_native_events_and_final_barrier(self):
        original = self.events['perf'][1]
        for ev in (original[:-1], original + original[-1:], original[1:],
                   original[:20] + original[21:]):
            with self.assertRaises(ValueError):
                self.architecture('perf', ev)

    def test_info_and_actual_entry_mutations(self):
        for mutate in (lambda e: next(row for tag, row in e if tag == 'info').update(result=0),
                       lambda e: next(row for tag, row in e if tag == 'info').update(index=4),
                       lambda e: e.insert(1, ('exec', dict(pc=self.events['perf'][0]['entries']['rotation_body']['pc'], tb='0x1')))):
            ev = copy.deepcopy(self.events['perf'][1])
            mutate(ev)
            with self.assertRaises(ValueError):
                self.architecture('perf', ev)

    def test_trace_parser_and_exact_cancelled_tb_pair(self):
        bound, events = self.events['perf']
        self.assertEqual(c.trace_events(as_trace(events), set(bound['points'])), (events, 0))
        pc = bound['points'][0]
        text = as_trace([('exec', dict(pc=pc, tb='0x1'))]) + 'Stopped execution of TB chain before 0x1 [%x]\n' % pc
        self.assertEqual(c.trace_events(text, set(bound['points'])), ([], 1))
        with self.assertRaises(ValueError):
            c.trace_events(text.replace('before 0x1', 'before 0x2'), set(bound['points']))

    def test_unknown_duplicate_trace_fields_cpu_and_interrupt_rejected(self):
        bound, events = self.events['perf']
        text = as_trace(events)
        for bad in (text.replace('Trace 0:', 'Trace 1:', 1), text + 'akv_arch_unknown x=1\n',
                    text.replace('index=3', 'index=3 index=3', 1), text + 'assertion failed\n'):
            with self.assertRaises(ValueError):
                c.trace_events(bad, set(bound['points']))

    def test_native_qbs_exact_sequence_and_fault_counts(self):
        b = c.binding('qbs')
        result = c.qbs_architecture(self.qbs_events(b), b)
        self.assertEqual(result['native_instructions'], 190)
        self.assertEqual(result['traps'], {'5': 20, '2': 49})
        r.checked_gate(self.proof('qbs'), 'qbs')

    def test_native_qbs_missing_wrong_fault_and_extra_instruction_rejected(self):
        b = c.binding('qbs')
        original = self.qbs_events(b)
        for mutation in ('cause', 'tval', 'pc', 'missing', 'extra'):
            events = copy.deepcopy(original)
            if mutation == 'missing':
                events.pop()
            elif mutation == 'extra':
                events += events[-1:]
            else:
                next(row for tag, row in events if tag == 'trap')[mutation] ^= 1
            with self.assertRaises(ValueError):
                c.qbs_architecture(events, b)

    def recipe(self, out):
        g = r.shared()
        qemu = dict(build=str(r.BUILD), build_sha256=r.BUILD_SHA, executable=str(r.BUILD / 'qemu-system-riscv64'),
                    executable_sha256=r.BINARY_SHA)
        reports = {k: b[1] for k, b in self.data.items()}
        return r.selection(out, qemu, reports, g, '/usr/bin/python3.11')

    def test_exact_native_trace_recipes_and_unchanged_elfs(self):
        s = self.recipe(r.OUT / 'stage5_qemu_execution_host_recipe')
        self.assertEqual([x['kind'] for x in s['commands']], list(r.KINDS))
        for job in s['commands']:
            self.assertEqual(job['guest'][0], str(r.BUILD / 'qemu-system-riscv64'))
            self.assertIn('tcg,one-insn-per-tb=on', job['guest'])
            self.assertIn('exec,nochain,int', job['guest'])
            self.assertEqual(c.sha(job['elf']), job['elf_sha256'])
        self.assertIn('virt', s['commands'][0]['guest'])
        self.assertIn('virt,x-ara-stage4=on', s['commands'][1]['guest'])

    def test_wrong_build_identity_rejected(self):
        s = self.recipe(r.OUT / 'stage5_qemu_execution_host_recipe')
        for key in ('build', 'build_sha256', 'executable_sha256'):
            q = copy.deepcopy(s['qemu'])
            q[key] = 'wrong'
            with self.assertRaises(ValueError):
                r.selection(r.OUT / 'stage5_qemu_execution_host_recipe', q, {}, r.shared())

    def command_fixture(self, mutation=None):
        g = r.shared()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            s = self.recipe(out)
            rows = []
            time = 100
            ownership = dict(unit=r.unit(out), owner_pid=12, main_pid=12, invocation_id='1' * 32,
                             cgroup='0::/user.slice/' + r.unit(out))
            for job in s['commands']:
                work = out / 'work' / job['kind']
                work.mkdir(parents=True)
                (work / 'guest.log').write_text('synthetic host fixture, not a guest\n')
                (work / 'trace.log').write_text('synthetic host fixture, not a guest\n')
                proof = self.proof(job['kind'])
                proof.update(log_sha256=c.sha(work / 'guest.log'), trace_sha256=c.sha(work / 'trace.log'))
                g.save(work / 'checked.json', proof)
                row = dict(kind=job['kind'], state='PASS', returncode=0, checked=proof)
                for key, name, file, timeout in (('guest', 'guest', 'guest.log', r.GUEST_SECONDS),
                                                ('checker', 'checked', 'checked.json', r.CHECK_SECONDS)):
                    record = dict(argv=job[key], cwd=str(work), timeout_seconds=timeout, pid=30,
                                  state='EXITED', returncode=0, started_ns=time, ended_ns=time + 1,
                                  log_sha256=c.sha(work / file))
                    time += 2
                    g.save(work / (name + '.command.json'), record)
                    row[key + '_command'] = record
                rows.append(row)
            if mutation:
                mutation(rows, s, ownership)
            r.validate_commands(rows, s, out, ownership)

    def test_actual_command_receipt_positive_host_fixture(self):
        self.command_fixture()

    def test_argv_cwd_timeout_owner_and_count_mutations(self):
        for change in (lambda a, s, o: a.pop(), lambda a, s, o: a[0].update(returncode=1),
                       lambda a, s, o: a[0]['guest_command'].update(cwd='/wrong'),
                       lambda a, s, o: a[0]['guest_command'].update(timeout_seconds=301),
                       lambda a, s, o: a[0]['guest_command']['argv'].append('-wrong'),
                       lambda a, s, o: o.update(main_pid=13),
                       lambda a, s, o: o.update(cgroup='0::/wrong')):
            with self.assertRaises(ValueError):
                self.command_fixture(change)

    def test_checker_partial_counts_and_false_timing_rejected(self):
        for kind in r.KINDS:
            for key in ('state', 'elf_sha256', 'rtl_timing'):
                p = self.proof(kind)
                p[key] = True if key == 'rtl_timing' else 'wrong'
                with self.assertRaises(ValueError):
                    r.checked_gate(p, kind)
        p = self.proof('perf')
        p['work']['legacy_commands'] -= 1
        with self.assertRaises(ValueError):
            r.checked_gate(p, 'perf')

    def test_four_gate_requires_actual_rom_and_same_image(self):
        three = dict(state='NATIVE_QEMU_THREE_GATES_CHECKED', qemu_build=str(r.BUILD),
                     qemu_build_receipt_sha256=r.BUILD_SHA, qemu_prepare='same', qemu_prepare_receipt_sha256='same',
                     executable='same', executable_sha256=r.BINARY_SHA)
        native = dict(three, state='DIRECTED_NATIVE_AKV_CHECKED',
                      rom_probe=dict(state='PASS', checked=dict(state='ROM_RAM_ONLY_FAULT_CHECKED')))
        r.combined(three, native)
        for mutate in (lambda x: x.pop('rom_probe'), lambda x: x.update(executable_sha256='wrong'),
                       lambda x: x.update(state='PREPARED_NOT_EXECUTED'),
                       lambda x: x['rom_probe'].update(state='FAIL')):
            wrong = copy.deepcopy(native)
            mutate(wrong)
            with self.assertRaises(ValueError):
                r.combined(three, wrong)

    def test_direct_service_limits_environment_and_frozen_worker(self):
        out = r.OUT / 'stage5_qemu_execution_host_recipe'
        s = self.recipe(out)
        args = r.service_argv(out, s, 'a' * 64)
        self.assertIn('--property=Type=exec', args)
        self.assertIn('--property=MemoryMax=8G', args)
        self.assertIn('--property=RuntimeMaxSec=3000', args)
        self.assertIn(str(out / 'inputs/run.py'), args)
        self.assertEqual(s['environment']['PYTHONDONTWRITEBYTECODE'], '1')

    def test_shared_final_reader_and_validator_closure(self):
        g = r.shared()
        self.assertEqual(c.sha(g.__file__), r.GATE_SHA)
        v = g.validator()
        self.assertEqual(len(v.OWN), 18)
        self.assertIn('build_v9.py', v.OWN)
        self.assertTrue(any(name.startswith('rom_probe/') for name in g.layout(v)))


def host(output):
    output = Path(output).absolute()
    r.require(output.parent == r.OUT and output.name.startswith('stage5_qemu_execution_host_') and
              not output.exists(), 'Fresh owned host output required')
    output.mkdir()
    pins = {str(r.HERE / n): c.sha(r.HERE / n) for n in r.OWN}
    report = dict(state='FAIL', synthetic_host_only=True, guest_executed=False, pins=pins)
    def expired(sig, frame):
        raise TimeoutError('180-second host bound')
    signal.signal(signal.SIGALRM, expired)
    signal.alarm(180)
    try:
        with (output / 'host.log').open('x') as log:
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(ExecutionTests))
        report.update(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors))
        r.require(result.wasSuccessful(), 'Execution host tests failed')
        r.require(pins == {str(r.HERE / n): c.sha(r.HERE / n) for n in r.OWN}, 'Host source changed')
        report['state'] = 'EXECUTION_HOST_PASS_NOT_EXECUTED'
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        signal.alarm(0)
        report['log_sha256'] = c.sha(output / 'host.log')
        with (output / 'result.json').open('x') as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    if '--output' in sys.argv:
        parser = argparse.ArgumentParser()
        parser.add_argument('--output', required=True)
        host(parser.parse_args().output)
    else:
        unittest.main()
