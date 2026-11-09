"""Offline synthetic tests only; no EDA and no modification of run evidence."""
from collections import Counter
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import attribute as a


def elf(functions=None):
    functions = functions or [(a.QK, 0x1000, 32), *[(n, 0x1040+64*i, 32) for i, n in enumerate(a.PV)]]
    raw = bytearray(1536)
    names, symbols = bytearray(b'\0'), [bytes(24)]
    for name, address, size in functions:
        offset = len(names)
        names.extend(name.encode()+b'\0')
        symbols.append(struct.pack('<IBBHQQ', offset, 18, 0, 1, address, size))
    raw[:64] = struct.pack('<16sHHIQQQIHHHHHH', b'\x7fELF\x02\x01\x01'+bytes(9),
        2, 243, 1, 0x1000, 0, 64, 4, 64, 56, 0, 64, 4, 0)
    sections = [bytes(64), struct.pack('<IIQQQQIIQQ', 0, 1, 6, 0x1000, 512, 512, 0, 0, 2, 0),
        struct.pack('<IIQQQQIIQQ', 0, 2, 0, 0, 1024, 24*len(symbols), 3, 1, 8, 24),
        struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, 1200, len(names), 0, 0, 1, 0)]
    raw[64:320] = b''.join(sections)
    raw[1024:1024+24*len(symbols)] = b''.join(symbols)
    raw[1200:1200+len(names)] = names
    return bytes(raw)


def retired(cycle, pc=0x2000, insn=0x13, value=0):
    return dict(cycle=str(cycle), event='retire', pc=f'{pc:016x}', insn=f'{insn:08x}', rd_wdata=f'{value:016x}')


class SymbolsAndRetirement(unittest.TestCase):
    def test_structural_symtab_size_not_next_symbol(self):
        ranges = a.elf_ranges(elf())
        self.assertEqual(ranges[a.PV[-1]], (0x10c0, 0x10e0))
        self.assertEqual(set(ranges), {a.QK, *a.PV})

    def test_invalid_missing_duplicate_and_overlapping_symbols(self):
        base = [(a.QK, 0x1000, 32), *[(n, 0x1040+64*i, 32) for i, n in enumerate(a.PV)]]
        for functions in (base[:-1], base[:-1]+[(a.PV[-1], 0x10c0, 0)],
                          base[:-1]+[(a.PV[0], 0x10c0, 32)], base[:-1]+[(a.PV[-1], 0x1080, 32)]):
            with self.subTest(functions=functions), self.assertRaises(ValueError):
                a.elf_ranges(elf(functions))
        for raw in (b'', elf()[:100], elf()[:1205]):
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                a.elf_ranges(raw)

    def test_prepare_and_body_are_one_pv_phase(self):
        ranges = a.elf_ranges(elf())
        rows = [retired(11, insn=0xc0002573, value=10), retired(20, 0x1000), retired(25),
                retired(30, 0x1040), retired(35, 0x1080), retired(40, 0x1044),
                retired(42, 0x10c0), retired(50, 0x1048), retired(55),
                retired(121, insn=0xc0002573, value=120)]
        spans, markers = a.cpu_spans(rows, ranges, {10, 120})
        self.assertEqual([x['helper'] for x in spans], ['qk', 'pv'])
        self.assertEqual((spans[1]['begin'], spans[1]['end'], spans[1]['retired']), (30, 55, 5))
        self.assertEqual(markers, {10: 11, 120: 121})

    def test_arm_zero_tailcall_body_is_not_truncated(self):
        rows = [retired(11, insn=0xc0002573, value=10), retired(30, 0x1040),
                retired(35, 0x10c0), retired(50, 0x10c4), retired(55),
                retired(121, insn=0xc0002573, value=120)]
        spans, _ = a.cpu_spans(rows, a.elf_ranges(elf()), {10, 120})
        self.assertEqual((len(spans), spans[0]['begin'], spans[0]['end']), (1, 30, 55))

    def test_unique_clock_offset_and_duplicate_markers(self):
        for rows in ([retired(11, insn=0xc0002573, value=10), retired(122, insn=0xc0002573, value=120)],
                     [retired(11, insn=0xc0002573, value=10), retired(12, insn=0xc0002573, value=10),
                      retired(121, insn=0xc0002573, value=120)]):
            with self.assertRaises(ValueError):
                a.cpu_spans(rows, a.elf_ranges(elf()), {10, 120})


def example():
    trials, spans, matched = [], [], {}
    resident = dict(pv_terminals=[], actual_vector_writes=[])
    for trial, arm in enumerate((0, 1, 1, 0)):
        begin = 1000+10000*trial
        end = begin+(5000 if arm else 7000)
        row = dict(trial=trial, arm=arm, begin=begin, returned=end-100, end=end, fcsr=3)
        trials.append(row)
        matched.update({row[k]: row[k]+17 for k in ('begin', 'returned', 'end')})
        for tile, tokens in enumerate((64, 64, 9)):
            start = begin+17+1500*tile+10
            spans.append(dict(helper='qk', begin=start, end=start+100, retired=2, opcodes=Counter()))
            pv = dict(helper='pv', begin=start+100, end=start+1400, retired=10,
                      opcodes=Counter({'0205345b': tokens, a.FMA_OPCODES[0]: 2*tokens}))
            spans.append(pv)
            if not arm:
                continue
            cycles = (1148, 1148, 213)[tile]
            resident['pv_terminals'].append(dict(tokens=tokens, cycles=cycles, flags=1,
                lanes=[dict(lane=i, issued=16*tokens, returned=16*tokens) for i in range(4)]))
            alloc = pv['begin']+1
            done = pv['end']+25 if tile == 2 else alloc+cycles
            resident['actual_vector_writes'].append(dict(allocation_cycle=alloc, completion_cycle=done))
    return trials, spans, matched, resident


