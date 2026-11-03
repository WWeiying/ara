module complete_repair_probe (
    input wire clk, input wire reset, input wire [7:0] data,
    output reg [7:0] result
);
    (* ASYNC_REG = "TRUE" *) reg [1:0] reset_sync;
    reg [7:0] intermediate;
    always @(posedge clk) begin
        reset_sync <= {reset_sync[0], reset};
        intermediate <= data + 8'd1;
        if (reset_sync[1]) result <= 0;
        else result <= intermediate ^ 8'h5a;
    end
endmodule
