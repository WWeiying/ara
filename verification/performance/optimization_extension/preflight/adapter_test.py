import unittest
import adapter_run as a


def receipt():
    return dict(state='M4_ADAPTER_GATE_REVIEWED', enabled_k=[1536, 2048, 4096],
                live_overlays={name: 'a'*64 for name in a.OVERLAYS})


def benchmark():
    return dict(state='M4_PREFLIGHT_FRAMING_AUDIT_CHECKED', post_pins_match=True, post_image_match=True,
                original_worker_state='FAIL', original_result_sha256=a.ORIGINAL_RESULT,
                raw_log_sha256=a.RAW_SHA, vector_trace_sha256=a.VECTOR_SHA, original_report_preserved=True,
                simulation_rerun=False, complete_numerical=True, complete_raw_protocol=True,
                performance_measured=True, trials=8, uart_fragments=24, csr_probe_interruptions=16,
                cycle_metrics=[dict(k=k, baseline_mean=100, candidate_mean=90, cycle_reduction_fraction=.1)
                               for k in (2048, 4096)])


def fixture(k, case, gate=1):
    if case == 8:
        return ('0x0000000000000000\nM4_ADAPTER_VSTART_PASS k='+str(k)+
                ' candidate_delta=0 generic_delta=0 cache_queries_delta=0 untouched=1 vstart=1\n')
    rejected = case in (7, 9, 10, 16)
    selected = int(bool(gate) and case not in (1, 2, 3, 4, 5, 6, 9, 10, 16))
    computations = 0 if rejected else 4 if case == 0 else 2 if case == 17 else 1
    hits = 0 if rejected or 11 <= case <= 15 else 256 if case == 0 else 1
    queries = 0 if rejected else 261 if case == 0 else 4 if case == 17 else 1 if 11 <= case <= 15 else 3
    stores = 0 if rejected or 11 <= case <= 15 else 4 if case == 0 else 1
    row = dict(k=k, case=case, selected=selected, checks=100, candidate_entries=selected*computations,
               generic_entries=int(11 <= case <= 14), computations=computations,
               queries=queries, hits=hits, misses=queries-hits, stores=stores, allocation_failures=int(case == 15),
               planner_calls=0 if case == 9 else 2, bytes=k//256*1168, payload_hash=123,
               guards=1, input_preserved=1, errors=0)
    extra = ('M4_ADAPTER_INVALIDATION_PASS k='+str(k)+
             ' quartet_last_byte=1 epoch=1 source=1 computations=4\n') if case == 0 else ''
    return '0x0000000000000000\n'+extra+'M4_ADAPTER_PASS'+''.join(' '+key+'='+str(value)
        for key, value in row.items())+'\n'


