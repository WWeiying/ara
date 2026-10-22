"""Strict synthetic negatives plus actual frozen729 target binding; no EDA."""
from dataclasses import replace
import unittest
import build_store_fifo_burst_preflight as p
from ara_verify.spike_trace import SpikeCommit


def commit(pc, instruction=0x2023, memory=(), vectors=None, **context):
    return SpikeCommit(pc, instruction, {}, {}, vectors or {}, {}, tuple(memory), **context)


def fixture():
    names = dict(tohost=0x80001000, g75_result=0x80010000, num_failed=0x80010008,
                 trap_fail=0x80000060, sfb_seed=0x80011000, sfb_dest=0x80012000,
                 sfb_dump=0x80015000, sfb_cfg=0x80016000, sfb_init=0x80002000,
                 sfb_burst_begin=0x80002020, sfb_burst_end=0x8000205c, sfb_dump_pc=0x80002080)
    cs = []
    for name, words in [('sfb_seed', 36), ('sfb_dest', 2016), ('sfb_dump', 252)]:
        for i in range(words):
            value = p.source(i) if name == 'sfb_seed' else p.SENTINEL
            cs.append(commit(0x80003000, memory=[(names[name] + i * 4, value)]))
    seed = b''.join(p.source(i).to_bytes(4, 'little') for i in range(2, 34))
    cs.append(commit(names['sfb_init'], 0x02056407, vectors={8: int.from_bytes(seed, 'little')}))
    for phase, length in enumerate(p.LENGTHS):
        for store in range(8):
            address = names['sfb_dest'] + (phase * 8 + store) * 144 + 8
            cs.append(commit(names['sfb_burst_begin'] + store * 8, p.STORE,
                [(address + i * 4, p.source(i + 2)) for i in range(length)],
                vector_sew=32, vector_lmul='m1', vector_vl=length, vector_vstart=0, vector_vtype=16))
        address = names['sfb_dump'] + phase * 144 + 8
        cs.append(commit(names['sfb_dump_pc'], 0x02850427,
                         [(address + i, value) for i, value in enumerate(seed)]))
        for when in range(2):
            for i, value in enumerate([length, 16, 0, 128]):
                cs.append(commit(0x80003000, 0x3023,
                    [(names['sfb_cfg'] + ((phase * 2 + when) * 4 + i) * 8, value)]))
    for name, size in [('sfb_seed', 144), ('sfb_dest', 8064), ('sfb_dump', 1008), ('sfb_cfg', 448)]:
        cs.extend(commit(0x80003000, 0x2003, [(names[name] + i, None)]) for i in range(0, size, 4))
    cs += [commit(0x80003000, memory=[(names['g75_result'], p.CHECKS)]),
           commit(0x80003000, memory=[(names['g75_result'] + 4, 0)]),
           commit(0x80003000, memory=[(names['num_failed'], 0)]),
           commit(0x80003000, 0x3023, [(names['tohost'], 1)])]
    return cs, names


class StoreBurstTests(unittest.TestCase):
    def test_actual729_exact_eight_zero_targets(self):
        targets, pins = p.target_binding()
        self.assertEqual(len(targets), 8)
        self.assertEqual({t['metric'] for t in targets}, {'line', 'branch'})
        self.assertTrue(all(t['hit729'] is False and t['native_GUI_binding'] is False for t in targets))
        self.assertIn(str(p.SOURCE_PINS), pins)

    def test_target_hit_and_shape_rejected(self):
        for r in [dict(width=17, checksum=None, bits='0x200'), dict(width=18, checksum=None, bits='0')]:
            with self.assertRaises(ValueError): p.zero_target(r, 17, None, 7)

    def test_fixed_burst_eight_stores_no_fence(self):
        self.assertEqual(p.burst_words().count(p.STORE), 8)
        self.assertEqual(p.burst_words().count(p.STEP), 7)
        self.assertEqual(len(p.burst_words()), 15)

    def test_gold_bounds_and_tails(self):
        for phase, length in enumerate(p.LENGTHS):
            self.assertEqual(p.destination(phase, 2 + length), p.SENTINEL)
            self.assertEqual(p.destination(phase, 1 + length), p.source(1 + length))
        with self.assertRaises(ValueError): p.destination(7, 2)
        with self.assertRaises(ValueError): p.source(36)

    def test_full_oracle_accepts(self):
        cs, symbols = fixture()
        result = p.validate(cs, symbols, '')
        self.assertEqual(result['checks'], 2360)
        self.assertFalse(result['native_scheduling_measured'])

    def test_store_value_corruption_rejected(self):
        cs, s = fixture(); i = next(i for i, c in enumerate(cs) if c.pc == s['sfb_burst_begin'])
        cs[i] = replace(cs[i], memory_accesses=((cs[i].memory_accesses[0][0], 0),) + cs[i].memory_accesses[1:])
        with self.assertRaisesRegex(ValueError, 'store footprint'): p.validate(cs, s, '')

    def test_missing_store_rejected(self):
        cs, s = fixture(); cs = [c for c in cs if c.pc != s['sfb_burst_begin'] + 56]
        with self.assertRaises(ValueError): p.validate(cs, s, '')

    def test_extra_vector_write_rejected(self):
        cs, s = fixture(); cs.insert(0, commit(0x80003000, vectors={9: 0}))
        with self.assertRaises(ValueError): p.validate(cs, s, '')

    def test_guard_corruption_rejected(self):
        cs, s = fixture(); cs.insert(-1, commit(0x80003000, memory=[(s['sfb_dest'], 0)]))
        with self.assertRaisesRegex(ValueError, 'guard/tail'): p.validate(cs, s, '')

    def test_missing_scalar_readback_rejected(self):
        cs, s = fixture(); cs = [c for c in cs if c.memory_accesses != ((s['sfb_seed'], None),)]
        with self.assertRaisesRegex(ValueError, 'scalar readback'): p.validate(cs, s, '')

    def test_wrong_vstart_rejected(self):
        cs, s = fixture(); i = next(i for i, c in enumerate(cs) if c.pc == s['sfb_burst_begin'])
        cs[i] = replace(cs[i], vector_vstart=1)
        with self.assertRaisesRegex(ValueError, 'vector context'): p.validate(cs, s, '')

    def test_exception_and_terminal_rejected(self):
        cs, s = fixture()
        with self.assertRaises(ValueError): p.validate(cs, s, 'exception trap_illegal_instruction')
        cs[-1] = replace(cs[-1], memory_accesses=((s['tohost'], 3),))
        with self.assertRaisesRegex(ValueError, 'terminal'): p.validate(cs, s, '')


if __name__ == '__main__':
    unittest.main()
