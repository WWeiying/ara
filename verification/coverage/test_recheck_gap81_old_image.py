"""Offline negative fixtures; tests never launch VCS or DVE."""
import csv
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import recheck_gap81_old_image as r


class RecoveryTests(unittest.TestCase):
    def test_only_audit_count_failure_can_recover(self):
        service = dict(Id=r.UNIT,LoadState="loaded",ActiveState="failed",SubState="failed",MainPID="0",
            ExecMainCode="1",ExecMainStatus="1",WorkingDirectory=str(r.ROOT),
            ExecStart="{ argv[]=/usr/bin/python3 -u %s --preflight %s --output %s ; }"%(r.RUNNER,r.PREFLIGHT,r.ORIGINAL))
        status = dict(status="FAIL",reason="ValueError: DUT command selfcheck incomplete",
                      coverage_status="INCOMPLETE",rtl_changed=False)
        self.assertIn("returned_zero",r.eligibility(service,status,r.SNAPSHOT_SHA))
        for reason in ("CalledProcessError: exit1","TimeoutExpired: 600s","ValueError: Runtime contract violation"):
            with self.assertRaises(ValueError):
                r.eligibility(service,dict(status,reason=reason),r.SNAPSHOT_SHA)
        for change in (dict(MainPID="123"),dict(LoadState="not-found"),dict(ExecMainCode="2"),
                       dict(ActiveState="active"),dict(ExecMainStatus="9"),dict(WorkingDirectory="/other")):
            with self.assertRaises(ValueError):
                r.eligibility(dict(service,**change),status,r.SNAPSHOT_SHA)
        with self.assertRaises(ValueError):
            r.eligibility(service,status,"0"*64)

    def test_exact_baseline_order_duplicates_and_substitutions(self):
        before = dict(tests=["/test/%d.vdb"%i for i in range(687)])
        expected = ["/design.vdb",*before["tests"]]
        self.assertEqual(r.baseline_members(before,expected[0],expected,expected),expected)
        for changed in (expected[:-1],expected[:-1]+[expected[1]],
                        expected[:1]+list(reversed(expected[1:])),expected[:-1]+["/foreign.vdb"]):
            with self.assertRaises(ValueError):
                r.baseline_members(before,expected[0],expected,changed)

    def test_command_foreign_image_or_trace_rejected(self):
        static = dict(simv="/old/simv")
        original,elf = Path("/original"),Path("/preflight.elf")
        command = [static["simv"],"-l","run.vcs.log","+NO_FSDB","+ntb_random_seed=1",
            "+PRELOAD="+str(elf),"+TESTCASE="+r.NAME,"+COMMIT_TRACE=/original/commit_trace.csv",
            "+VECTOR_TRACE=/original/vector_trace.csv","+QBS_PERF","-cm","line+cond+fsm+tgl+branch",
            "-cm_dir","/original/code.vdb","-cm_name",r.NAME]
        record = dict(command=command,cwd=str(original),timeout_s=600)
        r.validate_command(record,static,elf,original)
        for index,value in ((0,"/new/simv"),(7,"+COMMIT_TRACE=/foreign"),(13,"/foreign.vdb")):
            changed = dict(record,command=list(command))
            changed["command"][index] = value
            with self.assertRaises(ValueError):
                r.validate_command(changed,static,elf,original)

    def test_runtime17_not18_and_no_fatal_or_partial_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            commit,vector,log = (root/name for name in ("commit.csv","vector.csv","run.log"))
            rows = [dict(event=e,insn="06b5045b",trans_id="0",trap="0",pc="80000004")
                    for e in ("cvx_req","cvx_resp","retire")]
            rows[1]["insn"] = "00000000"
            def write(items):
                with commit.open("w") as stream:
                    writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(items)
            write(rows)
            text = ("GAP81 command=0 checks=17 errors=0\n"
                "GAP81 inspected vrf_words=1024 initial_words=1024 source_bytes=3440 csr_words=12\n"
                "PASSED: qbs_gap81_m4_phase12 checks=24 errors=0\nCore Test *** SUCCESS ***\n"
                "$finish at simulation time 510715000\n")
            log.write_text(text)
            values = {}
            for context in range(4):
                data = struct.pack("<f",float(256*(context+1)))+bytes(124)
                values.update({(8+context,i):(v,None) for i,v in enumerate(data)})
            activity = SimpleNamespace(instruction=0x06b5045b,allocations=1,completions=1,writes=[])
            with patch.object(r,"validate_trace",return_value={}), \
                 patch.object(r,"check_contract_log",return_value=[]), \
                 patch.object(r,"_parse_vector_trace",return_value=(4,1024,{1:activity})), \
                 patch.object(r,"_architectural_bytes",return_value=values):
                self.assertEqual(r.runtime(commit,vector,log,0x80000004)["command_checks"],17)
                for bad in (text.replace("checks=17","checks=18"),text.replace("checks=24","checks=23"),
                            text+"Fatal: failed\n",text.replace("$finish at simulation time 510715000\n","")):
                    log.write_text(bad)
                    with self.assertRaises(ValueError):
                        r.runtime(commit,vector,log,0x80000004)
                log.write_text(text)
                write(rows[1:])
                with self.assertRaisesRegex(ValueError,"Orphan"):
                    r.runtime(commit,vector,log,0x80000004)
                write(rows)
                values[(8,0)] = (None,None)
                with self.assertRaisesRegex(ValueError,"VRF bytes"):
                    r.runtime(commit,vector,log,0x80000004)

    def test_raw400_gain_must_be_real(self):
        row = dict(width=5914,checksum="2250470448",bits="0x0")
        before = dict(design={},tests=["old"],input_hashes={},metrics=dict(cond={r.target.SCOPE:row}))
        newrow = dict(row,bits=hex(1<<(5914-1-400)))
        sample = dict(design={},tests=["new"],input_hashes={},metrics=dict(cond={r.target.SCOPE:newrow}))
        after,delta = r.collect_gain(before,sample)
        self.assertEqual(r.target.bit(after["metrics"]["cond"][r.target.SCOPE],400),"1")
        sample["metrics"]["cond"][r.target.SCOPE] = row
        with self.assertRaisesRegex(ValueError,"0->1"):
            r.collect_gain(before,sample)


if __name__ == "__main__":
    unittest.main()
