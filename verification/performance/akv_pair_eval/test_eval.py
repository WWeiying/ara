#!/usr/bin/env python3
"""Host-only positive/negative tests; synthetic logs are not target evidence."""
import copy
import csv
import importlib.util
import io
import json
import shutil
import struct
import subprocess
import tarfile
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('akv_pair_test_' + name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, check = load('build'), load('check')


def fields(prefix, row):
    return prefix + ' ' + ' '.join('%s=%s' % (k, v) for k, v in row.items())


def firmware_log(native, cycles=(100000, 110000, 120000, 105000)):
    # Deliberately slower candidates: correctness PASS cannot encode speedup.
    lines = ['AKV_PAIR_SHAPE d=128 qheads=2 kvheads=1 tokens=137 capacity=256 tile=64 vlenb=128']
    begin = 100
    bits = struct.unpack('<256I', native)
    for trial, arm in enumerate((0, 1, 1, 0)):
        lines.append(fields('AKV_PAIR_TRIAL', dict(trial=trial, arm=arm, begin=begin,
            returned=begin+cycles[trial]-10, end=begin+cycles[trial], fcsr=1, vcsr=0, vstart=0,
            initial_fcsr=0, initial_vcsr=0, initial_vstart=0, groups=1, errors=0)))
        lines.append('AKV_PAIR_MEMORY trial=%d query_hash=%016x guard_hash=%016x guard_bytes=%d' %
                     (trial, build.MEMORY['query_hash'], build.MEMORY['guard_hash'], build.MEMORY['guard_bytes']))
        lines += ['AKV_PAIR_OUT trial=%d index=%d bits=%08x' % (trial, i, value)
                  for i, value in enumerate(bits)]
        begin += cycles[trial]+100
    lines += ['AKV_PAIR_DATA data_hash=%016x data_bytes=135168 checks=1 errors=0' % build.MEMORY['data_hash'],
              'AKV_PAIR_DONE trials=4 errors=0']
    return '\n'.join(lines) + '\n'


def command_rows(arms=(0, 1, 1, 0)):
    rows = []
    for arm in arms:
        for tile, tokens in enumerate((64, 64, 9)):
            codes = [4 if tile == 0 else 5] + [6]*(32 if arm else 256) + [2]*(tokens if arm else 2*tokens)
            for code in codes:
                row = dict.fromkeys(check.PERF_FIELDS, 0)
                row.update(seq=len(rows)+1, command=code, success=1, context_ready=1, busy_cycles=10)
                if code in (4, 5):
                    row['v2_full' if code == 4 else 'v2_refill'] = 1
                    row['q_external_bytes'] = 512 if code == 4 else 0
                    row['kv_external_bytes'] = tokens*512
                    row['read_payload_bytes'] = tokens*512 + (576 if code == 4 else 0)
                    row['read_outstanding_max'] = 2
                elif code == 6:
                    row.update(v2_column_load=1, v2_column_panel=arm,
                               v2_logical_column=4 if arm else 1, replay_bytes=tokens*(8 if arm else 2))
                else:
                    row.update(v2_row_load=1, load=1, replay_bytes=256)
                rows.append(row)
        release = dict.fromkeys(check.PERF_FIELDS, 0)
        release.update(seq=len(rows)+1, command=3, success=1, busy_cycles=2, release=1)
        rows.append(release)
    return rows


def hardware_log(rows=None):
    if rows is None:
        rows = command_rows()
    totals = Counter()
    for row in rows:
        for k in check.SUMMARY_FIELDS - {'records', 'success_records', 'fault_records', 'validation_fault_records'}:
            totals[k] = max(totals[k], row[k]) if k == 'read_outstanding_max' else totals[k]+row[k]
    summary = dict(totals, records=len(rows), success_records=len(rows), fault_records=0, validation_fault_records=0)
    return '\n'.join([*(fields('[AKV_PERF]', row) for row in rows),
        fields('[AKV_PERF_SUMMARY]', summary), 'Core Test *** SUCCESS *** (tohost = 0)',
        'UVM_ERROR : 0', ' UVM_FATAL : 0 ']) + '\n'


def vector_csv(signatures=None):
    if signatures is None:
        signatures = []
        for paired in (False, True, True, False):
            for length in (64, 64, 9):
                signatures.extend([0x0205745b if paired else 0x0005745b]*(32 if paired else 256))
                signatures.extend([0x0205345b]*(length if paired else 2*length))
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'])
    writer.writerow([0, 'config', '00000000', 4, 1024])
    for i, insn in enumerate(signatures, 1):
        writer.writerow([i, 'alloc', '%08x' % insn, 4, 1024])
    return stream.getvalue()


HOST_STUB = r'''
#include "akv/akv.h"
#include "akv/akv_decode.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int pair_eval_main(void);
extern float native_golden[], decode_golden[];
extern unsigned short decode_key[], decode_value[], decode_mask[], decode_query_f16[];
extern unsigned char data_guard_before[];
static int mode, trial, finished;
static unsigned long fc, vc, vs, tick;
int printf_(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt); int n = vprintf(fmt, ap); va_end(ap); return n;
}
unsigned long pair_host_cycles(void) { return ++tick * 100000; }
unsigned long pair_host_initialize(void) { return mode == 1 ? 64 : 128; }
void pair_host_drain(void) {}
void pair_host_reset(void) { fc = mode == 2; vc = vs = 0; finished = 0; }
void pair_host_csr(unsigned long *f, unsigned long *v, unsigned long *s) {
  *f = fc; *v = vc; *s = vs;
}
unsigned long akv_native_info(void *context, unsigned index) {
  (void)context;
  if (mode == 3) return 0;
  unsigned long base = akv_capability_word(index, 1);
  return base ? base : akv_v2_capability_word(index, 1);
}
akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t *p,
                                           akv_attention_v2_workspace_t *w) {
  int arms[] = {0,1,1,0};
  if (trial >= 4 || !getenv("AKV_PAIR_HEADS") || getenv("AKV_PAIR_HEADS")[0] != '0'+arms[trial] ||
      getenv("AKV_PAIR_HEADS")[1] || getenv("AKV_QK_PANEL4") || getenv("AKV_PREFILL_PAIR_PV") ||
      getenv("OTHER") || getenv(NULL)) return AKV_STATUS_EXECUTION;
  if (!akv_attention_plan_v2_is_valid(p) || p->descriptor.q_rows != 2 ||
      p->descriptor.head_dim != 128 || p->descriptor.kv_length != 137 ||
      p->descriptor.q_row_stride_bytes != 256 || p->descriptor.k_token_stride_bytes != 256 ||
      p->descriptor.v_token_stride_bytes != 256 || p->output_row_stride_bytes != 512 ||
      p->scale != 0x1.6a09e6p-4f) return AKV_STATUS_EXECUTION;
  memcpy(p->output, native_golden, 1024);
  fc = 1; finished = 1;
  if (trial == 1) {
    if (mode == 4) return AKV_STATUS_EXECUTION;
    if (mode == 5) fc = 8;
    if (mode == 6) vc = 1;
    if (mode == 7) vs = 1;
    if (mode == 8) p->output[0] = 100.0f;
    if (mode == 9) { unsigned b; memcpy(&b,p->output,4); ++b; memcpy(p->output,&b,4); }
    if (mode == 10) ((unsigned char *)w)[sizeof(*w)] ^= 1;
    if (mode == 11) w->accumulator[0][128] ^= 1;
    if (mode == 12) w->score[2][0] = 0;
    if (mode == 13) ((unsigned char *)w)[sizeof(*w)-1] ^= 1;
    if (mode == 14) ((unsigned short *)(unsigned long)p->descriptor.q_base)[0] ^= 1;
    if (mode == 15) ((unsigned short *)decode_key)[32767] ^= 1;
    if (mode == 16) ((unsigned short *)decode_value)[32767] ^= 1;
    if (mode == 17) ((unsigned short *)decode_mask)[255] ^= 1;
    if (mode == 18) ((unsigned char *)decode_golden)[0] ^= 1;
    if (mode == 19) ((unsigned char *)native_golden)[0] ^= 1;
    if (mode == 20) ((unsigned char *)decode_query_f16)[0] ^= 1;
    if (mode == 21) ((unsigned char *)data_guard_before)[0] ^= 1;
    if (mode == 22) ((unsigned char *)p->output)[1024] ^= 1;
  }
  ++trial;
  return AKV_STATUS_OK;
}
int main(int argc, char **argv) {
  mode = argc > 1 ? atoi(argv[1]) : 0;
  int rc = pair_eval_main();
  if (!mode && (trial != 4 || !finished)) return 99;
  return rc;
}
'''


class EvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='akv_pair_eval_host_')
        cls.directory = Path(cls.temp.name)
        cls.sdk_inputs = cls.directory / 'inputs'
        cls.sdk_inputs.mkdir()
        archive = subprocess.check_output(['git', '-C', str(build.ROOT), 'archive',
                                           build.SDK_COMMIT, 'software/akv', 'apps/common'])
        build.unpack_archive(archive, cls.sdk_inputs)
        cls.archive = archive
        cls.run_host([build.HOST_CC, '-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off',
                      HERE / 'reference.c', '-lm', '-o', cls.directory / 'reference'])
        cls.native = cls.directory / 'native_golden.bin'
        cls.run_host([cls.directory / 'reference', build.DATA, cls.native])
        cls.golden = (build.DATA / 'decode_golden.bin').read_bytes()
        cls.oracle = cls.native.read_bytes()
        cls.log = firmware_log(cls.oracle) + hardware_log()
        (cls.directory / 'expected.h').write_text(build.expected_header(build.MEMORY))
        assembly = build.data_assembly(build.DATA, cls.native).replace(
            '.section .rodata.akv_pair,"a",@progbits', '.section .data.akv_pair,"aw",@progbits')
        (cls.directory / 'data.S').write_text(assembly)
        (cls.directory / 'stub.c').write_text(HOST_STUB)
        flags = ['-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra',
                 '-ffunction-sections', '-fdata-sections', '-I'+str(cls.sdk_inputs/'software/akv/include'),
                 '-I'+str(cls.sdk_inputs/'apps/common'), '-I'+str(cls.directory)]
        cls.run_host([build.HOST_CC, *flags, '-DAKV_PAIR_HOST_TEST', '-Dmain=pair_eval_main',
                      '-c', HERE/'main.c', '-o', cls.directory/'caller.o'])
        cls.run_host([build.HOST_CC, *flags, cls.directory/'caller.o', cls.directory/'data.S',
                      cls.directory/'stub.c', cls.sdk_inputs/'software/akv/src/akv_decode.c',
                      cls.sdk_inputs/'software/akv/src/akv_runtime.c', '-Wl,--gc-sections',
                      '-lm', '-o', cls.directory/'caller'])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def run_host(cls, argv):
        proc = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
        if proc.returncode:
            raise AssertionError('Host command failed: ' + repr(argv) + '\n' + proc.stdout + proc.stderr)
        return proc.stdout

    def check_log(self, text):
        return check.check_log(text, self.golden, self.oracle, build.MEMORY)

    def test_real_input_mapping_and_frozen_oracle(self):
        self.assertTrue(build.validate_data())
        self.assertEqual(build.sha(self.native), build.NATIVE_SHA)
        self.assertEqual(build.memory_expected(), build.MEMORY)
        raw = b''.join((build.DATA/(n+'.bin')).read_bytes() for n in build.FILES)+self.oracle
        self.assertEqual(len(raw), 135168)
        self.assertEqual(build.fnv64(raw), build.MEMORY['data_hash'])

    def test_full_call_host_fixture_with_real_sdk_plan_and_decode(self):
        text = self.run_host([self.directory/'caller'])
        result = self.check_log(text + hardware_log())
        self.assertEqual(result['output_values_checked'], 1024)
        self.assertEqual(result['full_data_hash_checks'], 1)

    def test_all_firmware_failures_return_nonzero_eoc(self):
        for mode in range(1, 23):
            with self.subTest(mode=mode):
                proc = subprocess.run([str(self.directory/'caller'), str(mode)],
                                      capture_output=True, text=True, timeout=5)
                self.assertEqual(proc.returncode, 1, proc.stdout[-500:] + proc.stderr)

    def test_correctness_does_not_require_speedup_and_ratio_formula(self):
        result = self.check_log(self.log)
        self.assertGreater(result['candidate_over_generic'], 1)
        self.assertAlmostEqual(result['candidate_over_generic'], 115000/102500)
        self.assertAlmostEqual(result['generic_over_candidate'], 102500/115000)
        self.assertEqual(result['paired_candidate_over_generic'], [1.1, 120000/105000])
        self.assertAlmostEqual(result['cycle_reduction_fraction'], 1-115000/102500)
        self.assertFalse(result['performance_acceptance'])

    def test_all_raw_values_are_independently_checked(self):
        for trial in range(4):
            for index in (0, 127, 128, 255):
                with self.subTest(trial=trial, index=index):
                    old = 'AKV_PAIR_OUT trial=%d index=%d bits=%08x' % (
                        trial, index, struct.unpack('<256I', self.oracle)[index])
                    with self.assertRaises(ValueError):
                        self.check_log(self.log.replace(old, old[:old.index('bits=')]+'bits=7fc00000'))
        all_bad = reformat_outputs(self.log, 0x42c80000)
        with self.assertRaisesRegex(ValueError, 'Numerical'):
            self.check_log(all_bad)
        # One ULP can be within both tolerances, but exact A/B equality still rejects it.
        old = 'AKV_PAIR_OUT trial=1 index=0 bits=%08x' % struct.unpack('<I', self.oracle[:4])[0]
        changed = old[:old.index('bits=')]+'bits=%08x' % (struct.unpack('<I', self.oracle[:4])[0]+1)
        with self.assertRaisesRegex(ValueError, 'raw output'):
            self.check_log(self.log.replace(old, changed))

    def test_numeric_golden_sizes_and_nonfinite_reference(self):
        for golden, native in ((b'', self.oracle), (self.golden, b''),
                               (struct.pack('<f', float('nan'))*256, self.oracle),
                               (self.golden, struct.pack('<f', 100.0)*256)):
            with self.subTest(size=(len(golden), len(native))), self.assertRaises(ValueError):
                check.check_log(self.log, golden, native, build.MEMORY)

    def test_flags_csrs_work_and_timing_rejected(self):
        changes = [('fcsr=1', 'fcsr=8'), ('initial_fcsr=0', 'initial_fcsr=1'),
                   ('initial_vcsr=0', 'initial_vcsr=1'), ('initial_vstart=0', 'initial_vstart=1'),
                   ('vcsr=0', 'vcsr=1'), ('vstart=0', 'vstart=1'), ('groups=1', 'groups=0'),
                   ('errors=0', 'errors=1'), ('trial=1 arm=1', 'trial=1 arm=0'),
                   ('returned=100090', 'returned=100100'), ('begin=100', 'begin=0')]
        for old, new in changes:
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.check_log(self.log.replace(old, new, 1))
        # Same acceptable flag set is mandatory, not just absence of invalid/overflow.
        with self.assertRaisesRegex(ValueError, 'CSR'):
            self.check_log(self.log.replace('fcsr=1', 'fcsr=3', 1))

    def test_hash_guard_and_complete_data_gates(self):
        for field in ('query_hash', 'guard_hash', 'data_hash'):
            old = '%s=%016x' % (field, build.MEMORY[field])
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check_log(self.log.replace(old, field+'=0000000000000000', 1))
        for old, new in [('guard_bytes=5736', 'guard_bytes=5704'),
                         ('data_bytes=135168', 'data_bytes=134144'), ('checks=1', 'checks=0')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                self.check_log(self.log.replace(old, new))

    def test_schema_missing_duplicates_extra_and_malformed(self):
        lines = self.log.splitlines()
        for index in (0, 1, 2, 3, 258, 1033, 1034):
            for operation in ('missing', 'duplicate'):
                mutated = list(lines)
                if operation == 'missing':
                    del mutated[index]
                else:
                    mutated.insert(index, lines[index])
                with self.subTest(index=index, operation=operation), self.assertRaises(ValueError):
                    self.check_log('\n'.join(mutated))
        for old, new in [('groups=1', 'groups=1 groups=1'), ('groups=1', 'groups=1 unexpected=0'),
                         ('groups=1', 'groups=-1'), ('groups=1', 'groups=no'),
                         ('AKV_PAIR_DONE', 'AKV_PAIR_UNKNOWN'), ('index=0', 'index=256')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.check_log(self.log.replace(old, new, 1))

    def test_uvm_zero_whole_line_only_and_eoc(self):
        self.assertEqual(self.check_log(self.log)['state'], 'LOG_CHECKED')
        for extra in ('UVM_ERROR : 1', 'UVM_FATAL @ 123: event', 'prefix UVM_ERROR : 0',
                      'UVM_ERROR : 0 trailing', 'UVM_FATAL : 00', 'TIMEOUT', 'timeout',
                      'Error: bad', 'Fatal: bad', '*** FAILED ***', 'AKV_PAIR_FAIL reason=1'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check_log(self.log + extra + '\n')
        for old, new in [('tohost = 0', 'tohost = 1'), ('SUCCESS', 'INCOMPLETE')]:
            with self.assertRaises(ValueError):
                self.check_log(self.log.replace(old, new))
        with self.assertRaises(ValueError):
            self.check_log(self.log+'Core Test *** SUCCESS *** (tohost = 0)\n')

    def test_exact_native_work_and_arithmetic(self):
        result = check.check_hardware_work(self.log)
        self.assertEqual(result['commands'], 2*1046+2*237)
        self.assertEqual(result['per_call_commands'], [1046, 237, 237, 1046])
        expected = check.expected_commands()
        for start, end, arm in ((0, 1046, 0), (1046, 1283, 1), (1283, 1520, 1), (1520, 2566, 0)):
            rows = expected[start:end]
            self.assertEqual(sum(r['v2_full'] for r in rows), 1)
            self.assertEqual(sum(r['v2_refill'] for r in rows), 2)
            self.assertEqual(sum(r['v2_column_load'] for r in rows), 96 if arm else 768)
            self.assertEqual(sum(r['v2_logical_column'] for r in rows), 384 if arm else 768)
            self.assertEqual(sum(r['v2_row_load'] for r in rows), 137 if arm else 274)
            self.assertEqual(sum(r['q_external_bytes'] for r in rows), 512)
            self.assertEqual(sum(r['kv_external_bytes'] for r in rows), 137*512)
            self.assertEqual(sum(r['replay_bytes'] for r in rows), (137*256)*(2 if arm else 4))

    def test_candidate_claim_with_generic_work_rejected(self):
        with self.assertRaisesRegex(ValueError, 'native command'):
            check.check_hardware_work(firmware_log(self.oracle)+hardware_log(command_rows((0, 0, 0, 0))))
        real = build.OUT/'chain_profile_runs_20261107_01/f16/work/run.vcs.log'
        if real.is_file():
            with self.assertRaisesRegex(ValueError, 'native command'):
                check.check_hardware_work(real.read_text())

    def test_commands_tail_panel_payload_fault_sequence_schema(self):
        cases = [(0, 'q_external_bytes', 256), (0, 'kv_external_bytes', 64),
                 (0, 'read_payload_bytes', 33280), (1, 'replay_bytes', 126),
                 (1047, 'v2_logical_column', 1), (1047, 'v2_column_panel', 0),
                 (1047, 'replay_bytes', 128), (1263, 'replay_bytes', 512),
                 (1250, 'kv_external_bytes', 32768), (0, 'seq', 2),
                 (1, 'busy_cycles', 0), (1, 'context_ready', 0)]
        cases += [(1047, field, 1) for field in ('fault', 'validation_fault', 'validation_error',
                                               'read_fault', 'v2_rejected', 'full', 'refill')]
        for index, field, value in cases:
            rows = command_rows()
            rows[index][field] = value
            with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                check.check_hardware_work(hardware_log(rows))
        for extra in ('', hardware_log().splitlines()[0]+'\n'):
            # Missing one command or duplicated first command.
            log = hardware_log().split('\n', 1)[1] if not extra else extra+hardware_log()
            with self.assertRaises(ValueError):
                check.check_hardware_work(log)
        for old, new in [('id=0', 'id=0 id=0'), ('id=0', 'id=0 unknown=0'),
                         ('success=1', 'success=-1'), ('seq=1', 'seq=18446744073709551616')]:
            with self.assertRaises(ValueError):
                check.check_hardware_work(hardware_log().replace(old, new, 1))
        with self.assertRaises(ValueError):
            check.check_hardware_work(hardware_log().replace('[AKV_PERF_SUMMARY]', '[MISSING_SUMMARY]'))

    def vector_check(self, text):
        path = self.directory/'trace.csv'
        path.write_text(text)
        with patch.object(check, 'verify_build', return_value={'elf_sha256': 'host-fixture'}):
            return check.check_vector_workcounts(path, self.directory)

    def test_vector_api_two_arguments_and_signature_counts(self):
        result = self.vector_check(vector_csv())
        self.assertEqual(result['counts'], dict(k_column_commands=1536, k_panel4_commands=192, v_row_commands=822))
        self.assertEqual(result['native_commands_with_lifecycle'], 2566)
        self.assertEqual(result['replay_commands'], 2550)

    def test_vector_missing_duplicate_wrong_signature_disabled_candidate_and_schema(self):
        text = vector_csv()
        lines = text.splitlines()
        mutations = [text.replace('0205745b', '0005745b'), text.replace('0205345b', '0405345b', 1),
                     '\n'.join(lines[:-1]), '\n'.join([*lines, lines[-1]]),
                     text.replace('vlen_bits', 'wrong_header'), text.replace(',1024', ',2048', 1),
                     text.replace('0005745b', 'nonsense', 1), text.replace(',alloc,', ',reset,', 1)]
        reordered = list(lines)
        a, b = reordered[2].split(','), reordered[258].split(',')
        a[2], b[2] = b[2], a[2]
        reordered[2], reordered[258] = ','.join(a), ','.join(b)
        mutations.append('\n'.join(reordered))
        for index, value in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.vector_check(value)

    def test_input_mutation_even_receipt_rewritten_is_rejected(self):
        data = self.directory/'changed-data'
        shutil.copytree(build.DATA, data)
        path = data/'decode_value.bin'
        raw = bytearray(path.read_bytes()); raw[-1] ^= 1; path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, 'Data identity'):
            build.validate_data(data)
        receipt = json.loads((data/'result.json').read_text())
        receipt['artifacts'][str(build.DATA/'decode_value.bin')] = build.sha(path)
        (data/'result.json').write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, 'Data identity'):
            build.validate_data(data)

    def test_build_rejects_reuse_wrong_output_tool_or_input_before_compiling(self):
        candidates = [(self.directory, build.CC, build.DATA),
                      (build.OUT/'akv_pair_eval_build_20261107_hosttest', Path('/usr/bin/clang'), build.DATA),
                      (build.OUT/'akv_pair_eval_build_20261107_hosttest', build.CC, self.directory)]
        for out, cc, data in candidates:
            with self.subTest(output=out), self.assertRaises(ValueError), patch.object(
                    build.subprocess, 'run', side_effect=AssertionError('Must not compile')):
                build.build(out, cc, data)
        with tempfile.TemporaryDirectory(prefix='akv_pair_eval_build_20261107_', dir=build.OUT) as out:
            with self.assertRaisesRegex(ValueError, 'fresh'):
                build.build(Path(out))

    def test_archive_unsafe_link_or_parent_rejected(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as tar:
                info = tarfile.TarInfo(name); info.type = kind; info.linkname = '/tmp/escape'
                tar.addfile(info)
            with self.assertRaises(ValueError):
                build.unpack_archive(buffer.getvalue(), self.directory/'badarchive')

    def build_receipt_fixture(self):
        # Receipt-only synthetic artifacts exercise checker gates, not a target build.
        directory = Path(tempfile.mkdtemp(prefix='receipt-', dir=self.directory))
        inputs = directory/'inputs'
        shutil.copytree(self.sdk_inputs, inputs)
        archive = inputs/'sdk-785084122.tar'
        archive.write_bytes(self.archive)
        native = directory/'native_golden.bin'
        native.write_bytes(self.oracle)
        elf = directory/'akv_pair_eval.elf'
        elf.write_bytes(b'\x7fELF' + b'HOSTTEST_ONLY_NOT_TARGET_EVIDENCE')
        (directory/'expected.h').write_text(build.expected_header(build.MEMORY))
        (directory/'data.S').write_text(build.data_assembly(build.DATA, native))
        (directory/'link.ld').write_text('/* host-only receipt fixture */\n')
        common, sdk = inputs/'apps/common', inputs/'software/akv'
        sources = [HERE/'main.c', directory/'data.S',
            *[common/n for n in ('crt0.S', 'printf.c', 'string.c', 'serial.c', 'util.c', 'print_trap_cause.c')],
            *[sdk/'src'/n for n in ('akv_runtime.c', 'akv_decode.c', 'akv_features.c',
                'akv_prefill_reference.c', 'akv_native_riscv.c', 'akv_v2_native_riscv.c',
                'akv_v2_attention_rvv.S', 'akv_attention_rvv.S')]]
        objects, commands = [], []
        for index, source in enumerate(sources):
            obj = directory/('%02d_%s.o' % (index, source.stem))
            obj.write_bytes(b'HOST_RECEIPT_ONLY')
            objects.append(str(obj))
            commands.append(dict(label='compile-'+obj.stem, returncode=0, cwd=str(directory),
                argv=[str(build.CC.resolve()), '-DAKV_REFILL_OVERLAP=0', '-c', str(source), '-o', str(obj)]))
        (directory/'commands.json').write_text(json.dumps(commands))
        pins = build.validate_data()
        pins.update({str(HERE/n): build.sha(HERE/n) for n in build.OWN_FILES})
        pins.update({str(p): build.sha(p) for p in inputs.rglob('*') if p.is_file()})
        for name in ('expected.h', 'data.S', 'link.ld', 'native_golden.bin'):
            pins[str(directory/name)] = build.sha(directory/name)
        pinfile = directory/'source-pins.json'
        pinfile.write_text(json.dumps(pins))
        manifest = dict(schema=1, state='BUILT_NOT_EXECUTED', target_executed=False,
            rtl_executed=False, performance_measured=False, sdk_head=build.SDK_COMMIT,
            sdk_tree=build.SDK_TREE, common_tree=build.COMMON_TREE, sdk_unmodified=True,
            dirty_asm_excluded=True, all_runtime_objects_recompiled=True, shape=build.SHAPE,
            order=build.ORDER, image_contract=build.IMAGE, initial_csr=dict(fcsr=0, vcsr=0, vstart=0),
            data=str(build.DATA), capture=str(build.CAPTURE), memory_expected=build.MEMORY,
            toolchain=dict(target=str(build.CC.resolve()), host=str(build.HOST_CC), zcc=False),
            elf=str(elf), elf_sha256=build.sha(elf), source_pins=str(pinfile),
            source_pins_sha256=build.sha(pinfile), sdk_archive=str(archive), sdk_archive_sha256=build.sha(archive),
            SDKpins={str(p.relative_to(inputs)): build.sha(p) for p in sdk.rglob('*') if p.is_file()},
            golden=dict(captured=str(build.DATA/'decode_golden.bin'),
                captured_sha256=build.DATA_SHA['decode_golden'], native_tile64=str(native),
                native_tile64_sha256=build.NATIVE_SHA, capture_atol=0.003, capture_rtol=0.02,
                native_atol=0.0002, native_rtol=0.003), objects_recompiled=16, objects=objects,
            compile_commands=str(directory/'commands.json'),
            artifacts={str(p): build.sha(p) for p in directory.rglob('*') if p.is_file()})
        (directory/'build.json').write_text(json.dumps(manifest))
        return directory, manifest

    def test_checker_public_apis_and_owner_checked_software_receipt_compatibility(self):
        directory, manifest = self.build_receipt_fixture()
        log, vector = directory/'synthetic.log', directory/'vector.csv'
        log.write_text(self.log)
        vector.write_text(vector_csv())
        self.assertEqual(check.check_run(log, directory)['state'], 'PASS')
        self.assertTrue(check.check_vector_workcounts(vector, directory))
        spec = importlib.util.spec_from_file_location('pair_owner_shared_run_case',
                                                      HERE.parent/'chain_profile/run_case.py')
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.path.insert(0, str(HERE.parent/'chain_profile'))
        try:
            spec.loader.exec_module(module)
            checked, pins = module.checked_software(directory)
        finally:
            sys.path.pop(0)
        self.assertEqual(checked['elf_sha256'], manifest['elf_sha256'])
        self.assertTrue(pins)

    def test_build_schema_contract_and_identity_mutations_rejected(self):
        directory, manifest = self.build_receipt_fixture()
        mutations = [dict(schema=2), dict(schema=True), dict(state='PASS'),
                     dict(sdk_head='640862d2d'), dict(sdk_unmodified=False), dict(dirty_asm_excluded=False),
                     dict(all_runtime_objects_recompiled=False), dict(objects_recompiled=15),
                     dict(order=[0, 0, 0, 0]), dict(shape={**build.SHAPE, 'valid_tokens': 136}),
                     dict(image_contract={**build.IMAGE, 'VLEN': 2048}),
                     dict(initial_csr=dict(fcsr=1, vcsr=0, vstart=0)), dict(data='/wrong-real-input'),
                     dict(memory_expected={**build.MEMORY, 'data_hash': 0}),
                     dict(golden={**manifest['golden'], 'capture_atol': 1.0}),
                     dict(source_pins_sha256='0'*64), dict(elf_sha256='0'*64), dict(artifacts={})]
        for mutation in mutations:
            (directory/'build.json').write_text(json.dumps({**manifest, **mutation}))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                check.verify_build(directory)
        (directory/'build.json').write_text(json.dumps(manifest))
        path = directory/'inputs/software/akv/src/akv_v2_attention_rvv.S'
        path.write_text(path.read_text()+'\n/* wrong assembly */\n')
        with self.assertRaisesRegex(ValueError, 'drift'):
            check.verify_build(directory)

    def test_compiler_dependency_parser_and_frozen_fnv(self):
        dep = self.directory/'test.d'
        dep.write_text('test.o: /tmp/source.c \\\n /tmp/a\\ b.h\n')
        self.assertEqual(build.dependency_inputs(dep), [Path('/tmp/source.c'), Path('/tmp/a b.h')])
        self.assertEqual(build.fnv64(b''), 14695981039346656037)
        self.assertEqual(build.fnv64(b'hello'), 0xa430d84680aabd0b)


def reformat_outputs(text, value):
    lines = []
    for line in text.splitlines():
        if line.startswith('AKV_PAIR_OUT '):
            line = line[:line.index('bits=')]+'bits=%08x' % value
        lines.append(line)
    return '\n'.join(lines)


if __name__ == '__main__':
    unittest.main()
