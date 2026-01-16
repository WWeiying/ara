module vrf_perf_monitor import ara_pkg::*; import rvv_pkg::*; #(
  parameter int unsigned NrBanks               = 8,
  parameter int unsigned NrOperandQueues       = 9,
  parameter int unsigned NrGlobalMasters       = 5,
  parameter int unsigned Concurrent_count      = 10
)(
    // Clock and Reset
    input  logic                                    clk_i,
    input  logic                                    rst_ni,
    input  logic [NrBanks-1:0][NrOperandQueues-1:0] lane_operand_req,
    input  logic [NrBanks-1:0][NrGlobalMasters-1:0] ext_operand_req
);

  typedef struct {
    logic [31:0] total_bank_requests;
    logic [31:0] total_hp_bank_requests;
    logic [31:0] total_lp_bank_requests;
    logic [31:0] total_bank_conflicts;
    logic [31:0] total_hp_bank_conflicts;
    logic [31:0] total_lp_bank_conflicts;
    logic [31:0] hp_block_lp; 
    logic [31:0] bank_total_requests [NrBanks-1:0];
    logic [31:0] bank_total_conflicts [NrBanks-1:0];
    logic [31:0] bank_requests [NrBanks-1:0];
    logic [31:0] bank_conflicts [NrBanks-1:0];
    logic        bank_conflict_flag [NrBanks-1:0];
  } lane_stats_t;

  lane_stats_t lane_stats;

  logic [31:0] bank_req_count_incr[NrBanks-1:0];
  logic [31:0] hp_req_count_incr[NrBanks-1:0];
  logic [31:0] lp_req_count_incr[NrBanks-1:0];
  logic [31:0] bank_req_count;
  logic [31:0] hp_req_count;
  logic [31:0] lp_req_count; 
  logic [31:0] hp_block_lp;
  logic [31:0] bank_conflicts;
  logic [31:0] hp_bank_conflicts;
  logic [31:0] lp_bank_conflicts;

  always_comb begin
    bank_req_count = 0;
    hp_req_count = 0;
    lp_req_count = 0; 
    hp_block_lp = 0;
    bank_conflicts = 0;
    hp_bank_conflicts = 0;
    lp_bank_conflicts = 0;

    for (int bank = 0; bank < NrBanks; bank++) begin
      bank_req_count_incr[bank] = 0;
      hp_req_count_incr[bank] = 0;
      lp_req_count_incr[bank] = 0;
      
      for (int i = AluA; i <= MulFPUC; i++) begin 
        if (lane_operand_req[bank][i]) begin
          hp_req_count_incr[bank]++;
          bank_req_count_incr[bank]++;
          hp_req_count++;
          bank_req_count++;
        end
      end
      for (int i = VFU_Alu; i <= VFU_MFpu; i++) begin 
        if (ext_operand_req[bank][i]) begin
          hp_req_count_incr[bank]++;
          bank_req_count_incr[bank]++;
          hp_req_count++;
          bank_req_count++;
        end
      end
      
      for (int i = MaskB; i <= SlideAddrGenA; i++) begin
        if (lane_operand_req[bank][i]) begin
          lp_req_count_incr[bank]++;
          bank_req_count_incr[bank]++;
          lp_req_count++;
          bank_req_count++;
        end
      end
      for (int i = VFU_SlideUnit; i <= VFU_LoadUnit; i++) begin
        if (ext_operand_req[bank][i])  begin
          lp_req_count_incr[bank]++;
          bank_req_count_incr[bank]++;
          lp_req_count++;
          bank_req_count++;
        end
      end
          
      if (hp_req_count_incr[bank] > 0 && lp_req_count_incr[bank] > 0)
        hp_block_lp++;

      if(bank_req_count_incr[bank] > 1) bank_conflicts += bank_req_count_incr[bank] - 1;
      if(hp_req_count_incr[bank] > 1) hp_bank_conflicts += hp_req_count_incr[bank] - 1;
      if(lp_req_count_incr[bank] > 1) lp_bank_conflicts += lp_req_count_incr[bank] - 1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      lane_stats <= '{
        total_bank_requests     : 0,
        total_hp_bank_requests  : 0,
        total_lp_bank_requests  : 0,
        total_bank_conflicts    : 0,
        total_hp_bank_conflicts : 0,
        total_lp_bank_conflicts : 0,
        hp_block_lp             : 0, 
        bank_total_requests     : '{default: 0},
        bank_total_conflicts    : '{default: 0},
        bank_requests           : '{default: 0},
        bank_conflicts          : '{default: 0},
        bank_conflict_flag      : '{default: 0}
      };
    end else begin
      lane_stats.total_bank_requests <= lane_stats.total_bank_requests + bank_req_count;
      lane_stats.total_hp_bank_requests <= lane_stats.total_hp_bank_requests + hp_req_count;
      lane_stats.total_lp_bank_requests <= lane_stats.total_lp_bank_requests + lp_req_count;
      lane_stats.total_bank_conflicts <= lane_stats.total_bank_conflicts + bank_conflicts;
      lane_stats.total_hp_bank_conflicts <= lane_stats.total_hp_bank_conflicts + hp_bank_conflicts;
      lane_stats.total_lp_bank_conflicts <= lane_stats.total_lp_bank_conflicts + lp_bank_conflicts;
      lane_stats.hp_block_lp <= lane_stats.hp_block_lp + hp_block_lp;

      for (int bank = 0; bank < NrBanks; bank++) begin
        lane_stats.bank_total_requests[bank] <= lane_stats.bank_total_requests[bank] + bank_req_count_incr[bank];
        lane_stats.bank_requests[bank] <= bank_req_count_incr[bank];
        lane_stats.bank_conflict_flag[bank] <= bank_req_count_incr[bank] > 1;
        if (bank_req_count_incr[bank] > 1) begin
          lane_stats.bank_total_conflicts[bank] <= lane_stats.bank_total_conflicts[bank] + (bank_req_count_incr[bank] - 1);
          lane_stats.bank_conflicts[bank] <= bank_req_count_incr[bank] - 1;
        end
      end
    end
  end

endmodule
