import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import audit_memory_decode_repair as a


NAMES = tuple(a.CASES)


class MemoryDecodeRepairTests(unittest.TestCase):
    def test_complete_original_fixtures_not_subsets(self):
        for name, checks in zip(NAMES, (1075, 4229)):
            with self.subTest(name=name):
                pre, pins = a.fixture(a.source(name), name)
                self.assertEqual(pre['validation']['checks'], checks)
                self.assertFalse(any('/hardware/' in p or 'simv' in p or
                                     'admission' in p for p in pins))
                if checks == 1075:
                    self.assertEqual(pre['validation']['phases'], 2)
                else:
                    self.assertEqual(pre['validation']['snapshots'], 7)

    def test_unknown_or_truncated_elf_rejected(self):
        with self.assertRaises(ValueError):
            a.source('vgap101a_nf_emul_only')
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / 'input.elf').write_bytes(b'not-the-original')
            for name in NAMES:
                with self.assertRaises(ValueError):
                    a.fixture(Path(temp), name)

    def test_original_failures_rejected(self):
        histories = ('gap101-illegal-segment-store-old-image-20261006-01',
                     'memory-emul-r2-old-image-parent-20261006-01')
        for name, history in zip(NAMES, histories):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                run = Path(temp)
                shutil.copyfile(a.source(name) / 'input.elf', run / 'input.elf')
                old = a.ROOT / 'verification/out' / history
                for filename in ('commit_trace.csv', 'vector_trace.csv',
                                 'run.vcs.log', 'trace_hart_0.log'):
                    (run / filename).symlink_to(old / filename)
                with self.assertRaisesRegex(ValueError, 'Runtime/contract failure'):
                    a.audit(run, name)

    def lifecycle(self):
        rows = []
        for seq, word in enumerate(a.g101.WORDS):
            for event in ('arch_start', 'cvx_req', 'cvx_resp'):
                rows.append(dict(event=event, order=str(seq), trans_id=str(seq),
                                 insn=hex(word), cycle=str(seq * 3 + 1), trap='1' if event == 'cvx_resp' else '0'))
        return rows

    def test_both_rejections_required(self):
        rows = self.lifecycle()
        result = a.gap101_lifecycle(rows, [])
        self.assertEqual(result['rejected_arch_seqs'], [0, 1])
        for bad in (rows[:3], rows[3:]):
            with self.assertRaises(ValueError):
                a.gap101_lifecycle(bad, [])
        bad = copy.deepcopy(rows)
        bad[-1]['trap'] = '0'
        with self.assertRaises(ValueError):
            a.gap101_lifecycle(bad, [])

    def test_illegal_backend_allocation_rejected(self):
        rows = self.lifecycle()
        rows += [dict(event=e, order='1', trans_id='1', insn=hex(a.g101.WORDS[1]),
                      cycle='8', port='0') for e in ('uop_alloc', 'uop_done')]
        with self.assertRaisesRegex(ValueError, 'Illegal backend'):
            a.gap101_lifecycle(rows, [])

    def observation(self):
        pre = json.loads((a.source(NAMES[0]) / 'preflight-manifest.json').read_text())
        s = pre['symbols']
        writes = [(s[name] + off, value, 8) for (name, off), value in a.g101.expected_words().items()]
        for phase, site in enumerate(('g101_bad_a', 'g101_bad_b')):
            ledger = [2, s[site], a.g101.WORDS[phase], 1, 1-phase, 0, 0, phase+1]
            writes += [(s['g101_ledger'] + phase * 80 + i * 8, value, 8)
                       for i, value in enumerate(ledger)]
        writes += [(s['g101_restore'] + i * 8, value, 8)
                   for i, value in enumerate((0x80000000, 0x80000000, 0, 0))]
        writes += [(s['g75_result'], 1075, 4), (s['g75_result']+4, 0, 4),
                   (s['num_failed'], 0, 4), (s['tohost'], 1, 8)]
        rows = [dict(event='retire', order=str(i), trap='0', pc='80000000',
                     mem_addr=hex(addr), mem_wmask=hex(((1 << width)-1) << (addr & 7)),
                     mem_wdata=hex(value), insn=hex(0x3023 if width == 8 else 0x2023))
                for i, (addr, value, width) in enumerate(writes)]
        return rows, s

    def test_all_1075_checks_and_snapshots_required(self):
        rows, s = self.observation()
        self.assertEqual(a.gap101_observed(rows, s)['checks'], 1075)
        for address in (s['g101_target_dump']+80, s['g101_dump']+8184,
                        s['g101_recovery_dump']+120, s['g101_ledger']+80,
                        s['g75_result']):
            bad = copy.deepcopy(rows)
            row = next(r for r in bad if int(r['mem_addr'], 16) == address)
            row['mem_wdata'] = hex(int(row['mem_wdata'], 16) ^ 1)
            with self.subTest(address=hex(address)), self.assertRaises(ValueError):
                a.gap101_observed(bad, s)

    def test_dispatcher_guards_and_qbs_preserved(self):
        text = (a.ROOT / 'hardware/src/ara_dispatcher.sv').read_text()
        load = text.split('riscv::OpcodeLoadFp: begin', 1)[1].split('//  Vector Stores', 1)[0]
        store = text.split('riscv::OpcodeStoreFp: begin', 1)[1].split('//  CSR Reads', 1)[0]
        for block, flag in ((load, 'illegal_insn_load'), (store, 'illegal_insn_store')):
            self.assertIn(flag + ' = csr_vtype_q.vill;', block)
            whole = block.split('// Vector whole register', 1)[1]
            self.assertRegex(whole, flag + r'\s*= 1\x27b0;')
        segment = store.split('// Check for segment stores', 1)[1].split('// Vector whole register', 1)[0]
        self.assertIn("unsigned'(ara_req.vs1)", segment)
        self.assertNotIn("unsigned'(ara_req.vd)", segment)
        self.assertIn('layout_req.op != VQBEXEC', text)
        self.assertIn('faulting QBS changed VRF layout metadata without committing data', text)


if __name__ == '__main__':
    unittest.main()
