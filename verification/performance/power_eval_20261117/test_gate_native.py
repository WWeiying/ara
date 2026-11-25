"""Native gate host-only contract fixtures. Never launches EDA or creates measurements."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('native_gate_owned', Path(__file__).with_name('gate_native.py'))
n = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(n)


def record(prefix, **values):
    return prefix + ' '.join(f'{k}={v}' for k, v in values.items()) + '\n'


def projection_fixture(compact=False):
    c = dict(backend='native', m=4 if compact else 1, n=64, k=2048, profile=1,
             activation_profile=1, k_blocks=8, activation_block_bytes=292)
    counts = dict(GUARD=640, Q8=c['m']*2336, PACK=c['m']*2336, OUT=c['m']*64)
    gold = {k: dict(count=v, expected_hash=123) for k, v in counts.items()}
    m = dict(case=c, mode='native', build_id='fixture_id', plan=dict(flags=1), flag_seeds=[0, 8],
             comparisons=gold, golden_checks=gold)
    if compact:
        text = record('OPQ_META ', id='fixture_id', m=4, n=64, k=2048, profile=1, rvv=0, trials=2)
        trial_tag, check_tag, done_tag = 'OPQ_TRIAL ', 'OPQC_CHECK ', 'OPQ_DONE '
        kinds = ('GUARD', 'Q8', 'PACK', 'OUT')
    else:
        text = record('OPR_META ', id='fixture_id', m=1, n=64, k=2048, profile=1, ap=1, kb=8, ab=292, rvv=0, trials=2, policy=1)
        trial_tag, check_tag, done_tag = 'OPR_TRIAL ', 'OPR_CHECK ', 'OPR_DONE '
        kinds = ('Q8', 'PACK', 'OUT', 'GUARD')
    for trial in range(2):
        values = dict(trial=trial, status=0, commands=2, quant_fcsr=1, fcsr=1 | (8 if trial else 0), vcsr=2, vstart=0,
                      **{f't{i}': trial*20+i+1 for i in range(6)})
        values.update(dict(context=0, eligible=0, coop=0) if compact else dict(quant_vcsr=2))
        text += record(trial_tag, **values)
        for kind in kinds:
            text += record(check_tag, trial=trial, kind=kind, count=counts[kind], mismatches=0, first=0xffffffff,
                           expected_hash=123, actual_hash=123, raw_differences=0, first_actual=0, first_expected=0)
        if compact:
            text += record('OPQC_POWER ', trial=trial, count=256, finite=256, mismatches=0,
                           first=0xffffffff, max_abs_bits=0, max_ratio_bits=0)
    text += record(done_tag, errors=0) + 'Core Test *** SUCCESS *** (tohost = 0)\n'
    return text, m


class NativeGateTests(unittest.TestCase):
    def test_m1_target_proof_does_not_require_or_invent_rtl_monitors(self):
        text, m = projection_fixture()
        r = n.projection_numeric(text, m)
        self.assertEqual(r['output_values_checked'], 128)
        self.assertEqual(r['state'], 'GATE_TARGET_NUMERIC_PASS_NO_RTL_MONITORS')
        self.assertFalse(r['gate_engine_monitor_checked'])
        self.assertFalse(r['gate_protocol_checked'])
        self.assertFalse(r['actual_command_issue_observed'])

    def test_m1_numeric_mutations(self):
        text, m = projection_fixture()
        for bad in [text.replace('fcsr=9', 'fcsr=1'), text.replace('quant_vcsr=2', 'quant_vcsr=0', 1),
                    text.replace('kind=GUARD count=640', 'kind=GUARD count=639', 1),
                    text.replace('mismatches=0', 'mismatches=1', 1), text.replace('OPR_DONE errors=0', 'OPR_DONE errors=1'),
                    text.replace('Core Test *** SUCCESS ***', 'Core Test *** FAILED ***'),
                    text + 'OPR_UNKNOWN x=1\n', text + '[QBS_PERF] synthetic=1\n']:
            with self.subTest(text=bad[-100:]), self.assertRaises(ValueError):
                n.projection_numeric(bad, m)

    def test_compact_m4_requires_its_own_records(self):
        text, m = projection_fixture(True)
        r = n.projection_numeric(text, m, True)
        self.assertEqual(r['output_values_checked'], 512)
        with self.assertRaises(ValueError):
            n.projection_numeric(text.replace('finite=256', 'finite=255', 1), m, True)
        with self.assertRaises(ValueError):
            n.projection_numeric(text.replace('max_abs_bits=0', 'max_abs_bits=1', 1), m, True)

    def test_no_raw_m4_or_baseline_substitution(self):
        _, m = projection_fixture()
        self.assertEqual(n.family(m), 'm1')
        m['case']['m'] = 4
        with self.assertRaises(ValueError):
            n.family(m)
        m['case']['m'], m['case']['backend'] = 1, 'rvv_x32'
        with self.assertRaises(ValueError):
            n.family(m)

    def test_bounded_copy_keeps_initial_state_and_omits_only_empty_trailer(self):
        with tempfile.TemporaryDirectory(prefix='native-gate-host-') as directory:
            root = Path(directory)
            raw, bounded = root/'raw.vcd', root/'bounded.vcd'
            prefix = b'$timescale 100 fs $end\n#100\n$dumpvars\n0!\n$end\n#200\n$dumpoff\nx!\n$end\n'
            raw.write_bytes(prefix + b'#900\n\n#1000\n')
            r = n.bounded_window(raw, bounded, 200)
            self.assertEqual(bounded.read_bytes(), prefix)
            self.assertTrue(r['initial_state_retained'])
            self.assertFalse(r['window_activity_bytes_changed'])
            self.assertGreater(r['omitted_empty_trailer_bytes'], 0)
            raw.write_bytes(prefix + b'#900\n1!\n')
            with self.assertRaises(ValueError):
                n.bounded_window(raw, root/'bad.vcd', 200)

    def test_roi_is_exact_trace_candidate_not_gate_acceptance(self):
        with tempfile.TemporaryDirectory(prefix='native-roi-host-') as directory:
            work = Path(directory)
            (work/'commit.csv').write_text('cycle,event,pc,insn,trap\n'
                '36519,retire,80003dd4,00b5045b,0\n39994,retire,80003dd4,00b5045b,0\n')
            roi = n.roi_candidate(work, n.M1)
            self.assertEqual((roi['first_cycle'], roi['last_cycle']), (36520, 39994))
            self.assertFalse(roi['gate_phase_verified'])
            self.assertFalse(roi['measured_power'])
            with self.assertRaises(ValueError):
                n.roi_candidate(work, 'some_other_m4_elf')

    def test_capture_control_has_no_mandatory_early_stop(self):
        p = n.b.GATE/'source/power_capture.sv'
        self.assertEqual(n.sha(p), n.CONTROL_SHA)
        self.assertIn('if ($test$plusargs("GATE_STOP_AFTER_CAPTURE")) $finish;', p.read_text())
        with self.assertRaises(ValueError):
            n.execute(Path('/not-a-worker'), None, None, False)

    def test_release_binds_prechecked_rtl_not_gate_image(self):
        with tempfile.TemporaryDirectory(prefix='native-release-host-') as directory:
            root = Path(directory)
            output = root/'power_native_release_20261117_fixture'
            def fixture_read(path):
                if path.name == 'gate-receipt.json':
                    return dict(rtl_image='/frozen/exact-rtl')
                return dict(cases=[dict(id=case, elf='/fixture/' + case) for case in (n.M1, n.AKV)])
            with patch.object(n, 'OUT', root), patch.object(n, 'read', side_effect=fixture_read), \
                 patch.object(n, 'ref', side_effect=lambda path: dict(path=str(path), sha256='0'*64)), \
                 patch.object(n.b, 'admit', return_value=dict(cases=[])):
                n.make_release(output)
            release = json.loads((output/'release.json').read_text())
            self.assertEqual(release['image'], '/frozen/exact-rtl')
            self.assertEqual([c['id'] for c in release['cases']], [n.M1, n.AKV])

    def test_one_run_requires_target_completion_and_keeps_capture_non_task_state(self):
        with tempfile.TemporaryDirectory(prefix='native-combined-host-') as directory:
            root = Path(directory)
            work = root/'run'
            work.mkdir()
            markers = ('GATE_ROI_BEGIN cycle=10 time=100000\n'
                       'GATE_CAPTURE_WINDOW_COMPLETE cycle=14 time=140000 task_pass=0\n')
            (work/'run.vcs.log').write_text(markers + 'Core Test *** SUCCESS *** (tohost = 0)\n')
            (work/'console.log').write_text(markers)
            raw = work/'window.vcd'
            header = ('$timescale 100 fs $end\n$scope module ara_tb $end\n$scope module dut $end\n'
                      '$scope module i_ara_soc $end\n$var wire 1 ! clk_i $end\n'
                      '$upscope $end\n$upscope $end\n$upscope $end\n$enddefinitions $end\n'
                      '#100000\n$dumpvars\n0!\n$end\n')
            raw.write_text(header + ''.join(f'#{100000+i*5000}\n{i%2}!\n' for i in range(1, 9)) +
                           '$dumpoff\nx!\n$end\n#900000\n')
            for name in ('plan.json', 'source-pins.json', 'image-pins.json', 'image-binding.json'):
                (root/name).write_text('{}')
            stat = raw.stat()
            run = dict(returncode=0, started_ns=min(stat.st_mtime_ns, stat.st_ctime_ns)-1000000,
                       finished_ns=max(stat.st_mtime_ns, stat.st_ctime_ns)+1000000)
            plan = dict(first_cycle=10, last_cycle=14, max_vcd_bytes=1000000, family='m1',
                        build='/fixture/build.json', case_id=n.M1, elf_map=dict(sha256='0'*64))
            with patch.object(n, 'numeric', return_value=dict(state='GATE_TARGET_NUMERIC_PASS_NO_RTL_MONITORS')):
                result = n.final_check(root, plan, dict(simv_sha256='1'*64), run)
            self.assertEqual(result['state'], 'CAPTURE_COMPLETE_NOT_TASK_PASS')
            self.assertFalse(result['task_pass'])
            self.assertEqual(result['target_completion']['state'], 'GATE_TARGET_COMPLETION_PASS')
            self.assertIn('numericproof', result['target_completion'])
            self.assertTrue(result['vcd_derivation']['initial_state_retained'])
            (work/'run.vcs.log').write_text(markers)
            with self.assertRaises(ValueError):
                n.final_check(root, plan, dict(simv_sha256='1'*64), run)


if __name__ == '__main__':
    unittest.main()
