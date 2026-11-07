"""Registered optional scale-port edit of the frozen accumulator/controller.

Generate isolated build inputs. Never overwrite a source consumed by the live
SoC campaigns, and never change the original per-accumulator FP operation order.
"""
import hashlib

from audit import require

ACC_SHA='13a400d7daa62779e6f829237365c4df7b31fbd4f2f6024491c1fb59468f4d60'
COMPUTE_SHA='f8cdc47107dd434743d30c0372f4dba029a91b2cfc7f931ca6c3e11b9203546a'


def accumulator(source):
    require(hashlib.sha256(source.encode()).hexdigest()==ACC_SHA,'Frozen accumulator identity differs')
    text=source;edits=[]
    def edit(old,new):
        nonlocal text
        require(text.count(old)==1,'Exact scale integration anchor required: '+old[:60])
        text=text.replace(old,new,1);edits.append(dict(before=old,after=new))
    edit('  parameter bit RawSeedEnable = 1\'b0',
         '  parameter bit RawSeedEnable = 1\'b0,\n  parameter bit MixedScaleIssue = 1\'b0')
    anchor='  wire request_half_scale = HalfScaleIssue &&'
    edit(anchor,'''  logic [3:0] mixed_rr_q, mixed_index, mixed_upper_index, mixed_lower_index;
  logic [NumEntries-1:0] mixed_upper, mixed_lower;
  logic mixed_upper_empty, mixed_lower_empty, mixed_found;
  logic mixed_fire, mixed_out_valid, mixed_busy, mixed_eligible;
  logic [31:0] mixed_weight, mixed_result;
  logic [4:0] mixed_flags;
  fp_tag_t mixed_tag_out;

  function automatic logic mixed_scale_admitted(input logic [31:0] a, w);
    logic [8:0] base;
    base = {1'b0,a[30:23]} + {1'b0,w[30:23]} - 9'd127;
    return a[30:23] != 0 && a[30:23] != 8'hff &&
           w[30:23] >= 8'd103 && w[30:23] <= 8'd142 &&
           w[12:0] == 0 && base >= 9'd1 && base <= 9'd252;
  endfunction

'''+anchor)
    edit('    wire eligible = ready_entry && (!SplitIssue || !is_cast) && !is_half_scale;',
         '''    wire is_scale = entry_state_q[entry] inside {FP_SCALE_MULTIPLY, FP_MIN_SCALE_MULTIPLY};
    wire [31:0] scale_weight = entry_state_q[entry] == FP_MIN_SCALE_MULTIPLY
        ? entry_min_scale_value_q[entry] : entry_scale_value_q[entry];
    wire use_mixed = MixedScaleIssue && is_scale && !is_half_scale &&
                     mixed_scale_admitted(entry_work_value_q[entry],scale_weight);
    wire eligible = ready_entry && (!SplitIssue || !is_cast) && !is_half_scale && !use_mixed;
    assign mixed_upper[entry] = ready_entry && use_mixed && 4'(entry) >= mixed_rr_q;
    assign mixed_lower[entry] = ready_entry && use_mixed && 4'(entry) < mixed_rr_q;''')
    anchor='  function automatic logic [31:0] fp16_to_fp32(input logic [15:0] value);'
    edit(anchor,'''  lzc #(.WIDTH(NumEntries), .MODE(1'b0)) i_mixed_upper (
    .in_i(mixed_upper), .cnt_o(mixed_upper_index), .empty_o(mixed_upper_empty));
  lzc #(.WIDTH(NumEntries), .MODE(1'b0)) i_mixed_lower (
    .in_i(mixed_lower), .cnt_o(mixed_lower_index), .empty_o(mixed_lower_empty));
  assign mixed_found = !mixed_upper_empty || !mixed_lower_empty;
  assign mixed_index = !mixed_upper_empty ? mixed_upper_index : mixed_lower_index;
  assign mixed_fire = mixed_found && rst_ni && !clear_i;
  assign mixed_weight = entry_state_q[mixed_index] == FP_MIN_SCALE_MULTIPLY
      ? entry_min_scale_value_q[mixed_index] : entry_scale_value_q[mixed_index];

  if (MixedScaleIssue) begin : gen_mixed_scale_port
    qbs_fp16_f32_scale #(.TagWidth(4)) i_scale (
      .clk_i, .rst_ni, .clear_i, .valid_i(mixed_fire),
      .activation_i(entry_work_value_q[mixed_index]), .weight_i(mixed_weight), .tag_i(mixed_index),
      .eligible_o(mixed_eligible), .valid_o(mixed_out_valid), .result_o(mixed_result),
      .fflags_o(mixed_flags), .tag_o(mixed_tag_out), .busy_o(mixed_busy)
    );
  end else begin : gen_no_mixed_scale_port
    assign mixed_eligible = 1'b0;
    assign mixed_out_valid = 1'b0;
    assign mixed_result = '0;
    assign mixed_flags = '0;
    assign mixed_tag_out = '0;
    assign mixed_busy = 1'b0;
  end

'''+anchor)
    edit('assign busy_o = (|entry_valid_q) || fp_busy || cast_busy || half_busy;',
         'assign busy_o = (|entry_valid_q) || fp_busy || cast_busy || half_busy || mixed_busy;')
    edit('  wire write_accumulator = rst_ni && !clear_i && fp_out_valid &&',
         '''  wire [AccIndexWidth-1:0] mixed_accumulator_index = entry_accumulator_index_q[mixed_tag_out];
  wire write_accumulator = rst_ni && !clear_i && fp_out_valid &&''')
    edit("      half_rr_q <= '0;\n      fflags_q <= '0;", "      half_rr_q <= '0;\n      mixed_rr_q <= '0;\n      fflags_q <= '0;")
    edit("        half_rr_q <= '0;\n        fflags_q <= '0;", "        half_rr_q <= '0;\n        mixed_rr_q <= '0;\n        fflags_q <= '0;")
    edit('''        if (fp_fire || cast_fire || half_fire)
          fp_uop_issue_o <= fp_uop_issue_o + 32'(fp_fire) + 32'(cast_fire) + 32'(half_fire);
        if (fp_out_valid || cast_out_valid)
          fflags_q <= fflags_q |
              (fp_out_valid ? fflags_t'(fp_status) : 5'b0) |
              (cast_out_valid ? fflags_t'(cast_status) : 5'b0);''',
         '''        if (mixed_fire) begin
          entry_inflight_q[mixed_index] <= 1'b1;
          mixed_rr_q <= mixed_index + 1'b1;
        end
        if (fp_fire || cast_fire || half_fire || mixed_fire)
          fp_uop_issue_o <= fp_uop_issue_o + 32'(fp_fire) + 32'(cast_fire) + 32'(half_fire) + 32'(mixed_fire);
        if (fp_out_valid || cast_out_valid || mixed_out_valid)
          fflags_q <= fflags_q |
              (fp_out_valid ? fflags_t'(fp_status) : 5'b0) |
              (cast_out_valid ? fflags_t'(cast_status) : 5'b0) |
              (mixed_out_valid ? mixed_flags : 5'b0);''')
    anchor='        if (half_out_valid) begin\n          entry_inflight_q[half_tag_out] <= 1\'b0;'
    edit(anchor,'''        if (mixed_out_valid) begin
          entry_inflight_q[mixed_tag_out] <= 1'b0;
          if (entry_state_q[mixed_tag_out] == FP_SCALE_MULTIPLY) begin
            entry_scale_value_q[mixed_tag_out] <= mixed_result;
            if (!entry_affine_q[mixed_tag_out])
              entry_work_value_q[mixed_tag_out] <= entry_first_block_q[mixed_tag_out]
                  ? '0 : accumulator_data_q[mixed_accumulator_index[2:0]][mixed_accumulator_index[6:3]];
            entry_state_q[mixed_tag_out] <= entry_affine_q[mixed_tag_out]
                ? FP_MIN_SCALE_MULTIPLY : FP_ACCUMULATE_DOT;
          end else begin
            entry_min_scale_value_q[mixed_tag_out] <= mixed_result;
            entry_work_value_q[mixed_tag_out] <= entry_first_block_q[mixed_tag_out]
                ? '0 : accumulator_data_q[mixed_accumulator_index[2:0]][mixed_accumulator_index[6:3]];
            entry_state_q[mixed_tag_out] <= FP_ACCUMULATE_DOT;
          end
        end

'''+anchor)
    anchor='      if (half_fire)\n        issued_state_q[half_index] <= entry_state_q[half_index];'
    edit(anchor,anchor+'''
      if (mixed_fire) begin
        issued_state_q[mixed_index] <= entry_state_q[mixed_index];
        assert (mixed_eligible &&
                (!fp_fire || fp_tag_in != mixed_index) &&
                (!cast_fire || cast_index != mixed_index) &&
                (!half_fire || half_index != mixed_index))
          else $fatal(1,"Mixed scale duplicate issue or invalid admission");
      end
      if (mixed_out_valid) begin
        assert (entry_valid_q[mixed_tag_out] && entry_inflight_q[mixed_tag_out] &&
                entry_state_q[mixed_tag_out] == issued_state_q[mixed_tag_out] &&
                entry_state_q[mixed_tag_out] inside {FP_SCALE_MULTIPLY,FP_MIN_SCALE_MULTIPLY} &&
                (!fp_out_valid || fp_tag_out != mixed_tag_out) &&
                (!cast_out_valid || cast_tag_out != mixed_tag_out) &&
                (!half_out_valid || half_tag_out != mixed_tag_out))
          else $fatal(1,"Mixed scale response ownership/state violation");
      end''')
    restored=text
    for e in reversed(edits):
        require(restored.count(e['after'])==1,'Nonreversible mixed-scale integration')
        restored=restored.replace(e['after'],e['before'],1)
    require(restored==source,'Original accumulator must restore exactly')
    text=text.replace('module qbs_fp_accumulator\n','module qbs_fp_accumulator_mixed\n',1)
    text=text.replace('endmodule : qbs_fp_accumulator','endmodule : qbs_fp_accumulator_mixed',1)
    return text,dict(edits=edits,original_sha256=ACC_SHA,source_reversible=True,
        default_disabled=True,original_fp_order_unchanged=True,legacy_scale_fallback_retained=True,
        result_index_comes_from_mixed_return_tag=True,concurrent_flags_combined_once=True)


