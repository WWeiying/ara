"""Independent lifecycle, complete software-output and native-site rejection tests."""
import struct
from types import SimpleNamespace
import unittest

import build_akv_lifecycle_preflight as b


class LifecycleTest(unittest.TestCase):
    def test_lifecycle_predicates(self):
        result=b.reference_lifecycle()
        self.assertEqual(result["validation_errors"],[0,12,0,12,0,6,11,0,0,0])
        self.assertEqual(result["context_ready_after"],[False,False,True,False,True,True,False,True,True,False])
        self.assertEqual(sum(result["custom_write_bytes"]),128)

    def test_priority_context_before_tile(self):
        self.assertEqual(b.reference_lifecycle([("refill",False,1)])["validation_errors"],[12])

    def test_ready_mode_mismatch(self):
        self.assertEqual(b.reference_lifecycle([("full",True),("refill",False,0)])["validation_errors"],[0,12])

    def test_unknown_reference_operation_rejected(self):
        with self.assertRaises(ValueError):b.reference_lifecycle([("unknown",)])

    def test_whole_VRF_recovery_only_v8(self):
        old=b.expected_frame(7)[64:-64];new=b.expected_frame(8)[64:-64]
        self.assertEqual(len(old),4096)
        self.assertEqual(old[:8*128],new[:8*128]);self.assertEqual(old[9*128:],new[9*128:])
        self.assertEqual(new[8*128:9*128],struct.pack("<64H",*[0x2400+i for i in range(64)]))

    def test_actual721_zero_source_shape(self):
        _,target=b.target_evidence()
        self.assertEqual([r["raw_index"] for r in target["targets"]],[8,194,199,201])
        self.assertTrue(all(r["baseline_hit"] is False for r in target["targets"]))


class NativeEncodingTest(unittest.TestCase):
    def fixture(self):
        payload=struct.pack("<10I",*b.WORDS)
        elf=bytearray(120)+payload;elf[:6]=b"\x7fELF\x02\x01"
        struct.pack_into("<HHIQQQIHHHHHH",elf,16,2,243,1,0x80000000,64,0,4,64,56,1,0,0,0)
        struct.pack_into("<IIQQQQQQ",elf,64,1,5,120,0x80000000,0,len(payload),len(payload),4)
        symbols={"lifecycle_site_"+str(i):0x80000000+4*i for i in range(10)}
        return elf,symbols

    def test_exact_native_sites(self):
        elf,symbols=self.fixture();self.assertEqual(len(b.native_elf_audit(elf,symbols)["sites"]),10)

    def test_wrong_D96_word_rejected(self):
        elf,symbols=self.fixture();struct.pack_into("<I",elf,120+5*4,0x0005345b)
        with self.assertRaises(ValueError):b.native_elf_audit(elf,symbols)

    def test_wrong_trap_PC_rejected(self):
        elf,symbols=self.fixture();symbols["lifecycle_site_3"]+=4
        with self.assertRaises(ValueError):b.native_elf_audit(elf,symbols)

    def test_compressed_flag_rejected(self):
        elf,symbols=self.fixture();struct.pack_into("<I",elf,48,5)
        with self.assertRaises(ValueError):b.native_elf_audit(elf,symbols)


class SoftwareOutputTest(unittest.TestCase):
    def fixture(self):
        objects={"tohost":struct.pack("<Q",1),"g75_result":struct.pack("<2I",b.SOFTWARE_CHECKS,0),
          "num_failed":bytes(8),"lifecycle_snapshots":b"".join(b.expected_frame(p) for p in range(10)),
          "lifecycle_csrs":struct.pack("<60Q",*([21,0,64,8,2,1]*10)),
          "lifecycle_status":struct.pack("<10I",*b.FAULTS),"lifecycle_scan":struct.pack("<20I",*([512,0]*10)),
          "lifecycle_trap_count":struct.pack("<Q",4),"lifecycle_semantic_errors":struct.pack("<4I",*b.ERRORS),
          "g75_trap":bytes(24),"lifecycle_seed":b.expected_seed(),"lifecycle_sources":b.expected_sources()}
        symbols={};address=0x80010000
        for name,data in objects.items():symbols[name]=address;address+=len(data)+64
        symbols["lifecycle_descriptor"]=address;symbols["trap_fail"]=0x80000080
        source=symbols["lifecycle_sources"]
        objects["lifecycle_descriptor"]=struct.pack("<4B2H4I5Q",1,1,1,0,64,1,128,128,128,0,
                                                    source+64,source+320,source+576,0,0)
        commits=[]
        for name,data in objects.items():
            accesses=[(symbols[name]+i,int.from_bytes(data[i:i+8],"little")) for i in range(0,len(data),8)]
            commits.append(SimpleNamespace(vector_writes=[],pc=0x80002000,instruction=0x3023,memory_accesses=accesses))
        return commits,symbols,list(objects)

    def test_complete_software_output(self):
        commits,symbols,_=self.fixture();self.assertEqual(b.validate_software(commits,symbols)["real_Spike_traps"],0)

    def corrupt(self,name):
        commits,symbols,names=self.fixture();row=commits[names.index(name)]
        address,value=row.memory_accesses[0];row.memory_accesses[0]=(address,value^1)
        with self.assertRaises(ValueError):b.validate_software(commits,symbols)

    def test_snapshot_guard_corruption(self):self.corrupt("lifecycle_snapshots")
    def test_CSR_corruption(self):self.corrupt("lifecycle_csrs")
    def test_rejection_ledger_corruption(self):self.corrupt("lifecycle_semantic_errors")
    def test_source_guard_corruption(self):self.corrupt("lifecycle_sources")
    def test_descriptor_corruption(self):self.corrupt("lifecycle_descriptor")
    def test_missing_final_frame(self):
        commits,symbols,names=self.fixture();commits[names.index("lifecycle_snapshots")].memory_accesses.pop()
        with self.assertRaises(ValueError):b.validate_software(commits,symbols)
    def test_real_unexpected_trap(self):
        commits,symbols,_=self.fixture();commits[0].pc=symbols["trap_fail"]
        with self.assertRaises(ValueError):b.validate_software(commits,symbols)
    def test_nonunique_terminal(self):
        commits,symbols,_=self.fixture();commits.append(commits[0])
        with self.assertRaises(ValueError):b.validate_software(commits,symbols)


if __name__=="__main__":unittest.main()
