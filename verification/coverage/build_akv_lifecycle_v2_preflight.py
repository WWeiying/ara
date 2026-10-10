"""Pinned lifecycle successor: observe command-return CSRs before snapshot VSET."""
from pathlib import Path
import build_akv_lifecycle_preflight as first

APP=first.ROOT/"apps/riscv-tests/isa/rv64uv/vakv_lifecycle_boundary_v2.c"
FIRST=first.OUT/"akv-lifecycle-preflight-721-20261006-01"
FIRST_SEAL="e6d47a7cd66591203cdfdbd57fba5f629b94fa3edec6742142642d391dd6fd2d"
OLD_BLOCK='#ifndef AKV_LIFECYCLE_HOST\n    asm volatile("li t0,64\\nvsetvli zero,t0,e16,m1,tu,mu" ::: "t0","memory");\n#endif\n    capture_csrs(p);snapshot(p);'
NEW_BLOCK='    // Observe architectural CSRs before snapshot changes the vector configuration.\n    capture_csrs(p);snapshot(p);'


def capture_contract(predecessor, successor):
    first.require(predecessor.count(OLD_BLOCK)==1 and successor==predecessor.replace(OLD_BLOCK,NEW_BLOCK),
                  "Unexpected successor delta / command-return CSR observation lost")


def target_evidence():
    pins,target=_target()
    first.require(first.sha(FIRST/"preflight-manifest.json")==FIRST_SEAL,"Predecessor preflight drift")
    import json
    manifest=json.loads((FIRST/"preflight-manifest.json").read_text())
    source=first.ROOT/"apps/riscv-tests/isa/rv64uv/vakv_lifecycle_boundary.c"
    first.require(first.sha(source)==manifest["pins"][str(source)],"Frozen predecessor source drift")
    capture_contract(source.read_text(),APP.read_text())
    for p in (source,FIRST/"preflight-manifest.json",Path(__file__).resolve(),
              Path(__file__).with_name("test_build_akv_lifecycle_v2_preflight.py")):
        pins[str(p)]=first.sha(p)
    target=dict(target,command_return_CSR_capture_before_snapshot_VSET=True,
                expected_native_vsets=11,expected_vector_loads=32,expected_vector_stores=320,
                frozen_predecessor_seal=FIRST_SEAL)
    return pins,target


_target=first.target_evidence


def main():
    # Configure the sealed builder only in this fresh process; no files are edited.
    first.APP=APP;first.NAME="vakv_lifecycle_boundary_v2"
    first.target_evidence=target_evidence
    first.main()


if __name__=="__main__":main()
