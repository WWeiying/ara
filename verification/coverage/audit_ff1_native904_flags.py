#!/usr/bin/env python3
"""Bind effective historical VCS arguments and source-manifest override audit, offline only."""
import argparse
import json
from pathlib import Path
import re
import shlex
import sys

sys.dont_write_bytecode = True
import prepare_ff1_native904 as prep
import old_image_source_snapshot as snapshot

require, sha = prep.require, prep.sha
BASE = prep.BUILD.parent
STATIC = prep.OUT / "ff1-native904-static-prepare-20261006-01/config.json"
STATIC_SHA = "be2e3cd40d8d994ef44ca6d2505d6988a0131db15e2ac25319ed39fcf9439447"
DEFINES = set("ARA_AKV_ENABLE=1 ARA_AKV_V2_ENABLE=1 ARA_QBS_ENABLE=1 ARIANE_ACCELERATOR_PORT=1 COMMON_CELLS_ASSERTS_OFF FOR_VERIFY NR_LANES=4 SIM_L2_SIZE_BYTES=2097152 TARGET_ARA_TEST TARGET_CV64A6_IMAFDCV_SV39 TARGET_CVA6_TEST TARGET_EXCLUDE_FIRST_PASS_DECODER TARGET_NOTSYNTHESIS TARGET_RTL TARGET_TECH_CELLS_GENERIC_INCLUDE_TC_CLK TARGET_TECH_CELLS_GENERIC_INCLUDE_TC_SRAM TARGET_VERILATOR VLEN=1024 SIMULATION no_warning TSMC_NO_WARNING ARA_VERIFY_UVM_CVXIF ARA_VERIFY_AXI_DELAY ARA_NO_FSDB".split())
SWITCHES = set("-full64 -sverilog +v2k -Mupdate -j64 -lca -kdb -debug_access+all +nospecify +notimingchecks +lint=TFIPC-L +vpi +lint=PCWM +error+30 -timescale=1ns/100fs".split())


def scrub(text):
    return re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                  lambda m: "\n" * m[0].count("\n") + " ", text, flags=re.S)


def check_source(text):
    clean = scrub(text)
    require(not re.search(r'\b(?:defparam|config|endconfig)\b', clean), "Source defparam/config override")
    require(not re.search(r'`(?:define|undef)\s+(?:FPUSupport|TARGET_GATESIM)\b', clean), "Source configuration macro override")


def rebuild_args(text):
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    require(len(lines) == 1, "Unexpected rebuild shell body")
    words = shlex.split(lines[0], posix=True)
    require(words[0] == "vcs" and words[-1] == "2>&1", "Unexpected rebuild launcher/redirection")
    words = words[1:-1]
    require(not any(re.search(r'[;$`\n\r<>|&]', w) for w in words), "Shell expansion/operator forbidden")
    return words


def expand(words, pin, stack=(), top=False):
    sources, lists, definitions, includes = [], [], [], []
    i = 0
    while i < len(words):
        word = words[i]
        i += 1
        if word in ("-f", "-F"):
            require(i < len(words), "Missing nested filelist")
            path = Path(words[i]); i += 1
            require(path.is_absolute() and str(path) == str(path.resolve()), "Ambiguous/aliased filelist path")
            require(str(path) not in stack, "Recursive filelist cycle")
            raw = pin(path)
            child = expand(shlex.split(raw.decode(), comments=True), pin, stack + (str(path),))
            lists.append(str(path)); lists.extend(child[1])
            sources.extend(child[0]); definitions.extend(child[2]); includes.extend(child[3])
        elif word.startswith("+define+"):
            values = word[len("+define+"):].split("+")
            require(all(v in DEFINES for v in values), "Unreviewed compile macro override")
            definitions.extend(values)
        elif word.startswith("+incdir+"):
            dirs = word[len("+incdir+"):].split("+")
            require(all(Path(d).is_absolute() and Path(d).is_dir() for d in dirs), "Invalid include directory")
            includes.extend(dirs)
        elif top and word in SWITCHES:
            pass
        elif top and word in ("-cm", "-cm_dir", "-ntb_opts", "-top", "-l"):
            require(i < len(words), "Missing VCS option value")
            expected = {"-cm": "line+cond+fsm+tgl+branch", "-cm_dir": str(BASE / "sim/simv.vdb"),
                        "-ntb_opts": "uvm-1.2", "-top": "ara_tb", "-l": "comp.vcs.log"}[word]
            require(words[i] == expected and words.count(word) == 1, "VCS option binding differs")
            i += 1
        elif top and word == "-Mlib=./incremental_db":
            pass
        elif word.startswith(("-", "+")):
            raise ValueError("Unreviewed VCS/filelist option: " + word)
        else:
            path = Path(word)
            require(path.is_absolute() and path.suffix in (".v", ".sv", ".o"), "Unreviewed compilation operand")
            sources.append(str(path))
    if top:
        require(all(words.count(w) == 1 for w in ("-top", "-ntb_opts", "-cm", "-cm_dir")), "Incomplete effective invocation")
    return sources, lists, definitions, includes


