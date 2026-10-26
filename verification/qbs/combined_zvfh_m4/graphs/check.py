"""Combined-Zvfh successor: Q8_K opt-in traces; unchanged untraced Q8_0 Zvfh path."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import check_ggml_tile_context as tile


def check_group(text, prepare):
    clean, graph, run, count, lifetimes = [], None, None, 0, []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("QBS_TILE_RUN_BEGIN "):
            fields = tile._fields(line, "run context wide threads".split())
            run = tile._int(fields, "run")
            tile._require(run < len(tile.RUNS), "Unexpected run")
        elif line.startswith("QBS_TILE_GRAPH_BEGIN "):
            tile._require(graph is None and run is not None, "Invalid graph nesting")
            fields = tile._fields(line, "case type m n k_blocks threads epoch".split())
            case = tile._int(fields, "case")
            tile._require(case < len(tile.SHAPES), "Invalid case")
            shape = tile.SHAPES[case]
            wide = tile._wide_selected(shape, tile.RUNS[run][1])
            graph = dict(expected=shape.m // 4 if shape.kind == "q4_K" and not wide else 0,
                         seen=0, k=shape.blocks * shape.elements)
        elif "GGML_RISCV_QBS_M4_PREPARE" in line:
            raise ValueError("Q8_0 must retain its untraced combined-Zvfh path")
        elif line.startswith("GGML_RISCV_QBS_Q8K_M4_PREPARE"):
            tile._require(graph is not None and line.split()[0] == "GGML_RISCV_QBS_Q8K_M4_PREPARE",
                          "Preparation outside graph or malformed tag")
            fields = tile._fields(line, "enabled path k".split())
            tile._require(tile._int(fields, "enabled") == prepare and
                          fields["path"] == ("rvv" if prepare else "generic") and
                          tile._int(fields, "k") == graph["k"], "Q8_K selection mismatch")
            graph["seen"] += 1
            count += 1
            continue
        elif line.startswith("GGML_RISCV_QBS_LIFETIME "):
            fields = tile._fields(line, tile.LIFETIME_FIELDS, extra=True)
            lifetimes.append(tile._digest(fields["digest"]))
        elif line.startswith("QBS_TILE_GRAPH_PASS "):
            tile._require(graph is not None and graph["seen"] == graph["expected"],
                          "Wrong Q8_K preparation call count")
            graph = None
        clean.append(raw)
    tile._require(graph is None and count == 52, "No completed Q8_K selection evidence")
    report = tile.check_output("\n".join(clean))
    report["q8k_prepare_calls"] = count
    report["activation_digests"] = lifetimes
    report["q8_0_graphs"] = 132
    report["q8_0_optin_traces"] = 0
    return report


def check_output(text):
    tile._require(tile.FAILURE.search(text) is None, "Guest failure")
    groups, lines, active, done = [], [], False, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Q8K_GRAPH_GROUP_BEGIN"):
            tile._require(not active and not done and len(groups) < 2 and
                          line == f"Q8K_GRAPH_GROUP_BEGIN prepare={len(groups)}", "Invalid group BEGIN")
            active, lines = True, []
        elif line.startswith("Q8K_GRAPH_GROUP_END"):
            tile._require(active and line == f"Q8K_GRAPH_GROUP_END prepare={len(groups)} exit=0",
                          "Failed/incomplete graph group")
            groups.append(check_group("\n".join(lines), len(groups)))
            active = False
        elif line.startswith("Q8K_GRAPH_GUEST_EXIT"):
            tile._require(not active and not done and len(groups) == 2 and
                          line == "Q8K_GRAPH_GUEST_EXIT=0", "Failed/incomplete guest")
            done = True
        elif "Q8K_GRAPH_" in line:
            raise ValueError("Unknown/malformed graph group protocol")
        elif active:
            lines.append(raw)
        elif any(tag in line for tag in ("QBS_TILE_", "GGML_RISCV_QBS_", "GUEST_TEST_EXIT", "Q8K_GRAPH_")):
            raise ValueError("Protocol outside graph group")
    tile._require(done and not active and len(groups) == 2, "Truncated output")
    for off, on in zip(groups[0]["runs"], groups[1]["runs"]):
        tile._require(off["digests"] == on["digests"], "Preparation changed graph outputs")
    tile._require(groups[0]["activation_digests"] == groups[1]["activation_digests"],
                  "Preparation changed packed activation digests")
    tile._require(groups[0]["q8k_prepare_calls"] == groups[1]["q8k_prepare_calls"],
                  "Q8_K preparation work changed")
    return dict(state="PASS", graphs=sum(g["graphs"] for g in groups),
                q8k_calls_per_mode=groups[0]["q8k_prepare_calls"], groups=groups,
                q8_0_graphs=264, q8_0_path="existing_zvfh_no_optin_trace",
                scope="Combined-Zvfh full-GGML QEMU functional gate; not RTL performance")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check.py SERIAL_LOG")
    print(json.dumps(check_output(Path(sys.argv[1]).read_text()), indent=2))
