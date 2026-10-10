from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import collect_itlb_asid_exec_bulk as c


def witness():
    symbols=dict(itm_code=0x80010000)
    commits=[]
    for i in range(8192):
        e,w=divmod(i,512)
        commits.append(SimpleNamespace(pc=0x80002000,instruction=0x00053023,
            memory_accesses=((symbols['itm_code']+8*i,c.bulk.codeword(e,w)),)))
    for p in range(3):
        for e in range(16):
            commits.append(SimpleNamespace(pc=c.bulk.address(p,e),instruction=0x513,memory_accesses=()))
    for i in range(8192):
        commits.append(SimpleNamespace(pc=0x80003000,instruction=0x00053503,
            memory_accesses=((symbols['itm_code']+8*i,None),)))
    return commits,symbols


class Collector(unittest.TestCase):
    def test_complete_native_dominance_not_preload_claim(self):
        commits,symbols=witness();proof=c.code_write_dominance(commits,symbols)
        self.assertEqual(proof['word_stores'],8192)
        self.assertEqual(proof['word_reads'],8192)
        self.assertFalse(proof['initial_ELF_memory_readback_claimed'])

    def test_missing_redundant_incorrect_and_late_write_rejected(self):
        for mutation in ('missing','duplicate','value','late'):
            commits,symbols=witness()
            if mutation=='missing':del commits[511]
            if mutation=='duplicate':commits.insert(1,commits[0])
            if mutation=='value':commits[0]=SimpleNamespace(pc=0x80002000,instruction=0x00053023,
                memory_accesses=((symbols['itm_code'],0),))
            if mutation=='late':commits.append(commits[0])
            with self.assertRaises(ValueError):c.code_write_dominance(commits,symbols)

    def test_missing_duplicate_early_and_partial_read_rejected(self):
        for mutation in ('missing','duplicate','early','partial'):
            commits,symbols=witness()
            if mutation=='missing':commits.pop()
            if mutation=='duplicate':commits.append(commits[-1])
            if mutation=='early':commits.insert(0,commits[-1])
            if mutation=='partial':commits[-1]=SimpleNamespace(pc=0x80003000,instruction=0x00050503,
                memory_accesses=commits[-1].memory_accesses)
            with self.assertRaises(ValueError):c.code_write_dominance(commits,symbols)

    def test_entry_and_successful_terminal_are_strict(self):
        def x(pc,mem=()):return SimpleNamespace(pc=pc,memory_accesses=mem)
        good=[x(0x1000),x(0x80000000),x(0x80000004,((0x80001000,1),))]
        self.assertEqual(c.bulk.reference_interval(good),good[1:])
        for bad in (good+[x(0x80000000)],good[:-1],good[2:],
            good+[x(0x80000008,((0x80001000,1),))]):
            with self.assertRaises(ValueError):c.bulk.reference_interval(bad)

    def test_raw_exception_mismatch_precedes_parsing_or_augmentation(self):
        expected='\n'.join('exception trap_supervisor_ecall, epc '+hex(c.bulk.address(p,e)+8)
            for p in range(3) for e in range(16))
        for text in (expected.replace('trap_supervisor_ecall','trap_illegal_instruction',1),
            expected.rsplit('\n',1)[0],expected+'\n'+expected.splitlines()[0],
            expected.replace(hex(c.bulk.address(0,0)+8),hex(c.bulk.address(0,0)+4),1)):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'spike.trace';path.write_text(text)
                with patch.object(c.pre.build,'parse_spike_commits',side_effect=AssertionError('must not parse')):
                    with self.assertRaisesRegex(ValueError,'raw Spike'):c.checked_reference(path,{})

    def test_actual_frozen_reference_full_replay(self):
        path=c.life.OUT/'itlb-asid-exec-bulk-preflight-agent-20261007-01/preflight.json'
        q=c.life.read_bound(path,c.PREFLIGHT_SHA)
        ref,ledger=c.checked_reference(path.parent/'spike.trace',q['symbols'])
        self.assertEqual(len(ref),103572)
        self.assertEqual(ledger['trap_count'],48)
        expected=dict(q['counts'],matched_instructions=q['counts']['matched_instructions']+48)
        self.assertEqual(c.pre.validate(c.pre.with_ecalls(ref,q['symbols']),q['symbols']),expected)
        self.assertEqual(c.pre.architecture.reference_counts(ref,q['symbols']),q['counts'])
        self.assertEqual(c.code_write_dominance(ref,q['symbols'])['word_reads'],8192)

    def test_real773_ledger_has_exact_compiled_pins(self):
        bits,ledger,pins=c.baseline()
        self.assertEqual(len(bits['tests']),773)
        self.assertEqual(ledger[1:],bits['tests'])
        self.assertTrue(all(str(Path(ledger[0])/'snps/coverage/db'/p) in pins for p in bits['design']))

    def test_union_rejects_772_and_duplicate(self):
        for before,single in [(dict(tests=list(map(str,range(772)))),dict(tests=['new'])),
            (dict(tests=list(map(str,range(773)))),dict(tests=['0']))]:
            with self.assertRaises(ValueError):c.full_union(before,single)


if __name__=='__main__':unittest.main()
