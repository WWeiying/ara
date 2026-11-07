import importlib.util
from pathlib import Path
import struct
import unittest
from unittest import mock


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


build = module('q6_build', 'build.py')
check = module('q6_check', 'check.py')


class CropTests(unittest.TestCase):
    def test_nonzero_group_crop_keeps_every_kblock(self):
        n, kb, size = 16, 8, 2
        data = bytearray(n*kb*size)
        for row in range(n):
            for block in range(kb):
                offset = ((row//4*kb+block)*4+row%4)*size
                data[offset:offset+size] = bytes((row, block))
        cropped = build.crop_r4(data, n, 4, 8, kb, size)
        for row in range(8):
            for block in range(kb):
                offset = ((row//4*kb+block)*4+row%4)*size
                self.assertEqual(cropped[offset:offset+size], bytes((row+4, block)))

    def test_invalid_crops(self):
        for kwargs in ({'first': 1}, {'n': 65}, {'kb': 0}, {'n': 132}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build.crop_r4(bytes(128*8*210), **kwargs)
        with self.assertRaises(ValueError):
            build.crop_r4(bytes(128*8*210-1))


class ParserTests(unittest.TestCase):
    def setUp(self):
        # Parser fixtures only. The workload builder admits only SHA-pinned real data.
        self.q8 = bytes((i*17+31) % 256 for i in range(2336))
        self.expected = struct.pack('<64f', *[i/8 for i in range(64)])
        lines = []
        for i in range(4):
            p = dict(seq=i+1, m=1, n=32, vlen=1024, lanes=4, success=1, fault=0,
                     validation_fault=0, validation_error=0, read_fault=0,
                     context_validation_fault_count=0, weight_bytes=53760,
                     activation_bytes=2336, tiles=64, useful_pairs=65536,
                     pair_capacity=65536, dot_active_cycles=2048,
                     probe_compute_without_dot_issue_cycles=320,
                     activation_access=(1, 3)[i % 2], context_fill_count=1-i%2,
                     context_reuse_count=i%2)
            p.update({k: 0 for k in check.PHASES})
            p.update(phase_compute_cycles=296, phase_overlap_cycles=2072, phase_weight_cycles=1000,
                     busy_cycles=3368)
            lines.append('[QBS_PERF] ' + ' '.join(f'{k}={v}' for k, v in p.items()))
        lines.append('Q6_DECODE_META build_id=test m=1 k=2048 n=64 profile=2 trials=2 q8_bytes=2336 guard_bytes=64')
        for t in range(2):
            ts = [100+t*20000, 1100+t*20000, 1600+t*20000, 9600+t*20000, 9700+t*20000]
            r = dict(trial=t, context=1, status=0, commands=2, plan_errors=0, q8_errors=0,
                     output_errors=0, **{'t'+str(i): value for i, value in enumerate(ts)},
                     prep=1000, admit=500, execute=8000, drain=100, total=9600)
            lines.append('Q6_DECODE_TRIAL ' + ' '.join(f'{k}={v}' for k, v in r.items()))
            lines.append(f'Q6_DECODE_CSR trial={t} fcsr_before=0 vcsr_before=0 vstart_before=0 '
                         'fcsr_quant=1 fcsr_after=1 vcsr_after=0 vstart_after=0 vl_after=32 vtype_after=208')
            lines.append(f'Q6_DECODE_WORK trial={t} quant_calls=1 plan_calls=1 execute_calls=1 '
                         'planned_commands=2 k_elements=2048 n_elements=64 guard_errors=0')
            for g in range(8):
                lines.append(f'Q6_DECODE_GUARD trial={t} index={g} hex=' + 'a5'*64)
            for b in range(8):
                lines.append(f'Q6_DECODE_Q8 trial={t} block={b} hex={self.q8[b*292:(b+1)*292].hex()}')
            for i in range(64):
                value = struct.unpack_from('<I', self.expected, 4*i)[0]
                lines.append(f'Q6_DECODE_OUT trial={t} index={i} bits={value:08x}')
        lines.append('Q6_DECODE_DONE errors=0 trials=2 commands=4')
        self.lines = lines
        self.text = '\n'.join(lines)

    def parse(self, text=None):
        return check.parse_log(self.text if text is None else text, 'test', self.q8, self.expected)

    def reject(self, text):
        with self.assertRaises((ValueError, KeyError)):
            self.parse(text)

    def test_complete_partition_not_signoff(self):
        r = self.parse()
        self.assertEqual(r['state'], 'PASS')
        self.assertFalse(r['independent_protocol_checked'])
        self.assertEqual(r['full_q8_bytes_checked_per_trial'], 2336)
        self.assertEqual(sum(r['trials'][0]['complete_slice_partition_cycles'].values()), 9600)

    def test_direct_fallback(self):
        text = self.text.replace('context=1', 'context=0')
        for field in ('activation_access', 'context_fill_count', 'context_reuse_count'):
            import re
            text = re.sub(field + r'=[0-9]+', field + '=0', text)
        self.parse(text)

    def test_missing_every_record(self):
        for i in range(len(self.lines)):
            with self.subTest(line=i):
                self.reject('\n'.join(self.lines[:i]+self.lines[i+1:]))

    def test_duplicate_every_record(self):
        for i in range(len(self.lines)):
            with self.subTest(line=i):
                self.reject('\n'.join(self.lines[:i]+[self.lines[i]]+self.lines[i:]))

    def test_geometry_identity_faults_and_timing(self):
        for old, new in (
            ('build_id=test', 'build_id=other'), ('m=1', 'm=4'), ('n=32', 'n=16'),
            ('weight_bytes=53760', 'weight_bytes=26880'), ('tiles=64', 'tiles=32'),
            ('activation_bytes=2336', 'activation_bytes=1168'), ('fault=0', 'fault=1'),
            ('success=1', 'success=0'), ('commands=2', 'commands=1'),
            ('context_fill_count=1', 'context_fill_count=0'), ('activation_access=3', 'activation_access=2'),
            ('busy_cycles=3368', 'busy_cycles=9000'), ('total=9600', 'total=9601'),
            ('t2=1600', 't2=0'), ('q8_errors=0', 'q8_errors=1'), ('output_errors=0', 'output_errors=1'),
            ('seq=1', 'seq=2'), ('prep=1000', 'prep=-1'), ('trial=0', 'trial=0 trial=0'),
        ):
            with self.subTest(old=old):
                self.reject(self.text.replace(old, new, 1))

    def test_all_q8_byte_regions(self):
        old = 'hex=' + self.q8[:292].hex()
        for i in (0, 3, 4, 259, 260, 291):
            changed = bytearray(self.q8[:292])
            changed[i] ^= 1
            self.reject(self.text.replace(old, 'hex=' + changed.hex(), 1))

    def test_output_nan_or_different(self):
        self.reject(self.text.replace('bits=00000000', 'bits=7fc00000', 1))

    def test_simulator_failure(self):
        for extra in ('\nTIMEOUT', '\nUVM_FATAL: broken', '\nError: failed',
                      '\nUVM_ERROR : 1', '\nUVM_FATAL : 2',
                      '\nUVM_ERROR source.sv(42) @ 0: failed'):
            self.reject(self.text+extra)

    def test_zero_uvm_summaries_are_not_errors(self):
        self.parse(self.text+'\nUVM_ERROR :    0\nUVM_FATAL :    0\n')

    def test_csr_guards_and_work_rejected(self):
        for old, new in (
            ('fcsr_before=0', 'fcsr_before=1'), ('vcsr_before=0', 'vcsr_before=2'),
            ('vstart_before=0', 'vstart_before=1'), ('fcsr_quant=1', 'fcsr_quant=16'),
            ('fcsr_after=1', 'fcsr_after=17'), ('vstart_after=0', 'vstart_after=1'),
            ('vcsr_after=0', 'vcsr_after=1'), ('vl_after=32', 'vl_after=16'),
            ('vtype_after=208', 'vtype_after=209'), ('quant_calls=1', 'quant_calls=0'),
            ('plan_calls=1', 'plan_calls=2'), ('execute_calls=1', 'execute_calls=2'),
            ('guard_errors=0', 'guard_errors=1'), ('k_elements=2048', 'k_elements=1024'),
            ('hex=' + 'a5'*64, 'hex=' + 'a5'*63+'a4'),
        ):
            with self.subTest(old=old):
                self.reject(self.text.replace(old, new, 1))

    def test_stdout_success_markers_alone_rejected(self):
        self.reject(self.lines[4] + '\n' + self.lines[-1])

    def test_unified_check_run_interface(self):
        manifest = dict(build_id='test', q8_expected='q8', expected='expected',
                        elf_sha256='elf', source_pins_sha256='pins')
        def run(text):
            with mock.patch.object(check, 'check_build', return_value=manifest), \
                 mock.patch.object(Path, 'read_text', return_value=text), \
                 mock.patch.object(Path, 'read_bytes', side_effect=[self.q8, self.expected]), \
                 mock.patch.object(check, 'digest', return_value='fixture'):
                return check.check_run(Path('fixture.log'), Path('fixture_build'))
        self.assertEqual(run(self.text)['state'], 'PASS')
        for text in (self.text.replace('bits=00000000', 'bits=00000001', 1),
                     '\n'.join(self.lines[:-1]),
                     self.text.replace('fcsr_after=1', 'fcsr_after=17', 1),
                     self.text.replace('hex='+'a5'*64, 'hex='+'a4'*64, 1)):
            with self.assertRaises(ValueError):
                run(text)


if __name__ == '__main__':
    unittest.main()
