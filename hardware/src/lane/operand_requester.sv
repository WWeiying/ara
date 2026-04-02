// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// This stage is responsible for requesting individual elements from the vector
// register file, in order, and sending them to the corresponding operand
// queues. This stage also includes the VRF arbiter.

module operand_requester import ara_pkg::*; import rvv_pkg::*; #(
    parameter  int  unsigned NrLanes               = 0,
    parameter  int  unsigned VLEN                  = 0,
    parameter  int  unsigned NrBanks               = 0,     // Number of banks in the vector register file
    parameter  type          vaddr_t               = logic, // Type used to address vector register file elements
    parameter  type          operand_request_cmd_t = logic,
    parameter  type          operand_queue_cmd_t   = logic,
    // Dependant parameters. DO NOT CHANGE!
    localparam type          strb_t  = logic[$bits(elen_t)/8-1:0],
    localparam type          vlen_t  = logic[$clog2(VLEN+1)-1:0]
  ) (
    input  logic                                       clk_i,
    input  logic                                       rst_ni,
    // Interface with the main sequencer
    input  logic            [NrVInsn-1:0][NrVInsn-1:0] global_hazard_table_i,
    // Interface with the lane sequencer
    input  operand_request_cmd_t [NrOperandQueues-1:0] operand_request_i,
    input  logic                 [NrOperandQueues-1:0] operand_request_valid_i,
    output logic                 [NrOperandQueues-1:0] operand_request_ready_o,
    // Support for store exception flush
    input  logic                                       lsu_ex_flush_i,
    output logic                                       lsu_ex_flush_o,
    // Interface with the VRF
    output logic                 [NrBanks-1:0]         vrf_req_o,
    output vaddr_t               [NrBanks-1:0]         vrf_addr_o,
    output logic                 [NrBanks-1:0]         vrf_wen_o,
    output elen_t                [NrBanks-1:0]         vrf_wdata_o,
    output strb_t                [NrBanks-1:0]         vrf_be_o,
    output opqueue_e             [NrBanks-1:0]         vrf_tgt_opqueue_o,
    //forward
    output elen_t                [NrOperandQueues-1:0] forward_operand_o,
    output logic                 [NrOperandQueues-1:0] forward_operand_valid_o,
    // Interface with the operand queues
    input  logic                 [NrOperandQueues-1:0] operand_queue_ready_i,
    output logic                 [NrOperandQueues-1:0] operand_issued_o,
    output operand_queue_cmd_t   [NrOperandQueues-1:0] operand_queue_cmd_o,
    output logic                 [NrOperandQueues-1:0] operand_queue_cmd_valid_o,
    // Interface with the VFUs
    // ALU
    input  logic                                       alu_result_req_i,
    input  vid_t                                       alu_result_id_i,
    input  vaddr_t                                     alu_result_addr_i,
    input  elen_t                                      alu_result_wdata_i,
    input  strb_t                                      alu_result_be_i,
    output logic                                       alu_result_gnt_o,
    // Multiplier/FPU
    input  logic                                       mfpu_result_req_i,
    input  vid_t                                       mfpu_result_id_i,
    input  vaddr_t                                     mfpu_result_addr_i,
    input  elen_t                                      mfpu_result_wdata_i,
    input  strb_t                                      mfpu_result_be_i,
    output logic                                       mfpu_result_gnt_o,
    // Mask unit
    input  logic                                       masku_result_req_i,
    input  vid_t                                       masku_result_id_i,
    input  vaddr_t                                     masku_result_addr_i,
    input  elen_t                                      masku_result_wdata_i,
    input  strb_t                                      masku_result_be_i,
    output logic                                       masku_result_gnt_o,
    output logic                                       masku_result_final_gnt_o,
    // Slide unit
    input  logic                                       sldu_result_req_i,
    input  vid_t                                       sldu_result_id_i,
    input  vaddr_t                                     sldu_result_addr_i,
    input  elen_t                                      sldu_result_wdata_i,
    input  strb_t                                      sldu_result_be_i,
    output logic                                       sldu_result_gnt_o,
    output logic                                       sldu_result_final_gnt_o,
    // Load unit
    input  logic                                       ldu_result_req_i,
    input  vid_t                                       ldu_result_id_i,
    input  vaddr_t                                     ldu_result_addr_i,
    input  elen_t                                      ldu_result_wdata_i,
    input  strb_t                                      ldu_result_be_i,
    output logic                                       ldu_result_gnt_o,
    output logic                                       ldu_result_final_gnt_o
  );

  import cf_math_pkg::idx_width;

  ////////////////////////
  //  Stream registers  //
  ////////////////////////

  typedef struct packed {
    vid_t id;
    vaddr_t addr;
    elen_t wdata;
    strb_t be;
  } stream_register_payload_t;

  // Load unit
  vid_t   ldu_result_id;
  vaddr_t ldu_result_addr;
  elen_t  ldu_result_wdata;
  strb_t  ldu_result_be;
  logic   ldu_result_req;
  logic   ldu_result_gnt;
