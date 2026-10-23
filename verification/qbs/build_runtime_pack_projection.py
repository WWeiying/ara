#!/usr/bin/env python3
"""Build current-runtime scalar/vector twins from the frozen ten-object projection.

Requires the completed public-API native gate. Never modifies original objects,
sources, libraries, or the simulator. Does not run a guest or simulation.
"""
import argparse
import difflib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import sys

from run_half_scale_soc import ROOT, atomic_json, digest, hashes, run_command
from run_runtime_activation_pack import check_log


APP = "llama_qwen25_q8_0_prefill_m4_direct_qbs"
BASELINE_SHA256 = "ebc3363158f73c181bd5644c74b25a23cc28a3e6548747fd972927b6c53471da"
OBJECT_NAMES = [f"{i}-{name}.o" for i, name in enumerate((
    "main.c", "data.S", "crt0.S", "printf.c", "string.c", "serial.c", "util.c",
    "print_trap_cause.c", "qbs_runtime.c", "qbs_native_riscv.c"))]
RUNTIME = ROOT / "software/qbs/src/qbs_runtime.c"
HERE = Path(__file__).resolve().parent
DEFAULT_BASE = ROOT / "apps" / APP / "build-gnu-m4-pair-20261023-03"
DEFAULT_ANCHOR = ROOT / "verification/out/qbs-pack-projection-build-20261023-01"
DEFAULT_GATE = ROOT / "verification/out/qbs-runtime-pack-native-20261023-01"
PACK_SECTION = re.compile(r"^\.text\.(?:pack_activation_group|qbs_pack_activation_m4|"
                          r"qbs_pack_interleave_(?:bytes|aux16)_internal|"
                          r"qbs_pack_activation_m8_grouped)(?:[.]|$)")


def read_json(path):
    return json.loads(path.read_text())


def verify_pins(pins):
    if not pins or hashes(map(Path, pins)) != pins:
        raise ValueError("Pinned input/artifact changed")


def runtime_headers():
    base = ROOT / "software/qbs"
    return sorted([*base.glob("include/**/*.h"), *base.glob("src/*.h")])


def require_gate(directory):
    directory = directory.resolve(strict=True)
    status_path, manifest_path = directory / "status.json", directory / "manifest.json"
    state, pins = read_json(status_path), read_json(manifest_path)
    if state.get("state") != "PASS" or state.get("child_pid") is not None:
        raise ValueError("Public API gate is not completed PASS; no build/launch allowed")
    required = {str(path) for path in [RUNTIME, *runtime_headers(),
                HERE / "run_runtime_activation_pack.py", HERE / "test_runtime_activation_pack.c",
                HERE / "runtime_activation_pack_init.c"]}
    if not required <= pins.keys():
        raise ValueError("Native gate did not pin all current runtime sources/headers")
    verify_pins(pins)
    cases = state.get("cases", [])
    expected = [("scalar", 1024, 0), ("vector", 128, 0),
                ("vector", 1024, 0), ("vector", 1024, 7)]
    if [(c.get("mode"), c.get("vlen"), c.get("avl_limit")) for c in cases] != expected:
        raise ValueError("Native gate configuration coverage differs")
    artifacts = [status_path, manifest_path]
    for case in cases:
        label = f"{case['mode']}-avl{case['avl_limit']}"
        log = directory / f"vlen{case['vlen']}-{label}.log"
        elf = directory / f"init-{label}"
        if (digest(log) != case["log_sha256"] or digest(elf) != case["elf_sha256"] or
                check_log(log.read_text()) != {"cases": case.get("cases"),
                                              "invalid_cases": case.get("invalid_cases")}):
            raise ValueError("Native gate log/ELF/count mismatch")
        artifacts.extend([log, elf])
    return {**pins, **hashes(artifacts)}


