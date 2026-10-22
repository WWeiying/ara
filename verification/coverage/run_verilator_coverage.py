#!/usr/bin/env python3
"""Run a passing Ara ELF on an instrumented Verilator image and save coverage."""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path


SUCCESS = re.compile(r"Core Test \*{3} SUCCESS \*{3} \(tohost = 0\)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log_tail(path: Path, limit=20) -> list[str]:
    with path.open("rb") as source:
        source.seek(0, 2)
        source.seek(max(0, source.tell() - 16384))
        return source.read().decode("utf-8", errors="replace").splitlines()[-limit:]


def summarize_lcov(path: Path, include_paths=()) -> dict:
    files = set()
    lines = {}
    branches = {}
    current = None
    for raw in path.read_text().splitlines():
        if raw.startswith("SF:"):
            current = raw[3:]
            if include_paths and not any(token in current for token in include_paths):
                current = None
            if current is not None:
                files.add(current)
        elif raw.startswith("DA:") and current is not None:
            line, hits, *_ = raw[3:].split(",")
            key = (current, int(line))
            lines[key] = max(lines.get(key, 0), int(hits))
        elif raw.startswith("BRDA:") and current is not None:
            line, block, branch, hits = raw[5:].split(",")
            key = (current, line, block, branch)
            branches[key] = max(branches.get(key, 0), 0 if hits == "-" else int(hits))
        elif raw == "end_of_record":
            current = None
    return {
        "source_files": len(files),
        "lines_total": len(lines),
        "lines_hit": sum(hits > 0 for hits in lines.values()),
        "branches_total": len(branches),
        "branches_hit": sum(hits > 0 for hits in branches.values()),
    }


def summarize_raw(path: Path, hierarchy_prefix="") -> dict:
    by_type = {}
    matched = 0
    for properties, count in iter_raw_points(path, hierarchy_prefix):
        point_type = properties.get("t", "unknown")
        bucket = by_type.setdefault(point_type, {"total": 0, "hit": 0})
        bucket["total"] += 1
        bucket["hit"] += count > 0
        matched += 1
    return {"hierarchy_prefix": hierarchy_prefix or None,
            "points_total": matched,
            "points_hit": sum(bucket["hit"] for bucket in by_type.values()),
            "by_type": by_type}


def iter_raw_points(path: Path, hierarchy_prefix=""):
    with path.open(encoding="utf-8", errors="replace") as source:
        for raw in source:
            if not raw.startswith("C '"):
                continue
            payload, separator, count_text = raw[3:].rstrip("\n").rpartition("' ")
            if not separator:
                raise ValueError(f"malformed Verilator coverage point in {path}")
            properties = dict(field.split("\x02", 1)
                              for field in payload.split("\x01") if "\x02" in field)
            hierarchy = properties.get("h", "").removeprefix("TOP.")
            if hierarchy_prefix and not (hierarchy == hierarchy_prefix or
                                         hierarchy.startswith(hierarchy_prefix + ".")):
                continue
            yield properties, int(count_text)


def write_uncovered_raw(path: Path, output: Path, hierarchy_prefix="", include_paths=()) -> dict:
    """Keep the full missed-point list while returning compact per-source counts."""
    by_source = {}
    by_type = {}
    total = hit = 0
    with output.open("w", encoding="utf-8") as stream:
        for properties, count in iter_raw_points(path, hierarchy_prefix):
            source = properties.get("f", "")
            if include_paths and not any(token in source for token in include_paths):
                continue
            point_type = properties.get("t", "unknown")
            for buckets, key in ((by_source, source or "<unknown>"),
                                 (by_type, point_type)):
                bucket = buckets.setdefault(key, {"total": 0, "hit": 0})
                bucket["total"] += 1
                bucket["hit"] += count > 0
            total += 1
            hit += count > 0
            if count == 0:
                item = {"source": source, "line": properties.get("l"),
                        "type": point_type, "instance": properties.get("h"),
                        "label": properties.get("o"), "point": properties.get("S")}
                stream.write(json.dumps(item, sort_keys=True) + "\n")
    return {"points_total": total, "points_hit": hit,
            "by_type": by_type, "by_source": by_source}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verilator-coverage", type=Path, required=True)
    parser.add_argument("--term-cycles", type=int, default=1000000)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--tohost-addr", type=lambda value: int(value, 0),
                        help="64-bit tohost address for VCS/Spike random programs")
    args = parser.parse_args()
    if args.term_cycles <= 0 or args.timeout <= 0:
        parser.error("term-cycles and timeout must be positive")
    if args.tohost_addr is not None and not (0x80000000 <= args.tohost_addr < 1 << 64 and
                                             args.tohost_addr % 8 == 0):
        parser.error("tohost-addr must be aligned and within RAM address space")

    source_simv = args.simv.resolve(strict=True)
    source_elf = args.elf.resolve(strict=True)
    reporter = args.verilator_coverage.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source_simv_sha256 = sha256(source_simv)
    source_elf_sha256 = sha256(source_elf)
    simv = output / "simv"
    elf = output / "input.elf"
    shutil.copy2(source_simv, simv)
    shutil.copy2(source_elf, elf)
    if sha256(simv) != source_simv_sha256 or sha256(elf) != source_elf_sha256:
        raise RuntimeError("simulator or ELF changed while freezing inputs")
    coverage = output / "coverage.dat"
    info = output / "coverage.info"
    command = [str(simv), f"--term-after-cycles={args.term_cycles}",
               f"--meminit=ram,{elf},elf", f"+verilator+coverage+file+{coverage}"]
    if args.tohost_addr is not None:
        command.append(f"+COMMIT_TOHOST={args.tohost_addr:016x}")
    result = {
        "status": "FAIL",
        "simv": str(simv),
        "simv_sha256": source_simv_sha256,
        "elf": str(elf),
        "elf_sha256": source_elf_sha256,
        "source_simv": str(source_simv),
        "source_elf": str(source_elf),
        "command": command,
        "timeout_s": args.timeout,
        "term_cycles": args.term_cycles,
        "tohost_addr": args.tohost_addr,
    }
    started = time.monotonic()
    try:
        with (output / "sim.log").open("w") as log:
            process = subprocess.run(command, cwd=output, stdout=log,
                                     stderr=subprocess.STDOUT, timeout=args.timeout,
                                     check=False)
        result["sim_returncode"] = process.returncode
        result["self_check_pass"] = bool(SUCCESS.search((output / "sim.log").read_text()))
        if process.returncode != 0 or not result["self_check_pass"]:
            result["reason"] = "simulation or in-program self-check failed"
        elif not coverage.is_file() or coverage.stat().st_size == 0:
            result["reason"] = "instrumented simulation did not write coverage.dat"
        else:
            report = subprocess.run([str(reporter), "--write-info", str(info),
                                     str(coverage)], cwd=output, capture_output=True,
                                    text=True, timeout=60, check=False)
            result["report_returncode"] = report.returncode
            result["report_output"] = report.stdout + report.stderr
            if report.returncode != 0 or not info.is_file() or info.stat().st_size == 0:
                result["reason"] = "verilator_coverage did not write a valid info file"
            else:
                result["raw_coverage"] = summarize_lcov(info)
                result["sim_log_sha256"] = sha256(output / "sim.log")
                result["coverage_sha256"] = sha256(coverage)
                result["coverage_info_sha256"] = sha256(info)
                result["status"] = "PASS"
    except subprocess.TimeoutExpired as exc:
        result["reason"] = f"timeout: {exc.cmd}"
    finally:
        result["elapsed_s"] = round(time.monotonic() - started, 3)
        log_path = output / "sim.log"
        if log_path.is_file():
            result["sim_log_sha256"] = sha256(log_path)
            result["sim_log_tail"] = log_tail(log_path)
        if coverage.is_file():
            result["coverage_sha256"] = sha256(coverage)
            result["coverage_bytes"] = coverage.stat().st_size
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{result['status']}: {output}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
