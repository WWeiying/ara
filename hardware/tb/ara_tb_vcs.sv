/*Copyright 2019-2021 T-Head Semiconductor Co., Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
/*Copyright 2019-2021 T-Head Semiconductor Co., Ltd.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/
`timescale 1ns/100ps

`define CLK_PERIOD          10
`define MAX_RUN_TIME        32'h3000000
`define LAST_CYCLE 100000

module tb();

  `ifdef NR_LANES
  localparam NrLanes = `NR_LANES;
  `else
  localparam NrLanes = 0;
  `endif

  `ifdef VLEN
  localparam VLEN = `VLEN;
  `else
  localparam VLEN = 0;
  `endif

  localparam int unsigned AxiRespDelay = 200;
  localparam AxiAddrWidth      = 64;
  localparam AxiWideDataWidth  = 64 * NrLanes / 2;
  localparam AxiWideBeWidth    = AxiWideDataWidth / 8;
  localparam AxiWideByteOffset = $clog2(AxiWideBeWidth);
  parameter int unsigned AxiUserWidth = 1,
  parameter int unsigned AxiIdWidth   = 5,

  reg clk;
  reg rst_ni;
  
  initial
  begin
    clk =0;
    forever begin
      #(`CLK_PERIOD/2) clk = ~clk;
    end
  end
  
  initial
  begin
    rst_ni = 1;
    #100;
    rst_ni = 0;
    #100;
    rst_ni = 1;
  end
  
  ara_soc #(
    .NrLanes     (NrLanes      ),
    .VLEN        (VLEN         ),
    .AxiAddrWidth(AxiAddrWidth ),
    .AxiDataWidth(AxiDataWidth ),
    .AxiIdWidth  (AxiIdWidth   ),
    .AxiUserWidth(AxiUserWidth ),
    .AxiRespDelay(AxiRespDelay )
  ) i_ara_soc (
    .clk_i         (clk_i       ),
    .rst_ni        (rst_ni      ),
    .hw_cnt_en_o   (/* Unused */),
    .exit_o        (      ),
    .scan_enable_i (1'b0        ),
    .scan_data_i   (1'b0        ),
    .scan_data_o   (/* Unused */),
    // UART
    .uart_penable_o(),
    .uart_pwrite_o (),
    .uart_paddr_o  (),
    .uart_psel_o   (),
    .uart_pwdata_o (),
    .uart_prdata_i (32'b0 ),
    .uart_pready_i (1'b0 ),
    .uart_pslverr_i(1'b0)
  );

endmodule
