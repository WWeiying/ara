#!/usr/bin/env python3
"""Export a self-contained, link-free Windows Vivado source snapshot."""
import argparse
import datetime
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from prepare import HERE, ROOT, CACHE, CHESHIRE, BOARD_PORT, BOARD_TREE


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f"Integration source changed; cannot apply: {old!r}")
    return text.replace(old, new)


def patch_akv_descriptor_reduction(text):
    old = "!&descriptor_byte_valid_q"
    new = "!(&descriptor_byte_valid_q)"
    # Newer Ara revisions already contain this syntax fix in the source RTL.
    counts = (text.count(old), text.count(new))
    if counts == (0, 1):
        return text
    if counts == (1, 0):
        return replace_once(text, old, new)
    raise RuntimeError("Integration source changed: unexpected AKV descriptor reduction")


def patch_akv_byte_counts(text):
    text = patch_akv_descriptor_reduction(text)
    text = replace_once(text,
        "  logic [AxiDataWidth/8-1:0] read_data_strb;",
        """  logic [AxiDataWidth/8-1:0] read_data_strb;
  logic [$clog2(AxiDataWidth/8+1)-1:0] fpga_read_data_byte_count;""")
    text = replace_once(text, """  always_comb begin
    replay_word_bytes = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++)
      replay_word_bytes += 7'($countones(ldu_result_be_o[lane]));
  end""", """  // Fixed-bound loops avoid dynamic $countones in Vivado 2020.1.
  // Procedural if counts only known ones, preserving $countones X/Z behavior.
  always_comb begin
    replay_word_bytes = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++)
      for (int unsigned byte_lane = 0; byte_lane < 8; byte_lane++)
        if (ldu_result_be_o[lane][byte_lane])
          replay_word_bytes += 7'd1;
  end

  always_comb begin
    fpga_read_data_byte_count = '0;
    for (int unsigned byte_lane = 0; byte_lane < AxiDataWidth/8; byte_lane++)
      if (read_data_strb[byte_lane])
        fpga_read_data_byte_count += 1'b1;
  end""")
    old = "32'($countones(read_data_strb))"
    if text.count(old) != 2:
        raise RuntimeError("Integration source changed: unexpected AKV byte counter updates")
    return text.replace(old, "32'(fpga_read_data_byte_count)")


def patch_dispatcher_vlen_casts(text):
    # Vivado 2020.1 rejects these casts in comparisons on struct members.
    # vlen_t is unsigned packed logic; a low slice has identical bit semantics.
    replacements = (
        ("""csr_vl_d = ((|acc_req_i.rs1[$bits(acc_req_i.rs1)-1:$bits(csr_vl_d)]) ||
                        (vlen_t'(acc_req_i.rs1) > vlmax)) ? vlmax : vlen_t'(acc_req_i.rs1);""",
         """csr_vl_d = ((|acc_req_i.rs1[$bits(acc_req_i.rs1)-1:$bits(csr_vl_d)]) ||
                        (acc_req_i.rs1[$bits(csr_vl_d)-1:0] > vlmax)) ? vlmax : acc_req_i.rs1[$bits(csr_vl_d)-1:0];""",
         1),
        ("""if (|ara_req.stride[$bits(ara_req.stride)-1:$bits(csr_vl_q)] ||
                      (vlen_t'(ara_req.stride) >= csr_vl_q)) null_vslideup = 1'b1;""",
         """if (|ara_req.stride[$bits(ara_req.stride)-1:$bits(csr_vl_q)] ||
                      (ara_req.stride[$bits(csr_vl_q)-1:0] >= csr_vl_q)) null_vslideup = 1'b1;""",
         2),
    )
    for old, new, expected in replacements:
        counts = (text.count(old), text.count(new))
        if counts == (0, expected):
            continue
        if counts != (expected, 0):
            raise RuntimeError("Integration source changed: unexpected dispatcher VL comparison")
        text = text.replace(old, new)
    return text


def patch_soc_pkg(text):
    return replace_once(text, "    // Modify what we need to\n", """    // FPGA-only integration: retain the current scalar/vector FP16 contract.
    // This CVA6 snapshot has stub-only FpgaEn RAMs. Use its real generic
    // implementation; tc_sram is independently mapped to Xilinx XPM.
    ret.FpgaEn = 0;
    ret.XF16 = 1;
    // Modify what we need to
""")


