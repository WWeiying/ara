#!/usr/bin/env python3
"""Package matching host/Linux/RTL evidence. Does not infer board performance."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text())
def save(p, x): p.write_text(json.dumps(x, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("software", "module", "linux", "rtl", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--wait-seconds", type=int, default=0)
    p.add_argument("--worker-sha256")
    a = p.parse_args()
    assert 0 <= a.wait_seconds <= 2400
    if a.worker_sha256: assert sha(__file__) == a.worker_sha256, "worker source drift"
    sw, mod, linux, rtl, out = (getattr(a, n).resolve() for n in ("software", "module", "linux", "rtl", "output"))
    root = Path("/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out")
    assert all(x.parent == root for x in (sw, mod, linux, rtl, out)) and not out.exists()
    deadline = time.monotonic() + a.wait_seconds
    if not (rtl / "result.json").exists():
        print(json.dumps(dict(state="WAITING_FOR_RTL", rtl=str(rtl), timeout_seconds=a.wait_seconds)), flush=True)
    while not (rtl / "result.json").exists():
        if time.monotonic() >= deadline: raise TimeoutError("RTL result not ready; nothing packaged")
        time.sleep(min(15, max(0, deadline - time.monotonic())))
    q, m, l, r = read(sw / "qualification.json"), read(mod / "result.json"), read(linux / "result.json"), read(rtl / "result.json")
    assert q["state"] == "HOST_SANITIZER_RV64_CHECKED_LINUX_RTL_BOARD_PENDING"
    assert m["state"] == "MODULE_BUILT_NOT_EXECUTED" and l["state"] == "QEMU_LINUX_VIEW_V2_SAFETY_PASS"
    assert r["state"] == "REAL_KERNEL_VIEWS_RTL_CHECKED", r
    assert q["module_sha256"] == m["module_sha256"] == l["module_sha256"] == sha(sw / "board/ara_resident.ko")
    assert r["core_sha256"] == m["core_sha256"] == sha(mod / "module/sdk/ara_resident_compute_core.o")
    assert q["elf_sha256"] == sha(sw / "board/resident-ggml-pair")
    assert q["pins_match"] and m["pins_match"] and l["source_pins_match"] and r["post_pins_match"]
    for filename in (sw / "qualification-source-pins.json", mod / "source-pins.json"):
        assert all(sha(path) == digest for path, digest in read(filename).items()), str(filename)
    copied_inputs = {}
    if (sw / "reuse.json").exists():
        old = Path(read(sw / "reuse.json")["build"])
        final_pins = read(sw / "qualification-source-pins.json")
        for path, expected in read(old / "source-pins.json").items():
            try: relative = Path(path).relative_to(old / "inputs")
            except ValueError: continue
            copied = sw / "inputs" / relative
            expected = final_pins.get(str(copied), expected)
            assert sha(copied) == expected, "copied frozen input drift: " + str(copied)
            copied_inputs[str(copied)] = expected
    out.mkdir()
    board = out / "board"
    shutil.copytree(sw / "board", board)
    evidence = {}
    for name, directory, filename in (("software", sw, "qualification.json"), ("module", mod, "result.json"),
                                      ("linux", linux, "result.json"), ("rtl", rtl, "result.json")):
        evidence[name] = dict(path=str(directory / filename), sha256=sha(directory / filename))
        shutil.copyfile(directory / filename, board / (name + "-evidence.json"))
    manifest = read(board / "manifest.json")
    manifest.update(linux_lifecycle_pending=False, rtl_compute_pending=False, board_executed=False,
                    performance_claim=False, evidence=evidence)
    save(board / "manifest.json", manifest)
    receipt = dict(state="SOFTWARE_LINUX_RTL_CHECKED_BOARD_PENDING", evidence=evidence,
                   module_sha256=m["module_sha256"], elf_sha256=q["elf_sha256"], core_sha256=m["core_sha256"],
                   board_executed=False, performance_claim=False, rtl_modified=False)
    save(out / "copied-inputs-audit.json", copied_inputs)
    receipt["copied_inputs_checked"] = len(copied_inputs)
    save(board / "ACCEPTANCE.json", receipt)
    (board / "SHA256SUMS").write_text("".join(f"{sha(f)}  {f.name}\n" for f in sorted(board.iterdir())
                                            if f.is_file() and f.name != "SHA256SUMS"))
    subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=board, check=True)
    tar = out / "resident-live-kv-checked.tar.gz"
    subprocess.run(["tar", "-czf", tar, "-C", out, "board"], check=True)
    receipt["bundle_sha256"] = sha(tar)
    save(out / "result.json", receipt)
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__": main()
