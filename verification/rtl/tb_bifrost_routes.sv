`timescale 1ns/1ps

module tb_bifrost_routes;
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

  bifrost_router #(
    .ROUTER_X(1),
    .ROUTER_Y(1)
  ) dut (.*);

  always #5 clk = ~clk;

  function automatic logic [FLIT_W-1:0] single(
    input logic destination_x,
    input logic destination_y,
    input logic [15:0] packet_id
  );
    single = '0;
    single[HEAD_BIT] = 1'b1;
    single[TAIL_BIT] = 1'b1;
    single[DEST_X_BIT] = destination_x;
    single[DEST_Y_BIT] = destination_y;
    single[SOURCE_X_BIT] = 1'b1;
    single[SOURCE_Y_BIT] = 1'b1;
    single[PACKET_ID_MSB:PACKET_ID_LSB] = packet_id;
  endfunction

  task automatic clear_inputs;
    for (int port = 0; port < PORTS; port++) begin
      rx_valid[port] = 1'b0;
      rx_flit[port] = '0;
      rx_vc[port] = '0;
      credit_in_valid[port] = 1'b0;
      credit_in_vc[port] = '0;
    end
  endtask

  task automatic inject_and_expect(
    input logic [FLIT_W-1:0] flit,
    input int expected_port
  );
    rx_valid[PORT_LOCAL] = 1'b1;
    rx_flit[PORT_LOCAL] = flit;
    #4; @(posedge clk); #1; clear_inputs(); @(negedge clk);
    #4; @(posedge clk); #1; @(negedge clk);
    #4;
    for (int port = 0; port < PORTS; port++) begin
      assert (tx_valid[port] == (port == expected_port))
        else $fatal(1, "route expected only port %0d", expected_port);
    end
    assert (tx_flit[expected_port] == flit)
      else $fatal(1, "route test modified flit");
    @(posedge clk); #1; @(negedge clk);
  endtask

  initial begin
    clear_inputs();
    for (int port = 0; port < PORTS; port++)
      port_enable[port] = 1'b1;
    @(negedge clk);
    #4; @(posedge clk); #1; @(negedge clk);
    rst_n = 1'b1;

    // X takes precedence when both destination dimensions differ.
    inject_and_expect(single(1'b0, 1'b0, 16'h7000), PORT_WEST);
    inject_and_expect(single(1'b1, 1'b0, 16'h7001), PORT_SOUTH);
    inject_and_expect(single(1'b1, 1'b1, 16'h7002), PORT_LOCAL);
    $display("PASS: all deterministic XY directions and local route");
    $finish;
  end
endmodule
