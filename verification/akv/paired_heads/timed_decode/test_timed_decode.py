"""Synthetic host checks only; never build or run an EDA tool."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from timed_spec import HERE, SOURCE, render, inverse, s
from timed_check import check_log
import native_runtime_test as fixtures


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('timed_decode_builder_tests', HERE/'build.py')
runner = load('timed_decode_runner_tests', HERE/'run.py')


def timed_fixture():
    lines, busy, start = [], 0, 100
    for line in fixtures.fixture().splitlines():
        if line.startswith('NATIVE_PAIR_BEGIN '):
            busy = 0
        if line.startswith('[AKV_PERF] '):
            busy += s.numeric_fields(line[len('[AKV_PERF] '):], s.PERF_FIELDS)['busy_cycles']
        if line.startswith('NATIVE_PAIR_RESULT '):
            fields = dict(x.split('=') for x in line.split()[1:])
            cycles = busy+1000
            lines.append(f"NATIVE_PAIR_TIMING case={fields['case']} trial={fields['trial']} "
                         f"start={start} end={start+cycles} cycles={cycles}")
            start += cycles+100
        lines.append(line)
    return '\n'.join(lines)+'\n'


def entries():
    sources = [SOURCE, Path('/src/akv_v2_native_riscv.c')]+[Path(f'/src/{i}.c') for i in range(11)]
    flags = ['-fno-fast-math', '-ffp-contract=off', '-ffreestanding', '-fno-builtin']
    rows = [dict(argv=['/gnu/riscv64-unknown-elf-gcc', *flags, '-c', str(p), '-o', f'/old/{i}.o'])
            for i, p in enumerate(sources)]
    rows.append(dict(argv=['/gnu/riscv64-unknown-elf-gcc', '-nostdlib',
        *[f'/old/{i}.o' for i in range(13)], '-Wl,-Map=/old/link.map', '-o', '/old/old.elf']))
    return rows


class TimedDecodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = timed_fixture()

    def test_inverse_preserves_all_original_bytes(self):
        original = SOURCE.read_text()
        timed = render(original)
        self.assertEqual(inverse(timed), original)
        self.assertEqual(timed.count('rdcycle'), 2)
        self.assertEqual(timed.count('NATIVE_PAIR_TIMING'), 1)
        for changed in (original.replace('c < 4', 'c < 3'), original+'\n'):
            with self.assertRaises(ValueError):
                render(changed)
        with self.assertRaises(ValueError):
            inverse(timed.replace('trial < 3', 'trial < 2'))

    def test_complete_original_scope(self):
        result = check_log(self.text)
        self.assertEqual(len(result['trials']), 12)
        self.assertEqual(len(result['hardware_records']), 3680)
        self.assertEqual([r['hardware_totals']['records'] for r in result['trials']],
                         [197,84,197,774,373,774,137,137,137,386,98,386])
        for row, timing in zip(result['trials'], result['timings']):
            self.assertEqual(row['cycles'], timing['cycles'])
            self.assertGreaterEqual(row['cycles'], row['hardware_totals']['busy_cycles'])

    def test_missing_duplicate_unknown_timing(self):
        line = next(x for x in self.text.splitlines() if x.startswith('NATIVE_PAIR_TIMING'))
        for bad in (self.text.replace(line+'\n', '', 1), self.text+line+'\n',
                    self.text.replace(line, line+'\n'+line, 1),
                    self.text.replace(line, line+' extra=1', 1),
                    self.text.replace('NATIVE_PAIR_TIMING', 'NATIVE_PAIR_TIMING_BOGUS', 1),
                    self.text.replace(line, 'prefix '+line, 1)):
            with self.subTest(bad=bad[:40]), self.assertRaises(ValueError):
                check_log(bad)

    def test_wrong_timing_identity_order_and_boundary(self):
        line = next(x for x in self.text.splitlines() if x.startswith('NATIVE_PAIR_TIMING'))
        result = next(x for x in self.text.splitlines() if x.startswith('NATIVE_PAIR_RESULT'))
        for bad in (self.text.replace(line, line.replace('case=0', 'case=1'), 1),
                    self.text.replace(line, line.replace('trial=0', 'trial=1'), 1),
                    self.text.replace(line+'\n'+result, result+'\n'+line, 1),
                    self.text.replace(line, line+'\nboot noise', 1)):
            with self.assertRaises(ValueError):
                check_log(bad)

    def test_cycle_delta_busy_zero_wrap_and_overlap(self):
        line = next(x for x in self.text.splitlines() if x.startswith('NATIVE_PAIR_TIMING'))
        for start, end, cycles in ((100,100,0), (100,101,1), (100,3070,2971),
                                   (2**64-1,2**64,1), (500,100,1), (-1,3070,3071)):
            changed = f'NATIVE_PAIR_TIMING case=0 trial=0 start={start} end={end} cycles={cycles}'
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                check_log(self.text.replace(line, changed, 1))
        second = next(x for x in self.text.splitlines() if x.startswith('NATIVE_PAIR_TIMING case=0 trial=1'))
        with self.assertRaises(ValueError):
            check_log(self.text.replace(second,
                'NATIVE_PAIR_TIMING case=0 trial=1 start=1 end=1841 cycles=1840', 1))

    def test_original_failures_are_not_filtered(self):
        for old, new in (('errors=0', 'errors=1'), ('fcsr=3', 'fcsr=2'),
                         ('vcsr=5', 'vcsr=0'), ('NATIVE_PAIR_SUITE_PASS', 'NATIVE_PAIR_SUITE_PASS_BOGUS'),
                         ('success=1', 'success=0'), ('UVM_ERROR : 0', 'UVM_ERROR : 1')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_log(self.text.replace(old, new, 1))

    def test_object_recipe_only_changes_main_and_link_outputs(self):
        records = entries()
        compile_argv, link, reused = builder.recipe(records, Path('/new'))
        self.assertEqual(len(reused), 12)
        self.assertNotIn(Path('/old/0.o'), reused)
        self.assertEqual([x for x in link if x.endswith('.o')],
                         ['/new/main.o']+[str(p) for p in reused])
        self.assertEqual(compile_argv[compile_argv.index('-c')+1], '/new/main.c')
        bad = copy.deepcopy(records)
        bad[-1]['argv'].remove('/old/2.o')
        with self.assertRaises(ValueError):
            builder.recipe(bad, Path('/new'))
        bad = copy.deepcopy(records)
        bad[0]['argv'].remove('-ffp-contract=off')
        with self.assertRaises(ValueError):
            builder.recipe(bad, Path('/new'))

    def test_disassembly_order(self):
        text = ('00008000 <main>:\n'
                '8000: 0000 rdcycle s0\n8004: 0000 jal ra,9000 <akv_attention_execute_v2_native>\n'
                '8008: 0000 vmv.x.s a0,v12\n800c: 0000 fence rw,rw\n'
                '8010: 0000 rdcycle a1\n8014: 0000 frcsr a2\n8018: 0000 csrr a3,vcsr\n'
                '00009000 <akv_attention_execute_v2_native>:\n9000: 0000 ret\n')
        builder.check_disassembly(text)
        for old, new in (('fence rw,rw', 'nop'), ('vmv.x.s a0,v12', 'vmv.x.s a0,v0'),
                         ('rdcycle a1', 'nop'), ('frcsr a2', 'nop')):
            with self.assertRaises(ValueError):
                builder.check_disassembly(text.replace(old, new))

    def test_baseline_image_cannot_be_overridden(self):
        args = SimpleNamespace(variant='baseline', soc_build=None)
        with patch.object(s, 'checked_image', return_value=({'image':'sha'}, {})):
            self.assertEqual(runner.select_image(args, {'simv':'/accepted/simv'}, {'image':'sha'})[0],
                             Path('/accepted/simv'))
            with self.assertRaises(ValueError):
                runner.select_image(args, {'simv':'/accepted/simv'}, {'image':'other'})
        args.soc_build = Path('/other')
        with self.assertRaises(ValueError):
            runner.select_image(args, {'simv':'/accepted/simv'}, {})

    def test_unified_requires_storage_not_reader_only(self):
        args = SimpleNamespace(variant='unified', soc_build=HERE)
        soc = dict(simv='/unified/sim/simv', snapshot_sha256='abc')
        with patch.object(runner, 'checked_soc', return_value=(soc, {}, {}, {})):
            with self.assertRaises(ValueError):
                runner.select_image(args, {}, {})
        with patch.object(runner, 'checked_soc', return_value=(soc, {'storage_variant':runner.STORAGE}, {}, {})):
            self.assertEqual(runner.select_image(args, {}, {})[3]['variant'], 'unified')


if __name__ == '__main__':
    unittest.main()
