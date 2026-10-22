import copy
import unittest
from unittest.mock import patch

import admit_sv39_alias771 as a


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q = a.life.read_bound(a.QUAL / 'qualification.json', a.QUAL_SHA)
        cls.replay = a.life.read_bound(a.REPLAY / 'qualification.json', a.REPLAY_SHA)

    def reject(self, mutate):
        q = copy.deepcopy(self.q)
        mutate(q)
        with self.assertRaises(ValueError):
            a.contract(q)

    def test_real_qualified(self):
        a.contract(self.q)

    def test_actual_parent_replay(self):
        a.replay_equal(self.q, self.replay)

    def test_failed_status(self):
        self.reject(lambda q: q.update(status='FAILED'))

    def test_baseline_fork(self):
        self.reject(lambda q: q.update(baseline=769))

    def test_wrong_elf(self):
        self.reject(lambda q: q.update(elf_sha256='0' * 64))

    def test_wrong_run(self):
        self.reject(lambda q: q.update(run='/foreign'))

    def test_scalar_skip(self):
        self.reject(lambda q: q['scalar']['scalar'].update(skipped_unobservable_register_values=1))

    def test_scalar_retirement_missing_traps(self):
        self.reject(lambda q: q['scalar']['scalar'].update(ara_retired_instructions=55215))

    def test_compressed_memory_missing(self):
        self.reject(lambda q: q['scalar']['scalar']['complete_scalar_memory_postaudit'].update(
            compressed_memory_accesses=3713))

    def test_active_byte_missing(self):
        self.reject(lambda q: q['native'].update(known_active_bytes=7359))

    def test_tail_oracle_missing(self):
        self.reject(lambda q: q['native'].update(full_tail_checked_by_3_VRF_snapshots=False))

    def test_full_page_missing(self):
        self.reject(lambda q: q['observations'].update(full_page_phase_bytes=12287))

    def test_full_vrf_missing(self):
        self.reject(lambda q: q['observations'].update(full_VRF_bytes=12287))

    def test_guard_missing(self):
        self.reject(lambda q: q['observations'].update(full_guard_readback=False))

    def test_unknown_vector_record(self):
        self.reject(lambda q: q['vector']['instructions'][0].update(unknown_write_bytes=1))

    def test_lost_response(self):
        self.reject(lambda q: q['lifecycle'].update(responses=216))

    def test_pending_protocol(self):
        self.reject(lambda q: q['protocol'].update(outstanding=1))

    def test_lost_final_w(self):
        self.reject(lambda q: q['metadata'].update(total_external_final_W=146))

    def test_non_preedge(self):
        self.reject(lambda q: q['metadata'].update(preedge_sampling=False))

    def test_missing_fifo_slot(self):
        self.reject(lambda q: q['metadata']['pushes'][1].update(
            pointer=q['metadata']['pushes'][0]['pointer']))

    def test_wrong_virtual_phase(self):
        self.reject(lambda q: q['metadata']['pushes'][0].update(vaddr=0))

    def test_zero_gain(self):
        self.reject(lambda q: q['raw_gain'].update(toggle_binary_new_positions=0))

    def test_fsm_false_gain(self):
        self.reject(lambda q: q['raw_gain']['four_metrics']['metrics'].update(fsm=1))

    def test_replay_instruction_mutation(self):
        q = copy.deepcopy(self.replay)
        q['vector']['instructions'][0]['pc'] = '0x0'
        with self.assertRaises(ValueError):
            a.replay_equal(self.q, q)

    def test_replay_scope_position_mutation(self):
        q = copy.deepcopy(self.replay)
        q['raw_gain']['toggle_binary_instances'][0]['positions'][0] += 1
        with self.assertRaises(ValueError):
            a.replay_equal(self.q, q)

    def test_foreign_parent_before_reads(self):
        with patch.object(a.life, 'read_bound', side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):
                a.evaluate(a.REPLAY, '0' * 64)

    def test_pin_conflict(self):
        with self.assertRaises(ValueError):
            a.life.merge_pins({'/p': 'a' * 64}, {'/p': 'b' * 64})


