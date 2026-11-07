"""Isolated balanced compute wiring; retain request-owned scale admission."""
from audit import require
from mixed_accumulator_source import accumulator as mixed_accumulator, compute as mixed_compute


def patch(source, replacements):
    text=source;edits=[]
    for old,new in replacements:
        require(text.count(old)==1,'Exact balanced wiring anchor: '+old[:80])
        text=text.replace(old,new,1);edits.append(dict(before=old,after=new))
    restored=text
    for edit in reversed(edits):
        require(restored.count(edit['after'])==1,'Ambiguous balanced reverse edit')
        restored=restored.replace(edit['after'],edit['before'],1)
    require(restored==source,'Balanced wiring is not reversible')
    return text,edits


def accumulator(source):
    intermediate,parent=mixed_accumulator(source)
    text,edits=patch(intermediate,[
        ('module qbs_fp_accumulator_mixed\n','module qbs_fp_accumulator_balanced\n'),
        ('endmodule : qbs_fp_accumulator_mixed','endmodule : qbs_fp_accumulator_balanced'),
        ('request_valid_i,',
         'request_mixed_enable_i,\n  input  logic                 request_valid_i,'),
        ('  logic [3:0] mixed_rr_q, mixed_index, mixed_upper_index, mixed_lower_index;',
         '  logic [NumEntries-1:0] entry_mixed_allowed_q;\n'
         '  logic [3:0] mixed_rr_q, mixed_index, mixed_upper_index, mixed_lower_index;'),
        ('wire use_mixed = MixedScaleIssue && is_scale && !is_half_scale &&',
         'wire use_mixed = MixedScaleIssue && entry_mixed_allowed_q[entry] &&\n'
         '                     is_scale && !is_half_scale &&'),
        ("\n      mixed_rr_q <= '0;", "\n      mixed_rr_q <= '0;\n      entry_mixed_allowed_q <= '0;"),
        ("\n        mixed_rr_q <= '0;", "\n        mixed_rr_q <= '0;\n        entry_mixed_allowed_q <= '0;"),
        ("          entry_valid_q[request_slot_i] <= 1'b1;",
         "          entry_valid_q[request_slot_i] <= 1'b1;\n"
         '          entry_mixed_allowed_q[request_slot_i] <= request_mixed_enable_i;'),
    ])
    return text,dict(parent=parent,edits=edits,source_reversible=True,
        admission_owned_by_entry=True,source_of_admission='Returning integer context, not live current wave',
        unchanged_fma_order=True,original_fpu_fallback=True)


def compute(source):
    intermediate,parent=mixed_compute(source)
    text,edits=patch(intermediate,[
        ('module qbs_compute_engine_mixed\n','module qbs_compute_engine_balanced\n'),
        ('endmodule : qbs_compute_engine_mixed','endmodule : qbs_compute_engine_balanced'),
        ("  parameter bit MixedScaleIssue = 1'b0,", "  parameter bit BalancedMatrixDot = 1'b0,"),
        ("  qbs_profile_engine_int #(\n    .CompactRead(1'b1), .WideMatrixDot(WideMatrixDot)",
         "  qbs_profile_engine_int_balanced #(\n    .CompactRead(1'b1), .WideMatrixDot(WideMatrixDot),\n"
         '    .BalancedMatrixDot(BalancedMatrixDot)'),
        ('  qbs_fp_accumulator_mixed #(.RawSeedEnable(SeedRestoreEnable), .MixedScaleIssue(MixedScaleIssue)) i_fp_accumulator (',
         '''  wire balanced_result_wave = BalancedMatrixDot &&
      qbs_weight_block_elements(weight_profile_q) == 256 &&
      ((integer_result_context_base == 0 && m_q >= 3) ||
       (integer_result_context_base == 4 && m_q >= 7));

  qbs_fp_accumulator_balanced #(.RawSeedEnable(SeedRestoreEnable), .MixedScaleIssue(BalancedMatrixDot)) i_fp_accumulator ('''),
        ('    .request_valid_i               (integer_result_valid),',
         '    .request_mixed_enable_i        (balanced_result_wave),\n'
         '    .request_valid_i               (integer_result_valid),'),
        ('          !i_fp_accumulator.half_found)',
         '          !i_fp_accumulator.half_found && !i_fp_accumulator.mixed_found)'),
        ('endmodule : qbs_compute_engine_balanced',
         '''`ifndef SYNTHESIS
  initial assert (!BalancedMatrixDot || WideMatrixDot)
    else $fatal(1,"Balanced matrix path requires WideMatrixDot");
`endif
endmodule : qbs_compute_engine_balanced'''),
    ])
    return text,dict(parent=parent,edits=edits,source_reversible=True,default_disabled=True,
        request_enable='M3/M4 local wave of a 256-element profile, captured per FP entry',
        m1_m2_and_short_format_scale_paths_unchanged=True,
        probe_schedulable_counts_mixed_port=True)
