"""Host-only strict-checker tests. No simulator, build, or shared-source writes."""
import copy
import csv
import io
from pathlib import Path
import tempfile
import unittest

import run_refill_overlap_probe as probe


def kv(tag, values):
    return tag + " " + " ".join(f"{k}={v}" for k, v in values.items())


def fixture_perf(command, seq):
    # Explicit synthetic hardware records, independent of check_perf's expected dict.
    r = dict.fromkeys(probe.PERF_FIELDS, 0)
    r.update(seq=seq, id=seq % 8, command=command, success=1, busy_cycles=100,
             context_ready=int(command != 3))
    if command == 4:
        r.update(v2_full=1, q_external_bytes=256, kv_external_bytes=32768,
                 read_ranges=130, read_payload_bytes=33088, ar=132,
                 r_beats=2068, read_outstanding_max=2)
    elif command == 5:
        r.update(v2_refill=1, kv_external_bytes=4096, read_ranges=16,
                 read_payload_bytes=4096, ar=16, r_beats=256, read_outstanding_max=2)
    elif command == 2:
        r.update(load=1, v2_row_load=1, replay_bytes=256)
    elif command == 3:
        r.update(release=1)
    else:
        raise AssertionError(command)
    return r


def fixture_log():
    lines = ["AKV_REFILL_PROBE_CAPS word0=000f010808400101 word1=00000000006b1a5b "
             "word2=000001ff06084002 word3=0000000001803e5b",
             "AKV_REFILL_PROBE_EXPECT commands=54 v2_full=2 v2_refill=2 load=48 "
             "v2_row_load=48 release=2 q_external_bytes=512 kv_external_bytes=73728 "
             "replay_bytes=12288 read_ranges=292 read_payload_bytes=74368"]
    records = []
    for mode, start in (("immediate", 100), ("serial", 1000)):
        lines.append(f"AKV_REFILL_PROBE_BEGIN mode={mode} d=128 q_rows=1 kv_length=72 "
                     "tile_start=64 tile_count=8 fmas=16 elements=128")
        for command in [4] + [2] * 7 + [5] + [2] * 17 + [3]:
            r = fixture_perf(command, len(records) + 1)
            records.append(r)
            lines.append(kv("[AKV_PERF]", r))
        lines += [f"AKV_REFILL_PROBE_CYCLES mode={mode} start={start} returned={start + 80} "
                  f"drained={start + 90} to_return=80 to_drain=90",
                  f"AKV_REFILL_PROBE_PASS mode={mode} arithmetic=128 fflags=8 vstart=0 "
                  "q_rows=2 k_rows=11 v_rows=11 canaries=2 traps=0"]
    summary = {k: sum(r[k] for r in records) for k in probe.COUNTERS}
    summary.update(read_outstanding_max=2, records=54, success_records=54,
                   fault_records=0, validation_fault_records=0)
    lines += ["AKV_REFILL_PROBE_SUITE_PASS modes=2 traps=0", "Core Test *** SUCCESS ***",
              kv("[AKV_PERF_SUMMARY]", summary), "UVM_ERROR : 0", "UVM_FATAL : 0"]
    return "\n".join(lines) + "\n"


def commit_row(cycle, event, order, insn, port=-1, pc=0, tid=1):
    row = dict.fromkeys(probe.COMMIT_HEADER, "0")
    row.update(cycle=str(cycle), event=event, order=str(order), port=str(port),
               trans_id=str(tid), insn=f"{insn:08x}", pc=f"{pc:016x}")
    return row


def csv_text(rows, header):
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=header, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return text.getvalue()


