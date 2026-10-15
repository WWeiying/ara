"""Independently derive fractional scope from its own sealed source sequence."""
import unittest
import checker as c
import recovery as r


class FractionalScopeTests(unittest.TestCase):
    def test_own_sequence_and_geometry(self):
        spec = c.base.specification()
        rows = c.base.model()
        source = c.base.read(c.base.REF / 'sequence.json')
        self.assertEqual(len(rows), len(source))
        self.assertEqual(len(rows), 4095)
        self.assertEqual(spec['config'], dict(id='rvv_matrix_e8_mf2', sew=8, lmul='mf2', cap=64, calls=4095,
            vtype=7, physical_group_registers=1, observed_group_bytes=64, mask_bytes=128, vlm_bytes=8))
        target = spec['backend']['helpers']['op_19'][8]
        self.assertEqual((target['pc'], target['insn']), (0x80000fdc, 0x38813c57))
        changed = []
        required = 0
        for i, (actual, original) in enumerate(zip(rows, source)):
            for key in ('seed', 'op', 'li', 'mode', 'si', 'vl'):
                self.assertEqual(actual[key], original[key])
            self.assertEqual((actual['ordinal'], actual['vstart']), (original['ordinal'] - 1, original['start']))
            self.assertEqual(len(actual['a']), 64)
            self.assertEqual(len(actual['b']), 64)
            self.assertEqual(len(actual['mask']), 128)
            self.assertEqual(actual['mask'][8:], [0] * 120)
            raw = b''.join(w.to_bytes(8, 'little') for w in original['words'])[:66]
            self.assertEqual(actual['raw'], raw)
            self.assertEqual(len(raw), 66)
            self.assertEqual((raw[0], raw[65]), (91, 91))
            # Independent source-side predicate, not a call to the successor helper.
            original_needed = original['start'] < original['vl']
            empty_slide = original['op'] == 19 and original['vl'] in (0, 1, 2)
            wanted = original_needed and not empty_slide
            insn = spec['backend']['helpers'][f'op_{actual["op"]}'][8]['insn']
            self.assertEqual(c.target_required(insn, actual, spec), wanted)
            required += wanted
            if original_needed and empty_slide:
                changed.append(i)
        self.assertEqual(changed, [b+i for b in (1200, 2565, 3930) for i in range(6)])
        self.assertEqual(required, 2592)
        owners = dict(compulsory_memory_owners=5*len(source), required_target_owners=required,
            required_op24_memory_targets=sum(x['op'] == 24 and x['start'] < x['vl'] for x in source),
            minimum_required_owners=5*len(source)+required)
        self.assertEqual(owners, r.OWNERS)
        scope = dict(calls=len(source), results=len(source)*64, guards=len(source)*2,
            returned_vstart_zero=len(source), helper_instructions=len(source)*13,
            packed_output_reads=len(source)*9, fresh_output_bytes_each_call=66)
        self.assertEqual(scope, r.SCOPE)
        r.save(r.HERE / 'host01/model_evidence.json', dict(scope=scope, owners=owners,
            changed_zero_based_calls=changed, first_source_tuple={k:source[1200][k] for k in
            ('ordinal','seed','op','li','mode','si','vl','start')}, actual_target=target,
            sequence_sha256=r.sha(c.base.REF / 'sequence.json'), model_sha256=r.sha(c.base.REF / 'model.py'),
            soc_elf_sha256=c.base.ELF_SHA, config=spec['config'], own_full_source_rows_checked=4095))

    def test_nine_reads_not_m4_65(self):
        state = object.__new__(c.Strict)
        state.helper = None
        state.active = dict(reads=set(range(9)), returned_vstart=0)
        state.finish_call()
        state.active['reads'] = set(range(65))
        with self.assertRaisesRegex(ValueError, 'full8word'):
            state.finish_call()
        state.active = dict(reads=set(range(8)), returned_vstart=0)
        with self.assertRaisesRegex(ValueError, 'full8word'):
            state.finish_call()


if __name__ == '__main__':
    unittest.main(verbosity=2)
