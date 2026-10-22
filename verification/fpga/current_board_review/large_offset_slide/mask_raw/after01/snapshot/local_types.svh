typedef struct packed {
    vid_t id; // ID of the vector instruction

    logic [4:0] vs; // Vector register operand

    logic scale_vl; // Rescale vl taking into account the new and old EEW

    resize_e cvt_resize;    // Resizing of FP conversions

    logic is_reduct; // Is this a reduction?
    logic is_slide; // Is this a slide?
    logic source_snapshot_capture;
    logic source_snapshot_replay;

    rvv_pkg::vew_e eew;        // Effective element width
    opqueue_conversion_e conv; // Type conversion

    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)

    // Vector machine metadata
    rvv_pkg::vtype_t vtype;
    vlen_t vl;
    vlen_t vstart;

    // Hazards
    logic [NrVInsn-1:0] hazard;
    logic [NrVInsn-1:0] hazard_source_lifetime;
    logic [NrVInsn-1:0] hazard_wait_complete;
  } operand_request_cmd_t;
typedef struct packed {
    rvv_pkg::vew_e eew;        // Effective element width
    vlen_t elem_count;         // Vector body length
    opqueue_conversion_e conv; // Type conversion
    logic [1:0] ntr_red;       // Neutral type for reductions
    logic is_reduct;           // Is this a reduction?
    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)
  } operand_queue_cmd_t;
typedef struct packed {
    vid_t id; // ID of the vector instruction

    ara_op_e op; // Operation
    logic vm;    // Masked instruction

    logic use_vs1;   // This operation uses vs1
    logic use_vs2;   // This operation uses vs1
    logic use_vd_op; // This operation uses vd as an operand as well
    // A narrowing instruction may replay an aliased narrow vs1/old-vd after
    // the physical destination group was converted for its wide vs2.
    logic preserve_narrow_vd;

    elen_t scalar_op;    // Scalar operand
    logic use_scalar_op; // This operation uses the scalar operand
    logic skip_sldu_operand; // SLDU operation completes without the shared operand stream

    vfu_e vfu; // VFU responsible for this instruction

    logic [4:0] vd; // Vector destination register
    logic use_vd;

    logic swap_vs2_vd_op; // If asserted: vs2 is kept in MulFPU opqueue C, and vd_op in MulFPU A

    fpnew_pkg::roundmode_e fp_rm; // Rounding-Mode for FP operations
    logic wide_fp_imm;            // Widen FP immediate (re-encoding)
    resize_e cvt_resize;    // Resizing of FP conversions

    // Vector machine metadata
    vlen_t vl;
    vlen_t vstart;
    rvv_pkg::vtype_t vtype;
  } vfu_operation_t;
typedef struct packed {
    ara_op_e op; // Operation

    // Stores and slides do not re-shuffle the
    // source registers. In these two cases, vl refers
    // to the target EEW and vtype.vsew, respectively.
    // Since operand requesters work with the old
    // eew of the source registers, we should rescale
    // vl to the old eew to fetch the correct number of Bytes.
    //
    // Another solution would be to pass directly the target
    // eew (vstores) or the vtype.vsew (vslides), but this would
    // create confusion with the current naming convention
    logic scale_vl;

    // Mask vector register operand
    logic vm;
    rvv_pkg::vew_e eew_vmask;

    // 1st vector register operand
    logic [4:0] vs1;
    logic use_vs1;
    opqueue_conversion_e conversion_vs1;
    rvv_pkg::vew_e eew_vs1;
    rvv_pkg::vew_e old_eew_vs1;

    // 2nd vector register operand
    logic [4:0] vs2;
    logic use_vs2;
    opqueue_conversion_e conversion_vs2;
    rvv_pkg::vew_e eew_vs2;
    rvv_pkg::vew_e old_eew_vs2;

    // Use vd as an operand as well (e.g., vmacc)
    logic use_vd_op;
    rvv_pkg::vew_e eew_vd_op;

    // Scalar operand
    elen_t scalar_op;
    logic use_scalar_op;

    // 2nd scalar operand: stride for constant-strided vector load/stores, slide offset for vector
    // slides
    elen_t stride;
    logic is_stride_np2;

    // Destination vector register
    logic [4:0] vd;
    logic use_vd;

    // If asserted: vs2 is kept in MulFPU opqueue C, and vd_op in MulFPU A
    logic swap_vs2_vd_op;

    // Effective length multiplier
    rvv_pkg::vlmul_e emul;

    // Number of segments in segment mem op
    logic [2:0] nf;

    // Is this a fault-only-first load?
    logic fault_only_first;

    // Attention/KV command metadata. Meaningful only for VAKVFILL/VAKVLOAD.
    logic akv_refill;
    logic akv_v2;
    logic akv_column;

    // Rounding-Mode for FP operations
    fpnew_pkg::roundmode_e fp_rm;
    // Widen FP immediate (re-encoding)
    logic wide_fp_imm;
    // Resizing of FP conversions
    resize_e cvt_resize;

    // Internal widening-overlap repair protocol. A single aggregate VRF word
    // is captured before the architectural operation and may be replayed by a
    // later partial reshuffle to preserve undisturbed destination elements.
    logic overlap_capture;
    logic overlap_use_snapshot;
    vlen_t overlap_snapshot_word;

    logic source_snapshot_capture;
    logic source_snapshot_replay_vs1;
    logic source_snapshot_replay_vs2;

    // Vector machine metadata
    vlen_t vl;
    vlen_t vstart;
    rvv_pkg::vtype_t vtype;

`ifdef FOR_VERIFY
    // Keep the architectural request identity attached to any backend uops
    // introduced by reshuffling or segment-memory sequencing.
    logic [63:0] verify_arch_seq;
    logic [31:0] verify_arch_insn;
    logic [CVA6Cfg.TRANS_ID_BITS-1:0] verify_trans_id;
`endif

    // Request token, for registration in the sequencer
    logic token;
  } ara_req_t;
typedef struct packed {
    // Scalar response
    elen_t resp;

    // Instruction triggered an exception
    exception_t exception;

    // Fault-only-first exception on element whose idx > 0
    logic fof_exception;

    // New value for vstart
    vlen_t exception_vstart;

    // Command-local floating-point status. Ordinary vector instructions report
    // lane flags directly; blocking backend commands return their accumulated
    // flags together with the terminal response.
    logic [4:0] fflags;
    logic       fflags_valid;
  } ara_resp_t;