//  stream_register #(.T(stream_register_payload_t)) i_ldu_stream_register (
//    .clk_i     (clk_i                                                                    ),
//    .rst_ni    (rst_ni                                                                   ),
//    .clr_i     (1'b0                                                                     ),
//    .testmode_i(1'b0                                                                     ),
//    .data_i    ({ldu_result_id_i, ldu_result_addr_i, ldu_result_wdata_i, ldu_result_be_i}),
//    .valid_i   (ldu_result_req_i                                                         ),
//    .ready_o   (ldu_result_gnt_o                                                         ),
//    .data_o    ({ldu_result_id, ldu_result_addr, ldu_result_wdata, ldu_result_be}        ),
//    .valid_o   (ldu_result_req                                                           ),
//    .ready_i   (ldu_result_gnt                                                           )
//  );

  fall_through_register_v1 #(
    .T(stream_register_payload_t),
    .DEPTH(1)
  ) i_ldu_stream_register (
    .clk_i     (clk_i             ),
    .rst_ni    (rst_ni            ),
    .clr_i     (1'b0              ),
    .testmode_i(1'b0              ),
    .data_i    ({ldu_result_id_i, ldu_result_addr_i, ldu_result_wdata_i, ldu_result_be_i}),
    .valid_i   (ldu_result_req_i                                                         ),
    .ready_o   (ldu_result_gnt_o                                                         ),
    .data_o    ({ldu_result_id, ldu_result_addr, ldu_result_wdata, ldu_result_be}        ),
    .valid_o   (ldu_result_req                                                           ),
    .ready_i   (ldu_result_gnt                                                           )
  );

  // Slide unit
  vid_t   sldu_result_id;
  vaddr_t sldu_result_addr;
  elen_t  sldu_result_wdata;
  strb_t  sldu_result_be;
  logic   sldu_result_req;
  logic   sldu_result_gnt;
  fall_through_register_v1 #(
    .T(stream_register_payload_t),
    .DEPTH(1)
  ) i_sldu_stream_register (
    .clk_i     (clk_i                                                                        ),
    .rst_ni    (rst_ni                                                                       ),
    .clr_i     (1'b0                                                                         ),
    .testmode_i(1'b0                                                                         ),
    .data_i    ({sldu_result_id_i, sldu_result_addr_i, sldu_result_wdata_i, sldu_result_be_i}),
    .valid_i   (sldu_result_req_i                                                            ),
    .ready_o   (sldu_result_gnt_o                                                            ),
    .data_o    ({sldu_result_id, sldu_result_addr, sldu_result_wdata, sldu_result_be}        ),
    .valid_o   (sldu_result_req                                                              ),
    .ready_i   (sldu_result_gnt                                                              )
  );

  // Mask unit
  vid_t   masku_result_id;
  vaddr_t masku_result_addr;
  elen_t  masku_result_wdata;
  strb_t  masku_result_be;
  logic   masku_result_req;
  logic   masku_result_gnt;
  fall_through_register_v1 #(
    .T(stream_register_payload_t),
    .DEPTH(1)
  ) i_masku_stream_register (
    .clk_i     (clk_i                                                                            ),
    .rst_ni    (rst_ni                                                                           ),
    .clr_i     (1'b0                                                                             ),
    .testmode_i(1'b0                                                                             ),
    .data_i    ({masku_result_id_i, masku_result_addr_i, masku_result_wdata_i, masku_result_be_i}),
    .valid_i   (masku_result_req_i                                                               ),
    .ready_o   (masku_result_gnt_o                                                               ),
    .data_o    ({masku_result_id, masku_result_addr, masku_result_wdata, masku_result_be}        ),
    .valid_o   (masku_result_req                                                                 ),
    .ready_i   (masku_result_gnt                                                                 )
  );

  // The very last grant must happen when the instruction actually write in the VRF
  // Otherwise the dependency is freed in advance
  always_ff @(posedge clk_i or negedge rst_ni) begin : p_final_gnts
    if (!rst_ni) begin
      ldu_result_final_gnt_o   <= 1'b0;
      sldu_result_final_gnt_o  <= 1'b0;
      masku_result_final_gnt_o <= 1'b0;
    end else begin
      ldu_result_final_gnt_o   <= ldu_result_gnt;
      sldu_result_final_gnt_o  <= sldu_result_gnt;
      masku_result_final_gnt_o <= masku_result_gnt;
    end
  end

  `ifdef FOR_VERIFY
  // Count number of active dependencies per instruction from global_hazard_table bitmap
  localparam int unsigned InsnIdWidth = $clog2(NrVInsn);
  // Number of hazard dependencies for each instruction
  logic [NrVInsn-1:0][InsnIdWidth-1:0] global_hazard_count;

  always_comb begin
    global_hazard_count = '0;
    for (int insn_id = 0; insn_id < NrVInsn; insn_id++) begin
      automatic int hazard_cnt = 0;
      for (int hazard_id = 0; hazard_id < NrVInsn; hazard_id++) begin
        if (global_hazard_table_i[insn_id][hazard_id]) begin
          hazard_cnt++;
        end
      end
      global_hazard_count[insn_id] = InsnIdWidth'(hazard_cnt);
    end
  end
  `endif

  ///////////////////////
  //  Stall mechanism  //
  ///////////////////////

  // To handle any type of stall between vector instructions, we ensure
  // that operands of a second instruction that has a hazard on a first
  // instruction are read at the same rate the results of the second
  // instruction are written. Therefore, the second instruction can never
  // overtake the first one.

  // Instruction wrote a result
  logic [NrVInsn-1:0] vinsn_result_written_d, vinsn_result_written_q;
  vaddr_t alu_result_addr_q, mfpu_result_addr_q, masku_result_addr_q, ldu_result_addr_q, sldu_result_addr_q;
  vid_t   alu_result_id_q, mfpu_result_id_q, masku_result_id_q, ldu_result_id_q, sldu_result_id_q;
  logic   alu_result_written_q, mfpu_result_written_q, masku_result_written_q, ldu_result_written_q, sldu_result_written_q;

  always_comb begin
    vinsn_result_written_d = '0;

    // Which vector instructions are writing something?
    vinsn_result_written_d[alu_result_id_i] |= alu_result_gnt_o;
    vinsn_result_written_d[mfpu_result_id_i] |= mfpu_result_gnt_o;
    vinsn_result_written_d[masku_result_id] |= masku_result_gnt;
    vinsn_result_written_d[ldu_result_id] |= ldu_result_gnt;
    vinsn_result_written_d[sldu_result_id] |= sldu_result_gnt;
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin: p_vinsn_result_written_ff
    if (!rst_ni) begin
      vinsn_result_written_q <= '0;
      lsu_ex_flush_o <= 1'b0;
    end else begin
      vinsn_result_written_q <= vinsn_result_written_d;
      lsu_ex_flush_o <= lsu_ex_flush_i;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    // Unified reset branch
    if (!rst_ni) begin
      alu_result_addr_q     <= '0;
      alu_result_id_q       <= '0;
      alu_result_written_q  <= '0;
      mfpu_result_addr_q    <= '0;
      mfpu_result_id_q      <= '0;
      mfpu_result_written_q <= '0;
      masku_result_addr_q   <= '0;
      masku_result_id_q     <= '0;
      masku_result_written_q <= '0;
      ldu_result_addr_q     <= '0;
      ldu_result_id_q       <= '0;
      ldu_result_written_q  <= '0;
      sldu_result_addr_q    <= '0;
      sldu_result_id_q      <= '0;
      sldu_result_written_q <= '0;
    end else begin
      // ALU result logic
      if (alu_result_gnt_o) begin
        alu_result_addr_q   <= alu_result_addr_i;
        alu_result_id_q     <= alu_result_id_i;
        alu_result_written_q <= 1'b1;
      end else begin
        alu_result_written_q <= '0;
      end
      // MFPU result logic
      if (mfpu_result_gnt_o) begin
        mfpu_result_addr_q  <= mfpu_result_addr_i;
        mfpu_result_id_q    <= mfpu_result_id_i;
        mfpu_result_written_q <= 1'b1;
      end else begin
        mfpu_result_written_q <= '0;
      end
      // MASKU result logic
      if (masku_result_gnt) begin
        masku_result_addr_q <= masku_result_addr;
        masku_result_id_q   <= masku_result_id;
        masku_result_written_q <= 1'b1;
      end else begin
        masku_result_written_q <= '0;
      end
      // LDU result logic
      if (ldu_result_gnt) begin
        ldu_result_addr_q   <= ldu_result_addr;
        ldu_result_id_q     <= ldu_result_id;
        ldu_result_written_q <= 1'b1;
      end else begin
        ldu_result_written_q <= '0;
      end
      // SLDU result logic
      if (sldu_result_gnt) begin
        sldu_result_addr_q  <= sldu_result_addr;
        sldu_result_id_q    <= sldu_result_id;
        sldu_result_written_q <= 1'b1;
      end else begin
        sldu_result_written_q <= '0;
      end
    end
  end

  ///////////////////////
  //  Operand request  //
  ///////////////////////

  // There is an operand requester_index for each operand queue. Each one
  // can be in one of the following two states.
  typedef enum logic {
    IDLE,
    REQUESTING
  } state_t;

  // A set bit indicates that the the master q is requesting access to the bank b
  // Masters 0 to NrOperandQueues-1 correspond to the operand queues.
  // The remaining four masters correspond to the ALU, the MFPU, the MASKU, the VLDU, and the SLDU.
  localparam NrGlobalMasters = 5;
  localparam NrMasters = NrOperandQueues + NrGlobalMasters;

  typedef struct packed {
    vaddr_t addr;
    logic wen;
    elen_t wdata;
    strb_t be;
    opqueue_e opqueue;
  } payload_t;

  logic     [NrBanks-1:0][NrOperandQueues-1:0] lane_operand_req;
  logic     [NrOperandQueues-1:0][NrBanks-1:0] lane_operand_req_transposed;
  logic     [NrBanks-1:0][NrGlobalMasters-1:0] ext_operand_req;
  logic     [NrBanks-1:0][NrMasters-1:0] operand_gnt;
  payload_t [NrMasters-1:0]              operand_payload;

  // Metadata required to request all elements of this vector operand
  typedef struct packed {
    // ID of the instruction for this requester_index
    vid_t id;
    // Address of the next element to be read
    vaddr_t addr;
    // How many elements remain to be read
    vlen_t len;
    // Element width
    vew_e vew;

    // Hazards between vector instructions
    logic [NrVInsn-1:0] hazard;

    // Widening instructions produces two writes of every read
    // In case of a WAW with a previous instruction,
    // read once every two writes of the previous instruction
    logic is_widening;
    // One-bit counters
    logic [NrVInsn-1:0] waw_hazard_counter;
  } requester_metadata_t;

  for (genvar b = 0; b < NrBanks; b++) begin
    for (genvar r = 0; r < NrOperandQueues; r++) begin
      assign lane_operand_req[b][r] = lane_operand_req_transposed[r][b];
    end
  end


  // State of this operand requester_index
  state_t [NrOperandQueues-1:0] state_d;
  state_t [NrOperandQueues-1:0] state_q;

  requester_metadata_t [NrOperandQueues-1:0] requester_metadata_d;
  requester_metadata_t [NrOperandQueues-1:0] requester_metadata_q;

  logic [NrOperandQueues-1:0] stall;
  logic [NrOperandQueues-1:0][NrBanks-1:0] operand_requester_gnt;
    
  // Unified forward data signal, supports all sources (LDU/ALU/MFPU/MASK/SLDU)
  elen_t [NrOperandQueues-1:0] forward_data;
  // Forward done flag, asserted when any forward source hits
  logic  [NrOperandQueues-1:0] forward_done;
  logic [NrVInsn-1:0] addr_match_mask[NrOperandQueues];

  for (genvar requester_index = 0; requester_index < NrOperandQueues; requester_index++) begin : gen_operand_requester

    // Did we get a grant?
    for (genvar bank = 0; bank < NrBanks; bank++) begin: gen_operand_requester_gnt
      assign operand_requester_gnt[requester_index][bank] = operand_gnt[bank][requester_index];
    end

    // Did we issue a word to this operand queue? (VRF read grant OR LDU forwarding success)
    assign operand_issued_o[requester_index] = |(operand_requester_gnt[requester_index]) || forward_done[requester_index];

    always_comb begin: operand_requester
      // Helper local variables
      automatic operand_queue_cmd_t  operand_queue_cmd_tmp;
      automatic requester_metadata_t requester_metadata_tmp;
      automatic vlen_t               effective_vector_body_length;
      automatic vaddr_t              vrf_addr;

      automatic elen_t vl_byte;
      automatic elen_t vstart_byte;
      automatic elen_t vector_body_len_byte;
      automatic elen_t scaled_vector_len_elements;

      // Bank we are currently requesting
      automatic int bank = requester_metadata_q[requester_index].addr[idx_width(NrBanks)-1:0];

      stall[requester_index] = '0;

      // Maintain state
      state_d[requester_index]     = state_q[requester_index];
      requester_metadata_d[requester_index] = requester_metadata_q[requester_index];

      // Make no requests to the VRF
      operand_payload[requester_index] = '0;
      for (int b = 0; b < NrBanks; b++) lane_operand_req_transposed[requester_index][b] = 1'b0;

      // Do not acknowledge any operand requester_index commands
      operand_request_ready_o[requester_index] = 1'b0;

      // Do not send any operand conversion commands
      operand_queue_cmd_o[requester_index]       = '0;
      operand_queue_cmd_valid_o[requester_index] = 1'b0;

      // Count the number of packets to fetch if we need to deshuffle.
      // Slide operations use the vstart signal, which does NOT correspond to the architectural
      // vstart, only when computing the fetch address. Ara supports architectural vstart > 0
      // only for memory operations.
      vl_byte     = operand_request_i[requester_index].vl     << operand_request_i[requester_index].vtype.vsew;
      vstart_byte = operand_request_i[requester_index].is_slide
                  ? 0
                  : operand_request_i[requester_index].vstart << operand_request_i[requester_index].vtype.vsew;
      //Unaligned start address (vstart_byte % 8 = 3)
      //vstart_byte = 3, vl_byte = 20
      //Calculation: 20 - 3 + (3 % 8) = 17 + 3 = 20 bytes
      //Meaning: Read 20 bytes starting from byte 0, then discard the first 3 bytes.
      vector_body_len_byte = vl_byte - vstart_byte + (vstart_byte % 8);
      scaled_vector_len_elements = vector_body_len_byte >> operand_request_i[requester_index].eew;
      if (scaled_vector_len_elements << operand_request_i[requester_index].eew < vector_body_len_byte)
        scaled_vector_len_elements += 1;

      // Final computed length
      effective_vector_body_length = (operand_request_i[requester_index].scale_vl)
                                   ? scaled_vector_len_elements
                                   : operand_request_i[requester_index].vl;

      // Address of the vstart element of the vector in the VRF
      // This vstart is NOT the architectural one and was modified in the lane
      // sequencer to provide the correct start address
      vrf_addr = vaddr(operand_request_i[requester_index].vs, NrLanes, VLEN)
               + (operand_request_i[requester_index].vstart >>
                   (unsigned'(EW64) - unsigned'(operand_request_i[requester_index].eew)));
      // Init helper variables
      requester_metadata_tmp = '{
        id          : operand_request_i[requester_index].id,
        addr        : vrf_addr,
        len         : effective_vector_body_length,
        vew         : operand_request_i[requester_index].eew,
        hazard      : operand_request_i[requester_index].hazard,
        is_widening : operand_request_i[requester_index].cvt_resize == CVT_WIDE,
        default: '0
      };
      operand_queue_cmd_tmp = '{
        eew       : operand_request_i[requester_index].eew,
        elem_count: effective_vector_body_length,
        conv      : operand_request_i[requester_index].conv,
        ntr_red   : operand_request_i[requester_index].cvt_resize,
        target_fu : operand_request_i[requester_index].target_fu,
        is_reduct : operand_request_i[requester_index].is_reduct
      };

      forward_data[requester_index]    = '0;
      forward_done[requester_index]    = '0;
      addr_match_mask[requester_index] = '0;

      case (state_q[requester_index])
        IDLE: begin : state_q_IDLE
          // Accept a new instruction
          if (operand_request_valid_i[requester_index]) begin : op_req_valid
            state_d[requester_index] = REQUESTING;
            // Acknowledge the request
            operand_request_ready_o[requester_index] = 1'b1;

            // Send a command to the operand queue
            operand_queue_cmd_o[requester_index] = operand_queue_cmd_tmp;
            operand_queue_cmd_valid_o[requester_index] = 1'b1;

            // The length should be at least one after the rescaling
            if (operand_queue_cmd_o[requester_index].elem_count == '0) begin : cmd_zero_rescaled_vl
              operand_queue_cmd_o[requester_index].elem_count = 1;
            end : cmd_zero_rescaled_vl

            // Store the request
            requester_metadata_d[requester_index] = requester_metadata_tmp;

            // The length should be at least one after the rescaling
            if (requester_metadata_d[requester_index].len == '0) begin : req_zero_rescaled_vl
              requester_metadata_d[requester_index].len = 1;
            end : req_zero_rescaled_vl


            // Mute the requisition if the vl is zero
            if (operand_request_i[requester_index].vl == '0) begin : zero_vl
              state_d[requester_index]                              = IDLE;
              operand_queue_cmd_valid_o[requester_index] = 1'b0;
            end : zero_vl
          end : op_req_valid
        end : state_q_IDLE

        REQUESTING: begin : state_q_REQUESTING

          // LDU forward detection
          if (ldu_result_req &&
              !lsu_ex_flush_i &&
              requester_metadata_q[requester_index].hazard[ldu_result_id] &&
              ldu_result_addr == requester_metadata_q[requester_index].addr &&
              operand_queue_ready_i[requester_index]) begin
            forward_done[requester_index] = 1'b1;
            for (int byte_idx = 0; byte_idx < $bits(strb_t); byte_idx++) begin
              forward_data[requester_index][8*byte_idx +: 8] = ldu_result_be[byte_idx] ?
                ldu_result_wdata[8*byte_idx +: 8] : '0;
            end
          end
          // ALU forward detection
          else if (alu_result_req_i &&
              requester_metadata_q[requester_index].hazard[alu_result_id_i] &&
              alu_result_addr_i == requester_metadata_q[requester_index].addr &&
              operand_queue_ready_i[requester_index]) begin
            forward_done[requester_index] = 1'b1;
            for (int byte_idx = 0; byte_idx < $bits(strb_t); byte_idx++) begin
              forward_data[requester_index][8*byte_idx +: 8] = alu_result_be_i[byte_idx] ?
                alu_result_wdata_i[8*byte_idx +: 8] : '0;
            end
          end
          // MFPU forward detection
          else if (mfpu_result_req_i &&
              requester_metadata_q[requester_index].hazard[mfpu_result_id_i] &&
              mfpu_result_addr_i == requester_metadata_q[requester_index].addr &&
              operand_queue_ready_i[requester_index]) begin
            forward_done[requester_index] = 1'b1;
            for (int byte_idx = 0; byte_idx < $bits(strb_t); byte_idx++) begin
              forward_data[requester_index][8*byte_idx +: 8] = mfpu_result_be_i[byte_idx] ?
                mfpu_result_wdata_i[8*byte_idx +: 8] : '0;
            end
          end
          // Mask unit forward detection
          else if (masku_result_req &&
              requester_metadata_q[requester_index].hazard[masku_result_id] &&
              masku_result_addr == requester_metadata_q[requester_index].addr &&
              operand_queue_ready_i[requester_index]) begin
            forward_done[requester_index] = 1'b1;
            for (int byte_idx = 0; byte_idx < $bits(strb_t); byte_idx++) begin
              forward_data[requester_index][8*byte_idx +: 8] = masku_result_be[byte_idx] ?
                masku_result_wdata[8*byte_idx +: 8] : '0;
            end
          end
          // Slide unit forward detection
          else if (sldu_result_req &&
              requester_metadata_q[requester_index].hazard[sldu_result_id] &&
              sldu_result_addr == requester_metadata_q[requester_index].addr &&
              operand_queue_ready_i[requester_index]) begin
            forward_done[requester_index] = 1'b1;
            for (int byte_idx = 0; byte_idx < $bits(strb_t); byte_idx++) begin
              forward_data[requester_index][8*byte_idx +: 8] = sldu_result_be[byte_idx] ?
                sldu_result_wdata[8*byte_idx +: 8] : '0;
            end
          end

          //forward_done[requester_index] = 1'b0;

          stall[requester_index] = 1'b0;
          if (!forward_done[requester_index]) begin
            // Address match mask: 1 for ID that has matching write at current request address

            if (alu_result_written_q) begin
              addr_match_mask[requester_index][alu_result_id_q]   = (requester_metadata_q[requester_index].addr == alu_result_addr_q);
            end
            if (mfpu_result_written_q) begin
              addr_match_mask[requester_index][mfpu_result_id_q]  = (requester_metadata_q[requester_index].addr == mfpu_result_addr_q);
            end
            if (masku_result_written_q) begin
              addr_match_mask[requester_index][masku_result_id_q] = (requester_metadata_q[requester_index].addr == masku_result_addr_q);
            end
            if (ldu_result_written_q) begin
              addr_match_mask[requester_index][ldu_result_id_q]   = (requester_metadata_q[requester_index].addr == ldu_result_addr_q);
            end
            if (sldu_result_written_q) begin
              addr_match_mask[requester_index][sldu_result_id_q]  = (requester_metadata_q[requester_index].addr == sldu_result_addr_q);
            end

            // Original stall structure unchanged, added address match filter for vinsn_result_written
            stall[requester_index] = |(requester_metadata_q[requester_index].hazard & ~(
              (vinsn_result_written_q & addr_match_mask[requester_index]) &
              (~{NrVInsn{requester_metadata_q[requester_index].is_widening}} | requester_metadata_q[requester_index].waw_hazard_counter)
            ));
          end
  
          // Update waw counters
          for (int b = 0; b < NrVInsn; b++) begin : waw_counters_update
            if ( vinsn_result_written_d[b] ) begin : result_valid
              requester_metadata_d[requester_index].waw_hazard_counter[b] = ~requester_metadata_q[requester_index].waw_hazard_counter[b];
            end : result_valid
          end : waw_counters_update

          if (operand_queue_ready_i[requester_index]) begin : operand_queue_ready
            automatic vlen_t num_elements;

            // Operand request
            lane_operand_req_transposed[requester_index][bank] = !stall[requester_index] && !forward_done[requester_index];
            operand_payload[requester_index]   = '{
              addr   : requester_metadata_q[requester_index].addr >> $clog2(NrBanks),
              opqueue: opqueue_e'(requester_index),
              default: '0 // this is a read operation
            };

            // Received a grant.
            if (|operand_requester_gnt[requester_index] || forward_done[requester_index]) begin : op_req_grant
              // Bump the address pointer
              requester_metadata_d[requester_index].addr = requester_metadata_q[requester_index].addr + 1'b1;

              // We read less than 64 bits worth of elements
              num_elements = ( 1 << ( unsigned'(EW64) - unsigned'(requester_metadata_q[requester_index].vew) ) );
              if (requester_metadata_q[requester_index].len < num_elements) begin
                requester_metadata_d[requester_index].len    = 0;
              end
              else begin
                requester_metadata_d[requester_index].len = requester_metadata_q[requester_index].len - num_elements;
              end
            end : op_req_grant

            // Finished requesting all the elements
            if (requester_metadata_d[requester_index].len == '0) begin : finish_request
              state_d[requester_index] = IDLE;

              // Accept a new instruction
              if (operand_request_valid_i[requester_index]) begin : accept_a_new_inst
                state_d[requester_index]                 = REQUESTING;
                // Acknowledge the request
                operand_request_ready_o[requester_index] = 1'b1;

                // Send a command to the operand queue
                operand_queue_cmd_o[requester_index] = operand_queue_cmd_tmp;
                operand_queue_cmd_valid_o[requester_index] = 1'b1;

                // The length should be at least one after the rescaling
                if (operand_queue_cmd_o[requester_index].elem_count == '0) begin : cmd_zero_rescaled_vl
                  operand_queue_cmd_o[requester_index].elem_count = 1;
                end : cmd_zero_rescaled_vl

                // Store the request
                requester_metadata_d[requester_index] = requester_metadata_tmp;

                // The length should be at least one after the rescaling
                if (requester_metadata_d[requester_index].len == '0) begin : req_zero_rescaled_vl
                  requester_metadata_d[requester_index].len = 1;
                end : req_zero_rescaled_vl

                // Mute the requisition if the vl is zero
                if (operand_request_i[requester_index].vl == '0) begin
                  state_d[requester_index]                   = IDLE;
                  operand_queue_cmd_valid_o[requester_index] = 1'b0;
                end
              end : accept_a_new_inst
            end : finish_request
          end : operand_queue_ready
        end : state_q_REQUESTING
      endcase

      // Always keep the hazard bits up to date with the global hazard table
      requester_metadata_d[requester_index].hazard &= global_hazard_table_i[requester_metadata_d[requester_index].id];

      // Kill all store-unit, idx, and mem-masked requests in case of exceptions
      if (lsu_ex_flush_o && (requester_index == StA || requester_index == SlideAddrGenA || requester_index == MaskM)) begin : vlsu_exception_idle
        // Reset state
        state_d[requester_index] = IDLE;
        // Don't wake up the store queue (redundant, as it will be flushed anyway)
        operand_queue_cmd_valid_o[requester_index] = 1'b0;
        // Clear metadata
        requester_metadata_d[requester_index] = '0;
        // Flush this request
        lane_operand_req_transposed[requester_index][bank] = '0;
      end : vlsu_exception_idle
    end : operand_requester

    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) begin
        state_q[requester_index]              <= IDLE;
        requester_metadata_q[requester_index] <= '0;
      end else begin
        state_q[requester_index]              <= state_d[requester_index];
        requester_metadata_q[requester_index] <= requester_metadata_d[requester_index];
      end
    end
  end : gen_operand_requester

  always_comb begin
    forward_operand_o = '0;
    forward_operand_valid_o = '0;

    for (int i = 0; i < NrOperandQueues; i++) begin
      if (forward_done[i]) begin
        forward_operand_o[i] = forward_data[i];
        forward_operand_valid_o[i] = 1'b1;
      end
    end
  end

  ////////////////
  //  Arbiters  //
  ////////////////

  // Remember whether the VFUs are trying to write something to the VRF
  always_comb begin
    // Default assignment
    for (int bank = 0; bank < NrBanks; bank++) begin
      ext_operand_req[bank][VFU_Alu]       = 1'b0;
      ext_operand_req[bank][VFU_MFpu]      = 1'b0;
      ext_operand_req[bank][VFU_MaskUnit]  = 1'b0;
      ext_operand_req[bank][VFU_SlideUnit] = 1'b0;
      ext_operand_req[bank][VFU_LoadUnit]  = 1'b0;
    end

    // Generate the payloads for write back operations
    operand_payload[NrOperandQueues + VFU_Alu] = '{
      addr   : alu_result_addr_i >> $clog2(NrBanks),
      wen    : 1'b1,
      wdata  : alu_result_wdata_i,
      be     : alu_result_be_i,
      opqueue: AluA,
      default: '0
    };
    operand_payload[NrOperandQueues + VFU_MFpu] = '{
      addr   : mfpu_result_addr_i >> $clog2(NrBanks),
      wen    : 1'b1,
      wdata  : mfpu_result_wdata_i,
      be     : mfpu_result_be_i,
      opqueue: AluA,
      default: '0
    };
    operand_payload[NrOperandQueues + VFU_MaskUnit] = '{
      addr   : masku_result_addr >> $clog2(NrBanks),
      wen    : 1'b1,
      wdata  : masku_result_wdata,
      be     : masku_result_be,
      opqueue: AluA,
      default: '0
    };
    operand_payload[NrOperandQueues + VFU_SlideUnit] = '{
      addr   : sldu_result_addr >> $clog2(NrBanks),
      wen    : 1'b1,
      wdata  : sldu_result_wdata,
      be     : sldu_result_be,
      opqueue: AluA,
      default: '0
    };
    operand_payload[NrOperandQueues + VFU_LoadUnit] = '{
      addr   : ldu_result_addr >> $clog2(NrBanks),
      wen    : 1'b1,
      wdata  : ldu_result_wdata,
      be     : ldu_result_be,
      opqueue: AluA,
      default: '0
    };

    // Store their request value
    ext_operand_req[alu_result_addr_i[idx_width(NrBanks)-1:0]][VFU_Alu] =
    alu_result_req_i;
    ext_operand_req[mfpu_result_addr_i[idx_width(NrBanks)-1:0]][VFU_MFpu] =
    mfpu_result_req_i;
    ext_operand_req[masku_result_addr[idx_width(NrBanks)-1:0]][VFU_MaskUnit] =
    masku_result_req;
    ext_operand_req[sldu_result_addr[idx_width(NrBanks)-1:0]][VFU_SlideUnit] =
    sldu_result_req;
    ext_operand_req[ldu_result_addr[idx_width(NrBanks)-1:0]][VFU_LoadUnit] =
    ldu_result_req;

    // Generate the grant signals
    alu_result_gnt_o  = 1'b0;
    mfpu_result_gnt_o = 1'b0;
    masku_result_gnt  = 1'b0;
    sldu_result_gnt   = 1'b0;
    ldu_result_gnt    = 1'b0;
    for (int bank = 0; bank < NrBanks; bank++) begin
      alu_result_gnt_o  = alu_result_gnt_o | operand_gnt[bank][NrOperandQueues + VFU_Alu];
      mfpu_result_gnt_o = mfpu_result_gnt_o | operand_gnt[bank][NrOperandQueues + VFU_MFpu];
      masku_result_gnt  = masku_result_gnt | operand_gnt[bank][NrOperandQueues + VFU_MaskUnit];
      sldu_result_gnt   = sldu_result_gnt | operand_gnt[bank][NrOperandQueues + VFU_SlideUnit];
      ldu_result_gnt    = ldu_result_gnt | operand_gnt[bank][NrOperandQueues + VFU_LoadUnit];
    end
  end

  `ifdef FOR_VERIFY
    typedef enum logic [5:0] {
      none,
      v0 = 6'b100000, v1, v2, v3,
      v4, v5, v6, v7,
      v8, v9, v10, v11,
      v12, v13, v14, v15,
      v16, v17, v18, v19,
      v20, v21, v22, v23,
      v24, v25, v26, v27,
      v28, v29, v30, v31
    } vid_e;
    logic [NrBanks-1:0] bank_vld;
    logic [NrBanks-1:0] bank_rd_vld;
    logic [NrBanks-1:0] bank_wr_vld;
    vid_e bank_rd_vid[NrBanks-1:0];
    vid_e bank_wr_vid[NrBanks-1:0];
    // Forward bank valid signal (reverse index per bank for Verdi)
    logic forward_bank_rd_vld [NrBanks-1:0];
    // Forward bank VID signal (reverse index per bank for Verdi)
    vid_e forward_bank_rd_vid [NrBanks-1:0];
    // LDU forwarding tracking for verification
    logic [NrOperandQueues-1:0] forward_vld;
    vaddr_t forward_addr;
    vid_e forward_vid;
    always_comb begin
      forward_vld = '0;
      forward_addr = '0;
      forward_vid = none;
      for (int q = 0; q < NrOperandQueues; q++) begin
        if (forward_done[q]) begin
          forward_vld[q] = 1'b1;
          forward_addr = ldu_result_addr_i;
          forward_vid = vid_e'({1'b1, {5{1'b1}} & 5'(ldu_result_addr_i >> 2)});
        end
      end
    end
  `endif

  // Instantiate a RR arbiter per bank
  for (genvar bank = 0; bank < NrBanks; bank++) begin: gen_vrf_arbiters
    // High-priority requests
    payload_t payload_hp;
    logic payload_hp_req;
    logic payload_hp_gnt;
    rr_arb_tree #(
      .NumIn    (unsigned'(MulFPUC) - unsigned'(AluA) + 1 + unsigned'(VFU_MFpu) - unsigned'(VFU_Alu) + 1),
      .DataWidth($bits(payload_t)                                                   ),
      .AxiVldRdy(1'b0                                                               )
    ) i_hp_vrf_arbiter (
      .clk_i  (clk_i ),
      .rst_ni (rst_ni),
      .flush_i(1'b0  ),
      .rr_i   ('0    ),
      .data_i ({operand_payload[MulFPUC:AluA],
          operand_payload[NrOperandQueues + VFU_MFpu:NrOperandQueues + VFU_Alu]} ),
      .req_i ({lane_operand_req[bank][MulFPUC:AluA],
          ext_operand_req[bank][VFU_MFpu:VFU_Alu]}),
      .gnt_o ({operand_gnt[bank][MulFPUC:AluA],
          operand_gnt[bank][NrOperandQueues + VFU_MFpu:NrOperandQueues + VFU_Alu]}),
      .data_o (payload_hp    ),
      .idx_o  (/* Unused */  ),
      .req_o  (payload_hp_req),
      .gnt_i  (payload_hp_gnt)
    );

    // Low-priority requests
    payload_t payload_lp;
    logic payload_lp_req;
    logic payload_lp_gnt;
    rr_arb_tree #(
      .NumIn(unsigned'(SlideAddrGenA)- unsigned'(MaskB) + 1 + unsigned'(VFU_LoadUnit) - unsigned'(VFU_SlideUnit) + 1),
      .DataWidth($bits(payload_t)                                                               ),
      .AxiVldRdy(1'b0                                                                           )
    ) i_lp_vrf_arbiter (
      .clk_i  (clk_i ),
      .rst_ni (rst_ni),
      .flush_i(1'b0  ),
      .rr_i   ('0    ),
      .data_i ({operand_payload[SlideAddrGenA:MaskB],
          operand_payload[NrOperandQueues + VFU_LoadUnit:NrOperandQueues + VFU_SlideUnit]} ),
      .req_i ({lane_operand_req[bank][SlideAddrGenA:MaskB],
          ext_operand_req[bank][VFU_LoadUnit:VFU_SlideUnit]}),
      .gnt_o ({operand_gnt[bank][SlideAddrGenA:MaskB],
          operand_gnt[bank][NrOperandQueues + VFU_LoadUnit:NrOperandQueues + VFU_SlideUnit]}),
      .data_o (payload_lp    ),
      .idx_o  (/* Unused */  ),
      .req_o  (payload_lp_req),
      .gnt_i  (payload_lp_gnt)
    );

    // High-priority requests always mask low-priority requests
    rr_arb_tree #(
      .NumIn    (2               ),
      .DataWidth($bits(payload_t)),
      .AxiVldRdy(1'b0            ),
      .ExtPrio  (1'b1            )
    ) i_vrf_arbiter (
      .clk_i  (clk_i                            ),
      .rst_ni (rst_ni                           ),
      .flush_i(1'b0                             ),
      .rr_i   (1'b0                             ),
      .data_i ({payload_lp, payload_hp}         ),
      .req_i  ({payload_lp_req, payload_hp_req} ),
      .gnt_o  ({payload_lp_gnt, payload_hp_gnt} ),
      .data_o ({vrf_addr_o[bank], vrf_wen_o[bank], vrf_wdata_o[bank], vrf_be_o[bank],
          vrf_tgt_opqueue_o[bank]}),
      .idx_o (/* Unused */    ),
      .req_o (vrf_req_o[bank] ),
      .gnt_i (vrf_req_o[bank] ) // Acknowledge it directly
    );

  `ifdef FOR_VERIFY
    // Check if this bank has a forwarding event
    logic fwd_vld;
    vaddr_t fwd_addr;
    always_comb begin
      fwd_vld = 1'b0;
      fwd_addr = '0;
      for (int q = 0; q < NrOperandQueues; q++) begin
        if (forward_done[q]) begin
          // Check all forwarding sources
          if (ldu_result_req && requester_metadata_q[q].hazard[ldu_result_id]) begin
            fwd_addr = ldu_result_addr;
          end
          else if (alu_result_req_i && requester_metadata_q[q].hazard[alu_result_id_i]) begin
            fwd_addr = alu_result_addr_i;
          end
          else if (mfpu_result_req_i && requester_metadata_q[q].hazard[mfpu_result_id_i]) begin
            fwd_addr = mfpu_result_addr_i;
          end
          else if (masku_result_req && requester_metadata_q[q].hazard[masku_result_id]) begin
            fwd_addr = masku_result_addr;
          end
          else if (sldu_result_req && requester_metadata_q[q].hazard[sldu_result_id]) begin
            fwd_addr = sldu_result_addr;
          end
          // Check if the forwarded address belongs to current bank
          if (fwd_addr[idx_width(NrBanks)-1:0] == bank) begin
            fwd_vld = 1'b1;
          end
        end
      end
    end
    // Original VRF access signals (unchanged, no forwarding)
    assign bank_vld[bank] = |{payload_lp_gnt, payload_hp_gnt};
    assign bank_rd_vld[bank] = |{payload_lp_gnt, payload_hp_gnt} & !vrf_wen_o[bank]; // Only VRF read
    assign bank_wr_vld[bank] = |{payload_lp_gnt, payload_hp_gnt} & vrf_wen_o[bank];
    // Separate forwarding read signals (global array for observation)
    assign forward_bank_rd_vld[bank] = fwd_vld; // Only forwarding read
    assign forward_bank_rd_vid[bank] = fwd_vld ? vid_e'({1'b1, {5{1'b1}} & 5'(fwd_addr >> 2)}) : none;
    // Original VID signals (unchanged, only for VRF access)
    assign bank_rd_vid[bank] = {bank_rd_vld[bank], {5{bank_rd_vld[bank]}} & 5'({vrf_addr_o[bank], 3'(bank)} >> 2)};
    assign bank_wr_vid[bank] = {bank_wr_vld[bank], {5{bank_wr_vld[bank]}} & 5'({vrf_addr_o[bank], 3'(bank)} >> 2)};
  `endif
  end : gen_vrf_arbiters

`ifdef FOR_VERIFY
// Remaining elements count for each operand queue (reverse index for Verdi)
vlen_t req_remaining_elements [NrOperandQueues-1:0];
// Instruction ID for each operand queue (reverse index for Verdi)
vid_t req_instr_id [NrOperandQueues-1:0];
// Hazard write done status (reverse index for Verdi)
logic req_hazard_write_done [NrOperandQueues-1:0];

generate
for (genvar q = 0; q < NrOperandQueues; q++) begin : gen_req_observe_signals
  // Reverse index assignment for Verdi display order
  assign req_remaining_elements[q] = requester_metadata_q[q].len;
  assign req_instr_id[q] = requester_metadata_q[q].id;
  // Update observation signal: OR of all matching written hazard IDs
  assign req_hazard_write_done[q] = |(vinsn_result_written_q & addr_match_mask[q]);
end
endgenerate

// Forwarding condition arrays, index = requester ID
logic ldu_forward_cond  [NrOperandQueues];
logic alu_forward_cond  [NrOperandQueues];
logic mfpu_forward_cond [NrOperandQueues];
logic masku_forward_cond[NrOperandQueues];
logic sldu_forward_cond [NrOperandQueues];

// Assign forwarding conditions for each requester
generate
for (genvar requester_index = 0; requester_index < NrOperandQueues; requester_index++) begin : gen_forward_cond
  assign ldu_forward_cond[requester_index] = ldu_result_req &&
                                              !lsu_ex_flush_i &&
                                              requester_metadata_q[requester_index].hazard[ldu_result_id] &&
                                              ldu_result_addr == requester_metadata_q[requester_index].addr &&
                                              operand_queue_ready_i[requester_index];

  assign alu_forward_cond[requester_index] = alu_result_req_i &&
                                              requester_metadata_q[requester_index].hazard[alu_result_id_i] &&
                                              alu_result_addr_i == requester_metadata_q[requester_index].addr &&
                                              operand_queue_ready_i[requester_index];

  assign mfpu_forward_cond[requester_index] = mfpu_result_req_i &&
                                               requester_metadata_q[requester_index].hazard[mfpu_result_id_i] &&
                                               mfpu_result_addr_i == requester_metadata_q[requester_index].addr &&
                                               operand_queue_ready_i[requester_index];

  assign masku_forward_cond[requester_index] = masku_result_req &&
                                                requester_metadata_q[requester_index].hazard[masku_result_id] &&
                                                masku_result_addr == requester_metadata_q[requester_index].addr &&
                                                operand_queue_ready_i[requester_index];

  assign sldu_forward_cond[requester_index] = sldu_result_req &&
                                               requester_metadata_q[requester_index].hazard[sldu_result_id] &&
                                               sldu_result_addr == requester_metadata_q[requester_index].addr &&
                                               operand_queue_ready_i[requester_index];
end
endgenerate

// Mutex assertion for each requester (disabled per user request)
// generate
// for (genvar requester_index = 0; requester_index < NrOperandQueues; requester_index++) begin : gen_forward_mutex_assert
//   assert property (@(posedge clk_i) disable iff (!rst_ni)
//     $onehot0({ldu_forward_cond[requester_index], alu_forward_cond[requester_index], mfpu_forward_cond[requester_index], masku_forward_cond[requester_index], sldu_forward_cond[requester_index]})
//   ) else $fatal(1, "Multiple forwarding conditions active for requester %0d at time %0t! LDU:%0d ALU:%0d MFPU:%0d MASK:%0d SLDU:%0d",
//                 requester_index, $time, ldu_forward_cond[requester_index], alu_forward_cond[requester_index], mfpu_forward_cond[requester_index], masku_forward_cond[requester_index], sldu_forward_cond[requester_index]);
// end
// endgenerate
`endif

endmodule : operand_requester
