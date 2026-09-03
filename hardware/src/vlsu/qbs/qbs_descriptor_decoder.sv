// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_descriptor_decoder import qbs_pkg::*; #(
  parameter int unsigned VLEN = 1024
) (
  input  logic [63:0]              descriptor_address_i,
  input  logic [63:0]              descriptor_header_i,
  input  logic [63:0]              descriptor_weight_base_i,
  input  logic [63:0]              activation_base_i,
  input  logic [3:0]               m_i,
  input  logic [4:0]               vd_i,

  output logic                     valid_o,
  output qbs_validation_error_e    error_o,
  output qbs_weight_profile_e      weight_profile_o,
  output qbs_activation_profile_e  activation_profile_o,
  output qbs_weight_layout_e       weight_layout_o,
  output qbs_activation_layout_e   activation_layout_o,
  output qbs_activation_access_e   activation_access_o,
  output logic [3:0]               context_id_o,
  output logic [7:0]               context_generation_o,
  output logic [5:0]               n_o,
  output logic [8:0]               k_blocks_o,
  output logic [15:0]              weight_block_bytes_o,
  output logic [15:0]              activation_block_bytes_o,
  output logic [63:0]              weight_storage_bytes_o,
  output logic [63:0]              activation_storage_bytes_o,
  output logic [63:0]              weight_last_address_o,
  output logic [63:0]              activation_last_address_o
);

  localparam int unsigned MaxNForVlen =
      VLEN / 32 < QbsMaxN ? VLEN / 32 : QbsMaxN;

  logic [5:0] padded_rows;
  logic [63:0] weight_rows;
  logic [64:0] weight_end_extended;
  logic [64:0] activation_end_extended;
  logic [3:0] destination_registers;

  always_comb begin
    weight_profile_o =
        qbs_weight_profile_e'(descriptor_header_i[7:4]);
    activation_profile_o =
        qbs_activation_profile_e'(descriptor_header_i[11:8]);
    weight_layout_o =
        qbs_weight_layout_e'(descriptor_header_i[15:12]);
    activation_layout_o =
        qbs_activation_layout_e'(descriptor_header_i[19:16]);
    activation_access_o =
        qbs_activation_access_e'(descriptor_header_i[34:33]);
    context_id_o = descriptor_header_i[38:35];
    context_generation_o = descriptor_header_i[46:39];
    n_o = {1'b0, descriptor_header_i[24:20]} + 1'b1;
    k_blocks_o = {1'b0, descriptor_header_i[32:25]} + 1'b1;

    weight_block_bytes_o = 16'(qbs_weight_block_bytes(weight_profile_o));
    activation_block_bytes_o =
        16'(qbs_activation_block_bytes(activation_profile_o));
    padded_rows = (n_o + 3) & 6'h3c;
    weight_rows = weight_layout_o == QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR
        ? padded_rows : n_o;
    weight_storage_bytes_o =
        weight_rows * k_blocks_o * weight_block_bytes_o;
    if (activation_layout_o == QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED)
      activation_storage_bytes_o =
          k_blocks_o * (QbsMaxM * activation_block_bytes_o);
    else if (activation_layout_o == QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED)
      activation_storage_bytes_o =
          k_blocks_o * (4 * activation_block_bytes_o);
    else
      activation_storage_bytes_o =
          m_i * k_blocks_o * activation_block_bytes_o;

    weight_end_extended = {1'b0, descriptor_weight_base_i} +
                          {1'b0, weight_storage_bytes_o} - 1'b1;
    activation_end_extended = {1'b0, activation_base_i} +
                              {1'b0, activation_storage_bytes_o} - 1'b1;
    weight_last_address_o = weight_end_extended[63:0];
    activation_last_address_o = activation_end_extended[63:0];
    destination_registers = m_i == 1 ? 4'd1 :
                            (m_i == 2 ? 4'd2 :
                            (m_i <= 4 ? 4'd4 : 4'd8));

    error_o = QBS_VALIDATION_OK;
    if (descriptor_address_i[QbsDescriptorAlignmentLog2-1:0] != '0)
      error_o = QBS_VALIDATION_DESCRIPTOR_ALIGNMENT;
    else if (descriptor_header_i[3:0] != QbsDescriptorVersion)
      error_o = QBS_VALIDATION_DESCRIPTOR_VERSION;
    else if (descriptor_header_i[63:QbsDescReservedLsb] != '0)
      error_o = QBS_VALIDATION_DESCRIPTOR_RESERVED;
    else if (weight_block_bytes_o == 0)
      error_o = QBS_VALIDATION_WEIGHT_PROFILE;
    else if (activation_block_bytes_o == 0 ||
             !qbs_profiles_compatible(weight_profile_o,
                                      activation_profile_o))
      error_o = QBS_VALIDATION_ACTIVATION_PROFILE;
    else if (!(weight_layout_o inside {
                 QBS_WEIGHT_LAYOUT_ROW_MAJOR,
                 QBS_WEIGHT_LAYOUT_R4_BLOCK_MAJOR}))
      error_o = QBS_VALIDATION_WEIGHT_LAYOUT;
    else if (!(activation_layout_o inside {
                 QBS_ACTIVATION_LAYOUT_ROW_MAJOR,
                 QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED,
                 QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED}) ||
             (activation_layout_o ==
                  QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED && m_i != 4) ||
             ((activation_layout_o ==
                   QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED) !=
                  (unsigned'(m_i) >= QbsWideMMin)))
      error_o = QBS_VALIDATION_ACTIVATION_LAYOUT;
    else if (!(m_i inside {[1:QbsMaxM]}))
      error_o = QBS_VALIDATION_M_RANGE;
    else if (unsigned'(n_o) > MaxNForVlen ||
             (unsigned'(m_i) >= QbsWideMMin &&
              unsigned'(n_o) > QbsWideMMaxN) ||
             unsigned'(m_i) * unsigned'(n_o) > QbsMaxResults)
      error_o = QBS_VALIDATION_N_RANGE;
    else if (unsigned'(k_blocks_o) > QbsMaxKBlocks)
      error_o = QBS_VALIDATION_K_RANGE;
    else if (activation_access_o == QBS_ACTIVATION_ACCESS_DIRECT &&
             (context_id_o != '0 || context_generation_o != '0))
      error_o = QBS_VALIDATION_CONTEXT_ENCODING;
    else if (activation_access_o != QBS_ACTIVATION_ACCESS_DIRECT &&
             (unsigned'(context_id_o) >= QbsActivationContextCount ||
              activation_profile_o != QBS_ACTIVATION_PROFILE_Q8_K ||
              activation_layout_o != QBS_ACTIVATION_LAYOUT_ROW_MAJOR ||
              unsigned'(m_i) > QbsActivationContextMaxM ||
              unsigned'(k_blocks_o) > QbsActivationContextMaxKBlocks))
      error_o = QBS_VALIDATION_CONTEXT_UNSUPPORTED;
    else if ((unsigned'(vd_i) % destination_registers) != 0 ||
             unsigned'(vd_i) + destination_registers > 32)
      error_o = QBS_VALIDATION_VD_ALIGNMENT;
    else if (descriptor_weight_base_i[
                 QbsWeightBaseAlignmentLog2-1:0] != '0)
      error_o = QBS_VALIDATION_WEIGHT_ALIGNMENT;
    else if (activation_access_o inside {
                 QBS_ACTIVATION_ACCESS_DIRECT,
                 QBS_ACTIVATION_ACCESS_FILL} &&
             activation_base_i[
                 QbsActivationBaseAlignmentLog2-1:0] != '0)
      error_o = QBS_VALIDATION_ACTIVATION_ALIGNMENT;
    else if (weight_end_extended[64])
      error_o = QBS_VALIDATION_WEIGHT_RANGE_OVERFLOW;
    else if (activation_access_o inside {
                 QBS_ACTIVATION_ACCESS_DIRECT,
                 QBS_ACTIVATION_ACCESS_FILL} && activation_end_extended[64])
      error_o = QBS_VALIDATION_ACTIVATION_RANGE_OVERFLOW;

    valid_o = error_o == QBS_VALIDATION_OK;
  end

`ifndef SYNTHESIS
  initial begin
    assert (VLEN >= 32 && VLEN % 32 == 0)
      else $fatal(1, "QBS requires a VLEN divisible by FP32 width");
  end
`endif

endmodule : qbs_descriptor_decoder
