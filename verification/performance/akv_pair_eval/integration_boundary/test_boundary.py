#!/usr/bin/env python3
"""Host-only new-SDK boundary contracts; no target build, VCS, or large old trace scan."""
import copy
import csv
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('auto_boundary_host_check', HERE / 'check.py')
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
b, o, s = c.b, c.old, c.succ
MINI = c.make_schema([[o.FULL, o.COLUMN, o.ROW96, o.ROW96, o.RELEASE]])
PCS = {0x80001000 + i * 4: w for i, w in enumerate([s.INFO, o.FULL, o.COLUMN, o.ROW96, o.RELEASE])}


def numeric_fixture(legacy):
    lines, records = ['Command: simv +AKV_PERF +AKV_SUMMARY', c.CAP, legacy.CAP], []
    for case in range(4):
        for trial in range(3):
            missing = int(case == 3 and trial == 1)
            lines += [legacy.begin(case, trial), f'AKV_AUTO_BOUNDARY_ROUTE case={case} trial={trial} '
                      f'auto={int(trial == 1)} missing_panel={missing} panel={1 - missing}']
            for item in c.numeric_work(legacy, case, trial):
                row = dict.fromkeys(legacy.s.PERF_FIELDS, 0)
                row.update(legacy.expected_record(legacy.CASES[case], item, len(records) + 1))
                row.update(id=0, busy_cycles=10)
                if item[0] in (4, 5):
                    row.update(ar=row['read_ranges'], r_beats=2000, read_outstanding_max=2)
                records.append(row)
                lines.append('[AKV_PERF] ' + ' '.join(f'{k}={v}' for k, v in row.items()))
            shape = legacy.CASES[case]
            lines.append(f'NATIVE_PAIR_RESULT case={case} trial={trial} requested={int(trial == 1)} '
                f'outputs={shape["d"] * shape["heads"]} compared=4096 hash=0123456789abcdef fcsr=3 vcsr=5 errors=0')
    lines.append(legacy.SUITE)
    lines += [f'AKV_BOUNDARY_PAYLOAD name={n} bytes={p["bytes"]} fnv={p["fnv64"]:016x} '
              f'expected={p["fnv64"]:016x} errors=0' for n, p in b.old.PAYLOADS.items()]
    lines += ['AKV_BOUNDARY_DONE body=0 checks=3 errors=0', c.DONE, legacy.s.TERMINAL,
              'UVM_ERROR : 0', 'UVM_FATAL : 0', '[AKV_PERF_SUMMARY] ' +
              ' '.join(f'{k}={v}' for k, v in legacy.s.totals(records).items())]
    return '\n'.join(lines) + '\n'


def small_fixture(overrides=None):
    vector, commit = [], []
    config = dict.fromkeys(s.VECTOR_FIELDS, '0')
    config.update(event='config', insn='00000000', be='00', wdata='0000000000000000', nr_lanes='4', vlen_bits='1024')
    vector.append(config)
    word_pc = {w: pc for pc, w in PCS.items()}
    retirement, index = 0, -1

    def row(event, cycle, order, word, port=-1):
        r = dict.fromkeys(s.COMMIT_FIELDS, '0')
        r.update(cycle=str(cycle), event=event, order=str(order), port=str(port), trans_id='-1',
            pc=f'{word_pc.get(word, 0):016x}', insn=f'{word:08x}', rd_wdata='0000000000000000',
            mem_addr='0000000000000000', mem_rmask='00', mem_wmask='00', mem_wdata='0000000000000000')
        return r

    shapes = {o.FULL: (0, 0, 1, 1, 0), o.RELEASE: (0, 0, 1, 1, 0),
              o.COLUMN: (1, 8, 1, 64, 0), o.ROW96: (1, 8, 1, 96, 0)}
    for seq, word in enumerate(MINI['extended']):
        cycle = 1000 + seq * 32
        start = row('arch_start', cycle, seq, word)
        start['trans_id'] = str(seq % 16)
        commit.append(start)
        if word != s.INFO:
            index += 1
            group = [shapes[word]]
            if index in MINI['triples']:
                group = [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0), (1, 8, 1, 96, 0)]
            group = (overrides or {}).get(index, group)
            for i, shape in enumerate(group):
                for event, offset in (('alloc', 2 + i * 4), ('done', 4 + i * 4)):
                    r = dict(config, event=event, cycle=str(cycle + offset), arch_seq=str(seq), vid=str(i))
                    r['insn'] = f'{word:08x}'
                    r.update({k: str(v) for k, v in zip(s.SHAPE, shape)})
                    vector.append(r)
                    commit.append(row('uop_' + event, cycle + offset, seq, word, i))
        commit.append(row('retire', cycle + 20, retirement, word, 0))
        retirement += 1
        commit.append(row('retire', cycle + 21, retirement, 0x13, 0))
        retirement += 1
    return vector, commit


class AutoBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='.host-auto-boundary-', dir=HERE)
        cls.root = Path(cls.tmp.name)
        cls.inputs = cls.root / 'inputs'
        cls.inputs.mkdir()
        cls.new = subprocess.check_output([str(b.GIT), '-C', str(b.ROOT), 'archive', b.SDK_COMMIT, *b.old.ARCHIVE_PATHS])
        cls.baseline = subprocess.check_output([str(b.GIT), '-C', str(b.ROOT), 'archive', b.old.SDK_COMMIT,
                                               *b.old.ARCHIVE_PATHS])
        cls.members = b.validate_archives(cls.new, cls.baseline)
        b.old.unpack_archive(cls.new, cls.inputs)
        cls.legacy = o.load_legacy(cls.inputs)
        cls.log = numeric_fixture(cls.legacy)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def audit(self, vector, commit):
        for path, fields, data in [(self.root / 'vector.csv', s.VECTOR_FIELDS, vector),
                                   (self.root / 'commit.csv', s.COMMIT_FIELDS, commit)]:
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(data)
        return c.audit_vector(self.root / 'vector.csv', PCS, MINI)

    def test_archive_diffset_and_fresh_recipes(self):
        self.assertEqual(len(b.compile_recipe(self.root)), 16)
        self.assertEqual(b.compile_recipe(self.root)[0][-3], str(HERE / 'main.c'))
        self.assertEqual(b.link_recipe(self.root)[-1], str(self.root / b.ELF_NAME))
        self.assertIn('run.py', b.OWN_FILES)
        prior = b.old.archive_members(self.baseline)
        changed = {n for n in self.members.keys() | prior.keys() if self.members.get(n) != prior.get(n)}
        self.assertEqual(changed, set(b.SDK_DELTA))
        self.assertTrue(all(self.members[n] == data for n, data in prior.items() if n.endswith('.S')))
        native = self.members['software/akv/src/akv_v2_native_riscv.c'].decode()
        policy = self.members['software/akv/experimental/paired_heads/auto_policy.h'].decode()
        self.assertIn('const int paired_heads = automatic\n', native)
        self.assertIn('? auto_pair_enabled_for_plan(plan, auto_device, features == NULL)', native)
        self.assertNotIn('akv_device_query', policy)
        self.assertNotIn('getenv', policy)
        self.assertEqual(b.helper_pins()[str(b.PARENT / 'run.py')], b.SEALED['run.py'])
        with self.assertRaises(ValueError):
            b.validate_archives(self.baseline, self.baseline)
        with mock.patch.object(b, 'SDK_DELTA', {}), self.assertRaisesRegex(ValueError, 'diffset'):
            b.validate_archives(self.new, self.baseline)

    def test_new_work_and_complete_numerical_log(self):
        schema = c.work_schema()
        self.assertEqual(schema['per_call_commands'], b.WORK['per_call_commands'])
        self.assertEqual((len(schema['native']), len(schema['extended']), schema['raw_allocations']), (3968, 3972, 3980))
        self.assertEqual(schema['counts']['panel4'], 64)
        self.assertEqual(schema['counts']['column_v8'] + schema['counts']['column_v9'], 2944)
        self.assertEqual(schema['counts']['row_d128'], 384)
        result = c.check_log(self.log, self.legacy)
        self.assertEqual(result['raw_hardware_summary']['records'], 3968)
        self.assertEqual(len(result['trials']), 12)
        self.assertFalse(result['performance_measured'])
        for old, new in [(b.SDK_COMMIT, b.old.SDK_COMMIT), ('missing_panel=1 panel=0', 'missing_panel=0 panel=1'),
                         ('compared=4096', 'compared=2048'), ('fcsr=3', 'fcsr=2'),
                         ('fnv=afefa3ea4b06654c', 'fnv=bfefa3ea4b06654c'), ('queries=1', 'queries=2')]:
            with self.subTest(field=old), self.assertRaises(ValueError):
                c.check_log(self.log.replace(old, new, 1), self.legacy)

    def test_small_vector_commit_positive_and_discriminating_negatives(self):
        vector, commit = small_fixture()
        result = self.audit(vector, commit)
        self.assertEqual(result['native_commands'], 5)
        self.assertEqual(result['raw_custom_allocations'], 7)
        self.assertEqual(result['commit_checks']['retired_info_commands'], 4)
        self.assertTrue(result['raw_preserved'])
        for override in ({1: [(1, 8, 1, 64, 0)] * 2},
                         {2: [(1, 8, 1, 64, 0), (1, 9, 1, 64, 0)]},
                         {2: [(1, 8, 1, 64, 0), (1, 8, 1, 64, 0), (1, 8, 1, 96, 0)]}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.audit(*small_fixture(override))
        for event, field, value in [('retire', 'trap', '1'), ('retire', 'pc', '000000008000ffff'),
                                    ('retire', 'insn', f'{o.REFILL:08x}'), ('arch_start', 'order', '99')]:
            changed = copy.deepcopy(commit)
            next(r for r in changed if r['event'] == event)[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.audit(vector, changed)
        changed = copy.deepcopy(vector)
        next(r for r in changed if r['event'] == 'alloc')['vid'] = '8'
        with self.assertRaises(ValueError):
            self.audit(changed, commit)

    def test_unsealed_build_and_run_never_launch(self):
        runner = b.load(HERE / 'run.py', 'auto_boundary_host_runner')
        with mock.patch.object(b.subprocess, 'run') as command, self.assertRaisesRegex(ValueError, 'seal-ready'):
            b.build()
        command.assert_not_called()
        args = types.SimpleNamespace(kind='boundary', build=self.root)
        with mock.patch.object(runner, 'private_owner') as owner, self.assertRaisesRegex(ValueError, 'seal-ready'):
            runner.run(args)
        owner.assert_not_called()
        private = runner.private_owner()
        self.assertIs(private.load_checker, runner.load_checker)
        self.assertEqual(private.run.__globals__['__file__'], str(b.PARENT / 'run.py'))
        self.assertEqual(runner.load_checker('boundary')[0], HERE / 'check.py')
        with self.assertRaises(ValueError):
            runner.load_checker('qwen3_abba')
        with mock.patch.object(runner.checker, 'verify_build'), mock.patch.object(runner, 'private_owner') as factory:
            factory.return_value.run.return_value = {'fixture_only': True}
            self.assertEqual(runner.run(args, seal_ready=True), {'fixture_only': True})
            factory.return_value.run.assert_called_once_with(args)

    def test_reject_old_sdk_build_and_missing_new_pins(self):
        with self.assertRaisesRegex(ValueError, 'New SDK'):
            c.verify_build(b.OUT / 'akv_pair_boundary_build_20261107_01')
        with mock.patch.object(c, 'verify_build', side_effect=ValueError('missing new pins')), \
             mock.patch.object(c, 'audit_vector') as gate, self.assertRaisesRegex(ValueError, 'missing new pins'):
            c.check_vector_workcounts(self.root / 'vector.csv', self.root)
        gate.assert_not_called()

    def test_static_callgraph_tolerates_new_internal_clone_but_not_missing_auto(self):
        # Synthetic instruction bytes exercise the ELF graph gate, not target execution.
        names = ['main', 'boundary_body', 'boundary_route', 'capture_device', 'getenv', 'akv_device_query',
                 'akv_attention_plan_create_v2', 'akv_attention_execute_v2_native',
                 'akv_attention_execute_v2_native_auto', 'execute_v2_with_features_native_internal.constprop.0']
        helpers = {n: w for n, w in o.FUNCTION_WORDS.items() if n != 'akv_attention_execute_v2_with_features_native'}
        names = list(dict.fromkeys(names + list(helpers)))
        addresses = {n: 0x80001000 + i * 256 for i, n in enumerate(names)}
        internal = 'execute_v2_with_features_native_internal.constprop.0'
        edges = {'main': ['boundary_body'], 'boundary_body': ['capture_device', 'boundary_route', 'akv_attention_plan_create_v2'],
                 'capture_device': ['akv_device_query'], 'boundary_route': ['akv_attention_execute_v2_native',
                 'akv_attention_execute_v2_native_auto'], 'akv_attention_execute_v2_native': [internal],
                 'akv_attention_execute_v2_native_auto': [internal]}
        symbols = {}
        for name in names:
            code = bytearray(b''.join(struct.pack('<I', w) for w in helpers.get(name, [])))
            if name == internal:
                code += b''.join(struct.pack('<I', w) for w in (o.FULL, o.REFILL, o.RELEASE))
            for target in edges.get(name, []):
                delta = addresses[target] - (addresses[name] + len(code))
                upper = (delta + 0x800) >> 12
                lower = delta - (upper << 12)
                code += struct.pack('<II', (upper & 0xfffff) << 12 | (6 << 7) | 0x17,
                                    (lower & 0xfff) << 20 | (6 << 15) | 0x67)
            code += struct.pack('<I', 0x00008067)
            symbols[name] = dict(type=2, bytes=len(code), data=bytes(code), address=addresses[name], section_flags=6)
        for item in b.old.PAYLOADS.values():
            raw = (b.old.CAPTURE / (item['role'] + '-0.bin')).read_bytes()
            symbols[item['symbol']] = dict(type=1, bytes=len(raw), data=raw, address=0x80010000, section_flags=2)
        with mock.patch.object(o, 'elf_contents', return_value=symbols):
            self.assertTrue(c.check_elf('synthetic_only')['new_auto_and_legacy_call_edges_checked'])
            symbols['boundary_route']['data'] = struct.pack('<I', 0x00008067)
            with self.assertRaisesRegex(ValueError, 'call edge'):
                c.check_elf('synthetic_only')

    def test_host_wrapper_null_environment_cached_device_and_fallback(self):
        host = self.root / 'host_wrapper'
        host.mkdir()
        (host / 'expected.h').write_text(b.old.expected_header())
        (host / 'data.S').write_text(b.old.data_assembly(host))
        for p in b.old.PAYLOADS.values():
            shutil.copyfile(b.old.CAPTURE / (p['role'] + '-0.bin'), host / (p['role'] + '-0.bin'))
        # Explicit host stub replaces only the hardware body. No RTL/native arithmetic claim.
        (host / 'native_runtime_main.c').write_text('''
extern const float candidate_query_f32[];
extern const uint16_t candidate_key[], candidate_value[];
static unsigned requested;
char *getenv(const char *name) { (void)name; return "1"; }
int main(void) {
  akv_device_t device;
  if (akv_device_query(akv_native_info, NULL, &device)) return 1;
  const unsigned dims[] = {64,96,128,128}, heads[] = {3,3,6,2};
  for (unsigned c = 0; c < 4; ++c) for (unsigned t = 0; t < 3; ++t) {
    akv_attention_plan_t p = {0}; akv_attention_v2_workspace_t ws = {0};
    p.descriptor.head_dim = dims[c]; p.descriptor.q_rows = heads[c]; requested = t == 1;
    if (akv_attention_execute_v2_native(&p, &ws)) return 1;
  }
  return BODY_STATUS;
}
''')
        (host / 'stubs.c').write_text('''
#include "akv/akv.h"
#include <stdlib.h>
#include <stdio.h>
void _putchar(char ch) { putchar((unsigned char)ch); }
uint64_t akv_native_info(void *p, unsigned i) { (void)p; (void)i; return 0; }
akv_status_t akv_device_query(akv_info_reader_t r, void *p, akv_device_t *d) {
  (void)r; (void)p; *d = (akv_device_t){0}; d->capabilities.token_axis_column_panel4=1; return AKV_STATUS_OK;
}
akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t *p, akv_attention_v2_workspace_t *w) {
  (void)p; (void)w; return getenv("AKV_PAIR_HEADS") == NULL ? AKV_STATUS_OK : AKV_STATUS_EXECUTION;
}
akv_status_t akv_attention_execute_v2_native_auto(const akv_device_t *d, const akv_attention_plan_t *p,
                                               akv_attention_v2_workspace_t *w) {
  (void)w; unsigned missing=p->descriptor.head_dim==128 && p->descriptor.q_rows==2;
  return d->capabilities.token_axis_column_panel4==!missing && getenv("AKV_PAIR_HEADS")==NULL
    ? AKV_STATUS_OK : AKV_STATUS_EXECUTION;
}
''')
        self.assertEqual(b.sha(b.HOST_CC), b.old.HOST_CC_SHA)
        for body, mutate in ((0, False), (7, False), (0, True)):
            if mutate:
                path = host / 'attn_v_input-0.bin'
                data = path.read_bytes()
                path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            command = [str(b.HOST_CC), '-std=gnu11', '-O2', '-fno-builtin', '-Wall', '-Wextra', '-Werror',
                '-DBODY_STATUS=' + str(body), '-I' + str(self.inputs / 'software/akv/include'),
                '-I' + str(self.inputs / 'apps/common'), '-I' + str(host), str(HERE / 'main.c'),
                str(host / 'stubs.c'), str(self.inputs / 'apps/common/printf.c'), str(host / 'data.S'),
                '-o', str(host / 'wrapper')]
            # Only the host character sink uses libc; the formatter is archived Ara printf.
            command.insert(1, '-DPRINTF_DISABLE_SUPPORT_FLOAT')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(host / 'wrapper')], capture_output=True, text=True)
            self.assertEqual(result.returncode, int(body != 0 or mutate))
            self.assertEqual(result.stdout.count('AKV_AUTO_BOUNDARY_ROUTE '), 12)
            self.assertIn('AKV_AUTO_BOUNDARY_ROUTE case=3 trial=1 auto=1 missing_panel=1 panel=0', result.stdout)
            self.assertIn('calls=12 queries=1 autos=4 fallbacks=1 errors=' + str(int(body != 0 or mutate)), result.stdout)
            self.assertEqual(result.stdout.count('AKV_BOUNDARY_PAYLOAD '), 3)


if __name__ == '__main__':
    unittest.main()
