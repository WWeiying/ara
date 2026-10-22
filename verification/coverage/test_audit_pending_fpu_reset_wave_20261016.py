"""Sidecar-only tests; synthetic VCDs and the original strict parser, no EDA."""
import copy
import inspect
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import audit_pending_fpu_reset_wave_20261016 as sidecar
import audit_gap115_axi_v2 as parser
import qualify_external_reset_fixture as shared
import run_vmfpu_ured_reset763 as ured


def clock_samples(release=50):
    return [(time, {'ara_tb.clk': int(time % 10 == 5),
                    'ara_tb.rst_n': int(not 10 <= time < release)})
            for time in range(0, 66, 5)]


def write_vcd(path, samples, extra=None):
    widths = {'ara_tb.clk': 1, 'ara_tb.rst_n': 1, **(extra or {})}
    codes = {name: 'c' + str(i) for i, name in enumerate(widths)}
    text = ['$timescale 100fs $end', '$scope module ara_tb $end']
    for name, width in widths.items():
        text.append(f'$var wire {width} {codes[name]} \\{name[7:]} $end')
    text += ['$upscope $end', '$enddefinitions $end']
    for time, values in samples:
        text.append('#' + str(time))
        for name, value in values.items():
            if widths[name] == 1:
                text.append(str(value) + codes[name])
            else:
                bits = value if isinstance(value, str) else format(value, 'b')
                text.append('b' + bits + ' ' + codes[name])
    path.write_text('\n'.join(text) + '\n')


