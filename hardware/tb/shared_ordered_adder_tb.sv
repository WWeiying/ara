module shared_ordered_adder_case #(parameter int Units = 1, parameter int Clients = 4)(output logic done_o);
  import ara_pkg::*;
  import fpnew_pkg::*;
  logic clk = 0;
  always #5 clk = !clk;
  logic rst_n = 0;
  ordered_add_request_t [Clients-1:0] request;
  ordered_add_response_t [Clients-1:0] response;
  logic [Clients-1:0] valid, ready, out_valid, out_ready, accepted_last;
  ordered_add_response_t [Clients-1:0] reference_response;
  logic [Clients-1:0] reference_valid, reference_ready;
  int accepted[Clients], retired[Clients], stalls[Clients], multirequest_cycles, checked;
  logic [31:0] rng;
  localparam fpu_features_t Features = '{Width:64, EnableVectors:0, EnableNanBox:0,
    FpFmtMask:6'b111000, IntFmtMask:4'b0111};
  localparam fpu_implementation_t Impl = '{
    PipeRegs:'{'{default:1},'{default:0},'{default:0},'{default:0},'{default:0}},
    UnitTypes:'{'{default:PARALLEL},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED},'{default:DISABLED}},
    PipeConfig:AFTER};
  shared_ordered_adder #(.NrUnits(Units), .NrClients(Clients)) dut (
    .clk_i(clk), .rst_ni(rst_n), .request_i(request), .valid_i(valid), .ready_o(ready),
    .response_o(response), .response_valid_o(out_valid), .response_ready_i(out_ready));