class Tests(unittest.TestCase):
    def test_all_case_parse_shapes_and_header_off(self):
        for k in (2048, 4096):
            for case in range(len(a.CASES)):
                for gate in (0, 1):
                    with self.subTest(k=k, case=case, gate=gate):
                        self.assertEqual(a.check_log(fixture(k, case, gate), k, case, gate)['state'], 'PASS')

    def test_negative_log_structure_and_exit(self):
        text = fixture(4096, 0)
        for bad in (text.replace('bytes=18688', 'bytes=9344'), text.replace('guards=1', 'guards=0'),
                    text.replace('selected=1', 'selected=0'), text.replace('candidate_entries=4', 'candidate_entries=1'),
                    text.replace('computations=4', 'computations=3'), text.replace('errors=0', 'errors=1'),
                    text.replace('selected=1', 'selected=1 selected=1'), text+'M4_ADAPTER_EXTRA\n',
                    text.replace('0x0000000000000000', '0x0000000000000001'), text+'TRAP cause=2\n',
                    text.replace('quartet_last_byte=1', 'quartet_last_byte=0')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                a.check_log(bad, 4096, 0, 1)

    def test_late_special_must_be_single_generic(self):
        for case in (11, 12, 13, 14):
            for count in (0, 2):
                with self.subTest(case=case, count=count), self.assertRaises(ValueError):
                    a.check_log(fixture(2048, case).replace('generic_entries=1', 'generic_entries='+str(count)),
                                2048, case, 1)

    def test_vstart_abort_no_side_effects(self):
        text = fixture(2048, 8)
        for old, new in (('vstart=1', 'vstart=0'), ('candidate_delta=0', 'candidate_delta=1'),
                         ('cache_queries_delta=0', 'cache_queries_delta=1'), ('untouched=1', 'untouched=0')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                a.check_log(text.replace(old, new), 2048, 8, 1)

    def test_disabled_and_rejected_no_candidate(self):
        for case in (1, 2, 3, 4, 5, 6, 7, 9, 10, 16):
            with self.subTest(case=case), self.assertRaises(ValueError):
                a.check_log(fixture(2048, case).replace('candidate_entries=0', 'candidate_entries=1'),
                            2048, case, 1)

    def test_only_reviewed_positive_gate(self):
        self.assertEqual(a.gate_contract(receipt(), benchmark()), [1536, 2048, 4096])
        for change in (dict(state='DRAFT'), dict(enabled_k=[2048, 4096]), dict(enabled_k=[1536, 2048, 6144]),
                       dict(enabled_k=[1536, 2048, 2048]), dict(enabled_k=[1536, '2048']),
                       dict(live_overlays={'qbs.cpp': 'a'*64})):
            with self.subTest(change=change), self.assertRaises(ValueError):
                a.gate_contract(dict(receipt(), **change), benchmark())
        for change in (dict(state='RUNNING'), dict(state='PASS'), dict(state='M4_EXTENSION_PREFLIGHT_VCS_CHECKED'),
                       dict(post_image_match=False), dict(post_pins_match=False), dict(original_worker_state='PASS'),
                       dict(original_result_sha256=''), dict(raw_log_sha256=''), dict(complete_numerical=False),
                       dict(vector_trace_sha256=''), dict(original_report_preserved=False),
                       dict(complete_raw_protocol=False), dict(simulation_rerun=True), dict(trials=7),
                       dict(uart_fragments=25), dict(csr_probe_interruptions=15)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                a.gate_contract(receipt(), dict(benchmark(), **change))
        for candidate in (100, 110):
            result = benchmark(); result['cycle_metrics'][0]['candidate_mean'] = candidate
            with self.assertRaises(ValueError): a.gate_contract(receipt(), result)
        result = benchmark(); result['cycle_metrics'][1]['candidate_mean'] = 110
        gate = receipt(); gate['enabled_k'] = [1536, 2048]
        self.assertEqual(a.gate_contract(gate, result), [1536, 2048])

    def test_owned_sources_exclude_sealed_bench(self):
        self.assertEqual(a.OWN, ('adapter_run.py', 'adapter_target.cpp', 'adapter_test.py'))
        self.assertNotIn('qbs.cpp', a.OVERLAYS)

    def test_no_empty_or_implicit_evidence_paths(self):
        for path in ('', ' ', None, [], {}, '.', '/tmp', str(a.OUT)):
            with self.subTest(path=path), self.assertRaises((ValueError, FileNotFoundError)):
                a.evidence_directory(path, 'optimization_extension_preflight_')
        for gate in ({}, dict(evidence_kind='PASS'), dict(evidence_kind='framing_audit_v1', benchmark=''),
                     dict(evidence_kind='framing_audit_v1', benchmark=str(a.OUT/'optimization_extension_preflight_20261111_02'),
                          audit_output='')):
            with self.subTest(gate=gate), self.assertRaises(ValueError): a.reviewed_evidence(gate)
        for value in ('', None, 'a'*63, 'g'*64, []):
            with self.subTest(digest=value), self.assertRaises(ValueError): a.digest_value(value)
        binding = dict(evidence_kind='framing_audit_v1',
                       benchmark=str(a.OUT/'optimization_extension_preflight_20261111_02'),
                       audit_output=str(a.OUT/'optimization_extension_preflight_framing_audit_20261111_01'),
                       benchmark_result_sha256='', audit_source_pins_sha256='')
        with self.assertRaises(ValueError): a.reviewed_evidence(binding)


if __name__ == '__main__':
    unittest.main()
