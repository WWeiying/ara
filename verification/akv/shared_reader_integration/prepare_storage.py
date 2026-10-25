#!/usr/bin/env python3
"""Fresh shared-reader + unified-storage overlay; never modify an older snapshot."""
import argparse
import difflib
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import prepare as reader

HERE, ROOT = reader.HERE, reader.ROOT
STORAGE = HERE.parent / "unified_storage_candidate"
VARIANT = "shared_reader_unified_q2_kv32_v1"
SUPPORT = [STORAGE / "akv_q_store.sv", STORAGE / "akv_unified_context.sv",
           HERE.parent / "storage_adapter/akv_legacy_repacker.sv"]
UNIT_ROOTS = {kind: ROOT / f"verification/out/akv-unified-storage-unit-{kind}-20261025-01"
              for kind in ("tc", "macro")}


def verify(pins):
    if not pins:
        raise ValueError("Missing pins")
    for path, expected in pins.items():
        if reader.digest(path) != expected:
            raise ValueError("Input drift: " + str(path))


def merge_pins(*identities):
    result = {}
    for identity in identities:
        for path, value in identity.items():
            if path in result and result[path] != value:
                raise ValueError("Conflicting pin: " + path)
            result[path] = value
    return result


def instance(text, module, name):
    start = f"  {module} {name} (\n"
    if text.count(start) != 1:
        raise ValueError("Ambiguous storage instance: " + start)
    first = text.index(start)
    last = text.index("\n  );", first) + len("\n  );")
    block = text[first:last]
    # Named frozen SV connections; balance casts/parentheses without interpreting
    # expressions. Only clock/reset may use implicit shorthand connections.
    ports = {}
    for match in re.finditer(r"^\s*\.(\w+)\s*", block, re.M):
        name, pos = match.group(1), match.end()
        if block[pos] == "," and name in ("clk_i", "rst_ni"):
            continue
        if block[pos] != "(" or name in ports:
            raise ValueError("Changed storage connection grammar")
        first_expr, depth = pos + 1, 1
        while depth and pos + 1 < len(block):
            pos += 1
            depth += (block[pos] == "(") - (block[pos] == ")")
        if depth:
            raise ValueError("Unbalanced storage connection")
        ports[name] = block[first_expr:pos].strip()
    if block.count("    .clk_i,") != 1 or block.count("    .rst_ni,") != 1:
        raise ValueError("Changed storage clock/reset")
    return first, last, ports


LEGACY_PORTS = {name: "legacy_" + name for name in (
    "write_valid_i", "write_slot_i", "write_offset_i", "write_data_i", "write_strb_i",
    "write_busy_o", "replay_read_i", "replay_slot_i", "replay_word_i", "replay_data_o")}
V2_PORTS = {name: "v2_" + name for name in (
    "write_valid_i", "write_stream_i", "write_token_i", "write_offset_i", "write_data_i",
    "write_strb_i", "write_busy_o", "row_read_i", "row_stream_i", "row_token_i",
    "row_word_i", "row_data_o")}
V2_PORTS.update({name: name for name in (
    "column_start_i", "column_stream_i", "column_dimension_i", "column_count_i",
    "column_token_count_i", "column_busy_o", "column_valid_o", "column_data_o",
    "column_bank_cycle_o", "conflict_o")})
BUSY_ASSIGN = "  assign context_write_busy =\n      v1_context_write_busy || v2_context_write_busy;\n\n"


def transform_engine(text):
    a, b, legacy = instance(text, "akv_context", "i_context")
    c, d, v2 = instance(text, "akv_v2_context", "i_v2_context")
    if set(legacy) != set(LEGACY_PORTS) or set(v2) != set(V2_PORTS) or text[b:c] != "\n\n":
        raise ValueError("Storage port/adjacency contract changed")
    if not text[:a].endswith(BUSY_ASSIGN) or text.count(BUSY_ASSIGN) != 1:
        raise ValueError("Storage busy assignment changed")
    for anchor in ("  assign payload_row_bytes = context_head_dim_q << 1;",
                   "          context_head_dim_q <= descriptor.head_dim;",
                   "      if (read_fault_valid && read_fault_ready) begin"):
        if text.count(anchor) != 1:
            raise ValueError("Changed head dimension/fault contract")
    lines = ["  // Unified payload only; command, metadata, replay and fault FSM are unchanged.",
             "  akv_unified_context i_unified_context (", "    .clk_i,", "    .rst_ni,",
             "    .abort_i(read_fault_valid && read_fault_ready),",
             "    .legacy_row_bytes_i(9'(payload_row_bytes)),",
             "    .write_busy_o(context_write_busy),"]
    for old_ports, rename in ((legacy, LEGACY_PORTS), (v2, V2_PORTS)):
        for old, new in rename.items():
            lines.append(f"    .{new}({old_ports[old]}),")
    lines[-1] = lines[-1].removesuffix(",")
    lines.append("  );")
    return text[:a - len(BUSY_ASSIGN)] + "\n".join(lines) + text[d:]


