`timescale 1ns/1ps

module qbs_commit_tb;
  import qbs_pkg::*;

  localparam int unsigned NrLanes = 4;
  localparam int unsigned VLEN = 1024;
  localparam int unsigned WordsPerRegister = VLEN / 8 / (NrLanes * 8);

  typedef logic [2:0] vid_t;
  typedef logic [9:0] vaddr_t;

  logic clk;
  logic rst_n;
  logic start_valid;
  logic start_ready;
  vid_t start_id;
  logic [4:0] start_vd;
  logic [2:0] start_m;
  logic [5:0] start_n;
  logic [3:0] bank_row;
  logic [7:0] bank_valid;
  logic [31:0] bank_data [8];
  logic [NrLanes-1:0] result_req;
  vid_t [NrLanes-1:0] result_id;
  vaddr_t [NrLanes-1:0] result_addr;
  logic [63:0] result_wdata [NrLanes];
  logic [7:0] result_be [NrLanes];
  logic [NrLanes-1:0] result_gnt;
  logic [NrLanes-1:0] result_final_gnt;
  logic done_valid;
  logic done_ready;
  logic busy;
  logic [31:0] commit_word_count;
  logic [31:0] commit_backpressure_cycles;

  qbs_commit #(
    .NrLanes (NrLanes),
    .VLEN    (VLEN),
    .vid_t   (vid_t),
    .vaddr_t (vaddr_t)
  ) dut (
    .clk_i                         (clk),
    .rst_ni                        (rst_n),
    .start_valid_i                 (start_valid),
    .start_ready_o                 (start_ready),
    .start_id_i                    (start_id),
    .start_vd_i                    (start_vd),
    .start_m_i                     (start_m),
    .start_n_i                     (start_n),
    .accumulator_bank_row_o        (bank_row),
    .accumulator_bank_valid_i      (bank_valid),
    .accumulator_bank_data_i       (bank_data),
    .ldu_result_req_o              (result_req),
    .ldu_result_id_o               (result_id),
    .ldu_result_addr_o             (result_addr),
    .ldu_result_wdata_o            (result_wdata),
    .ldu_result_be_o               (result_be),
    .ldu_result_gnt_i              (result_gnt),
    .ldu_result_final_gnt_i        (result_final_gnt),
    .done_valid_o                  (done_valid),
    .done_ready_i                  (done_ready),
    .busy_o                        (busy),
    .commit_word_count_o           (commit_word_count),
    .commit_backpressure_cycles_o  (commit_backpressure_cycles)
  );

  always #5 clk = ~clk;

  logic [2:0] model_m;
  logic [5:0] model_n;
  logic [4:0] model_vd;
  vid_t model_id;

  function automatic logic [31:0] accumulator_value(input integer index);
    return 32'h3f00_0000 + index;
  endfunction

  always_comb begin
    for (int unsigned bank = 0; bank < 8; bank++) begin
      automatic int unsigned index = unsigned'(bank_row) * 8 + bank;
      bank_data[bank] = accumulator_value(index);
      bank_valid[bank] = (index % QbsMaxN) < unsigned'(model_n);
    end
  end

  logic use_grant_backpressure;
  logic [7:0] grant_cycle;
  logic [NrLanes-1:0] final_pending;
  logic [2:0] final_delay [NrLanes];

  always_comb begin
    result_gnt = '1;
    if (use_grant_backpressure) begin
      for (int unsigned lane = 0; lane < NrLanes; lane++)
        result_gnt[lane] = ((unsigned'(grant_cycle) + lane) % 3) != 0;
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      grant_cycle <= '0;
      final_pending <= '0;
      result_final_gnt <= '0;
      for (int unsigned lane = 0; lane < NrLanes; lane++)
        final_delay[lane] <= '0;
    end else begin
      grant_cycle <= grant_cycle + 1'b1;
      result_final_gnt <= '0;
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        if (result_req[lane] && result_gnt[lane]) begin
          final_pending[lane] <= 1'b1;
          final_delay[lane] <= 3'(lane + 1);
        end else if (final_pending[lane]) begin
          if (final_delay[lane] == 0) begin
            result_final_gnt[lane] <= 1'b1;
            final_pending[lane] <= 1'b0;
          end else begin
            final_delay[lane] <= final_delay[lane] - 1'b1;
          end
        end
      end
    end
  end

  logic score_reset;
  logic [31:0] request_count;
  logic [31:0] zero_tail_words;

  always_ff @(posedge clk or negedge rst_n) begin : check_commit_payload
    if (!rst_n || score_reset) begin
      request_count <= '0;
      zero_tail_words <= '0;
    end else begin
      request_count <= request_count + $countones(result_req & result_gnt);
      for (int unsigned lane = 0; lane < NrLanes; lane++) begin
        if (result_req[lane] && result_gnt[lane]) begin
          automatic int unsigned word_index;
          automatic int unsigned ctx;
          automatic int unsigned register_word;
          automatic int unsigned low_element;
          automatic int unsigned high_element;
          automatic logic [31:0] expected_low;
          automatic logic [31:0] expected_high;

          word_index = unsigned'(result_addr[lane]) -
                       unsigned'(model_vd) * WordsPerRegister;
          ctx = word_index / WordsPerRegister;
          register_word = word_index % WordsPerRegister;
          low_element = register_word * 8 + lane;
          high_element = low_element + NrLanes;
          expected_low = low_element < unsigned'(model_n)
              ? accumulator_value(ctx * QbsMaxN + low_element) : 32'b0;
          expected_high = high_element < unsigned'(model_n)
              ? accumulator_value(ctx * QbsMaxN + high_element) : 32'b0;

          if (ctx >= unsigned'(model_m))
            $fatal(1, "QBS commit wrote inactive context %0d", ctx);
          if (result_id[lane] != model_id || result_be[lane] != 8'hff ||
              result_wdata[lane] != {expected_high, expected_low})
            $fatal(1, "QBS commit payload mismatch word=%0d lane=%0d",
                   word_index, lane);
          if ((low_element >= unsigned'(model_n)) &&
              (high_element >= unsigned'(model_n)))
            zero_tail_words <= zero_tail_words + 1'b1;
        end
      end
    end
  end

  task automatic run_case(input integer active_m,
                          input integer active_n,
                          input integer vd,
                          input integer id,
                          input logic backpressure);
    integer timeout;
    integer expected_words;

    expected_words = active_m * WordsPerRegister;
    while (!start_ready) @(posedge clk);
    @(negedge clk);
    model_m = active_m[2:0];
    model_n = active_n[5:0];
    model_vd = vd[4:0];
    model_id = id[2:0];
    use_grant_backpressure = backpressure;
    score_reset = 1'b1;
    @(negedge clk);
    score_reset = 1'b0;
    start_m = active_m[2:0];
    start_n = active_n[5:0];
    start_vd = vd[4:0];
    start_id = id[2:0];
    start_valid = 1'b1;
    @(negedge clk);
    start_valid = 1'b0;

    timeout = 0;
    while (!done_valid && timeout < 5000) begin
      @(posedge clk);
      timeout++;
    end
    if (!done_valid)
      $fatal(1, "timeout waiting for QBS commit");
    if (commit_word_count != expected_words ||
        request_count != expected_words * NrLanes)
      $fatal(1, "QBS commit accounting words=%0d/%0d requests=%0d/%0d",
             commit_word_count, expected_words, request_count,
             expected_words * NrLanes);
    if (backpressure && commit_backpressure_cycles == 0)
      $fatal(1, "QBS commit did not record injected backpressure");
    if (active_n < 32 && zero_tail_words == 0)
      $fatal(1, "QBS commit did not write zero tail bytes");

    @(negedge clk);
    done_ready = 1'b1;
    @(negedge clk);
    done_ready = 1'b0;
    use_grant_backpressure = 1'b0;
  endtask

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    start_valid = 1'b0;
    start_id = '0;
    start_vd = '0;
    start_m = '0;
    start_n = '0;
    done_ready = 1'b0;
    model_m = '0;
    model_n = '0;
    model_vd = '0;
    model_id = '0;
    use_grant_backpressure = 1'b0;
    score_reset = 1'b0;

    repeat (4) @(posedge clk);
    rst_n = 1'b1;
    repeat (2) @(posedge clk);

    run_case(1, 32, 3, 1, 1'b0);
    run_case(3, 5, 4, 2, 1'b1);
    run_case(4, 1, 8, 5, 1'b1);

    $display("QBS commit PASS");
    $finish;
  end

endmodule : qbs_commit_tb
