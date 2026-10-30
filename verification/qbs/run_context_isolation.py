#!/usr/bin/env python3
"""Run distinct-data DIRECT isolation without editing a sealed engine bench.

Derive a private successor bench from a pinned projection campaign. Resident
input rows 0..3 and intervening DIRECT rows 4..7 share the same real weights;
the existing context suite then checks resident results after external memory
is poisoned, including fault/retry and release. This is not a performance test.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal

from run_half_scale_soc import atomic_json, digest, hashes
from run_tile_context_engine import check_geometry, check_log, run_command

ROOT = Path(__file__).resolve().parents[2]
START = "        // A DIRECT command may use the datapath but must not replace the saved tile.\n"
END = "        // REUSE must not depend on the original bytes after a committed FILL.\n"


def projection_pins(baseline):
    pinned = json.loads((baseline / "status.json").read_text())["sources_and_inputs"]
    for leaf in ("inputs0.vectors", "inputs4.vectors"):
        if str((baseline / leaf).resolve(strict=True)) not in pinned:
            raise ValueError("Projection manifest has not sealed " + leaf)
    if any(digest(Path(path)) != sha for path, sha in pinned.items()):
        raise RuntimeError("Sealed projection source/input/image drift")
    return pinned


def first_tile(text):
    if not text.startswith("QBSCMD1 28\n"):
        raise ValueError("Expected full real projection vectors")
    blocks = re.findall(r"^CMD .*?^END$", text, re.M | re.S)
    if len(blocks) != 28:
        raise ValueError("Incomplete projection")
    block = blocks[0]
    header = block.splitlines()[0].split()
    if header[:8] != ["CMD", "0", "6", "2", "2", "4", "32", "28"]:
        raise ValueError("Expected Q8_0 M4/N32/K896 interleaved geometry")
    flags = int(header[8], 16)
    activations, outputs, weights = {}, {}, []
    tile_k = None
    for line in block.splitlines()[1:]:
        fields = line.split()
        if fields[0] == "T":
            tile_k = int(fields[1])
            if not 0 <= tile_k < 28:
                raise ValueError("Bad K block")
        elif fields[0] == "A":
            ctx, offset, strobe, data = (int(fields[1]), int(fields[2]),
                                         int(fields[3], 16), int(fields[4], 16))
            if tile_k is None or ctx != 0 or offset < 0 or offset % 16:
                raise ValueError("Bad interleaved beat")
            for byte in range(16):
                if strobe & (1 << byte):
                    if offset + byte >= 136:
                        raise ValueError("Beat exceeds activation block")
                    index = tile_k * 136 + offset + byte
                    value = (data >> (8 * byte)) & 255
                    if index in activations and activations[index] != value:
                        raise ValueError("Conflicting activation records")
                    activations[index] = value
        elif fields[0] == "W":
            weights.append((tile_k, *fields[1:]))
        elif fields[0] == "O":
            index, value = int(fields[1]), int(fields[2], 16)
            if index in outputs:
                raise ValueError("Duplicate expected output")
            outputs[index] = value
    if set(activations) != set(range(3808)) or set(outputs) != set(range(128)):
        raise ValueError("Incomplete activation or output coverage")
    return dict(vector="QBSCMD1 1\n" + block + "\n", flags=flags,
                activations=activations, outputs=outputs, weights=weights)


def successor(source, resident, direct):
    if source.count(START) != 1 or source.count(END) != 1:
        raise ValueError("Sealed bench isolation boundary changed")
    if resident["weights"] != direct["weights"] or not resident["weights"]:
        raise ValueError("Isolation requires identical nonempty weights")
    changed_bytes = sum(resident["activations"][i] != value
                        for i, value in direct["activations"].items())
    changed_outputs = sum(resident["outputs"][i] != value
                          for i, value in direct["outputs"].items())
    if not changed_bytes or not changed_outputs:
        raise ValueError("Isolation inputs and outputs must differ")
    assignments = "\n".join(
        f"          memory[longint'(activation_base + {index})] = 8'h{value:02x};"
        for index, value in sorted(direct["activations"].items()))
    assignments += "\n" + "\n".join(
        f"          expected_output[{index}] = 32'h{value:08x};"
        for index, value in sorted(direct["outputs"].items()))
    replacement = f"""        // Private successor: a distinct real DIRECT input must not replace A.
        begin
          logic [31:0] saved_output [128];
          integer saved_flags;
          for (int index = 0; index < 128; index++)
            saved_output[index] = expected_output[index];
          saved_flags = expected_flags;
{assignments}
          expected_flags = 5'h{direct['flags']:02x};
          memory_epoch++;
          install_descriptor(descriptor_base, weight_base, QbsDescriptorVersion,
                             profile, weight_layout, activation_layout, n, k_blocks);
          reset_scoreboard();
          send_command(score_id, score_vd, m, descriptor_base, activation_base);
          wait_success(104);
          if (result_fflags !== expected_flags[4:0] || unexpected_write_count != 0 ||
              commit_aggregate_words != context_commit_words ||
              context_fill_count != 0 || context_reuse_count != 0 ||
              context_read_bytes != 0 || activation_axi_bytes_saved != 0 ||
              read_payload_bytes != QbsDescriptorBytes + expected_weight_bytes + expected_activation_bytes ||
              dut.i_activation_context.context_valid_q !== 1'b1 ||
              dut.i_activation_context.context_generation_q !== context_generation[7:0])
            $fatal(1, "Distinct DIRECT result/traffic/context mismatch");
          acknowledge_terminal();
          for (int index = 0; index < 128; index++)
            expected_output[index] = saved_output[index];
          expected_flags = saved_flags;
          $display("QBS distinct DIRECT PASS changed_bytes={changed_bytes} changed_outputs={changed_outputs}");
        end