def accepted_units():
    spec = importlib.util.spec_from_file_location("accepted_storage_unit", STORAGE / "run_unit.py")
    unit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(unit)
    identities, receipts = [], {}
    for kind, out in UNIT_ROOTS.items():
        manifest_path, result_path = out / "manifest.json", out / "result.json"
        manifest = json.loads(manifest_path.read_text())
        result = json.loads(result_path.read_text())
        if (result.get("state") != "PASS" or result.get("post_pins_match") is not True or
                result.get("sram") != kind or manifest.get("sram") != kind or
                result.get("counts") != unit.EXPECTED or
                result.get("manifest_sha256") != reader.digest(manifest_path)):
            raise ValueError("Storage unit is not the accepted profile: " + kind)
        evidence = result["evidence"]
        for name in ("manifest.json", "compile.log", "unit.log", "simv", "compile.command.json",
                     "compile.exit.json", "unit.command.json", "unit.exit.json"):
            if evidence.get(str(out / name)) != reader.digest(out / name):
                raise ValueError("Missing/drifted consumed unit evidence: " + name)
        for name in ("compile.exit.json", "unit.exit.json"):
            if json.loads((out / name).read_text()) != {"exit_code": 0}:
                raise ValueError("Nonzero unit exit")
        unit.check_log((out / "unit.log").read_text(), 0)
        for source in [*SUPPORT, STORAGE / "run_unit.py"]:
            if manifest["source_pins"].get(str(source)) != reader.digest(source):
                raise ValueError("Accepted unit does not pin current source: " + str(source))
        verify(manifest["source_pins"])
        verify(evidence)
        identities.extend([manifest["source_pins"], evidence,
                           {str(result_path): reader.digest(result_path)}])
        receipts[kind] = {"result": str(result_path), "result_sha256": reader.digest(result_path),
                          "manifest": str(manifest_path), "manifest_sha256": reader.digest(manifest_path)}
    return merge_pins(*identities), receipts


def storage_filelist(lines, engine_path, support):
    if lines.count(str(engine_path)) != 1:
        raise ValueError("AKV engine missing/duplicated in filelist")
    additions = [str(support / p.name) for p in reversed(SUPPORT)]
    if any(p in lines for p in additions):
        raise ValueError("Storage overlay already applied")
    i = lines.index(str(engine_path))
    return lines[:i] + additions + lines[i:]


def validate_snapshot(snapshot):
    report = json.loads((snapshot / "manifest.json").read_text())
    if (report.get("state") != "PREPARED_NOT_COMPILED" or report.get("storage_variant") != VARIANT or
            report.get("overlay_modules") != list(reader.MODULES.values()) or
            report.get("storage_overlay_modules") != [reader.MODULES["akv"]] or
            set(report.get("storage_unit_receipts", {})) != {"tc", "macro"}):
        raise ValueError("Wrong storage snapshot type")
    verify(report["input_pins"])
    verify(report["artifact_pins"])
    return report


def prepare(manifest, output):
    unit_pins, receipts = accepted_units()
    report = reader.prepare(manifest, output)
    inputs = merge_pins(report["input_pins"], unit_pins,
                        {str(HERE / "STORAGE_README.md"): reader.digest(HERE / "STORAGE_README.md")})
    support = output / "support"
    for source in SUPPORT:
        (support / source.name).write_bytes(source.read_bytes())
    engine = Path(report["source_mapping"][str(ROOT / reader.MODULES["akv"])])
    before = engine.read_text()
    after = transform_engine(before)
    engine.write_text(after)
    (output / "reader-overlay.patch").write_bytes((output / "overlay.patch").read_bytes())
    (output / "storage.patch").write_text("".join(difflib.unified_diff(
        before.splitlines(True), after.splitlines(True),
        fromfile="shared-reader/" + reader.MODULES["akv"],
        tofile="shared-reader-storage/" + reader.MODULES["akv"])))
    patches = []
    for relative in reader.MODULES.values():
        source = ROOT / relative
        changed = Path(report["source_mapping"][str(source)])
        patches.extend(difflib.unified_diff(source.read_text().splitlines(True),
                                           changed.read_text().splitlines(True),
                                           fromfile=relative, tofile="overlay/" + relative))
    (output / "overlay.patch").write_text("".join(patches))
    filelist = Path(report["filelist"])
    lines = storage_filelist(filelist.read_text().splitlines(), engine, support)
    filelist.write_text("\n".join(lines) + "\n")
    filtered, omitted = reader.compile_lines(lines, output / "source")
    Path(report["compile_filelist"]).write_text("\n".join(filtered) + "\n")
    verify(inputs)
    report.update(input_pins=inputs, storage_variant=VARIANT,
                  storage_overlay_modules=[reader.MODULES["akv"]], storage_unit_receipts=receipts,
                  storage_support=[str(support / p.name) for p in SUPPORT],
                  storage_capacity_bytes={"q": 2048, "kv": 32768}, compile_omitted=omitted,
                  scope="Complete shared-reader/unified-storage production overlay; not yet compiled or run")
    report["artifact_pins"] = {str(p): reader.digest(p) for p in output.rglob("*")
                               if p.is_file() and p != output / "manifest.json"}
    (output / "manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    validate_snapshot(output)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.manifest.resolve(), args.output.resolve())
    print(json.dumps({"state": result["state"], "variant": VARIANT,
                      "manifest": str(args.output.resolve() / "manifest.json"),
                      "manifest_sha256": reader.digest(args.output.resolve() / "manifest.json")}))
