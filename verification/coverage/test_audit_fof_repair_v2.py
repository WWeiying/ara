"""Offline oracle fixtures only; no EDA or modification of sealed helpers."""
import copy
from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
import unittest

import audit_fof_repair_v2 as v2
import test_audit_fof_repair as fixture


class AcceptanceV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.Acceptance.setUpClass()
        cls.f = fixture.Acceptance

    @classmethod
    def tearDownClass(cls):
        fixture.Acceptance.tearDownClass()

    def native(self, activities=None):
        return v2.native_state(self.f.reference, activities or self.f.activities,
                               self.f.mapping, self.f.symbols)

    def mutation(self, opcode, change):
        activities = copy.deepcopy(self.f.activities)
        a = next(a for a in activities.values() if a.instruction == opcode)
        change(a)
        return activities

    def test_complete_audit_unknown_mask_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp)
            for p in self.f.directory.iterdir():
                shutil.copyfile(p, d / p.name)
            rows = copy.deepcopy(self.f.vectors)
            for r in rows:
                if r['event'] == 'write' and int(r['insn'],16) == v2.base.MASK:
                    # EW8: physical bytes 0 and 4 per lane cover active bits 0..63.
                    r['wdata'] = 'xxxxxxffxxxxxxff' if int(r['addr']) == 0 else 'xxxxxxxxxxxxxxxx'
            fixture.write_csv(d/'vector_trace.csv',v2.base.common.VECTOR_FIELDS,rows)
            result = v2.audit(d)
            self.assertEqual(result['scalar']['matched_instructions'],83732)
            self.assertEqual(result['native']['defined_compared_bytes'],684)
            self.assertGreater(result['native']['unknown_accepted_bit_events'],0)
            self.assertFalse(result['coverage_admitted'])

    def test_known_positive(self):
        self.assertEqual(self.native()['defined_compared_bytes'],684)

    def test_zero_be_drain(self):
        acts=self.mutation(v2.base.FOF,lambda a:a.writes.append(
            replace(a.writes[0],lane=3,be=0,known_be=0,data=0)))
        self.assertEqual(self.native(acts)['zero_be_events'],1)

    def test_active_unknown_mask_rejected(self):
        acts=self.mutation(v2.base.MASK,lambda a:a.writes.__setitem__(0,
            replace(a.writes[0],known_be=0)))
        with self.assertRaisesRegex(ValueError,'defined destination'):self.native(acts)

    def test_active_unknown_fof_rejected(self):
        acts=self.mutation(v2.base.FOF,lambda a:a.writes.__setitem__(0,
            replace(a.writes[0],known_be=0)))
        with self.assertRaisesRegex(ValueError,'defined destination'):self.native(acts)

    def test_other_writer_unknown_rejected(self):
        for op in (v2.base.DIV,v2.base.RECOVERY):
            acts=self.mutation(op,lambda a:a.writes.__setitem__(0,
                replace(a.writes[0],known_be=0)))
            with self.assertRaisesRegex(ValueError,'defined destination'):self.native(acts)

    def test_mask_tail_unproved_zero_rejected(self):
        acts=self.mutation(v2.base.MASK,lambda a:a.writes.append(
            replace(a.writes[0],addr=1,cycle=a.writes[-1].cycle+1,be=1,data=0)))
        with self.assertRaisesRegex(ValueError,'provenance'):self.native(acts)

    def test_fof_nonoriginal_active_tail_zero_rejected(self):
        acts=self.mutation(v2.base.FOF,lambda a:a.writes.append(
            replace(a.writes[0],addr=33,cycle=a.writes[-1].cycle+1,be=1,data=0)))
        with self.assertRaisesRegex(ValueError,'provenance'):self.native(acts)

    def test_unknown_neighbor_clobber_rejected(self):
        acts=self.mutation(v2.base.FOF,lambda a:a.writes.append(
            replace(a.writes[0],addr=40,be=1,known_be=0)))
        with self.assertRaisesRegex(ValueError,'clobber'):self.native(acts)

    def test_prior_bad_write_not_hidden(self):
        acts=self.mutation(v2.base.FOF,lambda a:a.writes.insert(0,
            replace(a.writes[0],cycle=a.writes[0].cycle-1,data=a.writes[0].data^1)))
        with self.assertRaisesRegex(ValueError,'defined destination'):self.native(acts)

    def test_missing_recovery_writer_rejected(self):
        acts=self.mutation(v2.base.RECOVERY,lambda a:a.writes.clear())
        with self.assertRaisesRegex(ValueError,'Missing defined'):self.native(acts)

    def test_probe_unknown_be_rejected(self):
        path=v2.base.ROOT/'verification/out/fof-build02-prefix-probe-agent-20261008-01/vector_trace.csv'
        with self.assertRaisesRegex(ValueError,'invalid be'):v2.parse_native(path)

    def test_original_failed_trace_rejected(self):
        path=v2.base.PRE.parent/'gap112-sv39-fof-old-image-740-agent-20261007-01'
        with self.assertRaises(ValueError):v2.audit(path)

    def test_bitwise_tail_and_prestart_provenance(self):
        v2.preserve_bits(0xf0,0xf0,0,0,allow_ones=True)
        v2.preserve_bits(0xa0,0xf0,0xa0,0xf0)
        for value,known,old,old_known,ones in [
                (0,0,1,1,True), (0,255,1,255,True),
                (1,1,0,0,False), (0,1,0,0,True), (0,0,0,255,False)]:
            with self.assertRaises(ValueError):v2.preserve_bits(value,known,old,old_known,ones)

    def test_partial_nibble_knownness_not_lost(self):
        value,known,z=v2.parse_wdata('xxxxxxxxxxxxxxfx')
        self.assertEqual((value,known,z),(0xf0,0xf0,0))
        w=self.f.activities[next(seq for seq,a in self.f.activities.items()
                 if a.instruction==v2.base.MASK)].writes[0]
        bw=v2.BitWrite(**dict(vars(w),data=value,be=2),known_bits=known<<8)
        self.assertEqual(next(v2.byte_events(bw))[1][1],0xf0)


if __name__=='__main__':unittest.main()
