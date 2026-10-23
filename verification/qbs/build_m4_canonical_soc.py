#!/usr/bin/env python3
"""Retarget the accepted ABBA harness to the canonical GGML helper.

Reuse the frozen generic oracle, real capture, golden and support objects.
Only the optimized-helper translation unit is rebuilt; never edit the old build.
"""
import argparse
import json
from pathlib import Path
import subprocess

from run_half_scale_soc import atomic_json, digest, hashes, ROOT


def retarget(text):
    replacements = {
        '#include "ggml_m4_prepare_candidate.h"': '#include "arch/riscv/q8_0-m4.h"',
        'qbs_m4_prepare_candidate::quantize': 'ggml_riscv_q8_0_m4::quantize',
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise ValueError("Harness boundary changed: " + before)
        text = text.replace(before, after)
    return text


def validate_oracle(repack, archived):
    start = '\nvoid ggml_quantize_mat_q8_0_4x1_generic('
    end = '\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic('
    if repack.count(start) != 1 or repack.count(end) != 1:
        raise ValueError("Production generic boundaries changed")
    body = repack[repack.index(start):repack.index(end)]
    expected = '#include "ggml_m4_prepare_candidate.h"\nextern "C" {\n' + body + '\n}\n'
    if archived != expected:
        raise ValueError("Production generic no longer equals the archived oracle")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous", type=Path, required=True)
    p.add_argument("--llama", type=Path, default=Path("/home/wangwy/llama/llama.cpp"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    previous = args.previous.resolve(strict=True)
    original_pins = json.loads((previous / "manifest.json").read_text())
    repack = args.llama.resolve(strict=True) / "ggml/src/ggml-cpu/repack.cpp"
    current_pins = hashes(map(Path, original_pins))
    changed = [path for path in original_pins if original_pins[path] != current_pins[path]]
    if any(path != str(repack) for path in changed):
        raise ValueError("Unrelated prior build inputs drifted: " + repr(changed))
    validate_oracle(repack.read_text(), (previous / "production_oracle.cpp").read_text())
    report = json.loads((previous / "build.json").read_text())
    if (report["state"] != "BUILT_NOT_EXECUTED" or
            report["elf_sha256"] != digest(previous / "qbs_m4_prepare_soc")):
        raise ValueError("Prior build identity changed")
    commands = json.loads((previous / "commands.json").read_text())
    compile_cmd, link_cmd = commands[0][:], commands[-1][:]
    source = ROOT / "verification/qbs/m4_prepare_soc.cpp"
    if str(source) not in compile_cmd or "-c" not in compile_cmd:
        raise ValueError("Unexpected compile recipe")
    old_obj = Path(compile_cmd[compile_cmd.index("-o") + 1])
    if str(old_obj) not in link_cmd:
        raise ValueError("Compiled object not linked")
    objects = [Path(x) for x in link_cmd if x.endswith(".o")]
    helper = args.llama.resolve(strict=True) / "ggml/src/ggml-cpu/arch/riscv/q8_0-m4.h"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    generated = out / "m4_canonical_soc.cpp"
    generated.write_text(retarget(source.read_text()))
    obj = out / "canonical.o"
    elf = out / "qbs_m4_prepare_soc"
    compile_cmd[compile_cmd.index(str(source))] = str(generated)
    compile_cmd[compile_cmd.index("-o") + 1] = str(obj)
    compile_cmd += ["-ffp-contract=off"]
    link_cmd[link_cmd.index(str(old_obj))] = str(obj)
    link_cmd[link_cmd.index("-o") + 1] = str(elf)
    link_cmd = ["-Wl,-Map=" + str(out / "link.map") if x.startswith("-Wl,-Map=") else x
                for x in link_cmd]
    pins = {**current_pins, **hashes([Path(__file__), helper, generated, *objects,
            previous / "production_oracle.cpp",
            previous / "commands.json", previous / "build.json", previous / "manifest.json",
            previous / "golden_state.h", previous / "link.ld"])}
    atomic_json(out / "manifest.json", pins)
    atomic_json(out / "commands.json", [compile_cmd, link_cmd])
    for label, command in (("compile", compile_cmd), ("link", link_cmd)):
        with (out / (label + ".log")).open("x") as log:
            subprocess.run(command, cwd=previous, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=120)
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Inputs changed during build")
    atomic_json(out / "build.json", dict(state="BUILT_NOT_EXECUTED",
                elf_sha256=digest(elf), manifest_sha256=digest(out / "manifest.json"),
                canonical_helper_sha256=digest(helper), previous=str(previous),
                validated_generic_source_drift={path: {"before": original_pins[path],
                    "after": current_pins[path]} for path in changed},
                scope="Canonical shared helper; unchanged generic oracle and real M4/K896 ABBA work"))
    print(elf)


if __name__ == "__main__":
    main()
