# M9 FMV.D.X Observability

Static conclusion: **the frozen M9 retire CSV exposes the FMV.D.X FP destination
writeback payload**. It is not forced GPR x0 data merely because rd=0. No trace
has been read and no dynamic payload correctness is claimed yet.

Frozen root: `/home/wangwy/fpga_runs/current_board_memory_candidate09/frozen/sources`.
All14 inspected source hashes match snapshot.json; exact bindings are in the
adjacent JSON. image.json SHA48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a.

1. `hardware/src/ara_soc.sv:539` derives RVF/RVD from the selected HalfSingleDouble
   support bits; build_config_pkg.sv:6,8,89 derives FpPresent=true and FLen64.
2. `hardware/deps/cva6/core/decoder.sv:1481` decodes FMV.X2F. The original helper
   opcode f2038053 is FMV.D.X f0,t2, with the double format and no boxing OR.
   ariane_pkg.sv:599-610 includes FMV_X2F in is_rd_fpr.
3. `cva6_rvfi_probes.sv:108-112` takes op/rd/result from the same commit instruction.
   `cva6_rvfi.sv:315-343` qualifies valid retirement and registers rd_addr plus
   `FpPresent && is_rd_fpr(op) ? commit_instr_result : wdata`. This is the FPR arm
   for FMV.D.X, independent of rd being zero.
4. `commit_stage.sv:178-181` enables the FPR write for this instruction; line148
   supplies the same result (the AMO alternative is irrelevant to FMV). cva6.sv
   connects commit wdata/we_fpr to issue_read_operands. That module's923-956 path
   takes all64 result bits and instantiates the FPR with ZERO_REG_ZERO(0).
5. `hardware/src/ara_system.sv:214-245` connects the RVFI generator to the monitor.
   `hardware/tb/ara_commit_monitor.sv:248-264` prints rd_addr and rd_wdata without
   zero-register masking for every valid retirement. CSV omits an explicit
   destination-bank bit, so actual opcode/PC must select FP rather than GPR tracking.

Required worker check: for each of10752 original vf moves, require the actual
SoC helper PC/code f2038053, no trap, rd=0 and full64 rd_wdata equal the source
seed's zero-extended b[0]. Independently check preceding LHU/t2, exact helper
window and source setup. Do not update or consult GPR x0 as the move's destination.
Seeds0/16 legitimately carry zero; the other30 must not be silently zeroed or boxed.

This can distinguish incorrect raw0 versus raw0x8000 despite both being invalid
FP16 boxes consumed as qNaN. Numerical compare/flags PASS alone cannot distinguish
those payloads. Add a nonzero-seed payload-to-zero negative retaining t2 and
numerical results, and a boxed-highbits negative. These are checker requirements,
not new RTL experiments.

Scope wording: direct *retired FPR writeback payload*, plus observed consuming
instruction/result. The CSV does not directly read the post-write physical FPR
cell or separately expose the accelerator's scalar operand; do not claim those.
No new image/build/Host/reference/DUT/live query or active/raw trace read occurred.
Actual worker plan/Host/dryrun remains to be reviewed; this is not launch approval.
