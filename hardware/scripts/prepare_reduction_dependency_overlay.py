#!/usr/bin/env python3
"""Apply confirmed divider and scalar/vector CSR repairs to private build copies.

Never edit hardware/deps: this worktree can share it with another checkout.
Keep the original source, patched source and hashes beside the VCS filelist.
The repair only matches the inherited remainder-extension implementation;
unmodified upstream implementations without that extension are left intact.
"""
import argparse
import hashlib
import json
from pathlib import Path


def digest(data):
    return hashlib.sha256(data.encode()).hexdigest()


def repair(source):
    old = "   assign Remainder_nonzero_SO = Special_case_dly_SBI && (|Partial_remainder_DP);"
    denominator = "   assign  Denominator_se_D={1'b0,Denominator_DI};"
    if "Remainder_nonzero_SO" not in source:
        return source, "upstream_without_remainder_extension"
    if "Partial_remainder_DP != Negative_divisor_D" in source:
        return source, "already_repaired"
    if source.count(old) != 1 or source.count(denominator) != 1:
        raise ValueError("Unrecognized divider remainder implementation; inspect before patching")
    source = source.replace(old, """   // Non-restoring division encodes exact remainder as 0 or -D.
   // A negative divisor residue must not create a false sticky/NX bit.
   logic [C_MANT_FP64+5:0] Negative_divisor_D;
   assign Remainder_nonzero_SO = Special_case_dly_SBI && Div_enable_SO &&
                                (|Partial_remainder_DP) &&
                                (Partial_remainder_DP != Negative_divisor_D);""")
    source = source.replace(denominator, denominator +
        "\n   assign Negative_divisor_D = ~{Denominator_se_D, 4'b0} + 1'b1;")
    return source, "repaired_exact_negative_divisor_residue"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filelist", type=Path)
    args = parser.parse_args()
    filelist = args.filelist.resolve()
    lines = filelist.read_text().splitlines()
    directory = filelist.parent / "reduction_dependency_overlay"
    directory.mkdir(exist_ok=True)
    entries = []
    for name, transform in [("control_mvp.sv", repair),
                            ("acc_dispatcher.sv", repair_fp_csr)]:
        matches = [(i, Path(line.strip())) for i, line in enumerate(lines)
                   if line.strip().endswith("/" + name)]
        if len(matches) != 1:
            raise ValueError("Expected exactly one " + name + " in the VCS filelist")
        index, original = matches[0]
        source = original.read_text()
        patched, status = transform(source)
        target = directory / name
        (directory / (name + ".original")).write_text(source)
        target.write_text(patched)
        entries.append({
            "original": str(original), "original_sha256": digest(source),
            "compiled": str(target), "compiled_sha256": digest(patched),
            "status": status,
        })
        lines[index] = str(target)
    (directory / "manifest.json").write_text(json.dumps({
        "entries": entries,
        "reference": "ara_dsa_signoff_integration 7d5d1829 working dependency repair",
    }, indent=2) + "\n")
    filelist.write_text("\n".join(lines) + "\n")


def repair_fp_csr(source):
    """Serialize FFLAGS/FRM/FCSR against all older accelerator transfer stages.

    Deliberately omit the reference branch's unrelated queue and fence changes.
    """
    if "fp_csr_busy" in source:
        raise ValueError("Inspect existing FP CSR interlock before applying this overlay")
    anchor = "  // Stall issue stage in three cases:"
    insertion = """  logic fp_csr_access, fp_csr_wait;
  // The issue immediate belongs to this instruction; csr_addr_i can be older.
  assign fp_csr_access = !issue_instr_i.ex.valid && (issue_instr_i.fu == CSR) &&
      (issue_instr_i.op inside {CSR_READ, CSR_WRITE, CSR_SET, CSR_CLEAR}) &&
      (issue_instr_i.result[11:0] inside {riscv::CSR_FFLAGS, riscv::CSR_FRM,
                                         riscv::CSR_FCSR});
  // Queue-empty alone does not cover the spill, backend or last flag update.
  assign fp_csr_wait = acc_valid_q || !acc_insn_queue_empty ||
      acc_req_o.acc_req.req_valid || acc_resp_i.acc_resp.fp_csr_busy ||
      acc_resp_i.acc_resp.fflags_valid;

"""
    end = "      default: issue_stall_o = 1'b0;\n    endcase\n  end"
    declaration = "  logic                                            acc_insn_queue_empty;"
    for pattern in [anchor, end, declaration]:
        if source.count(pattern) != 1:
            raise ValueError("Unrecognized accelerator issue implementation")
    source = source.replace(declaration, "")
    source = source.replace(anchor, "  logic acc_insn_queue_empty;\n" + insertion + anchor)
    source = source.replace(end, end[:-5] +
        "    if (fp_csr_access) issue_stall_o |= fp_csr_wait;\n  end")
    return source, "serialize_fp_csr_with_accelerator_completion"


if __name__ == "__main__":
    main()
