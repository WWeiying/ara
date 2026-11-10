"""Source-only checks. No compiler, QEMU process, guest, or source-tree writes."""
import importlib.util
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('stage5_overlay', HERE / 'overlay.py')
overlay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(overlay)
sys.path.insert(0, str(HERE))
import recipe
BASE = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/'
            'qemu-context-20261023-01/qemu-10.2.0')


def decode_patterns(text):
    result = []
    for line in text.splitlines():
        fields = line.split()
        if fields and fields[0] in ('akvexec', 'akvinfo'):
            if len(fields) != 8 or not fields[7].startswith('@akv_'):
                raise ValueError('Malformed instruction format')
            pattern = ''.join(fields[1:7])
            if len(pattern) != 32 or re.search(r'[^01.]', pattern):
                raise ValueError('Malformed instruction pattern')
            mask = int(''.join('0' if c == '.' else '1' for c in pattern), 2)
            value = int(pattern.replace('.', '0'), 2)
            result.append((fields[0], mask, value))
    return result


class AdapterSourceTests(unittest.TestCase):
    def test_inventory_mutations_fail_closed(self):
        expected = {'a': {'kind': 'file', 'sha256': 'old'},
                    'd': {'kind': 'directory'}, 'l': {'kind': 'symlink', 'target': 'a'}}
        recipe.verify_membership(expected, expected)
        for changed in ({k: v for k, v in expected.items() if k != 'a'},
                        dict(expected, extra={'kind': 'file', 'sha256': 'new'}),
                        dict(expected, a={'kind': 'file', 'sha256': 'new'}),
                        dict(expected, l={'kind': 'symlink', 'target': '/outside'})):
            with self.assertRaises(ValueError):
                recipe.verify_membership(changed, expected)

    def test_build_environment_does_not_inherit_injections(self):
        tools = {'gcc': '/usr/bin/gcc', 'g++': '/usr/bin/g++'}
        clean = recipe.build_environment(Path('/fresh'), tools)
        with patch.dict(recipe.os.environ, {
            'CPATH': '/untrusted', 'C_INCLUDE_PATH': '/untrusted',
            'GCC_EXEC_PREFIX': '/untrusted', 'COMPILER_PATH': '/untrusted',
            'PYTHONPATH': '/untrusted', 'PKG_CONFIG_PATH': '/untrusted',
            'LD_PRELOAD': '/untrusted', 'CFLAGS': '-ffast-math', 'PATH': '/untrusted',
        }):
            self.assertEqual(recipe.build_environment(Path('/fresh'), tools), clean)
        self.assertEqual(clean['PATH'], '/usr/bin:/bin')
        self.assertEqual(set(clean), {'PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL',
                                     'CC', 'CXX', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE'})

    def test_existing_source_anchors_exact_and_nonrepeatable(self):
        for path in overlay.EDITS:
            with self.subTest(path=path):
                before = (BASE / path).read_text()
                after = overlay.transform(path, before)
                self.assertNotEqual(before, after)
                with self.assertRaises(ValueError):
                    overlay.transform(path, after)

    def test_anchor_mutations_fail_closed(self):
        for path, edits in overlay.EDITS.items():
            before = (BASE / path).read_text()
            anchor = edits[0][0]
            with self.subTest(path=path):
                for changed in (before.replace(anchor, '', 1), before + anchor):
                    with self.assertRaises(ValueError):
                        overlay.transform(path, changed)

    def test_exact_native_words_decode_once(self):
        patterns = decode_patterns((HERE / 'Xaraakv.decode').read_text())
        for word in (0x0005455b, 0x0605705b, 0x0485705b,
                     0x0205745b, 0x0005745b, 0x0005345b, 0x0405345b, 0x0205345b):
            with self.subTest(word=hex(word)):
                self.assertEqual(sum(word & mask == value for _, mask, value in patterns), 1)

    def test_qbs_custom2_slots_not_intercepted(self):
        patterns = decode_patterns((HERE / 'Xaraakv.decode').read_text())
        for funct3 in (0, 1):
            for funct7 in range(128):
                word = funct7 << 25 | funct3 << 12 | 0x5b
                self.assertFalse(any(word & mask == value for _, mask, value in patterns))

    def test_qbs_implementation_files_not_patched(self):
        for path in overlay.EDITS:
            self.assertNotIn(Path(path).name, ('qbs_helper.c', 'qbs_ref.c', 'qbs_ref.h',
                                             'qbs_abi.h', 'Xaraqbs.decode', 'trans_xaraqbs.c.inc'))
        self.assertIn('native-qbs-successor-smoke', (HERE / 'recipe.py').read_text())

    def test_software_float_only_fused_operations(self):
        source = (HERE / 'akv_helper.c').read_text()
        self.assertIn('float16_muladd(', source)
        self.assertIn('float32_muladd(', source)
        self.assertIn('float_status status = call->env->fp_status;', source)
        self.assertIn('set_float_exception_flags(0, &status)', source)
        self.assertNotRegex(source, r'\b(float|double|fmaf|fma|sqrt|tanh|exp)\s*\(')
        self.assertNotIn('float16_to_float32(', source)
        self.assertIn('riscv_cpu_get_fflags(env) | result.fflags', source)
        self.assertNotRegex(source, r'env->(?:frm|vtype|vl|vxrm|vxsat)\s*=')

    def test_info_does_not_read_fp_vector_csrs(self):
        source = (HERE / 'trans_xaraakv.c.inc').read_text().split('static bool trans_akvexec')[0]
        self.assertNotIn('mstatus_', source)
        self.assertNotIn('vstart_eq_zero', source)
        self.assertNotIn('mark_', source)

    def test_bootstrap_exact_pmp_and_jump(self):
        text = (HERE / 'ara_stage4.c').read_text().split('uint32_t boot[] = {')[1].split('};')[0]
        words = [int(x, 16) for x in re.findall(r'^\s*(0x[0-9a-f]{8}),', text, re.M)]
        self.assertEqual(words, [0xfff00293, 0x3b029073, 0x01f00293, 0x3a029073,
                                 0x00000297, 0x0102b283, 0x00028067, 0x00000013])
        self.assertEqual((words[1] >> 20, words[3] >> 20), (0x3b0, 0x3a0))
        self.assertEqual(16 + (words[5] >> 20), 32)

    def test_defaults_off_and_migration_rejected(self):
        source = overlay.transform('target/riscv/cpu.c', (BASE / 'target/riscv/cpu.c').read_text())
        self.assertIn('MULTI_EXT_CFG_BOOL("xaraakv", ext_Xaraakv, false)', source)
        self.assertIn('DEFINE_PROP_BOOL("xaraakv-resident", RISCVCPU, cfg.ext_XaraakvResident, false)', source)
        self.assertNotIn('ISA_EXT_DATA_ENTRY(xaraakvresident', source)
        self.assertIn('akv_model_reset(&env->akv_context)', source)
        machine = overlay.transform('target/riscv/machine.c', (BASE / 'target/riscv/machine.c').read_text())
        self.assertIn('.pre_save = riscv_akv_pre_save', machine)
        self.assertIn('return cpu->cfg.ext_Xaraakv ? -ENOTSUP : 0', machine)
        self.assertIn('if (cpu->cfg.ext_Xaraakv) {\n        return -ENOTSUP;', machine)


if __name__ == '__main__':
    unittest.main()