def audit():
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased flags evidence")
        raw = path.read_bytes()
        import hashlib
        value = hashlib.sha256(raw).hexdigest()
        require(expected is None or value == expected, "Flags evidence hash differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Conflicting evidence pin")
        pins[str(path)] = value
        return raw
    config = json.loads(pin(STATIC, STATIC_SHA))
    for path, expected in config["pins"].items():
        pin(path, expected)
    prep.tool.revalidate(config["tool_identity"])
    manifest_path = BASE / "sim/vcs_source_manifest.json"
    manifest = json.loads(pin(manifest_path))
    require(manifest["schema_version"] == 1 and manifest["repo_root"] == str(prep.ROOT), "Foreign source manifest")
    recovery = snapshot.validate(prep.ROOT, prep.OUT / "old-image-source-evidence-20261006-01")
    for path, expected in recovery["evidence_pins"].items():
        pin(path, expected)
    args = rebuild_args(pin(BASE / "sim/simv.daidir/vcs_rebuild").decode())
    sources, lists, defines, includes = expand(args, pin, top=True)
    require(lists and lists[0] == manifest["filelist"], "Effective manifest filelist differs")
    records = {r["path"]: r["sha256"] for r in manifest["files"]}
    require(len(records) == len(manifest["files"]) == 458, "Incomplete/duplicate source manifest")
    require(set(sources) <= set(records) and set(lists) <= set(records), "Unmanifested compile input")
    require(set(manifest["extra_sources"]) == set(sources) - set(expand(shlex.split(pin(Path(lists[0])).decode(), comments=True), pin)[0]),
            "Effective extra source membership differs")
    scanned, substitutions = [], []
    for original, expected in records.items():
        path = Path(original)
        if original in recovery["source_aliases"]:
            alias = recovery["source_aliases"][original]
            require(alias["sha256"] == expected, "Historical source manifest/snapshot conflict")
            path = Path(alias["snapshot"])
            substitutions.append(dict(original=original, snapshot=str(path), sha256=expected))
        raw = pin(path, expected)
        if Path(original).suffix in (".v", ".sv", ".vh", ".svh"):
            check_source(raw.decode())
            scanned.append(original)
    for path in (Path(__file__), Path(__file__).with_name("test_audit_ff1_native904_flags.py"), Path(snapshot.__file__)):
        pin(path)
    for path, expected in pins.items():
        require(sha(path) == expected, "Evidence changed during flags audit")
    return dict(status="FF1_NATIVE904_EFFECTIVE_FLAGS_SOURCE_OVERRIDE_AUDIT_VERIFIED_NO_DVE",
                static_config_sha256=STATIC_SHA, targets=904, protected=824, effective_top="ara_tb",
                effective_arguments=args, recursive_filelists=lists, defines=sorted(set(defines)),
                include_directories=sorted(set(includes)), manifest_files=len(records),
                source_override_scan=scanned, historical_source_substitutions=substitutions, pins=pins,
                source_defparam_or_config=False, effective_compile_flags_defparam_audit_complete=True,
                native_selectors_qualified=False, native_capture_started=False, application_approval=False,
                scope="Historical processor manifest and exact effective arguments; implicit vendor UVM library not inventoried")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == prep.OUT and not output.is_symlink(), "Unsafe flags output")
    if args.command == "prepare":
        require(not output.exists(), "Fresh flags output required")
        result = audit()
        output.mkdir()
        prep.write(output / "flags-audit.json", result)
        print(result["status"] + " seal=" + sha(output / "flags-audit.json"))
    else:
        require(sha(output / "flags-audit.json") == args.seal, "External flags seal differs")
        saved = json.loads((output / "flags-audit.json").read_bytes())
        for path, expected in saved["pins"].items():
            require(sha(path) == expected, "Flags pin differs")
        require(saved == audit(), "Flags audit regeneration differs")
        print("FF1_FLAGS_OFFLINE_REVERIFIED")
