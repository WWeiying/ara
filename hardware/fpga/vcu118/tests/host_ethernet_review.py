#!/usr/bin/env python3
"""Collect existing Ethernet example integration files for offline review only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

import host_axi_upload as evidence
import host_ethernet_preflight as preflight


HERE = Path(__file__).resolve().parent
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES = 96
IMPORTS = tuple("eth_j10_" + name + ".v" for name in (
    "example", "support", "clocks_resets", "axi_lite_ctrl", "basic_pat_gen",
    "address_swap", "reset_sync", "bit_sync", "axi_mux", "axi_pipe",
    "axi_pat_gen", "axi_pat_check", "frame_typ", "rx_client_fifo",
    "tx_client_fifo", "ten_100_1g_eth_fifo", "bram_tdp",
))
IMPORT_XDC = ("eth_j10_ex_des_loc.xdc", "eth_j10_example_design.xdc")
IP_ROOT = PurePosixPath("eth_j10_ex.srcs/sources_1/ip/eth_j10")
PREFLIGHT_STATE = "ip_example_generated_needs_license_and_constraints_review"


def safe_file(root, relative):
    """Reject links/junctions and traversal, including Windows reparse points."""
    if relative.is_absolute() or any(part in (".", "..") for part in relative.parts):
        raise ValueError(f"Unsafe relative path: {relative}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink() or getattr(current, "is_junction", lambda: False)():
            raise ValueError(f"Refusing linked input: {current}")
    current.resolve(strict=True).relative_to(root.resolve(strict=True))
    if not current.is_file():
        raise ValueError(f"Required input is not a file: {current}")
    return current


def read_text(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Input empty or exceeds 4 MiB: {path}")
    text = data.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError(f"Binary input is not reviewable text: {path}")
    # Never package protected HDL or license material, even under an allowed name.
    if re.search(r"(?im)^\s*(?:`pragma\s+protect|`protect|pragma\s+protect|--\s*pragma\s+protect|"
                 r"(?:-+)?BEGIN [A-Z ]*PRIVATE KEY|(?:INCREMENT|FEATURE)\s+\S+\s+(?:xilinxd|snpslmd)\b)", text):
        raise ValueError(f"Protected HDL or license material in selected file: {path}")
    return text, {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def xml_root(text):
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("DTD/entity declarations are not accepted in review XML")
    return ET.fromstring(text)


def config_summary(text):
    """Extract IP-XACT metadata; do not interpret or execute generated HDL/Tcl."""
    components, parameters = [], {}
    for node in xml_root(text).iter():
        tag = node.tag.rsplit("}", 1)[-1]
        attributes = {key.rsplit("}", 1)[-1]: value for key, value in node.attrib.items()}
        if tag == "componentRef":
            components.append({key: attributes[key] for key in ("vendor", "library", "name", "version")
                               if key in attributes})
        if tag == "configurableElementValue":
            key = attributes.get("referenceId", "")
            if key.startswith(("PARAM_VALUE.", "MODELPARAM_VALUE.", "CONFIG.")):
                if key in parameters:
                    raise ValueError(f"Ambiguous duplicate IP parameter: {key}")
                parameters[key] = node.text or ""
    return {"components": components, "parameters": parameters,
            "recognized": bool(components and parameters)}


def collect(source):
    files, records, texts = [], {}, {}

    def select(relative, member, role):
        if member in records or len(records) >= MAX_FILES:
            raise ValueError("Duplicate archive member or too many review inputs")
        path = safe_file(source, PurePosixPath(relative))
        text, fingerprint = read_text(path)
        if sum(row["bytes"] for row in records.values()) + fingerprint["bytes"] > MAX_TOTAL_BYTES:
            raise ValueError("Selected review inputs exceed 16 MiB")
        records[member] = dict(fingerprint, role=role, source_relative=relative)
        texts[member] = text
        files.append((path, member))
        return text

    for name in preflight.UPLOAD_FILES:
        select(name, "preflight/" + name, "preflight_evidence")
    record = json.loads(texts["preflight/preflight.json"])
    if (record.get("state") != PREFLIGHT_STATE or record.get("vivado_exit_code") != 0 or
            record.get("stages") != dict.fromkeys(preflight.STAGES, "PASS") or
            record.get("requested_config") != preflight.CONFIG):
        raise ValueError("Need the completed, supported Ethernet preflight; no regeneration attempted")
    report = texts["preflight/preflight.rpt"]
    if "PREFLIGHT_COMPLETE" not in report.splitlines() or "EXAMPLE_PROJECT eth_j10_ex" not in report.splitlines():
        raise ValueError("Missing completion marker or unexpected example project")
    if preflight.read_stages(source) != record["stages"]:
        raise ValueError("Stage file differs from preflight.json")
    board = preflight.board_contract(preflight.BOARD)
    if record.get("board", {}).get("files_sha256") != board["files_sha256"]:
        raise ValueError("Board XML differs from the successful preflight")

    # Use the original inventory's root, not its absolute paths, so an intact
    # preflight directory can be moved without following references elsewhere.
    command = record.get("command", [])
    if command.count("-tclargs") != 1:
        raise ValueError("Missing original preflight command provenance")
    original_args = command[command.index("-tclargs") + 1:]
    if len(original_args) != 2:
        raise ValueError("Unexpected preflight Tcl arguments")
    original = original_args[0]
    path_type = PureWindowsPath if PureWindowsPath(original).drive else PurePosixPath
    original_root = path_type(original)
    if not original_root.is_absolute() or ".." in original_root.parts:
        raise ValueError("Original preflight path is not absolute")
    original_example = original_root / "example" / "eth_j10_ex"
    example_prefix = "example/eth_j10_ex/"
    inventory, selected, configs = set(), set(), {}
    counts = {"xdc": 0, "example_hdl": 0, "ip_config": 0}
    for line in report.splitlines():
        if not line.startswith("EXAMPLE_FILE "):
            continue
        # File types can contain spaces (for example, "Verilog Template").
        # The report format separates the type from an absolute Vivado path.
        match = re.fullmatch(r"EXAMPLE_FILE (.+?) ((?:[A-Za-z]:[/\\]|/|\\\\).+)", line)
        if not match:
            raise ValueError(f"Unrecognized example inventory row: {line}")
        kind, value = match.groups()
        if kind not in ("Verilog", "XDC", "IP"):
            continue
        original_path = path_type(value)
        if ".." in original_path.parts:
            raise ValueError("Traversal in preflight inventory")
        relative = PurePosixPath(*original_path.relative_to(original_example).parts)
        key = relative.as_posix().lower()
        if key in inventory:
            raise ValueError(f"Duplicate inventory file: {relative}")
        inventory.add(key)
        role = None
        if kind == "Verilog" and relative.parent == PurePosixPath("imports") and relative.name in IMPORTS:
            role = "example_hdl"
        elif kind == "XDC" and (relative.as_posix().startswith(IP_ROOT.as_posix() + "/") or
                                key in {"imports/" + name for name in IMPORT_XDC}):
            if relative.suffix.lower() != ".xdc":
                raise ValueError(f"Wrong XDC extension: {relative}")
            role = "xdc"
        elif kind == "IP" and relative.as_posix().startswith(IP_ROOT.as_posix() + "/"):
            if relative.suffix.lower() != ".xci":
                raise ValueError(f"Wrong IP configuration extension: {relative}")
            role = "ip_config"
        if role is None:
            if kind == "XDC":
                raise ValueError(f"Constraint outside supported example layout: {relative}")
            continue
        member = "example/" + relative.as_posix()
        text = select(example_prefix + relative.as_posix(), member, role)
        selected.add(key)
        counts[role] += 1
        if role == "ip_config":
            configs[member] = config_summary(text)
    required = {"imports/" + name for name in (*IMPORTS, *IMPORT_XDC)}
    required.add((IP_ROOT / "eth_j10.xci").as_posix())
    if not required <= selected:
        raise ValueError("Required integration files missing from inventory: " + ", ".join(sorted(required - selected)))
    summary = re.findall(r"(?m)^EXAMPLE_FILES=(\d+) XDC_FILES=(\d+)\r?$", report)
    if (len(summary) != 1 or int(summary[0][1]) != counts["xdc"] or
            int(summary[0][0]) != sum(line.startswith("EXAMPLE_FILE ") for line in report.splitlines())):
        raise ValueError("Example inventory counts disagree; nothing uploaded")
    project = select(example_prefix + "eth_j10_ex.xpr", "example/eth_j10_ex.xpr", "project_metadata")
    project_root = xml_root(project)
    if project_root.tag != "Project":
        raise ValueError("Unexpected Vivado project XML")
    project_options = [dict(node.attrib) for node in project_root.findall("./Configuration/Option")
                       if node.get("Name") in ("Part", "BoardPart", "TargetLanguage")]
    return files, {
        "diagnostic_only": True, "hardware_access": False, "hardware_verified": False,
        "build_ready": False, "state": "collected_needs_manual_clock_reset_pin_review",
        "source": str(source), "created_utc": datetime.now(timezone.utc).isoformat(),
        "preflight_started_utc": record.get("started_utc"),
        "preflight_tools_sha256": record.get("tools_sha256"), "board": board,
        "license_report": preflight.assess_mac_license(texts["preflight/ip_status_after.rpt"]),
        "counts": counts, "selected": records, "ip_configurations": configs,
        "project_options": project_options,
        "note": "Files are hashed at collection, not at original generation. No HDL/XDC was executed. "
                "XDC inventory includes scoped/OOC files, not a list to apply at top level. "
                "Example HDL and XDC are included; protected implementation HDL, license files, "
                "DCP, bitstream, and simulator products are excluded.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight", type=Path, help="Existing successful preflight directory")
    parser.add_argument("--upload-example", action="store_true",
                        help="Upload allowlisted example HDL/XDC, XCI/XPR configuration and reports to origin")
    args = parser.parse_args(argv)
    output = None
    try:
        source = args.preflight.resolve(strict=True)
        print(f"SOURCE {source}", flush=True)
        print("Read-only collection; no Vivado, IP generation, synthesis, routing or board access.", flush=True)
        files, review = collect(source)
        output = Path(tempfile.mkdtemp(prefix="ara_eth_review_"))
        print(f"BUNDLE {output}", flush=True)
        review["collector_sha256"] = preflight.digest(Path(__file__))
        review["collection_checkout_commit"] = evidence.git(HERE, "rev-parse", "HEAD")
        review_path = output / "review.json"
        review_path.write_text(json.dumps(review, indent=2) + "\n", encoding="utf-8")
        branch = "fpga-evidence/ethernet-review-" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "-" + uuid.uuid4().hex[:8]
        evidence.package(files + [(review_path, "review.json")], output,
                         {"diagnostic_only": True, "hardware_access": False, "build_ready": False,
                          "evidence_branch": branch, "note": review["note"],
                          "collection_checkout_commit": review["collection_checkout_commit"]})
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["path"] == "review.json":
                continue
            expected = review["selected"][entry["path"]]
            if any(entry[key] != expected[key] for key in ("bytes", "sha256")):
                raise ValueError("Source changed while packaging; nothing uploaded")
        print("COUNTS " + json.dumps(review["counts"]), flush=True)
        print("REVIEW_REQUIRED: collection is not a constraints, timing or hardware pass.", flush=True)
        if args.upload_example:
            remote = evidence.git(HERE, "remote", "get-url", "--push", "origin")
            print("Uploading selected example HDL/XDC and configuration, not protected IP implementation HDL.", flush=True)
            commit = evidence.publish(output, remote, branch, message="Collect Ethernet example integration for review")
            print(f"UPLOADED_BRANCH {branch}\nUPLOADED_COMMIT {commit}", flush=True)
        else:
            print("PACKAGED_ONLY: --upload-example explicitly enables upload of the selected example files.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ET.ParseError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if output is not None:
            print(f"Local bundle retained (do not use as build approval): {output}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
