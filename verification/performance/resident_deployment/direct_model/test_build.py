"""Host-only tests, optionally reading configured artifacts. Never cross-build."""

import ast
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

import build


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="direct-model-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root / "tools"
        self.compilers, self.pins = {}, {}
        for name in ("gcc", "g++"):
            compiler = self.put("real/" + name, "reviewed GNU fixture " + name)
            self.compilers[name] = compiler
            self.pins[str(compiler)] = build.sha(compiler)
            tools.mkdir(exist_ok=True)
            (tools / ("riscv64-linux-" + name)).symlink_to(compiler)
        patch = mock.patch.object(build, "TOOL_BIN", tools)
        patch.start()
        self.addCleanup(patch.stop)

    def put(self, name, content="fixture\n"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def cache_fixture(self, cached=True, canonical=False):
        lines = [key + ":BOOL=" + ("ON" if enabled else "OFF") for key, enabled in build.BOOL_OPTIONS.items()]
        lines += ["CMAKE_CACHE_" + part + "_VERSION:INTERNAL=" + value
                  for part, value in (("MAJOR", "3"), ("MINOR", "26"), ("PATCH", "5"))]
        for lang, name in (("C", "gcc"), ("CXX", "g++"), ("ASM", "gcc")):
            compiler = self.compilers[name] if canonical else build.TOOL_BIN / ("riscv64-linux-" + name)
            key = "CMAKE_" + lang + "_COMPILER"
            if cached:
                lines.append(key + ":FILEPATH=" + str(compiler))
            self.put("build/CMakeFiles/3.26.5/CMake" + lang + "Compiler.cmake",
                     'set(' + key + ' "' + str(compiler) + '")\nset(' + key + '_ID "GNU")\n' +
                     'set(' + key + '_ARG1 "")\n')
        return self.put("build/CMakeCache.txt", "\n".join(lines))

    def compile_fixture(self, canonical=False):
        inputs = self.root / "inputs"
        records = []
        for source in ("linux-direct.cpp", "direct_client.c", "pv_compact.S", "qk.S", "akv_v2_attention_rvv.S", "akv.cpp"):
            name = "g++" if source.endswith(".cpp") else "gcc"
            compiler = self.compilers[name] if canonical else build.TOOL_BIN / ("riscv64-linux-" + name)
            args = [str(compiler), "-c", str(inputs / source)]
            if source == "akv.cpp":
                args += ["-DAKV_RESIDENT_COMPACT_COEFFICIENTS=1", "-DGGML_USE_RISCV_AKV_LINUX_DIRECT", "-DGGML_AKV_RESIDENT=1"]
            if source == "linux-direct.cpp":
                args += ['-DGGML_AKV_DIRECT_CONTRACT_SHA256="' + "a" * 64 + '"']
            records.append(dict(file=str(inputs / source), arguments=args))
        return self.put("compile_commands.json", json.dumps(records)), inputs, records

    def test_sdk_allowlist_matches_reviewed_eleven(self):
        source = build.HERE.parent / "direct_cost/build_compact.py"
        tree = ast.parse(source.read_text())
        overlays = [ast.literal_eval(node.value) for node in ast.walk(tree)
                    if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name) and target.id == "overlay" for target in node.targets)]
        self.assertEqual(len(overlays), 1)
        self.assertEqual(tuple("software/akv/" + item for item in overlays[0]), build.SDK_OVERLAYS)
        self.assertEqual(len(build.SDK_OVERLAYS), 11)
        self.assertEqual(len(build.DIRECT_OVERLAYS), 3)
        self.assertNotIn(build.FORBIDDEN, build.SDK_OVERLAYS + build.DIRECT_OVERLAYS)
        self.assertIn("examples/simple/simple.cpp", build.LLAMA_OVERLAYS)
        self.assertEqual(len(build.LLAMA_OVERLAYS), 6)

    def test_approval_required_before_output_creation(self):
        out = self.root / "resident_direct_model_no_approval"
        for options in ([], ["--sources-stable"], ["--stability-note", "tests passed"]):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    build.main(["--output", str(out), *options])
                self.assertFalse(out.exists())

    def test_output_is_fresh_and_confined(self):
        valid = self.root / "resident_direct_model_test"
        self.assertEqual(build.validate_output(valid, self.root), valid)
        valid.mkdir()
        for path in (valid, self.root / "wrong", self.root / "nested/resident_direct_model_test"):
            with self.assertRaises(ValueError):
                build.validate_output(path, self.root)
        link = self.root / "resident_direct_model_symlink"
        link.symlink_to(self.root / "absent")
        with self.assertRaises(ValueError):
            build.validate_output(link, self.root)

    def test_environment_injection_rejected_and_unknown_environment_not_inherited(self):
        with mock.patch.dict(os.environ, {"CFLAGS": "-march=native"}, clear=True):
            with self.assertRaisesRegex(ValueError, "CFLAGS"):
                build.clean_environment(self.root, Path("/usr/bin/cmake"), 1)
        with mock.patch.dict(os.environ, {"GGML_RISCV_AKV_EMULATE": "1", "CC": "zcc"}, clear=True):
            env = build.clean_environment(self.root, Path("/usr/bin/cmake"), 1)
        self.assertNotIn("CC", env)
        self.assertNotIn("GGML_RISCV_AKV_EMULATE", env)
        self.assertEqual(env["SOURCE_DATE_EPOCH"], "1")
        self.assertEqual(env["GIT_CEILING_DIRECTORIES"], str(self.root / "inputs"))

    def test_frozen_archive_uses_only_allowed_live_overlays(self):
        repo, inputs, output = self.root / "repo", self.root / "inputs", self.root / "out"
        repo.mkdir()
        inputs.mkdir()
        output.mkdir()
        self.put("repo/" + build.FORBIDDEN, "pinned assembly\n")
        for name in build.SDK_OVERLAYS:
            self.put("repo/" + name, "base\n")
        self.put("repo/software/qbs/base.c")
        self.put("repo/software/llama/base.c")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL).decode().strip()
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Unit Test", "-c", "user.email=unit@example.invalid", "commit", "-qm", "fixture")
        commit = git("rev-parse", "HEAD")
        self.put("repo/" + build.FORBIDDEN, "FORBIDDEN DIRTY ASSEMBLY\n")
        for name in build.SDK_OVERLAYS + build.DIRECT_OVERLAYS:
            self.put("repo/" + name, "reviewed overlay\n")
        self.put("repo/software/qbs/unreviewed.c", "must not appear\n")
        pins = {}
        run = build.Commands(output, dict(os.environ))
        result = build.freeze_repo(run, "sdk", repo, commit,
                                   ("software/qbs", "software/akv", "software/llama"),
                                   build.SDK_OVERLAYS + build.DIRECT_OVERLAYS, inputs, pins)
        self.assertEqual((inputs / "sdk" / build.FORBIDDEN).read_text(), "pinned assembly\n")
        self.assertFalse((inputs / "sdk/software/qbs/unreviewed.c").exists())
        self.assertEqual(len(result["overlays"]), 14)
        build.check_pins(pins)
        self.put("repo/" + build.SDK_OVERLAYS[0], "changed again\n")
        with self.assertRaisesRegex(ValueError, "input drift"):
            build.check_pins(pins)

    def test_overlay_rejects_forbidden_path_traversal_and_symlinks(self):
        self.put("source/good")
        (self.root / "source/link").symlink_to(self.root / "source/good")
        for path in (build.FORBIDDEN, "../escape", "/absolute", "link"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build.copy_overlay(self.root / "source", self.root / "target", path, {})

    def test_archive_rejects_escaping_entries_and_links(self):
        for index, (name, kind) in enumerate((("../bad", tarfile.REGTYPE), ("/bad", tarfile.REGTYPE),
                                            ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE))):
            archive = self.root / (str(index) + ".tar")
            with tarfile.open(archive, "w") as stream:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = "../escape"
                stream.addfile(info)
            with self.assertRaises(ValueError):
                build.extract_archive(archive, self.root / ("extract" + str(index)))

    def test_cmake_has_exact_static_direct_compact_flags(self):
        argv = build.cmake_arguments(self.root, Path("/usr/bin/cmake"), "a" * 64)
        for flag in ("GGML_RISCV_AKV_LINUX_DIRECT=ON", "GGML_RISCV_AKV_RESIDENT=ON",
                     "GGML_RISCV_AKV_COMPACT_COEFFICIENTS=ON", "GGML_RISCV_AKV_LINUX_PORTAL=OFF",
                     "GGML_BACKEND_DL=OFF", "GGML_OPENMP=OFF", "BUILD_SHARED_LIBS=OFF",
                     "GGML_CCACHE=OFF",
                     "GGML_NATIVE=OFF", "GGML_RISCV_QBS=ON", "GGML_RISCV_AKV=ON", "GGML_RISCV_ACCEL_AUTO=ON"):
            self.assertIn("-D" + flag, argv)
        self.assertIn("-DGGML_RISCV_AKV_DIRECT_CONTRACT_SHA256=" + "a" * 64, argv)
        self.assertIn("-DGGML_RISCV_AKV_LINUX_DIRECT_DIR=" + str(self.root / "inputs/sdk/software/llama/platform/linux/direct"), argv)
        self.assertTrue(any("rv64gcv_zfh_zvfh" in item for item in argv))
        self.assertNotIn("zcc", " ".join(argv).lower())
        with self.assertRaises(ValueError):
            build.cmake_arguments(self.root, Path("/usr/bin/cmake"), "")

    def test_cache_rejects_silent_option_or_compiler_drift(self):
        cache = self.cache_fixture()
        build.audit_cache(cache, self.pins)
        cache.write_text(cache.read_text().replace("GGML_OPENMP:BOOL=OFF", "GGML_OPENMP:BOOL=ON"))
        with self.assertRaisesRegex(ValueError, "GGML_OPENMP"):
            build.audit_cache(cache, self.pins)

    def test_cache_accepts_noncache_toolchain_compilers_and_canonical_aliases(self):
        for cached in (False, True):
            for canonical in (False, True):
                with self.subTest(cached=cached, canonical=canonical):
                    build.audit_cache(self.cache_fixture(cached, canonical), self.pins)

    def test_compiler_metadata_requires_gnu_and_one_unambiguous_path(self):
        for change in ("id", "duplicate", "missing", "launcher"):
            with self.subTest(change=change):
                cache = self.cache_fixture(cached=False)
                metadata = cache.parent / "CMakeFiles/3.26.5/CMakeCCompiler.cmake"
                text = metadata.read_text()
                if change == "id":
                    text = text.replace('"GNU"', '"Clang"')
                elif change == "duplicate":
                    text += text.splitlines()[0] + "\n"
                elif change == "missing":
                    text = "\n".join(text.splitlines()[1:])
                else:
                    text += 'set(CMAKE_C_COMPILER_LAUNCHER "ccache")\n'
                metadata.write_text(text)
                with self.assertRaises(ValueError):
                    build.audit_cache(cache, self.pins)

    def test_cache_rejects_unrelated_even_same_hash_pinned_compiler(self):
        cache = self.cache_fixture()
        other = self.put("unrelated/gcc", self.compilers["gcc"].read_text())
        pins = dict(self.pins, **{str(other): build.sha(other)})
        cache.write_text(cache.read_text().replace(
            "CMAKE_C_COMPILER:FILEPATH=" + str(build.TOOL_BIN / "riscv64-linux-gcc"),
            "CMAKE_C_COMPILER:FILEPATH=" + str(other)))
        with self.assertRaisesRegex(ValueError, "reviewed GNU compiler"):
            build.audit_cache(cache, pins)

    def test_cache_rejects_missing_or_changed_compiler_hash_pin(self):
        cache = self.cache_fixture(cached=False)
        with self.assertRaisesRegex(ValueError, "compiler hash pin"):
            build.audit_cache(cache, {})
        self.compilers["gcc"].write_text("compiler drift")
        with self.assertRaisesRegex(ValueError, "compiler hash pin"):
            build.audit_cache(cache, self.pins)

    def test_cache_rejects_ccache(self):
        cache = self.cache_fixture()
        cache.write_text(cache.read_text().replace("GGML_CCACHE:BOOL=OFF", "GGML_CCACHE:BOOL=ON"))
        with self.assertRaisesRegex(ValueError, "GGML_CCACHE"):
            build.audit_cache(cache, self.pins)

    def test_symbols_require_definitions_and_compact_leaf(self):
        nm = "\n".join("00000001 T " + symbol + (")" if symbol.endswith("(") else "") for symbol in build.REQUIRED_SYMBOLS)
        self.assertEqual(build.audit_symbols(nm), list(build.REQUIRED_SYMBOLS))
        with self.assertRaisesRegex(ValueError, "pv_compact"):
            build.audit_symbols(nm.replace("T akv_experimental_resident_pv_compact", "U akv_experimental_resident_pv_compact"))

    def test_elf_must_be_static_riscv64(self):
        good = "Class: ELF64\nMachine: RISC-V\nType: EXEC (Executable file)\n"
        build.audit_elf(good)
        for bad in (good + " INTERP ", good + "(NEEDED)", good.replace("EXEC", "DYN"), good.replace("RISC-V", "x86")):
            with self.assertRaises(ValueError):
                build.audit_elf(bad)

    def test_compile_database_requires_frozen_direct_compact_contract(self):
        path, inputs, records = self.compile_fixture()
        build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        records[0]["file"] = str(self.root / "live/linux-direct.cpp")
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "outside frozen"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        records[0]["file"] = str(inputs / "linux-direct.cpp")
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "missing"):
            build.audit_compile_commands(path, inputs, "b" * 64, self.pins)

    def test_compile_database_accepts_canonical_aliases_but_rejects_unrelated_compiler(self):
        path, inputs, records = self.compile_fixture(canonical=True)
        build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        other = self.put("unrelated/g++", self.compilers["g++"].read_text())
        self.pins[str(other)] = build.sha(other)
        records[0]["arguments"][0] = str(other)
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "reviewed GNU compiler"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)

    def test_compile_database_rejects_launcher_and_changed_pin(self):
        path, inputs, records = self.compile_fixture()
        launcher = self.put("ccache", "unreviewed launcher")
        records[0]["arguments"].insert(0, str(launcher))
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "reviewed GNU compiler"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        path, inputs, _ = self.compile_fixture()
        self.compilers["g++"].write_text("compiler drift")
        with self.assertRaisesRegex(ValueError, "compiler hash pin"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)

    def test_generated_build_info_requires_pin_and_no_other_build_source_is_allowed(self):
        path, inputs, records = self.compile_fixture()
        generated = self.put("build/common/build-info.cpp")
        records.append(dict(file=str(generated), arguments=[str(self.compilers["g++"]), "-c", str(generated)]))
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "generated build-info source pin"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        self.pins[str(generated)] = build.sha(generated)
        build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        generated.write_text("drift")
        with self.assertRaisesRegex(ValueError, "input drift"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)
        records[-1]["file"] = str(self.root / "build/other.cpp")
        path.write_text(json.dumps(records))
        with self.assertRaisesRegex(ValueError, "outside frozen inputs"):
            build.audit_compile_commands(path, inputs, "a" * 64, self.pins)

    def test_deterministic_tar_metadata(self):
        self.put("tree/a")
        self.put("tree/sub/b")
        a, b = self.root / "a.tar", self.root / "b.tar"
        build.pack_tree(self.root / "tree", a, 123)
        os.utime(self.root / "tree/a", (999, 999))
        build.pack_tree(self.root / "tree", b, 123)
        self.assertEqual(build.sha(a), build.sha(b))
        with tarfile.open(a) as archive:
            self.assertTrue(all(info.mtime == 123 and info.uid == 0 and info.gid == 0 for info in archive))

    def test_failed_command_retains_log_and_status(self):
        run = build.Commands(self.root, dict(os.environ))
        with self.assertRaises(RuntimeError):
            run.run("failure", ["sh", "-c", "printf first-failure; exit 7"])
        self.assertEqual(run.records[0]["returncode"], 7)
        self.assertEqual((self.root / "failure.log").read_text(), "first-failure")

    def test_timeout_retains_bounded_failure(self):
        run = build.Commands(self.root, dict(os.environ))
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            run.run("timeout", ["sh", "-c", "sleep 10"], timeout=0.01)
        self.assertEqual(run.records[0]["timeout_seconds"], 0.01)
        self.assertTrue((self.root / "timeout.log").exists())

    def test_contract_records_prerequisites_not_hardware_acceptance(self):
        inputs, delivery = self.root / "inputs", self.root / "delivery"
        inputs.mkdir()
        for name in build.DELIVERY_FILES:
            self.put("delivery/" + name, "fixture")
        image_sha = build.sha(delivery / "kernel/Image")
        self.put("delivery/manifest.json", json.dumps(dict(kernel_sha256=image_sha)))
        self.put("delivery/kernel/result.json", json.dumps(dict(
            image_sha256=image_sha, status="COMPILED_TEST_CANDIDATE_RUNTIME_PENDING")))
        four = {"core/" + name: "a" * 64 for name in ("csr_regfile.sv", "decoder.sv", "cva6.sv", "id_stage.sv")}
        gate = dict(baseline=four, current=four, artifacts={
            name: dict(sha256=build.sha(delivery / "rtl" / name))
            for name in ("cva6-baseline-prerequisite.patch", "cva6-akv-direct-gate.patch", "focused-validation.json")})
        self.put("delivery/rtl/baseline-current-hashes.json", json.dumps(gate))
        with mock.patch.object(build, "KERNEL_SHA256", image_sha):
            contract = build.candidate_contract(inputs, {}, {"commit": "sdk"}, {"commit": "llama"}, delivery)
        self.assertFalse(contract["hardware_accepted"])
        self.assertFalse(contract["provenance_attests_running_board"])
        self.assertTrue(contract["board_pending"])
        self.assertEqual(contract["requirements"]["runtime_workers"], 1)
        self.assertTrue(contract["requirements"]["root_only"])
        self.assertFalse(contract["requirements"]["normal_memory_quant_kv_authority_granted"])
        self.assertFalse(contract["requirements"]["llama_simple_use_mlock"])
        self.assertIn("foreign mapping updates", contract["requirements"]["invalidate_before_external_out_of_lease_changes"])
        self.assertIn("deployment-evidence/kernel/Image", contract["input_sha256"])
        with self.assertRaisesRegex(ValueError, "v4"):
            build.candidate_contract(self.root / "bad-inputs", {}, {}, {}, delivery)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="direct-model-runner-unit-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runner = build.HERE / "run_board.sh"

    def test_shell_syntax_and_help(self):
        subprocess.run(["sh", "-n", str(self.runner)], check=True)
        result = subprocess.run(["sh", str(self.runner), "-h"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("rvv|native|resident", result.stdout)

    def test_real_runner_requires_ack_before_any_output(self):
        out = self.root / "not-created"
        result = subprocess.run(["sh", str(self.runner), "resident", "missing.gguf", str(out)],
                                env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ARA_DIRECT_PREFLIGHT_ACK", result.stderr)
        self.assertFalse(out.exists())

    def mock_bundle(self, help_text="-m model -n count -ngl layers -t workers -fa auto|on|off --kv-type f16|q8_0|q4_0", rc=0, memlock=True):
        bundle = self.root / "bundle"
        bundle.mkdir()
        source = self.runner.read_text()
        # Only the test copy bypasses physical board probes. Production has no bypass.
        substitutions = {
            '"$(uname -m)" = riscv64': '"riscv64" = riscv64',
            '"$(id -u)" = 0': '"0" = 0',
            '"$(cat /sys/devices/system/cpu/online)" = 0': '"0" = 0',
            '-c /dev/ara-akv-direct': '-d /tmp',
            'lock=/tmp/ara-direct-model.lock': 'lock=' + str(self.root / "test.lock"),
        }
        for old, new in substitutions.items():
            self.assertEqual(source.count(old), 1)
            source = source.replace(old, new)
        self.assertIn("ulimit -l unlimited", source)
        source = source.replace("set -eu\n", "set -eu\n" +
            "ulimit() { if [ \"$#\" = 1 ]; then printf 'unlimited\\n'; else return " +
            ("0" if memlock else "1") + "; fi; }\n", 1)
        (bundle / "run_board.sh").write_text(source)
        (bundle / "llama-simple").write_text(
            '#!/bin/sh\nif [ "$1" = -h ]; then\n' + "printf '%s\\n' '" + help_text + "'\nexit 1\nfi\n" +
            "printf '%s\\n' \"$@\"\nenv >&2\n" +
            'if [ -n "${LLAMA_SIMPLE_LOGITS_FILE:-}" ]; then\n' +
            'printf mock-logits > "$LLAMA_SIMPLE_LOGITS_FILE"\n' +
            "printf '%s\\n' 'GGML_AKV_DIRECT_COVERAGE resident_groups=0 legacy_calls=2 legacy_completed=2' >&2\nfi\n" +
            "if [ \"${GGML_RISCV_AKV_TRACE:-0}\" = 1 ]; then printf '%s\\n' 'GGML_AKV_DIRECT_PREP prepares=2 maps=2 smaps=1 cache_hits=1 mlock=1 acquire_attempts=2 releases=2 last_error=none' >&2; fi\n" +
            "exit " + str(rc) + "\n")
        (bundle / "llama-simple").chmod(0o755)
        for name in ("README.md", "candidate.json", "freeze.json", "source-pins.json", "symbol-audit.json", "candidate-contract.json"):
            (bundle / name).write_text("{}\n")
        digest = build.sha(bundle / "candidate-contract.json")
        (bundle / "candidate-contract.sha256").write_text(digest + "\n")
        (bundle / "kernel-image.sha256").write_text(build.KERNEL_SHA256 + "\n")
        (bundle / "SHA256SUMS").write_text("".join(build.sha(path) + "  " + path.name + "\n" for path in sorted(bundle.iterdir())))
        model = self.root / "model with spaces.gguf"
        model.write_text("mock model, not executable data\n")
        env = dict(PATH="/usr/bin:/bin", ARA_DIRECT_PREFLIGHT_ACK="kernel-v4-new-gate-single-worker",
                   ARA_DIRECT_SINGLE_WORKER="yes", ARA_DIRECT_MEMORY_ACK="normal-ram-no-mmio-immutable-model",
                   ARA_DIRECT_POLICY_ACK="helper-owned-locks-no-external-policy",
                   ARA_DIRECT_CONTRACT_SHA256=digest, BOARD_ID="mock-unit-test",
                   BOARD_CLOCK_HZ="50000000", BOARD_HART="0",
                   BITSTREAM_SHA256="a" * 64, KERNEL_SHA256=build.KERNEL_SHA256,
                   GGML_RISCV_AKV_EMULATE="1", GGML_RISCV_QBS_EMULATE="1",
                   GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY="1", LLAMA_SIMPLE_TEACHER_FORCE="1")
        return bundle / "run_board.sh", model, env

    def run_mock(self, runner, model, env, mode):
        out = self.root / (mode + "-output")
        result = subprocess.run(["sh", str(runner), mode, str(model), str(out), "a prompt; still one argument", "4"],
                                env=env, text=True, capture_output=True)
        return result, out

    def test_modes_single_worker_fa_kv_prompt_and_clean_environment(self):
        runner, model, env = self.mock_bundle()
        for mode, akv, resident in (("rvv", "0", "0"), ("native", "1", "0"), ("resident", "1", "1")):
            with self.subTest(mode=mode):
                result, out = self.run_mock(runner, model, env, mode)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((out / "status").read_text(), "EXECUTED_UNVERIFIED\n")
                args = (out / "stdout.txt").read_text().splitlines()
                self.assertEqual(args, ["-m", str(model), "-n", "4", "-ngl", "0", "-t", "1",
                                        "-fa", "on", "--kv-type", "f16", "a prompt; still one argument"])
                actual = dict(line.split("=", 1) for line in (out / "stderr.txt").read_text().splitlines())
                self.assertEqual(actual["GGML_RISCV_AKV"], akv)
                self.assertEqual(actual["GGML_RISCV_AKV_RESIDENT"], resident)
                self.assertEqual(actual["GGML_RISCV_AKV_EMULATE"], "0")
                self.assertEqual(actual["GGML_RISCV_QBS_EMULATE"], "0")
                self.assertEqual(actual["GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY"], "0")
                self.assertNotIn("LLAMA_SIMPLE_TEACHER_FORCE", actual)
                self.assertNotIn("LLAMA_SIMPLE_LOGITS_FILE", actual)
                self.assertEqual(actual["GGML_RISCV_AKV_TRACE"], "0")
                self.assertEqual((out / "memlock-after.txt").read_text(), "unlimited\n")
                again, _ = self.run_mock(runner, model, env, mode)
                self.assertNotEqual(again.returncode, 0)
                self.assertIn("output exists", again.stderr)

    def test_help_mismatch_blocks_model_execution(self):
        runner, model, env = self.mock_bundle(help_text="-m model -n count -ngl layers -t workers")
        result, out = self.run_mock(runner, model, env, "rvv")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLI mismatch", result.stderr)
        self.assertFalse((out / "stdout.txt").exists())
        self.assertEqual((out / "status").read_text(), "FAILED\n")

    def test_failure_is_not_relabelled_or_retried(self):
        runner, model, env = self.mock_bundle(rc=9)
        result, out = self.run_mock(runner, model, env, "resident")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((out / "exit-code.txt").read_text(), "9\n")
        self.assertEqual((out / "status").read_text(), "FAILED\n")
        self.assertFalse((self.root / "test.lock").exists())

    def test_wrong_contract_or_kernel_ack_blocks_output(self):
        runner, model, env = self.mock_bundle()
        for key in ("ARA_DIRECT_CONTRACT_SHA256", "KERNEL_SHA256"):
            bad = dict(env, **{key: "b" * 64})
            result, out = self.run_mock(runner, model, bad, "native")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(out.exists())

    def test_bundle_drift_blocks_output(self):
        runner, model, env = self.mock_bundle()
        (runner.parent / "candidate.json").write_text("changed\n")
        result, out = self.run_mock(runner, model, env, "native")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bundle identity mismatch", result.stderr)
        self.assertFalse(out.exists())

    def test_diagnostic_preserves_zero_resident_counts_and_logits(self):
        runner, model, env = self.mock_bundle()
        env["ARA_DIRECT_DIAGNOSTIC"] = "1"
        result, out = self.run_mock(runner, model, env, "resident")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((out / "status").read_text(), "EXECUTED_UNVERIFIED\n")
        self.assertIn("resident_groups=0", (out / "counters.txt").read_text())
        self.assertIn("legacy_completed=2", (out / "counters.txt").read_text())
        self.assertIn("GGML_AKV_DIRECT_PREP prepares=2 maps=2 smaps=1", (out / "counters.txt").read_text())
        self.assertIn("GGML_RISCV_AKV_TRACE=1", (out / "runtime-environment.txt").read_text())
        self.assertEqual((out / "logits.bin").read_text(), "mock-logits")
        self.assertIn("clock_hz=50000000\nhart=0\ndiagnostic=1", (out / "operator-preflight.txt").read_text())

    def test_memlock_failure_blocks_help_and_execution(self):
        runner, model, env = self.mock_bundle(memlock=False)
        result, out = self.run_mock(runner, model, env, "resident")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot raise memlock", result.stderr)
        self.assertFalse((out / "help.txt").exists())
        self.assertFalse((out / "stdout.txt").exists())

    def test_clock_is_not_guessed(self):
        runner, model, env = self.mock_bundle()
        del env["BOARD_CLOCK_HZ"]
        result, out = self.run_mock(runner, model, env, "resident")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BOARD_CLOCK_HZ", result.stderr)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
