"""Pure/mocked admission and exact-layout negatives; never invokes EDA."""
import copy
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/coverage'))
sys.path.insert(0, str(ROOT / 'verification/tests'))
import gap65_late_fault_checks as c
import coverage_evidence as e
import run_gap65_late_fault_checked_extension as adapter


def fixture():
    fixed = {'_start': 0x80000000, '__gap65_stack_guard_low': 0x80100000,
             '__gap65_stack_bottom': 0x80100040, '__gap65_stack_top': 0x80110000,
             '__gap65_stack_guard_high': 0x80110000, '__gap65_tail_guard': 0x801ffd80,
             '__gap65_tail_weights': 0x801ffdc0, '__gap65_tail_end': 0x80200000,
             'rvtest_init': 0x80000100, 'gap65_fault_site': 0x80000200, 'gap65_recovery_site': 0x80000300}
    sizes = {'gap65_seed': 640, 'gap65_observed': 640, 'gap65_activation': 1296,
             'gap65_descriptor': 144, 'gap65_csrs': 224, 'gap65_trap': 160, 'gap65_boot': 40}
    symbols = [dict(Name={'Name': n}, Value=v, Size=0) for n, v in fixed.items()]
    symbols += [dict(Name={'Name': n}, Value=0x80004000 + i * 0x1000, Size=s)
                for i, (n, s) in enumerate(sizes.items())]
    def section(n, start, size, kind, flags):
        return {'Section': dict(Name={'Name': n}, Address=start, Size=size, Offset=0,
                                Type={'Name': kind}, Flags={'Value': flags})}
    meta = dict(Symbols=[{'Symbol': s} for s in symbols], ProgramHeaders=[], Sections=[
        section('.text', 0x80000000, 0x1000, 'SHT_PROGBITS', 6),
        section('.gap65_stack', 0x80100000, 0x10040, 'SHT_NOBITS', 3),
        section('.gap65_tail', 0x801ffd80, 640, 'SHT_NOBITS', 3)])
    blob = bytearray(4096)
    for offset, word in ((0x100, 0x10393), (0x104, 0x00110117), (0x108, 0xefc10113),
                         (0x200, 0x06b5045b), (0x300, 0x06b5045b)):
        struct.pack_into('<I', blob, offset, word)
    return meta, blob


