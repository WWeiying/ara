#!/usr/bin/env python3
"""One bounded installed-library GGML/QEMU stride reproducer; mismatch is failure."""
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / "verification/out/m4-packed-stride-repro-20261027-01"
RUNTIME = ROOT / "verification/out/m4-prepared-installed-build-20261027-01"
REFERENCE = ROOT / "verification/out/m4-vector-runtime-graph-20261027-01"
ACTIVE = ROOT / "verification/out/m4-packed-qkv-vcs-20261027-01/source-pins.json"
CAPTURE = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight/activation_f32.bin")
MANIFEST_SHA = "7e01c4446b81f73705f61fc4e76977057662bd9f587aa39060d219ba9ed49c84"
ACTIVE_SHA = "06097034f29a8f21b0b83e877ba9aebecb4e9ea7b4356cefb119bab4449f475d"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(path.read_text())


def save(name, value):
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def verify(pins):
    bad = [name for name, expected in pins.items() if not Path(name).is_file() or digest(name) != expected]
    require(not bad, "SHA256 drift: " + repr(bad))


def fields(line):
    return dict(word.split("=", 1) for word in line.split()[1:])


def check(log):
    """Independently reconcile every output bit, scope, callback and completion."""
    lines = log.splitlines()
    expected = [(t, m, p) for t in ("Q4_K", "Q6_K") for m in (4, 7) for p in (0, 1, 16)]
    cases, firsts, values, observations, prepares, execs = [], [], [], [], [], {}
    active = None
    for line in lines:
        if line.startswith("M4_STRIDE_ERROR"):
            raise ValueError(line)
        if line.startswith("M4_STRIDE_BEGIN "):
            require(active is None, "Nested case")
            f = fields(line)
            active = (f["type"], int(f["m"]), int(f["pad"]))
            require(active == expected[len(cases)], "Case order")
            values, observations, prepares, firsts = [], [], [], []
        elif line.startswith(("M4_STRIDE_VALUE ", "M4_STRIDE_OBSERVE ", "M4_STRIDE_FIRST_MISMATCH ", "M4_STRIDE_CASE ")):
            f = fields(line)
            key = (f["type"], int(f["m"]), int(f["pad"]))
            require(key == active and f["k"] == "256" and f["n"] == "8", "Case scope/shape")
            if line.startswith("M4_STRIDE_VALUE "):
                i = len(values)
                require((int(f["index"]), int(f["row"]), int(f["col"])) == (i, i // 8, i % 8), "Output order")
                for key_name in ("ref", "got"):
                    value = struct.unpack("!f", bytes.fromhex(f[key_name + "_bits"]))[0]
                    require(math.isfinite(value) and math.isfinite(float(f[key_name])), "Nonfinite output")
                    require(struct.pack("!f", float(f[key_name])).hex() == f[key_name + "_bits"], "Decimal/bit disagreement")
                values.append(f)
            elif line.startswith("M4_STRIDE_OBSERVE "):
                side = int(f["side"])
                require(side in (0, 1) and f["phase"] in ("before", "after"), "Callback side/phase")
                pad = active[2] if side else 0
                require(f["nb0"] == "4" and int(f["nb1"]) == (256 + pad) * 4, "Actual source stride")
                require(f["same_tensor"] == f["same_data"] == "1" and int(f["contiguous"]) == int(pad == 0), "Contiguized input")
                observations.append((side, f["phase"]))
            elif line.startswith("M4_STRIDE_FIRST_MISMATCH "):
                firsts.append(f)
            else:
                require(len(values) == 8 * active[1], "Incomplete paired outputs")
                require(observations == [(0, "before"), (0, "after"), (1, "before"), (1, "after")], "Incomplete graph callbacks")
                require(len(prepares) == 2 and all(p == {"enabled": "1", "path": "rvv", "k": "256"} for p in prepares), "Old four-row producer not used twice")
                mismatch = [v for v in values if v["ref_bits"] != v["got_bits"]]
                require(firsts == mismatch[:1], "First mismatch evidence")
                equal_rows = sum(1 << row for row in range(active[1]) if not any(int(v["row"]) == row for v in mismatch))
                require(int(f["mismatches"]) == len(mismatch) and int(f["equal_rows"]) == equal_rows, "Mismatch accounting")
                require(f["complete"] == f["finite"] == f["input_integrity"] == "1" and f["graph_status"] == "0", "Graph/integrity failure")
                require(f["result"] == ("FAIL" if mismatch else "PASS"), "False case acceptance")
                cases.append(dict(type=active[0], k=256, n=8, m=active[1], pad=active[2],
                                  nb0=4, nb1=(256 + active[2]) * 4, mismatches=len(mismatch),
                                  equal_rows=equal_rows, first_mismatch=firsts[0] if firsts else None,
                                  graph_success=True, finite=True, full_input_integrity=True))
                active = None
        elif line.startswith("GGML_RISCV_QBS_Q8K_M4_PREPARE "):
            require(active is not None, "Unscoped preparation")
            prepares.append(fields(line))
        elif line.startswith("GGML_RISCV_QBS_M4_CACHE "):
            raise ValueError("Cache unexpectedly active")
        elif line.startswith("GGML_RISCV_QBS_EXEC "):
            f = fields(line)
            require(f["type"] not in execs, "Duplicate execution summary")
            execs[f["type"]] = f
    require(len(cases) == 12 and active is None, "Incomplete suite")
    require(set(execs) == {"Q4_K", "Q6_K"}, "Missing native format execution")
    for f in execs.values():
        require(int(f["native_qbexec"]) > 0 and f["emulated_commands"] == "0" and int(f["commands_m4"]) > 0, "Native QEMU instruction path missing")
    failed = sum(c["mismatches"] != 0 for c in cases)
    mismatches = sum(c["mismatches"] for c in cases)
    terminal = (f"M4_STRIDE_SUITE_{'FAIL' if failed else 'PASS'} graphs=12 matmuls=24 pairs=528 "
                f"failed_cases={failed} mismatches={mismatches} capture_integrity=1 performance=not_measured")
    require([l for l in lines if l.startswith("M4_STRIDE_SUITE_")] == [terminal], "False or missing terminal result")
    require([l for l in lines if l.startswith("GUEST_TEST_EXIT=")] == [f"GUEST_TEST_EXIT={int(bool(failed))}"], "Guest exit status")
    require(lines.count("M4_STRIDE_CONFIG cache=0 prepare=1 wide_m=0 activation_context=0 emulate=0 threads=1") == 1, "Configuration")
    controls_ok = all(c["mismatches"] == 0 for c in cases if c["pad"] == 0)
    return dict(cases=cases, failed_cases=failed, mismatches=mismatches, native_execution=execs,
                controls_pass=controls_ok, first_mismatch=next((c["first_mismatch"] for c in cases if c["mismatches"]), None),
                conclusion=("CONFIRMED" if controls_ok else "INCONCLUSIVE_CONTROL_FAILURE") if failed else "NOT_REPRODUCED_IN_BOUNDED_MATRIX")


def main():
    require(len(sys.argv) == 1, "No overrides: fixed bounded one-run recipe")
    require(ROOT == Path("/home/wangwy/openproject/ara_dsa_signoff_integration"), "Wrong worktree")
    OUT.mkdir(parents=True, exist_ok=False)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None, qemu_limit_seconds=300,
                 qemu_runs=0, object_overrides=False, performance_measured=False)
    pins = {}

    def pin(paths):
        pins.update({str(p): digest(p) for p in paths})

    def run(argv, label, limit):
        argv = list(map(str, argv))
        save(label + ".command.json", argv)
        state.update(state=label.upper(), child_pid=None)
        save("status.json", state)
        start = time.monotonic()
        with (OUT / (label + ".log")).open("x") as stream:
            with subprocess.Popen(argv, cwd=OUT, stdout=stream, stderr=subprocess.STDOUT) as process:
                state["child_pid"] = process.pid
                save("status.json", state)
                try:
                    rc = process.wait(timeout=limit)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    save(label + ".exit.json", dict(timeout=True, limit_seconds=limit))
                    raise
        save(label + ".exit.json", dict(returncode=rc, elapsed_seconds=time.monotonic() - start))
        require(rc == 0, label + " process failed: " + str(rc))

    try:
        require(digest(RUNTIME / "manifest.json") == MANIFEST_SHA, "Installed manifest identity")
        require(digest(ACTIVE) == ACTIVE_SHA, "Active VCS pin inventory identity")
        installed = read_json(RUNTIME / "manifest.json")
        verify(installed)
        report = read_json(RUNTIME / "result.json")
        require(report["state"] == "PASS", "Installed build not passing")
        libs = report["libraries"]
        require(len(libs) == 4 and {Path(p).name for p in libs} == {"libllama.a", "libggml.a", "libggml-cpu.a", "libggml-base.a"}, "Normal libraries only")
        require(all(p in installed for p in libs), "Unpinned normal library")
        active_pins = read_json(ACTIVE)
        sources = [HERE / name for name in ("test.cpp", "run.py", "README.md")]
        require(not any(str(p) in active_pins for p in sources), "Owned source is sealed by VCS worker")
        require(read_json(REFERENCE / "result.json")["state"] == "PASS", "Verified reference required")
        reference_pins = read_json(REFERENCE / "manifest.json")
        argv = read_json(REFERENCE / "qemu.command.json")
        require("xaraqbs=true" in argv[argv.index("-cpu") + 1], "Custom instruction QEMU required")
        recipe = REFERENCE / "initramfs.list"
        entries = [shlex.split(line) for line in recipe.read_text().splitlines() if line.strip()]
        init = [Path(row[2]) for row in entries if row[:2] == ["file", "/init"]]
        require(len(init) == 1 and CAPTURE.stat().st_size == 92160, "Init/capture geometry")
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        used = [CAPTURE, recipe, *init, cpio, Path(argv[0]), Path(argv[argv.index("-bios") + 1]), Path(argv[argv.index("-kernel") + 1])]
        require(all(str(p) in reference_pins for p in used), "Unpinned reference asset")
        verify({str(p): reference_pins[str(p)] for p in used})
        pins.update(installed)
        pin([*used, *sources, ACTIVE, RUNTIME / "manifest.json", RUNTIME / "result.json",
             REFERENCE / "manifest.json", REFERENCE / "result.json", REFERENCE / "qemu.command.json",
             REFERENCE / "compile-test.command.json"])
        save("preflight.json", dict(installed_manifest_sha256=MANIFEST_SHA, installed_entries=len(installed),
                                    installed_sha_check="PASS", active_pins_sha256=ACTIVE_SHA,
                                    capture_sha256=digest(CAPTURE), prefix_floats=1792, reference_assets_sha_check="PASS"))
        cmd = read_json(REFERENCE / "compile-test.command.json")
        compiler = Path(cmd[0])
        pin([compiler, compiler.resolve()])
        cmd[cmd.index("-c") + 1] = str(HERE / "test.cpp")
        cmd[cmd.index("-o") + 1] = str(OUT / "test.o")
        run(cmd, "compile-test", 180)
        run([compiler, "-static", OUT / "test.o", *libs, "-ldl", "-lm", "-pthread",
             "-Wl,-Map=" + str(OUT / "link.map"), "-o", OUT / "test"], "link", 180)
        require(sum(row[:2] == ["file", "/test"] for row in entries) == 1, "Guest test recipe")
        for row in entries:
            if row[:2] == ["file", "/test"]:
                row[2] = str(OUT / "test")
        entries.append(["file", "/activation.bin", str(CAPTURE), "444", "0", "0"])
        listing = OUT / "initramfs.list"
        listing.write_text("".join(" ".join(row) + "\n" for row in entries))
        save("initramfs.command.json", [str(cpio), str(listing)])
        with (OUT / "initramfs.cpio").open("xb") as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pin([OUT / "test.o", OUT / "test", OUT / "link.map", listing, OUT / "initramfs.cpio"])
        save("manifest.json", pins)
        verify(pins)
        argv[argv.index("-initrd") + 1] = str(OUT / "initramfs.cpio")
        state["qemu_runs"] = 1
        run(argv, "qemu", 300)
        log = (OUT / "qemu.log").read_text()
        # Preserve raw first-failure evidence even if later schema validation fails.
        first = next((line for line in log.splitlines() if line.startswith("M4_STRIDE_FIRST_MISMATCH ")), None)
        save("first-mismatch.json", dict(line=first))
        measured = check(log)
        save("comparison.json", measured)
        verify(pins)
        state.update(state="FAIL" if measured["failed_cases"] else "PASS", measured=measured,
                     input_sha_check_after="PASS", log_sha256=digest(OUT / "qemu.log"),
                     normal_libraries=libs, scope="Software functional only; not RTL or performance evidence")
    except Exception as exc:
        state.update(state="FAIL", error=repr(exc))
    finally:
        if (OUT / "qemu.log").exists() and not (OUT / "first-mismatch.json").exists():
            log = (OUT / "qemu.log").read_text(errors="replace")
            first = next((line for line in log.splitlines() if line.startswith("M4_STRIDE_FIRST_MISMATCH ")), None)
            save("first-mismatch.json", dict(line=first))
        state["child_pid"] = None
        save("status.json", state)
        save("result.json", state)
    print(json.dumps(dict(state=state["state"], conclusion=state.get("measured", {}).get("conclusion"),
                          error=state.get("error"), output=str(OUT)), sort_keys=True), flush=True)
    return 0 if state["state"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
