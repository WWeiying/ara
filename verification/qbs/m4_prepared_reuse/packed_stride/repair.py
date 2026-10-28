#!/usr/bin/env python3
"""Build a private blockwise stride repair and replay the unchanged failing graphs."""
import argparse
import difflib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "verification/qbs"))
from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import run_command
from run import check


def once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("Reviewed source structure changed: " + before[:100])
    return source.replace(before, after)


def transform(source):
    source = '#include "strided_input.h"\n' + source
    start = source.index("    void forward_mul_mat(ggml_compute_params * params, ggml_tensor * op) {")
    end = source.index("    void forward_mul_mat_id", start)
    body = source[start:end]
    # The existing cache rejects non-contiguous tensors before reaching this
    # block. Handle those views before the direct four-row producer is called.
    before = """                ggml_quantize_mat_t<INTER_SIZE, PARAM_TYPE>((float *) (data_ptr + i11 * nb11),
                                                            (void *) (wdata_ptr + i11 * nbw1), 4, ne10);"""
    after = """                if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {
                    if (nb10 != sizeof(float) || nb11 != size_t(ne10)*sizeof(float)) {
                        constexpr size_t block = PARAM_TYPE == GGML_TYPE_Q8_K ? 256 : 32;
                        constexpr size_t bytes = PARAM_TYPE == GGML_TYPE_Q8_K ? sizeof(block_q8_K) : sizeof(block_q8_0);
                        ggml_qbs_strided_input::quantize<4, block, 4*bytes>(
                            data_ptr + i11*nb11, wdata_ptr + i11*nbw1, ne10, nb10, nb11,
                            [](const float *x, void *y, int64_t k) {
                                ggml_quantize_mat_t<INTER_SIZE, PARAM_TYPE>(x, y, 4, k);
                            });
                        continue;
                    }
                }
""" + before
    body = once(body, before, after)
    before = """                from_float((float *) (data_ptr + i11 * nb11), (void *) (wdata_ptr + i11 * nbw1), ne10);"""
    after = """                if constexpr (is_qbs_block_type<BLOC_TYPE>::value && INTER_SIZE == 1) {
                    if (nb10 != sizeof(float)) {
                        constexpr size_t block = PARAM_TYPE == GGML_TYPE_Q8_K ? 256 : 32;
                        constexpr size_t bytes = PARAM_TYPE == GGML_TYPE_Q8_K ? sizeof(block_q8_K) : sizeof(block_q8_0);
                        ggml_qbs_strided_input::quantize<1, block, bytes>(
                            data_ptr + i11*nb11, wdata_ptr + i11*nbw1, ne10, nb10, nb11, from_float);
                        continue;
                    }
                }
""" + before
    body = once(body, before, after)
    before = """                from_float((float *) ((char *) src1->data + i11 * nb11),
                           row_major + i11 * nbw1, ne10);"""
    after = """                if (nb10 != sizeof(float)) {
                    constexpr size_t block = PARAM_TYPE == GGML_TYPE_Q8_K ? 256 : 32;
                    constexpr size_t bytes = PARAM_TYPE == GGML_TYPE_Q8_K ? sizeof(block_q8_K) : sizeof(block_q8_0);
                    ggml_qbs_strided_input::quantize<1, block, bytes>(
                        (char *)src1->data + i11*nb11, row_major + i11*nbw1, ne10, nb10, nb11, from_float);
                } else {
""" + before + "\n                }"
    body = once(body, before, after)
    return source[:start] + body + source[end:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.resolve()
    if not out.is_relative_to(ROOT / "verification/out") or out.exists():
        raise ValueError("Fresh independent output required")
    prior = ROOT / "verification/out/m4-packed-stride-repro-20261027-01"
    pins = json.loads((prior / "manifest.json").read_text())
    old = json.loads((prior / "result.json").read_text())
    if old["state"] != "FAIL" or old.get("measured", {}).get("conclusion") != "CONFIRMED":
        raise ValueError("Missing original failure evidence")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Original reproducer/runtime drift")
    runtime = ROOT / "verification/out/m4-prepared-installed-build-20261027-01"
    source = Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp")
    database = runtime / "build/compile_commands.json"
    rows = [r for r in json.loads(database.read_text()) if Path(r["file"]).resolve() == source]
    if len(rows) != 1:
        raise ValueError("Production compile record")
    record = rows[0]
    command = shlex.split(record["command"])
    pins.update(hashes([Path(__file__), HERE / "strided_input.h", HERE / "run.py", database,
                       prior / "result.json", prior / "link.command.json", prior / "qemu.command.json"]))
    out.mkdir(parents=True)
    state = dict(state="PREPARING", pid=os.getpid(), child_pid=None, performance_measured=False,
                 object_overrides=True, production_modified=False, rtl_changed=False)

    def save():
        atomic_json(out / "status.json", state)

    def started(pid):
        state["child_pid"] = pid
        save()

    def run(cmd, name, limit, cwd=out):
        cmd = list(map(str, cmd))
        atomic_json(out / (name + ".command.json"), cmd)
        state.update(state=name.upper(), child_pid=None)
        save()
        if cwd != out:
            # Production -I/dependency paths are relative to this directory.
            with (out / (name + ".log")).open("x") as log:
                proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
                started(proc.pid)
                try:
                    code = proc.wait(timeout=limit)
                except BaseException:
                    proc.kill()
                    proc.wait()
                    raise
        else:
            code = run_command(cmd, out / (name + ".log"), limit, os.environ.copy(), started)
        if code:
            raise RuntimeError(name + " failed")

    try:
        target = out / "repack.cpp"
        before = source.read_text()
        after = transform(before)
        target.write_text(after)
        patch = out / "repair.patch"
        patch.write_text("".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                         fromfile="a/ggml/src/ggml-cpu/repack.cpp", tofile="b/ggml/src/ggml-cpu/repack.cpp")))
        command[command.index("-c") + 1] = str(target)
        command[command.index("-o") + 1] = str(out / "repack.o")
        for option in ("-MF", "-MT"):
            if option in command:
                command[command.index(option)+1] = str(out / ("repack.d" if option == "-MF" else "repack.o"))
        command += ["-iquote", str(source.parent), "-I" + str(HERE)]
        run(command, "compile-repair", 180, record["directory"])
        link = json.loads((prior / "link.command.json").read_text())
        link.insert(link.index("-static")+1, str(out / "repack.o"))
        link[link.index("-o")+1] = str(out / "test")
        link = ["-Wl,-Map="+str(out/"link.map") if arg.startswith("-Wl,-Map=") else arg for arg in link]
        run(link, "link", 180)
        listing = out / "initramfs.list"
        recipe = (prior / "initramfs.list").read_text()
        if recipe.count(str(prior / "test")) != 1:
            raise ValueError("Original initramfs structure")
        listing.write_text(recipe.replace(str(prior/"test"),str(out/"test")))
        cpio = Path("/home/wangwy/llama/platforms/cva6-qemu/sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio")
        with (out/"initramfs.cpio").open("xb") as stream:
            subprocess.run([str(cpio), str(listing)], stdout=stream, check=True, timeout=60)
        pins.update(hashes([target, patch, out/"repack.o", out/"test", out/"link.map", listing, out/"initramfs.cpio"]))
        atomic_json(out/"manifest.json", pins)
        qemu = json.loads((prior/"qemu.command.json").read_text())
        qemu[qemu.index("-initrd")+1] = str(out/"initramfs.cpio")
        run(qemu,"qemu",300)
        measured = check((out/"qemu.log").read_text())
        atomic_json(out/"comparison.json",measured)
        if measured["failed_cases"] or not measured["controls_pass"]:
            raise ValueError("Original failure not fixed")
        if hashes(map(Path,pins))!=pins:
            raise ValueError("Source drift")
        state.update(state="PASS",measured=measured,log_sha256=digest(out/"qemu.log"),
                     scope="Private repack object repairs original Q4_K/Q6_K padded-row graphs; normal integration pending")
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc))
        raise
    finally:
        state["child_pid"]=None
        save()
        atomic_json(out/"result.json",state)


if __name__ == "__main__":
    main()