def fixture_trace():
    rows = []
    now, order, retired = 10, 0, 0

    def issue(insn, pc=None, backend=True, delay=5, alloc_delay=1):
        nonlocal now, order, retired
        vid = 2 if insn == probe.REFILL else 1
        rows.append(commit_row(now, "arch_start", order, insn))
        rows.append(commit_row(now + 1, "cvx_req", -1, insn))
        if backend:
            rows.append(commit_row(now + alloc_delay, "uop_alloc", order, insn, port=vid))
            rows.append(commit_row(now + delay, "uop_done", order, insn, port=vid))
        if pc is not None:
            rows.append(commit_row(now + 2, "retire", retired, insn, port=0, pc=pc, tid=-1))
            retired += 1
        order += 1
        now += max(10, alloc_delay + delay)

    for _ in range(4):
        issue(probe.INFO, backend=False)
    for mode in ("immediate", "serial"):
        issue(probe.FULL)
        for _ in range(7):
            issue(probe.LOAD)
        for i in range(16):
            start = now
            issue(probe.FMA, probe.PC[mode]["first"] + i * 4,
                  delay=30 if i == 15 and mode == "immediate" else 5)
            if i == 15 and mode == "immediate":
                now = start + 10  # REFILL presented 20 cycles before final FMA done.
        if mode == "serial":
            issue(0x0c82f057)
        issue(probe.REFILL, probe.PC[mode]["refill"], alloc_delay=21, delay=40)
        for _ in range(17):
            issue(probe.LOAD)
        issue(probe.RELEASE)
    priority = dict(arch_start=0, uop_done=1, uop_alloc=2, retire=3, cvx_req=4)
    rows.sort(key=lambda r: (int(r["cycle"]), priority[r["event"]]))
    vector = [dict.fromkeys(probe.VECTOR_HEADER, "0")]
    vector[0].update(event="config", nr_lanes="4", vlen_bits="1024")
    for r in rows:
        if r["event"] not in ("uop_alloc", "uop_done"):
            continue
        v = dict.fromkeys(probe.VECTOR_HEADER, "0")
        v.update(cycle=r["cycle"], event=r["event"].removeprefix("uop_"),
                 arch_seq=r["order"], vid=r["port"], insn=r["insn"],
                 nr_lanes="4", vlen_bits="1024")
        vector.append(v)
    return rows, vector


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.text = fixture_log()

    def reject(self, text):
        with self.assertRaises(ValueError):
            probe.check_log(text)

    def test_exact_success(self):
        result = probe.check_log(self.text)
        self.assertEqual(result["hardware_totals"]["records"], 54)
        self.assertEqual(result["hardware_totals"]["replay_bytes"], 12288)

    def test_missing_each_program_marker(self):
        for line in self.text.splitlines():
            if line.startswith("AKV_REFILL_PROBE_"):
                with self.subTest(line=line):
                    self.reject(self.text.replace(line + "\n", "", 1))

    def test_extra_each_program_marker(self):
        for line in self.text.splitlines():
            if line.startswith("AKV_REFILL_PROBE_"):
                with self.subTest(line=line):
                    self.reject(self.text.replace(line, line + "\n" + line, 1))

    def test_unknown_and_duplicate_fields_all_records(self):
        for line in self.text.splitlines():
            if line.startswith(("AKV_REFILL_PROBE_", "[AKV_PERF")):
                for suffix in (" unknown=1", " " + line.split()[1]):
                    with self.subTest(line=line[:50], suffix=suffix):
                        self.reject(self.text.replace(line, line + suffix, 1))

    def test_missing_each_field_all_schemas(self):
        seen = set()
        for line in self.text.splitlines():
            if not line.startswith(("AKV_REFILL_PROBE_", "[AKV_PERF")):
                continue
            tokens = line.split()
            if tokens[0] in seen:
                continue
            seen.add(tokens[0])
            for token in tokens[1:]:
                with self.subTest(tag=tokens[0], token=token):
                    self.reject(self.text.replace(line, line.replace(" " + token, "", 1), 1))

    def test_missing_extra_reordered_commands(self):
        lines = self.text.splitlines()
        indices = [i for i, s in enumerate(lines) if s.startswith("[AKV_PERF] ")]
        for index in indices:
            with self.subTest(index=index):
                self.reject("\n".join(lines[:index] + lines[index + 1:]))
        self.reject(self.text.replace(lines[indices[0]], "\n".join([lines[indices[0]]] * 2)))
        a, b = indices[:2]
        lines[a], lines[b] = lines[b], lines[a]
        self.reject("\n".join(lines))

    def test_wrong_count_flags_unknown_numeric_and_failures(self):
        for before, after in (("commands=54", "commands=298"), ("k_rows=11", "k_rows=72"),
                              ("fflags=8", "fflags=0"), ("success=1", "success=0"),
                              ("busy_cycles=100", "busy_cycles=x"), ("seq=1 ", "seq=0 "),
                              ("read_ranges=130", "read_ranges=129"),
                              ("replay_bytes=256", "replay_bytes=255"),
                              ("records=54", "records=53"), ("to_return=80", "to_return=79"),
                              ("word2=000001ff06084002", "word2=xxxxxxxxxxxxxxxx"),
                              ("word2=000001ff06084002", "word2=000001fe06084002"),
                              ("UVM_ERROR : 0", "UVM_ERROR : 1")):
            with self.subTest(before=before):
                self.reject(self.text.replace(before, after, 1))
        for extra in ("AKV_REFILL_PROBE_FAIL stage=bad", "AKV_REFILL_PROBE_WHATEVER value=1",
                      "Fatal: simulated failure", "Error: failure", "[QBS_PERF] success=1"):
            self.reject(self.text + extra + "\n")

    def test_summary_and_core_required_exactly_once(self):
        for tag in ("[AKV_PERF_SUMMARY]", "Core Test *** SUCCESS"):
            line = next(s for s in self.text.splitlines() if s.startswith(tag))
            self.reject(self.text.replace(line, ""))
            self.reject(self.text + line + "\n")


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.vector = fixture_trace()

    def check(self, rows=None, vector=None):
        return probe.check_traces(io.StringIO(csv_text(self.rows if rows is None else rows,
                                                      probe.COMMIT_HEADER)),
                                  io.StringIO(csv_text(self.vector if vector is None else vector,
                                                      probe.VECTOR_HEADER)))

    def test_order_join_and_zero_window_are_valid(self):
        result = self.check()
        self.assertEqual(result["modes"]["immediate"]["remaining_arithmetic_cycles"], 20)
        self.assertEqual(result["modes"]["serial"]["remaining_arithmetic_cycles"], 0)
        self.assertNotIn("command_fire", result["modes"]["immediate"])

    def test_missing_extra_unknown_csv_columns(self):
        commit = csv_text(self.rows, probe.COMMIT_HEADER)
        vector = csv_text(self.vector, probe.VECTOR_HEADER)
        for c, v in ((commit.replace("cycle,event,", "event,", 1), vector),
                     (commit.replace("cycle,event,", "cycle,unknown,event,", 1), vector),
                     (commit, vector.replace("cycle,event,", "cycle,unknown,event,", 1))):
            with self.assertRaises(ValueError):
                probe.check_traces(io.StringIO(c), io.StringIO(v))

    def test_corrupt_commit_events(self):
        for event, field, value in (("arch_start", "order", "1"),
                                    ("uop_done", "insn", "ffffffff"),
                                    ("uop_done", "order", "9999"),
                                    ("uop_alloc", "port", "9"),
                                    ("cvx_req", "trans_id", "9"),
                                    ("retire", "pc", "0000000000000000"),
                                    ("retire", "trap", "1"),
                                    ("arch_start", "cycle", "x"),
                                    ("arch_start", "event", "unknown")):
            rows = copy.deepcopy(self.rows)
            next(r for r in rows if r["event"] == event)[field] = value
            with self.subTest(event=event, field=field), self.assertRaises(ValueError):
                self.check(rows=rows)

    def test_missing_done_duplicate_done_and_wrong_vid(self):
        index = next(i for i, r in enumerate(self.rows) if r["event"] == "uop_done")
        for rows in (self.rows[:index] + self.rows[index + 1:],
                     self.rows[:index] + [self.rows[index]] + self.rows[index:]):
            with self.assertRaises(ValueError):
                self.check(rows=rows)
        rows = copy.deepcopy(self.rows)
        rows[index]["port"] = "7"
        with self.assertRaises(ValueError):
            self.check(rows=rows)

    def test_vector_missing_done_metadata_geometry_or_reset(self):
        for field, value in (("event", "reset"), ("arch_seq", "99999"),
                             ("insn", "xxxxxxxx"), ("nr_lanes", "8"), ("vlen_bits", "128")):
            vector = copy.deepcopy(self.vector)
            vector[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(vector=vector)
        with self.assertRaises(ValueError):
            self.check(vector=self.vector[:-1])

    def test_command_missing_from_both_backend_traces(self):
        order = next(r["order"] for r in self.rows if
                     r["event"] == "arch_start" and r["insn"] == "0205345b")
        rows = [r for r in self.rows if not (r["order"] == order and
                r["event"] in ("uop_alloc", "uop_done"))]
        vector = [r for r in self.vector if r["arch_seq"] != order]
        with self.assertRaisesRegex(ValueError, "no backend completion"):
            self.check(rows, vector)

    def test_serial_drain_wrong_instruction(self):
        rows = copy.deepcopy(self.rows)
        for r in rows:
            if r["insn"] == "0c82f057":
                r["insn"] = "0c92f057"
        vector = copy.deepcopy(self.vector)
        for r in vector:
            if r["insn"] == "0c82f057":
                r["insn"] = "0c92f057"
        with self.assertRaises(ValueError):
            self.check(rows, vector)

    def test_multiple_uops_per_order_use_last_completion(self):
        rows, vector = copy.deepcopy(self.rows), copy.deepcopy(self.vector)
        done = next(r for r in rows if r["event"] == "uop_done" and r["insn"] == "b3481457")
        order = done["order"]
        alloc = copy.deepcopy(done)
        alloc.update(event="uop_alloc", cycle=str(int(done["cycle"]) + 1), port="3")
        end = copy.deepcopy(alloc)
        end.update(event="uop_done", cycle=str(int(done["cycle"]) + 2))
        rows.extend([alloc, end])
        rows.sort(key=lambda r: int(r["cycle"]))
        for r in (alloc, end):
            v = dict.fromkeys(probe.VECTOR_HEADER, "0")
            v.update(cycle=r["cycle"], event=r["event"].removeprefix("uop_"),
                     arch_seq=order, vid="3", insn=r["insn"], nr_lanes="4", vlen_bits="1024")
            vector.append(v)
        vector.sort(key=lambda r: int(r["cycle"]))
        result = self.check(rows, vector)
        self.assertEqual(result["modes"]["immediate"]["fma_uop_counts"][0], 2)


class RunnerTests(unittest.TestCase):
    def test_timeout_bounds_before_creating_output(self):
        from argparse import Namespace
        for timeout in (0, -1, 2701):
            with self.assertRaises(ValueError):
                probe.run(Namespace(timeout=timeout))

    def test_hashes_detect_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input"
            p.write_text("original")
            before = probe.hashes([p])
            p.write_text("changed")
            self.assertNotEqual(before, probe.hashes(before))

    def test_reject_unsealed_elf_before_other_receipt_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / "akv_refill_overlap_probe.elf").write_bytes(b"unapproved")
            (p / "build.json").write_text('{"elf_sha256":"wrong"}')
            with self.assertRaisesRegex(ValueError, "sealed"):
                probe.validate_build(p)


if __name__ == "__main__":
    unittest.main()
