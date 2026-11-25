// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module cva6_single_branch_checks #(parameter bit Compressed = 1)(output logic done=0);
  import ariane_pkg::*;
  function automatic config_pkg::cva6_cfg_t configuration();
    config_pkg::cva6_cfg_t c;
    c = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
    c.SuperscalarEn = 0;
    c.NrIssuePorts = 1;
    c.RVC = Compressed;
    return c;
  endfunction
  localparam config_pkg::cva6_cfg_t CVA6Cfg = configuration();
  `include "branch_types.svh"
  logic clk_i=0, rst_ni=1, v_i=0, debug_mode_i=0;
  fu_data_t [0:0] fu_data_i;
  logic [0:0] alu_valid_i, branch_valid_i, csr_valid_i, aes_valid_i;
  logic [0:0][CVA6Cfg.VLEN-1:0] rs1_forwarding_i='0, rs2_forwarding_i='0;
  logic [CVA6Cfg.VLEN-1:0] pc_i;
  logic is_zcmt_i=0, is_compressed_instr_i;
  branchpredict_sbe_t branch_predict_i;
  bp_resolve_t resolved_branch_o, old_resolved;
  exception_t flu_exception_o, old_exception;
  logic resolve_branch_o, old_resolve, branch_comp_o, old_comp;
  logic [CVA6Cfg.VLEN-1:0] branch_result_o, old_result;
  int checks=0, invalid_checks=0, poison_checks=0, op_count[8];
  logic [63:0] edges[12] = '{0, 1, 2, 64'h7ffffffffffffffe,
      64'h7fffffffffffffff, 64'h8000000000000000, 64'h8000000000000001,
      64'hffffffffffffffff, 64'hfffffffffffffffe, 64'h100000000,
      64'h100000001, 64'hffffffff};
  fu_op ops[8] = '{EQ, NE, LTS, GES, LTU, GEU, ADD, JALR};

  cva6_branch_slice #(.CVA6Cfg(CVA6Cfg), .fu_data_t(fu_data_t),
      .branchpredict_sbe_t(branchpredict_sbe_t), .bp_resolve_t(bp_resolve_t),
      .exception_t(exception_t)) dut (.*);
  cva6_branch_slice_old #(.CVA6Cfg(CVA6Cfg), .fu_data_t(fu_data_t),
      .branchpredict_sbe_t(branchpredict_sbe_t), .bp_resolve_t(bp_resolve_t),
      .exception_t(exception_t)) reference_path (
      .clk_i, .rst_ni, .v_i, .debug_mode_i, .fu_data_i, .alu_valid_i,
      .branch_valid_i, .csr_valid_i, .aes_valid_i, .rs1_forwarding_i,
      .rs2_forwarding_i, .pc_i, .is_zcmt_i, .is_compressed_instr_i,
      .branch_predict_i, .resolved_branch_o(old_resolved),
      .flu_exception_o(old_exception), .resolve_branch_o(old_resolve),
      .branch_result_o(old_result), .branch_comp_o(old_comp));

  function automatic logic compare_oracle(fu_op op, logic [63:0] a, b);
    case (op)
      EQ: return a == b;
      NE: return a != b;
      LTS: return $signed(a) < $signed(b);
      GES: return $signed(a) >= $signed(b);
      LTU: return a < b;
      GEU: return a >= b;
      default: return 1;
    endcase
  endfunction

  task automatic check(input bit poisoned=0);
    logic taken, mispredict, ex_valid;
    logic [CVA6Cfg.VLEN-1:0] target, next_pc;
    cf_t cf;
    #1;
    if ({resolved_branch_o,flu_exception_o,resolve_branch_o,branch_result_o} !==
        {old_resolved,old_exception,old_resolve,old_result})
      $fatal(1,"BRANCH_PAIR_MISMATCH rvc=%0d check=%0d op=%0d valid=%b a=%h b=%h new=%h old=%h",
             Compressed,checks,fu_data_i[0].operation,branch_valid_i,
             fu_data_i[0].operand_a,fu_data_i[0].operand_b,resolved_branch_o,old_resolved);
    if ($isunknown({resolved_branch_o,flu_exception_o,resolve_branch_o,branch_result_o}))
      $fatal(1,"Unknown branch-unit visible output");
    next_pc = pc_i + (is_compressed_instr_i ? 2 : 4);
    if (branch_result_o !== next_pc || resolve_branch_o !== branch_valid_i[0] ||
        resolved_branch_o.valid !== branch_valid_i[0]) $fatal(1,"Branch validity/link result oracle");
    if (!poisoned) begin
      taken = compare_oracle(fu_data_i[0].operation,fu_data_i[0].operand_a,fu_data_i[0].operand_b);
      if (branch_comp_o !== taken)
        $fatal(1,"RAW_COMPARE_MISMATCH rvc=%0d check=%0d op=%0d a=%h b=%h got=%b want=%b enables=%b%b%b%b",
               Compressed,checks,fu_data_i[0].operation,fu_data_i[0].operand_a,
               fu_data_i[0].operand_b,branch_comp_o,taken,alu_valid_i,branch_valid_i,csr_valid_i,aes_valid_i);
      if (branch_valid_i[0] && old_comp !== taken) $fatal(1,"Old ALU disagrees with independent oracle");
    end
    if (!branch_valid_i[0]) begin
      if (resolved_branch_o.is_taken !== 0 || resolved_branch_o.is_mispredict !== 0 ||
          resolved_branch_o.target_address !== '0 || flu_exception_o.valid !== 0)
        $fatal(1,"Invalid branch affected redirect or exception");
      invalid_checks++;
      if (poisoned) poison_checks++;
    end else begin
      target = (fu_data_i[0].operation == JALR ? fu_data_i[0].operand_a : pc_i) + fu_data_i[0].imm;
      if (fu_data_i[0].operation == JALR) target[0]=0;
      cf = branch_predict_i.cf;
      mispredict=0;
      if (fu_data_i[0].operation inside {EQ,NE,LTS,GES,LTU,GEU}) begin
        cf=Branch;
        mispredict=taken != (branch_predict_i.cf == Branch);
      end else if (fu_data_i[0].operation == JALR &&
                   (branch_predict_i.cf == NoCF || target != branch_predict_i.predict_address)) begin
        mispredict=1;
        if (branch_predict_i.cf != Return) cf=JumpR;
      end
      ex_valid = !Compressed && (|target[1:0]) && taken;
      if (resolved_branch_o.target_address !== (taken ? target : next_pc) ||
          resolved_branch_o.is_taken !== taken || resolved_branch_o.is_mispredict !== mispredict ||
          resolved_branch_o.cf_type !== cf || flu_exception_o.valid !== ex_valid)
        $fatal(1,"Target/prediction/exception oracle check=%0d",checks);
    end
    checks++;
  endtask

  task automatic drive(input int op_index, input logic [63:0] a,b, input int mode);
    fu_data_i='0;
    fu_data_i[0].fu=CTRL_FLOW;
    fu_data_i[0].operation=ops[op_index];
    fu_data_i[0].operand_a=a;
    fu_data_i[0].operand_b=b;
    // Includes forward/backward offsets, all alignment classes and overflow.
    fu_data_i[0].imm=64'(mode%17)-8;
    pc_i=CVA6Cfg.VLEN'(64'h3ffffffffc + 4*(mode%7));
    is_compressed_instr_i=Compressed && mode[0];
    branch_valid_i=mode[0];
    alu_valid_i=mode[1]; csr_valid_i=mode[2]; aes_valid_i=mode[3];
    branch_predict_i.cf=cf_t'((mode/2)%5);
    branch_predict_i.predict_address=(mode%3 == 0) ?
        CVA6Cfg.VLEN'((ops[op_index] == JALR ? a : pc_i) + fu_data_i[0].imm) & ~CVA6Cfg.VLEN'(1) : pc_i;
    check();
    op_count[op_index]++;
  endtask

  initial begin
    if (CVA6Cfg.XLEN != 64 || CVA6Cfg.SuperscalarEn || CVA6Cfg.NrIssuePorts != 1)
      $fatal(1,"Not the intended RV64 single-issue configuration");
    if ($test$plusargs("NEGATIVE_CONTROL")) force dut.branch_comp_res=1'b0;
    for (int op=0;op<8;op++) begin
      foreach (edges[a]) foreach (edges[b])
        for (int enables=0;enables<16;enables++) drive(op,edges[a],edges[b],enables);
      for (int bit_index=0;bit_index<64;bit_index++) begin
        // Equal values, only one low/high bit different, both orderings.
        for (int enables=0;enables<16;enables++) begin
          drive(op,64'b1<<bit_index,64'b1<<bit_index,enables);
          drive(op,0,64'b1<<bit_index,enables);
          drive(op,64'b1<<bit_index,0,enables);
          drive(op,~(64'b1<<bit_index),'1,enables);
        end
      end
    end
    // No valid branch may expose arbitrary/X input bits as a redirect/exception.
    for (int enables=0;enables<8;enables++) begin
      branch_valid_i=0;
      {aes_valid_i,csr_valid_i,alu_valid_i}=3'(enables);
      fu_data_i='x;
      check(1);
    end
    foreach (op_count[i]) if (op_count[i] != 6400) $fatal(1,"Missing operation coverage");
    $display("SINGLE_BRANCH_PASS rvc=%0d checks=%0d invalid=%0d poison=%0d ops=%p",
             Compressed,checks,invalid_checks,poison_checks,op_count);
    done=1;
  end
endmodule

module cva6_single_branch_tb;
  wire [1:0] done;
  cva6_single_branch_checks #(.Compressed(1)) rvc_on(done[0]);
  cva6_single_branch_checks #(.Compressed(0)) rvc_off(done[1]);
  initial begin wait (&done); $display("SINGLE_BRANCH_MATRIX_PASS"); $finish; end
  initial begin #1000000; $fatal(1,"Bounded component watchdog"); end
endmodule
