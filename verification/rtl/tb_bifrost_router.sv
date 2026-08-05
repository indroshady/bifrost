`timescale 1ns/1ps

module tb_bifrost_router;
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

  logic [PORTS-1:0] observed_tx_valid;
  logic [FLIT_W-1:0] observed_tx_flit [PORTS];
  logic [VC_ID_W-1:0] observed_tx_vc [PORTS];
  logic [PORTS-1:0] observed_credit_valid;
  logic [VC_ID_W-1:0] observed_credit_vc [PORTS];

  bifrost_router dut (
    .clk,
    .rst_n,
    .port_enable,
    .rx_valid,
    .rx_flit,
    .rx_vc,
    .tx_valid,
    .tx_flit,
    .tx_vc,
    .credit_out_valid,
    .credit_out_vc,
    .credit_in_valid,
    .credit_in_vc
  );

  always #5 clk = ~clk;

  function automatic logic [FLIT_W-1:0] header(
    input logic tail,
    input logic destination_x,
    input logic destination_y,
    input logic [15:0] packet_id,
    input logic [103:0] payload
  );
    header = '0;
    header[HEAD_BIT] = 1'b1;
    header[TAIL_BIT] = tail;
    header[DEST_X_BIT] = destination_x;
    header[DEST_Y_BIT] = destination_y;
    header[PACKET_ID_MSB:PACKET_ID_LSB] = packet_id;
    header[PAYLOAD_MSB:PAYLOAD_LSB] = payload;
  endfunction

  function automatic logic [FLIT_W-1:0] body(
    input logic tail,
    input logic [103:0] payload
  );
    body = '0;
    body[TAIL_BIT] = tail;
    body[PAYLOAD_MSB:PAYLOAD_LSB] = payload;
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

  task automatic enable_all_ports;
    for (int port = 0; port < PORTS; port++)
      port_enable[port] = 1'b1;
  endtask

  task automatic drive_flit(
    input int port,
    input int vc,
    input logic [FLIT_W-1:0] flit
  );
    rx_valid[port] = 1'b1;
    rx_vc[port] = vc[VC_ID_W-1:0];
    rx_flit[port] = flit;
  endtask

  task automatic return_credit(input int port, input int vc);
    credit_in_valid[port] = 1'b1;
    credit_in_vc[port] = vc[VC_ID_W-1:0];
  endtask

  task automatic step;
    #4;
    for (int port = 0; port < PORTS; port++) begin
      observed_tx_valid[port] = tx_valid[port];
      observed_tx_flit[port] = tx_flit[port];
      observed_tx_vc[port] = tx_vc[port];
      observed_credit_valid[port] = credit_out_valid[port];
      observed_credit_vc[port] = credit_out_vc[port];
    end
    @(posedge clk);
    #1;
    clear_inputs();
    @(negedge clk);
  endtask

  task automatic reset_router;
    clear_inputs();
    rst_n = 1'b0;
    step();
    assert (observed_tx_valid == '0 && observed_credit_valid == '0)
      else $fatal(1, "reset did not suppress outputs");
    rst_n = 1'b1;
  endtask

  task automatic expect_no_tx;
    assert (observed_tx_valid == '0)
      else $fatal(1, "unexpected transfer mask %b", observed_tx_valid);
  endtask

  task automatic expect_tx(
    input int output_port,
    input logic [FLIT_W-1:0] expected_flit
  );
    assert (observed_tx_valid == (1 << output_port))
      else $fatal(
        1,
        "expected output %0d got=%b empty=%b route_valid=%b route=%0d vc=%0d credit=%0d alloc=%b select=%b",
        output_port,
        observed_tx_valid,
        dut.fifo_empty[PORT_LOCAL][0],
        dut.route_valid[PORT_LOCAL][0],
        dut.route_cache[PORT_LOCAL][0],
        dut.assigned_vc[PORT_LOCAL][0],
        dut.credit_count[output_port][0],
        dut.allocation_valid[output_port],
        dut.selected_valid[output_port]
      );
    assert (observed_tx_flit[output_port] == expected_flit)
      else $fatal(1, "flit changed on output %0d expected=%h observed=%h",
                  output_port, expected_flit, observed_tx_flit[output_port]);
  endtask

  task automatic test_head_tail_and_encoding;
    logic [FLIT_W-1:0] first;
    logic [FLIT_W-1:0] second;
    logic [FLIT_W-1:0] third;
    first = header(1'b1, 1'b1, 1'b1, 16'h1234, 104'h123);
    second = header(1'b1, 1'b1, 1'b0, 16'h1235, 104'h456);
    third = header(1'b1, 1'b1, 1'b0, 16'h1236, 104'h789);

    reset_router();
    drive_flit(PORT_LOCAL, 0, first);
    step();
    expect_no_tx();
    step();
    expect_no_tx();
    step();
    expect_tx(PORT_EAST, first);
    assert (observed_tx_vc[PORT_EAST] == 0)
      else $fatal(1, "first allocation did not begin at VC0");
    assert (observed_credit_valid[PORT_LOCAL] &&
            observed_credit_vc[PORT_LOCAL] == 0)
      else $fatal(1, "missing exact upstream credit for HEAD+TAIL valid=%b vc=%b",
                  observed_credit_valid, observed_credit_vc[PORT_LOCAL]);

    drive_flit(PORT_LOCAL, 0, second);
    step();
    step();
    step();
    expect_tx(PORT_EAST, second);
    assert (observed_tx_vc[PORT_EAST] == 1)
      else $fatal(1, "released output VC was not followed by VC round robin");

    drive_flit(PORT_LOCAL, 0, third);
    step();
    step();
    step();
    expect_tx(PORT_EAST, third);
    assert (observed_tx_vc[PORT_EAST] == 0)
      else $fatal(1, "HEAD+TAIL did not release VC0 for exact reuse");
  endtask

  task automatic test_bubbles_and_throughput;
    logic [FLIT_W-1:0] flits [5];
    int output_vc;
    flits[0] = header(1'b0, 1'b0, 1'b1, 16'h2000, 104'h10);
    flits[1] = body(1'b0, 104'h11);
    flits[2] = body(1'b0, 104'h12);
    flits[3] = body(1'b0, 104'h13);
    flits[4] = body(1'b1, 104'h14);

    reset_router();
    drive_flit(PORT_NORTH, 1, flits[0]);
    step();
    step();
    step();
    expect_tx(PORT_NORTH, flits[0]);
    output_vc = observed_tx_vc[PORT_NORTH];
    step();
    expect_no_tx();
    step();
    expect_no_tx();

    for (int index = 1; index < 5; index++) begin
      drive_flit(PORT_NORTH, 1, flits[index]);
      if (index > 1)
        return_credit(PORT_NORTH, output_vc);
      step();
      if (index == 1)
        expect_no_tx();
      else
        expect_tx(PORT_NORTH, flits[index-1]);
    end
    return_credit(PORT_NORTH, output_vc);
    step();
    expect_tx(PORT_NORTH, flits[4]);
  endtask

  task automatic test_contention_and_physical_input_conflict;
    logic [FLIT_W-1:0] a [2];
    logic [FLIT_W-1:0] b [2];
    logic [FLIT_W-1:0] east;
    logic [FLIT_W-1:0] north;
    a[0] = header(1'b0, 1'b1, 1'b0, 16'h3000, 104'ha0);
    a[1] = body(1'b1, 104'ha1);
    b[0] = header(1'b0, 1'b1, 1'b0, 16'h3001, 104'hb0);
    b[1] = body(1'b1, 104'hb1);

    reset_router();
    drive_flit(PORT_LOCAL, 0, a[0]);
    drive_flit(PORT_NORTH, 0, b[0]);
    step();
    drive_flit(PORT_LOCAL, 0, a[1]);
    drive_flit(PORT_NORTH, 0, b[1]);
    step();
    step();
    expect_tx(PORT_EAST, a[0]);
    step();
    expect_tx(PORT_EAST, b[0]);
    step();
    expect_tx(PORT_EAST, a[1]);
    step();
    expect_tx(PORT_EAST, b[1]);

    east = header(1'b1, 1'b1, 1'b0, 16'h3010, 104'he);
    north = header(1'b1, 1'b0, 1'b1, 16'h3011, 104'hf);
    reset_router();
    drive_flit(PORT_LOCAL, 0, east);
    step();
    drive_flit(PORT_LOCAL, 1, north);
    step();
    step();
    assert ($countones(observed_tx_valid) == 1)
      else $fatal(1, "one physical input drove multiple outputs");
    step();
    assert ($countones(observed_tx_valid) == 1)
      else $fatal(1, "physical-input loser did not make progress");
  endtask

  task automatic test_zero_credit_and_recovery;
    logic [FLIT_W-1:0] flits [5];
    int output_vc;
    flits[0] = header(1'b0, 1'b1, 1'b0, 16'h4000, 104'h20);
    flits[1] = body(1'b0, 104'h21);
    flits[2] = body(1'b0, 104'h22);
    flits[3] = body(1'b0, 104'h23);
    flits[4] = body(1'b1, 104'h24);

    reset_router();
    for (int index = 0; index < 5; index++) begin
      drive_flit(PORT_LOCAL, 0, flits[index]);
      step();
      if (observed_tx_valid[PORT_EAST])
        output_vc = observed_tx_vc[PORT_EAST];
    end
    step();
    expect_tx(PORT_EAST, flits[3]);
    step();
    expect_no_tx();
    return_credit(PORT_EAST, output_vc);
    step();
    expect_no_tx();
    step();
    expect_tx(PORT_EAST, flits[4]);
  endtask

  task automatic test_concurrent_outputs_and_reset_flush;
    logic [FLIT_W-1:0] east;
    logic [FLIT_W-1:0] north;
    logic [FLIT_W-1:0] replacement;
    east = header(1'b1, 1'b1, 1'b0, 16'h5000, 104'h30);
    north = header(1'b1, 1'b0, 1'b1, 16'h5001, 104'h31);
    replacement = header(1'b1, 1'b1, 1'b0, 16'h5002, 104'h32);

    reset_router();
    drive_flit(PORT_LOCAL, 0, east);
    drive_flit(PORT_NORTH, 1, north);
    step();
    step();
    step();
    assert (observed_tx_valid[PORT_EAST] &&
            observed_tx_valid[PORT_NORTH] &&
            $countones(observed_tx_valid) == 2)
      else $fatal(1, "nonconflicting outputs did not transfer concurrently");
    assert (observed_tx_flit[PORT_EAST] == east &&
            observed_tx_flit[PORT_NORTH] == north)
      else $fatal(1, "concurrent crossbar data mismatch");
    assert (observed_credit_valid[PORT_LOCAL] &&
            observed_credit_valid[PORT_NORTH])
      else $fatal(1, "concurrent transfers missed upstream credits");

    drive_flit(PORT_LOCAL, 0, header(1'b0, 1'b1, 1'b0, 16'h5003, 104'h33));
    step();
    step();
    rst_n = 1'b0;
    step();
    rst_n = 1'b1;
    step();
    expect_no_tx();
    drive_flit(PORT_LOCAL, 0, replacement);
    step();
    step();
    step();
    expect_tx(PORT_EAST, replacement);
  endtask

  task automatic test_disabled_output;
    logic [FLIT_W-1:0] blocked;
    blocked = header(1'b1, 1'b1, 1'b0, 16'h6000, 104'h40);
    enable_all_ports();
    port_enable[PORT_EAST] = 1'b0;
    reset_router();
    drive_flit(PORT_LOCAL, 0, blocked);
    step();
    repeat (5) begin
      step();
      expect_no_tx();
    end
    enable_all_ports();
  endtask

  initial begin
    clear_inputs();
    enable_all_ports();
    @(negedge clk);
    test_head_tail_and_encoding();
    test_bubbles_and_throughput();
    test_contention_and_physical_input_conflict();
    test_zero_credit_and_recovery();
    test_concurrent_outputs_and_reset_flush();
    test_disabled_output();
    $display("PASS: directed Core v0.2 RTL transitions");
    $finish;
  end
endmodule
