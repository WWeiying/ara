`timescale 1ns/1ps

module qbs_descriptor_decoder_tb;
  import qbs_pkg::*;

  logic [63:0] descriptor_address;
  logic [63:0] descriptor_header;
  logic [63:0] descriptor_weight_base;
  logic [63:0] activation_base;
  logic [3:0] m;
  logic [4:0] vd;
  logic valid;
  qbs_validation_error_e error;
  qbs_weight_profile_e weight_profile;
  qbs_activation_profile_e activation_profile;
  qbs_weight_layout_e weight_layout;
  qbs_activation_layout_e activation_layout;
  qbs_activation_access_e activation_access;
  logic [3:0] context_id;
  logic [7:0] context_generation;
  logic [5:0] n;
  logic [8:0] k_blocks;
  logic [15:0] weight_block_bytes;
  logic [15:0] activation_block_bytes;
  logic [63:0] weight_storage_bytes;
  logic [63:0] activation_storage_bytes;
  logic [63:0] weight_last_address;
  logic [63:0] activation_last_address;

  logic small_valid;
  qbs_validation_error_e small_error;

  qbs_descriptor_decoder #(.VLEN(1024)) dut (
    .descriptor_address_i          (descriptor_address),
    .descriptor_header_i           (descriptor_header),
    .descriptor_weight_base_i      (descriptor_weight_base),
    .activation_base_i             (activation_base),
    .m_i                           (m),
    .vd_i                          (vd),
    .valid_o                       (valid),
    .error_o                       (error),
    .weight_profile_o              (weight_profile),
    .activation_profile_o          (activation_profile),
    .weight_layout_o               (weight_layout),
    .activation_layout_o           (activation_layout),
    .activation_access_o           (activation_access),
    .context_id_o                  (context_id),
    .context_generation_o          (context_generation),
    .n_o                            (n),
    .k_blocks_o                     (k_blocks),
    .weight_block_bytes_o           (weight_block_bytes),
    .activation_block_bytes_o       (activation_block_bytes),
    .weight_storage_bytes_o         (weight_storage_bytes),
    .activation_storage_bytes_o     (activation_storage_bytes),
    .weight_last_address_o          (weight_last_address),
    .activation_last_address_o      (activation_last_address)
  );

  qbs_descriptor_decoder #(.VLEN(256)) i_small_vlen (
    .descriptor_address_i          (descriptor_address),
    .descriptor_header_i           (descriptor_header),
    .descriptor_weight_base_i      (descriptor_weight_base),
    .activation_base_i             (activation_base),
    .m_i                           (m),
    .vd_i                          (vd),
    .valid_o                       (small_valid),
    .error_o                       (small_error),
    .weight_profile_o              (),
    .activation_profile_o          (),
    .weight_layout_o               (),
    .activation_layout_o           (),
    .activation_access_o           (),
    .context_id_o                  (),
    .context_generation_o          (),
    .n_o                            (),
    .k_blocks_o                     (),
    .weight_block_bytes_o           (),
    .activation_block_bytes_o       (),
    .weight_storage_bytes_o         (),
    .activation_storage_bytes_o     (),
    .weight_last_address_o          (),
    .activation_last_address_o      ()
  );

  function automatic logic [63:0] make_header(
      input integer version,
      input integer wp,
      input integer ap,
      input integer wl,
      input integer al,
      input integer active_n,
      input integer active_k);
    logic [63:0] value;
    value = '0;
    value[3:0] = version[3:0];
    value[7:4] = wp[3:0];
    value[11:8] = ap[3:0];
    value[15:12] = wl[3:0];
    value[19:16] = al[3:0];
    value[24:20] = (active_n - 1) & 5'h1f;
    value[32:25] = (active_k - 1) & 8'hff;
    return value;
  endfunction

  task automatic check_error(input qbs_validation_error_e expected);
    #1;
    if (error != expected || valid != (expected == QBS_VALIDATION_OK))
      $fatal(1, "descriptor error got=%0d valid=%0b expected=%0d",
             error, valid, expected);
  endtask

  initial begin
    descriptor_address = 64'h1000;
    descriptor_weight_base = 64'h2000;
    activation_base = 64'h4000;
    m = 1;
    vd = 0;

    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 1, 32, 64);
    check_error(QBS_VALIDATION_OK);
    if (weight_block_bytes != 144 || weight_storage_bytes != 294912 ||
        activation_storage_bytes != 18688 ||
        weight_last_address != 64'h49fff ||
        activation_last_address != 64'h88ff)
      $fatal(1, "Q4 descriptor derived range mismatch");

    descriptor_header = make_header(QbsDescriptorVersion, 2, 1, 2, 2, 31, 35);
    m = 4;
    vd = 4;
    check_error(QBS_VALIDATION_OK);
    if (weight_block_bytes != 210 || weight_storage_bytes != 235200 ||
        activation_storage_bytes != 40880)
      $fatal(1, "Q6 R4/M4 descriptor derived size mismatch");

    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 2, 3, 15, 2);
    m = 5;
    vd = 8;
    check_error(QBS_VALIDATION_OK);
    if (weight_storage_bytes != 4608 ||
        activation_storage_bytes != 4672)
      $fatal(1, "Q4 R4/M8 descriptor derived size mismatch");

    m = 8;
    vd = 16;
    descriptor_header = make_header(QbsDescriptorVersion, 2, 1, 2, 3, 16, 1);
    check_error(QBS_VALIDATION_OK);
    if (weight_storage_bytes != 3360 ||
        activation_storage_bytes != 2336)
      $fatal(1, "Q6 maximum M8 descriptor derived size mismatch");

    descriptor_header = make_header(QbsDescriptorVersion, 2, 1, 2, 1, 16, 1);
    check_error(QBS_VALIDATION_ACTIVATION_LAYOUT);
    descriptor_header = make_header(QbsDescriptorVersion, 2, 1, 2, 3, 17, 1);
    check_error(QBS_VALIDATION_N_RANGE);
    descriptor_header = make_header(QbsDescriptorVersion, 2, 1, 2, 3, 16, 1);
    vd = 4;
    check_error(QBS_VALIDATION_VD_ALIGNMENT);
    m = 4;
    vd = 8;
    check_error(QBS_VALIDATION_ACTIVATION_LAYOUT);

    descriptor_header = make_header(QbsDescriptorVersion, 3, 2, 1, 1, 32, 64);
    m = 4;
    vd = 4;
    check_error(QBS_VALIDATION_OK);
    if (weight_block_bytes != 18 || activation_block_bytes != 34 ||
        weight_storage_bytes != 36864 || activation_storage_bytes != 8704 ||
        weight_last_address != 64'h0000_0000_0000_afff ||
        activation_last_address != 64'h0000_0000_0000_61ff)
      $fatal(1, "Q4_0/Q8_0 descriptor derived range mismatch");

    descriptor_header = make_header(QbsDescriptorVersion, 3, 2, 1, 1, 1, 256);
    m = 1;
    vd = 0;
    check_error(QBS_VALIDATION_OK);
    if (k_blocks != 256 || weight_storage_bytes != 4608 ||
        activation_storage_bytes != 8704 ||
        weight_last_address != 64'h0000_0000_0000_31ff ||
        activation_last_address != 64'h0000_0000_0000_61ff)
      $fatal(1, "Q4_0 maximum-K descriptor range mismatch");

    descriptor_address = 64'h1008;
    check_error(QBS_VALIDATION_DESCRIPTOR_ALIGNMENT);
    descriptor_address = 64'h1000;

    descriptor_header = make_header(QbsDescriptorVersion + 1,
                                    1, 1, 1, 1, 4, 2);
    check_error(QBS_VALIDATION_DESCRIPTOR_VERSION);
    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4, 2) |
                        (64'h1 << 47);
    check_error(QBS_VALIDATION_DESCRIPTOR_RESERVED);
    descriptor_header = make_header(QbsDescriptorVersion, 15, 1, 1, 1, 4, 2);
    check_error(QBS_VALIDATION_WEIGHT_PROFILE);
    descriptor_header = make_header(QbsDescriptorVersion, 1, 2, 1, 1, 4, 2);
    check_error(QBS_VALIDATION_ACTIVATION_PROFILE);
    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 3, 1, 4, 2);
    check_error(QBS_VALIDATION_WEIGHT_LAYOUT);
    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 3, 4, 2);
    check_error(QBS_VALIDATION_ACTIVATION_LAYOUT);

    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4, 2) |
                        (64'h1 << QbsDescContextIdLsb);
    check_error(QBS_VALIDATION_CONTEXT_ENCODING);
    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4, 2) |
                        (64'(QBS_ACTIVATION_ACCESS_FILL) <<
                         QbsDescActivationAccessLsb) |
                        (64'h1 << QbsDescContextIdLsb);
    check_error(QBS_VALIDATION_CONTEXT_UNSUPPORTED);
    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4,
                                    QbsActivationContextMaxKBlocks) |
                        (64'(QBS_ACTIVATION_ACCESS_FILL) <<
                         QbsDescActivationAccessLsb) |
                        (64'ha5 << QbsDescContextGenerationLsb);
    check_error(QBS_VALIDATION_OK);
    if (activation_access != QBS_ACTIVATION_ACCESS_FILL ||
        context_id != 0 || context_generation != 8'ha5)
      $fatal(1, "QBS context fields decoded incorrectly");
    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4,
                                    QbsActivationContextMaxKBlocks + 1) |
                        (64'(QBS_ACTIVATION_ACCESS_FILL) <<
                         QbsDescActivationAccessLsb);
    check_error(QBS_VALIDATION_CONTEXT_UNSUPPORTED);

    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 1, 4, 2);
    m = 0;
    check_error(QBS_VALIDATION_M_RANGE);
    m = 1;
    vd = 0;
    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 1, 9, 2);
    #1;
    if (small_valid || small_error != QBS_VALIDATION_N_RANGE)
      $fatal(1, "small-VLEN N limit was not enforced");

    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 1, 4, 256);
    check_error(QBS_VALIDATION_OK);
    descriptor_header = make_header(QbsDescriptorVersion, 1, 1, 1, 1, 4, 2);
    m = 3;
    vd = 2;
    check_error(QBS_VALIDATION_VD_ALIGNMENT);
    m = 1;
    vd = 0;

    descriptor_weight_base = 64'h2001;
    check_error(QBS_VALIDATION_WEIGHT_ALIGNMENT);
    descriptor_weight_base = 64'h2000;
    activation_base = 64'h4002;
    check_error(QBS_VALIDATION_ACTIVATION_ALIGNMENT);
    activation_base = 64'h4000;

    descriptor_weight_base = 64'hffff_ffff_ffff_fffe;
    check_error(QBS_VALIDATION_WEIGHT_RANGE_OVERFLOW);
    descriptor_weight_base = 64'h2000;
    activation_base = 64'hffff_ffff_ffff_fffc;
    check_error(QBS_VALIDATION_ACTIVATION_RANGE_OVERFLOW);

    descriptor_header = make_header(QbsDescriptorVersion,
                                    1, 1, 1, 1, 4, 2) |
                        (64'(QBS_ACTIVATION_ACCESS_REUSE) <<
                         QbsDescActivationAccessLsb) |
                        (64'h7 << QbsDescContextGenerationLsb);
    activation_base = 64'hffff_ffff_ffff_ffff;
    check_error(QBS_VALIDATION_OK);

    $display("QBS descriptor decoder PASS");
    $finish;
  end

endmodule : qbs_descriptor_decoder_tb