def frozen_plan(base, anchor):
    report, anchor_report = read_json(base / "build.json"), read_json(anchor / "build.json")
    anchor_manifest = anchor / "manifest.json"
    if digest(anchor_manifest) != anchor_report["manifest_sha256"]:
        raise ValueError("Frozen pack build manifest changed")
    pins = read_json(anchor_manifest)
    elf = base / (APP + ".elf")
    if (report.get("app") != APP or report.get("scope") != "single_full_projection" or
            report.get("simulation_l2_mb") != 16 or
            report.get("elf_sha256") != BASELINE_SHA256 or
            anchor_report.get("baseline_sha256") != BASELINE_SHA256):
        raise ValueError("Unexpected real projection baseline")
    commands = read_json(base / "commands.json")
    links = [c["argv"] for c in commands if "-nostdlib" in c["argv"] and "-c" not in c["argv"]]
    compiles = [c["argv"] for c in commands if "-c" in c["argv"]]
    runtime = [c for c in compiles if Path(c[c.index("-c") + 1]) == RUNTIME]
    if len(links) != 1 or len(runtime) != 1 or len(compiles) != 10:
        raise ValueError("Unexpected baseline compile/link commands")
    link, compile_command = links[0], runtime[0]
    objects = [Path(x) for x in link if x.endswith(".o")]
    if ([p.name for p in objects] != OBJECT_NAMES or
            any(p.parent != base for p in objects) or
            any("--wrap" in x or "QBS_PACK_" in x for x in link + compile_command)):
        raise ValueError("Not the original ten-object unwrapped link")
    script = Path(link[link.index("-T") + 1])
    compiler = Path(compile_command[0])
    if link[0] != str(compiler):
        raise ValueError("Compiler/link driver differs")
    frozen = [elf, base / "build.json", base / "commands.json", script, compiler, *objects]
    for path in frozen:
        if pins.get(str(path)) != digest(path):
            raise ValueError(f"Original artifact absent/changed in frozen manifest: {path}")
    return dict(elf=elf, objects=objects, script=script, compiler=compiler,
                compile=compile_command, compiles=compiles, link=link,
                frozen=[*frozen, anchor / "build.json", anchor_manifest])


def replace_link(link, replacements, output):
    result = [str(replacements.get(arg, arg)) for arg in link]
    result[result.index("-o") + 1] = str(output / APP)
    return ["-Wl,-Map=" + str(output / "link.map") if arg.startswith("-Wl,-Map=")
            else arg for arg in result]


def disassembly_sections(text):
    sections = {}
    current = None
    for line in text.splitlines():
        match = re.fullmatch(r"Disassembly of section (.+):", line)
        if match:
            current = match[1]
            if current in sections:
                raise ValueError("Duplicate objdump section")
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.rstrip())
    if not sections:
        raise ValueError("No object disassembly sections")
    return {name: "\n".join(lines) for name, lines in sections.items()}


def section_changes(old, new):
    changed = sorted(k for k in old.keys() | new.keys() if old.get(k) != new.get(k))
    return dict(changed_sections=changed,
                non_pack_sections=[k for k in changed if not PACK_SECTION.match(k)])


