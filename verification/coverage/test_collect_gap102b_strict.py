"""Focused rejection fixtures; never execute DUT, collector main, or bitmap tools."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

import collect_gap102b_strict as c


class StrictTests(unittest.TestCase):
    def test_reference_entry_and_terminal(self):
        def item(pc,memory=(),gpr=None):
            return SimpleNamespace(pc=pc,memory_accesses=memory,gpr_writes=gpr or {},
                                   fpr_writes={},instruction=0x00003023)
        boot=item(0x1000,gpr={1:1})
        entry=item(0x80000000,gpr={0:0,1:2})
        end=item(0x80000004,((0x80001000,1),))
        expected=dict(matched_instructions=2,matched_scalar_writes=1,
                      matched_floating_writes=0,matched_scalar_memory_accesses=1)
        self.assertEqual(c.reference_counts([boot,entry,end,item(0x80000008)],{"tohost":0x80001000}),expected)
        with self.assertRaises(ValueError):
            c.reference_counts([boot,entry],{"tohost":0x80001000})

    def test_actual_sealed_reference_counts(self):
        pre=c.life.read_bound(c.runner.PRE/"preflight-manifest.json",c.runner.PRE_SEAL)
        self.assertEqual(c.life.digest(c.runner.proof.PRE/"spike.trace"),pre["pins"][str(c.runner.proof.PRE/"spike.trace")])
        commits=c.proof.s.parse_spike_commits(c.runner.proof.PRE/"spike.trace")
        self.assertEqual(c.reference_counts(commits,pre["symbols"]),c.SCALAR_COUNTS)

    def vector(self):
        return dict(status="PASS",compared_instructions=35,compared_bytes=5504,
            skipped_unknown_bytes=0,non_bit_exact_instructions=0,nr_lanes=4,vlen_bits=1024,
            selected_index=None,stopped_at_spike_index=None,trapped_requests=[],
            incomplete_requests=[],unretired_requests=[])

    def test_vector_exact(self):
        c.vector_exact(self.vector())

    def test_vector_rejections(self):
        for key,value in (("compared_bytes",516),("compared_instructions",34),
                          ("skipped_unknown_bytes",1),("non_bit_exact_instructions",1),
                          ("trapped_requests",[37]),("unretired_requests",[2]),
                          ("incomplete_requests",[2]),("selected_index",0)):
            with self.subTest(key=key):
                result=self.vector(); result[key]=value
                with self.assertRaises(ValueError): c.vector_exact(result)

    def test_scalar_strict(self):
        expected=dict(matched_instructions=4,matched_scalar_writes=2,
                      matched_floating_writes=0,matched_scalar_memory_accesses=1)
        result=dict(status="TERMINAL_TOHOST_MATCH",entry="0x0000000080000000",
            rvfi_store_data_layout="unshifted",skipped_unobservable_register_values=0,
            stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=0,
            mismatch=None,terminal_ecall=None,vector_state_compared=False,
            ara_retired_instructions=4,ara_committed_instructions=4,
            terminal_tohost=dict(address="0x0000000080001000",write_value="0x1"),**expected)
        c.scalar_exact(result,expected)
        for key,value in (("matched_scalar_writes",1),("matched_instructions",3),
                          ("matched_scalar_memory_accesses",0),("skipped_unobservable_register_values",1),
                          ("stopped_at_unobservable",1),("ara_trap_events",1),
                          ("mismatch",{}),("aligned_vector_faults",[1])):
            mutated=deepcopy(result); mutated[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): c.scalar_exact(mutated,expected)

    def observations(self):
        names={name for name,_ in c.proof.expected_words()}
        names.update(("g75_trap","g75_result","num_failed","tohost","trap_fail"))
        symbols={name:0x90000000+i*0x10000 for i,name in enumerate(sorted(names))}
        words=dict(c.proof.expected_words())
        words.update({("g75_trap",i*8):0 for i in range(3)})
        words.update({("g75_result",0):723,("g75_result",4):0,("num_failed",0):0,("tohost",0):1})
        ordered=[item for item in words.items() if item[0][0]!="tohost"]+[(("tohost",0),1)]
        rows=[]
        for i,((name,offset),value) in enumerate(ordered):
            width=4 if name in ("g75_result","num_failed") else 8
            rows.append(dict(event="retire",order=str(i),trap="0",pc="80000000",
                insn="00003023" if width==8 else "00002023",
                mem_addr="%x"%(symbols[name]+offset),mem_wmask="%x"%(((1<<width)-1)<<((symbols[name]+offset)&7)),
                mem_wdata="%x"%value))
        return symbols,rows

    def test_complete_observations(self):
        symbols,rows=self.observations()
        self.assertEqual(c.observed(rows,symbols)["checks"],723)

    def test_guard_tail_csr_and_recovery_rejected(self):
        symbols,rows=self.observations()
        for name,offset in (("g102b_dump",4096-8),("g102b_dump",8*128),
                            ("g102b_source_dump",512-8),("g102b_seed_dump",0),
                            ("g102b_csr",0),("g102b_recovery_dump",0),("g75_trap",0),
                            ("g75_result",4)):
            bad=deepcopy(rows)
            row=next(r for r in bad if int(r["mem_addr"],16)==symbols[name]+offset)
            row["mem_wdata"]="%x"%(int(row["mem_wdata"],16)^1)
            with self.subTest(name=name),self.assertRaises(ValueError): c.observed(bad,symbols)

    def test_missing_bytes_and_post_terminal_rejected(self):
        symbols,rows=self.observations()
        bad=deepcopy(rows); bad[0]["mem_wmask"]="1"
        with self.assertRaises(ValueError): c.observed(bad,symbols)
        bad=deepcopy(rows); extra=deepcopy(rows[0]); extra["order"]=str(len(rows));bad.append(extra)
        with self.assertRaises(ValueError): c.observed(bad,symbols)

    def events(self):
        common=dict(trans_id="0",order="0",pc="00000000",insn="f2c56457",trap="0",port="0",cycle="10")
        rows=[dict(common,event=e) for e in ("arch_start","cvx_req","uop_alloc","uop_done","cvx_resp","retire")]
        rows[-1].update(pc="80002234", cycle="20")
        vectors=[dict(event=e,arch_seq="0",vid="0",cycle="10",insn="f2c56457",
                      use_vd="1",vd="8",eew="2",vl="129",vstart="128",nr_lanes="4",vlen_bits="1024",
                      lane="0",source="1",be="0f") for e in ("alloc","write","done")]
        return rows,vectors,{"g102b_mac":0x80002234}

    def test_lifecycle_conservation(self):
        rows,vectors,symbols=self.events()
        self.assertEqual(c.lifecycle(rows,vectors,symbols)["backend_uops"],1)

    def test_lifecycle_rejections(self):
        rows,vectors,symbols=self.events()
        bad=deepcopy(rows);bad[4]["trap"]="1"
        for rr,vv in ((bad,vectors),(rows[:-2],vectors),(rows,vectors[:-1]),
                      (rows,vectors+[dict(event="write",arch_seq="999",vid="0")]),
                      (rows+[rows[0]],vectors)):
            with self.assertRaises(ValueError): c.lifecycle(rr,vv,symbols)

    def test_mac_retire_identity_and_order(self):
        rows,vectors,symbols=self.events()
        for field,value in (("pc","80002230"),("cycle","9")):
            bad=deepcopy(rows);bad[-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                c.lifecycle(bad,vectors,symbols)
        with self.assertRaises(ValueError):
            c.lifecycle(rows+[deepcopy(rows[-1])],vectors,symbols)

    def test_exact_mac_vstart_config_and_opcode(self):
        rows,vectors,symbols=self.events()
        for field,value in (("vstart","0"),("vl","1"),("eew","1"),("vd","12"),("use_vd","0")):
            bad=deepcopy(vectors)
            for row in bad:row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):c.lifecycle(rows,bad,symbols)
        bad=deepcopy(vectors)
        for row in bad:row["insn"]="00000013"
        with self.assertRaises(ValueError):c.lifecycle(rows,bad,symbols)

    def test_done_and_write_metadata_not_only_counter(self):
        rows,vectors,symbols=self.events()
        for pos in (1,2):
            bad=deepcopy(vectors);bad[pos]["vd"]="9"
            with self.assertRaises(ValueError):c.lifecycle(rows,bad,symbols)
        bad=deepcopy(rows);bad[3]["cycle"]="9"
        with self.assertRaises(ValueError):c.lifecycle(bad,vectors,symbols)
        with self.assertRaises(ValueError):c.lifecycle(rows,vectors+[deepcopy(vectors[0])],symbols)

    def test_completion_after_retire_allowed(self):
        rows,vectors,symbols=self.events()
        done=rows.pop(3);done["cycle"]="30";rows.append(done)
        vectors[-1]["cycle"]="30"
        self.assertEqual(c.lifecycle(rows,vectors,symbols)["original_mac_vstart"],128)

    def test_duplicate_and_unowned_mac(self):
        rows,vectors,symbols=self.events()
        with self.assertRaises(ValueError):c.lifecycle(rows+[deepcopy(rows[0])],vectors,symbols)
        bad=deepcopy(vectors);bad[1]["arch_seq"]="999"
        with self.assertRaises(ValueError):c.lifecycle(rows,bad,symbols)

    def test_raw_target_hit_is_measured_not_assumed(self):
        targets=json.loads((c.runner.PRE/"target-before.json").read_bytes())
        scope=c.runner.SCOPE
        old=dict(width=1215,checksum="1558979345",bits="0x0")
        before=dict(metrics=dict(branch={scope:old}))
        single=deepcopy(before)
        self.assertFalse(c.measure_targets(before,single,targets)[0]["hit_single"])
        single["metrics"]["branch"][scope]["bits"]=hex(1<<(1214-127))
        self.assertTrue(c.measure_targets(before,single,targets)[0]["hit_single"])
        single["metrics"]["branch"][scope]["checksum"]="different"
        with self.assertRaises(ValueError):c.measure_targets(before,single,targets)
        before["metrics"]["branch"][scope]["bits"]=hex(1<<(1214-127))
        with self.assertRaises(ValueError):c.measure_targets(before,before,targets)

    def test_attempt_identity(self):
        self.assertEqual(c.RUN.name,"gap102b-widen-acc-vstart-old-image-717-20261006-01")
        self.assertEqual(c.PREPARED_SEAL,"767835e44c1c2f952645f2e12045defad1ce20d77e6fa346d593acdd5cfcbd59")


if __name__=="__main__":
    unittest.main()
