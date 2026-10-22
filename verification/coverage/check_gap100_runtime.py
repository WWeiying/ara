"""Bounded GAP100 offline diagnostics, never admission or mismatch normalization."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import admit_gap97_offline as common
import admit_gap99_offline as zero
import build_gap100_preflight as software
import run_gap100_simulation as runner
from ara_verify.spike_trace import _scalar_memory_access

ROOT, OUT, require, save = common.ROOT, common.OUT, software.require, software.save
RUN = OUT / "gap100-csr-hpm-vectored-old-image-20261006-01"
RUN_SEAL = "99628c3b968ca032a79b389fab4a47b695cec7897fec94cc3eec99f8ee940e3d"
HEX_FIELDS = {"pc", "insn", "rd_wdata", "mem_addr", "mem_rmask", "mem_wmask", "mem_wdata"}


def scalar_memory(instruction):
    if instruction & 3 == 3:
        return _scalar_memory_access(instruction)
    # RV64 C.LW/C.LD/C.SW/C.SD and their SP forms. No FP C instructions
    # occur in this scalar integer fixture.
    quadrant, funct3 = instruction & 3, instruction >> 13
    if quadrant in (0, 2):
        return {2: ("read", 4), 3: ("read", 8), 6: ("write", 4), 7: ("write", 8)}.get(funct3)
    return None


def commit_rows(path):
    rows = [{k: v if k == "event" else int(v, 16 if k in HEX_FIELDS else 10)
             for k, v in r.items()} for r in common.read_csv(path, common.COMMIT_FIELDS)]
    require(rows and [r["order"] for r in rows] == list(range(len(rows))), "Incomplete scalar order")
    require(all(r["event"] == "retire" and r["trap"] in (0, 1) and r["trans_id"] == -1
                and r["port"] in (0, 1) and 0 <= r["rd"] < 32 for r in rows), "Unknown/non-scalar event")
    require(all(a["cycle"] <= b["cycle"] for a, b in zip(rows, rows[1:])), "Cycle regression")
    require(all(0 <= r[k] < (1 << (32 if k == "insn" else 64)) for r in rows for k in HEX_FIELDS),
            "Unknown/overflow scalar data")
    require(not any(zero.shape.is_accelerator(r["insn"]) for r in rows), "Unexpected VSET/vector/CVX")
    return rows


def retired_commits(rows):
    commits = []
    for r in rows:
        if r["trap"]:
            require(not r["mem_wmask"] and not r["mem_rmask"], "Trap memory side effect")
            continue
        access = scalar_memory(r["insn"])
        memory = ()
        if access is None:
            require(not r["mem_rmask"] and not r["mem_wmask"], "Non-memory instruction has memory effect")
        else:
            kind, size = access
            address = r["mem_addr"]
            require(address % size == 0, "Unexpected unaligned scalar access")
            mask = ((1 << size) - 1) << (address & 7)
            require(r["mem_wmask"] == (mask if kind == "write" else 0) and
                    r["mem_rmask"] == (mask if kind == "read" else 0), "Scalar address/mask differs")
            memory = ((address, r["mem_wdata"] & ((1 << (8 * size)) - 1) if kind == "write" else None),)
        commits.append(SimpleNamespace(pc=r["pc"], instruction=r["insn"],
            gpr_writes={r["rd"]: r["rd_wdata"]} if r["rd"] else {}, fpr_writes={},
            vector_writes={}, csr_writes={}, memory_accesses=memory))
    return commits


def expected_handler_causes():
    expected = []
    for row in range(15):
        priv, _, _, cause = software.phase(row)
        if cause:
            expected.append((0x142 if row >= 13 else 0x342, cause))
        expected.append((0x342, 2 if row == 14 else priv + 8))
    return expected


def handler_causes(commits):
    actual = []
    for c in commits:
        insn = c.instruction
        if insn & 127 == 0x73 and insn >> 20 in (0x142, 0x342) and (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0:
            rd = (insn >> 7) & 31
            require(rd == 6 and c.gpr_writes.keys() == {6}, "Wrong handler cause read destination")
            actual.append((insn >> 20, c.gpr_writes[6]))
    # The program also saves initial mcause/scause with arbitrary compiler-selected
    # destinations. Those reads are excluded by the exact handler PC inventory,
    # not by CSR value or a loose count, in runtime().
    require(actual == expected_handler_causes(), "Unexpected/missing/reordered handler traps")
    return actual


def handler_read_pcs(spike):
    pcs = set()
    for c in spike:
        insn = c.instruction
        if (insn & 127 == 0x73 and insn >> 20 in (0x142, 0x342) and
                (insn >> 12) & 7 == 2 and (insn >> 15) & 31 == 0 and (insn >> 7) & 31 == 6):
            pcs.add(c.pc)
    require(len(pcs) == 2, "Ambiguous compiled handler cause read PCs")
    return pcs


def scalar_qualified(result, rows):
    return (result.get("status") in ("TERMINAL_MATCH", "TERMINAL_TOHOST_MATCH") and
            result.get("mismatch") is None and result.get("stopped_at_unobservable") is None and
            result.get("skipped_unobservable_register_values") == 0 and
            result.get("ara_retired_instructions") == len(rows) and
            result.get("ara_committed_instructions") == sum(not r["trap"] for r in rows) and
            result.get("matched_instructions") == sum(not r["trap"] for r in rows))


def runtime(run, pre, scalar=None):
    symbols = pre["symbols"]
    elf = Path(pre["input_elf"])
    software.validate_elf_window(elf.read_bytes(), symbols)
    spike = software.shared.parse_spike_commits(Path(pre["input_spike_trace"]))
    require(software.validate(spike, symbols) ==
            {k: v for k, v in pre["spike_validation"].items() if k != "trap_distribution"}, "Sealed Spike oracle differs")
    rows = commit_rows(run / "commit_trace.csv")
    commits = retired_commits(rows)
    terminal = [(i, value) for i, c in enumerate(commits) for address, value in c.memory_accesses
                if address == symbols["tohost"] and value is not None]
    require(terminal == [(len(commits) - 1, 1)] and commits[0].pc == 0x80000000,
            "Non-complete/failed/multiple scalar terminal")
    observation = software.validate(commits, symbols)
    # Reuse the independent mathematical/signature oracle, not its Spike label.
    observation["status"] = "GAP100_DUT_OBSERVATION_CHECKS_PASS_NOT_SCALAR_QUALIFICATION"
    pcs = handler_read_pcs(spike)
    causes = handler_causes([c for c in commits if c.pc in pcs])
    zero.vector_zero(run / "vector_trace.csv")
    contract = zero.zero_contract(run / "run.vcs.log")
    if scalar is None:
        scalar = common.compare_commit_prefix(Path(pre["input_spike_trace"]), run / "commit_trace.csv", 0x80000000,
            terminal_tohost_address=symbols["tohost"], rvfi_store_data_layout="unshifted")
    vector = common.compare_vector_commits(Path(pre["input_spike_trace"]), run / "commit_trace.csv",
                                         run / "vector_trace.csv", 0x80000000)
    common.validate_vector(vector)
    require(vector["status"] == "UNOBSERVABLE", "Unexpected vector result in zero-data case")
    return dict(status="GAP100_RUNTIME_DIAGNOSTIC_NOT_ADMISSION", architecture=observation,
                handler_causes=causes, rvfi_trap_rows=sum(r["trap"] for r in rows),
                scalar=scalar, scalar_comparison_qualified=scalar_qualified(scalar, rows),
                vector=vector, vector_comparison_pass=False, contract=contract,
                normalization_performed=False, coverage_admitted=False,
                limitations=["Handler causes and final observations are not a complete independent trap/return proof.",
                             "Trap-marked RVFI rows are preserved; unmodified scalar comparator skips them.",
                             "Any scalar mismatch remains unqualified; no stuttering fallback is implemented."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    out = parser.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct diagnostic output required")
    manifest = runner.life.read_bound(RUN / "manifest.json", RUN_SEAL)
    require(runner.life.read_bound(RUN.with_name(RUN.name + ".prepared.json"), RUN_SEAL) == manifest and
            manifest["command"] == runner.command(RUN), "Prepared/live run identity differs")
    pre = runner.life.read_bound(runner.PRE / "preflight-manifest.json", runner.PRE_SEAL)
    runner.validate(pre)
    require(manifest["preflight"] == pre, "Oracle identity differs")
    pins = runner.life.merge_pins(manifest["pins"], {str(RUN / "manifest.json"): RUN_SEAL,
        str(RUN.with_name(RUN.name + ".prepared.json")): RUN_SEAL,
        str(runner.PRE / "preflight-manifest.json"): runner.PRE_SEAL})
    for path in (RUN / "simulation-status.json", RUN / "commit_trace.csv", RUN / "vector_trace.csv",
                 RUN / "run.vcs.log", Path(__file__).resolve(), Path(__file__).with_name("test_check_gap100_runtime.py"),
                 Path(zero.__file__).resolve(), Path(common.__file__).resolve()):
        pins = runner.life.merge_pins(pins, {str(path): runner.life.digest(path)})
    runner.life.check(pins)
    status = json.loads((RUN / "simulation-status.json").read_bytes())
    require(status.get("status") == "SIMULATION_EXITED_NOT_ADMITTED" and status.get("returncode") == 0,
            "Run not terminal-successful; no simulation retry")
    out.mkdir()
    try:
        scalar = common.compare_commit_prefix(Path(pre["input_spike_trace"]), RUN / "commit_trace.csv", 0x80000000,
            terminal_tohost_address=pre["symbols"]["tohost"], rvfi_store_data_layout="unshifted")
        save(out / "scalar-comparison.json", scalar)
        result = runtime(RUN, pre, scalar)
        runner.life.check(pins)
        save(out / "diagnostic.json", result)
        save(out / "input-pins.json", pins)
        print(json.dumps(dict(output=str(out), seal=runner.life.digest(out / "diagnostic.json"),
                              scalar_comparison_qualified=result["scalar_comparison_qualified"], coverage_admitted=False)))
    except Exception as error:
        save(out / "failure.json", dict(status="GAP100_DIAGNOSTIC_FAILED_NOT_ADMITTED", reason=str(error)))
        raise


if __name__ == "__main__":
    main()