class AttributionBookkeeping(unittest.TestCase):
    def test_all_calls_have_three_qk_and_three_union_pv_spans(self):
        report = a.summarize(*example())
        self.assertEqual([x['full_call_cycles'] for x in report['trials']], [7000, 5000, 5000, 7000])
        self.assertTrue(all(len(x['helpers']) == 6 and x['pv_scalar_fmas'] == 35072 for x in report['trials']))
        self.assertEqual(report['complete_call_speedup'], 1.4)
        delta = report['baseline_minus_candidate_retirement_interval_delta']
        self.assertEqual(delta['full_call'], delta['qk']+delta['pv']+delta['other'])
        self.assertTrue(report['noncausal_difference_bookkeeping'])

    def test_handshakes_service_and_cpu_intervals_are_separate(self):
        report = a.summarize(*example())
        trial = report['trials'][1]
        tile = trial['pv_tiles'][0]
        self.assertEqual(tile['fma_input_handshakes_by_lane'], [1024]*4)
        self.assertAlmostEqual(tile['fma_input_acceptance_per_service_lane_cycle'], 1024/1148)
        self.assertEqual(trial['pv_tiles'][2]['completion_after_cpu_helper_exit_cycles'], 25)
        self.assertIsNone(report['trials'][0]['pv_tiles'][0]['fma_handshake_utilization'])
        self.assertFalse(report['pipeline_occupancy_measured'])
        self.assertNotEqual(trial['cpu_retirement_interval_cycles']['pv'],
                            sum(x['controller_service_cycles_inclusive'] for x in trial['pv_tiles']))

    def test_missing_helper_wrong_work_csr_or_ownership_rejected(self):
        for kind in ('missing', 'work', 'csr', 'ownership', 'handshakes'):
            trials, spans, matched, resident = copy.deepcopy(example())
            if kind == 'missing':
                spans.pop(0)
            elif kind == 'work':
                spans[1]['opcodes'][a.FMA_OPCODES[0]] -= 1
            elif kind == 'csr':
                trials[0]['fcsr'] = 1
            elif kind == 'ownership':
                resident['actual_vector_writes'][0]['allocation_cycle'] = 0
            else:
                resident['pv_terminals'][0]['cycles'] = 100
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                a.summarize(trials, spans, matched, resident)


class ReadOnlyAdmission(unittest.TestCase):
    def test_running_evidence_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory/'result.json').write_text(json.dumps(dict(state='RUNNING')))
            with patch.object(a.r, 'output_path', return_value=directory), \
                 patch.object(a.r, 'verify_prepared', side_effect=AssertionError('Must reject first')):
                with self.assertRaisesRegex(ValueError, 'accepted ABBA'):
                    a.accepted_evidence(directory)

    def test_artifact_drift_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root/'run'
            directory.mkdir()
            (directory/'source-pins.json').write_text('{}')
            simv = root/'simv'
            simv.write_text('image')
            selected = dict(soc_build='soc03', build='abba01', smoke_admission={})
            soc = dict(configuration={}, simv=str(simv))
            software = dict(elf_sha256=a.r.ABBA_ELF_SHA)
            m = dict(state='PASS', kind='abba', numerical_checked=True, independent_protocol_checked=True,
                post_pins_match=True, post_image_match=True, **selected, configuration={},
                software_sha256=a.r.ABBA_ELF_SHA, image_sha256=a.sha(simv),
                source_pins_sha256=a.sha(directory/'source-pins.json'), artifacts={})
            (directory/'result.json').write_text(json.dumps(m))
            with patch.object(a.r, 'output_path', return_value=directory), \
                 patch.object(a.r, 'verify_prepared', return_value=(selected, {}, soc, software)), \
                 patch.object(a.r, 'check_numerical', side_effect=AssertionError('Unverified evidence')):
                with self.assertRaisesRegex(ValueError, 'inventory drift'):
                    a.accepted_evidence(directory)

    def test_no_terminal_pass_creates_no_output_or_evidence_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory, out = root/'evidence', root/'resident_pv_soc_attribute_test'
            directory.mkdir()
            source = directory/'original'
            source.write_text('unchanged')
            with patch.object(a.r, 'OUT', root), patch.object(a.r, 'output_path', return_value=directory), \
                 patch.object(a.sys, 'argv', ['attribute.py', '--run', str(directory), '--output', str(out)]):
                with self.assertRaisesRegex(ValueError, 'terminal PASS not available'):
                    a.main()
            self.assertFalse(out.exists())
            self.assertEqual(list(directory.iterdir()), [source])
            self.assertEqual(source.read_text(), 'unchanged')


if __name__ == '__main__':
    unittest.main()
