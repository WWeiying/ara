#!/usr/bin/env python3
"""Offline fail-closed tests. Synthetic logs are fixtures, never DUT evidence."""
import argparse
import copy
import csv
import gzip
import io
import json
import re
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / "verification/coverage"))
import gap54_akv_oracle as o
import gap54_akv_admission as admission
import run_gap54_akv_checked_extension as adapter

BUILD = None


def fixture(host=False, elf=None):
    lines = []
    total = traps = 0
    for i,w in enumerate(o.WORDS):
        bad = 4 <= i <= 6
        if not host:
            row = dict.fromkeys(o.PERF_KEYS,0)
            row.update(o.expected_perf(i))
            row.update(id=0,busy_cycles=20)
            if i in (0,7):
                row.update(ar=4,translations=0,r_beats=31 if i == 0 else 28,
                           read_outstanding_max=1,read_outstanding_occ_sum=20)
            lines.append("[AKV_PERF] "+" ".join(f"{k}={row[k]}" for k in o.PERF_KEYS))
            lines.append(f"AKV54_CSR phase={i+1} fflags=21 vstart=0")
            if bad:
                pc = elf["sites"][i]["pc"]
                lines.append(f"AKV54_TRAP phase={i+1} cause=2 pc={pc:x} expected={pc:x} tval={w:x}")
        traps += bad
        total += 13 if host else 14+3*bad
        lines.append(f"AKV54_PHASE phase={i+1} word={w:08x} traps={traps} checks={total} errors=0")
    lines.append(f"PASSED: {o.NAME} checks={total} errors=0")
    return "\n".join(lines)+"\n"


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = (BUILD / (o.NAME+".elf")).read_bytes()
        cls.elf = o.elf_audit(cls.blob)
        cls.log = fixture(False,cls.elf)

    def rejects(self, text):
        with self.assertRaises(ValueError):
            o.validate_log(text,False,self.elf)

    def test_positive_json_stability(self):
        result = o.validate_log(self.log,False,self.elf)
        self.assertEqual(json.loads(json.dumps(result)),result)
        self.assertEqual(result["checks"],177)
        self.assertEqual(o.validate_log(fixture(True),True)["checks"],156)

    def test_phase_missing_duplicate_reordered(self):
        phases = [s for s in self.log.splitlines() if s.startswith("AKV54_PHASE")]
        for line in phases:
            with self.subTest(line=line):
                self.rejects(self.log.replace(line+"\n",""))
                self.rejects(self.log+line+"\n")
        self.rejects(self.log.replace(phases[0],"TEMP").replace(phases[1],phases[0]).replace("TEMP",phases[1]))

    def test_perf_each_semantic_field(self):
        lines = self.log.splitlines()
        indices = [i for i,s in enumerate(lines) if s.startswith("[AKV_PERF]")]
        for phase,line_index in enumerate(indices):
            for key,value in o.expected_perf(phase).items():
                with self.subTest(phase=phase,key=key):
                    changed = lines.copy()
                    tokens = changed[line_index].split()
                    tokens = [f"{key}={value+1}" if s == f"{key}={value}" else s for s in tokens]
                    changed[line_index] = " ".join(tokens)
                    self.rejects("\n".join(changed))

    def test_perf_missing_unknown_duplicate(self):
        first = self.log.splitlines()[0]
        for changed in (self.log.replace(first+"\n",""),self.log+first+"\n",
                        self.log.replace("seq=1 ","seq=x ",1),
                        self.log.replace("seq=1 ","seq=1 seq=1 ",1),
                        self.log.replace("seq=1 ","bogus=1 ",1)):
            self.rejects(changed)

    def test_csr_snapshot_and_order(self):
        self.rejects(self.log.replace("fflags=21","fflags=0",1))
        self.rejects(self.log.replace("vstart=0","vstart=1",1))
        lines = self.log.splitlines()
        lines[0],lines[1] = lines[1],lines[0]
        self.rejects("\n".join(lines))

    def test_trap_cause_pc_tval(self):
        for old,new in (("cause=2","cause=5"),("tval=2a0605b","tval=1"),
                        ("pc="+format(self.elf["sites"][4]["pc"],"x"),"pc=0")):
            self.rejects(self.log.replace(old,new,1))

    def test_failure_and_counts(self):
        for suffix in ("FAIL injected\n","Error: injected\n","Assertion failed\n",self.log.splitlines()[-1]+"\n"):
            self.rejects(self.log+suffix)
        self.rejects(self.log.replace("checks=177","checks=176"))
        self.rejects(self.log.replace("errors=0","errors=1",1))

    def test_elf_snapshot_mutations(self):
        h = struct.unpack_from("<HHIQQQIHHHHHH",self.blob,16)
        sections = [struct.unpack_from("<IIQQQQIIQQ",self.blob,h[5]+64*i) for i in range(h[11])]
        for site in self.elf["sites"]:
            section = next(s for s in sections if s[2]&4 and s[3] <= site["pc"] < s[3]+s[5])
            base = section[4]+site["pc"]-section[3]
            for delta in (0,4,8,12,16):
                with self.subTest(phase=site["phase"],offset=delta):
                    bad = bytearray(self.blob)
                    bad[base+delta] ^= 1
                    with self.assertRaises(ValueError):
                        o.elf_audit(bad)

    def test_host_bit_mutations(self):
        log = (BUILD / "host-negative.log").read_text()
        self.assertEqual(log.splitlines()[-1],"GAP54_NEGATIVE_HOST rejected=20")
        self.assertEqual(sum(s.startswith("FAIL ") for s in log.splitlines()),2965)
        self.assertIn("GAP54_EXHAUSTIVE rejected=2944 cancellation_rejected=1",log.splitlines())
        self.assertEqual(o.validate_log((BUILD / "host.log").read_text(),True)["checks"],156)
        with self.assertRaises(ValueError):
            o.validate_log((BUILD / "host.log").read_text()+"AKV54_CSR phase=1 fflags=21 vstart=0\n",True)

    def test_generated_bytes_match_original_formulas(self):
        text = (ROOT / "apps/akv_gap54_skew_context/expected.h").read_text()
        def data(name):
            block = text.split("static const uint64_t "+name,1)[1].split(";",1)[0]
            return b"".join(int(h,16).to_bytes(8,"little") for h in re.findall(r"UINT64_C\(0x([0-9a-f]+)\)",block))
        source,mask,rows,frames = [data(n) for n in ("source_reference","poison_mask","row_reference","frame_reference")]
        self.assertEqual([len(x) for x in (source,mask,rows,frames)],[1536,1536,768,7680])
        for e in range(2):
            for s in range(3):
                start = 64+((2,6,14)[s] if e == 0 else 0)
                for b in range(256):
                    d = b-start
                    expected = ((0x1100+e*0x1000+s*0x2000+7*(d//2)) >> (8*(d%2)))&255 if 0 <= d < 128 else (0xa7+19*e+29*s+11*b)&255
                    idx = (e*3+s)*256+b
                    self.assertEqual(source[idx],expected)
                    self.assertEqual(mask[idx],0x5a if 0 <= d < 128 else 0)
                for d in range(64):
                    idx = ((e*3+s)*64+d)*2
                    self.assertEqual(int.from_bytes(rows[idx:idx+2],"little"),0x1100+e*0x1000+s*0x2000+7*d)
        for phase in range(12):
            for d in range(320):
                expected = 0xc100+d if d < 32 else 0x9000+phase*0x100+13*(d-32) if d < 288 else 0xd200+d-288
                idx = (phase*320+d)*2
                self.assertEqual(int.from_bytes(frames[idx:idx+2],"little"),expected)

    def test_no_post_execution_expected_refresh(self):
        source = (ROOT / "apps/akv_gap54_skew_context/main.c").read_text()
        self.assertNotIn("source_byte(",source)
        self.assertIn("actual[w] = expected[w] = reference[w]",source)
        self.assertIn("expected[w] ^= mask[w]",source)
        self.assertNotIn("expected[w] = actual[w]",source)
        self.assertIn("difference |= actual[w] ^ expected[w]",source)
        self.assertIn("const volatile alias_word *actual",source)

    def test_static_cost_includes_memcpy(self):
        cost = o.read(BUILD / "cost-analysis.json")["new_cost"]
        self.assertEqual(cost["word_pairs_per_phase"],368)
        self.assertEqual(cost["memcpy_aligned_loop_instructions"],6)
        self.assertGreater(cost["setup_instructions_upper"],2304)
        self.assertLess(cost["phase_instructions_upper"],12000)
        self.assertEqual(cost["functions"]["seed"]["memcpy_calls"],2)

    def test_exact_case_seal(self):
        case = dict(name=o.TEST,timeout_s=600,runtime_contract=o.RUNTIME_FORMAT,
                    sources=["a"],evidence=["b"],precheck=dict(format=o.FORMAT))
        record = dict(case=case)
        item = dict(case,precheck=dict(case["precheck"],record="/record",record_sha256="123"))
        admission.check_case(item,record,Path("/record"),"123")
        for key,value in (("timeout_s",601),("sources",["a","composer"]),
                          ("evidence",["b","draft"]),("extra",True)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                admission.check_case(dict(item,**{key:value}),record,Path("/record"),"123")

    def test_perf_injection_case_scope(self):
        command = ["simv","+TESTCASE="+o.NAME,"+NO_FSDB"]
        self.assertEqual(adapter.perf_command(command),command+["+AKV_PERF"])
        for value in (command+["+AKV_PERF"],command+["+AKV_PERF=0"],
                      ["simv","+TESTCASE=other","+NO_FSDB"],command[:-1]):
            with self.assertRaises(ValueError):
                adapter.perf_command(value)

    def test_composable_hooks_delegate_preserve_script(self):
        checked,full = adapter.checked,adapter.full
        with patch.object(adapter,"_HOOKS",None),patch.object(checked,"SCRIPT",Path("/parent")), \
             patch.object(checked.evidence,"precheck",return_value="pre") as pre, \
             patch.object(full,"worker",return_value=7) as worker, \
             patch.object(checked,"summarize",return_value="sum") as summary, \
             patch.object(full.batch,"directed",return_value="dir") as directed:
            hooks = adapter.install_hooks()
            self.assertIs(adapter.install_hooks(),hooks)
            self.assertEqual(checked.SCRIPT,Path("/parent"))
            self.assertEqual(checked.evidence.precheck(dict(name="app:other"),None),"pre")
            self.assertEqual(full.worker(Path("/unused"),"other"),7)
            self.assertEqual(checked.summarize(Path("/unused"),dict(cases=[])),"sum")
            self.assertEqual(full.batch.directed(Path("/unused"),"other"),"dir")
            pre.assert_called_once()
            worker.assert_called_once()
            summary.assert_called_once()
            directed.assert_called_once()

    def test_local_directed_restores_monitor_on_error(self):
        from ara_verify import runner
        checked,full = adapter.checked,adapter.full
        def explode(output,name):
            raise ValueError("delegate failure")
        with patch.object(adapter,"_HOOKS",None),patch.object(checked.evidence,"precheck"), \
             patch.object(full,"worker"),patch.object(checked,"summarize"), \
             patch.object(full.batch,"directed",side_effect=explode), \
             patch.object(runner,"_run_monitored") as monitor:
            hooks = adapter.install_hooks()
            with self.assertRaises(ValueError):
                hooks["directed"](Path("/unused"),o.NAME)
            self.assertIs(runner._run_monitored,monitor)
            monitor.assert_not_called()

    def test_branch_per_spec_reverse(self):
        from reviewed_20261004.audit_readonly import branch_index
        definition = ET.fromstring('<branch_def><branch_spec id="0"><branch_vector id="0"/><branch_vector id="1"/></branch_spec><branch_spec id="1"><branch_vector id="0"/><branch_vector id="1"/><branch_vector id="2"/></branch_spec></branch_def>')
        self.assertEqual(branch_index(definition,"0","0")[:3],(1,0,2))
        self.assertEqual(branch_index(definition,"1","0")[:3],(4,2,3))
        self.assertEqual(branch_index(definition,"1","2")[:3],(2,2,3))

    def test_native_checksum_and_missing_hit(self):
        from coverage_evidence import Evidence
        with tempfile.TemporaryDirectory(dir=BUILD,prefix="native-fixture-") as tmp:
            db = Path(tmp)/"snps/coverage/db/testdata/test"
            db.mkdir(parents=True)
            targets = dict(points=[dict(scope="scope",metric="branch",coordinate="Branch 0 (0)",
                raw_index=1,definition=dict(width=2,checksum="7"))])
            for metric in ("line","branch"):
                with gzip.open(db / (metric+".verilog.data.xml"),"wb") as f:
                    f.write(b'<covdata><instance_data name="scope" chksum="7" value="10"/></covdata>')
            result = o.native_runtime(tmp,targets,Evidence())
            self.assertEqual(result["status"],"GAPS_RETAINED")
            self.assertEqual(result["new_target_hits"],0)
            self.assertEqual(json.loads(json.dumps(result)),result)
            targets["points"][0]["definition"]["checksum"] = "8"
            with self.assertRaises(ValueError):
                o.native_runtime(tmp,targets,Evidence())

    def test_trace_protocol_and_csr_negatives(self):
        fields = "cycle event trans_id insn pc rd_wdata trap".split()
        rows = []
        for i,s in enumerate(self.elf["sites"]):
            cycle = i*200+1
            def add(event,insn=0,pc=0,value=0,trap=0):
                rows.append(dict(cycle=cycle+len(rows)%100,event=event,trans_id=0,
                                 insn=f"{insn:x}",pc=f"{pc:x}",rd_wdata=f"{value:x}",trap=trap))
            add("cvx_req",o.WORDS[i])
            add("cvx_resp",trap=int(4 <= i <= 6))
            if not 4 <= i <= 6:
                add("retire",o.WORDS[i],s["pc"])
            add("retire",0x001022f3,s["pc"]+4,21)
            add("retire",0x00802373,s["pc"]+8,0)
        contract = "[ARA_CONTRACT] requests=12 responses=12 exceptions=3 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n"
        with tempfile.TemporaryDirectory(dir=BUILD,prefix="trace-fixture-") as tmp:
            path = Path(tmp)/"trace.csv"
            def write(values):
                with path.open("w") as stream:
                    w = csv.DictWriter(stream,fieldnames=fields)
                    w.writeheader()
                    w.writerows(values)
            write(rows)
            result = o.trace_audit(path,self.elf,contract)
            self.assertEqual(json.loads(json.dumps(result)),result)
            for index,key,value in ((1,"trap",1),(3,"rd_wdata","0"),(4,"pc","0"),(0,"trans_id",1)):
                bad = copy.deepcopy(rows)
                bad[index][key] = value
                write(bad)
                with self.subTest(index=index,key=key),self.assertRaises(ValueError):
                    o.trace_audit(path,self.elf,contract)
            write(rows)
            with self.assertRaises(ValueError):
                o.trace_audit(path,self.elf,contract.replace("exceptions=3","exceptions=2"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build",type=Path,required=True)
    BUILD = parser.parse_args().build.resolve()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    o.save(BUILD / "negative-tests.json",dict(status="PASS" if result.wasSuccessful() else "FAIL",
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        host_mutations_rejected=20,exhaustive_byte_mutations_rejected=2944,
        cancelling_xor_rejected=1,synthetic_runtime_fixtures=True,vcs_launched=False))
    raise SystemExit(not result.wasSuccessful())
