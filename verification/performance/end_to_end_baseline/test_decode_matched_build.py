from pathlib import Path
import json
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

import build_decode_matched as b
from audit import digest


def recipes():
    rvv = ['/cc', '-static', '-nostdlib', *[str(b.BUILD / f'compiled-{i}.o') for i in range(6)],
           str(b.BASE / '1.o'), *[str(b.COMMON / f'{i}.o') for i in range(3, 9)],
           '-Wl,--gc-sections', '-Wl,-Map=old.map', '-T', '/frozen/link.ld',
           '-Wl,--start-group', '-lstdc++', '-lm', '-lc', '-lgcc', '-lnosys', '-Wl,--end-group', '-o', 'old.elf']
    sdk = ['/cc', *[str(b.COMMON / f'{i}.o') for i in range(3, 11)],
           *[str(b.BASE / f'{i}.o') for i in range(3)], '-o', 'sdk.elf']
    return rvv, sdk


def executable(text):
    data = bytearray(256 + len(text))
    struct.pack_into('<16sHHIQQQIHHHHHH', data, 0, b'\x7fELF\x02\x01' + bytes(10),
                     2, 243, 1, 0x80000000, 0, 64, 0, 64, 56, 0, 64, 2, 0)
    struct.pack_into('<IIQQQQIIQQ', data, 128, 0, 1, 6, 0x80000000, 256, len(text), 0, 0, 2, 0)
    data[256:] = text
    return bytes(data)


