"""Host tests only: exact transforms, identity, service and rejection gates."""
import copy
import json
from pathlib import Path
import unittest

from audit import digest
from check_projection_native import checksum, fields
from check_supply_decode import COUNTERS, WAIT, PHASES
from check_decode_native import CONTEXT_COUNTERS
from check_decode_matched_activity import ACCESS
import decode_partition_driver as driver
import decode_partition_check as checker
import decode_partition_build as builder
from decode_partition_run import accept_program, accept_protocol

HERE = Path(__file__).resolve().parent


def fixture(group, width, slower=False):
    c = driver.contract(group)
    native = [bytes([p+1])*256 for p in range(7)]
    rvv = [bytes([p+11])*256 for p in range(7)]
    packed = [bytes(n) for n in (2336, 2336, 7008, 2336)]
    flags = [0]*7
    lines = [driver.scope(group)]; seq = 0
    for trial, backend in enumerate(driver.ORDER):
        lines.append(f'DECODE_PARTITION_BEGIN group={group} trial={trial} backend={backend}')
        if backend:
            for part in c['parts']:
                for access in ACCESS[part]:
                    seq += 1; blocks = driver.K[part]//256; profile = driver.PROFILE[part]
                    reused = int(access in (2, 3)); activation = blocks*292
                    weight = 32*blocks*(144 if profile == 1 else 210)
                    r = {k: 0 for k in (*COUNTERS, *WAIT, *CONTEXT_COUNTERS)}
                    r.update(seq=seq, m=1, n=32, vlen=1024, lanes=4, success=1, fault=0,
                        validation_fault=0, read_fault=0, useful_pairs=8192*blocks,
                        dot_active_cycles=256*blocks, activation_access=access,
                        activation_bytes=activation, weight_bytes=weight,
                        payload_bytes=16+weight+(0 if reused else activation), context_fill_count=int(access == 1),
                        context_reuse_count=reused, context_reuse_block_count=blocks if reused else 0,
                        context_read_bytes=activation if reused else 0,
                        activation_axi_bytes_saved=activation if reused else 0,
                        ar=1+8*blocks+(0 if reused else blocks), read_ranges=1+8*blocks+(0 if reused else blocks))
                    beats = (36 if profile == 1 else 53) if width == 128 else (18 if profile == 1 else 27)
                    r['r_beats'] = 1+8*blocks*beats+(0 if reused else blocks*19)
                    r['busy_cycles'] = r['r_beats']+10000
                    r.update({'phase_'+p+'_cycles': r['busy_cycles'] if i == 0 else 0 for i, p in enumerate(PHASES)})
                    lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k, v in r.items()))
        for stage in c['stages']:
            lines.append(f'DECODE_PARTITION_PREP trial={trial} backend={backend} stage={stage} cycles=10 '
                         f'fcsr=9 vcsr=3 vstart=0 checksum={checksum(packed[stage])} errors=0')
        exe = 150000 if slower and backend else 100000
        for part in c['parts']:
            lines.append(f'DECODE_PARTITION_PART trial={trial} backend={backend} part={part} '
                         f'profile={driver.PROFILE[part]} k={driver.K[part]} admission=10 execution={exe} '
                         f'fcsr=9 vcsr=3 vstart=0 checksum={checksum((native if backend else rvv)[part])} errors=0')
        prep = len(c['stages'])*10; admission = len(c['parts'])*10; execution = len(c['parts'])*exe
        lines.append(f'DECODE_PARTITION_TRIAL trial={trial} backend={backend} preparation={prep} '
                     f'admission={admission} execution={execution} region={prep+admission+execution+10} '
                     f'commands={2*len(c["parts"]) if backend else 0} '
                     f'q4_calls={0 if backend else c["q4_calls"]} q6_calls={0 if backend else c["q6_calls"]} '
                     f'outputs={64*len(c["parts"])} untouched_errors=0 errors=0')
    lines.extend((checker.terminal(group), checker.CORE, 'UVM_ERROR : 0', 'UVM_FATAL : 0'))
    return '\n'.join(lines), [native, rvv, packed, flags]


