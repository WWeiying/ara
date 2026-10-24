"""Bounded synthetic host tests; no simulator and no live prerequisite reads."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import threeway_run as runner
import attention_run_test as prior_tests


def mechanism_fixture():
    # A positive synthetic mechanism gate, not a measured performance result.
    return prior_tests.fixture().replace('cycles=100000 ', 'cycles=120000 ', 1)


def rvv_end(index):
    return (f'THREEWAY_END trial={index} variant=rvv executed=1 native=0 admitted_groups=0 '
            'outputs=512 cycles=110000 fcsr=1 vcsr=5 checksum=fedcba9876543210 guardbytes=384 errors=0')


def fixture():
    lines = [runner.SUBSET, 'THREEWAY_BEGIN trial=0 variant=rvv', rvv_end(0)]
    for line in mechanism_fixture().splitlines():
        begin, end = runner.mechanism.BEGIN.fullmatch(line), runner.mechanism.END.fullmatch(line)
        if begin:
            variant = 'paired' if int(begin[2]) else 'generic'
            lines.append(f'THREEWAY_BEGIN trial={int(begin[1])+1} variant={variant}')
        elif end:
            variant = 'paired' if int(end[2]) else 'generic'
            lines.append(f'THREEWAY_END trial={int(end[1])+1} variant={variant} executed=1 native=1 '
                f'admitted_groups={end[3]} outputs=512 cycles={end[4]} fcsr={end[5]} vcsr=5 '
                f'checksum={end[6]} guardbytes=384 errors=0')
        elif line == runner.mechanism.SUITE:
            lines += ['THREEWAY_BEGIN trial=5 variant=rvv', rvv_end(5), runner.SUITE]
        elif line != runner.mechanism.SUBSET:
            lines.append(line)
    return '\n'.join(lines)+'\n'


class LogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()
        cls.first = next(x for x in cls.text.splitlines() if x.startswith('[AKV_PERF] '))

    def test_complete_and_zero_rvv(self):
        result = runner.check_log(self.text, ('0123456789abcdef', 3, 5))
        self.assertEqual([t['variant'] for t in result['trials']], ['rvv', 'generic', 'paired', 'paired', 'generic', 'rvv'])
        self.assertEqual([t['derived_hardware_totals']['records'] for t in result['trials']], [0, 1542, 390, 390, 1542, 0])
        for index in (0, 5):
            self.assertTrue(all(v == 0 for v in result['trials'][index]['derived_hardware_totals'].values()))
        summary = result['raw_hardware_summary']
        for key, value in dict(records=3864, read_outstanding_max=2, v2_logical_column=3072,
                v2_k_view_bank_cycles=18432, read_payload_bytes=528896, replay_bytes=786432).items():
            self.assertEqual(summary[key], value)
        self.assertNotEqual(result['trials'][0]['checksum'], result['trials'][1]['checksum'])
        self.assertNotEqual(result['trials'][0]['fcsr'], result['trials'][1]['fcsr'])
        self.assertIn('NOT strong tiled RVV', result['comparison'])
        self.assertEqual(result['sums']['rvv'], 220000)
        runner.check_log(self.text.replace('fcsr=1 ', 'fcsr=31 '))

    def test_missing_unknown_and_rvv_work(self):
        bad = [self.text.replace(self.first+'\n', '', 1), self.text+self.first+'\n',
               self.text.replace(rvv_end(0), self.first+'\n'+rvv_end(0), 1),
               self.text.replace(self.first, self.first+' extra=1', 1),
               self.text.replace(self.first, self.first+' seq=1', 1),
               self.text.replace(self.first, self.first.replace(' id=0', ''), 1)]
        for marker in ('[AKV_PERF]', '[AKV_PERF_SUMMARY]', 'THREEWAY_SUBSET',
                       'THREEWAY_BEGIN', 'THREEWAY_END', 'THREEWAY_SUITE_PASS'):
            bad.extend([self.text.replace(marker, marker+'_BOGUS', 1),
                        self.text.replace(marker, 'embedded '+marker, 1)])
        for text in bad:
            with self.subTest(index=bad.index(text)), self.assertRaises(ValueError):
                runner.check_log(text)
        for marker in (runner.SUBSET, runner.SUITE, runner.TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0'):
            for text in (self.text.replace(marker, '', 1), self.text+marker+'\n'):
                with self.subTest(marker=marker), self.assertRaises(ValueError):
                    runner.check_log(text)

    def test_order_admission_work_flags_and_repeat(self):
        for old, new in [('variant=rvv', 'variant=generic'), ('trial=2', 'trial=3'),
            ('executed=1', 'executed=0'), ('native=0', 'native=1'), ('native=1', 'native=0'),
            ('admitted_groups=0', 'admitted_groups=2'), ('admitted_groups=2', 'admitted_groups=0'),
            ('command=4', 'command=5'), ('seq=1 ', 'seq=2 '), ('fault=0', 'fault=1'),
            ('v2_column_panel=1', 'v2_column_panel=0'), ('replay_bytes=512', 'replay_bytes=128'),
            ('read_ranges=131', 'read_ranges=130'), ('v2_k_view_bank_cycles=8', 'v2_k_view_bank_cycles=7'),
            ('busy_cycles=10', 'busy_cycles=x'), ('fcsr=1', 'fcsr=0'), ('fcsr=1', 'fcsr=32'),
            ('fcsr=3', 'fcsr=1'), ('vcsr=5', 'vcsr=0'), ('guardbytes=384', 'guardbytes=383'),
            ('errors=0', 'errors=1'), ('outputs=512', 'outputs=511'),
            ('checksum=fedcba9876543210', 'checksum=0000000000000000')]:
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                runner.check_log(self.text.replace(old, new, 1))
        # Consistent paired repeats still must match generic.
        text = self.text.replace('variant=paired executed=1 native=1 admitted_groups=2 outputs=512 cycles=99900 fcsr=3',
                                'variant=paired executed=1 native=1 admitted_groups=2 outputs=512 cycles=99900 fcsr=2')
        text = text.replace('variant=paired executed=1 native=1 admitted_groups=2 outputs=512 cycles=99800 fcsr=3',
                            'variant=paired executed=1 native=1 admitted_groups=2 outputs=512 cycles=99800 fcsr=2')
        with self.assertRaisesRegex(ValueError, 'Generic/paired'):
            runner.check_log(text)
        with self.assertRaisesRegex(ValueError, 'accepted mechanism'):
            runner.check_log(self.text, ('0000000000000000', 3, 5))

    def test_summary_and_external_traffic(self):
        lines = self.text.splitlines()
        for key, value in [('records', 3863), ('read_outstanding_max', 32), ('replay_bytes', 0),
                           ('r_beats', 0), ('busy_cycles', 0)]:
            row = runner.numeric_fields(lines[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
            row[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.check_log('\n'.join(lines[:-1]+[prior_tests.metric('[AKV_PERF_SUMMARY]', row)]))
        with self.assertRaises(ValueError):
            runner.check_log(self.text.rstrip()+' extra=0\n')
        changed = self.text.replace(' ar=140 ', ' ar=141 ', 1).splitlines()
        row = runner.numeric_fields(changed[-1].split(' ', 1)[1], runner.SUMMARY_FIELDS)
        row['ar'] += 1
        changed[-1] = prior_tests.metric('[AKV_PERF_SUMMARY]', row)
        with self.assertRaisesRegex(ValueError, 'external traffic'):
            runner.check_log('\n'.join(changed))


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, data):
        p = self.root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
        return p

    def build_fixture(self):
        build, capture = self.root/'build', self.root/'capture'
        build.mkdir()
        (capture/'decode/block').mkdir(parents=True)
        sources, crops, unchanged = [], [], {}
        for index, (name, filename) in enumerate(runner.CAPTURE_NAMES.items()):
            source = capture/'decode/block'/filename
            source.write_bytes(b''.join(bytes([h+index])*512 for h in range(12)))
            sources.append(source)
            if name in ('input_a', 'golden'):
                output = build/(name+'.bin')
                data = source.read_bytes()
                output.write_bytes(b''.join(data[h*512:(h+1)*512] for h in (0, 1, 6, 7)))
                sources.append(output)
                crops.append(dict(name=name, source=str(source), output=str(output),
                    source_sha256=runner.digest(source), sha256=runner.digest(output),
                    source_heads=[0, 1, 6, 7], verified_bytes=2048))
            else:
                unchanged[name] = dict(path=str(source), sha256=runner.digest(source))
        config, elf = build/'config.bin', build/'test.elf'
        config.write_bytes(bytes(180))
        elf.write_bytes(b'ELF')
        proof = dict(state='HOST_DATA_CHECK_PASS', self_test=runner.HOST_CROP_TESTS, crops=crops,
            unchanged=unchanged, args=[128, 1, 4, 256, 2, 0, 0, 0], flag=1,
            params=[.004, .002, .125, 0., 0., 0., 0., 0.], config_sha256=runner.digest(config))
        proof_path = self.write('build/data-proof.json', proof)
        pins = self.write('build/source-pins.json', runner.hashes(sources))
        report = dict(state='BUILT_NOT_EXECUTED', execution='NOT_RUN', post_pins_match=True,
            expected=runner.EXPECTED, source_heads=[0, 1, 6, 7], source_kv_heads=[0, 1],
            tolerance=dict(atol=.004, rtol=.002), output_capacity=2048, shared_output_all_paths=True,
            linked_abi_and_all_blob_bytes_verified=True, host_self_tests=runner.HOST_CROP_TESTS,
            elf=str(elf), elf_sha256=runner.digest(elf), source_pins=str(pins), source_pins_sha256=runner.digest(pins),
            artifact_sha256=runner.hashes([elf, config, proof_path]), capture=str(capture), scale=.125)
        self.write('build/build.json', report)
        return build, report, proof

    def test_build_schema_crop_and_source_identity(self):
        build, report, proof = self.build_fixture()
        self.assertEqual(len(runner.checked_build(build)[2]), 5)
        for key, value in [('expected', {}), ('output_capacity', 2176), ('shared_output_all_paths', False),
                ('linked_abi_and_all_blob_bytes_verified', False), ('source_heads', [0, 1, 2, 3])]:
            self.write('build/build.json', dict(report, **{key: value}))
            with self.subTest(key=key), self.assertRaises(ValueError):
                runner.checked_build(build)
        self.write('build/build.json', report)
        # Even an updated crop receipt cannot make a wrong head mapping pass.
        cropped = build/'input_a.bin'
        cropped.write_bytes(bytes(2048))
        proof['crops'][0]['sha256'] = runner.digest(cropped)
        self.write('build/data-proof.json', proof)
        pins = runner.read_json(build/'source-pins.json')
        pins[str(cropped)] = runner.digest(cropped)
        self.write('build/source-pins.json', pins)
        report['source_pins_sha256'] = runner.digest(build/'source-pins.json')
        report['artifact_sha256'][str(build/'data-proof.json')] = runner.digest(build/'data-proof.json')
        self.write('build/build.json', report)
        with self.assertRaisesRegex(ValueError, 'Crop byte mapping'):
            runner.checked_build(build)

    def prerequisite_fixture(self):
        elf, simv = self.write('test.elf', 'ELF'), self.write('simv', 'image')
        image = runner.hashes([simv])
        captures = runner.hashes([self.write(f'capture{i}', str(i)) for i in range(5)])
        self.write('work/vector_trace.csv', 'trace')
        log = self.root/'work/run.vcs.log'
        log.write_text(mechanism_fixture())
        self.write('source-pins.json', dict(runner.hashes([elf, simv]), **captures))
        status = dict(state='PASS', child_pid=None, elf=str(elf), simv=str(simv))
        self.write('status.json', status)
        result = runner.mechanism.check_log(log.read_text())
        self.update_evidence(result, image, elf)
        return status, result, image, captures

    def update_evidence(self, result, image, elf):
        log, trace = self.root/'work/run.vcs.log', self.root/'work/vector_trace.csv'
        uvm = self.write('work/uvm_result.json', dict(status='PASS', issues=[], elf_sha256=runner.digest(elf),
            sim_image_sha256=image, log_sha256=runner.digest(log), vector_trace_sha256=runner.digest(trace)))
        result['evidence_sha256'] = runner.hashes([log, trace, uvm, self.root/'source-pins.json'])
        self.write('result.json', result)

    def test_prerequisite_terminal_raw_positive_and_input_binding(self):
        status, result, image, captures = self.prerequisite_fixture()
        self.assertEqual(runner.checked_prerequisite(self.root, image, captures)[1], ('0123456789abcdef', 3, 5))
        for state, pid in [('RUNNING', 123), ('FAIL', None), ('PASS', 123)]:
            self.write('status.json', dict(status, state=state, child_pid=pid))
            with self.subTest(state=state), self.assertRaises(ValueError):
                runner.checked_prerequisite(self.root, image, captures)
        self.write('status.json', status)
        wrong = dict(captures)
        wrong[next(iter(wrong))] = '0'*64
        with self.assertRaisesRegex(ValueError, 'inputs/subset'):
            runner.checked_prerequisite(self.root, image, wrong)
        bad = copy.deepcopy(result)
        bad['sums']['0'] += 1
        self.write('result.json', bad)
        with self.assertRaisesRegex(ValueError, 'result/raw'):
            runner.checked_prerequisite(self.root, image, captures)
        log, elf = self.root/'work/run.vcs.log', Path(status['elf'])
        log.write_text(mechanism_fixture().replace('AKV_PAIR_ABBA_PASS', 'AKV_PAIR_ABBA_PASS_BOGUS'))
        self.update_evidence(result, image, elf)
        with self.assertRaisesRegex(ValueError, 'program marker'):
            runner.checked_prerequisite(self.root, image, captures)
        log.write_text(prior_tests.fixture())  # Equal cycle sums: no positive mechanism gain.
        result = runner.mechanism.check_log(log.read_text())
        self.update_evidence(result, image, elf)
        with self.assertRaisesRegex(ValueError, 'positive mechanism'):
            runner.checked_prerequisite(self.root, image, captures)

    def test_prerequisite_uvm_evidence_and_image(self):
        _status, result, image, captures = self.prerequisite_fixture()
        with self.assertRaises(RuntimeError):
            runner.checked_prerequisite(self.root, {next(iter(image)): '0'*64}, captures)
        uvm_path = self.root/'work/uvm_result.json'
        good = runner.read_json(uvm_path)
        for key, value in [('status', 'FAIL'), ('issues', ['issue']), ('log_sha256', '0'*64)]:
            self.write('work/uvm_result.json', dict(good, **{key: value}))
            result['evidence_sha256'][str(uvm_path)] = runner.digest(uvm_path)
            self.write('result.json', result)
            with self.subTest(key=key), self.assertRaises((ValueError, RuntimeError)):
                runner.checked_prerequisite(self.root, image, captures)
        del result['evidence_sha256'][str(uvm_path)]
        self.write('result.json', result)
        with self.assertRaisesRegex(ValueError, 'Missing mechanism evidence'):
            runner.checked_prerequisite(self.root, image, captures)

    def test_no_launch_without_prerequisite_or_on_image_mismatch(self):
        for name in ('build', 'gate', 'prereq', 'integration/build/sim'):
            (self.root/name).mkdir(parents=True)
        simv = self.write('integration/build/sim/simv', 'image')
        image = runner.hashes([simv])
        for index, mismatch in enumerate((False, True)):
            argv = ['worker', '--build', str(self.root/'build'), '--output', str(self.root/f'out{index}'),
                '--gate', str(self.root/'gate'), '--prerequisite', str(self.root/'prereq'),
                '--integration', str(self.root/'integration'), '--preflight-only']
            report = dict(simv=str(simv), accepted_image_pins={} if mismatch else image)
            with patch.object(runner.sys, 'argv', argv), patch.object(runner.signal, 'signal'), \
                 patch.object(runner, 'checked_build', return_value=(report, {}, {})), \
                 patch.object(runner, 'checked_image', return_value=(image, {})), \
                 patch.object(runner, 'checked_prerequisite', side_effect=ValueError('not PASS')), \
                 patch.object(runner, 'run_command') as launch:
                with self.assertRaisesRegex(ValueError, 'Build/image mismatch' if mismatch else 'not PASS'):
                    runner.main()
                launch.assert_not_called()
            self.assertEqual(runner.read_json(self.root/f'out{index}/status.json')['state'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
