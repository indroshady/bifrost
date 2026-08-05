`timescale 1ns/1ps

module tb_bifrost_random;
  import bifrost_pkg::*;

  localparam int TARGET_FLITS = 80;
  localparam logic [31:0] RECORDED_SEED = 32'h0B1F205E;

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

  logic [FLIT_W-1:0] expected [PORTS][NUM_VCS][256];
  int write_index [PORTS][NUM_VCS];
  int read_index [PORTS][NUM_VCS];
  int outstanding [PORTS][NUM_VCS];
  logic [PORTS-1:0] sampled_tx_valid;
  logic [FLIT_W-1:0] sampled_tx_flit [PORTS];
  logic [VC_ID_W-1:0] sampled_tx_vc [PORTS];
  logic [PORTS-1:0] sampled_credit_valid;
  logic [VC_ID_W-1:0] sampled_credit_vc [PORTS];
  logic [31:0] lfsr;
  int accepted;
  int transmitted;

  bifrost_router dut (.*);
  always #5 clk = ~clk;

  function automatic logic [31:0] next_lfsr(input logic [31:0] value);
    next_lfsr = {value[30:0], value[31] ^ value[21] ^ value[1] ^ value[0]};
  endfunction

  function automatic logic [FLIT_W-1:0] packet(
    input logic destination_x,
    input logic destination_y,
    input logic [15:0] packet_id
  );
    packet = '0;
    packet[HEAD_BIT] = 1'b1;
    packet[TAIL_BIT] = 1'b1;
    packet[DEST_X_BIT] = destination_x;
    packet[DEST_Y_BIT] = destination_y;
    packet[PACKET_ID_MSB:PACKET_ID_LSB] = packet_id;
    packet[PAYLOAD_MSB:PAYLOAD_LSB] = {88'h0, packet_id};
  endfunction

  function automatic int expected_output(input logic [FLIT_W-1:0] flit);
    if (flit[DEST_X_BIT])
      expected_output = PORT_EAST;
    else if (flit[DEST_Y_BIT])
      expected_output = PORT_NORTH;
    else
      expected_output = PORT_LOCAL;
  endfunction

  task automatic clear_drives;
    for (int port = 0; port < PORTS; port++) begin
      rx_valid[port] = 1'b0;
      rx_flit[port] = '0;
      rx_vc[port] = '0;
      credit_in_valid[port] = 1'b0;
      credit_in_vc[port] = '0;
    end
  endtask

  task automatic sample_and_commit;
    #4;
    for (int port = 0; port < PORTS; port++) begin
      sampled_tx_valid[port] = tx_valid[port];
      sampled_tx_flit[port] = tx_flit[port];
      sampled_tx_vc[port] = tx_vc[port];
      sampled_credit_valid[port] = credit_out_valid[port];
      sampled_credit_vc[port] = credit_out_vc[port];
    end
    @(posedge clk);
    #1;
    @(negedge clk);
  endtask

  initial begin
    clear_drives();
    lfsr = RECORDED_SEED;
    accepted = 0;
    transmitted = 0;
    for (int port = 0; port < PORTS; port++) begin
      port_enable[port] = 1'b1;
      for (int vc = 0; vc < NUM_VCS; vc++) begin
        write_index[port][vc] = 0;
        read_index[port][vc] = 0;
        outstanding[port][vc] = 0;
      end
    end

    @(negedge clk);
    sample_and_commit();
    rst_n = 1'b1;

    for (int cycle = 0; cycle < 1000; cycle++) begin
      clear_drives();

      // Return each observed downstream credit on the following cycle.
      for (int output_port = 0; output_port < PORTS; output_port++) begin
        if (sampled_tx_valid[output_port]) begin
          credit_in_valid[output_port] = 1'b1;
          credit_in_vc[output_port] = sampled_tx_vc[output_port];
        end
      end

      // Recorded LFSR seed generates deterministic, independently scored traffic.
      for (int input_port = 0; input_port < PORTS; input_port++) begin
        int vc;
        logic [FLIT_W-1:0] flit;
        lfsr = next_lfsr(lfsr);
        vc = lfsr[0];
        if (accepted < TARGET_FLITS && outstanding[input_port][vc] < VC_DEPTH &&
            lfsr[3:1] != 0) begin
          flit = packet(lfsr[4], lfsr[5], accepted[15:0]);
          rx_valid[input_port] = 1'b1;
          rx_vc[input_port] = vc[VC_ID_W-1:0];
          rx_flit[input_port] = flit;
          expected[input_port][vc][write_index[input_port][vc]] = flit;
          write_index[input_port][vc]++;
          outstanding[input_port][vc]++;
          accepted++;
        end
      end

      sample_and_commit();

      // credit_out identifies the originating input/VC, forming an independent
      // conservation and per-VC ordering scoreboard for each crossbar transfer.
      assert ($countones(sampled_tx_valid) == $countones(sampled_credit_valid))
        else $fatal(1, "seed=%h cycle=%0d transfer/credit bijection failed",
                    RECORDED_SEED, cycle);
      for (int output_port = 0; output_port < PORTS; output_port++) begin
        if (sampled_tx_valid[output_port]) begin
          int matching_inputs;
          matching_inputs = 0;
          for (int input_port = 0; input_port < PORTS; input_port++) begin
            if (sampled_credit_valid[input_port]) begin
              int vc;
              vc = sampled_credit_vc[input_port];
              if (expected[input_port][vc][read_index[input_port][vc]] ==
                  sampled_tx_flit[output_port]) begin
                assert (expected_output(sampled_tx_flit[output_port]) == output_port)
                  else $fatal(1, "seed=%h cycle=%0d XY route mismatch",
                              RECORDED_SEED, cycle);
                read_index[input_port][vc]++;
                outstanding[input_port][vc]--;
                matching_inputs++;
                transmitted++;
              end
            end
          end
          assert (matching_inputs == 1)
            else $fatal(1, "seed=%h cycle=%0d loss, duplicate, or reordering",
                        RECORDED_SEED, cycle);
        end
      end

      if (accepted == TARGET_FLITS && transmitted == TARGET_FLITS) begin
        assert ($countones(sampled_tx_valid) == $countones(sampled_credit_valid))
          else $fatal(1, "transfer and upstream credit counts diverged");
        $display("PASS: seed=%h accepted=%0d transmitted=%0d",
                 RECORDED_SEED, accepted, transmitted);
        $finish;
      end
    end
    $fatal(1, "seed=%h random test did not drain: accepted=%0d transmitted=%0d",
           RECORDED_SEED, accepted, transmitted);
  end
endmodule
