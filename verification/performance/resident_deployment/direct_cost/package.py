#!/usr/bin/env python3
"""Package checked build artifacts for a separate, new-bitstream board test."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DIRECT = ROOT / "software/llama/platform/linux/direct"
OUT = ROOT.parent / "ara_dsa_signoff_integration/verification/out"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("userspace", "kernel", "safety", "output"):
        ap.add_argument("--" + name, type=Path, required=True)
    args = ap.parse_args()
    user, kernel, safety, out = (getattr(args, name).resolve() for name in
                                 ("userspace", "kernel", "safety", "output"))
    require(out.parent == OUT and out.name.startswith("resident_direct_delivery_") and not out.exists(),
            "use a fresh signoff resident_direct_delivery_* output")
    archive = out.with_suffix(".tar.gz")
    require(not archive.exists(), "archive already exists")
    for path in (user, kernel, safety):
        require(path.parent == OUT, "inputs must be direct signoff output directories")
    u, k, s = (read(path / "result.json") for path in (user, kernel, safety))
    require(u["state"] == "USERSPACE_BUILT_NOT_EXECUTED" and u["post_pins_match"], "userspace build not qualified")
    require(k["status"] == "COMPILED_TEST_CANDIDATE_RUNTIME_PENDING" and k["source_pins_match"],
            "kernel Image build not qualified")
    require(s["state"] == "PASS" and s["post_pins_match"] and s["safety_runtime_status"] == "NOT_RUN",
            "safety ELF build not qualified")
    for report in (u, k, s):
        key = "image" if "image" in report else "elf"
        require(sha(report[key]) == report[key + "_sha256"], "compiled artifact changed")
    for path in (user, kernel, safety):
        for name, digest in read(path / "source-pins.json").items():
            require(sha(name) == digest, "sealed input changed: " + name)
    guard_summary = read(kernel / "entry-guard-review.json")
    require(guard_summary["scope"] == "static-and-compiled-runtime-pending" and
            guard_summary["image_sha256"] == k["image_sha256"], "entry review summary mismatch")
    guard = read(kernel / "entry-guard-review.schema-v1.json")
    require(guard["status"] == "ENTRY_GUARD_STATIC_REVIEW_PASS_RUNTIME_PENDING" and
            guard["image_sha256"] == k["image_sha256"], "missing matching entry guard review")
    for name in ("early_pre_discard_drain", "initialized_state_admission", "saved_off_not_promoted",
                 "return_state_revalidated", "single_drain_per_return_grant",
                 "switch_cannot_bypass_guard", "generic_user_entry_guard"):
        require(guard[name] is True, "entry guard review failed: " + name)
    require(Path(guard["linux_tree"]).resolve() == kernel / "linux", "wrong reviewed kernel tree")
    for name, digest in guard["built_source_sha256"].items():
        require(sha(kernel / "linux" / name) == digest, "reviewed kernel source changed: " + name)
        require(guard_summary["built_files"][str(kernel / "linux" / name)] == digest,
                "entry review file inventories disagree")
    for name in ("early_pre_discard_drain", "initialized_state_admission", "saved_off_not_promoted",
                 "return_state_revalidated"):
        require(guard_summary[name] is True, "entry review summary failed: " + name)
    require(sha(kernel / "test.config") == guard["config_sha256"], "reviewed config changed")
    require(sha(kernel / "linux/arch/riscv/kernel/akv_direct.o") == guard["driver_object_sha256"],
            "reviewed kernel object changed")
    require(sha(guard["review_tool"]) == guard["review_tool_sha256"], "review tool changed")
    rtl = read(DIRECT / "rtl/focused-validation.json")
    require(rtl["state"] == "WIRED_CANDIDATE_REAL_ID_STAGE_INTEGRATION_CHECKED", "RTL gate not qualified")
    for path, digest in rtl["candidate_hashes"].items():
        require(sha(ROOT / "hardware/deps/cva6" / path) == digest, "live RTL changed: " + path)
    for path, digest in rtl["evidence_pins"].items():
        require(sha(path) == digest, "RTL evidence changed: " + path)
    for path in (user / "board", safety / "bundle"):
        subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=path, check=True)
    subprocess.run(["sh", "-n", str(HERE / "run_environment.sh")], check=True)
    out.mkdir()
    board = out / "board"
    board.mkdir()
    shutil.copytree(user / "board", board / "perf")
    shutil.copytree(safety / "bundle", board / "safety")
    shutil.copyfile(HERE / "run_environment.sh", board / "run_environment.sh")
    (board / "kernel.sha256").write_text(k["image_sha256"] + "\n")
    shutil.copytree(DIRECT / "rtl", out / "rtl")
    shutil.copytree(kernel / "inputs", out / "kernel-build-inputs")
    image_dir = out / "kernel"
    image_dir.mkdir()
    shutil.copyfile(k["image"], image_dir / "Image")
    for name in ("test.config", "config.diff", "commands.json", "source-pins.json", "result.json",
                 "entry-guard-review.json", "entry-guard-review.schema-v1.json"):
        shutil.copyfile(kernel / name, image_dir / name)
    for patch in kernel.glob("*.patch"):
        shutil.copyfile(patch, image_dir / patch.name)
    for name in ("direct_uapi.h", "direct_client.h", "direct_client.c", "README.md", "BOARD_HANDOFF.md"):
        shutil.copyfile(DIRECT / name, out / name)
    for name in ("LOW_OVERHEAD.md", "PREPARED_HANDOFF.md"):
        if (DIRECT / name).exists():
            shutil.copyfile(DIRECT / name, out / name)
    shutil.copyfile(__file__, out / "package.py")
    builder = {"resident-low-overhead-v1": "build_low_overhead.py",
               "resident-low-overhead-v2": "build_prepared.py"}.get(u.get("variant"), "build.py")
    shutil.copyfile(HERE / builder, out / "userspace-build.py")
    if u.get("sdk_overlay"):
        overlay = out / "sdk-overlay/software/akv"
        for relative in u["sdk_overlay"]:
            source = user / "inputs/sdk/software/akv" / relative
            dest = overlay / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
        save(out / "sdk-overlay/manifest.json", {
            "base_commit": u["sdk_commit"], "variant": u["variant"],
            "files": {relative: sha(overlay / relative) for relative in u["sdk_overlay"]}})
    shutil.copyfile(guard["review_tool"], out / "entry-guard-review.py")
    evidence = out / "evidence"
    evidence.mkdir()
    for name, path in (("userspace", user), ("kernel", kernel), ("safety", safety)):
        save(evidence / (name + "-build.json"), read(path / "result.json"))
    save(out / "manifest.json", {
        "state": "BUILT_CANDIDATE_BOARD_PREFLIGHT_PENDING", "board_executed": False,
        "performance_measured": False, "whole_model_tested": False,
        "requires_new_gate_bitstream": True, "requires_matching_test_kernel": True,
        "scope": "single-hart single-owner captured-Qwen3 complete SDK Attention pair",
        "inputs": {"userspace": str(user), "kernel": str(kernel), "safety": str(safety)},
        "kernel_sha256": k["image_sha256"], "performance_elf_sha256": u["elf_sha256"],
        "safety_elf_sha256": s["elf_sha256"], "sdk_commit": u["sdk_commit"],
        "sdk_variant": u.get("variant", "unmodified-pinned-sdk"),
        "sdk_overlay": u.get("sdk_overlay", []),
        "rtl_checks": rtl["focused_test"]["checks"], "rtl_whole_core_tested": False,
        "sequence": ["build gate bitstream separately", "boot isolated matching test kernel",
                     "run 11 bounded safety cases", "if passing, collect three paired SDK points",
                     "run analyzer off-board"],
        "not_included": ["bitstream", "OpenSBI", "board DTB", "root filesystem", "whole-model binary"],
    })
    # The board subset has its own inventory; the kernel need not be copied to the rootfs.
    def checksums(directory):
        files = sorted(p for p in directory.rglob("*") if p.is_file() and p != directory / "SHA256SUMS")
        (directory / "SHA256SUMS").write_text("".join(
            sha(p) + "  " + str(p.relative_to(directory)) + "\n" for p in files))
    checksums(board)
    checksums(out)
    with tarfile.open(archive, "x:gz") as tar:
        tar.add(out, arcname=out.name)
    print(json.dumps({"state": "PACKAGED_BOARD_NOT_RUN", "directory": str(out),
                      "archive": str(archive), "archive_sha256": sha(archive)}, indent=2))


if __name__ == "__main__":
    main()
