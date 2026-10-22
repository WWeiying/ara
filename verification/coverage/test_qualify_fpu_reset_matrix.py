import copy
import json
import unittest
from unittest.mock import patch
import qualify_fpu_reset_matrix as q


def vector_rows(sew=32, insn='5e02c057', data=None, vl=None):
    eew = {16: 1, 32: 2, 64: 3}[sew]
    return [dict(event='alloc', arch_seq='1', vid='0', insn=insn, vd='0', eew=str(eew),
                 vl=str(vl if vl is not None else 8192 // sew)),
            dict(event='write', arch_seq='1', vid='0', be='ff',
                 wdata='%016x' % (q.oracle.GOLD[sew][0] if data is None else data))]


class CanonicalBytes(unittest.TestCase):
    def test_all_precision_source_not_e64_initial_seed(self):
        for sew in (16, 32, 64):
            self.assertEqual(q.epoch0_bytes(vector_rows(sew), sew, 'RF'), 8)

    def test_written_byte_mutation_and_sew_rejected(self):
        with self.assertRaisesRegex(ValueError, 'written byte'):
            q.epoch0_bytes(vector_rows(data=q.oracle.GOLD[32][0] ^ 1), 32, 'RF')
        with self.assertRaisesRegex(ValueError, 'writer/precision'):
            q.epoch0_bytes(vector_rows(16), 32, 'RF')

    def test_div_before_result_stage_rejected(self):
        rows = vector_rows(insn='82881c57', data=q.oracle.GOLD[32][2])
        self.assertEqual(q.epoch0_bytes(rows, 32, 'WB_REQ'), 8)
        with self.assertRaisesRegex(ValueError, 'writer/precision'):
            q.epoch0_bytes(rows, 32, 'EX1')

    def test_guard_csr_and_tail_oracle(self):
        value = lambda name, offset=0, size=8: (679 if name == 'g75_result' and offset == 0 else
            1 if name == 'tohost' else 0 if name in ('g75_result', 'num_failed') else
            q.expected_word(32, offset // 8) if name == 'fpar_vrf' else [256, 19, 0, 0, 33][offset // 8])
        q.oracle.oracle(value, 32)
        with self.assertRaisesRegex(ValueError, 'VRF'):
            q.oracle.oracle(lambda n, o=0, size=8: value(n, o, size) ^ int(n == 'fpar_vrf' and o == 4088), 32)
        with self.assertRaisesRegex(ValueError, 'CSR'):
            q.oracle.oracle(lambda n, o=0, size=8: value(n, o, size) ^ int(n == 'fpar_csr' and o == 32), 32)


class Cancellation(unittest.TestCase):
    def case(self):
        return dict(sew=32, preflight_case=dict(symbols=dict(fpar_div=0x80002200)))

    def inputs(self):
        return [dict(event='arch_start', order='4', insn='82881c57'),
                dict(event='retire', pc='80002200', insn='82881c57', trap='0')], [dict(
                    event='alloc', arch_seq='4', vid='2', insn='82881c57', eew='2', vl='256', vd='24')]

    def test_exact_div_cancel_and_no_completed_owner(self):
        c, v = self.inputs(); self.assertEqual(q.cancelled_owners(c, v, self.case()), [4])
        v.append(dict(event='done', vid='2'))
        with self.assertRaisesRegex(ValueError, 'cancelled operation'):
            q.cancelled_owners(c, v, self.case())

    def test_wrong_site_precision_and_extra_owner_rejected(self):
        c, v = self.inputs(); c[1]['pc'] = '80002204'
        with self.assertRaisesRegex(ValueError, 'site'):
            q.cancelled_owners(c, v, self.case())
        c, v = self.inputs(); v[0]['eew'] = '1'
        with self.assertRaisesRegex(ValueError, 'precision'):
            q.cancelled_owners(c, v, self.case())
        c, v = self.inputs(); v.append(dict(v[0], vid='3', insn='deadbeef'))
        with self.assertRaisesRegex(ValueError, 'operation'):
            q.cancelled_owners(c, v, self.case())


class ActualFixtures(unittest.TestCase):
    def test_all_actual_epoch0_bytes_cancelled_and_sew(self):
        plan = q.life.read_bound(q.matrix.PLAN, q.SEAL)
        for record in plan['cases']:
            root = q.Path(record['output'])
            _, c = q.events.run.reset.read_csv(root / 'commit_trace.csv')
            _, v = q.events.run.reset.read_csv(root / 'vector_trace.csv')
            epochs, _ = q.events.run.reset.split_epochs(c, v)
            self.assertGreater(q.epoch0_bytes(epochs[0][1], record['sew'], record['stage']), 0)
            self.assertIn(39, q.cancelled_owners(*epochs[0], record))
            sample = q.all_controller_states(root / 'external-reset.vcd', record)
            self.assertEqual(sample['states'][record['selection']['ext_target']], record['selection']['ext_value'])
            self.assertEqual(len(sample['states']), {16: 16, 32: 8, 64: 4}[record['sew']])

    def test_full6162_or_duplicates_and_foreign_shape(self):
        b = json.loads((q.matrix.BASE / 'combined-bits.json').read_bytes())
        single = copy.deepcopy(b); single['tests'] = ['new.vdb']
        merged = q.merge(b, [single]); self.assertEqual(merged['tests'], b['tests'] + ['new.vdb'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            q.merge(b, [single, single])
        single['metrics']['fsm'].pop(next(iter(single['metrics']['fsm'])))
        with self.assertRaisesRegex(ValueError, 'inventory'):
            q.merge(b, [single])


if __name__ == '__main__':
    unittest.main()
