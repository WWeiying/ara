"""Check the Spike vector-restart behavior required by RVV differential tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .artifacts import sha256


def check_spike_vstart(spike: Path, gcc: Path, output: Path, source: Path) -> dict:
    spike = spike.resolve(strict=True)
    gcc = gcc.resolve(strict=True)
    source = source.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=True)
    elf = output / "spike_vstart_probe.elf"
    compile_command = [
        str(gcc), "-march=rv64gcv_zvl1024b", "-mabi=lp64d",
        "-nostdlib", "-nostartfiles", "-Wl,-Ttext-segment=0x80000000",
        "-Wl,--no-relax", "-o", str(elf), str(source),
    ]
    compiled = subprocess.run(compile_command, capture_output=True, text=True,
                              timeout=30, check=False)
    (output / "compile.log").write_text(compiled.stdout + compiled.stderr,
                                         encoding="utf-8")
    report = {
        "status": "FAIL", "spike": str(spike), "spike_sha256": sha256(spike),
        "source": str(source), "source_sha256": sha256(source),
        "gcc": str(gcc), "compile_command": compile_command,
        "compile_returncode": compiled.returncode,
    }
    if compiled.returncode == 0:
        report["elf_sha256"] = sha256(elf)
        command = [str(spike), "--isa=rv64gcv_zvl1024b", str(elf)]
        report["spike_command"] = command
        try:
            completed = subprocess.run(command, capture_output=True, text=True,
                                       timeout=5, check=False)
            report["spike_returncode"] = completed.returncode
            (output / "spike_console.log").write_text(
                completed.stdout + completed.stderr, encoding="utf-8")
            report["status"] = "PASS" if completed.returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired as error:
            report["spike_returncode"] = None
            report["reason"] = f"Spike probe timed out: {error}"
    (output / "spike_probe.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def probe_paths(repo_root: Path) -> tuple[Path, Path]:
    return (repo_root / "install/riscv-gcc/bin/riscv64-unknown-elf-gcc",
            repo_root / "verification/riscv_dv/spike_vstart_probe.S")


__all__ = ["check_spike_vstart", "probe_paths"]
