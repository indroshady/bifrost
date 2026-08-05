`timescale 1ns/1ps

module tb_bifrost_protocol_error;
  import bifrost_pkg::*;

  logic clk = 1'b0;
  logic rst_n = 1'b0;
  logic port_enable [PORTS];
  logic rx_valid [PORTS];
  logic [FLIT_W-1:0] rx_flit [PORTS];
  logic [VC_ID_W-1:0] rx_vc [PORTS];
  wire tx_valid [PORTS];
  wire [FLIT_W-1:0] tx_flit [PORTS];
  wire [VC_ID_W-1:0] tx_vc [PORTS];
  wire credit_out_valid [PORTS];
  wire [VC_ID_W-1:0] credit_out_vc [PORTS];
  logic credit_in_valid [PORTS];
  logic [VC_ID_W-1:0] credit_in_vc [PORTS];

  bifrost_router dut (.*);
  always #5 clk = ~clk;

  initial begin
    for (int port = 0; port < PORTS; port++) begin
      port_enable[port] = 1'b1;
      rx_valid[port] = 1'b0;
      rx_flit[port] = '0;
      rx_vc[port] = '0;
      credit_in_valid[port] = 1'b0;
      credit_in_vc[port] = '0;
    end
    @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;
    rx_valid[PORT_LOCAL] = 1'b1;
    rx_flit[PORT_LOCAL] = '0;
    @(posedge clk);
    #1;
    $fatal(1, "body-at-idle protocol violation was not detected");
  end
endmodule
