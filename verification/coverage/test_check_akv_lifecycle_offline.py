import copy
from types import SimpleNamespace
import unittest

import check_akv_lifecycle_offline as check


class NativeTests(unittest.TestCase):
    def test_terminal_status_not_bool_returncode(self):
        status=dict(status="SIMULATION_EXITED_NOT_ADMITTED",returncode=False,case=check.runner.NAME,
                    coverage_admitted=False,native_oracle_qualified=False,full_scalar_independent_qualified=False)
        with self.assertRaises(ValueError):check.terminal_status(status)

    def test_failed_terminal_rejected(self):
        with self.assertRaises(ValueError):check.terminal_status(dict(status="SIMULATION_FAILED_NOT_ADMITTED",returncode=0))

    def log(self):
        return ('Core Test *** SUCCESS ***\n$finish at simulation time 123\n$finish called from file "'+
                str(check.life.ROOT/"hardware/tb/ara_commit_monitor.sv")+'", line 270.\n'+
                '[ARA_CONTRACT] requests=426 responses=426 exceptions=4 mmu_request_cycles=0 protocol_errors=0 outstanding=0\n')

    def test_stdout_complete(self): self.assertEqual(check.stdout_audit(self.log())["exceptions"],4)

    def test_UVM_ERROR_message(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log()+"UVM_ERROR @ 12: boom\n")

    def test_UVM_FATAL_message(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log()+"UVM_FATAL @ 12: boom\n")

    def test_nonzero_summary(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log()+"UVM_ERROR : 1\n")

    def test_zero_summaries(self): check.stdout_audit(self.log()+"UVM_ERROR : 0\nUVM_FATAL : 0\n")

    def test_partial_contract(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log().replace("responses=426","responses=425"))

    def test_unexpected_exception(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log().replace("exceptions=4","exceptions=5"))

    def test_multiple_success(self):
        with self.assertRaises(ValueError): check.stdout_audit(self.log()+"Core Test *** SUCCESS ***\n")

    def vector(self):
        row=dict(event="config",cycle="0",arch_seq="0",vid="0",insn="00000000",use_vd="0",vd="0",
                 eew="0",vl="0",vstart="0",lane="0",source="0",addr="0",be="00",wdata="0",
                 nr_lanes="4",vlen_bits="1024")
        allocation=dict(row,event="alloc",cycle="1",arch_seq="7",insn="02005007",use_vd="1",eew="1",vl="64")
        write=dict(allocation,event="write",cycle="2",source="4",be="01",wdata="12")
        done=dict(allocation,event="done",cycle="3")
        arch=dict(allocations={7:dict(insn=0x02005007,port=0,cycle=1)},
                  done={7:dict(cycle=3)},commands=[])
        model=SimpleNamespace(vector_effects=[dict(word=0x02005007,vd=0,data="12",kind="seed")])
        return [row,allocation,write,done],model,arch

    def test_native_independent_byte_binding(self):
        rows,m,a=self.vector();check.vector_audit(rows,m,a)

    def test_wrong_native_byte(self):
        rows,m,a=self.vector();rows[2]["wdata"]="13"
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_neighbor_write(self):
        rows,m,a=self.vector();rows[2]["addr"]="4"
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_duplicate_byte(self):
        rows,m,a=self.vector();rows.insert(3,copy.deepcopy(rows[2]))
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_missing_done(self):
        rows,m,a=self.vector()
        with self.assertRaises(ValueError):check.vector_audit(rows[:-1],m,a)

    def test_wrong_source(self):
        rows,m,a=self.vector();rows[2]["source"]="3"
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_zero_enable_rejected(self):
        rows,m,a=self.vector();rows[2]["be"]="00"
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_mirror_cycle_mismatch(self):
        rows,m,a=self.vector();a["done"][7]["cycle"]=4
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_partial_frontend_rejected(self):
        with self.assertRaises(ValueError):check.commit_audit([],SimpleNamespace(requests=[],commands=[]))

    def test_missing_PERF_rejected(self):
        with self.assertRaises(ValueError):check.perf_audit(self.log(),{},SimpleNamespace(commands=[]))

    def test_foreign_config_metadata(self):
        rows,m,a=self.vector();rows[0]["be"]="01"
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_partial_native_effects(self):
        rows,m,a=self.vector();rows.pop(2)
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)

    def test_rejected_command_write(self):
        rows,m,a=self.vector();m.vector_effects=[]
        with self.assertRaises(ValueError):check.vector_audit(rows,m,a)


if __name__ == "__main__": unittest.main()
