#!/usr/bin/env python3
"""Audit completed QBACC evidence without replaying a completed simulation.

VCS may print a constant-zero packed vector as `0`, despite `%b`. Parse its
binary value strictly, then pad solely for the original sealed checker's text
format. Unknowns, nonzero store masks and incomplete handshakes still reject.
The original worker/status/log are never edited.
"""
import argparse
import json
from pathlib import Path
import re

from run_half_scale_soc import atomic_json, check_result, digest, hashes, image_files
from run_qbacc_soc import check_probe


def normalized_log(text):
    lines=[]
    for line in text.splitlines():
        if line.startswith("[QBACC_SEED]"):
            match=re.fullmatch(r"\[QBACC_SEED\] seq=(\d+) fire=([01]{1,4}) "
                               r"owner=([01]) store_valid=([01]{1,4})",line)
            if match is None:
                raise ValueError("Malformed/unknown source-mask trace")
            seq,fire,owner,store=match.groups()
            line=f"[QBACC_SEED] seq={seq} fire={int(fire,2):04b} owner={owner} store_valid={int(store,2):04b}"
        elif line.startswith("[QBACC_START]"):
            if re.fullmatch(r"\[QBACC_START\] seq=\d+ id=\d+ m=\d+ vd=\d+ vl=\d+ sew=\d+",line) is None:
                raise ValueError("Malformed/unknown source geometry trace")
        elif line.startswith("[QBACC_END]"):
            if re.fullmatch(r"\[QBACC_END\] seq=\d+ success=[01] fault=[01]",line) is None:
                raise ValueError("Malformed/unknown terminal trace")
        elif line.startswith("[QBS_PERF]"):
            if re.fullmatch(r"\[QBS_PERF\](?: [a-z_]\w*=\d+)+",line) is None:
                raise ValueError("Malformed/unknown hardware counter trace")
        lines.append(line)
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();run=args.run.resolve(strict=True)
    status=json.loads((run/"status.json").read_text())
    if status["state"] not in ("PASS","FAIL") or status.get("child_pid") is not None:
        raise ValueError("Original worker must be terminal before consuming its evidence")
    pins=json.loads((run/"source-pins.json").read_text())
    if hashes(map(Path,pins))!=pins:raise ValueError("Original sources/ELF/helper drift")
    image=json.loads((run/"image-pins.json").read_text())
    simv=next(Path(path) for path in image if Path(path).name=="simv")
    if hashes(image_files(simv))!=image:raise ValueError("Original image drift")
    case=run/"qbacc_soc_probe";work=case/"work"
    check_result(case/"uvm_result.json",status["cases"]["qbacc_soc_probe"]["elf_sha256"],image)
    result=check_probe(normalized_log((work/"run.vcs.log").read_text()),work/"vector_trace.csv")
    result.update(original_worker_state=status["state"],
        original_worker_error=status.get("error"),
        normalization="Strict binary parse and zero padding only; unknowns/nonzero store mask reject",
        original_run=str(run),
        scope="Actual QBACC probe only; neighbor regressions are separate evidence",
        evidence_sha256=hashes([Path(__file__).resolve(),run/"source-pins.json",run/"image-pins.json",
            run/"status.json",case/"uvm_result.json",work/"run.vcs.log",work/"vector_trace.csv",
            work/"commit_trace.csv"]))
    args.output.resolve().mkdir(parents=True,exist_ok=False)
    atomic_json(args.output.resolve()/"result.json",result)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":main()
