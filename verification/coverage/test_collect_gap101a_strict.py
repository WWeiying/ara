import copy
import unittest
import collect_gap101a_strict as m


def control_fixture():
    def row(event, seq, tid=1, instruction="e2050827", trap=0):
        return dict(event=event,order=str(seq),trans_id=str(tid),insn=instruction,trap=str(trap),port="0")
    return [row("arch_start",37),row("cvx_req",-1),row("cvx_resp",-1,trap=1)],[]


def data_fixture():
    symbols = {key:0x80000000+i*0x10000 for i,key in enumerate(m.software.SYMBOLS)}
    words = {(symbols[key]+off,8):v for (key,off),v in m.software.expected_words().items()}
    ledger=[2,symbols["g101a_bad_a"],0xe2050827,1,1,0,0,1]
    words.update({(symbols["g101a_ledger"]+8*i,8):v for i,v in enumerate(ledger)})
    words.update({(symbols["g101a_restore"]+8*i,8):0 for i in range(4)})
    words.update({(symbols["g75_result"],4):539,(symbols["g75_result"]+4,4):0,
                  (symbols["num_failed"],4):0,(symbols["tohost"],8):1})
    rows=[]
    for (address,size),value in words.items():
        rows.append(dict(event="retire",order=str(len(rows)),pc="80000004",trap="0",
                         mem_addr="%016x"%address,mem_wmask="%02x"%(((1<<size)-1)<<(address&7)),
                         mem_wdata="%016x"%value,insn="00a2b023" if size==8 else "00a2a023"))
    return rows,symbols


class CollectorTests(unittest.TestCase):
    def test_rejection_no_backend(self):
        self.assertEqual(m.lifecycle(*control_fixture())["rejected_backend_uops"],0)

    def test_original_phase_rejected(self):
        rows,v=control_fixture();rows[0]["insn"]="22050fa7"
        with self.assertRaisesRegex(ValueError,"Original failing phase"):m.lifecycle(rows,v)

    def test_rejected_backend_allocation(self):
        rows,v=control_fixture();extra=copy.deepcopy(rows[0]);extra["event"]="uop_alloc";rows.append(extra)
        extra=copy.deepcopy(extra);extra["event"]="uop_done";rows.append(extra)
        with self.assertRaisesRegex(ValueError,"allocated backend"):m.lifecycle(rows,v)

    def test_rejected_vector_activity(self):
        rows,v=control_fixture();v.append(dict(event="write",arch_seq="37"))
        with self.assertRaisesRegex(ValueError,"rejected vector"):m.lifecycle(rows,v)

    def test_missing_response(self):
        rows,v=control_fixture()
        with self.assertRaisesRegex(ValueError,"conservation"):m.lifecycle(rows[:-1],v)

    def test_full_data(self):
        self.assertEqual(m.observed(*data_fixture())["checks"],539)

    def test_changed_vrf(self):
        rows,s=data_fixture()
        next(r for r in rows if int(r["mem_addr"],16)==s["g101a_dump"]+4088)["mem_wdata"]="0"
        with self.assertRaisesRegex(ValueError,"mismatch"):m.observed(rows,s)

    def test_guard_and_recovery(self):
        for name in ("g101a_target_dump","g101a_recovery_dump"):
            rows,s=data_fixture()
            next(r for r in rows if int(r["mem_addr"],16)==s[name]+16)["mem_wdata"]="0"
            with self.assertRaisesRegex(ValueError,"mismatch"):m.observed(rows,s)

    def test_extra_terminal_row(self):
        rows,s=data_fixture();extra=copy.deepcopy(rows[-1]);extra["order"]=str(len(rows));rows.append(extra)
        with self.assertRaisesRegex(ValueError,"terminal"):m.observed(rows,s)

    def test_unknown_byte_not_skipped(self):
        result=dict(status="PASS",compared_instructions=32,compared_bytes=4096,skipped_unknown_bytes=1,
                    non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,selected_index=None,
                    stopped_at_spike_index=None,trapped_requests=[37],incomplete_requests=[],unretired_requests=[])
        with self.assertRaisesRegex(ValueError,"vector"):m.vector_exact(result,37)


if __name__ == "__main__":unittest.main()
