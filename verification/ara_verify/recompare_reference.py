"""Recompare frozen Ara traces against a different Spike without rerunning RTL."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .artifacts import sha256, simulation_image
from .random_rvv import _run_logged
from .rvv_postprocess import postprocess_existing_case


COPIED_FILES = (
    "ara_commit_trace.csv",
    "ara_vector_trace.csv",
    "trace_hart_0.log",
    "rtl_console.log",
    "run.vcs.log",
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_case(source: Path, row: dict) -> Path:
    case = Path(row["artifact_dir"]).resolve()
    if case.parent != source / "tests" or not case.is_dir():
        raise ValueError(f"case is outside source run: {case}")
    return case


def recompare(source: Path, output: Path, spike: Path, names: set[str],
              timeout_s: int, readelf: Path) -> list[dict]:
    source = source.resolve(strict=True)
    spike = spike.resolve(strict=True)
    readelf = readelf.resolve(strict=True)
    if not spike.is_file() or timeout_s <= 0:
        raise ValueError("Spike must be a file and timeout must be positive")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output must be new or empty: {output}")
    rows = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("source summary has no cases")
    selected = [row for row in rows if not names or row["name"] in names]
    if names.difference(row["name"] for row in selected):
        raise ValueError("requested case is absent from source summary")
    if not selected:
        raise ValueError("no cases selected")
    output.mkdir(parents=True, exist_ok=True)
    source_run = json.loads((source / "run.json").read_text(encoding="utf-8"))
    run = {
        "status": "RUNNING", "source_run": str(source),
        "invocation": sys.argv, "git": source_run.get("git"),
        "spike": {"path": str(spike), "sha256": sha256(spike)},
        "input_snapshots": True,
        "tests": [row["name"] for row in selected],
    }
    _write_json(output / "run.json", run)
    results = []
    image_cache: dict[str, dict[str, str]] = {}
    for row in selected:
        if row.get("vector_checkpoints"):
            raise ValueError("checkpoint cases need checkpoint-aware recomparison")
        old = _source_case(source, row)
        case = output / "tests" / old.name
        case.mkdir(parents=True)
        elf_source = Path(row["elf"]).resolve(strict=True)
        elf = case / "input.elf"
        shutil.copy2(elf_source, elf)
        sources = {str(elf_source): sha256(elf)}
        if sha256(elf_source) != sources[str(elf_source)]:
            raise ValueError(f"source ELF changed while freezing: {elf_source}")
        for name in COPIED_FILES:
            original = old / name
            if original.is_file():
                shutil.copy2(original, case / name)
                sources[str(original)] = sha256(case / name)
                if sha256(original) != sources[str(original)]:
                    raise ValueError(f"source trace changed while freezing: {original}")
        command_info = json.loads((old / "rtl.command.json").read_text(encoding="utf-8"))
        rtl_command = command_info["command"]
        rtl_command = [f"+PRELOAD={elf}" if arg.startswith("+PRELOAD=") else arg
                       for arg in rtl_command]
        _write_json(case / "rtl.command.json", {**command_info, "command": rtl_command})
        simv = Path(rtl_command[0]).resolve(strict=True)
        if str(simv) not in image_cache:
            image_cache[str(simv)] = simulation_image(simv)
        _write_json(case / "inputs.json", {
            "binary": {"source": str(elf_source), "path": str(elf), "sha256": sha256(elf)},
            "simv": {"path": str(simv), "image_sha256": image_cache[str(simv)]},
        })
        _write_json(case / "source_evidence.json", {
            "source_case": str(old), "copied_sha256": sources,
            "source_result_status": row["status"],
        })
        spike_log = case / "spike_commit.log"
        spike_command = [str(spike), "--isa=rv64gcv_zvl1024b", "--log-commits",
                         f"--log={spike_log}", str(elf)]
        _write_json(case / "spike.command.json", {"command": spike_command, "cwd": str(case)})
        rc, elapsed, timed_out = _run_logged(
            spike_command, case, case / "spike_console.log", timeout_s=timeout_s)
        _write_json(case / "reference_output.json", {
            "spike_sha256": run["spike"]["sha256"],
            "spike_commit_sha256": sha256(spike_log) if spike_log.is_file() else None,
            "spike_console_sha256": sha256(case / "spike_console.log"),
        })
        result = postprocess_existing_case(case, readelf)
        result.update({"source_case": str(old), "spike_returncode": rc,
                       "spike_elapsed_s": round(elapsed, 3), "spike_timed_out": timed_out,
                       "vector_signature": bool(row.get("vector_signature"))})
        if rc != 0 or timed_out:
            result["status"] = "SPIKE_FAIL"
            result["reason"] = f"Spike returncode={rc} timed_out={timed_out}"
        _write_json(case / "result.json", result)
        results.append(result)
        print(f"[{result['status']}] {old.name}", flush=True)
    _write_json(output / "summary.json", results)
    run["status"] = "COMPLETE"
    _write_json(output / "run.json", run)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--spike", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    results = recompare(args.source_run, args.output.resolve(), args.spike,
                        set(args.case), args.timeout,
                        root / "install/riscv-gcc/bin/riscv64-unknown-elf-readelf")
    return 0 if all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
