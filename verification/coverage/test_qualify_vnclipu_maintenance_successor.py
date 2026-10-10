"""Synthetic software fixtures only; never read actual DUT logs."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import qualify_vnclipu_maintenance_successor as c
from test_qualify_vnclipu_parent_terminal import row


def fixture():
    reference = [SimpleNamespace(pc=0x80002000+i*4, instruction=0x02000007+i*128,
        vector_writes={i: int.from_bytes(c.old.p.expected_register(i, 0), 'little')}) for i in range(32)]
    reference.append(SimpleNamespace(pc=c.PC, instruction=c.WORD,
        vector_writes={16: int.from_bytes(c.old.p.expected_register(16, 2), 'little')},
        vector_vl=2, vector_vstart=0, vector_sew=16,
        vector_tail_agnostic=False, vector_mask_agnostic=False))
    rows = [row('arch_start', order=c.SEQ, cycle=101168, trans_id=2, insn='%08x'%c.WORD),
            row(pc='%016x'%c.PC, insn='%08x'%c.WORD)]
    vectors = []
    for phase, (start, vid, vd, eew, vl, done) in enumerate(c.PHASES):
        base = dict.fromkeys(c.old.common.VECTOR_FIELDS, '0')
        base.update(arch_seq=str(c.SEQ), vid=str(vid), vd=str(vd), eew=str(eew), vl=str(vl),
                    insn='%08x'%c.WORD, use_vd='1', nr_lanes='4', vlen_bits='1024')
        for event, time in [('alloc', start), ('done', done)]:
            vectors.append(dict(base, event=event, cycle=str(time)))
            rows.append(row('uop_'+event, order=c.SEQ, cycle=time, port=vid, trans_id=2, insn='%08x'%c.WORD))
        data = c.old.p.expected_register(vd, 2 if phase == 2 else 0)
        for word in range(1 if phase == 2 else 4):
            for lane in range(2 if phase == 2 else 4):
                raw = bytearray(8)
                for b in range(8):
                    natural = word*32 + c.vc._deshuffle_byte(lane*8+b, 4, eew)
                    raw[b] = data[natural]
                vectors.append(dict(base, event='write', source='0' if phase == 2 else '3',
                    cycle=str(101202 if phase == 2 else 101178 if phase == 0 else 101187),
                    lane=str(lane), addr=str(vd*4+word), be='03' if phase == 2 else 'ff',
                    wdata='%016x'%int.from_bytes(raw, 'little')))
    records = [dict(arch_seq=i, pc=hex(x.pc), instruction=hex(x.instruction), status='PASS',
        compared_bytes=128, skipped_unknown_bytes=0, unknown_write_bytes=0,
        mismatch_count=0, first_mismatch=None, uops=1, write_events=16) for i,x in enumerate(reference)]
    records[-1].update(arch_seq=c.SEQ, skipped_unknown_bytes=128, uops=3, write_events=34)
    result = dict(status='PASS', compared_instructions=33, skipped_unknown_bytes=128,
        non_bit_exact_instructions=0, nr_lanes=4, vlen_bits=1024, selected_index=None,
        stopped_at_spike_index=None, trapped_requests=[81], first_mismatch=None,
        unobservable_instructions=0, incomplete_requests=[], unretired_requests=[],
        compared_bytes=4224, instructions=records)
    return rows, vectors, reference, result


class MaintenanceTests(unittest.TestCase):
    def setUp(self): self.rows, self.vectors, self.reference, self.result = fixture()
    def check(self): return c.vector_gate(self.result, self.rows, self.vectors, self.reference)
    def rejected(self):
        with self.assertRaises((ValueError, KeyError)): self.check()
    def source(self):
        return next(r for r in self.vectors if r['event']=='write' and r['vd']=='8')
    def test_complete_known_maintenance(self):
        before = deepcopy(self.result)
        self.assertEqual(self.check()['known_source_maintenance_bytes'], 128)
        self.assertEqual(self.result, before)
    def test_owner(self): self.source()['arch_seq']='125'; self.rejected()
    def test_opcode(self): self.source()['insn']='ba904857'; self.rejected()
    def test_source(self): self.source()['source']='0'; self.rejected()
    def test_vid(self): self.source()['vid']='0'; self.rejected()
    def test_eew(self): self.source()['eew']='1'; self.rejected()
    def test_type(self): self.source()['event']='config'; self.rejected()
    def test_vl(self): self.source()['vl']='2'; self.rejected()
    def test_cycle(self): self.source()['cycle']='101194'; self.rejected()
    def test_unknown(self): self.source()['wdata']='xxxxxxxxxxxxxxxx'; self.rejected()
    def test_missing(self): self.vectors.remove(self.source()); self.rejected()
    def test_extra_duplicate(self): self.vectors.append(dict(self.source())); self.rejected()
    def test_duplicate_replacing_byte(self):
        xs=[r for r in self.vectors if r['event']=='write' and r['vd']=='8']
        xs[1].update(xs[0]); self.rejected()
    def test_missing_byte(self): self.source()['be']='fe'; self.rejected()
    def test_source_value(self): self.source()['wdata']='0000000000000000'; self.rejected()
    def test_spike_prestate(self): self.reference[8].vector_writes[8]^=1; self.rejected()
    def test_spike_poststate(self): self.reference[-1].vector_writes[16]^=1; self.rejected()
    def test_spike_tail_policy(self): self.reference[-1].vector_tail_agnostic=True; self.rejected()
    def test_destination_tail(self):
        r=next(r for r in self.vectors if r['event']=='write' and r['vd']=='16' and r['addr']=='67')
        r['wdata']='0000000000000000'; self.rejected()
    def test_result_value(self):
        r=next(r for r in self.vectors if r['event']=='write' and r['source']=='0')
        r['wdata']='0000000000000000'; self.rejected()
    def test_result_extra_tail_write(self):
        r=next(r for r in self.vectors if r['event']=='write' and r['source']=='0')
        r['be']='ff'; self.rejected()
    def test_backend_tid(self): self.rows[-1]['trans_id']='3'; self.rejected()
    def test_backend_done(self): self.rows[-1]['cycle']='101204'; self.rejected()
    def test_wrong_pc(self): self.rows[1]['pc']='80002758'; self.rejected()
    def test_other_skip(self):
        self.result['instructions'][0]['skipped_unknown_bytes']=1; self.rejected()
    def test_total_skip(self): self.result['skipped_unknown_bytes']=129; self.rejected()
    def test_unknown_elsewhere(self):
        self.result['instructions'][0]['unknown_write_bytes']=1; self.rejected()
    def test_mismatch_elsewhere(self):
        self.result['instructions'][0]['mismatch_count']=1; self.rejected()
    def test_extra_exception(self): self.result['trapped_requests']=[81,82]; self.rejected()
    def test_missing_destination_population(self):
        self.result['instructions'][0]['compared_bytes']=127; self.rejected()
    def test_original_failure_preserved(self):
        self.assertEqual(c.life.digest(c.FAIL), c.FAIL_SEAL)


if __name__ == '__main__': unittest.main()
