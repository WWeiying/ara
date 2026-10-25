"""Synthetic protocol mutations only; no numerical RTL acceptance is implied."""
import copy
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from verification.akv.quantized_kv.tail_split.scope import HERE, PARENT, render, command_count, suite
sys.path.insert(0, str(PARENT))
import test_tail_attention_check as old_fixture
from verification.akv.quantized_kv.tail_split.check import check_log
from verification.akv.quantized_kv.tail_split.combine import validate_matrix, checked_run, checked_combined


def fixture(kind, visible):
    text, gold, rtl = old_fixture.TailAcceptance().fixture(kind)
    lines = [text.splitlines()[0].replace('prefixes=5,33', f'prefixes={visible}')]
    enabled = False
    seq = 0
    for line in text.splitlines()[1:]:
        if line.startswith('QUANT_TAIL_BEGIN '):
            enabled = line.startswith(f'QUANT_TAIL_BEGIN visible={visible} ')
        if line.startswith('QUANT_TAIL_SUITE'):
            break
        if not enabled:
            continue
        if line.startswith('[QBS_PERF]'):
            seq += 1
            line = re.sub(r'\bseq=[0-9]+', f'seq={seq}', line)
        elif line.startswith('QUANT_TAIL_QK '):
            line = re.sub(r'\bseq=[0-9]+', f'seq={seq}', line)
        lines.append(line)
    lines.extend((suite(visible), old_fixture.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0'))
    return '\n'.join(lines), gold, rtl


def check(text, kind, visible, gold, rtl):
    return check_log(text, kind, gold, rtl, bytes(512 * (72 if kind else 136)),
                     lambda _kind, _key, _query: (0x3f800000, 0), visible)


class SplitTests(unittest.TestCase):
    def test_clean_process_entrypoints(self):
        for name in ('build.py', 'run.py', 'combine.py'):
            result = subprocess.run([sys.executable, '-B', str(HERE / name), '--help'],
                                    cwd='/', capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--output', result.stdout)

    def test_all_four_scopes(self):
        for kind in (0, 1):
            for visible in (5, 33):
                text, gold, rtl = fixture(kind, visible)
                result = check(text, kind, visible, gold, rtl)
                self.assertEqual(result['commands'], command_count(visible))
                self.assertEqual(len(result['trials']), 3)
                expected = [5] * 4 if visible == 5 else [32, 32, 1, 1] * 2
                self.assertEqual([r['n'] for r in result['hardware_records']], expected)

    def test_wrong_work_flags_outputs(self):
        for kind in (0, 1):
            for visible in (5, 33):
                text, gold, rtl = fixture(kind, visible)
                work = next(line for line in text.splitlines() if line.startswith('[QBS_PERF]'))
                mutations = (
                    text.replace('heads=6', 'heads=2', 1),
                    text.replace('workspace=13120', 'workspace=8192', 1),
                    text.replace('groups=1', 'groups=0', 1),
                    text.replace('copied=' + str(visible * (72 if kind else 136)), 'copied=0', 1),
                    text.replace('panels=1', 'panels=9', 1) if visible == 5 else text.replace('panels=2', 'panels=1', 1),
                    text.replace('fcsr=1', 'fcsr=3', 1),
                    text.replace('vcsr=5', 'vcsr=0', 1),
                    text.replace('errors=0', 'errors=1', 1),
                    text.replace('hex=3f800000', 'hex=7fc00000', 1),
                    text.replace(work + '\n', '', 1),
                    text.replace('scores=3f800000', 'scores=40000000', 1),
                    text.replace('activation=00', 'activation=01', 1),
                    text.replace('stride=32', 'stride=64', 1),
                )
                for bad in mutations:
                    with self.subTest(kind=kind, visible=visible, mutation=mutations.index(bad)):
                        with self.assertRaises(ValueError):
                            check(bad, kind, visible, gold, rtl)

    def test_strict_protocol(self):
        text, gold, rtl = fixture(0, 33)
        qk = next(line for line in text.splitlines() if line.startswith('QUANT_TAIL_QK '))
        for bad in (text + '\n' + suite(33), text.replace(suite(33), suite(33) + '_BOGUS'),
                    text + '\nQUANT_TAIL_UNKNOWN anything', text + '\nQBS_PERF_BOGUS',
                    text + '\nQUANT_TAIL_RESULT bad=0', text + '\nFAILED',
                    text.replace(qk + '\n', ''), text.replace(qk, qk + '\n' + qk),
                    text.replace(old_fixture.TERMINAL, ''), text.replace('UVM_ERROR : 0', 'UVM_ERROR : 1'),
                    text.replace('prefixes=33 native', 'prefixes=5,33 native'),
                    text.replace('trial=2 native=1', 'trial=1 native=1'),
                    text.replace(suite(33), old_fixture.SUITE)):
            with self.assertRaises(ValueError):
                check(bad, 0, 33, gold, rtl)

    def test_native_repeat_bits_even_within_tolerance(self):
        text, gold, rtl = fixture(0, 5)
        needle = 'QUANT_TAIL_RESULT visible=5 trial=2 '
        line = next(line for line in text.splitlines() if line.startswith(needle))
        bad = text.replace(line, line.replace('hex=3f800000', 'hex=3f800001'))
        with self.assertRaises(ValueError):
            check(bad, 0, 5, gold, rtl)

    def test_prefix33_uses_own_independent_gold(self):
        text, gold, rtl = fixture(0, 33)
        gold[33] = bytes(6144)
        with self.assertRaises(ValueError):
            check(text, 0, 33, gold, rtl)

    def test_source_exact_five_changes(self):
        source = (PARENT / 'attention_tail_main.c').read_text()
        for visible in (5, 33):
            result = render(source, visible)
            before, after = source.splitlines(), result.splitlines()
            self.assertEqual(len(before), len(after))
            self.assertEqual(sum(a != b for a, b in zip(before, after)), 5)
            self.assertIn('visible_tokens == 33 ? attention_tail_gold_33 : attention_tail_gold_5', result)
            self.assertIn('trial < 3', result)
            self.assertIn('if (trial == 2) errors += bits(actual) != bits(previous_native', result)
            self.assertIn('fabsf(actual - expected) > 0.004f + 0.002f * fabsf(expected)', result)
            self.assertIn('for (unsigned head = 0; head < m; ++head)', result)
        with self.assertRaises(ValueError):
            render(source.replace('prefix < 2;', 'prefix < 3;'), 5)
        for wrong in (True, 0, 32, 34):
            with self.assertRaises(ValueError):
                render(source, wrong)

    def records(self):
        results = []
        for kind in (0, 1):
            for visible in (5, 33):
                text, gold, rtl = fixture(kind, visible)
                result = check(text, kind, visible, gold, rtl)
                result.update(state='PASS', kind='q4_0' if kind else 'q8_0', post_pins_match=True,
                              independent_protocol_checked=True, simulator_exit_code=0)
                results.append(result)
        return results

    def test_combined_all_scope(self):
        result = validate_matrix(self.records())
        self.assertEqual(result['commands'], 24)
        self.assertEqual(result['trials'], 12)
        self.assertIs(result['original_timeout_reclassified'], False)

    def test_combined_missing_failed_duplicate_wrong_query(self):
        records = self.records()
        mutations = [records[:3], records + [records[0]], [records[0]] * 4]
        for key, value in (('state', 'TIMEOUT'), ('commands', 12), ('prefixes', [5, 33]),
                           ('independent_protocol_checked', False), ('post_pins_match', False),
                           ('simulator_exit_code', 1)):
            altered = copy.deepcopy(records)
            altered[0][key] = value
            mutations.append(altered)
        altered = copy.deepcopy(records)
        altered[0]['query_hex']['0'] = '01' * 136
        mutations.append(altered)
        for bad in mutations:
            with self.assertRaises(ValueError):
                validate_matrix(bad)

    def test_timeout_never_reaudited_as_pass(self):
        with patch('verification.akv.quantized_kv.tail_split.combine.s.read_json',
                   return_value={'state': 'TIMEOUT', 'child_pid': None}):
            with self.assertRaises(ValueError):
                checked_run(HERE)
            with self.assertRaises(ValueError):
                checked_combined(HERE)


if __name__ == '__main__':
    unittest.main()