class LayoutTests(unittest.TestCase):
    def test_exact_layout_and_stack_relocation(self):
        proof = c.elf_proof(*fixture())
        self.assertTrue(proof['stack_relocated_before_C'])
        self.assertEqual(proof['high_weight'] & proof['ram_alias_mask'], 0x1ffdc0)

    def test_unsafe_old_stack_rejected(self):
        meta, blob = fixture()
        next(s['Symbol'] for s in meta['Symbols'] if s['Symbol']['Name']['Name'] == '__gap65_stack_top')['Value'] = 0x80200000
        with self.assertRaisesRegex(ValueError, 'boundary'):
            c.elf_proof(meta, blob)

    def test_each_entry_instruction_mutation_rejected(self):
        for offset in (0x100, 0x104, 0x108):
            meta, blob = fixture()
            blob[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                c.elf_proof(meta, blob)

    def test_m1_instruction_not_accepted_as_m4(self):
        meta, blob = fixture()
        struct.pack_into('<I', blob, 0x200, 0x00b5045b)
        with self.assertRaisesRegex(ValueError, 'M4'):
            c.elf_proof(meta, blob)

    def test_orphan_and_allocated_tail_file_bytes(self):
        for mode in ('orphan', 'file', 'boundary'):
            meta, blob = fixture()
            s = meta['Sections'][-1]['Section']
            if mode == 'orphan': s['Name']['Name'] = '.unknown'
            if mode == 'file': s['Type']['Name'] = 'SHT_PROGBITS'
            if mode == 'boundary': s['Size'] += 8
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                c.elf_proof(meta, blob)

    def test_buffer_size_alignment_bounds(self):
        for key, value in (('Size', 512), ('Value', 0x801ffdc0), ('Value', 0x80004001)):
            meta, blob = fixture()
            s = next(x['Symbol'] for x in meta['Symbols'] if x['Symbol']['Name']['Name'] == 'gap65_seed')
            s[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                c.elf_proof(meta, blob)


class OracleTests(unittest.TestCase):
    def test_independent_nonzero_distinct_outputs(self):
        v = c.vectors()
        self.assertEqual(len(set(v['expected_bits'])), 16)
        self.assertEqual(len(bytes.fromhex(v['weight_image'])), 640)
        self.assertEqual(len(bytes.fromhex(v['activation_image'])), 1296)
        self.assertTrue(any(x['dot'] < 0 for x in v['scalar']))

    def test_bsum_corruption_and_truncation(self):
        v = c.vectors()
        w, a = bytes.fromhex(v['weight_hex']), bytearray.fromhex(v['activation_hex'])
        a[260] ^= 1
        with self.assertRaisesRegex(ValueError, 'bsum'):
            c.scalar_oracle(w, a)
        with self.assertRaisesRegex(ValueError, 'length'):
            c.scalar_oracle(w[:-1], a)

    def test_numerical_payload_change_not_invisible(self):
        v = c.vectors()
        w, a = bytearray.fromhex(v['weight_hex']), bytes.fromhex(v['activation_hex'])
        w[16] ^= 1
        self.assertNotEqual(c.scalar_oracle(w, a)[0], v['expected_bits'])

    def test_exact_trap_pc_count_and_no_short_check(self):
        proof = c.elf_proof(*fixture())
        log = ('GAP65 traps=1 cause=5 tval=c0000000 pc=80000200 fault_vrf=128 '
               'recovery_vrf=128 numerical=16 errors=0\nPASSED: ' + c.NAME + ' checks=49 errors=0\n')
        c.check_runtime_log(log, proof)
        for old, new in (('traps=1', 'traps=0'), ('cause=5', 'cause=13'), ('pc=80000200', 'pc=80000300'),
                         ('tval=c0000000', 'tval=0'), ('fault_vrf=128', 'fault_vrf=32'), ('checks=49', 'checks=47')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                c.check_runtime_log(log.replace(old, new), proof)

    def test_raw_neighbor_not_target(self):
        before = dict(checksum='2676500856', width=43, bits='0x0')
        target = dict(before, bits=hex(1 << (42 - 15)))
        c.check_target_delta(before, target)
        for index in (14, 16, 31):
            with self.subTest(index=index), self.assertRaises(ValueError):
                c.check_target_delta(before, dict(before, bits=hex(1 << (42 - index))))
        with self.assertRaises(ValueError): c.check_target_delta(target, target)

    def test_state_witness_not_aggregate_or_load_fault(self):
        samples = [dict(cycle=100, rst_n=1, state=3, next_state=10, fault=1),
                   dict(cycle=101, rst_n=1, state=10, next_state=10, fault=1)]
        c.check_state_samples(samples)
        for row, key, val in ((0, 'state', 2), (0, 'fault', 0), (1, 'state', 2), (1, 'cycle', 102), (1, 'rst_n', 0)):
            bad = copy.deepcopy(samples); bad[row][key] = val
            with self.subTest(key=key, val=val), self.assertRaises(ValueError): c.check_state_samples(bad)


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='gap65-late-fault-preflight-unit-', dir=ROOT / 'verification/out')
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.elf = self.out / 'toy.elf'; self.elf.write_bytes(b'TOY_A')
        self.record = self.out / 'toy.json'; c.save(self.record, {})
        self.item = dict(name=adapter.CASE, timeout_s=300, binary=str(self.elf),
            sources=['fixture.c'], precheck=dict(format='accel-host-v1', record=str(self.record)))
        self.result = dict(scope='host-reference-only', name=adapter.CASE, elf_sha256=c.sha(self.elf))
        self.draft = self.out / 'selection.checked-draft.json'; c.save(self.draft, dict(cases=[self.item]))
        for n in adapter.MANIFESTS: c.save(self.out / n, {str(self.elf): c.sha(self.elf)})
        c.save(self.out / 'cost-preflight.json', dict(status='CONDITIONAL_STATIC_BUDGET',
            proposed_timeout_s=300, conditional_seconds_upper=200, input_hashes={str(self.elf): c.sha(self.elf)}))
        proof = e.Evidence(); proof.pin(self.draft)
        for n in adapter.MANIFESTS: proof.hashes(proof.read(self.out / n))
        self.delegate(self.item, proof)
        self.saved = dict(status='PASS', scope='host-reference-only', vcs_launched=False,
            read_only_validation=True, observer_launch_admitted=False, result=self.result, checked_files=proof.files)
        self.reseal()

    def delegate(self, item, proof):
        proof.pin(self.elf, self.result['elf_sha256']); return copy.deepcopy(self.result)

    def reseal(self):
        saved = self.out / 'checked-precheck.json'; c.save(saved, self.saved)
        c.save(self.out / 'draft.sha256.json', {str(p): c.sha(p) for p in
               (self.draft, saved, self.out / 'artifact_hashes.json')})

    def gate(self, item=None): return adapter.precheck(item or self.item, e.Evidence(), self.delegate)

    def test_frozen_positive_no_subprocess(self):
        with patch('subprocess.Popen', side_effect=AssertionError('subprocess forbidden')):
            self.assertEqual(self.gate(), self.result)

    def test_case_mutations_rejected_before_delegate(self):
        for key, value in (('timeout_s', 301), ('sources', ['different.c']), ('binary', '/other.elf')):
            with self.subTest(key=key), self.assertRaises(ValueError): self.gate(dict(self.item, **{key: value}))

    def test_same_size_mtime_restored_elf_mutation(self):
        stamp = self.elf.stat(); self.elf.write_bytes(b'TOY_B')
        os.utime(self.elf, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        with self.assertRaises(ValueError): self.gate()

    def test_missing_pin_result_and_scope_drift(self):
        for kind in ('pin', 'result', 'scope', 'observer'):
            original = copy.deepcopy(self.saved)
            if kind == 'pin': self.saved['checked_files'].pop(str(self.elf))
            if kind == 'result': self.saved['result']['extra'] = True
            if kind == 'scope': self.saved['scope'] = 'RTL-PASS'
            if kind == 'observer': self.saved['observer_launch_admitted'] = True
            self.reseal()
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.gate()
            self.saved = original

    def test_budget_over_300_rejected(self):
        p = self.out / 'cost-preflight.json'; value = json.loads(p.read_text()); value['conditional_seconds_upper'] = 301
        c.save(p, value)
        with self.assertRaises(ValueError): self.gate()

    def test_composition_does_not_replace_parent_script(self):
        old = Mock(return_value={'other': True})
        with patch.object(adapter, '_HOOKS', None), patch.object(e, 'precheck', old), \
                patch.object(adapter.checked, 'SCRIPT', Path('/parent.py')):
            adapter.install_hooks(); adapter.install_hooks()
            self.assertEqual(e.precheck({'name': 'app:other'}, object()), {'other': True})
            self.assertEqual(adapter.checked.SCRIPT, Path('/parent.py'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
