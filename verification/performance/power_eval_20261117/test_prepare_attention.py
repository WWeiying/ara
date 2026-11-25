"""Host-only synthetic log tests. These are not target or power acceptance."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
import prepare_attention as p


def fixture(mode):
    f = json.loads((p.FROZEN / 'inputs/fixture.json').read_text())
    f.update(order=[mode, mode], printed_values=256)
    return f


def synthetic_log(f):
    lines = []
    hexkeys = p.checker().HEX

    def emit(tag, **values):
        lines.append('OP_ATTN_' + tag + ' ' + ' '.join(
            k + '=' + (format(v, 'x') if k in hexkeys else str(v)) for k, v in values.items()))

    c = f['case']
    for trial, mode in enumerate(f['order']):
        emit('CALL', trial=trial, mode=mode, d=128, heads=2, kvheads=1, tokens=137,
             begin=1000 + trial * 1000, returned=1500 + trial * 1000, end=1510 + trial * 1000,
             initial_fcsr=c['initial_flags'], initial_vcsr=0, initial_vstart=0,
             fcsr=f['result']['expected_fcsr'], vcsr=0, vstart=0, groups=1, errors=0)
        emit('GROUP', trial=trial, group=0, first_head=0, rows=2,
             q=0x80040000, k=0x80010000, v=0x80020000, output=0x80041000)
        emit('MEMORY', trial=trial, **f['memory'])
        emit('CHECK', trial=trial, values=256, output_hash=f['output_hash'], model_errors=0)
        for i, bits in enumerate(f['result']['bits']):
            emit('OUT', trial=trial, index=i, bits=bits)
    emit('DATA', bytes=f['data_bytes'], hash=f['data_hash'])
    emit('DONE', calls=2, errors=0)
    lines.append('Core Test *** SUCCESS *** (tohost = 0)')
    return '\n'.join(lines) + '\n'


class AttentionTest(unittest.TestCase):
    def test_both_modes_no_monitors(self):
        for mode in (0, 1):
            f = fixture(mode)
            r = p.check_text(synthetic_log(f), f)
            self.assertEqual(r['bitexact_output_values'], 512)
            for gate in ('activity_checked', 'execution_path_checked', 'protocol_checked',
                         'image_checked', 'power_acceptance', 'performance_acceptance'):
                self.assertIs(r[gate], False)

    def test_fail_closed(self):
        f = fixture(0)
        text = synthetic_log(f)
        changes = [
            ('mode=0', 'mode=1'), ('initial_fcsr=8', 'initial_fcsr=0'),
            (' vcsr=0', ' vcsr=1'), (' vstart=0', ' vstart=1'),
            ('fcsr=' + str(f['result']['expected_fcsr']) + ' vcsr', 'fcsr=0 vcsr'),
            ('guard_bytes=' + str(f['memory']['guard_bytes']), 'guard_bytes=0'),
            ('guard_hash=' + format(f['memory']['guard_hash'], 'x'), 'guard_hash=0'),
            ('query_hash=' + format(f['memory']['query_hash'], 'x'), 'query_hash=0'),
            ('model_errors=0', 'model_errors=1'), ('errors=0', 'errors=1'),
            ('index=255 bits=' + format(f['result']['bits'][255], 'x'), 'index=255 bits=ffffffff'),
            ('output_hash=' + format(f['output_hash'], 'x'), 'output_hash=0'),
            ('OP_ATTN_DONE calls=2 errors=0', ''),
            ('Core Test *** SUCCESS *** (tohost = 0)', ''),
            ('tohost = 0', 'tohost = 1'), ('tokens=137', 'tokens=136'),
        ]
        for old, new in changes:
            with self.subTest(old=old):
                self.assertIn(old, text)
                with self.assertRaises(ValueError):
                    p.check_text(text.replace(old, new, 1), f)
        for tail in ('\nError: broken', '\nUVM_ERROR : 1', '\nTIMEOUT',
                     '\nOP_ATTN_DONE calls=2 errors=0', '\n' + text):
            with self.subTest(tail=tail[:40]), self.assertRaises(ValueError):
                p.check_text(text + tail, f)

    def test_derivation_templates(self):
        inputs = p.FROZEN / 'inputs'
        for mode in (0, 1):
            h = p.adapt_header((inputs / 'fixture.h').read_text(), mode)
            self.assertIn('{%d,%d}' % (mode, mode), h)
            self.assertIn('ATTN_CALLS UINT64_C(0x2)', h)
            self.assertIn('ATTN_PRINT_VALUES 256', h)
        link = p.adapt_linker((inputs / 'link.ld').read_text())
        self.assertIn('LENGTH = 0x00100000', link)
        self.assertIn('ASSERT(__power_image_end <= __power_stack_bottom', link)
        self.assertIn('*(.bss .bss.*)', link)
        crt = p.adapt_crt((inputs / 'sdk/apps/common/crt0.S').read_text())
        self.assertIn('la      sp, __power_stack_top', crt)
        self.assertNotIn('ld      sp, 0(t0)', crt)
        with self.assertRaises(ValueError):
            p.adapt_header(h, 0)
        with self.assertRaises(ValueError):
            p.adapt_linker(link)
        main = (inputs / 'main.c').read_text()
        rvv, akv = p.adapt_main(main, 0), p.adapt_main(main, 1)
        self.assertNotIn('akv_device_query(akv_native_info', rvv)
        self.assertIn('akv_device_init_reference(&device)', rvv)
        self.assertNotIn('return akv_attention_execute_v2_native_auto', rvv)
        self.assertNotIn('return attention_rvv_group', akv)
        self.assertIn('akv_device_query(akv_native_info', akv)

    def test_custom_opcode_scan(self):
        self.assertEqual(p.custom_instructions('  80000000: 00000013 nop\n'), [])
        self.assertEqual(p.custom_instructions('  80000000: 0005455b custom\n'),
                         [dict(pc=0x80000000, word=0x0005455b)])
        with self.assertRaises(ValueError):
            p.custom_instructions('')

    def test_data_digest_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for role in p.ROLES:
                (root / (role + '.bin')).write_bytes(b'fixed')
            first = p.paired_data(root)
            self.assertEqual(first, p.paired_data(root))
            (root / 'key.bin').write_bytes(b'changed')
            self.assertNotEqual(first['sha256'], p.paired_data(root)['sha256'])

    def test_cli_bad_receipt_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = Path(tmp) / 'result.json'
            proc = subprocess.run([sys.executable, '-B', str(p.HERE / 'prepare_attention.py'),
                'check', '--build', tmp, '--log', str(Path(tmp) / 'missing.log'),
                '--output', str(result)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(json.loads(result.read_text())['state'], 'FAIL')

    def test_built_pair_when_present(self):
        paths = [p.OUT / ('power_attention_prepare_20261117_%s_01' % mode) for mode in p.MODES]
        if not all((path / 'build.json').exists() for path in paths):
            self.skipTest('Pair not built yet')
        reports = [p.receipt(path) for path in paths]
        self.assertEqual(reports[0]['paired_source_data'], reports[1]['paired_source_data'])
        self.assertEqual([r['order'] for r in reports], [[0, 0], [1, 1]])
        self.assertNotEqual(reports[0]['elf_sha256'], reports[1]['elf_sha256'])
        for path, report in zip(paths, reports):
            self.assertEqual(p.elf_bounds(path / 'attention.elf'), report['load_segments'])
            with tempfile.TemporaryDirectory() as tmp:
                log, result = Path(tmp) / 'synthetic.log', Path(tmp) / 'result.json'
                log.write_text(synthetic_log(report['fixture']))
                proc = subprocess.run([sys.executable, '-B', str(p.HERE / 'prepare_attention.py'),
                    'check', '--build', str(path), '--log', str(log), '--output', str(result)],
                    capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(json.loads(result.read_text())['state'], 'PASS')


if __name__ == '__main__':
    unittest.main()
