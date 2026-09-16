"""FPGA-only fixes for the measured DDR reset and wide FIFO routing paths."""
import hashlib


def replace(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("FPGA CDC integration source changed: " + old[:80])
    return text.replace(old, new, 1)


RESET_MUXES = """    // bypass mode: use (clock) multiplexers
    tc_clk_mux2 i_tc_clk_mux2_rst_n (
        .clk0_i     ( rst_ni ),
        .clk1_i     ( rst_test_mode_ni ),
        .clk_sel_i  ( test_mode_i ),
        .clk_o      ( rst_n )
    );

    tc_clk_mux2 i_tc_clk_mux2_rst_no (
        .clk0_i     ( synch_regs_q[NumRegs-1] ),
        .clk1_i     ( rst_test_mode_ni ),
        .clk_sel_i  ( test_mode_i ),
        .clk_o      ( rst_no )
    );

    tc_clk_mux2 i_tc_clk_mux2_init_no (
        .clk0_i     ( synch_regs_q[NumRegs-1] ),
        .clk1_i     ( 1'b1 ),
        .clk_sel_i  ( test_mode_i ),
        .clk_o      ( init_no )
    );"""
RESET_LOGIC = """    // These are reset/data muxes, not clocks. tc_clk_mux2 maps to BUFGMUX
    // on Xilinx and prevents constant test_mode_i from removing the bypass.
    // Keep the original asynchronous assertion and NumRegs-cycle release.
    assign rst_n = test_mode_i ? rst_test_mode_ni : rst_ni;
    assign rst_no = test_mode_i ? rst_test_mode_ni : synch_regs_q[NumRegs-1];
    assign init_no = test_mode_i ? 1'b1 : synch_regs_q[NumRegs-1];"""


def patch_reset_muxes(text):
    return replace(text, RESET_MUXES, RESET_LOGIC)


OLD_WRITE = """  always_comb begin
    data_d                          = data_q;
    data_d[wptr_bin[LOG_DEPTH-1:0]] = src_data_i;
  end
  `FFLARN(data_q, data_d, src_valid_i & src_ready_o, '0, src_clk_i, src_rst_ni)"""
NEW_WRITE = """  if (LOG_DEPTH == 5 && $bits(T) >= 128) begin : gen_fpga_write
    // Local one-hot word enables avoid Gray->binary->word decode on the
    // 300 MHz CE path. Each preserved selector drives at most 64 data bits.
    localparam int Depth = 2**LOG_DEPTH;
    localparam int Width = $bits(T);
    localparam int Slice = 64;
    for (genvar s = 0; s < (Width+Slice-1)/Slice; s++) begin : gen_slice
      localparam int Bits = (Width-s*Slice < Slice) ? Width-s*Slice : Slice;
      (* DONT_TOUCH = "TRUE" *) logic [Depth-1:0] select_q;
      always_ff @(posedge src_clk_i or negedge src_rst_ni) begin
        if (!src_rst_ni) select_q <= {{(Depth-1){1'b0}}, 1'b1};
        else if (src_valid_i && src_ready_o)
          select_q <= {select_q[Depth-2:0], select_q[Depth-1]};
      end
      for (genvar word_idx = 0; word_idx < Depth; word_idx++) begin : gen_word
        always_ff @(posedge src_clk_i or negedge src_rst_ni) begin
          if (!src_rst_ni) data_q[word_idx][s*Slice +: Bits] <= '0;
          else if (src_valid_i && src_ready_o && select_q[word_idx])
            data_q[word_idx][s*Slice +: Bits] <= src_data_i[s*Slice +: Bits];
        end
      end
    end
  end else begin : gen_generic_write
    always_comb begin
      data_d = data_q;
      data_d[wptr_bin[LOG_DEPTH-1:0]] = src_data_i;
    end
    `FFLARN(data_q, data_d, src_valid_i & src_ready_o, '0, src_clk_i, src_rst_ni)
  end"""

OLD_READ = """  // Data selector and register.
  assign dst_data = async_data_i[rptr_bin[LOG_DEPTH-1:0]];"""
NEW_READ = """  // Preserve the Gray pointer crossing and the spill-register handshake.
  // Only the local wide data selector changes; no additional data latency.
  if (LOG_DEPTH == 5 && $bits(T) >= 128) begin : gen_fpga_read
    localparam int Depth = 2**LOG_DEPTH;
    localparam int Width = $bits(T);
    localparam int Slice = 64;
    for (genvar s = 0; s < (Width+Slice-1)/Slice; s++) begin : gen_slice
      localparam int Bits = (Width-s*Slice < Slice) ? Width-s*Slice : Slice;
      // Replicas must not merge back into one high-fanout pointer decoder.
      (* DONT_TOUCH = "TRUE" *) logic [Depth-1:0] select_q;
      logic [Bits-1:0] selected;
      always_ff @(posedge dst_clk_i or negedge dst_rst_ni) begin
        if (!dst_rst_ni) select_q <= {{(Depth-1){1'b0}}, 1'b1};
        else if (dst_valid && dst_ready)
          select_q <= {select_q[Depth-2:0], select_q[Depth-1]};
      end
      // Parallel one-hot reduction, not a priority or binary address mux.
      always_comb begin
        selected = '0;
        for (int word_idx = 0; word_idx < Depth; word_idx++)
          selected |= async_data_i[word_idx][s*Slice +: Bits] & {Bits{select_q[word_idx]}};
      end
      assign dst_data[s*Slice +: Bits] = selected;
    end
  end else begin : gen_generic_read
    assign dst_data = async_data_i[rptr_bin[LOG_DEPTH-1:0]];
  end"""


def patch_fifo_selectors(text):
    # Changes to the pointer/full/empty protocol need a new equivalence review.
    if hashlib.sha256(text.encode()).hexdigest() != \
            "1592390f962a957869ecb55e93e3ebfa2dfec61070ea2b7a60624cd42aa40835":
        raise RuntimeError("FPGA FIFO integration requires the reviewed cdc_fifo_gray source")
    return replace(replace(text, OLD_WRITE, NEW_WRITE), OLD_READ, NEW_READ)
