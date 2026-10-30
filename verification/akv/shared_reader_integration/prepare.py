#!/usr/bin/env python3
"""Create a fresh, pinned complete source closure with three mechanical overlays."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CANDIDATE = HERE.parent / "shared_reader_candidate"
MODULES = {
    "qbs": "hardware/src/vlsu/qbs/qbs_engine.sv",
    "akv": "hardware/src/vlsu/akv/akv_engine.sv",
    "vlsu": "hardware/src/vlsu/vlsu.sv",
}
READ_PORTS = {
    "range_ready_o": "range_ready", "data_valid_o": "data_valid", "data_o": "data",
    "data_strb_o": "data_strb", "data_offset_o": "data_offset", "data_tag_o": "data_tag",
    "completion_valid_o": "completion_valid", "completion_tag_o": "completion_tag",
    "fault_valid_o": "fault_valid", "fault_kind_o": "fault_kind", "fault_vaddr_o": "fault_vaddr",
    "fault_tag_o": "fault_tag", "fault_mmu_exception_o": "fault_mmu_exception",
    "range_count_o": "range_count", "translation_count_o": "translation_count",
    "ar_count_o": "ar_count", "r_beat_count_o": "r_beat_count",
    "payload_byte_count_o": "payload_byte_count", "store_wait_cycles_o": "store_wait_cycles",
    "r_backpressure_cycles_o": "r_backpressure_cycles",
    "outstanding_occupancy_sum_o": "outstanding_occupancy_sum",
    "outstanding_max_o": "outstanding_max", "outstanding_full_cycles_o": "outstanding_full_cycles",
    "busy_o": "busy",
}
REQ_PORTS = {f"{field}_i": field for field in (
    "range_valid", "range_vaddr", "range_bytes", "range_tag", "range_cache", "range_prot",
    "data_ready", "completion_ready", "fault_ready")}
PROBES = {
    "i_read_engine.plan_state_q": "reader_probe_plan_state_i",
    "i_read_engine.range_fifo_count_q": "reader_probe_range_count_i",
    "i_read_engine.burst_fifo_count_q": "reader_probe_burst_count_i",
    "axi_ar_valid_o": "reader_probe_ar_valid_i", "axi_ar_ready_i": "reader_probe_ar_ready_i",
    "axi_r_valid_i": "reader_probe_r_valid_i", "axi_r_ready_o": "reader_probe_r_ready_i",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Changed source anchor: {old[:90]!r}")
    return text.replace(old, new, 1)


def engine(text, kind):
    text = once(text, "    parameter type         exception_t = logic",
                "    parameter type         reader_req_t = logic,\n"
                "    parameter type         reader_rsp_t = logic,\n"
                "    parameter type         exception_t = logic")
    start = text.index("    input  logic                         core_st_pending_i,")
    end = text.index("    output logic [NrLanes-1:0]", start)
    ports = "    output reader_req_t reader_req_o,\n    input reader_rsp_t reader_rsp_i,\n"
    if kind == "qbs":
        ports += "`ifndef SYNTHESIS\n"
        for name in PROBES.values():
            width = "[1:0] " if name.endswith(("state_i", "count_i")) else ""
            ports += f"    input logic {width}{name},\n"
        ports += "`endif\n"
    text = text[:start] + ports + "\n" + text[end:]
    start = text.index("  qbs_read_engine #(\n")
    end = text.index("\n  );", start) + len("\n  );")
    old = text[start:end]
    connection = dict(re.findall(r"\.(\w+)\s*\((\w+)\)", old))
    lines = ["  // Reader state now lives once in VLSU; client scheduling is unchanged.",
             "  assign reader_req_o = '{"]
    for port, field in REQ_PORTS.items():
        expr = connection[port]
        if field == "range_tag":
            expr = "{8'b0, read_range_tag}" if kind == "akv" else "16'(read_range_tag)"
        lines.append(f"    {field}: {expr},")
    lines[-1] = lines[-1].removesuffix(",")
    lines.append("  };")
    for port, field in READ_PORTS.items():
        expr = f"reader_rsp_i.{field}"
        if field in ("data_tag", "completion_tag", "fault_tag"):
            expr = f"{kind}_range_tag_t'({expr}" + ("[7:0])" if kind == "akv" else ")")
        lines.append(f"  assign {connection[port]} = {expr};")
    lines += ["`ifndef SYNTHESIS", f"  initial assert ($bits({kind}_range_tag_t) == {8 if kind == 'akv' else 16})",
              '    else $fatal(1, "SHARED_CLIENT_TAG_WIDTH");', "`endif"]
    text = text[:start] + "\n".join(lines) + text[end:]
    if kind == "qbs":
        for old, new in PROBES.items():
            if old not in text:
                raise ValueError(f"Missing probe {old}")
            text = text.replace(old, new)
    if "i_read_engine" in text or "qbs_read_engine #(" in text:
        raise ValueError("Reader was not completely extracted")
    return text


def vlsu(text):
    text = once(text, "  logic normal_vlsu_idle;",
                '  `include "vlsu_shared_reader.svh"\n\n  logic normal_vlsu_idle;')
    for index, kind in enumerate(("qbs", "akv")):
        start = text.index(f"  {kind}_engine #(\n")
        end = text.index("\n  );", start) + len("\n  );")
        block = text[start:end]
        block = once(block, f"  {kind}_engine #(\n", f"  {kind}_engine #(\n"
                     "    .reader_req_t(shared_read_req_t), .reader_rsp_t(shared_read_rsp_t),\n")
        a = block.index("    .core_st_pending_i,")
        b = block.index("    .ldu_result_req_o", a)
        ports = (f"    .reader_req_o(shared_read_req[{index}]),\n"
                 f"    .reader_rsp_i(shared_read_rsp[{index}]),\n")
        if kind == "qbs":
            ports += "`ifndef SYNTHESIS\n"
            for old, new in PROBES.items():
                expr = "i_shared_reader." + old if old.startswith("i_read_engine.") else {
                    "axi_ar_valid_o": "qbs_axi_ar_valid", "axi_ar_ready_i": "qbs_axi_ar_ready",
                    "axi_r_valid_i": "qbs_axi_r_valid", "axi_r_ready_o": "qbs_axi_r_ready"}[old]
                ports += f"    .{new}({expr}),\n"
            ports += "`endif\n"
        block = block[:a] + ports + block[b:]
        text = text[:start] + block + text[end:]
    text = once(text,
        "  assign qbs_physical_range_allowed = qbs_range_is_cacheable_idempotent(\n"
        "      qbs_physical_check_addr, qbs_physical_check_bytes);\n"
        "  assign akv_physical_range_allowed = qbs_range_is_cacheable_idempotent(\n"
        "      akv_physical_check_addr, akv_physical_check_bytes);",
        "  assign qbs_physical_range_allowed = shared_physical_range_allowed;\n"
        "  assign akv_physical_range_allowed = shared_physical_range_allowed;")
    text = text.replace("i_qbs_engine.i_read_engine.", "i_shared_reader.i_read_engine.")
    return once(text, "endmodule", '  `include "admission_assertions.svh"\nendmodule')


def compile_lines(lines, source_root):
    """Exclude SoC TB $unit exports/binds, not production modules or defines."""
    kept, omitted = [], []
    roots = [source_root / "hardware/tb", source_root / "verification/uvm"]
    for line in lines:
        token = line.strip()
        if token.startswith("/") and any(Path(token).is_relative_to(p) for p in roots):
            omitted.append(token)
        else:
            kept.append(line)
    return kept, omitted


def prepare(manifest, output):
    receipt = json.loads(manifest.read_text())
    originals = {row["path"]: row["sha256"] for row in receipt["files"]}
    if receipt["repo_root"] != str(ROOT) or len(originals) != len(receipt["files"]):
        raise ValueError("Wrong root or duplicate source pins")
    for path, sha in originals.items():
        if digest(path) != sha:
            raise ValueError(f"Accepted image source drift: {path}")
    candidate_receipt = ROOT / "verification/out/qbs-akv-shared-reader-unit-20261024-03/source-pins.json"
    candidate_pins = json.loads(candidate_receipt.read_text())
    additions = [CANDIDATE / "qbs_akv_shared_reader.sv", CANDIDATE / "shared_reader_types.svh"]
    for path in additions:
        if digest(path) != candidate_pins[str(path)]:
            raise ValueError(f"Accepted candidate drift: {path}")
    extra = [*additions, *HERE.glob("*.py"), *HERE.glob("*.sv"), *HERE.glob("*.svh"),
             HERE / "README.md", manifest, candidate_receipt]
    inputs = {**originals, **{str(p): digest(p) for p in extra}}
    output.mkdir(parents=True, exist_ok=False)
    mapping = {}
    # Preserve paths and copy bytes (never symlink). Includes and unchanged source
    # modules come from this complete closure, not a mutable canonical tree.
    for source in originals:
        path = Path(source)
        relative = path.relative_to(ROOT)
        dest = output / "source" / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
        mapping[source] = str(dest)
    patches = []
    for kind, relative in MODULES.items():
        original = ROOT / relative
        dest = Path(mapping[str(original)])
        before = original.read_text()
        after = vlsu(before) if kind == "vlsu" else engine(before, kind)
        dest.write_text(after)
        patches.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                           fromfile=relative, tofile="overlay/" + relative))
    support = output / "support"
    support.mkdir()
    for path in [*additions, HERE / "vlsu_shared_reader.svh", HERE / "compile_top.sv",
                 HERE / "admission_assertions.svh"]:
        (support / path.name).write_bytes(path.read_bytes())
    original_filelist = Path(receipt["filelist"])
    lines = ["+incdir+" + str(support)]
    for raw in original_filelist.read_text().splitlines():
        token = raw.strip()
        if token.startswith("+incdir+"):
            path = Path(token[len("+incdir+"):])
            lines.append("+incdir+" + str(output / "source" / path.relative_to(ROOT)))
        elif token in mapping:
            lines.append(mapping[token])
            if token == str(ROOT / "hardware/src/vlsu/qbs/qbs_read_engine.sv"):
                lines.append(str(support / "qbs_akv_shared_reader.sv"))
        elif not token or token.startswith(("+define+", "//")):
            lines.append(raw)
        else:
            raise ValueError(f"Unrecognized filelist entry: {token}")
    filelist = output / "sources.f"
    filelist.write_text("\n".join(lines) + "\n")
    compile_filelist = output / "vlsu_sources.f"
    filtered, omitted = compile_lines(lines, output / "source")
    compile_filelist.write_text("\n".join(filtered) + "\n")
    (output / "overlay.patch").write_text("".join(patches))
    for path, sha in inputs.items():
        if digest(path) != sha:
            raise ValueError(f"Input drift during snapshot: {path}")
    artifacts = {str(p): digest(p) for p in output.rglob("*") if p.is_file()}
    result = {"state": "PREPARED_NOT_COMPILED", "input_pins": inputs,
              "source_mapping": mapping, "overlay_modules": list(MODULES.values()),
              "artifact_pins": artifacts, "filelist": str(filelist),
              "compile_filelist": str(compile_filelist), "compile_omitted": omitted,
              "top": str(support / "compile_top.sv"),
              "baseline_manifest": str(manifest), "candidate_receipt": str(candidate_receipt),
              "scope": "Complete production source closure, no CPU/SoC elaboration or simulation yet"}
    (output / "manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.manifest.resolve(), args.output.resolve())
    print(json.dumps({"state": result["state"], "sources": len(result["source_mapping"]),
                      "output": str(args.output.resolve())}))