class Union(unittest.TestCase):
    def fixture(self):
        metrics = {m: {} for m in a.case.bitmap.METRICS}
        for i in range(6162):
            metric = a.case.bitmap.METRICS[i % 4]
            metrics[metric]['scope' + str(i)] = dict(bits='1', width=2, checksum='1')
        before = dict(tests=['test' + str(i) for i in range(770)], design={'cond': 'a'},
                      metrics=metrics, input_hashes={'/before': 'a' * 64})
        single = copy.deepcopy(before)
        single.update(tests=[str(a.case.RUN / 'code.vdb')], input_hashes={'/single': 'b' * 64})
        for rows in single['metrics'].values():
            for row in rows.values():
                row['bits'] = '2'
        return before, single

    def test_full6162_or_prefix(self):
        before, single = self.fixture()
        after = a.union(before, single)
        self.assertEqual(after['tests'], before['tests'] + single['tests'])
        self.assertTrue(all(int(row['bits'], 16) == 3 for rows in after['metrics'].values() for row in rows.values()))

    def test_duplicate_baseline(self):
        before, single = self.fixture()
        before['tests'][1] = before['tests'][0]
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_duplicate_vdb(self):
        before, single = self.fixture()
        before['tests'][0] = single['tests'][0]
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_foreign_single(self):
        before, single = self.fixture()
        single['tests'] = ['foreign']
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_incompatible_shape(self):
        before, single = self.fixture()
        next(iter(single['metrics'].values()))['scope0']['width'] = 3
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_wrong_design(self):
        before, single = self.fixture()
        single['design'] = {'cond': 'b'}
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_lost_instance(self):
        before, single = self.fixture()
        del single['metrics'][a.case.bitmap.METRICS[0]]['scope0']
        with self.assertRaises(ValueError):
            a.union(before, single)

    def test_bad_or_even_when_combine_claims_pass(self):
        before, single = self.fixture()
        bad = a.case.bitmap.combine(before, single)
        bad['metrics'][a.case.bitmap.METRICS[0]]['scope0']['bits'] = '2'
        with patch.object(a.case.bitmap, 'combine', return_value=bad):
            with self.assertRaises(ValueError):
                a.union(before, single)


class AdmittedVerify(unittest.TestCase):
    def setUp(self):
        self.out = a.life.OUT / 'test-not-created-formal771'
        self.proposal = dict(input_pins={'/input': 'a' * 64}, output_pins={'/output': 'b' * 64},
                             coverage_admitted=False)
        self.manifest = dict(self.proposal, coverage_admitted=True,
            prepared=str(self.out.with_name(self.out.name + '.prepared.json')),
            prepared_seal='c' * 64,
            authorization_source='EXPLICIT_PARENT_REPLAY_PASS_AND_ADMISSION_AUTHORIZATION')

    def test_readonly_recompute_all_pins(self):
        with patch.object(a.life, 'read_bound', side_effect=[self.manifest, self.proposal]), \
                patch.object(a.life, 'check') as checked, \
                patch.object(a.life, 'save', side_effect=AssertionError('no writes')):
            a.verify_admitted(self.out, self.proposal, 'd' * 64)
            self.assertEqual([c.args[0] for c in checked.call_args_list],
                             [self.proposal['input_pins'], self.proposal['output_pins']])

    def test_false_admission_rejected(self):
        self.manifest['coverage_admitted'] = False
        with patch.object(a.life, 'read_bound', return_value=self.manifest):
            with self.assertRaises(ValueError):
                a.verify_admitted(self.out, self.proposal, 'd' * 64)

    def test_prepared_contract_drift(self):
        with patch.object(a.life, 'read_bound', side_effect=[self.manifest, {}]):
            with self.assertRaises(ValueError):
                a.verify_admitted(self.out, self.proposal, 'd' * 64)


class HistoricalPins(unittest.TestCase):
    def test_actual_exact_relative_plan(self):
        normalized = a.qualification_pins({a.LEGACY_PLAN: a.LEGACY_PLAN_SHA})
        self.assertEqual(normalized, {str(a.life.ROOT / a.LEGACY_PLAN): a.LEGACY_PLAN_SHA})

    def test_foreign_relative(self):
        with self.assertRaises(ValueError):
            a.qualification_pins({'verification/out/foreign.json': 'a' * 64})

    def test_changed_expected_sha(self):
        with self.assertRaises(ValueError):
            a.qualification_pins({a.LEGACY_PLAN: 'a' * 64})

    def test_changed_actual_bytes(self):
        with patch.object(a.life, 'digest', return_value='a' * 64):
            with self.assertRaises(ValueError):
                a.qualification_pins({a.LEGACY_PLAN: a.LEGACY_PLAN_SHA})

    def test_absolute_conflict(self):
        with self.assertRaises(ValueError):
            a.qualification_pins({a.LEGACY_PLAN: a.LEGACY_PLAN_SHA,
                                 str(a.life.ROOT / a.LEGACY_PLAN): 'a' * 64})


if __name__ == '__main__':
    unittest.main()
