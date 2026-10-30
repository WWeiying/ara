#!/usr/bin/env python3
"""One bounded 71-command handoff run on a checked shared-reader SoC image."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "reader_handoff"))
spec = importlib.util.spec_from_file_location("shared_baseline_handoff", HERE.parent / "reader_handoff/run.py")
baseline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = baseline
spec.loader.exec_module(baseline)
s, Execution = baseline.s, baseline.Execution
import check_reader_handoff_v2 as log_checker

SIM_TIMEOUT_SECONDS = 600


def validate_timeout(timeout):
    s.require(type(timeout) is int and 1 <= timeout <= SIM_TIMEOUT_SECONDS,
              "Integrated handoff wall bound must be 1..600 seconds")


def checked_soc(directory):
    report = s.read_json(directory / "result.json")
    status = s.read_json(directory / "status.json")
    s.require(report.get("state") == status.get("state") == "SOC_BUILT_NOT_EXECUTED" and
              status.get("child_pid") is None and report.get("post_pins_match") is True,
              "Need terminal checked shared-reader SoC build")
    source = directory / "source-pins.json"
    s.require(s.digest(source) == report["source_pins_sha256"], "Build input receipt drift")
    pins = s.read_json(source)
    s.merge_pins(pins, report["artifact_pins"])
    snapshot_manifest = Path(report["snapshot_manifest"])
    s.require(s.digest(snapshot_manifest) == report["snapshot_sha256"], "Snapshot receipt drift")
    snapshot = s.read_json(snapshot_manifest)
    s.merge_pins(pins, snapshot["input_pins"])
    s.merge_pins(pins, snapshot["artifact_pins"])
    simv = Path(report["simv"])
    s.require(simv == directory / "sim/simv", "Wrong image path")
    image = s.hashes(s.image_files(simv))
    s.require(all(pins.get(k) == v for k, v in image.items()), "Image inventory not sealed by build")
    s.merge_pins(pins, s.hashes([directory / "result.json", directory / "status.json", source]))
    s.verify_pins(pins)
    return report, snapshot, pins, image


def run(args):
    # Parent owns these two modules; imports occur before inventory capture.
    from shared_wave import profile, script
    from sharedwave_checker import check_cycles
    validate_timeout(args.timeout)
    build = args.soc_build.resolve(strict=True)
    fixture = args.fixture_build.resolve(strict=True)
    out = args.output.resolve()
    s.require(not out.is_relative_to(build) and not out.is_relative_to(fixture), "Use fresh independent output")
    out.mkdir(parents=True, exist_ok=False)
    work = out / "work"
    work.mkdir()
    owner = Execution(out)
    owner.state.update(soc_build=str(build), fixture_build=str(fixture), performance=False)
    owner.save()
    try:
        soc, snapshot, pins, image = checked_soc(build)
        original, fixture_pins = baseline.checked_build(fixture)
        s.merge_pins(pins, fixture_pins)
        elf = Path(original["elf"])
        simv = Path(soc["simv"])
        s.require(original["qbs_commands"] == 6 and original["akv_commands"] == 65,
                  "Wrong original handoff fixture")
        exporter = ROOT / "hardware/scripts/fsdb_trace/extract_cycles.py"
        tool_pins = s.hashes(baseline.exporter_files(args.fsdbreport))
        own = [Path(__file__), HERE / "test_run_handoff.py", HERE / "shared_wave.py",
               HERE / "sharedwave_checker.py", Path(log_checker.__file__).resolve(),
               HERE.parent / "reader_handoff/test_check_reader_handoff_v2.py",
               exporter, *s.script_files(), Path(sys.executable).resolve()]
        own.extend(HERE.glob("test_shared*.py"))
        for module in tuple(sys.modules.values()):
            filename = getattr(module, "__file__", None)
            if filename:
                path = Path(filename).resolve()
                if path.is_relative_to(ROOT) and path.is_file():
                    own.append(path)
        s.merge_pins(pins, s.hashes(own))
        s.merge_pins(pins, tool_pins)
        capture = profile()
        s.atomic_json(out / "profile.json", capture)
        (out / "probe.tcl").write_text(script(500000))
        s.merge_pins(pins, s.hashes([out / "profile.json", out / "probe.tcl"]))
        s.atomic_json(out / "source-pins.json", pins)
        receipt = s.digest(out / "source-pins.json")
        owner.state.update(simv=str(simv), elf=str(elf), source_pins_sha256=receipt)
        owner.save()

        def identity():
            s.require(s.digest(out / "source-pins.json") == receipt, "Worker receipt drift")
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, "New image inventory drift")
            s.require(s.hashes(baseline.exporter_files(args.fsdbreport)) == tool_pins,
                      "Exporter implementation inventory drift")
            s.require(profile() == capture and (out / "probe.tcl").read_text() == script(500000),
                      "Shared capture profile drift")

        def manifest(stage):
            owner.execute([sys.executable, "-B", "-m", "ara_verify.vcs_source_manifest", "--output",
                           simv.parent / "vcs_source_manifest.json", "--check"],
                          out / (stage + ".log"), 300, stage.upper())

        identity()
        manifest("manifest-before")
        owner.execute(["bash", ROOT / "hardware/scripts/llama_q4km_extract/check-sim-l2.sh",
                       simv.parent, elf], out / "image-contract.log", 180, "IMAGE_CONTRACT")
        identity()
        log, trace = work / "run.vcs.log", work / "vector_trace.csv"
        owner.execute([simv, "-no_save", "-ucli", "-do", out / "probe.tcl", "-l", log,
                       "+PRELOAD=" + str(elf), "+TESTCASE=reader_handoff_shared",
                       "+NO_FSDB", "+NO_INSTR_TRACE", "+QBS_PERF", "+AKV_PERF",
                       "+VECTOR_TRACE=" + str(trace), "+ARA_CONTRACT_TRACE_LIMIT=2000000",
                       "+ARA_UVM_TRACE_LIMIT=2000000"], work / "console.log", args.timeout, "RUNNING")
        overlay = Path(snapshot["source_mapping"][str(ROOT / "hardware/src/vlsu/vlsu.sv")])
        parsed = log_checker.check_log(log.read_text(), overlay.read_text())
        owner.execute([sys.executable, "-B", exporter, "--fsdb", work / "reader.fsdb",
                       "--profile", out / "profile.json", "--begin", "0ns", "--end", "500000ns",
                       "--output", out / "cycles", "--fsdbreport", args.fsdbreport],
                      out / "extract.log", 180, "EXTRACTING")
        metadata = s.read_json(out / "cycles/metadata.json")
        s.require(metadata.get("edge") == "negedge" and metadata.get("cycle_count", 0) > 10 and
                  set(metadata.get("present_signals", [])) == {r["alias"] for r in capture["signals"]} and
                  not metadata.get("missing_signals", []), "Incomplete shared-reader capture")
        waves = check_cycles(out / "cycles/cycles.csv")
        s.require(waves.get("state") == "SHARED_READER_HANDOFF_WAVE_CHECKED" and
                  waves.get("physical_readers_observed") == 1 and waves.get("zero_read_commands") == 63 and
                  len(waves.get("fires", [])) == len(waves.get("terminals", [])) == 71,
                  "Wrong shared-reader proof")
        owner.execute([sys.executable, "-B", "-m", "ara_verify.uvm_dut", "--require-events", "--require-backend",
                       "--require-axi", "--require-axi-write", "--vector-trace", trace, "--log", log,
                       "--simv", simv, "--elf", elf, "--output", work / "uvm_result.json"],
                      work / "checker.log", 600, "CHECKING")
        s.check_result(work / "uvm_result.json", original["elf_sha256"], image)
        uvm = s.read_json(work / "uvm_result.json")
        s.require(uvm["log_sha256"] == s.digest(log) and uvm["vector_trace_sha256"] == s.digest(trace),
                  "Protocol evidence drift")
        manifest("manifest-after")
        identity()
        parsed.update(state="PASS", wave_evidence=waves, post_pins_match=True, simulator_exit_code=0,
                      independent_protocol_checked=True, source_pins_sha256=receipt,
                      elf_sha256=original["elf_sha256"], snapshot_sha256=soc["snapshot_sha256"],
                      evidence_sha256=s.hashes([log, trace, work / "reader.fsdb", work / "uvm_result.json",
                          out / "source-pins.json", out / "profile.json", out / "probe.tcl",
                          out / "cycles/cycles.csv", out / "cycles/metadata.json", out / "cycles/fsdbreport.raw.csv",
                          out / "extract.log", out / "image-contract.log", out / "manifest-before.log",
                          out / "manifest-after.log"]))
        s.atomic_json(out / "result.json", parsed)
        owner.state["state"] = "PASS"
    except BaseException as exc:
        state = "TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired) else "FAIL"
        owner.state.update(state=state, error=repr(exc))
        s.atomic_json(out / "result.json", dict(state=state, error=repr(exc)))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soc-build", type=Path, required=True)
    parser.add_argument("--fixture-build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=SIM_TIMEOUT_SECONDS)
    parser.add_argument("--fsdbreport", type=Path, default=Path(
        "/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport"))
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f"Signal {sig}")

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
