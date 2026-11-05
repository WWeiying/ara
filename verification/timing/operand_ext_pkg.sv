package operand_ext_pkg;
  typedef struct packed {
    rvv_pkg::vew_e eew;
    logic [10:0] elem_count;
    ara_pkg::opqueue_conversion_e conv;
    logic [1:0] ntr_red;
    logic is_reduct;
    ara_pkg::target_fu_e target_fu;
  } cmd_t;
endpackage