def compute(source):
    require(hashlib.sha256(source.encode()).hexdigest()==COMPUTE_SHA,'Frozen compute identity differs')
    old='  parameter bit WideWeightIngress = 1\'b0,'
    new=old+'\n  parameter bit MixedScaleIssue = 1\'b0,'
    require(source.count(old)==1,'Compute parameter anchor')
    text=source.replace(old,new,1)
    old_instance='qbs_fp_accumulator #(.RawSeedEnable(SeedRestoreEnable)) i_fp_accumulator'
    new_instance='qbs_fp_accumulator_mixed #(.RawSeedEnable(SeedRestoreEnable), .MixedScaleIssue(MixedScaleIssue)) i_fp_accumulator'
    require(text.count(old_instance)==1,'Compute accumulator instance anchor')
    text=text.replace(old_instance,new_instance,1)
    require(text.replace(new_instance,old_instance,1).replace(new,old,1)==source,'Compute edit not reversible')
    text=text.replace('module qbs_compute_engine\n','module qbs_compute_engine_mixed\n',1)
    text=text.replace('endmodule : qbs_compute_engine','endmodule : qbs_compute_engine_mixed',1)
    return text,dict(original_sha256=COMPUTE_SHA,source_reversible=True,
                     changes=['One optional parameter','Pass parameter to isolated accumulator'])