def patch_soc(text):
    return replace_once(text, "      .rvfi_probes_o    ( ),", """      .clic_irq_valid_i ( 1'b0 ),
      .clic_irq_id_i    ( '0 ),
      .clic_irq_level_i ( '0 ),
      .clic_irq_priv_i  ( riscv::PRIV_LVL_M ),
      .clic_irq_v_i     ( 1'b0 ),
      .clic_irq_vsid_i  ( '0 ),
      .clic_irq_shv_i   ( 1'b0 ),
      .clic_irq_ready_o ( ),
      .clic_kill_req_i  ( 1'b0 ),
      .clic_kill_ack_o  ( ),
      .rvfi_probes_o    ( ),""")


def patch_sram_cache(text):
    # Generic ASIC memory ignored these floating inputs. XPM has an actual
    # output reset port, so preserve the existing cache reset down the wrapper.
    text = replace_once(text, "          .clk_i  (clk_i),", """          .clk_i  (clk_i),
          .rst_ni (rst_ni),
          .wuser_i(wuser_i),
          .ruser_o(ruser_o),""")
    return text


def patch_dram(text):
    text = replace_once(text, "  input  logic  soc_clk_i,", """  input  logic  soc_clk_i,
  output logic  fabric_ready_o,""")
    text = replace_once(text, "  logic dram_rst_o;", """  logic dram_rst_o;
  logic calib_complete;
  logic ui_resetn;
  // Common asynchronous assertion, separately synchronized deassertion.
  assign fabric_ready_o = ~sys_rst_i & ~dram_rst_o & calib_complete;
  rstgen i_ui_rstgen (
    .clk_i(dram_axi_clk), .rst_ni(fabric_ready_o), .test_mode_i(1'b0),
    .rst_no(ui_resetn), .init_no()
  );""")
    text = replace_once(text, ".dst_rst_ni ( ~dram_rst_o  )", ".dst_rst_ni ( ui_resetn    )")
    text = replace_once(text, ".c0_ddr4_aresetn            ( soc_resetn_i )",
                        ".c0_ddr4_aresetn            ( ui_resetn    )")
    text = replace_once(text, ".c0_init_calib_complete     ( )",
                        ".c0_init_calib_complete     ( calib_complete )")
    text = replace_once(text, ".addn_ui_clkout1            ( dram_clk_o )",
                        ".addn_ui_clkout1            ( )")
    text = text.replace("// 333 MHz AXI (cf. CdcLogDepth)",
                        "// UI clock derived by the Vivado DDR4 IP")
    return text


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True)


SMOKE_INPUTS = ("start.S", "smoke.c", "smoke.ld", "build_smoke.py",
                "include/qbs_abi.h", "include/akv_abi.h")
SMOKE_OUTPUTS = ("smoke.elf", "smoke.map", "smoke.dump")


def build_or_reuse_smoke(dst, gcc, objdump, previous=None):
    # A source-only update should not recompile an unchanged smoke program or
    # churn its map file with compiler temporary paths.
    reusable = False
    if previous is not None:
        hashes = dict((name, digest) for digest, name in
                      (line.split("  ", 1) for line in
                       (previous / "SHA256SUMS").read_text().splitlines()))
        reusable = all(hashlib.sha256((dst / "software" / name).read_bytes()).hexdigest() ==
                       hashes.get("software/" + name) for name in SMOKE_INPUTS)
        reusable = reusable and all(
            (previous / "software" / name).is_file() and
            not (previous / "software" / name).is_symlink() and
            hashlib.sha256((previous / "software" / name).read_bytes()).hexdigest() ==
            hashes.get("software/" + name) for name in SMOKE_OUTPUTS)
    if reusable:
        for name in SMOKE_OUTPUTS:
            shutil.copyfile(previous / "software" / name, dst / "software" / name)
        print("Reused unchanged, checksum-verified smoke ELF/map/dump")
    else:
        subprocess.run([sys.executable, str(dst / "software/build_smoke.py"),
                        "--gcc", gcc, "--objdump", objdump], check=True)


