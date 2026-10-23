import json
from pathlib import Path
import tempfile
import unittest
from audit_q8k_prepare_soc import audit
from run_half_scale_soc import digest
from run_q8k_prepare_soc import check_result


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/"soc/work").mkdir(parents=True)
        self.simv=self.root/"simv";self.elf=self.root/"input.elf"
        self.simv.write_bytes(b"image");self.elf.write_bytes(b"elf")
        (self.root/"soc/work/input.elf").write_bytes(b"elf")
        log="\n".join(f"Q8K_SOC trial={i} path={'vector' if i in (1,2) else 'generic'} cycles={80 if i in (1,2) else 100} flags=1 used={int(i in (1,2))}" for i in range(4))
        log+="\nQ8K_SOC_RESULT errors=0 bytes=7008 inputs=6144 k=1536 calls=4 golden=linux_ggml\n"
        (self.root/"soc/work/run.vcs.log").write_text(log)
        (self.root/"soc/work/vector_trace.csv").write_text("trace\n")
        self.write("status.json",dict(state="PASS",command=["bash","runner",str(self.simv),str(self.elf),"qbs_q8k_prepare_soc","soc"]))
        self.write("manifest.json",{str(self.simv):digest(self.simv),str(self.elf):digest(self.elf)})
        self.write("result.json",dict(state="PASS",log_sha256=digest(self.root/"soc/work/run.vcs.log"),
            trials=check_result(log),generic_sum_cycles=200,vector_sum_cycles=160))
        self.write("soc/uvm_result.json",dict(status="PASS",issues=[],simv_sha256=digest(self.simv),elf_sha256=digest(self.elf),
            sim_image_sha256={str(self.simv):digest(self.simv)},log_sha256=digest(self.root/"soc/work/run.vcs.log"),
            vector_trace_sha256=digest(self.root/"soc/work/vector_trace.csv"),
            contract_counts=dict(requests=10,responses=10,outstanding=0,exceptions=0,protocol_errors=0),
            backend_counts=dict(allocations=10,completions=10,aborted=0)))

    def write(self,name,value):
        (self.root/name).write_text(json.dumps(value))

    def test_valid(self):
        self.assertEqual(audit(self.root)["preparation_speedup"],1.25)

    def test_bad_recorded_sum(self):
        path=self.root/"result.json";value=json.loads(path.read_text());value["vector_sum_cycles"]=159;self.write("result.json",value)
        with self.assertRaises(ValueError):audit(self.root)

    def test_bad_protocol(self):
        value=json.loads((self.root/"soc/uvm_result.json").read_text());value["contract_counts"]["exceptions"]=1
        self.write("soc/uvm_result.json",value)
        with self.assertRaises(ValueError):audit(self.root)

    def test_drift(self):
        self.elf.write_bytes(b"changed")
        with self.assertRaises(ValueError):audit(self.root)

    def test_wrong_executed_elf(self):
        (self.root/"soc/work/input.elf").write_bytes(b"other")
        with self.assertRaises(ValueError):audit(self.root)


if __name__=="__main__":unittest.main()
