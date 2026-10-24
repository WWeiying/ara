"""Strict compact on-chip numerical evidence plus actual AKV work accounting."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "verification/akv"))
from run_refill_overlap_probe import numeric_fields, COUNTERS, PERF_FIELDS, SUMMARY_FIELDS

SHAPES = [dict(id=0, head=0, d=64, tokens=1, stride=320),
          dict(id=1, head=1, d=96, tokens=63, stride=256),
          dict(id=2, head=1, d=128, tokens=64, stride=320)]
EXPECTED = dict(pairs=3, runs=6, qk_outputs=512, pv_outputs=1152, full=6, release=6,
                column_single=576, column_panel4=72, logical_columns=864,
                row_load=384, commands=1044, q_external_bytes=2304,
                kv_external_bytes=147456, read_ranges=786, read_payload_bytes=150144,
                replay_bytes=196416)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def check_output(text, cases, golden):
    require(len(cases) == 3 and len(golden) == 1536, "Bad oracle geometry")
    require([{k: c[k] for k in SHAPES[0]} for c in cases] == SHAPES, "Changed test shapes")
    require(all(isinstance(c['fcsr'], int) and c['fcsr'] & ~31 == 0 and c['fcsr'] & 8
                for c in cases), "Invalid expected CSR")
    require(not re.search(r"\b(?:FAIL|FAILED|FATAL|TIMEOUT)\b|Core Test \*\*\* FAILURE", text, re.I),
            "Failure in simulator transcript")
    require(text.count("Core Test *** SUCCESS") == 1, "Missing/duplicate SoC terminal")
    lines = [s for s in text.splitlines() if s.startswith("PAIR_")]
    require(len(lines) == 26 and lines[0] == "PAIR_CAP native=1 panel4=1 vlenb=128 pairs=3",
            "Missing/extra numeric evidence")
    pos, pv = 1, []
    for c in cases:
        i, d, t = c['id'], c['d'], c['tokens']
        paired = []
        for mode in (0, 1):
            require(lines[pos] == f"PAIR_BEGIN case={i} mode={mode} head={c['head']} d={d} tokens={t} stride={c['stride']}", "Incorrect BEGIN")
            require(lines[pos+1] == f"PAIR_QK case={i} mode={mode} outputs={2*t} tailbytes={512-8*t} compared=512 hash={fnv(golden[i*512:(i+1)*512]):08x} fcsr={c['fcsr']} vcsr=5 guardbytes=1152 inputbytes=34112 errors=0", "Incorrect QK exact-comparison evidence")
            m = re.fullmatch(rf"PAIR_PV case={i} mode={mode} outputs={2*d} gapbytes={1024-4*d} baseline_bytes={1024*mode} hash=([0-9a-f]{{8}}) fcsr=(\d+) vcsr=5 guardbytes=1152 inputbytes=34112 errors=0", lines[pos+2])
            require(m is not None, "Incorrect PV regression evidence")
            require(int(m[2]) & ~31 == 0 and int(m[2]) & 8, "PV FRM/sticky flag changed")
            paired.append((m[1], int(m[2])))
            require(lines[pos+3] == f"PAIR_END case={i} mode={mode} errors=0", "Incorrect END")
            pos += 4
        require(paired[0] == paired[1], "PV baseline/candidate digest or FCSR differs")
        pv.append(dict(case=i, hash=paired[0][0], fcsr=paired[0][1]))
    require(lines[pos] == "PAIR_SUITE_PASS pairs=3 runs=6 qk_outputs=512 pv_outputs=1152 commands=1044", "Incorrect suite completion")
    return dict(state="PASS", pairs=3, runs=6, qk_outputs=512, pv_outputs=1152,
                pv_regression=pv, oracle="QK independent host fmaf; PV canonical baseline only",
                comparison="On-chip exact bytes/CSRs; UART hashes are secondary, not acceptance substitutes")


def command_work(case, mode):
    d, t = case['d'], case['tokens']
    return [4] + [6] * (d // 4 if mode else 2*d) + [2] * (t if mode else 2*t) + [3]


def expected_record(case, mode, command, sequence):
    d = case['d']
    full, col, row, release = (int(command == c) for c in (4, 6, 2, 3))
    logical = col * (4 if mode else 1)
    return dict(seq=sequence, command=command, success=1, fault=0,
                validation_fault=0, validation_error=0, read_fault=0,
                context_ready=1-release, full=0, refill=0, load=row, release=release,
                v2_full=full, v2_refill=0, v2_row_load=row, v2_column_load=col,
                v2_column_panel=col*mode, v2_logical_column=logical,
                v2_k_view_bank_cycles=8*col, v2_bank_conflict_cycles=0, v2_rejected=0,
                q_external_bytes=4*d*full, kv_external_bytes=256*d*full,
                replay_bytes=128*logical+2*d*row, read_ranges=131*full,
                read_payload_bytes=(64+260*d)*full)


def check_perf(text):
    records, summaries, active, next_run, qk_done, pv_done = [], [], None, 0, False, False
    for line in text.splitlines():
        if line.startswith("PAIR_BEGIN "):
            require(active is None and next_run < 6, "Unexpected run BEGIN")
            case, mode = SHAPES[next_run//2], next_run % 2
            require(line == f"PAIR_BEGIN case={case['id']} mode={mode} head={case['head']} d={case['d']} tokens={case['tokens']} stride={case['stride']}", "Workload order changed")
            active = [case, mode, 0]
            qk_done = pv_done = False
        elif "[AKV_PERF]" in line:
            require(line.startswith("[AKV_PERF] ") and active is not None and not pv_done,
                    "Command outside numeric run")
            case, mode, index = active
            work = command_work(case, mode)
            require(index < len(work), "Extra command")
            cmd = work[index]
            require((cmd in (4, 6)) != qk_done, "Command crosses QK/PV stage boundary")
            r = numeric_fields(line[len("[AKV_PERF] "):], PERF_FIELDS)
            want = expected_record(case, mode, cmd, len(records)+1)
            require(all(r[k] == v for k, v in want.items()), f"Work/lifecycle/fault mismatch at seq {len(records)+1}")
            require(r['id'] < 8 and r['busy_cycles'] > 0 and r['read_outstanding_max'] <= 2, "Invalid ID/cycles/outstanding")
            if cmd == 4:
                require(r['ar'] >= 131 and r['r_beats'] >= r['ar'] and r['read_outstanding_max'] > 0, "FULL lacks read traffic")
            else:
                require(all(r[k] == 0 for k in ('ar', 'r_beats', 'translations', 'read_outstanding_max', 'read_outstanding_occ_sum')), "Unexpected external read")
            records.append(r)
            active[2] += 1
        elif line.startswith("PAIR_QK "):
            require(active is not None and not qk_done and active[2] == 1 + (active[0]['d']//4 if active[1] else 2*active[0]['d']), "Missing QK commands")
            qk_done = True
        elif line.startswith("PAIR_PV "):
            require(active is not None and qk_done and not pv_done and active[2] == len(command_work(active[0], active[1])), "Missing PV/release commands")
            pv_done = True
        elif line.startswith("PAIR_END "):
            require(active is not None and pv_done, "Premature END")
            active = None
            next_run += 1
        elif "[AKV_PERF_SUMMARY]" in line:
            require(line.startswith("[AKV_PERF_SUMMARY] ") and active is None and next_run == 6, "Premature/malformed summary")
            summaries.append(numeric_fields(line[len("[AKV_PERF_SUMMARY] "):], SUMMARY_FIELDS))
    require(active is None and next_run == 6 and len(records) == 1044 and len(summaries) == 1, "Incomplete hardware evidence")
    require("[QBS_PERF]" not in text, "Unexpected QBS work")
    total = {k: max(r[k] for r in records) if k == 'read_outstanding_max' else sum(r[k] for r in records) for k in COUNTERS}
    total.update(records=1044, success_records=1044, fault_records=0, validation_fault_records=0)
    require(summaries[0] == total, "Summary differs from exact per-command evidence")
    for k in ('q_external_bytes', 'kv_external_bytes', 'read_ranges', 'read_payload_bytes', 'replay_bytes'):
        require(total[k] == EXPECTED[k], "Aggregate work changed: " + k)
    return total


def check_pins(build):
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    report = json.loads((build / 'build.json').read_text())
    require(report['state'] == 'BUILT_NOT_EXECUTED' and report['expected'] == EXPECTED and report['post_pins_match'], "Invalid build receipt")
    require(sha(build/'source-pins.json') == report['source_pins_sha256'], "Source receipt drift")
    for pins in (json.loads((build/'source-pins.json').read_text()), report['artifact_sha256']):
        for path, digest in pins.items():
            require(sha(path) == digest, "Source/artifact drift: " + path)
    require(sha(report['elf']) == report['elf_sha256'], "ELF drift")
    return report


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', required=True, type=Path)
    p.add_argument('--log', required=True, type=Path)
    a = p.parse_args()
    report = check_pins(a.build)
    text = a.log.read_text()
    numeric = check_output(text, report['cases'], (a.build/'golden.bin').read_bytes())
    counters = check_perf(text)
    print(json.dumps(dict(state='NUMERIC_AND_WORK_CHECKED', numeric=numeric, counters=counters,
                          acceptance='Still requires unchanged independent UVM backend/AXI-write checks and run image/source pre/post pins'), sort_keys=True))
