"""Bounded host tests; no EDA, Spike invocation or large raw-log replay."""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import collect_decode_partition as c


def fake_measured():
    result = {}
    for group, width in c.RESULT_SHA:
        scope = c.contract(group)
        measured = dict(parts=[], preparation=[], trials=[])
        for trial, backend in enumerate(c.ORDER):
            prep = [dict(trial=trial, backend=backend, stage=s, cycles=100 + s,
                         checksum=10000 + s, fcsr=9, vcsr=3, vstart=0, errors=0)
                    for s in scope['stages']]
            parts = [dict(trial=trial, backend=backend, part=p, profile=c.PROFILE[p], k=c.K[p],
                          admission=20 + backend + p,
                          execution=(1000 + p * 100) * (10 if backend == 0 else 1) // (width // 128),
                          checksum=100 * p + backend, fcsr=9, vcsr=3, vstart=0, errors=0)
                     for p in scope['parts']]
            measured['parts'].extend(parts)
            measured['preparation'].extend(prep)
            row = dict(trial=trial, backend=backend, preparation=sum(r['cycles'] for r in prep),
                       admission=sum(r['admission'] for r in parts), execution=sum(r['execution'] for r in parts))
            row['region'] = row['preparation'] + row['admission'] + row['execution'] + 7
            measured['trials'].append(row)
        result[group, width] = measured
    return result


