import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import unittest

from rtl_run import check_perf, stop_group, EXPECTED, COUNTERS, PERF_FIELDS, SUMMARY_FIELDS
from rtl_build import cases


def fixture():
    lines, records = [], []
    for c in cases():
        for mode in (0, 1):
            lines.append(f"RTL_QK_BEGIN case={c['id']} mode={mode} kvhead={c['head']} tile={c['tile']} vl={c['vl']} stride={c['stride']}")
            commands = [4] + [6] * (32 if mode else 128) + [3]
            for command in commands:
                r = {name: 0 for name in PERF_FIELDS}
                col = int(command == 6)
                count = col * (4 if mode else 1)
                r.update(seq=len(records) + 1, id=len(records) % 8, command=command,
                         success=1, context_ready=int(command != 3), busy_cycles=20,
                         release=int(command == 3), v2_full=int(command == 4),
                         v2_column_load=col, v2_column_panel=col * mode,
                         v2_logical_column=count, v2_k_view_bank_cycles=8 * col,
                         replay_bytes=count * 128)
                if command == 4:
                    r.update(q_external_bytes=1536, kv_external_bytes=32768, read_ranges=135,
                             read_payload_bytes=34368, ar=135, r_beats=2148, read_outstanding_max=2)
                records.append(r)
                lines.append("[AKV_PERF] " + " ".join(f"{k}={r[k]}" for k in PERF_FIELDS))
            lines.append(f"RTL_QK_END case={c['id']} mode={mode}")
    total = {k: (max(r[k] for r in records) if k == "read_outstanding_max" else
                 sum(r[k] for r in records)) for k in COUNTERS}
    total.update(records=1312, success_records=1312, fault_records=0, validation_fault_records=0)
    lines.append("[AKV_PERF_SUMMARY] " + " ".join(f"{k}={total[k]}" for k in SUMMARY_FIELDS))
    return "\n".join(lines) + "\n"


class PerfTest(unittest.TestCase):
    def test_complete(self):
        totals = check_perf(fixture(), EXPECTED)
        self.assertEqual(totals["v2_column_load"], 1280)
        self.assertEqual(totals["v2_column_panel"], 256)
        self.assertEqual(totals["q_external_bytes"], 24576)
        self.assertEqual(totals["read_payload_bytes"], 549888)

    def test_bad_records(self):
        text = fixture()
        lines = text.splitlines()
        mutations = ["PASS\n", "\n".join(lines[:1] + lines[2:]),
            "\n".join(lines[:2] + [lines[1]] + lines[2:]),
            text.replace("seq=1 ", "seq=2 ", 1),
            text.replace("read_ranges=135", "read_ranges=134", 1),
            text.replace("success=1", "success=0", 1),
            text.replace("fault=0", "fault=1", 1),
            text.replace("busy_cycles=20", "busy_cycles=x", 1),
            text.replace("v2_column_panel=1", "v2_column_panel=0", 1),
            text.replace("v2_logical_column=4", "v2_logical_column=1", 1),
            text.replace("replay_bytes=512", "replay_bytes=128", 1),
            text.replace("context_ready=0", "context_ready=1", 1),
            text.replace("read_payload_bytes=549888", "read_payload_bytes=549887"),
            text + lines[-1] + "\n", text + "[QBS_PERF] command=1\n",
            text.replace("RTL_QK_BEGIN case=0 mode=0", "RTL_QK_BEGIN case=0 mode=1", 1),
            text.replace(" busy_cycles=20", " busy_cycles=20 busy_cycles=20", 1)]
        for i, mutated in enumerate(mutations):
            with self.subTest(i=i), self.assertRaises(ValueError):
                check_perf(mutated, EXPECTED)

    def test_expected_work_cannot_change(self):
        expected = dict(EXPECTED, commands=1)
        with self.assertRaises(ValueError):
            check_perf(fixture(), expected)


class ProcessTest(unittest.TestCase):
    def test_cleanup(self):
        script = ("import subprocess,sys,time; "
                  "c=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                  "print(c.pid,flush=True); time.sleep(60)")
        p = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE,
                             text=True, start_new_session=True)
        try:
            self.assertTrue(select.select([p.stdout], [], [], 10)[0])
            grandchild = int(p.stdout.readline())
            self.assertEqual(os.getpgid(grandchild), p.pid)
        finally:
            stop_group(p)
            p.stdout.close()
        self.assertEqual(p.returncode, -signal.SIGTERM)
        # A zombie (or this host's killpg(0) behavior) is not a live worker.
        deadline = time.monotonic() + 2
        while True:
            table = subprocess.check_output(["ps", "-eo", "pid,pgid,stat"], text=True)
            live = [row for row in (line.split() for line in table.splitlines()[1:])
                    if int(row[1]) == p.pid and not row[2].startswith("Z")]
            if not live or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        self.assertEqual(live, [])
        self.assertFalse(Path(f"/proc/{p.pid}").exists())


if __name__ == "__main__":
    unittest.main()
