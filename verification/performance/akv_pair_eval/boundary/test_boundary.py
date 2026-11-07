#!/usr/bin/env python3
"""Host-only source/data and adversarial checker fixtures. No target or RTL PASS evidence."""
from collections import Counter
import csv
import importlib.util
import io
import json
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
_spec = importlib.util.spec_from_file_location('boundary_checker_hosttests', HERE / 'check.py')
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)
b = check.contract


def payload_lines():
    return [f'AKV_BOUNDARY_PAYLOAD name={n} bytes={p["bytes"]} fnv={p["fnv64"]:016x} '
            f'expected={p["fnv64"]:016x} errors=0' for n, p in b.PAYLOADS.items()] + [
                'AKV_BOUNDARY_DONE body=0 checks=3 errors=0']


def log_fixture(r):
    lines, records = [r.CAP], []
    for i, case in enumerate(r.CASES):
        for trial in range(3):
            lines.append(r.begin(i, trial))
            for item in r.work(case, trial == 1):
                row = dict.fromkeys(r.s.PERF_FIELDS, 0)
                row.update(r.expected_record(case, item, len(records) + 1))
                row.update(id=0, busy_cycles=10)
                if item[0] in (4, 5):
                    row.update(ar=row['read_ranges'], r_beats=2000, read_outstanding_max=2)
                records.append(row)
                lines.append('[AKV_PERF] ' + ' '.join(f'{k}={v}' for k, v in row.items()))
            lines.append(f'NATIVE_PAIR_RESULT case={i} trial={trial} requested={int(trial == 1)} '
                         f'outputs={case["d"] * case["heads"]} compared=4096 '
                         'hash=0123456789abcdef fcsr=3 vcsr=5 errors=0')
    lines += [r.SUITE, *payload_lines(), r.s.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0']
    lines.append('[AKV_PERF_SUMMARY] ' + ' '.join(f'{k}={v}' for k, v in r.s.totals(records).items()))
    return '\n'.join(lines) + '\n'


def vector_fixture(words=None):
    words = [w for c in check.expected_vector_calls() for w in c] if words is None else words
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow('cycle event arch_seq insn nr_lanes vlen_bits'.split())
    writer.writerow([0, 'config', 0, '00000000', 4, 1024])
    for seq, word in enumerate(words, 1):
        writer.writerow([seq, 'alloc', seq, f'{word:08x}', 4, 1024])
    return out.getvalue()


def elf_fixture():
    """Synthetic ELF structure only: deliberately not executable/RTL evidence."""
    names = sorted({'_start', 'main', 'boundary_body', 'akv_device_query',
                    'akv_attention_plan_create_v2', 'akv_attention_execute_v2_native',
                    'getenv', *check.FUNCTION_WORDS})
    offsets = {n: 0x1000 + i * 128 for i, n in enumerate(names)}
    base = 0x80000000
    edges = {'main': ['boundary_body'], 'boundary_body': ['akv_device_query',
             'akv_attention_plan_create_v2', 'akv_attention_execute_v2_native'],
             'akv_attention_execute_v2_native': ['akv_attention_execute_v2_with_features_native']}
    text = bytearray(b'\x01\x00' * (len(names) * 64))
    symbols = []
    for n in names:
        code = bytearray(b''.join(struct.pack('<I', w) for w in check.FUNCTION_WORDS.get(n, [])))
        for target in edges.get(n, []):
            delta = offsets[target] - (offsets[n] + len(code))
            high = (delta + 0x800) >> 12
            low = delta - (high << 12)
            code += struct.pack('<II', (high & 0xfffff) << 12 | (6 << 7) | 0x17,
                                (low & 0xfff) << 20 | (6 << 15) | 0x67)
        code += struct.pack('<I', 0x00008067)
        off = offsets[n] - 0x1000
        text[off:off + len(code)] = code
        symbols.append((n, 0x12, 1, base + offsets[n], len(code)))
    ro_offset = (0x1000 + len(text) + 63) & ~63
    rodata = bytearray()
    for p in b.PAYLOADS.values():
        raw = (b.CAPTURE / (p['role'] + '-0.bin')).read_bytes()
        symbols.append((p['symbol'], 0x11, 2, base + ro_offset + len(rodata), len(raw)))
        rodata += raw
    strings, symtab = bytearray(b'\0'), bytearray(24)
    for name, info, section, addr, size in symbols:
        symtab += struct.pack('<IBBHQQ', len(strings), info, 0, section, addr, size)
        strings += name.encode() + b'\0'
    load_end = ro_offset + len(rodata)
    symoff = (load_end + 7) & ~7
    stroff = symoff + len(symtab)
    shoff = (stroff + len(strings) + 7) & ~7
    raw = bytearray(shoff + 5 * 64)
    ident = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<16sHHIQQQIHHHHHH', raw, 0, ident, 2, 243, 1,
                     base + offsets['_start'], 64, shoff, 5, 64, 56, 1, 64, 5, 0)
    struct.pack_into('<IIQQQQQQ', raw, 64, 1, 5, 0, base, base, load_end, load_end, 4096)
    raw[0x1000:0x1000 + len(text)] = text
    raw[ro_offset:load_end] = rodata
    raw[symoff:symoff + len(symtab)] = symtab
    raw[stroff:stroff + len(strings)] = strings
    sections = [(0,) * 10,
                (0, 1, 6, base + 0x1000, 0x1000, len(text), 0, 0, 4, 0),
                (0, 1, 2, base + ro_offset, ro_offset, len(rodata), 0, 0, 64, 0),
                (0, 2, 0, 0, symoff, len(symtab), 4, 1, 8, 24),
                (0, 3, 0, 0, stroff, len(strings), 0, 0, 1, 0)]
    for i, section in enumerate(sections):
        struct.pack_into('<IIQQQQIIQQ', raw, shoff + i * 64, *section)
    return bytes(raw)


class BoundaryHostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='.host-boundary-', dir=HERE)
        cls.directory = Path(cls.temp.name)
        cls.inputs = cls.directory / 'inputs'
        cls.inputs.mkdir()
        cls.archive = subprocess.check_output([str(b.GIT), '-C', str(b.ROOT), 'archive',
                                               b.SDK_COMMIT, *b.ARCHIVE_PATHS])
        if b.hashlib.sha256(cls.archive).hexdigest() != b.ARCHIVE_SHA:
            raise ValueError('Hosttest exact git archive drift')
        b.unpack_archive(cls.archive, cls.inputs)
        cls.legacy = check.load_legacy(cls.inputs)
        cls.log = log_fixture(cls.legacy)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_no_unsealed_crossbuild(self):
        with mock.patch.object(b.subprocess, 'run') as run, self.assertRaisesRegex(ValueError, 'seal-ready'):
            b.build()
        run.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'GNU target'):
            b.build(b.OUT / 'akv_pair_boundary_build_29990101_hosttest',
                    cc=b.HOST_CC, seal_ready=True)

    def test_exact_archive_and_original_helpers(self):
        self.assertEqual(len(b.compile_recipe(self.directory)), 16)
        self.assertEqual(b.sha(self.inputs / b.HARNESS), b.LEGACY[b.HARNESS])
        self.assertEqual(b.archive_members(self.archive)[b.HARNESS],
                         (self.inputs / b.HARNESS).read_bytes())
        for n, digest in b.LEGACY.items():
            self.assertEqual(b.sha(self.inputs / n), digest)
        for argv in b.compile_recipe(self.directory):
            self.assertEqual(argv[0], str(b.CC))
            self.assertIn('-DAKV_REFILL_OVERLAP=0', argv)
            self.assertNotIn('SPIKE', ' '.join(argv))
        self.assertTrue(all(str(b.ROOT / 'software') not in ' '.join(c)
                            for c in b.compile_recipe(self.directory)))

    def test_import_isolation_and_hash_gate(self):
        previous = sys.modules.get('attention_run')
        sentinel = types.ModuleType('attention_run')
        sys.modules['attention_run'] = sentinel
        paths = sys.path[:]
        try:
            loaded = check.load_legacy(self.inputs)
            self.assertIs(sys.modules['attention_run'], sentinel)
            self.assertEqual(sys.path, paths)
            self.assertIsNot(loaded.s, sentinel)
        finally:
            if previous is None:
                sys.modules.pop('attention_run', None)
            else:
                sys.modules['attention_run'] = previous
        with mock.patch.object(b, 'LEGACY', {**b.LEGACY,
              'verification/akv/paired_heads/native_runtime_check.py': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'identity'):
                check.load_legacy(self.inputs)

    def test_data_identity_and_metadata(self):
        pins = b.validate_data()
        self.assertEqual(len(pins), 9)
        self.assertEqual(sum(p['bytes'] for p in b.PAYLOADS.values()), 268288)
        for p in b.PAYLOADS.values():
            data = (b.CAPTURE / (p['role'] + '-0.bin')).read_bytes()
            self.assertEqual(b.fnv64(data), p['fnv64'])
        self.assertEqual(b.fnv64(b''), 0xcbf29ce484222325)
        self.assertEqual(b.fnv64(b'a'), 0xaf63dc4c8601ec8c)
        self.assertEqual(b.fnv64(b'foobar'), 0x85944171f73967e8)

    def test_payload_tail_and_metadata_mutations(self):
        with tempfile.TemporaryDirectory(dir=self.directory) as tmp:
            cap = Path(tmp)
            for p in b.PAYLOADS.values():
                for suffix in ('.bin', '.json'):
                    name = p['role'] + '-0' + suffix
                    shutil.copyfile(b.CAPTURE / name, cap / name)
            for role in ('q', 'k', 'v'):
                path = cap / (b.PAYLOADS[role]['role'] + '-0.bin')
                original = path.read_bytes()
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                with self.subTest(tail=role), self.assertRaises(ValueError):
                    b.validate_data(cap)
                path.write_bytes(original)
            path = cap / 'attn_k_input-0.json'
            meta = json.loads(path.read_text())
            meta['strides'][2] += 256
            path.write_text(json.dumps(meta))
            with self.assertRaises(ValueError):
                b.validate_data(cap)

    def test_original_checker_and_payload_records(self):
        original = self.legacy.check_log(self.log)
        self.assertEqual([t['hardware_totals']['records'] for t in original['trials']], b.CALL_COMMANDS)
        self.assertEqual(original['raw_hardware_summary']['records'], 3680)
        self.assertEqual(set(check.check_payload_log(self.log, self.legacy)), {'q', 'k', 'v'})
        self.assertFalse(any('NATIVE_PAIR' in x or 'FAIL' in x for x in payload_lines()))

    def test_log_mutations_rejected(self):
        text = self.log
        changes = [('errors=0', 'errors=1'), ('fcsr=3', 'fcsr=2'), ('vcsr=5', 'vcsr=0'),
                   ('compared=4096', 'compared=2048'), ('requested=1', 'requested=0'),
                   ('hash=0123456789abcdef', 'hash=1123456789abcdef'),
                   ('v2_column_panel=1', 'v2_column_panel=0'), ('read_ranges=6', 'read_ranges=5'),
                   ('command=4', 'command=5'), ('success=1', 'success=0'),
                   ('UVM_ERROR : 0', 'UVM_ERROR : 1'), (self.legacy.s.TERMINAL, ''),
                   ('bytes=131072', 'bytes=65536'), ('name=k', 'name=q'),
                   ('fnv=afefa3ea4b06654c', 'fnv=bfefa3ea4b06654c'),
                   ('expected=afefa3ea4b06654c', 'expected=bfefa3ea4b06654c'),
                   ('body=0', 'body=1'), ('checks=3', 'checks=2')]
        for old, new in changes:
            self.assertIn(old, text)
            with self.subTest(field=old), self.assertRaises(ValueError):
                bad = text.replace(old, new, 1)
                self.legacy.check_log(bad)
                check.check_payload_log(bad, self.legacy)
        extra = payload_lines()[0]
        wrong = [text + extra + '\n', text.replace(extra + '\n', '', 1),
                 extra + '\n' + text.replace(extra + '\n', '', 1),
                 text.replace(extra, 'prefix ' + extra), text + 'Error-[BROKEN]\n']
        for bad in wrong[:-1]:
            with self.subTest(kind='record placement'), self.assertRaises(ValueError):
                self.legacy.check_log(bad)
                check.check_payload_log(bad, self.legacy)

    def test_check_run_api_preserves_unfiltered_text(self):
        path = self.directory / 'fixture.log'
        path.write_text(self.log)
        info = dict(elf_sha256='fixture-only', source_pins_sha256='fixture-only',
                    elf_link_checks=dict(fixture_only=True))
        # Bypass build admission only to unit-test the log API. This is not an RTL run.
        with mock.patch.object(check, 'verify_build', return_value=info), \
             mock.patch.object(check, 'load_legacy', return_value=self.legacy), \
             mock.patch.object(self.legacy, 'check_log', wraps=self.legacy.check_log) as original:
            result = check.check_run(path, self.directory)
            original.assert_called_once_with(self.log)
            self.assertEqual(result['state'], 'PASS')
            self.assertFalse(result['performance_measured'])
            self.assertFalse(result['independent_protocol_checked'])
        path.write_text(self.log + 'Error-[BROKEN]\n')
        with mock.patch.object(check, 'verify_build', return_value=info), self.assertRaises(ValueError):
            check.check_run(path, self.directory)

    def test_independent_vector_formulas(self):
        calls = check.expected_vector_calls()
        counts = Counter(check.SIGNATURE_NAMES[w] for c in calls for w in c)
        self.assertEqual(counts, check.EXPECTED_COUNTS)
        self.assertEqual([len(c) for c in calls], b.CALL_COMMANDS)
        path = self.directory / 'vector.csv'
        path.write_text(vector_fixture())
        result = check.vector_workcounts(path)
        self.assertEqual((result['panel_commands'], result['column_commands']), (96, 2688))
        self.assertEqual((result['d64_commands'], result['d96_commands'], result['d128_commands']),
                         (8, 520, 341))
        self.assertEqual(result['lifecycle_commands'], 27)
        self.assertEqual(result['native_commands'], 3680)
        self.assertEqual(result['replay_commands'], 3653)
        with mock.patch.object(check, 'verify_build', return_value=dict(
                elf_sha256='fixture-only', source_pins_sha256='fixture-only')):
            self.assertTrue(check.check_vector_workcounts(path, self.directory))

    def test_vector_signature_and_schema_mutations(self):
        path = self.directory / 'vector_bad.csv'
        text = vector_fixture()
        rows = text.splitlines()
        bads = [text.replace('4,1024', '4,512', 1), text.replace('00b5605b', '02a0605b', 1),
                text.replace('0405345b', '0205345b', 1), text.replace('0205375b', '0205345b', 1),
                text.replace('000574db', '0005745b', 1), text.replace('0205745b', '0005745b', 1),
                text.replace('0000505b', '0005455b', 1), text.replace('alloc', 'reset', 1),
                '\n'.join(rows[:-1]) + '\n', text + rows[-1] + '\n',
                '\n'.join([rows[0], rows[1], *rows[1:]]) + '\n',
                text.replace('cycle,event', 'cycle,cycle', 1),
                text.replace('0005745b', 'XXXXXXXX', 1)]
        for i, bad in enumerate(bads):
            path.write_text(bad)
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                check.vector_workcounts(path)

    def test_actual_elf_structure_link_and_signatures(self):
        path = self.directory / 'synthetic-only.elf'
        original = elf_fixture()
        path.write_bytes(original)
        self.assertTrue(check.check_elf(path)['knowncall_signatures_checked'])
        syms = check.elf_contents(path)
        offsets = [syms[p['symbol']]['offset'] + p['bytes'] - 1 for p in b.PAYLOADS.values()]
        offsets += [syms['main']['offset'], syms['akv_experimental_qk_f16_pair_panel4']['offset'],
                    syms['akv_v2_update_outputs_f16_d128_gqa6']['offset']]
        for offset in offsets:
            bad = bytearray(original)
            bad[offset] ^= 0x20
            path.write_bytes(bad)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                check.check_elf(path)
        for offset in (4, 5, 18, 48):
            bad = bytearray(original)
            bad[offset] ^= 0x20
            path.write_bytes(bad)
            with self.subTest(header=offset), self.assertRaises(ValueError):
                check.check_elf(path)

    def test_wrapper_host_fnv_and_nonzero_body(self):
        # Host-compiled wrapper with an explicit stub body, not a mock target/RTL PASS.
        self.assertEqual(b.sha(b.HOST_CC), b.HOST_CC_SHA)
        host = self.directory / 'host_wrapper'
        host.mkdir(exist_ok=True)
        (host / 'expected.h').write_text(b.expected_header())
        for p in b.PAYLOADS.values():
            shutil.copyfile(b.CAPTURE / (p['role'] + '-0.bin'), host / (p['role'] + '-0.bin'))
        (host / 'data.S').write_text(b.data_assembly(host))
        header = ('#include <stdio.h>\nextern const float candidate_query_f32[];\n'
                  'extern const unsigned short candidate_key[], candidate_value[];\n'
                  'int main(void) { return BODY_STATUS; }\n')
        (host / 'native_runtime_main.c').write_text(header)
        for body, mutated in ((0, False), (7, False), (0, True)):
            if mutated:
                path = host / 'attn_v_input-0.bin'
                value = path.read_bytes()
                path.write_bytes(value[:-1] + bytes([value[-1] ^ 1]))
            proc = subprocess.run([str(b.HOST_CC), '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                '-DBODY_STATUS=' + str(body), '-I' + str(host), str(HERE / 'main.c'),
                str(host / 'data.S'), '-o', str(host / 'wrapper')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            proc = subprocess.run([str(host / 'wrapper')], capture_output=True, text=True)
            self.assertEqual(proc.returncode, int(body != 0 or mutated))
            self.assertEqual(sum(line.startswith('AKV_BOUNDARY_PAYLOAD ') for line in proc.stdout.splitlines()), 3)
            if not body and not mutated:
                self.assertEqual(proc.stdout.splitlines(), payload_lines())
            else:
                self.assertIn(f'AKV_BOUNDARY_DONE body={body} checks=3 errors=1', proc.stdout)

    def test_fail_closed_build_api_and_json(self):
        target = self.directory / 'bad_build'
        target.mkdir(exist_ok=True)
        (target / 'build.json').write_text(json.dumps(dict(state='PASS', performance_measured=True)))
        with self.assertRaisesRegex(ValueError, 'contract'):
            check.verify_build(target)
        (target / 'dup.json').write_text('{"sha":1,"sha":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            b.read_json(target / 'dup.json')
        source = (HERE / 'main.c').read_text()
        self.assertIn('#define main boundary_body\n#include "native_runtime_main.c"\n#undef main', source)
        self.assertIn('const volatile unsigned char *p', source)
        self.assertIn('return errors != 0;', source)

    def test_build_receipt_and_sourcepin_rejection(self):
        target = self.directory / 'receipt_negatives'
        target.mkdir(exist_ok=True)
        # Satisfy only the metadata gate to exercise missing/changed mandatory pins.
        # These are deliberately incomplete receipts, never build acceptance.
        m = dict(schema=1, kind='boundary', state='BUILT_NOT_EXECUTED', execution='NOT_RUN',
            target_executed=False, rtl_executed=False, performance_measured=False, seal_ready=True,
            post_pins_match=True, sdk_head=b.SDK_COMMIT, sdk_tree=b.SDK_TREE, common_tree=b.COMMON_TREE,
            sdk_unmodified=True, dirty_asm_excluded=True, all_runtime_objects_recompiled=True,
            cases=b.CASES, order=b.ORDER, runs=12, expected_commands=3680,
            per_call_commands=b.CALL_COMMANDS, image_contract=b.IMAGE, capture=str(b.CAPTURE),
            payloads=b.PAYLOADS, original_data_receipt=str(b.ORIGIN),
            toolchain=dict(target=str(b.CC), host=str(b.HOST_CC), zcc=False))
        elf, pinfile = target / 'akv_pair_boundary.elf', target / 'source-pins.json'
        elf.write_bytes(elf_fixture())
        pinfile.write_text(json.dumps({str(elf): b.sha(elf)}))
        m.update(elf=str(elf), elf_sha256=b.sha(elf), source_pins=str(pinfile),
                 source_pins_sha256=b.sha(pinfile), artifacts={str(elf): b.sha(elf)})
        b.save(target / 'build.json', m)
        with self.assertRaisesRegex(ValueError, 'mandatory source/data pin'):
            check.verify_build(target)
        original_pins = pinfile.read_bytes()
        pinfile.write_bytes(original_pins + b'\n')
        with self.assertRaisesRegex(ValueError, 'inventory identity'):
            check.verify_build(target)
        pinfile.write_bytes(original_pins)
        for key, value in [('sdk_head', 'dirty'), ('performance_measured', True),
                           ('expected_commands', 3653), ('order', [0, 1, 1, 0]),
                           ('capture', str(target)), ('dirty_asm_excluded', False)]:
            changed = dict(m, **{key: value})
            b.save(target / 'build.json', changed)
            with self.subTest(field=key), self.assertRaisesRegex(ValueError, 'contract mismatch'):
                check.verify_build(target)
        b.save(target / 'build.json', m)
        elf.write_bytes(elf.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'inventory identity'):
            check.verify_build(target)


if __name__ == '__main__':
    unittest.main()