class PartitionSource(unittest.TestCase):
    def test_exact_both_groups_and_inverse(self):
        source = (HERE/'decode_matched.cpp').read_text()
        self.assertEqual(digest(HERE/'decode_matched.cpp'), driver.SOURCE_SHA)
        for g in (0, 1):
            text, proof = driver.transform(source, g)
            restored = text.replace('DECODE_PARTITION_', 'MATCHED_DECODE_')
            for edit in reversed(proof['edits']): restored = restored.replace(edit['after'], edit['before'])
            self.assertEqual(restored, source)
            self.assertIn(driver.scope(g), text)
            self.assertIn('finished[p]=completed_state();\n            const uint64_t c=cycle();', text)
            self.assertIn('prepared[s]=completed_state();\n                prep[s]=cycle()-start;', text)
            prefix = source[:source.index('int main()')]
            # Only the two selector arrays were added before main.
            for line in text[:text.index('int main()')].splitlines(keepends=True):
                if 'static constexpr bool Selected' in line or 'static constexpr bool UsedStage' in line: continue
                self.assertIn(line, prefix)

    def test_source_drift_and_invalid_group_reject(self):
        source = (HERE/'decode_matched.cpp').read_text()
        for changed in (source+'\n', source.replace('N=64', 'N=32', 1)):
            with self.assertRaises(ValueError): driver.transform(changed, 0)
        for g in (-1, 2, True, '0'):
            with self.assertRaises(ValueError): driver.contract(g)

    def test_partitions_disjoint_full_k_and_original_stages(self):
        a, b = (driver.contract(g) for g in (0, 1))
        self.assertEqual(sorted(a['parts']+b['parts']), list(range(7)))
        self.assertEqual(a['native_commands'], 24); self.assertEqual(b['native_commands'], 4)
        self.assertEqual(a['outputs_checked']+b['outputs_checked'], 1792)
        self.assertEqual([a['pairs_per_backend'], b['pairs_per_backend']], [786432, 393216])
        self.assertEqual(a['stages'], [0, 1, 3]); self.assertEqual(b['stages'], [2])

    def test_link_changes_only_driver_and_output_paths(self):
        records = json.loads((builder.BASE/'commands.json').read_text())
        old = builder.parent.labelled(records, 'link')
        new = builder.link_recipe(old, Path('/new/driver.o'), Path('/new/a.elf'), Path('/new/link.map'))
        self.assertEqual(len(builder.parent.objects(new)), 16)
        diff = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(diff), 3)
        self.assertIn((str(builder.BASE/'driver.o'), '/new/driver.o'), diff)
        with self.assertRaises(ValueError): builder.link_recipe(old+['extra.o'], Path('/x'), Path('/y'), Path('/z'))


class PartitionChecks(unittest.TestCase):
    def test_complete_both_groups_both_physical_widths(self):
        for g in (0, 1):
            for width in (128, 256):
                text, oracle = fixture(g, width); r = checker.check(text, g, width, *oracle)
                self.assertEqual(r['outputs_checked'], 1536 if g == 0 else 256)
                self.assertEqual(len(r['native_activity']), 12 if g == 0 else 2)
                self.assertFalse(r['external_individual_words_dumped'])
                self.assertFalse(r['independent_protocol_checked'])
                self.assertFalse(r['continuous_seven_part_run'])

    def test_slower_native_is_not_rejected(self):
        text, oracle = fixture(1, 256, True)
        self.assertLess(checker.check(text, 1, 256, *oracle)['speedups']['region'], 1)

    def test_wrong_group_width_or_oracle_rejects(self):
        text, oracle = fixture(0, 128)
        with self.assertRaises(ValueError): checker.check(text, 1, 128, *oracle)
        with self.assertRaises(ValueError): checker.check(text, 0, 256, *oracle)
        bad = list(oracle); bad[0], bad[1] = bad[1], bad[0]
        with self.assertRaises(ValueError): checker.check(text, 0, 128, *bad)

    def test_eoc_failed_nonzero_duplicate_and_missing_reject(self):
        text, oracle = fixture(1, 128)
        for extra in ('Core Test *** FAILED *** (tohost = 1)',
                      'Core Test *** SUCCESS *** (tohost = 1)', checker.CORE):
            with self.subTest(extra=extra), self.assertRaises(ValueError): checker.check(text+'\n'+extra, 1, 128, *oracle)
        with self.assertRaises(ValueError): checker.check(text.replace(checker.CORE, ''), 1, 128, *oracle)

    def test_every_numeric_payload_csr_guard_and_count_gate(self):
        text, oracle = fixture(0, 128)
        mutations = [('vcsr=3', 'vcsr=5'), ('fcsr=9', 'fcsr=8'), ('vstart=0', 'vstart=1'),
                     ('stage=3', 'stage=2'), ('part=6', 'part=5'), ('k=2048', 'k=6144'),
                     ('outputs=384', 'outputs=448'), ('q6_calls=128', 'q6_calls=192'),
                     ('commands=12', 'commands=14'), ('untouched_errors=0', 'untouched_errors=1'),
                     ('errors=0', 'errors=1'), ('checksum=', 'wrong_checksum='), ('region=600100', 'region=1')]
        for old, new in mutations:
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError): checker.check(text.replace(old, new, 1), 0, 128, *oracle)

    def test_native_sequence_context_geometry_and_exact_beats(self):
        text, oracle = fixture(0, 256)
        for old, new in [('seq=1 ', 'seq=2 '), ('n=32 ', 'n=16 '), ('activation_access=1 ', 'activation_access=0 '),
                         ('read_fault=0 ', 'read_fault=1 '), ('weight_bytes=36864 ', 'weight_bytes=36863 '),
                         ('context_fill_count=1 ', 'context_fill_count=0 '), ('r_beats=1305 ', 'r_beats=1299 ')]:
            self.assertIn(old, text)
            with self.subTest(old=old), self.assertRaises(ValueError): checker.check(text.replace(old, new, 1), 0, 256, *oracle)

    def test_hardware_ownership_and_order_not_just_aggregate(self):
        text, oracle = fixture(1, 128); lines = text.splitlines()
        command = next(line for line in lines if line.startswith('[QBS_PERF] '))
        for changed in (text+'\n'+command, command+'\n'+text,
                        text.replace(command+'\n', '', 1), text.replace(command, command+'\n'+command, 1),
                        text+'\n[AKV_PERF] seq=1', text.replace(command, 'prefix '+command, 1)):
            with self.assertRaises(ValueError): checker.check(changed, 1, 128, *oracle)

    def test_no_legacy_partial_unknown_or_duplicate_terminal(self):
        text, oracle = fixture(1, 128)
        for changed in (text.replace('DECODE_PARTITION_', 'MATCHED_DECODE_'), text+'\n'+checker.terminal(1),
                        text+'\nDECODE_PARTITION_BOGUS a=1', text.replace('DECODE_PARTITION_PREP ', 'OMITTED ', 1),
                        text.replace('DECODE_PARTITION_RESULT group=1', 'DECODE_PARTITION_RESULT group=0', 1)):
            with self.assertRaises(ValueError): checker.check(changed, 1, 128, *oracle)

    def test_uvm_and_failure_noise_rejected(self):
        text, oracle = fixture(1, 256)
        for extra in ('Fatal: unexpected', 'Error: unexpected', 'UVM_ERROR : 0', 'UVM_ERROR : 1', 'TIMEOUT'):
            with self.subTest(extra=extra), self.assertRaises(ValueError): checker.check(text+'\n'+extra, 1, 256, *oracle)

    def test_busy_phase_and_wait_cannot_be_forged_consistently(self):
        text, oracle = fixture(0, 256); lines = text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('[QBS_PERF] '))
        row = fields(lines[index], '[QBS_PERF]'); row['busy_cycles'] = row['dot_active_cycles']-1
        for p in PHASES: row['phase_'+p+'_cycles'] = 0
        row['phase_'+PHASES[0]+'_cycles'] = row['busy_cycles']
        lines[index] = '[QBS_PERF] '+' '.join(f'{k}={v}' for k, v in row.items())
        with self.assertRaises(ValueError): checker.check('\n'.join(lines), 0, 256, *oracle)


