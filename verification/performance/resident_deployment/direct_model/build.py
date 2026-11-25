#!/usr/bin/env python3
"""Freeze and cross-build a full llama-simple Direct-U candidate, never run it."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ARA = HERE.parents[3]
OUT = ARA.parent / "ara_dsa_signoff_integration/verification/out"
LLAMA = Path("/home/wangwy/llama/llama.cpp")
ARA_HEAD = "4a7361f51ba5447a616217dad1c8e72e3ee2b45b"
LLAMA_HEAD = "a2b7f30da9aadf88b0a068c447383ed2e26ee867"
TOOL_BIN = Path("/home/wangwy/llama/platforms/cva6-qemu/tools/bin")
DELIVERY = OUT / "resident_direct_delivery_compact_20261113_02"
KERNEL_SHA256 = "d52d67d62a6d97c61684ede19f406dd72e805c8b606538c916190cab2aea50d1"
DELIVERY_FILES = (
    "manifest.json", "kernel/Image", "kernel/result.json",
    "rtl/baseline-current-hashes.json", "rtl/cva6-baseline-prerequisite.patch",
    "rtl/cva6-akv-direct-gate.patch", "rtl/focused-validation.json",
)
FORBIDDEN = "software/akv/src/akv_v2_attention_rvv.S"
RISCV = "ggml/src/ggml-cpu/arch/riscv/"

# Same eleven reviewed SDK overlays as direct_cost/build_compact.py.
SDK_OVERLAYS = tuple("software/akv/" + path for path in (
    "src/akv_v2_native_riscv.c", "include/akv/akv.h",
    "experimental/resident_attention/pv_compact.h",
    "experimental/resident_attention/pv_compact.S",
    "experimental/resident_attention/pv.S",
    "experimental/resident_attention/pv.h",
    "experimental/resident_attention/pv_fast.inc",
    "experimental/resident_attention/qk.S",
    "experimental/resident_attention/qk.h",
    "experimental/resident_attention/admission.h",
    "experimental/resident_attention/dispatch.h",
))
DIRECT_OVERLAYS = tuple("software/llama/platform/linux/direct/" + name for name in (
    "direct_client.c", "direct_client.h", "direct_uapi.h",
))
LLAMA_OVERLAYS = (
    "ggml/src/ggml-cpu/CMakeLists.txt", RISCV + "akv.cpp", RISCV + "resident.inc",
    RISCV + "linux-direct.cpp", RISCV + "linux-direct.h", "examples/simple/simple.cpp",
)
RECIPE_FILES = ("build.py", "toolchain-rvv.cmake", "run_board.sh", "README.md", "test_build.py")
REQUIRED_SYMBOLS = (
    "llama_decode", "qbs_native_execute_command", "akv_native_info",
    "akv_attention_execute_v2_native", "akv_experimental_attention_execute_v2_native",
    "akv_experimental_resident_qk_prepared", "akv_experimental_resident_pv_compact",
    "ara_akv_direct_open", "ara_akv_direct_acquire", "ara_akv_direct_release", "ara_akv_direct_close",
    "ggml_akv_direct::prepare(", "ggml_akv_direct::begin(",
    "ggml_akv_direct::end(", "ggml_akv_direct::provider(",
    "ggml_akv_direct::invalidate(", "ggml_akv_direct::stats(", "ggml_akv_direct::last_error(",
)
BOOL_OPTIONS = {
    "BUILD_SHARED_LIBS": False, "GGML_STATIC": True, "GGML_NATIVE": False,
    "GGML_BACKEND_DL": False, "GGML_OPENMP": False, "GGML_LTO": False,
    "GGML_CCACHE": False,
    "GGML_LLAMAFILE": False, "GGML_CPU_REPACK": True,
    "GGML_RVV": True, "GGML_RV_ZFH": True, "GGML_RV_ZVFH": True,
    "GGML_RV_ZVFBFWMA": False, "GGML_RV_ZICBOP": False,
    "GGML_RV_ZIHINTPAUSE": False, "GGML_RV_ZBA": False,
    "GGML_CPU_ALL_VARIANTS": False, "GGML_CPU_RISCV64_SPACEMIT": False,
    "GGML_RISCV_QBS": True, "GGML_RISCV_QBS_M4_PREFLIGHT": True,
    "GGML_RISCV_AKV": True, "GGML_RISCV_ACCEL_AUTO": True,
    "GGML_RISCV_AKV_QUANT_KV": True, "GGML_RISCV_AKV_QUANT_PREFILL": True,
    "GGML_RISCV_AKV_REGISTER_PV": True, "GGML_RISCV_AKV_RESIDENT": True,
    "GGML_RISCV_AKV_LINUX_DIRECT": True, "GGML_RISCV_AKV_LINUX_PORTAL": False,
    "GGML_RISCV_AKV_COMPACT_COEFFICIENTS": True,
    "LLAMA_BUILD_COMMON": True, "LLAMA_BUILD_EXAMPLES": True,
    "LLAMA_BUILD_TESTS": False, "LLAMA_BUILD_TOOLS": False,
    "LLAMA_BUILD_SERVER": False, "LLAMA_BUILD_APP": False,
    "LLAMA_OPENSSL": False,
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def validate_output(path, root=OUT):
    path = Path(path).absolute()
    if (path.is_symlink() or path.parent.resolve() != root.resolve() or
            not re.fullmatch(r"resident_direct_model_[A-Za-z0-9_.-]+", path.name)):
        raise ValueError("use a fresh signoff_integration/verification/out/resident_direct_model_* directory")
    if path.exists():
        raise ValueError("output already exists; never overwrite or resume")
    return path.parent.resolve() / path.name


def clean_environment(out, cmake, epoch):
    for name in ("CPATH", "C_INCLUDE_PATH", "CPLUS_INCLUDE_PATH", "LIBRARY_PATH",
                 "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "GCC_EXEC_PREFIX",
                 "COMPILER_PATH", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS"):
        if os.environ.get(name):
            raise ValueError("compiler environment injection: " + name)
    return {
        "PATH": str(TOOL_BIN) + ":" + str(cmake.parent) + ":/usr/bin:/bin",
        "HOME": str(out / "home"), "LC_ALL": "C", "TZ": "UTC",
        "SOURCE_DATE_EPOCH": str(epoch), "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
        # An extracted archive must not inherit the signoff worktree's Git identity.
        "GIT_CEILING_DIRECTORIES": str(out / "inputs"),
    }


class Commands:
    def __init__(self, out, env):
        self.out, self.env, self.records = out, env, []

    def run(self, name, argv, cwd=None, timeout=1800):
        argv = list(map(str, argv))
        record = dict(name=name, argv=argv, cwd=str(cwd or self.out), returncode=None)
        self.records.append(record)
        log = self.out / (name + ".log")
        with log.open("xb") as stream:
            try:
                with subprocess.Popen(argv, cwd=record["cwd"], env=self.env, start_new_session=True,
                                      stdout=stream, stderr=subprocess.STDOUT) as process:
                    try:
                        record["returncode"] = process.wait(timeout=timeout)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()
                        raise
            except subprocess.TimeoutExpired:
                record["timeout_seconds"] = timeout
                raise RuntimeError(name + " timed out; original log retained") from None
        if record["returncode"]:
            raise RuntimeError(name + " failed; inspect " + str(log))
        return log


def extract_archive(archive, destination):
    destination.mkdir()
    with tarfile.open(archive) as source:
        # Source links may point at local trees or escape the frozen input root.
        # Fail closed rather than silently consume their live targets.
        members = source.getmembers()
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError("unsupported archive entry: " + member.name)
        source.extractall(destination, members=members)


def copy_overlay(source_root, target_root, relative, pins):
    path = PurePosixPath(relative)
    if relative == FORBIDDEN or path.is_absolute() or ".." in path.parts:
        raise ValueError("forbidden overlay: " + relative)
    source, target = source_root / relative, target_root / relative
    if source.is_symlink() or source.resolve() != source.absolute() or not source.is_file():
        raise ValueError("overlay must be a regular, non-symlink file: " + str(source))
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    pins[str(source)] = digest
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    target.chmod(source.stat().st_mode & 0o777)
    return dict(path=relative, sha256=digest)


def check_pins(pins):
    for path, expected in pins.items():
        if not Path(path).is_file() or Path(path).is_symlink() or sha(path) != expected:
            raise ValueError("input drift: " + path)


def freeze_repo(run, name, repo, commit, paths, overlays, inputs, pins):
    archive = inputs / (name + ".tar")
    run.run(name + "-archive", ["git", "-C", repo, "archive", "--format=tar",
                              "--output=" + str(archive), commit, *paths])
    destination = inputs / name
    extract_archive(archive, destination)
    base_assembly = sha(destination / FORBIDDEN) if name == "sdk" else None
    applied = [copy_overlay(repo, destination, path, pins) for path in overlays]
    if base_assembly is not None and sha(destination / FORBIDDEN) != base_assembly:
        raise ValueError("archived native assembly changed")
    return dict(commit=commit, archive_sha256=sha(archive), overlays=applied,
                archive_native_assembly_sha256=base_assembly)


def candidate_contract(inputs, pins, sdk, llama, delivery=DELIVERY):
    evidence = inputs / "deployment-evidence"
    for name in DELIVERY_FILES:
        copy_overlay(delivery, evidence, name, pins)
    manifest = json.loads((evidence / "manifest.json").read_text())
    kernel = json.loads((evidence / "kernel/result.json").read_text())
    image_sha = sha(evidence / "kernel/Image")
    if (image_sha != KERNEL_SHA256 or manifest.get("kernel_sha256") != image_sha or
            kernel.get("image_sha256") != image_sha or
            kernel.get("status") != "COMPILED_TEST_CANDIDATE_RUNTIME_PENDING"):
        raise ValueError("not the selected v4 test kernel Image")
    gate = json.loads((evidence / "rtl/baseline-current-hashes.json").read_text())
    expected_files = {"core/csr_regfile.sv", "core/decoder.sv", "core/cva6.sv", "core/id_stage.sv"}
    if set(gate["current"]) != expected_files or set(gate["baseline"]) != expected_files:
        raise ValueError("unexpected four-file gate inventory")
    for name, artifact in gate["artifacts"].items():
        if PurePosixPath(name).name != name or sha(evidence / "rtl" / name) != artifact["sha256"]:
            raise ValueError("gate evidence drift: " + name)
    return {
        "schema": 1, "purpose": "controlled-board-test candidate only",
        "hardware_accepted": False, "board_pending": True, "performance_measured": False,
        "provenance_attests_running_board": False,
        "ara": sdk, "llama": llama,
        "kernel": {"revision": "Direct-U v4", "image_sha256": image_sha},
        "gate": gate,
        "requirements": {
            "runtime_workers": 1, "online_cpus": "0", "root_only": True,
            "static_rv64_linux": True, "isa": "rv64gcv_zfh_zvfh",
            "no_mmio": True, "normal_ram_only": True, "immutable_file_mappings": True,
            "exclusive_accelerator_owner": True, "manual_kernel_and_gate_install": True,
            "normal_memory_quant_kv_authority_granted": False,
            "llama_simple_use_mlock": False,
            "memory_lock_owner": "linux-direct helper; launcher only raises RLIMIT_MEMLOCK",
            "maps_cache_is_not_lock_state_attestation": True,
            "no_memory_policy_or_foreign_mapping_changes_during_lease": True,
            "invalidate_before_external_out_of_lease_changes": [
                "munlock", "mlock policy", "madvise", "userfault", "foreign mapping updates"],
            "clock_hz": "operator must identify actual configured clock; no inferred 50 MHz",
            "hart": 0,
        },
        "input_sha256": {path.relative_to(inputs).as_posix(): sha(path)
                         for path in sorted(inputs.rglob("*")) if path.is_file()},
    }


def cmake_arguments(out, cmake, contract_sha256):
    if not re.fullmatch(r"[0-9a-f]{64}", contract_sha256):
        raise ValueError("contract SHA256 must be 64 lowercase hex digits")
    inputs, build = out / "inputs", out / "build"
    sdk = inputs / "sdk/software"
    flags = ("-fno-fast-math -ffp-contract=off -fno-lto "
             "-ffile-prefix-map=" + str(out) + "=/direct-model "
             "-fdebug-prefix-map=" + str(out) + "=/direct-model")
    values = {
        "CMAKE_BUILD_TYPE": "Release", "CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
        "CMAKE_TOOLCHAIN_FILE": str(inputs / "recipe/toolchain-rvv.cmake"),
        "CMAKE_C_FLAGS": "-march=rv64gcv_zfh_zvfh -mabi=lp64d " + flags,
        "CMAKE_CXX_FLAGS": "-march=rv64gcv_zfh_zvfh -mabi=lp64d " + flags,
        "CMAKE_ASM_FLAGS": "-march=rv64gcv_zfh_zvfh -mabi=lp64d",
        "CMAKE_EXE_LINKER_FLAGS": "-static -Wl,-Map=" + str(out / "link.map"),
        "GGML_RISCV_AKV_PROVIDER_SOURCE": "",
        "GGML_RISCV_AKV_DIRECT_CONTRACT_SHA256": contract_sha256,
        "GGML_RISCV_QBS_RUNTIME_DIR": str(sdk / "qbs"),
        "GGML_RISCV_AKV_RUNTIME_DIR": str(sdk / "akv"),
        "GGML_RISCV_AKV_LINUX_DIRECT_DIR": str(sdk / "llama/platform/linux/direct"),
        "LLAMA_BUILD_COMMIT": LLAMA_HEAD + "-direct-u-overlay", "LLAMA_BUILD_NUMBER": "0",
    }
    values.update({key: "ON" if enabled else "OFF" for key, enabled in BOOL_OPTIONS.items()})
    return [str(cmake), "-S", str(inputs / "llama"), "-B", str(build), "-G", "Unix Makefiles",
            *["-D" + key + "=" + value for key, value in sorted(values.items())]]


def read_cmake_cache(path):
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith(("#", "//")) and "=" in line and ":" in line:
            key, value = line.split("=", 1)
            values[key.split(":", 1)[0]] = value
    return values


def reviewed_compilers(pins):
    compilers = {name: (TOOL_BIN / ("riscv64-linux-" + name)).resolve(strict=True)
                 for name in ("gcc", "g++")}
    for compiler in set(compilers.values()):
        digest = pins.get(str(compiler))
        if not digest or not compiler.is_file() or sha(compiler) != digest:
            raise ValueError("missing or changed compiler hash pin: " + str(compiler))
    return compilers


def audit_compiler_path(value, allowed):
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=True) not in allowed:
        raise ValueError("not a reviewed GNU compiler: " + value)


def compiler_scalar(text, key, required=True):
    # Read only literal scalars from CMake's generated compiler metadata. Never
    # execute this file, and reject ambiguous or interpolated compiler settings.
    declarations = re.findall(r"(?m)^set\(" + re.escape(key) + r"(?:\s|\))[^\n]*", text)
    if not declarations and not required:
        return ""
    if len(declarations) == 1:
        match = re.fullmatch(r'set\(' + re.escape(key) + r' "([^"\\$;\r\n]*)"\)', declarations[0])
        if match:
            return match.group(1)
    raise ValueError("missing or ambiguous compiler metadata: " + key)


def audit_compilers(path, values, pins):
    version = [values.get("CMAKE_CACHE_" + part + "_VERSION", "") for part in ("MAJOR", "MINOR", "PATCH")]
    if any(not re.fullmatch(r"[0-9]+", part) for part in version):
        raise ValueError("missing CMake cache version for compiler metadata")
    metadata = path.parent / "CMakeFiles" / ".".join(version)
    compilers = reviewed_compilers(pins)
    for language, compiler in (("C", "gcc"), ("CXX", "g++"), ("ASM", "gcc")):
        key = "CMAKE_" + language + "_COMPILER"
        text = (metadata / ("CMake" + language + "Compiler.cmake")).read_text()
        if compiler_scalar(text, key + "_ID") != "GNU":
            raise ValueError("not the reviewed GNU " + language + " compiler ID")
        for suffix in ("_ARG1", "_WRAPPER", "_LAUNCHER"):
            if values.get(key + suffix) or compiler_scalar(text, key + suffix, required=False):
                raise ValueError("unreviewed compiler wrapper/arguments: " + key + suffix)
        allowed = {compilers[compiler]}
        audit_compiler_path(compiler_scalar(text, key), allowed)
        # Toolchain set() variables need not appear in CMakeCache.txt. When a
        # cache entry exists it must agree with the generated compiler identity.
        if key in values:
            audit_compiler_path(values[key], allowed)


def audit_cache(path, pins):
    values = read_cmake_cache(path)
    for key, enabled in BOOL_OPTIONS.items():
        if values.get(key) != ("ON" if enabled else "OFF"):
            raise ValueError("CMake option mismatch: " + key)
    audit_compilers(path, values, pins)


def audit_compile_commands(path, inputs, contract_sha256, pins):
    records = json.loads(path.read_text())
    compilers = set(reviewed_compilers(pins).values())
    seen, compact, contract = set(), False, False
    for entry in records:
        source = Path(entry["file"]).resolve()
        generated = inputs.parent / "build/common/build-info.cpp"
        if not source.is_relative_to(inputs.resolve()) and source != generated:
            raise ValueError("source outside frozen inputs: " + str(source))
        if source == generated:
            if str(source) not in pins:
                raise ValueError("missing generated build-info source pin")
            check_pins({str(source): pins[str(source)]})
        argv = entry.get("arguments") or shlex.split(entry["command"])
        if "zcc" in " ".join(argv).lower() or any("-march=native" in arg for arg in argv):
            raise ValueError("unreviewed compiler/ISA in compile database")
        if not argv:
            raise ValueError("empty compiler command")
        audit_compiler_path(argv[0], compilers)
        seen.add(source.name)
        if source.name == "linux-direct.cpp":
            contract = ('-DGGML_AKV_DIRECT_CONTRACT_SHA256="' + contract_sha256 + '"') in argv
        if source.name == "akv.cpp":
            compact = "-DAKV_RESIDENT_COMPACT_COEFFICIENTS=1" in argv
            for definition in ("GGML_USE_RISCV_AKV_LINUX_DIRECT", "GGML_AKV_RESIDENT=1"):
                if "-D" + definition not in argv and "-D" + definition + "=1" not in argv:
                    raise ValueError("missing Direct-U definition: " + definition)
    needed = {"linux-direct.cpp", "direct_client.c", "pv_compact.S", "qk.S", "akv_v2_attention_rvv.S"}
    if not needed <= seen or not compact or not contract:
        raise ValueError("Direct-U/compact sources or definitions missing")


def audit_symbols(nm):
    defined = []
    for line in nm.splitlines():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[1] in ("T", "t", "W", "w"):
            defined.append(fields[2])
    missing = [symbol for symbol in REQUIRED_SYMBOLS if not any(
        name.startswith(symbol) if symbol.endswith("(") else name == symbol for name in defined)]
    if missing:
        raise ValueError("required executable symbols missing: " + ", ".join(missing))
    return list(REQUIRED_SYMBOLS)


def audit_elf(headers):
    if not re.search(r"Class:\s+ELF64", headers) or not re.search(r"Machine:\s+RISC-V", headers):
        raise ValueError("not an ELF64 RISC-V executable")
    if not re.search(r"Type:\s+EXEC", headers) or re.search(r"\b(INTERP|NEEDED)\b", headers):
        raise ValueError("ELF is not a static executable")


def pack_tree(root, archive, epoch):
    with tarfile.open(archive, "w", format=tarfile.PAX_FORMAT) as target:
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError("package symlink: " + str(path))
            info = target.gettarinfo(str(path), arcname=path.relative_to(root).as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = epoch
            if path.is_file():
                with path.open("rb") as stream:
                    target.addfile(info, stream)
            else:
                target.addfile(info)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--llama-root", type=Path, default=LLAMA)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--sources-stable", action="store_true",
                        help="parent has approved freezing after helper/integration tests")
    parser.add_argument("--stability-note", default="",
                        help="parent approval and passing helper/integration evidence references")
    args = parser.parse_args(argv)
    if not args.sources_stable or not args.stability_note.strip():
        parser.error("no freeze/build before parent approval; require --sources-stable and --stability-note")
    if args.jobs < 1 or args.jobs > 64:
        parser.error("--jobs must be 1..64 (build parallelism, not runtime workers)")
    try:
        out = validate_output(args.output)
        cmake = Path(shutil.which("cmake") or "/nonexistent/cmake").resolve(strict=True)
        env = clean_environment(out, cmake, 0)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    out.mkdir()
    (out / "home").mkdir()
    inputs, board = out / "inputs", out / "board"
    inputs.mkdir()
    board.mkdir()
    run, pins = Commands(out, env), {}
    report = dict(state="FAIL", scope="full llama-simple userspace candidate; build only",
                  board_executed=False, rtl_executed=False, model_executed=False,
                  hardware_accepted=False, performance_measured=False, pending_board=True,
                  stability_note=args.stability_note, runtime_workers=1)
    try:
        for name, repo, expected in (("ara", ARA, ARA_HEAD), ("llama", args.llama_root.resolve(), LLAMA_HEAD)):
            actual = run.run(name + "-head", ["git", "-C", repo, "rev-parse", "HEAD"]).read_text().strip()
            if actual != expected:
                raise ValueError(name + " HEAD drift: " + actual)
            run.run(name + "-dirty-tracked", ["git", "-C", repo, "diff", "--name-status", "HEAD"])
        epoch = int(run.run("source-epoch", ["git", "-C", args.llama_root, "show", "-s", "--format=%ct", LLAMA_HEAD]).read_text())
        env["SOURCE_DATE_EPOCH"] = str(epoch)
        save(out / "environment.json", env)
        for name in RECIPE_FILES:
            copy_overlay(HERE, inputs / "recipe", name, pins)
        tools = [cmake, Path("/usr/bin/make"), Path("/usr/bin/git")]
        tools += [TOOL_BIN / ("riscv64-linux-" + name) for name in ("gcc", "g++", "as", "ld", "ar", "ranlib", "nm", "objdump", "readelf")]
        for index, tool in enumerate(tools):
            pins[str(tool.resolve(strict=True))] = sha(tool)
            run.run("tool-" + str(index), [tool, "--version"])
        cc, cxx = TOOL_BIN / "riscv64-linux-gcc", TOOL_BIN / "riscv64-linux-g++"
        for name, compiler, option in (
            ("cc1", cc, "-print-prog-name=cc1"), ("cc1plus", cxx, "-print-prog-name=cc1plus"),
            *((name, cxx, "-print-file-name=" + name) for name in (
                "libstdc++.a", "libgcc.a", "libgcc_eh.a", "libc.a", "libm.a",
                "libpthread.a", "crt1.o", "crti.o", "crtn.o", "crtbeginT.o", "crtend.o")),
        ):
            path = Path(run.run("tool-input-" + name, [compiler, option]).read_text().strip())
            if not path.is_absolute() or not path.is_file():
                raise ValueError("missing toolchain input: " + name)
            pins[str(path.resolve())] = sha(path)
        sdk = freeze_repo(run, "sdk", ARA, ARA_HEAD,
                          ("software/qbs", "software/akv", "software/llama"),
                          SDK_OVERLAYS + DIRECT_OVERLAYS, inputs, pins)
        llama = freeze_repo(run, "llama", args.llama_root.resolve(), LLAMA_HEAD, (),
                            LLAMA_OVERLAYS, inputs, pins)
        save(out / "freeze.json", dict(ara=sdk, llama=llama, forbidden_live_overlay=FORBIDDEN))
        contract = candidate_contract(inputs, pins, sdk, llama)
        contract_dir = out / "pins"
        contract_dir.mkdir()
        save(contract_dir / "candidate-contract.json", contract)
        contract_sha = sha(contract_dir / "candidate-contract.json")
        pins[str(contract_dir / "candidate-contract.json")] = contract_sha
        report["contract_sha256"] = contract_sha
        for path in sorted(inputs.rglob("*")):
            if path.is_file():
                pins[str(path)] = sha(path)
        check_pins(pins)
        save(out / "source-pins.json", pins)
        pack_tree(inputs, out / "source-inputs.tar", epoch)
        run.run("shell-check", ["sh", "-n", inputs / "recipe/run_board.sh"])
        configure = run.run("configure", cmake_arguments(out, cmake, contract_sha))
        if "Manually-specified variables were not used" in configure.read_text():
            raise ValueError("unused CMake options; inspect configure.log")
        generated = out / "build/common/build-info.cpp"
        generated_pins = {str(generated): sha(generated)} if generated.is_file() else {}
        save(out / "generated-source-pins.json", generated_pins)
        audit_cache(out / "build/CMakeCache.txt", pins)
        audit_compile_commands(out / "build/compile_commands.json", inputs, contract_sha,
                               {**pins, **generated_pins})
        run.run("build", [cmake, "--build", out / "build", "--target", "llama-simple",
                          "--parallel", str(args.jobs), "--verbose"], timeout=7200)
        elf = board / "llama-simple"
        shutil.copyfile(out / "build/bin/llama-simple", elf)
        elf.chmod(0o755)
        headers = run.run("elf-headers", [TOOL_BIN / "riscv64-linux-readelf", "-hlAdW", elf])
        nm = run.run("nm", [TOOL_BIN / "riscv64-linux-nm", "-C", "--defined-only", elf])
        run.run("disassembly", [TOOL_BIN / "riscv64-linux-objdump", "-d", "-C", "-M", "no-aliases", elf])
        audit_elf(headers.read_text())
        symbols = audit_symbols(nm.read_text())
        if not (out / "link.map").stat().st_size:
            raise ValueError("empty link map")
        check_pins(pins)
        check_pins(generated_pins)
        save(out / "symbol-audit.json", dict(required=symbols, elf_sha256=sha(elf)))
        for name in ("run_board.sh", "README.md"):
            shutil.copyfile(inputs / "recipe" / name, board / name)
        (board / "run_board.sh").chmod(0o755)
        for name in ("freeze.json", "source-pins.json", "symbol-audit.json"):
            shutil.copyfile(out / name, board / name)
        shutil.copyfile(contract_dir / "candidate-contract.json", board / "candidate-contract.json")
        (board / "candidate-contract.sha256").write_text(contract_sha + "\n")
        (board / "kernel-image.sha256").write_text(KERNEL_SHA256 + "\n")
        report.update(state="USERSPACE_BUILT_NOT_EXECUTED", elf_sha256=sha(elf),
                      post_pins_match=True, source_inputs_sha256=sha(out / "source-inputs.tar"),
                      required_kernel="manually installed Direct-U v4", required_gate="matching new RTL gate",
                      gate_signature="0x414b5601", existing_bitstream_compatible=False)
        save(board / "candidate.json", report)
        (board / "SHA256SUMS").write_text("".join(
            sha(path) + "  " + path.name + "\n" for path in sorted(board.iterdir()) if path.is_file()))
        pack_tree(board, out / "board.tar", epoch)
        report["board_tar_sha256"] = sha(out / "board.tar")
    except Exception as exc:
        report.update(state="FAIL", error=str(exc))
    save(out / "commands.json", run.records)
    save(out / "result.json", report)
    artifacts = [path for path in out.iterdir() if path.is_file()]
    artifacts += [path for path in (out / "build/CMakeCache.txt", out / "build/compile_commands.json") if path.is_file()]
    save(out / "artifact-hashes.json", {str(path.relative_to(out)): sha(path) for path in sorted(artifacts)})
    print(json.dumps(report, indent=2))
    return 0 if report["state"] == "USERSPACE_BUILT_NOT_EXECUTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
