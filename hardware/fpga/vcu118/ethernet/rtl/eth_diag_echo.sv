// Diagnostic L2 echo AFTER the MAC's good-frame RX FIFO. FCS is not in this stream.
// One frame at a time, no throughput guarantee; Ethernet download is a later stage.
module eth_diag_echo #(
  parameter [47:0] LOCAL_MAC = 48'h020000000118,
  parameter integer MAX_BYTES = 1514
) (
  input wire clk,
  input wire reset,
  input wire enable,
  input wire [7:0] s_data,
  input wire s_valid,
  input wire s_last,
  output wire s_ready,
  output wire [7:0] m_data,
  output wire m_valid,
  output wire m_last,
  input wire m_ready,
  output reg seen_frame = 0,
  output reg sent_frame = 0,
  output reg rejected_frame = 0
);
  localparam [1:0] RECEIVE = 0, CHECK = 1, FETCH = 2, TRANSMIT = 3;
  localparam integer WIDTH = $clog2(MAX_BYTES + 1);
  reg [1:0] state = RECEIVE;
  (* ram_style = "block" *) reg [7:0] memory [0:MAX_BYTES-1];
  reg [WIDTH-1:0] length = 0, tx_index = 0;
  reg [47:0] destination = 0, source = 0;
  reg [15:0] ethertype = 0;
  reg eligible = 0, overflow = 0;
  reg [7:0] tx_data = 0;
  wire [WIDTH-1:0] read_index = tx_index < 6 ? tx_index + 6 :
                                       tx_index < 12 ? tx_index - 6 : tx_index;
  assign s_ready = state == RECEIVE;
  assign m_valid = state == TRANSMIT;
  assign m_data = tx_data;
  assign m_last = tx_index == length - 1'b1;

  // Separate synchronous RAM process preserves block-RAM inference.
  always @(posedge clk) begin
    if (s_valid && s_ready && length < MAX_BYTES) memory[length] <= s_data;
    if (state == FETCH) tx_data <= memory[read_index];
  end
  always @(posedge clk) begin
    if (reset) begin
      state <= RECEIVE;
      length <= 0;
      tx_index <= 0;
      destination <= 0;
      source <= 0;
      ethertype <= 0;
      eligible <= 0;
      overflow <= 0;
      seen_frame <= 0;
      sent_frame <= 0;
      rejected_frame <= 0;
    end else begin
      case (state)
        RECEIVE: if (s_valid) begin
          if (length == 0) eligible <= enable;
          else if (!enable) eligible <= 0;
          if (length < 6) destination <= {destination[39:0], s_data};
          else if (length < 12) source <= {source[39:0], s_data};
          else if (length < 14) ethertype <= {ethertype[7:0], s_data};
          if (length < MAX_BYTES) length <= length + 1'b1;
          else overflow <= 1;
          if (s_last) begin
            seen_frame <= 1;
            state <= CHECK;
          end
        end
        CHECK: begin
          tx_index <= 0;
          if (eligible && enable && !overflow && length >= 60 &&
              destination == LOCAL_MAC && source != 0 && !source[40] &&
              source != LOCAL_MAC && ethertype == 16'h88b5) state <= FETCH;
          else begin
            rejected_frame <= 1;
            length <= 0;
            overflow <= 0;
            state <= RECEIVE;
          end
        end
        FETCH: state <= TRANSMIT;
        TRANSMIT: if (m_ready) begin
          if (m_last) begin
            sent_frame <= 1;
            length <= 0;
            overflow <= 0;
            state <= RECEIVE;
          end else begin
            tx_index <= tx_index + 1'b1;
            state <= FETCH;
          end
        end
        default: state <= RECEIVE;
      endcase
    end
  end
endmodule