`ifdef ARA_RED_TEST_LEGACY_EQUIVALENCE
  ordered_add_response_t [Clients-1:0] legacy_response;
  logic [Clients-1:0] legacy_ready, legacy_valid;
  shared_ordered_adder_legacy #(.NrUnits(Units), .NrClients(Clients)) legacy (
    .clk_i(clk), .rst_ni(rst_n), .request_i(request), .valid_i(valid), .ready_o(legacy_ready),
    .response_o(legacy_response), .response_valid_o(legacy_valid), .response_ready_i(out_ready));
  always @(posedge clk) if (rst_n) begin
    if (ready !== legacy_ready || out_valid !== legacy_valid)
      $fatal(1,"cycle-level handshake mismatch units=%0d clients=%0d",Units,Clients);
    for (int lane=0; lane<Clients; lane++)
      if (out_valid[lane] && response[lane] !== legacy_response[lane])
        $fatal(1,"cycle-level payload mismatch units=%0d lane=%0d",Units,lane);
  end
`endif
  // Independent per-Lane arithmetic and scoreboards remove arbitration from
  // the reference. A reference accepts exactly the request the DUT accepted.
  for (genvar lane = 0; lane < Clients; lane++) begin : gen_reference
    ordered_add_response_t expected[$];
    fpnew_top #(.Features(Features), .Implementation(Impl), .TagType(logic[8:0]),
      .TrueSIMDClass(1), .EnableSIMDMask(1)) reference_add (
      .clk_i(clk), .rst_ni(rst_n), .hart_id_i('0), .flush_i(1'b0),
      .rnd_mode_i(request[lane].rm), .op_i(ADD), .op_mod_i(1'b0), .vectorial_op_i(1'b0),
      .operands_i(request[lane].operands), .tag_i(request[lane].tag), .simd_mask_i(request[lane].mask),
      .src_fmt_i(request[lane].src_fmt), .dst_fmt_i(request[lane].dst_fmt), .int_fmt_i(INT64),
      .in_valid_i(valid[lane] && ready[lane]), .in_ready_o(reference_ready[lane]),
      .result_o(reference_response[lane].result), .status_o(reference_response[lane].status),
      .tag_o(reference_response[lane].tag), .out_valid_o(reference_valid[lane]),
      .out_ready_i(1'b1), .busy_o());
    always @(posedge clk) begin
      if (!rst_n) begin
        expected.delete();
        accepted[lane] = 0; retired[lane] = 0; stalls[lane] = 0;
        accepted_last[lane] = 0;
      end else begin
        accepted_last[lane] = valid[lane] && ready[lane];
        if (accepted_last[lane]) begin
          if (!reference_ready[lane]) $fatal(1,"reference overflow");
          accepted[lane]++;
        end
        if (valid[lane] && !ready[lane]) stalls[lane]++;
        if (reference_valid[lane]) expected.push_back(reference_response[lane]);
        if (out_valid[lane] && out_ready[lane]) begin
          ordered_add_response_t value;
          if (!expected.size()) $fatal(1,"unsolicited or early result unit=%0d lane=%0d",Units,lane);
          value = expected.pop_front();
          if (value !== response[lane]) $fatal(1,"owner/data/tag/flags mismatch units=%0d lane=%0d",Units,lane);
          retired[lane]++;
        end
      end
    end
  end
  function automatic logic [31:0] step(input logic [31:0] x);
    x ^= x << 13; x ^= x >> 17; x ^= x << 5; return x;
  endfunction
  function automatic logic [63:0] pattern(input fp_format_e fmt, input int kind, input logic [63:0] random_bits);
    logic [63:0] expmask, signmask;
    expmask = ((64'b1 << exp_bits(fmt))-1) << man_bits(fmt);
    signmask = 64'b1 << (fp_width(fmt)-1);
    case(kind % 8)
      0: return 0;
      1: return signmask;
      2: return expmask; // +Inf
      3: return expmask | signmask;
      4: return expmask | 1; // sNaN
      5: return expmask | (64'b1 << (man_bits(fmt)-1)); // qNaN
      6: return 1; // Smallest subnormal.
      default: return random_bits;
    endcase
  endfunction
  initial begin
    done_o = 0; valid = 0; out_ready = 0; request = '0; accepted_last = 0;
    rng = 32'hcd035211 ^ Units; multirequest_cycles = 0;
    repeat(3) @(negedge clk);
    rst_n = 1;
    for(int cycle=0; cycle<6000; cycle++) begin
      // Reset discards outstanding responses, then all four producers restart.
      if (cycle==2500) begin rst_n=0; valid=0; end
      if (cycle==2503) rst_n=1;
      for(int lane=0; lane<Clients; lane++) begin
        rng=step(rng);
        out_ready[lane] = cycle>=5800 || (rng[0] && (cycle%256 >= 24 || lane!=1));
        if (rst_n && (!valid[lane] || accepted_last[lane])) begin
          valid[lane] = cycle<5500 && (cycle<100 || rng[2]);
          request[lane].src_fmt = lane==4 ? FP64 : (cycle%3==0 ? FP16 : (cycle%3==1 ? FP32 : FP64));
          request[lane].dst_fmt = request[lane].src_fmt;
          request[lane].int_fmt = INT64;
          request[lane].rm = roundmode_e'(rng%5);
          request[lane].tag = 9'(rng);
          request[lane].mask = rng[7];
          for(int op=0; op<3; op++) begin
            rng=step(rng);
            request[lane].operands[op] = pattern(request[lane].src_fmt,cycle+lane+op,{rng,~rng});
          end
        end
      end
      if ($countones(valid)>1 && rst_n) multirequest_cycles++;
      @(negedge clk);
    end
    checked=0;
    for(int lane=0; lane<Clients; lane++) begin
      if (accepted[lane]!=retired[lane] || accepted[lane]<100 || stalls[lane]<100)
        $fatal(1,"drain/fairness/coverage failure units=%0d lane=%0d accepted=%0d retired=%0d stalls=%0d",Units,lane,accepted[lane],retired[lane],stalls[lane]);
      checked+=retired[lane];
    end
    if(multirequest_cycles<100) $fatal(1,"missing arbitration pressure");
    $display("SHARED_ORDERED_CASE_PASS units=%0d clients=%0d checked_after_reset=%0d concurrent_cycles=%0d",Units,Clients,checked,multirequest_cycles);
    done_o=1;
  end
endmodule

module shared_ordered_adder_tb;
  logic one_done, two_done;
  shared_ordered_adder_case #(.Units(1)) one(one_done);
  shared_ordered_adder_case #(.Units(2)) two(two_done);
`ifdef ARA_RED_TEST_COMPLETION_CLIENT
  logic five_one_done, five_two_done;
  shared_ordered_adder_case #(.Units(1),.Clients(5)) five_one(five_one_done);
  shared_ordered_adder_case #(.Units(2),.Clients(5)) five_two(five_two_done);
  wire all_done=one_done && two_done && five_one_done && five_two_done;
`else
  wire all_done=one_done && two_done;
`endif
  initial begin wait(all_done); $display("SHARED_ORDERED_ADDER_PASS"); $finish; end
  initial begin #1000000; $fatal(1,"shared ordered unit timeout"); end
endmodule