def stop(signum, _frame):
    raise InterruptedError(f"Signal {signum}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline-build", type=Path, default=DEFAULT_BASE)
    p.add_argument("--anchor-build", type=Path, default=DEFAULT_ANCHOR)
    p.add_argument("--native-gate", type=Path, default=DEFAULT_GATE)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    gate = require_gate(args.native_gate)
    plan = frozen_plan(args.baseline_build.resolve(strict=True), args.anchor_build.resolve(strict=True))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    state = dict(state="preparing", scope="one real M4/N896/K896 DIRECT projection")
    commands = []

    def run(argv, label):
        argv = list(map(str, argv))
        commands.append(dict(argv=argv, cwd=str(ROOT), log=label + ".log"))
        atomic_json(out / "commands.json", commands)
        rc = run_command(argv, out / (label + ".log"), 120, os.environ.copy(), lambda pid: None)
        if rc:
            raise RuntimeError(f"Command returned {rc}: {label}")
        return (out / (label + ".log")).read_text()

    try:
        cc = plan["compiler"]
        flags = plan["compile"][1:plan["compile"].index("-c")]
        sources = [Path(c[c.index("-c") + 1]) for c in plan["compiles"]]
        # These current source pins are not retrospective proof of the old objects.
        current = [*sources, *runtime_headers(), Path(sys.executable).resolve(),
                   *ROOT.glob("apps/common/*.h"), *ROOT.glob("apps/include/**/*.h"),
                   *(ROOT / "apps" / APP).glob("generated/*.h"),
                   *[HERE / name for name in ("build_runtime_pack_projection.py",
                     "run_runtime_pack_projection.py", "test_runtime_pack_projection.py",
                     "run_runtime_activation_pack.py",
                     "run_half_scale_soc.py", "audit_projection_soc_pair.py")]]
        for source in sources:
            if source.suffix == ".S":
                for line in source.read_text().splitlines():
                    if line.strip().startswith(".incbin"):
                        fields = shlex.split(line)
                        if len(fields) != 2 or fields[0] != ".incbin":
                            raise ValueError("Unsupported embedded-data directive")
                        current.append(Path(fields[1]))
        pins = {**gate, **hashes([*plan["frozen"], *current])}
        verify_pins(gate)
        tools = {}
        for name in ("cc1", "as", "ld", "collect2"):
            value = run([cc, *flags, "-print-prog-name=" + name], "tool-" + name).strip()
            tool = Path(value) if "/" in value else Path(shutil.which(value) or value)
            tools[name] = tool.absolute()
            tools[name].resolve(strict=True)
        tools["objdump"] = cc.with_name(cc.name.removesuffix("gcc") + "objdump")
        tools["objdump"].resolve(strict=True)
        libraries = []
        for name in ("libm.a", "libgcc.a"):
            value = run([cc, *flags, "-print-file-name=" + name], "library-" + name).strip()
            library = Path(value).absolute()
            library.resolve(strict=True)
            libraries.append(library)
        verify_pins(pins)
        pins.update(hashes([*tools.values(), *libraries]))
        deps = out / "runtime.d"
        run([cc, *flags, "-M", "-MT", "runtime", "-MF", deps, RUNTIME], "dependencies")
        deptext = deps.read_text().replace("\\\n", " ")
        target, dependencies = deptext.split(":", 1)
        if target.strip() != "runtime":
            raise ValueError("Unexpected compiler dependency target")
        dependency_paths = [Path(x).resolve(strict=True) for x in shlex.split(dependencies)]
        verify_pins(pins)
        pins.update(hashes(dependency_paths))
        atomic_json(out / "manifest.json", pins)
        baseline = out / "baseline"
        baseline.mkdir()
        shutil.copyfile(plan["elf"], baseline / APP)
        if digest(baseline / APP) != BASELINE_SHA256:
            raise ValueError("Baseline ELF copy differs")
        sections = {}
        old_disasm = run([tools["objdump"], "-Dr", plan["objects"][8]], "baseline-runtime")
        sections["baseline"] = disassembly_sections(old_disasm)
        modes = {}
        for mode in ("scalar", "vector"):
            verify_pins(pins)
            target = out / mode
            target.mkdir()
            replacements = {}
            for original in [*plan["objects"], plan["script"]]:
                destination = target / original.name
                replacements[str(original)] = str(destination)
                if original == plan["objects"][8]:
                    continue
                shutil.copyfile(original, destination)
                if digest(destination) != pins[str(original)]:
                    raise ValueError("Frozen object/linker script copy differs")
            obj = target / OBJECT_NAMES[8]
            defines = ["-DQBS_PACK_FORCE_SCALAR=1"] if mode == "scalar" else []
            compile_cmd = [cc, *flags, *defines, "-c", RUNTIME, "-o", obj]
            run(compile_cmd, mode + "-compile")
            run(replace_link(plan["link"], replacements, target), mode + "-link")
            disasm = run([tools["objdump"], "-Dr", obj], mode + "-runtime")
            sections[mode] = disassembly_sections(disasm)
            pack = "\n".join(value for key, value in sections[mode].items() if PACK_SECTION.match(key))
            if not pack or (("vsse8.v" in pack and "vsse16.v" in pack) != (mode == "vector")):
                raise ValueError("Targeted runtime pack RVV/scalar code mismatch")
            if mode == "scalar" and re.search(r"\bv(?:sse|lse|le|se)\d+\.v\b", pack):
                raise ValueError("Forced scalar pack contains vector memory instructions")
            modes[mode] = dict(elf_sha256=digest(target / APP), runtime_sha256=digest(obj),
                              defines=defines, versus_baseline=section_changes(sections["baseline"], sections[mode]))
        twin_diff = section_changes(sections["scalar"], sections["vector"])
        # Disassembly includes relocations and data sections. Differences outside
        # pack are surfaced, not silently credited as pack-only improvements.
        diff = "\n".join(difflib.unified_diff(old_disasm.splitlines(),
                            (out / "scalar-runtime.log").read_text().splitlines(),
                            fromfile="original-runtime", tofile="current-scalar-runtime"))
        (out / "runtime-object.diff").write_text(diff + "\n")
        verify_pins(pins)
        artifacts = hashes(path for path in out.rglob("*") if path.is_file()
                           and path.name not in ("build.json", "artifacts.json"))
        atomic_json(out / "artifacts.json", artifacts)
        state.update(state="BUILT_NOT_EXECUTED", app=APP, baseline_sha256=BASELINE_SHA256,
            native_gate=str(args.native_gate.resolve()), modes=modes, scalar_vector_sections=twin_diff,
            manifest_sha256=digest(out / "manifest.json"), artifacts_sha256=digest(out / "artifacts.json"),
            source_provenance="Old runtime source/dependency/library hashes absent from baseline build. "
                "Current source pins do not authenticate old object sources; inspect runtime-object.diff. "
                "Disassembly section differences are conservative (including local-label/relocation renumbering).",
            deployment_approved=False)
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        raise
    finally:
        atomic_json(out / "build.json", state)
    print(json.dumps(state, sort_keys=True))


if __name__ == "__main__":
    main()