class ResetWaveTests(unittest.TestCase):
    def test_four_complete_stable_clocks(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wave.vcd'
            write_vcd(path, clock_samples())
            result = sidecar.four_clocks(path, parser)
            self.assertEqual(result['resets_100fs'], [10, 50])
            self.assertEqual(result['low_rising_edges'], 4)
            self.assertEqual(result['low_falling_edges'], 4)

    def test_hold_duration_glitch_unknown_duplicate_and_clock_mutations(self):
        fixtures = [clock_samples(40), clock_samples(60)]
        for value in ('1', 'x'):
            rows = clock_samples()
            rows.insert(6, (27, {'ara_tb.rst_n': value}))
            rows.insert(7, (28, {'ara_tb.rst_n': 0}))
            fixtures.append(rows)
        rows = clock_samples()
        rows += [(70, {'ara_tb.clk': 0, 'ara_tb.rst_n': 0})]
        fixtures.append(rows)
        rows = clock_samples()
        rows[6] = (30, {'ara_tb.clk': 1, 'ara_tb.rst_n': 0})
        fixtures.append(rows)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wave.vcd'
            for i, rows in enumerate(fixtures):
                write_vcd(path, rows)
                with self.subTest(fixture=i), self.assertRaises(ValueError):
                    sidecar.four_clocks(path, parser)

    def test_missing_waveform_declaration_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wave.vcd'
            write_vcd(path, clock_samples())
            path.write_text(path.read_text().replace('\\rst_n', '\\not_the_reset'))
            with self.assertRaisesRegex(ValueError, 'named waveform field'):
                sidecar.four_clocks(path, parser)

    def test_independent_epoch_boundary(self):
        log = '@ 21: anything [CVXIF/RESET] epoch=2'
        self.assertEqual(sidecar.reset_epoch(log, [10, 50]), 21)
        for bad in ('', log + '\n' + log, log.replace('21:', '10:'), log.replace('21:', '51:')):
            with self.subTest(log=bad), self.assertRaises(ValueError):
                sidecar.reset_epoch(bad, [10, 50])

    def test_ured_width_only_changes_original_declaration(self):
        with tempfile.TemporaryDirectory() as directory:
            function = sidecar.ured_wave(shared, ured.expected_word, Path(directory))
            actual = (Path(directory) / 'ured-wave-original-width3.py').read_text()
            expected = inspect.getsource(shared.wave).replace("'stage': 4", "'stage': 3")
            self.assertEqual(actual, expected)
            self.assertIs(function.__globals__['gold'].expected_word, ured.expected_word)
            self.assertIsNot(shared.wave.__globals__['gold'].expected_word, ured.expected_word)

    def test_ured_all_four_lanes_and_positive_owners(self):
        states = ured.states()
        counts = [s.rsplit('.', 1)[0] + '.vinsn_queue_q.issue_cnt' for s in states]
        extra = {name: 3 for name in states + counts}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wave.vcd'
            def wave(overrides):
                rows = clock_samples()
                rows[0][1].update(dict.fromkeys(extra, 1))
                rows[0][1].update(overrides)
                write_vcd(path, rows, extra)
            wave({})
            self.assertEqual(sidecar.ured_window(path, ured)['time_100fs'], 10)
            for name, value in [(states[3], 0), (counts[2], 0), (states[0], 'xxx')]:
                wave({name: value})
                with self.subTest(signal=name), self.assertRaises(ValueError):
                    sidecar.ured_window(path, ured)

    def test_private_function_preserves_original_code_and_globals(self):
        original = shared.wave
        before = dict(original.__globals__)
        clone = sidecar.private(original, gold=SimpleNamespace(expected_word=lambda i: 0))
        self.assertIs(clone.__code__, original.__code__)
        self.assertIs(original.__globals__['gold'], before['gold'])
        self.assertIsNot(clone.__globals__['gold'], before['gold'])

    def test_converter_is_pinned_splitpacked_and_output_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, out = root / 'work', root / 'audit'
            work.mkdir(); out.mkdir()
            (work / 'external-reset.vpd').write_bytes(b'captured-wave')
            calls = []
            def bind(path, expected=None):
                calls.append((Path(path), expected))
                return Path(path)
            a = SimpleNamespace(work=work, bind=bind)
            def convert(command, **kwargs):
                self.assertEqual(kwargs['cwd'], out)
                self.assertEqual(command[0], str(sidecar.CONVERTER))
                self.assertEqual(command[1], '+splitpacked')
                Path(command[-1]).write_text('converted fixture')
                return SimpleNamespace(returncode=0)
            with patch.object(sidecar.subprocess, 'run', side_effect=convert):
                path, receipt = sidecar.convert(a, out, 'external-reset.vpd')
            self.assertEqual(path.parent, out)
            self.assertIn((sidecar.CONVERTER, sidecar.CONVERTER_SHA), calls)
            self.assertFalse(receipt['simulation_started'])

    def test_selection_requires_actual_bound_copy_and_all_runtime_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, scripts = root / 'work', root / 'ucli'
            work.mkdir(); scripts.mkdir()
            content = 'set ext_value 4\n'
            for p in (work / 'external-reset-selection.tcl', scripts / 'selection.tcl'):
                p.write_text(content)
            digest = sidecar.sha(scripts / 'selection.tcl')
            def bind(path, expected=None):
                self.assertEqual(sidecar.sha(path), expected)
                return Path(path)
            a = SimpleNamespace(case=root, work=work, bind=bind,
                                old=dict(selection=dict(ext_target='controller', ext_value=4),
                                         selection_sha256=digest))
            markers = ['EXT_RESET_READY controller 4', 'EXT_RESET_TARGET controller 4',
                       'EXT_RESET_ASSERT', *[f'EXT_RESET_LOW_EDGE {i}' for i in range(1, 5)],
                       'EXT_RESET_RELEASE', 'EXT_RESET_DONE']
            logs = {'console.log': '\n'.join(markers), 'run.vcs.log': '\n'.join(markers)}
            sidecar.selection(a, logs)
            bad = copy.deepcopy(logs)
            bad['run.vcs.log'] = bad['run.vcs.log'].replace('EXT_RESET_LOW_EDGE 3\n', '')
            with self.assertRaises(ValueError):
                sidecar.selection(a, bad)


if __name__ == '__main__':
    unittest.main()
