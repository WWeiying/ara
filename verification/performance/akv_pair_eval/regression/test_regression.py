#!/usr/bin/env python3
"""Host-only tests: generated transcripts and native stubs are not RTL evidence."""
import copy
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from collections import Counter
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location('smollm_host_'+name, HERE/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, check = load('build'), load('check')


def fields(prefix, row):
    return prefix+' '+' '.join('%s=%s' % (k, v) for k, v in row.items())


def firmware_log(native, memory, cycles=(10000, 12000, 13000, 11000)):
    lines = ['AKV_SMOL_SHAPE d=64 qheads=3 kvheads=1 tokens=5 capacity=256 tile=64 vlenb=128']
    begin = 100
    for t, arm in enumerate((0, 1, 1, 0)):
        lines.append(fields('AKV_SMOL_TRIAL', dict(trial=t, arm=arm, begin=begin,
            returned=begin+cycles[t]-10, end=begin+cycles[t], fcsr=1, vcsr=0, vstart=0,
            initial_fcsr=0, initial_vcsr=0, initial_vstart=0, groups=1, errors=0)))
        lines.append('AKV_SMOL_MEMORY trial=%d query_hash=%016x guard_hash=%016x guard_bytes=%d' %
            (t, memory['query_hash'], memory['guard_hash'], memory['guard_bytes']))
        lines += ['AKV_SMOL_OUT trial=%d index=%d bits=%08x' % (t, i, b)
                  for i, b in enumerate(struct.unpack('<192I', native))]
        begin += cycles[t]+100
    payload = {k: '%016x' % memory[k] if k in check.HEX_KEYS else memory[k]
               for k in ('data_hash', 'data_bytes', 'query_f32_hash', 'key_hash', 'value_hash', 'mask_hash')}
    lines += [fields('AKV_SMOL_DATA', dict(payload, checks=1, errors=0)), 'AKV_SMOL_DONE trials=4 errors=0']
    return '\n'.join(lines)+'\n'


def command_rows():
    rows = []
    for arm in (0, 1, 1, 0):
        codes = [(4, 0)]+([(6, 1)]*16+[(6, 0)]*64 if arm else [(6, 0)]*192)
        codes += [(2, 0)]*(10 if arm else 15)+[(3, 0)]
        for code, panel in codes:
            row = dict.fromkeys(check.PERF_FIELDS, 0)
            row.update(seq=len(rows)+1, command=code, success=1, busy_cycles=10,
                       context_ready=int(code != 3))
            if code == 4:
                row.update(v2_full=1, q_external_bytes=384, kv_external_bytes=1280,
                           read_payload_bytes=1728, read_ranges=14, r_beats=108, ar=14,
                           read_outstanding_max=2)
            elif code == 6:
                row.update(v2_column_load=1, v2_column_panel=panel, v2_logical_column=4 if panel else 1,
                           v2_k_view_bank_cycles=1, replay_bytes=40 if panel else 10)
            elif code == 2:
                row.update(v2_row_load=1, load=1, replay_bytes=128)
            else:
                row.update(release=1)
            rows.append(row)
    return rows


def hardware_log(rows=None):
    rows = command_rows() if rows is None else rows
    total = Counter()
    for row in rows:
        for k in check.SUMMARY_FIELDS-{'records', 'success_records', 'fault_records', 'validation_fault_records'}:
            total[k] = max(total[k], row[k]) if k == 'read_outstanding_max' else total[k]+row[k]
    summary = dict(total, records=len(rows), success_records=len(rows), fault_records=0, validation_fault_records=0)
    return '\n'.join([*(fields('[AKV_PERF]', r) for r in rows), fields('[AKV_PERF_SUMMARY]', summary),
        'Core Test *** SUCCESS *** (tohost = 0)', 'UVM_ERROR : 0', ' UVM_FATAL : 0 '])+'\n'


def vector_csv(values=None):
    if values is None:
        values = []
        for arm in (0, 1, 1, 0):
            values.extend([0x0205745b]*16+[0x0005745b]*64 if arm else [0x0005745b]*192)
            values.extend([0x0005345b]*(10 if arm else 15))
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(['cycle', 'event', 'insn', 'nr_lanes', 'vlen_bits'])
    writer.writerow([0, 'config', '00000000', 4, 1024])
    for i, value in enumerate(values, 1):
        writer.writerow([i, 'alloc', '%08x' % value, 4, 1024])
    return stream.getvalue()


HOST_STUB = r'''
#include "akv/akv.h"
#include "akv/akv_decode.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int smol_main(void);
/* The assembly fixture is writable; const-qualified injection stores are UB. */
extern float native_golden[], decode_golden[], decode_query[];
extern unsigned short decode_key[], decode_value[], decode_mask[], decode_query_f16[];
extern unsigned char data_guard_before[];
static unsigned mode, trial, finished;
static unsigned long fc, vc, vs, tick;
int printf_(const char *fmt, ...) {
  va_list ap; va_start(ap, fmt); int count = vprintf(fmt, ap); va_end(ap); return count;
}
unsigned long smol_host_cycles(void) { return ++tick*100000; }
unsigned long smol_host_initialize(void) { return mode == 1 ? 64 : 128; }
void smol_host_drain(void) {}
void smol_host_reset(void) { fc = mode == 2; vc = vs = 0; finished = 0; }
void smol_host_csr(unsigned long *f, unsigned long *v, unsigned long *s) { *f = fc; *v = vc; *s = vs; }
unsigned long akv_native_info(void *context, unsigned index) {
  (void)context;
  if (mode == 3) return 0;
  unsigned long bits = akv_capability_word(index, 1);
  return bits ? bits : akv_v2_capability_word(index, 1);
}
akv_status_t akv_attention_execute_v2_native(const akv_attention_plan_t *p,
                                           akv_attention_v2_workspace_t *w) {
  unsigned arms[] = {0, 1, 1, 0};
  if (trial >= 4 || !getenv("AKV_PAIR_HEADS") || getenv("AKV_PAIR_HEADS")[0] != (char)('0'+arms[trial]) ||
      getenv("AKV_PAIR_HEADS")[1] || getenv("AKV_QK_PANEL4") || getenv("AKV_PREFILL_PAIR_PV") ||
      getenv("OTHER")) return AKV_STATUS_EXECUTION;
  if (!akv_attention_plan_v2_is_valid(p) || p->descriptor.q_rows != 3 ||
      p->descriptor.head_dim != 64 || p->descriptor.kv_length != 5 ||
      p->descriptor.q_row_stride_bytes != 128 || p->descriptor.k_token_stride_bytes != 128 ||
      p->descriptor.v_token_stride_bytes != 128 || p->output_row_stride_bytes != 256 ||
      p->scale != 0.125f) return AKV_STATUS_EXECUTION;
  memcpy(p->output, native_golden, 768);
  fc = 1; finished = 1;
  if (trial == 1) {
    if (mode == 4) return AKV_STATUS_EXECUTION;
    if (mode == 5) fc = 8;
    if (mode == 6) vc = 1;
    if (mode == 7) vs = 1;
    if (mode == 8) p->output[0] = 100;
    if (mode == 9) { unsigned b; memcpy(&b,p->output,4); ++b; memcpy(p->output,&b,4); }
    if (mode == 10) ((unsigned char *)w)[sizeof(*w)] ^= 1;
    if (mode == 11) w->accumulator[0][64] ^= 1;
    if (mode == 12) w->score[3][0] = 0;
    if (mode == 13) ((unsigned char *)w)[sizeof(*w)-1] ^= 1;
    if (mode == 14) ((unsigned short *)(unsigned long)p->descriptor.q_base)[0] ^= 1;
    if (mode == 15) ((unsigned short *)decode_key)[16383] ^= 1;
    if (mode == 16) ((unsigned short *)decode_value)[16383] ^= 1;
    if (mode == 17) ((unsigned short *)decode_mask)[255] ^= 1;
    if (mode == 18) ((unsigned char *)decode_golden)[0] ^= 1;
    if (mode == 19) ((unsigned char *)native_golden)[0] ^= 1;
    if (mode == 20) ((unsigned char *)decode_query_f16)[0] ^= 1;
    if (mode == 21) ((unsigned char *)data_guard_before)[0] ^= 1;
    if (mode == 22) ((unsigned char *)p->output)[768] ^= 1;
    if (mode == 23) w->score[0][5] = 0;
    if (mode == 24) w->old_scale[7] = 0;
    if (mode == 25) ((unsigned char *)decode_query)[0] ^= 1;
    if (mode == 26) fc = 2;
    if (mode == 27) w->accumulator[7][255] ^= 1;
    if (mode == 28) ((unsigned short *)(unsigned long)p->descriptor.q_base)[192] ^= 1;
    if (mode == 29 || mode == 30) {
      unsigned value = mode == 29 ? 0x7fc00000 : 0x7f800000; memcpy(p->output,&value,4);
    }
  }
  ++trial;
  return AKV_STATUS_OK;
}
int main(int argc, char **argv) {
  mode = argc > 1 ? (unsigned)atoi(argv[1]) : 0;
  int status = smol_main();
  if (!mode && (trial != 4 || !finished)) return 99;
  return status;
}
'''


class RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='akv_smollm_host_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.blobs, cls.capture_pins, cls.provenance = build.read_capture()
        cls.data = cls.directory/'data'
        cls.data.mkdir()
        for name, blob in cls.blobs.items():
            (cls.data/(name+'.bin')).write_bytes(blob)
        cls.archive = subprocess.check_output(['git', '-C', str(build.ROOT), 'archive',
                                              build.SDK_COMMIT, 'software/akv', 'apps/common'])
        cls.inputs = cls.directory/'inputs'
        cls.inputs.mkdir()
        build.unpack_archive(cls.archive, cls.inputs)
        cls.run_host([build.HOST_CC, '-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off',
                      HERE/'reference.c', '-lm', '-o', cls.directory/'reference'])
        cls.run_host([cls.directory/'reference', cls.data, cls.data/'native_golden.bin'])
        cls.native = (cls.data/'native_golden.bin').read_bytes()
        cls.memory = build.memory_expected(cls.blobs, cls.native)
        cls.text = firmware_log(cls.native, cls.memory)+hardware_log()
        (cls.directory/'expected.h').write_text(build.expected_header(cls.memory))
        (cls.directory/'data.S').write_text(build.data_assembly(cls.data))
        (cls.directory/'stub.c').write_text(HOST_STUB)
        flags = ['-std=gnu11', '-O2', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra', '-Werror',
            '-ffunction-sections', '-fdata-sections', '-I'+str(cls.inputs/'software/akv/include'),
            '-I'+str(cls.inputs/'apps/common'), '-I'+str(cls.directory)]
        cls.run_host([build.HOST_CC, *flags, '-DAKV_SMOL_HOST_TEST', '-Dmain=smol_main',
                      '-c', HERE/'main.c', '-o', cls.directory/'caller.o'])
        cls.run_host([build.HOST_CC, *flags, cls.directory/'caller.o', cls.directory/'data.S',
            cls.directory/'stub.c', cls.inputs/'software/akv/src/akv_runtime.c',
            cls.inputs/'software/akv/src/akv_decode.c', '-Wl,--gc-sections', '-lm', '-o', cls.directory/'caller'])

    @classmethod
    def run_host(cls, argv):
        p = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
        if p.returncode:
            raise AssertionError('Host command failed: '+repr(argv)+'\n'+p.stdout+p.stderr)
        return p.stdout

    def numerical(self, text):
        return check.check_log(text, self.blobs['decode_golden'], self.native, self.memory)

    def manifest_fixture(self, directory):
        """Synthetic ELF/objects exercise receipt gates; never target evidence."""
        inputs, data = directory/'inputs', directory/'data'
        shutil.copytree(self.inputs, inputs)
        shutil.copytree(self.data, data)
        archive = inputs/'sdk-785084122.tar'
        archive.write_bytes(self.archive)
        (directory/'expected.h').write_text(build.expected_header(self.memory))
        (directory/'data.S').write_text(build.data_assembly(data))
        (directory/'link.ld').write_text('HOST RECEIPT FIXTURE ONLY\n')
        elf = directory/'akv_pair_smollm.elf'
        elf.write_bytes(b'\x7fELF HOST FIXTURE NOT EXECUTABLE')
        sdk, common = inputs/'software/akv', inputs/'apps/common'
        sources = [HERE/'main.c', directory/'data.S', *[common/n for n in build.COMMON],
                   *[sdk/'src'/n for n in build.TARGET_SDK]]
        objects, commands = [], []
        for i, source in enumerate(sources):
            obj = directory/('%02d_%s.o' % (i, source.stem))
            obj.write_bytes(b'HOST RECEIPT OBJECT ONLY')
            objects.append(str(obj))
            commands.append(dict(label='compile-'+str(i), returncode=0, cwd=str(directory),
                argv=[str(build.CC), '-march=rv64gcv_zfh_zvfh', '-fno-fast-math', '-ffp-contract=off',
                      '-DAKV_REFILL_OVERLAP=0', '-c', str(source), '-o', str(obj)]))
        commands.append(dict(label='link', returncode=0, cwd=str(directory),
                             argv=[str(build.CC), *objects, '-o', str(elf)]))
        commandfile = directory/'commands.json'
        commandfile.write_text(json.dumps(commands))
        pins = {**self.capture_pins, **{str(HERE/n): build.sha(HERE/n) for n in build.OWN_FILES}}
        for base in (inputs, data):
            pins.update({str(p): build.sha(p) for p in base.rglob('*') if p.is_file()})
        for name in ('expected.h', 'data.S', 'link.ld'):
            pins[str(directory/name)] = build.sha(directory/name)
        pinfile = directory/'source-pins.json'
        pinfile.write_text(json.dumps(pins))
        manifest = dict(schema=build.SCHEMA, state='BUILT_NOT_EXECUTED', target_executed=False,
            rtl_executed=False, performance_measured=False, hardware_changed=False, old_runtime_objects_reused=False,
            sdk_head=build.SDK_COMMIT, sdk_tree=build.SDK_TREE, common_tree=build.COMMON_TREE,
            sdk_unmodified=True, dirty_asm_excluded=True, all_runtime_objects_recompiled=True,
            shape=build.SHAPE, order=build.ORDER, image_contract=build.IMAGE, fixed_image_sha256=build.FIXED_IMAGE_SHA,
            initial_csr=dict(fcsr=0, vcsr=0, vstart=0), environment=dict(AKV_PAIR_HEADS='0/1/1/0 local fixture; all other names NULL'),
            toolchain=dict(target=str(build.CC.resolve()), host=str(build.HOST_CC.resolve()), zcc=False),
            work=dict(per_call_commands=[209, 92, 92, 209], total_commands=602), data=str(data),
            capture=str(build.CAPTURE), provenance=self.provenance, memory_expected=self.memory,
            golden=dict(captured=str(data/'decode_golden.bin'), captured_sha256=build.sha(data/'decode_golden.bin'),
                native_tile64=str(data/'native_golden.bin'), native_tile64_sha256=build.sha(data/'native_golden.bin'),
                capture_atol=0.003, capture_rtol=0.02, native_atol=0.0002, native_rtol=0.003),
            native_reference=dict(source_origin=build.SDK_COMMIT+':'+build.REFERENCE_SOURCE,
                source_sha256=build.REFERENCE_SHA, parameterization='D64/H3/T5/cap256/scale0.125; no backend linked'),
            elf=str(elf), elf_sha256=build.sha(elf), source_pins=str(pinfile), source_pins_sha256=build.sha(pinfile),
            sdk_archive=str(archive), sdk_archive_sha256=build.sha(archive),
            SDKpins={str(p.relative_to(inputs)): build.sha(p) for p in sdk.rglob('*') if p.is_file()},
            objects=objects, objects_recompiled=16, compile_commands=str(commandfile),
            artifacts={str(p): build.sha(p) for p in directory.rglob('*') if p.is_file()})
        self.save_manifest(directory, manifest)
        return manifest

    @staticmethod
    def save_manifest(directory, manifest):
        (directory/'build.json').write_text(json.dumps(manifest, sort_keys=True))

    def test_full_manifest_and_public_apis_without_mocking_identity(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temp:
            directory = Path(temp)
            manifest = self.manifest_fixture(directory)
            self.assertEqual(check.verify_build(directory), manifest)
            log, trace = directory/'completed.log', directory/'vector.csv'
            log.write_text(self.text)
            trace.write_text(vector_csv())
            result = check.check_run(log, directory)
            self.assertEqual(result['state'], 'PASS')
            self.assertEqual(result['output_values_checked'], 768)
            self.assertTrue(check.check_vector_workcounts(trace, directory))

    def test_rehashed_manifest_semantics_cannot_waive_contract(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temp:
            directory = Path(temp)
            manifest = self.manifest_fixture(directory)
            for field, value in [('state', 'PASS'), ('schema', 'other'), ('sdk_head', 'dirty'),
                ('sdk_tree', '0'*40), ('dirty_asm_excluded', False), ('old_runtime_objects_reused', True),
                ('order', [1, 0, 0, 1]), ('fixed_image_sha256', '0'*64), ('objects_recompiled', 15),
                ('provenance', dict(self.provenance, source_receipt_verified=True)),
                ('golden', dict(manifest['golden'], capture_atol=100)),
                ('memory_expected', dict(self.memory, guard_bytes=0))]:
                with self.subTest(field=field):
                    bad = copy.deepcopy(manifest)
                    bad[field] = value
                    self.save_manifest(directory, bad)
                    with self.assertRaises(ValueError): check.verify_build(directory)
            self.save_manifest(directory, manifest)
            commandfile = directory/'commands.json'
            original = commandfile.read_bytes()
            for replacement in ('-ffast-math', '-ffp-contract=fast', '-DAKV_SMOL_HOST_TEST'):
                with self.subTest(command=replacement):
                    commands = json.loads(original)
                    commands[0]['argv'].append(replacement)
                    commandfile.write_text(json.dumps(commands))
                    bad = copy.deepcopy(manifest)
                    bad['artifacts'][str(commandfile)] = build.sha(commandfile)
                    self.save_manifest(directory, bad)
                    with self.assertRaises(ValueError): check.verify_build(directory)
            commandfile.write_bytes(original)
            self.save_manifest(directory, manifest)
            pinfile = directory/'source-pins.json'
            pins = json.loads(pinfile.read_text())
            del pins[str(HERE/'reference.c')]
            pinfile.write_text(json.dumps(pins))
            bad = copy.deepcopy(manifest)
            bad['source_pins_sha256'] = bad['artifacts'][str(pinfile)] = build.sha(pinfile)
            self.save_manifest(directory, bad)
            with self.assertRaises(ValueError): check.verify_build(directory)

    def test_sdk_or_materialized_data_and_object_drift_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temp:
            directory = Path(temp)
            manifest = self.manifest_fixture(directory)
            for p in (directory/'inputs/software/akv/src/akv_v2_attention_rvv.S',
                      directory/'data/decode_key.bin', directory/'data/decode_query.bin',
                      directory/'data/decode_golden.bin', Path(manifest['objects'][-1])):
                with self.subTest(path=p.name):
                    original = p.read_bytes()
                    p.write_bytes(original+b'broken')
                    with self.assertRaises(ValueError): check.verify_build(directory)
                    p.write_bytes(original)

    def test_exact_real_mapping_and_independent_math(self):
        self.assertFalse(self.provenance['source_receipt_verified'])
        self.assertEqual(self.provenance['source_commit_claim'], '316e72d38')
        self.assertLess(self.provenance['mapping_max_abs_error'], 0.00022)
        self.assertEqual(len(self.native), 768)
        self.assertEqual(self.memory['guard_bytes'], 6304)
        self.assertEqual(self.memory['data_bytes'], 68736)
        self.assertEqual(len(self.capture_pins), 13)
        self.assertEqual(hashlib.sha256(self.native).hexdigest(), build.NATIVE_SHA)
        self.assertEqual(self.memory, build.MEMORY)
        self.assertEqual(build.expected_header(self.memory),
                         build.expected_header(dict(reversed(list(self.memory.items())))))
        for name, source in [('decode_query', 'attn_q_input'), ('decode_key', 'attn_k_input'),
                             ('decode_value', 'attn_v_input'), ('decode_golden', 'kqv_out')]:
            self.assertEqual(self.blobs[name], (build.CAPTURE/(source+'-0.bin')).read_bytes()[:len(self.blobs[name])])

    def test_reference_exp_math_matches_frozen_chain_source(self):
        frozen = subprocess.check_output(['git', '-C', str(build.ROOT), 'show',
                                          build.SDK_COMMIT+':'+build.REFERENCE_SOURCE])
        self.assertEqual(hashlib.sha256(frozen).hexdigest(), build.REFERENCE_SHA)
        def exp_math(text):
            first, last = text.index('static float vector_exp'), text.index('static void read_file')
            return re.sub(r'\s+', '', text[first:last])
        self.assertEqual(exp_math(frozen.decode()), exp_math((HERE/'reference.c').read_text()))

    def test_capture_mutations_and_wrong_model_rejected(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as temp:
            root = Path(temp)
            for relative in build.SOURCE_SHA:
                p = root/relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes((build.CAPTURE_ROOT/relative).read_bytes())
            for relative in build.SOURCE_SHA:
                with self.subTest(relative=relative):
                    p = root/relative
                    original = p.read_bytes()
                    p.write_bytes(bytes([original[0] ^ 1])+original[1:])
                    with self.assertRaises(ValueError): build.read_capture(root)
                    p.write_bytes(original)

    def test_cross_kv_or_wrong_golden_not_mathematically_accepted(self):
        blobs = dict(self.blobs)
        blobs['decode_golden'] = bytes(768)
        with self.assertRaises(ValueError): build.mathematical_crosscheck(blobs)

    def test_no_cross_build_before_seal_ready(self):
        with patch.object(build.subprocess, 'run', side_effect=AssertionError('Unexpected command')), \
             patch.object(build.subprocess, 'check_output', side_effect=AssertionError('Unexpected git/EDA')):
            with self.assertRaisesRegex(ValueError, 'seal-ready'): build.build()

    def test_archive_safety(self):
        for name, type_ in [('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE), ('alias', tarfile.SYMTYPE)]:
            with self.subTest(name=name, type=type_):
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode='w') as archive:
                    item = tarfile.TarInfo(name)
                    item.type = type_
                    archive.addfile(item)
                with self.assertRaises(ValueError): build.unpack_archive(stream.getvalue(), self.directory)

    def test_real_sdk_host_caller_and_every_firmware_failure(self):
        text = self.run_host([self.directory/'caller'])+hardware_log()
        self.assertEqual(self.numerical(text)['output_values_checked'], 768)
        for mode in range(1, 31):
            with self.subTest(mode=mode):
                p = subprocess.run([str(self.directory/'caller'), str(mode)], capture_output=True, text=True, timeout=5)
                self.assertEqual(p.returncode, 1, p.stdout[-600:]+p.stderr)
                with self.assertRaises(ValueError): self.numerical(p.stdout+hardware_log())

    def test_negative_speedup_is_valid_and_ratios_correct(self):
        result = self.numerical(self.text)
        self.assertEqual(result['measured_total_cycles'], [10000, 12000, 13000, 11000])
        self.assertAlmostEqual(result['generic_over_candidate'], 10500/12500)
        self.assertLess(result['cycle_reduction_fraction'], 0)
        self.assertFalse(result['performance_acceptance'])

    def test_every_output_head_and_trial_checked(self):
        for t in range(4):
            for i in (0, 63, 64, 127, 128, 191):
                with self.subTest(trial=t, index=i):
                    word = struct.unpack('<192I', self.native)[i]
                    old = 'AKV_SMOL_OUT trial=%d index=%d bits=%08x' % (t, i, word)
                    new = 'AKV_SMOL_OUT trial=%d index=%d bits=%08x' % (t, i, word ^ 1)
                    with self.assertRaises(ValueError): self.numerical(self.text.replace(old, new, 1))

    def test_nonfinite_and_common_wrong_outputs_rejected(self):
        for native in (struct.pack('<192I', *([0x7fc00000]*192)), bytes(768)):
            with self.subTest(native=native[:4]):
                with self.assertRaises(ValueError): self.numerical(firmware_log(native, self.memory)+hardware_log())

    def test_record_schema_timing_csr_payload_and_eoc_rejected(self):
        mutations = [('fcsr=1', 'fcsr=2'), ('vcsr=0', 'vcsr=1'), ('vstart=0', 'vstart=1'),
            ('initial_fcsr=0', 'initial_fcsr=1'), ('groups=1', 'groups=0'), ('arm=1', 'arm=0'),
            ('begin=100 ', 'begin=0 '), ('returned=10090', 'returned=10100'),
            ('guard_bytes=6304', 'guard_bytes=6303'), ('errors=0', 'errors=1'),
            ('tokens=5', 'tokens=6'), ('data_bytes=68736', 'data_bytes=68735'),
            ('tohost = 0', 'tohost = 1'), ('UVM_ERROR : 0', 'UVM_ERROR : 1'),
            ('UVM_ERROR : 0', 'UVM_ERROR x : 0'), ('UVM_ERROR : 0', 'UVM_ERROR : 0\nUVM_ERROR : 0'),
            ('AKV_SMOL_DONE trials=4 errors=0', 'AKV_SMOL_DONE trials=4 errors=0 extra=0')]
        for old, new in mutations:
            with self.subTest(mutation=(old, new)):
                self.assertIn(old, self.text)
                with self.assertRaises(ValueError): self.numerical(self.text.replace(old, new, 1))
        for key in ('data_hash', 'query_f32_hash', 'key_hash', 'value_hash', 'mask_hash', 'query_hash', 'guard_hash'):
            with self.subTest(hash=key):
                old = '%s=%016x' % (key, self.memory[key])
                with self.assertRaises(ValueError): self.numerical(self.text.replace(old, key+'=0000000000000000', 1))
        for suffix in ('Fatal: simulated', 'Error: simulated', 'timeout', 'AKV_SMOL_FAIL reason=1'):
            with self.subTest(suffix=suffix):
                with self.assertRaises(ValueError): self.numerical(self.text+suffix+'\n')

    def test_missing_duplicate_reordered_raw_records(self):
        lines = self.text.splitlines()
        index = next(i for i, s in enumerate(lines) if s.startswith('AKV_SMOL_OUT '))
        for modified in (lines[:index]+lines[index+1:], lines[:index]+[lines[index]]+lines[index:],
                         lines[:index]+[lines[index+1], lines[index]]+lines[index+2:]):
            with self.assertRaises(ValueError): self.numerical('\n'.join(modified))

    def test_native_work_and_odd_tail_exact(self):
        result = check.check_hardware_work(self.text)
        self.assertEqual(result['per_call_commands'], [209, 92, 92, 209])
        self.assertEqual(result['commands'], 602)
        self.assertEqual(result['totals']['replay_bytes'], 2*3840+2*2560)
        self.assertEqual(result['calls'][1]['k_single_commands'], 64)

    def test_each_native_fault_work_and_summary_gate(self):
        for index, key in [(0, 'q_external_bytes'), (0, 'kv_external_bytes'), (0, 'read_ranges'),
            (0, 'read_payload_bytes'), (1, 'v2_logical_column'), (1, 'replay_bytes'), (1, 'seq'),
            (1, 'v2_bank_conflict_cycles'), (1, 'v2_k_view_bank_cycles'), (193, 'v2_row_load'),
            (210, 'v2_column_panel'), (226, 'v2_column_panel'), (290, 'replay_bytes')]:
            with self.subTest(index=index, key=key):
                rows = command_rows()
                rows[index][key] += 1
                with self.assertRaises(ValueError): check.check_hardware_work(hardware_log(rows))
        for key in ('fault', 'validation_fault', 'validation_error', 'read_fault', 'v2_rejected', 'success', 'context_ready'):
            with self.subTest(key=key):
                rows = command_rows()
                rows[211][key] ^= 1
                with self.assertRaises(ValueError): check.check_hardware_work(hardware_log(rows))
        for rows in (command_rows()[:-1], command_rows()+[command_rows()[-1]]):
            with self.assertRaises(ValueError): check.check_hardware_work(hardware_log(rows))
        text = hardware_log()
        summary = next(s for s in text.splitlines() if s.startswith('[AKV_PERF_SUMMARY]'))
        for bad in (text.replace(summary, ''), text+'\n'+summary, text.replace('records=602', 'records=603')):
            with self.assertRaises(ValueError): check.check_hardware_work(bad)

    def test_vector_independent_d64_signatures_order_and_dimension(self):
        trace = self.directory/'vector.csv'
        with patch.object(check, 'verify_build', return_value=dict(elf_sha256='host-fixture-only')):
            trace.write_text(vector_csv())
            self.assertEqual(check.check_vector_workcounts(trace, self.directory)['replay_commands'], 594)
            for old, new in [('0005345b', '0205345b'), ('0205745b', '0005745b'),
                             (',4,1024', ',4,512'), ('0,config', '0,reset')]:
                with self.subTest(mutation=(old, new)):
                    trace.write_text(vector_csv().replace(old, new, 1))
                    with self.assertRaises(ValueError): check.check_vector_workcounts(trace, self.directory)
            values = check.expected_vector_signatures()
            for bad in (values[:-1], values+[0x0005345b], [values[-1], *values[:-1]]):
                trace.write_text(vector_csv(bad))
                with self.assertRaises(ValueError): check.check_vector_workcounts(trace, self.directory)

    def test_public_api_schema_and_busy_roi(self):
        log = self.directory/'synthetic.log'
        log.write_text(self.text)
        manifest = dict(golden=dict(captured=str(self.data/'decode_golden.bin'),
            native_tile64=str(self.data/'native_golden.bin')), memory_expected=self.memory,
            provenance=self.provenance, image_contract=build.IMAGE, fixed_image_sha256=build.FIXED_IMAGE_SHA,
            elf_sha256='host-fixture-only', source_pins_sha256='host-fixture-only')
        (self.directory/'build.json').write_text('{}')
        with patch.object(check, 'verify_build', return_value=manifest):
            result = check.check_run(log, self.directory)
            self.assertEqual(result['state'], 'PASS')
            self.assertEqual(result['order'], [0, 1, 1, 0])
            self.assertEqual(result['work']['per_call_commands'], [209, 92, 92, 209])
            self.assertEqual(len(result['measured_total_cycles']), 4)
            slow = command_rows()
            slow[0]['busy_cycles'] = 1000000
            log.write_text(firmware_log(self.native, self.memory)+hardware_log(slow))
            with self.assertRaises(ValueError): check.check_run(log, self.directory)


if __name__ == '__main__':
    unittest.main()