class AdmissionTests(unittest.TestCase):
    def test_exact_worker_admission_rejects_missing_or_wrong_scope(self):
        program = dict(elf='/test/group0.elf', elf_sha256='a' * 64)
        row = dict(state='DECODE_PARTITION_RTL_ISA_PROTOCOL_PASS', group=0, width=128,
                   child_pid=None, performance_measured=True, independent_protocol_checked=True,
                   whole_model=False, continuous_seven_part_run=False, exact_mixed_elf_spike_executed=False,
                   build_result_sha256=c.BUILD_SHA, post_pins_match=True, **program,
                   checked_guest_outputs=c.contract(0)['outputs_checked'], measured={
                       'independent_reference': 'Original N128 Spike RVV bits exact N64 prefix; separate SDK C-reference bits'})
        c.accept_run(row, 0, 128, program)
        for key in row:
            bad = copy.deepcopy(row)
            del bad[key]
            with self.subTest(missing=key), self.assertRaises((ValueError, KeyError)):
                c.accept_run(bad, 0, 128, program)
        for key, value in (('group', 1), ('width', 256), ('elf_sha256', 'b' * 64),
                           ('exact_mixed_elf_spike_executed', True), ('whole_model', True),
                           ('independent_protocol_checked', False), ('child_pid', 123)):
            with self.subTest(field=key), self.assertRaises(ValueError):
                c.accept_run({**row, key: value}, 0, 128, program)

    def test_platform_capacity_and_non_width_fairness(self):
        def platform(w):
            return dict(state='PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED', post_pins_match=True, width=w,
                        source_root='/frozen', prepared_sha256='a' * 64,
                        config=dict(sim_axi_data_width=str(w), qbs_wide_weight_ingress=str(int(w == 256)),
                                    sim_l2_bytes='16777216', nr_lanes='4', vlen='1024'))
        platforms = {w: platform(w) for w in (128, 256)}
        c.platform_fairness(platforms)
        for key, value in (('sim_l2_bytes', '33554432'), ('nr_lanes', '8'),
                           ('qbs_wide_weight_ingress', '0'), ('sim_axi_data_width', '128')):
            bad = copy.deepcopy(platforms)
            bad[256]['config'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.platform_fairness(bad)
        bad = copy.deepcopy(platforms)
        bad[256]['source_root'] = '/other'
        with self.assertRaises(ValueError):
            c.platform_fairness(bad)

    def test_protocol_exact_replay_and_every_identity(self):
        actual = dict(status='PASS', issues=[], log_sha256='a' * 64,
                      vector_trace_sha256='b' * 64, backend_counts={'allocations': 4, 'completions': 4})
        images = {'/simv': 'c' * 64, '/simv.daidir/a.so': 'd' * 64}
        stored = dict(actual, elf_sha256='e' * 64, simv_sha256='c' * 64, sim_image_sha256=images)
        c.protocol_replay(stored, actual, 'e' * 64, 'c' * 64, images)
        for key in stored:
            bad = copy.deepcopy(stored)
            del bad[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                c.protocol_replay(bad, actual, 'e' * 64, 'c' * 64, images)
        for key, value in (('status', 'FAIL'), ('issues', ['unreported error']),
                           ('log_sha256', '0' * 64), ('elf_sha256', '0' * 64),
                           ('sim_image_sha256', {'/simv': 'c' * 64}),
                           ('backend_counts', {'allocations': 4, 'completions': 3})):
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.protocol_replay({**stored, key: value}, actual, 'e' * 64, 'c' * 64, images)

    def test_prefix_is_exact_zero_offset_not_same_length_substitute(self):
        full = bytes(range(256)) + b'\xff' * 256
        prefix = full[:256]
        sha = hashlib.sha256(prefix).hexdigest()
        c.prefix_proof('rvv_0.bin', full, prefix, sha, full.hex())
        for raw, sub, expected, isa in ((full, full[256:], sha, full.hex()),
                                         (full, prefix, '0' * 64, full.hex()),
                                         (full, prefix, sha, ('00' * 512)),
                                         (prefix, prefix, sha, prefix.hex())):
            with self.assertRaises(ValueError):
                c.prefix_proof('rvv_0.bin', raw, sub, expected, isa)
        # Native and RVV are separate oracles; no forced equality or tolerance relaxation.
        native = b'\x55' * 512
        c.prefix_proof('native_0.bin', native, native[:256], hashlib.sha256(native[:256]).hexdigest())

    def test_pin_content_expected_hash_and_symlink_retarget(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a, b, link = root / 'a', root / 'b', root / 'link'
            a.write_bytes(b'same')
            b.write_bytes(b'same')
            link.symlink_to(a)
            pins = c.Pins()
            pins.add(link, c.sha(a))
            pins.verify()
            link.unlink()
            link.symlink_to(b)
            with self.assertRaises(ValueError):
                pins.verify()
            with self.assertRaises(ValueError):
                pins.add(link)
            pins = c.Pins()
            pins.add(a)
            a.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                pins.verify()
            with self.assertRaises(ValueError):
                c.Pins().add(a, '0' * 64)

    def test_consumed_pin_must_exist_and_not_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source'
            path.write_text('data')
            key, digest = str(path.resolve()), c.sha(path)
            c.bound(c.Pins(), path, [{key: digest}, {key: digest}])
            for inventories in ([], [{}], [{key: digest}, {key: '0' * 64}]):
                with self.assertRaises(ValueError):
                    c.bound(c.Pins(), path, inventories)


class LedgerTests(unittest.TestCase):
    def test_stage_shared_region_only_partition_and_no_n_scaling(self):
        measured = fake_measured()
        result = c.ledger(measured)
        self.assertEqual(len(result['parts']), 7)
        self.assertEqual(len(result['preparation_stages']), 4)
        self.assertEqual(result['preparation_stages'][0]['shared_by_parts'], [0, 1, 2])
        self.assertFalse(result['whole_model'])
        self.assertFalse(result['continuous_seven_part_run'])
        self.assertFalse(result['exact_mixed_elf_spike_executed'])
        for p in result['parts']:
            self.assertEqual(p['n'], 64)
            self.assertFalse(p['per_part_region_measured'])
            self.assertEqual(p['group'], int(p['part'] == 5))
            for backend in ('rvv', 'native'):
                self.assertEqual(p['width_128_over_256'][backend]['execution'], 2)
        for item in result['noncontinuous_seven_part_ledger']:
            self.assertFalse(item['continuous_measurement'])
            # All four preparation stages, each counted once rather than per part.
            self.assertEqual(item['mean_cycles']['rvv']['preparation'], sum(range(100, 104)))
            self.assertEqual(item['mean_cycles']['native']['preparation'], sum(range(100, 104)))
        for item in result['partitions']:
            self.assertGreater(item['rvv_over_native']['region'], 1)

    def test_missing_partition_wrong_abba_or_crosswidth_identity_rejected(self):
        measured = fake_measured()
        bad = copy.deepcopy(measured)
        del bad[1, 256]
        with self.assertRaises(ValueError):
            c.ledger(bad)
        bad = copy.deepcopy(measured)
        bad[0, 256]['trials'][0]['backend'] = 1
        with self.assertRaises(ValueError):
            c.ledger(bad)
        for key in ('checksum', 'fcsr', 'vcsr', 'vstart', 'k', 'profile'):
            bad = copy.deepcopy(measured)
            bad[0, 256]['parts'][0][key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.ledger(bad)
        bad = copy.deepcopy(measured)
        bad[1, 128]['parts'] = bad[1, 128]['parts'][:-1]
        with self.assertRaises(ValueError):
            c.ledger(bad)

    def test_stats_require_real_positive_two_samples(self):
        for rows in ([], [{'cycles': 1}], [{'cycles': 1}] * 3,
                     [{'cycles': 1}, {'cycles': 0}], [{'cycles': 1}, {'cycles': True}]):
            with self.assertRaises(ValueError):
                c.stats(rows, ('cycles',))
        self.assertEqual(c.stats([{'cycles': 3}, {'cycles': 4}], ('cycles',))['cycles'],
                         dict(samples=[3, 4], sum=7, mean=3.5))


if __name__ == '__main__':
    unittest.main()