def export(dst, gcc, objdump, smoke_from=None):
    if dst.exists():
        raise RuntimeError(f"Refusing to overwrite existing export: {dst}")
    groups = json.loads((CACHE / "sources.json").read_text())
    roots = {name: Path(path).resolve() for name, path in
             json.loads((CACHE / "roots.json").read_text()).items()}
    dst.mkdir(parents=True)
    files, incdirs, defines, copied = [], [], {}, set()
    source_records = []
    changes = []
    excluded = {"cheshire_top_xilinx.sv", "dram_wrapper_xilinx.sv", "phy_definitions.svh",
                "fan_ctrl.sv", "ara_soc.sv", "ara_system.sv"}

    def relative(src):
        src = Path(src).resolve()
        matches = [(len(str(p)), name, p) for name, p in roots.items()
                   if src == p or p in src.parents]
        if not matches:
            raise RuntimeError(f"Unowned dependency file: {src}")
        _, name, parent = max(matches)
        return Path("rtl") / name / src.relative_to(parent)

    def copy(src):
        src = Path(src).resolve()
        target = relative(src)
        if target in copied:
            return target.as_posix()
        if not src.is_file():
            raise RuntimeError(f"Missing source: {src}")
        out = dst / target
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
        copied.add(target)
        source_records.append({"file": target.as_posix(),
                               "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest()})
        return target.as_posix()

    for group in groups:
        defines.update(group.get("defines", {}))
        includes = [item[1] if isinstance(item, list) else item
                    for item in group.get("include_dirs", [])]
        for dirs in group.get("export_incdirs", {}).values():
            includes.extend(item[1] if isinstance(item, list) else item for item in dirs)
        for directory in includes:
            path = relative(directory).as_posix()
            if path not in incdirs:
                incdirs.append(path)
            (dst / path).mkdir(parents=True, exist_ok=True)
            # Some packages use .sv as headers. Export the entire include tree.
            for src in sorted(Path(directory).rglob("*")):
                if src.is_file() and ".git" not in src.parts:
                    copy(src)
        for src in group["files"]:
            if not isinstance(src, str):
                raise RuntimeError(f"Unexpected non-flat Bender source {src}")
            if group["package"] == "axi" and Path(src).name == "axi_inval_filter.sv":
                continue  # Use this project's cache-invalidation filter, not the duplicate IP.
            if Path(src).name not in excluded:
                name = copy(src)
                if name not in files:
                    files.append(name)

    for rel, transform in [("rtl/cheshire/hw/cheshire_pkg.sv", patch_soc_pkg),
                           ("rtl/cheshire/hw/cheshire_soc.sv", patch_soc),
                           ("rtl/cva6/common/local/util/sram_cache.sv", patch_sram_cache),
                           ("rtl/ara/hardware/src/ara_dispatcher.sv", patch_dispatcher_vlen_casts),
                           ("rtl/ara/hardware/src/vlsu/akv/akv_engine.sv",
                            patch_akv_byte_counts)]:
        path = dst / rel
        before = path.read_text()
        after = transform(before)
        path.write_text(after)
        changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                           fromfile="a/" + rel, tofile="b/" + rel))
    board_src = CACHE / "cheshire_board/target/xilinx/src"
    for name in ["phy_definitions.svh", "dram_wrapper_xilinx.sv"]:
        path = dst / "rtl/board" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        before = (board_src / name).read_text()
        after = patch_dram(before) if name.endswith(".sv") else before
        path.write_text(after)
        if name.endswith(".sv"):
            files.append(path.relative_to(dst).as_posix())
            changes.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                fromfile="a/rtl/board/" + name, tofile="b/rtl/board/" + name))
    incdirs.append("rtl/board")
    shutil.copyfile(HERE / "rtl/ara_dsa_vcu118.sv", dst / "rtl/board/ara_dsa_vcu118.sv")
    files.append("rtl/board/ara_dsa_vcu118.sv")
    defines.update({"ARA": None, "NR_LANES": 4, "VLEN": 1024,
                    "ARA_QBS_ENABLE": 1, "ARA_AKV_ENABLE": 1, "ARA_AKV_V2_ENABLE": 1})
    forbidden = {"TARGET_SRAM_MC", "IDEAL_DISPATCHER", "FOR_VERIFY"}
    if forbidden.intersection(defines):
        raise RuntimeError("ASIC/verification defines present in FPGA configuration")

    for name in ["scripts", "constraints", "software", "docs"]:
        if (HERE / name).exists():
            shutil.copytree(HERE / name, dst / name,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(CACHE / "board_files", dst / "board_files")
    shutil.copyfile(HERE / "README_WINDOWS.md", dst / "README_WINDOWS.md")
    shutil.copyfile(HERE / "sync.py", dst / "scripts/sync.py")
    for name in (".gitignore", ".gitattributes"):
        shutil.copyfile(HERE / ("package" + name), dst / name)
    include = dst / "software/include"
    include.mkdir(parents=True, exist_ok=True)
    for name in ["qbs_abi.h", "akv_abi.h"]:
        shutil.copyfile(ROOT / "apps/common" / name, include / name)
    shutil.copytree(CACHE / "wheels", dst / "software/vendor")
    reference = dst / "software/reference"
    reference.mkdir()
    for name in ["hw/bootrom/cheshire_bootrom.c", "hw/bootrom/cheshire_bootrom.S",
                 "hw/bootrom/cheshire_bootrom.ld", "sw/lib/hal/uart_debug.c",
                 "sw/include/params.h", "sw/link/common.ldh"]:
        shutil.copyfile(roots["cheshire"] / name, reference / Path(name).name)
    build_or_reuse_smoke(dst, gcc, objdump, smoke_from)
    provenance = dst / "provenance"
    provenance.mkdir()
    (provenance / "integration.patch").write_text("".join(changes))
    (provenance / "cva6_local.patch").write_text(git(roots["cva6"], "diff", "HEAD", "--"))
    (provenance / "ara_local.patch").write_text(git(ROOT, "diff", "HEAD", "--", "hardware/src", "hardware/include"))
    revisions = {}
    for name, path in roots.items():
        revisions[name] = {"commit": git(path, "rev-parse", "HEAD").strip()}
        for license_path in list(path.glob("LICENSE*")) + list(path.glob("COPYING*")) + list(path.glob("NOTICE*")):
            if license_path.is_file():
                target = dst / "licenses" / name / license_path.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(license_path, target)
        revisions[name]["tracked_changes"] = git(path, "diff", "--name-only", "HEAD", "--").splitlines()
    manifest = {"top": "ara_dsa_vcu118", "part": "xcvu9p-flga2104-2L-e",
        "board_part": "xilinx.com:vcu118:part0:2.4", "soc_clock_mhz": 50,
        "files": files, "include_dirs": incdirs, "defines": defines,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "revisions": revisions, "cheshire_soc_commit": CHESHIRE,
        "cheshire_board_port_commit": BOARD_PORT, "board_definition_tree": BOARD_TREE,
        "source_hashes_before_integration": source_records,
        "validation": "Source snapshot only; validation logs from earlier snapshots are historical"}
    (dst / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Braced Tcl words keep paths relative and support an export directory with spaces.
    def tcl_list(values):
        for value in values:
            if any(c in value for c in "{}\\\n"):
                raise RuntimeError(f"Unsafe Tcl path: {value}")
        separator = " " + chr(92) + "\n    "
        return "[list " + separator.join("{" + str(value) + "}" for value in values) + "]"
    lines = ["# Generated from manifest.json. All paths are package-relative.",
             "set rtl_files " + tcl_list(files),
             "set rtl_include_dirs " + tcl_list(incdirs),
             "set rtl_defines " + tcl_list([k if v is None else f"{k}={v}" for k, v in defines.items()])]
    (dst / "scripts/sources.tcl").write_text("\n".join(lines) + "\n")
    seal(dst)
    print(f"Exported {len(files)} compilation files into {dst}")


def seal(dst):
    rows = []
    names = set()
    for path in sorted(dst.rglob("*")):
        if path.is_symlink():
            raise RuntimeError(f"Symlink in export: {path}")
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        rel = path.relative_to(dst).as_posix()
        if rel.casefold() in names:
            raise RuntimeError(f"Case-insensitive filename collision: {rel}")
        names.add(rel.casefold())
        rows.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    (dst / "SHA256SUMS").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--gcc", required=True, help="Host path to the RV64 GCC for prebuilt smoke ELF")
    parser.add_argument("--objdump", required=True, help="Host path to matching RV64 objdump")
    args = parser.parse_args()
    destination = args.destination.resolve()
    export(destination, args.gcc, args.objdump)
