#!/usr/bin/env python3
"""Fresh driver, immutable normal archives, explicit accepted private repack override."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

sys.dont_write_bytecode = True
from check import check, matrix, require

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "verification/out/m4-stride-expanded-20261027-01"
PRIOR = ROOT / "verification/out/m4-packed-stride-repair-20261027-01"
RUNTIME = ROOT / "verification/out/m4-prepared-installed-build-20261027-01"
REFERENCE = ROOT / "verification/out/m4-vector-runtime-graph-20261027-01"
ACTIVE = ROOT / "verification/out/m4-packed-qkv-vcs-20261027-01/source-pins.json"
CAPTURE = Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/prefill/operators/blk_0_attn_q_weight/activation_f32.bin")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def verify(pins):
    bad = [p for p, expected in pins.items() if not Path(p).is_file() or digest(p) != expected]
    require(not bad, "SHA256 drift: " + repr(bad))


def main():
    require(len(sys.argv) == 1 and ROOT == Path("/home/wangwy/openproject/ara_dsa_signoff_integration"), "fixed recipe/worktree")
    OUT.mkdir(parents=True, exist_ok=False)
    pins = {}
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None, qemu_runs=0, qemu_limit_seconds=300,
                 object_overrides=True, production_modified=False, rtl_changed=False, performance_measured=False,
                 planned_cases=65, completed_cases=0)

    def pin(paths):
        for p in paths:
            value = digest(p)
            require(str(p) not in pins or pins[str(p)] == value, "pin changed: " + str(p))
            pins[str(p)] = value

    def run(argv, label, limit, binary=None):
        argv = list(map(str, argv))
        save(OUT / (label + ".command.json"), dict(argv=argv, cwd=str(OUT), timeout_seconds=limit,
                                                  stdout=str(binary) if binary else label + ".log"))
        state.update(state=label.upper(), child_pid=None)
        save(OUT / "status.json", state)
        rc, timed_out = None, False
        with (OUT / (label + ".log")).open("xb") as log:
            stream = binary.open("xb") if binary else log
            try:
                with subprocess.Popen(argv, cwd=OUT, stdout=stream, stderr=log) as process:
                    state["child_pid"] = process.pid
                    save(OUT / "status.json", state)
                    try:
                        rc = process.wait(timeout=limit)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        process.kill()
                        rc = process.wait()
            finally:
                if binary:
                    stream.close()
                save(OUT / (label + ".exit.json"), dict(returncode=rc, timeout=timed_out, limit_seconds=limit))
        require(rc == 0 and not timed_out, label + " failed")

    try:
        for path, expected in (
            (PRIOR / "manifest.json", "8110224ad10cc00458e337b132ce6a351dc18d7fadc8064c6dec0f897495c6cf"),
            (PRIOR / "repack.o", "10393ebc1ff7c5144f767126c0705d405af603643941b690803fb81d03e173eb"),
            (PRIOR / "result.json", "b8c6b4e5a18bb2eeb4d8a53ebdbb0c0be155df9c682c9379b0b1a80f9f45dc48"),
            (PRIOR / "qemu.log", "4e3453e1f1e1cb79f015d40b3344e7c50e42f53c55e410fdd45a8596feb166e1"),
            (RUNTIME / "manifest.json", "7e01c4446b81f73705f61fc4e76977057662bd9f587aa39060d219ba9ed49c84"),
            (ACTIVE, "06097034f29a8f21b0b83e877ba9aebecb4e9ea7b4356cefb119bab4449f475d")):
            require(digest(path) == expected, "accepted identity: " + str(path))
            pins[str(path)] = expected
        active = read(ACTIVE)
        prior = read(PRIOR / "manifest.json")
        installed = read(RUNTIME / "manifest.json")
        for inventory in (active, prior, installed):
            for p, h in inventory.items():
                require(p not in pins or pins[p] == h, "conflicting manifests: " + p)
                pins[p] = h
        sources = sorted(HERE.glob("*"))
        require(all(p.is_file() for p in sources), "only standalone owned sources")
        require(not any(str(p).startswith(str(HERE) + "/") for p in active), "owned path sealed by active worker")
        pin(sources + [PRIOR / "link.command.json", PRIOR / "qemu.command.json", PRIOR / "initramfs.list",
                       RUNTIME / "result.json", REFERENCE / "compile-test.command.json", CAPTURE.with_suffix(".json")])
        verify(pins)
        require(read(PRIOR / "result.json")["state"] == read(RUNTIME / "result.json")["state"] == "PASS", "accepted inputs")
        spec = importlib.util.spec_from_file_location("original_stride_check", HERE.parent / "run.py")
        old_check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old_check)
        require(old_check.check((PRIOR / "qemu.log").read_text()) == read(PRIOR / "result.json")["measured"], "original checker replay")
        require(read(CAPTURE.with_suffix(".json"))["shape"] == [1536, 15, 1, 1], "captured row geometry")
        cases = matrix()
        require(len(cases) == 65, "matrix bound")
        save(OUT / "matrix.json", cases)
        save(OUT / "preflight.json", dict(active_inventory_entries=len(active), active_complete_sha_check="PASS",
              accepted_repair_sha_check="PASS", original_checker_replay="PASS", immutable_entries=len(pins),
              capture_sha256=digest(CAPTURE), capture_selection="first K elements of each original 1536-element row"))
        compile_cmd = read(REFERENCE / "compile-test.command.json")
        compile_cmd[compile_cmd.index("-c")+1] = str(HERE / "test.cpp")
        compile_cmd[compile_cmd.index("-o")+1] = str(OUT / "test.o")
        pin([Path(compile_cmd[0]), Path(compile_cmd[0]).resolve()])
        run(compile_cmd, "compile-test", 180)
        link = read(PRIOR / "link.command.json")
        libs = read(RUNTIME / "result.json")["libraries"]
        require([a for a in link if a.endswith(".a")] == libs and all(a in installed for a in libs), "original normal archives")
        require([a for a in link if a.endswith(".o")][0] == str(PRIOR / "repack.o"), "explicit checked repack override")
        link = [str(OUT / "test.o") if a.endswith("/test.o") else
                "-Wl,-Map=" + str(OUT / "link.map") if a.startswith("-Wl,-Map=") else a for a in link]
        link[link.index("-o")+1] = str(OUT / "test")
        run(link, "link", 180)
        map_text = (OUT / "link.map").read_text()
        require("LOAD " + str(PRIOR / "repack.o") in map_text and "libggml-cpu.a(repack.cpp.o)" not in map_text,
                "link override not effective")
        pin([OUT / "test.o", OUT / "test", OUT / "link.map", OUT / "matrix.json"])
        entries = [shlex.split(l) for l in (PRIOR / "initramfs.list").read_text().splitlines() if l.strip()]
        require(sum(row[:2] == ["file", "/test"] for row in entries) == 1, "initramfs test")
        for row in entries:
            if row[:2] == ["file", "/test"]:
                row[2] = str(OUT / "test")
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        require(str(cpio) in pins and str(CAPTURE) in pins, "pinned tools and capture")
        measured = []
        for typ in ("Q4_K", "Q6_K", "Q4_0", "Q8_0"):
            selected = [c for c in cases if c["type"] == typ]
            directory = OUT / typ
            directory.mkdir()
            recipe = directory / "cases.txt"
            recipe.write_text("".join(" ".join(str(c[k]) for k in ("id", "type", "k", "m", "element", "pad", "wide", "threads")) + "\n" for c in selected))
            listing = directory / "initramfs.list"
            listing.write_text("".join(" ".join(row) + "\n" for row in entries) + f"file /cases.txt {recipe} 444 0 0\n")
            image = directory / "initramfs.cpio"
            run([cpio, listing], typ + "/initramfs", 60, binary=image)
            pin([recipe, listing, image])
            save(OUT / "manifest.json", pins)
            verify(pins)
            cmd = read(PRIOR / "qemu.command.json")
            cmd[cmd.index("-initrd")+1] = str(image)
            cmd[cmd.index("-smp")+1] = "2"
            state["qemu_runs"] += 1
            run(cmd, typ + "/qemu", 300)
            log = (directory / "qemu.log").read_text()
            save(directory / "first-failure.json", dict(lines=[l for l in log.splitlines() if l.startswith(("XS_ERROR", "XS_FIRST_MISMATCH"))]))
            result = check(log, selected)
            save(directory / "comparison.json", result)
            measured.extend(result)
            state["completed_cases"] = len(measured)
            pin([directory / "qemu.log", directory / "comparison.json"])
            save(OUT / "comparison.json", measured)
            print(json.dumps(dict(shard=typ, checked_cases=len(result), total=len(measured))), flush=True)
        verify(pins)
        save(OUT / "manifest.json", pins)
        state.update(state="PASS", paired_cases=len(measured), matmuls=2*len(measured),
                     paired_outputs=sum(c["outputs"] for c in measured), native_commands=sum(c["native"]["native_qbexec"] for c in measured),
                     active_complete_sha_check_after="PASS", all_inputs_sha_check_after="PASS", normal_libraries=libs,
                     scope="Private object software-functional graph acceptance only; no production install, RTL or timing claim")
    except BaseException as exc:
        state.update(state="FAIL", error=repr(exc))
        save(OUT / "manifest.json", pins)
    finally:
        state["child_pid"] = None
        save(OUT / "status.json", state)
        save(OUT / "result.json", state)
    print(json.dumps(state, sort_keys=True), flush=True)
    return 0 if state["state"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