class DecodeMatchedBuildTests(unittest.TestCase):
    def test_reuses_numeric_objects_exactly_once_and_only_adds_sdk_runtime(self):
        rvv, sdk = recipes()
        result = b.reused_objects(rvv, sdk)
        self.assertEqual(len(result), 14)
        self.assertEqual(result[-2:], [str(b.COMMON / '9.o'), str(b.COMMON / '10.o')])
        for forbidden in (b.BUILD / 'compiled-0.o', b.BASE / '0.o', b.BASE / '2.o'):
            self.assertNotIn(str(forbidden), result)
        self.assertEqual(result.count(str(b.BASE / '1.o')), 1)
        self.assertIn(str(b.BUILD / 'compiled-5.o'), result)

    def test_link_preserves_every_non_object_option_except_output_and_map(self):
        rvv, sdk = recipes(); saved = rvv.copy()
        link = b.matched_link(rvv, sdk, '/new/driver.o', '/new/data.o', '/new/app.elf', '/new/link.map')
        self.assertEqual(rvv, saved)
        self.assertEqual(len(b.objects(link)), 16)
        without_objects = lambda command: [v for v in command if not v.endswith('.o')]
        expected = [v.replace('old.map', '/new/link.map').replace('old.elf', '/new/app.elf')
                    for v in without_objects(rvv)]
        self.assertEqual(without_objects(link), expected)

    def test_rejects_extra_duplicate_missing_or_reordered_producer_objects(self):
        rvv, sdk = recipes()
        for left, right in ((rvv + ['/evil.o'], sdk), (rvv + [str(b.BASE / '1.o')], sdk),
                            ([v for v in rvv if v != str(b.BUILD / 'compiled-5.o')], sdk),
                            (rvv, sdk + ['/extra.o']), (rvv, list(reversed(sdk)))):
            with self.assertRaises(ValueError): b.reused_objects(left, right)

    def test_sdk_compile_recipe_changes_only_source_output(self):
        recipe = ['/frozen/g++', '-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-mcmodel=medany',
                  '-mno-relax', '-O3', '-fno-fast-math', '-ffp-contract=off', '-Werror',
                  '-I/frozen/sdk/include', '-c', 'old.cpp', '-o', 'old.o']
        actual = b.compile_recipe(recipe, 'matched.cpp', 'matched.o')
        self.assertEqual(actual, [v.replace('old.cpp', 'matched.cpp').replace('old.o', 'matched.o') for v in recipe])
        for missing in ('-fno-fast-math', '-ffp-contract=off', '-Werror', '-march=rv64gcv_zfh_zvfh'):
            with self.assertRaises(ValueError): b.compile_recipe([v for v in recipe if v != missing], 'x', 'y')
        with self.assertRaises(ValueError): b.compile_recipe(recipe + ['-DGGML_USE_RISCV_QBS'], 'x', 'y')

    def test_data_has_only_native_weights_isa_expected_and_flags(self):
        symbols = b.data_symbols(); text = b.assembly(symbols)
        self.assertEqual(len(symbols), 15)
        self.assertEqual(text.count('.incbin '), 15)
        self.assertEqual(text.count('.balign 64'), 15)
        self.assertEqual(dict(symbols)['native_decode_weights_5'], b.BASE / 'part_5_r4.bin')
        self.assertEqual(dict(symbols)['rvv_decode_expected_1'], b.ISA / 'isa_output_1.bin')
        for old_symbol in ('decode_input_0:', 'decode_profiles:', 'decode_expected_0:', 'decode_quantized_0:', 'decode_weights_0:'):
            self.assertNotIn('\n' + old_symbol, text)
        with self.assertRaises(ValueError): b.assembly(symbols + [('decode_input_0', Path('/x'))])
        with self.assertRaises(ValueError): b.assembly([(symbols[0][0], Path('/bad"path')), *symbols[1:]])

    def test_checker_oracle_inventory_and_exact_source_copy(self):
        sources = b.oracle_sources()
        self.assertEqual(len(sources), 19)
        self.assertEqual(sources['native_0.bin'], b.BASE / 'part_0_expected.bin')
        self.assertEqual(sources['rvv_0.bin'], b.ISA / 'isa_output_0.bin')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'original.bin'; source.write_bytes(bytes(range(256)) * 2)
            pins = {str(source): digest(source)}
            with patch.object(b, 'oracle_sources', return_value={'native_0.bin': source}):
                copied = b.copy_oracles(root / 'oracle', pins)
            target = root / 'oracle/native_0.bin'
            self.assertEqual(target.read_bytes(), source.read_bytes()[:256])
            self.assertNotEqual(pins[str(target)], pins[str(source)])
            self.assertEqual(copied['native_0.bin']['source_sha256'], digest(source))
            self.assertEqual(copied['native_0.bin']['sha256'], digest(target))
            self.assertEqual((copied['native_0.bin']['source_bytes'], copied['native_0.bin']['bytes']), (512, 256))
            with patch.object(b, 'oracle_sources', return_value={'native_0.bin': source}):
                with self.assertRaises(ValueError): b.copy_oracles(root / 'unpinned', {})

    def test_output_oracles_are_prefixes_but_activations_and_flags_are_unchanged(self):
        data = bytes(range(256)) * 2
        for kind in ('native', 'rvv'):
            for part in range(7):
                self.assertEqual(b.oracle_payload(f'{kind}_{part}.bin', data), data[:256])
            for bad in (data[:256], data[:-1], data + b'x'):
                with self.assertRaises(ValueError): b.oracle_payload(f'{kind}_0.bin', bad)
        for stage, length in enumerate((2336, 2336, 7008, 2336)):
            raw = bytes([stage]) * length
            self.assertEqual(b.oracle_payload(f'activation_{stage}.bin', raw), raw)
        flags = struct.pack('<7I', 0, 1, 0, 1, 1, 0, 1)
        self.assertEqual(b.oracle_payload('flags.bin', flags), flags)
        self.assertEqual(b.checked_flags(flags), [0, 1, 0, 1, 1, 0, 1])
        for flag in (2, 8, 16, 31, 32, 0xffffffff):
            with self.assertRaises(ValueError): b.checked_flags(struct.pack('<7I', flag, 1, 1, 1, 1, 1, 1))

    def test_r32_and_r4_outer_group_prefix_lemma(self):
        rng = random.Random(640128)
        for k in (256, 2048, 6144):
            for profile, block_bytes in ((1, 144), (2, 210)):
                raw = rng.randbytes(128 * (k // 256) * block_bytes)
                half = len(raw) // 2
                full = b.pack_r4_for_prefix_proof(raw, 128, k, profile)
                self.assertEqual(b.pack_r4_for_prefix_proof(raw[:half], 64, k, profile), full[:half])
                # Explicit group/block/lane traversal independently constructs R4 order.
                row_bytes = (k // 256) * block_bytes
                independent = b''.join(raw[row * row_bytes + block * block_bytes:
                                           row * row_bytes + (block + 1) * block_bytes]
                    for group in range(32) for block in range(k // 256) for row in range(4 * group, 4 * group + 4))
                self.assertEqual(full, independent)
                if profile == 1:
                    self.assertEqual(b.pack_q4_r32(raw[:half], 64, k), b.pack_q4_r32(raw, 128, k)[:half])

    def test_native_prefix_descriptor_ranges_cover_exactly_28_commands(self):
        ranges = b.descriptor_prefix_ranges()
        self.assertEqual(len(ranges), 28)
        self.assertEqual({row['trial'] for row in ranges}, {1, 2})
        for trial in (1, 2):
            for part in range(7):
                rows = [row for row in ranges if row['trial'] == trial and row['part'] == part]
                self.assertEqual([row['output_start'] for row in rows], [0, 32])
                self.assertEqual([row['n'] for row in rows], [32, 32])
                self.assertEqual(rows[0]['weight_offset_bytes'], 0)
                self.assertEqual(rows[0]['weight_bytes'], rows[1]['weight_offset_bytes'])
                self.assertEqual(rows[1]['weight_offset_bytes'] + rows[1]['weight_bytes'], rows[1]['admitted_weight_bytes'])
                self.assertEqual(rows[1]['k_blocks'], b.K[part] // 256)

    def test_actual_accepted_qwen3_prefixes_and_pinned_r4_source(self):
        self.assertEqual(digest(b.BASE / 'build.json'), b.PROGRAMS['decode'][1])
        self.assertEqual(digest(b.RVV_AUDIT / 'result.json'), b.RVV_AUDIT_SHA)
        pins = {}
        for root in (b.BASE, b.RVV_AUDIT):
            for name, sha in json.loads((root / 'source-pins.json').read_text()).items():
                if name in pins: self.assertEqual(pins[name], sha)
                pins[name] = sha
        sdk = json.loads((b.BASE / 'build.json').read_text())
        proof = b.verify_prefixes(sdk, pins)
        self.assertEqual(len(proof['parts']), 7)
        self.assertTrue(all(row['prefix_equal'] and row['prefix_bytes'] * 2 == row['native_bytes'] for row in proof['parts']))
        self.assertEqual(len(proof['expected_native_descriptor_ranges']), 28)
        self.assertTrue(all(flag in (0, 1) for flag in b.checked_flags((b.BASE / 'flags.bin').read_bytes())))

    def test_dependency_gate_never_admits_live_headers_by_directory_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            header = Path(tmp) / 'accepted.h'; header.write_bytes(b'accepted')
            other = Path(tmp) / 'other.h'; other.write_bytes(b'unreviewed')
            self.assertEqual(b.dependency_allowed(header, {str(header): digest(header)}, set()), str(header))
            self.assertEqual(b.dependency_allowed(other, {}, {str(other)}), str(other))
            with self.assertRaises(ValueError): b.dependency_allowed(other, {str(header): digest(header)}, set())
            source = Path(tmp) / 'numeric.cpp'; source.write_bytes(b'not a header')
            with self.assertRaises(ValueError): b.dependency_allowed(source, {str(source): digest(source)}, set())

    def test_producer_receipt_inventory_and_artifact_identity_are_all_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'frozen.h'; source.write_bytes(b'header')
            artifact = root / 'kernel.o'; artifact.write_bytes(b'object')
            inventory = root / 'source-pins.json'
            inventory.write_text(json.dumps({str(source): digest(source)}))
            receipt = root / 'result.json'
            receipt.write_text(json.dumps(dict(state='ACCEPTED', source_pins_sha256=digest(inventory),
                                               artifacts={str(artifact): digest(artifact)})))
            pins = {}
            b.inherit(pins, root, 'result.json', digest(receipt), 'ACCEPTED')
            self.assertEqual(set(pins), {str(receipt), str(inventory), str(source), str(artifact)})
            with self.assertRaises(ValueError): b.inherit({}, root, 'result.json', '0'*64, 'ACCEPTED')
            with self.assertRaises(ValueError): b.inherit({}, root, 'result.json', digest(receipt), 'NOT_ACCEPTED')
            artifact.write_bytes(b'drift')
            with self.assertRaises(ValueError): b.inherit({}, root, 'result.json', digest(receipt), 'ACCEPTED')

    def test_custom_instructions_only_sdk_owners_and_exact_signatures(self):
        blob = executable(bytes.fromhex('5b1505005b04b5020100'))
        labels = ('0000000080000000 <qbs_native_info>:\n'
                  '0000000080000004 <qbs_native_execute_command>:\n'
                  '0000000080000008 <main>:\n')
        signature = b.custom_signature(blob, labels)
        self.assertEqual(signature, {('qbs_native_info', 0x0005155b): 1,
                                     ('qbs_native_execute_command', 0x02b5045b): 1})
        with self.assertRaises(ValueError): b.custom_signature(blob, labels.replace('qbs_native_execute_command', 'main_fake'))
        changed = executable(bytes.fromhex('5b1505005b04b5040100'))
        self.assertNotEqual(b.custom_signature(changed, labels), signature)
        with self.assertRaises(ValueError): b.custom_signature(executable(bytes.fromhex('01000100010001000100')), labels)

    def test_disassembly_requires_kernels_sdk_csr_and_completion(self):
        clone = 'ggml_vec_dot_q6_K_q8_K_vl1024.isra.0'
        bodies = {'_start': '\tnop', '_eoc': '\tsd\ta0,0(t0)',
            'main': '\tcsrwi\tfcsr,8\n\tcsrwi\tvcsr,5\n\tcsrwi\tvstart,0\n\tfrcsr\ta0\n'
                    '\tcsrr\ta1,vcsr\n\tcsrr\ta2,vstart\n\trdcycle\ta3',
            'ggml_gemv_q4_K_32x1_q8_K': '\tvsetvli',
            'ggml_vec_dot_q6_K_q8_K': '\tcsrr\tt1,vlenb\n\tli\ta3,1024\n\tjr\tt1 # <' + clone + '>',
            clone: '\tvsetvli\n\tvle8.v\n\tvwmul.vv', 'quantize_row_q8_K': '\tvsetvli',
            'qbs_device_query': '\tret', 'qbs_plan_create': '\tret', 'qbs_execute_with_options': '\tret',
            'qbs_native_info': '\t.word', 'qbs_native_execute_command': '\tfence\n\tvsetvli\n\tvse32.v'}
        text = '\n'.join(f'{0x80000000+i*0x100:016x} <{name}>:\n{body}' for i, (name, body) in enumerate(bodies.items()))
        self.assertIn('qbs_native_execute_command', b.check_disassembly(text))
        for old, new in (('fcsr,8', 'fcsr,0'), ('vcsr,5', 'vcsr,0'), ('vstart,0', 'vstart,1'),
                         ('\tvse32.v', '\tnop'), ('<'+clone+'>', '<wrong_clone>'), ('\tfrcsr', '\tnop')):
            with self.subTest(old=old), self.assertRaises(ValueError): b.check_disassembly(text.replace(old, new))
        with self.assertRaises(ValueError): b.check_disassembly(text + '\n0000000090000000 <qbs_ref_execute>:\n\tret')

    def test_no_build_without_explicit_frozen_driver_hash(self):
        with patch.object(b.subprocess, 'run') as launch:
            for sha in (None, '', '0'*63, 'x'*64):
                with self.assertRaises(ValueError): b.main(Path('/not-created'), sha)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