"""
    prefix, rest = source.split(START)
    _, suffix = rest.split(END)
    return prefix + replacement + END + suffix, (changed_bytes, changed_outputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = args.projection.resolve(strict=True)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pinned = projection_pins(baseline)
    pinned.update(hashes([Path(__file__).resolve()]))
    state = dict(state="preparing", pid=os.getpid(), scope=__doc__, pins=pinned)
    def save():
        atomic_json(out / "status.json", state)
    def unchanged():
        if any(digest(Path(path)) != sha for path, sha in pinned.items()):
            raise RuntimeError("Source/input/image drift")
    def run(argv, log, timeout):
        def started(pid):
            state.update(child_pid=pid, command=list(map(str, argv)), log=str(log))
            save()
        try:
            code = run_command(list(map(str, argv)), log, timeout, os.environ.copy(), started)
            if code:
                raise RuntimeError("Command failed: " + str(log))
        finally:
            state["child_pid"] = None
            save()
    def interrupted(signum, _frame):
        raise InterruptedError(f"worker received signal {signum}")
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    save()
    try:
        unchanged()
        resident = first_tile((baseline / "inputs0.vectors").read_text())
        direct = first_tile((baseline / "inputs4.vectors").read_text())
        source, changes = successor((ROOT / "verification/qbs/qbs_engine_tb.sv").read_text(),
                                    resident, direct)
        bench = out / "qbs_engine_tb_isolation.sv"
        bench.write_text(source)
        vector = out / "resident.vectors"
        vector.write_text(resident["vector"])
        pinned.update(hashes([bench, vector]))
        state.update(state="building", changed_bytes=changes[0], changed_outputs=changes[1])
        run(["make", "-C", ROOT / "verification/qbs", "rtl-engine-compile",
             f"RTL_ENGINE_BUILD={out / 'engine'}",
             "RTL_ENGINE_SOURCES=$(RTL_SOURCES) " + str(bench)], out / "compile.log", 300)
        unchanged()
        image = out / "engine/simv"
        libraries = list((out / "engine/simv.daidir").rglob("*.so"))
        if not libraries:
            raise RuntimeError("No fresh VCS libraries")
        pinned.update(hashes([image, *libraries, out / "engine/compile.log"]))
        state["state"] = "running"
        run([image, "-no_save", "-l", out / "run.log", "+QBS_FUNCTIONAL_ONLY",
             "+QBS_CONTEXT_SUITE", f"+QBS_COMMAND_VECTOR_FILE={vector}"],
            out / "console.log", 600)
        text = (out / "run.log").read_text()
        result = check_log(text, 1, 1, 0)
        check_geometry(resident["vector"], result["direct"])
        marker = f"QBS distinct DIRECT PASS changed_bytes={changes[0]} changed_outputs={changes[1]}\n"
        if text.count(marker) != 1:
            raise RuntimeError("Missing unique distinct-input DIRECT result")
        unchanged()
        state.update(state="PASS", result=result, log_sha256=digest(out / "run.log"))
    except BaseException as error:
        state.update(state="INTERRUPTED" if isinstance(error, (KeyboardInterrupt, InterruptedError))
                     else "FAIL", error=repr(error))
        raise
    finally:
        save()


if __name__ == "__main__":
    main()