class PartitionAdmission(unittest.TestCase):
    def report(self):
        return dict(state='DECODE_PARTITIONS_BUILT_NOT_EXECUTED', target_executed=False, rtl_executed=False,
                    performance_measured=False, production_library_changed=False, whole_model=False,
                    parent_build_sha256=builder.BASE_SHA, parent_elf_sha256=builder.BASE_ELF_SHA,
                    compiled_translation_units=2, arithmetic_objects_recompiled=False,
                    order=[0, 1, 1, 0], post_pins_match=True,
                    groups=[driver.contract(0), driver.contract(1)], reused_objects={str(i): 'sha' for i in range(15)})

    def test_exact_program_and_every_missing_gate(self):
        r = self.report(); accept_program(r, 0); accept_program(r, 1)
        for key in r:
            bad = copy.deepcopy(r); del bad[key]
            with self.subTest(key=key), self.assertRaises(ValueError): accept_program(bad, 0)
        for change in (dict(performance_measured=True), dict(compiled_translation_units=3), dict(order=[1, 0, 0, 1])):
            with self.assertRaises(ValueError): accept_program(dict(r, **change), 0)
        bad = self.report(); bad['groups'][0]['parts'] = list(range(7))
        with self.assertRaises(ValueError): accept_program(bad, 0)

    def test_protocol_identity_every_field(self):
        p = dict(status='PASS', elf_sha256='elf', log_sha256='log', vector_trace_sha256='trace', sim_image_sha256={'sim': 'sha'})
        accept_protocol(p, 'elf', 'log', 'trace', {'sim': 'sha'})
        for key in p:
            bad = dict(p); bad[key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(ValueError): accept_protocol(bad, 'elf', 'log', 'trace', {'sim': 'sha'})

    def test_runner_never_waits_or_launches_without_explicit_review_flag(self):
        text = (HERE/'decode_partition_run.py').read_text()
        self.assertNotIn('wait_predecessor', text)
        self.assertNotIn('accepted_predecessor', text)
        self.assertIn("'--require-axi-write'", text)
        self.assertIn("'--execute-reviewed', action='store_true'", text)
        self.assertIn('timeout <= 10800', text)


if __name__ == '__main__': unittest.main()
