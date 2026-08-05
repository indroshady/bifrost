`timescale 1ns/1ps

// Registered free-entry count for one downstream virtual channel.
//
// count represents credits already observed before the current edge. The
// router therefore cannot transmit using a credit returned on that same edge.
// A simultaneous send and matching return consumes and restores one entry, so
// the registered count does not change.
module bifrost_credit_counter #(
  parameter int DEPTH = 4,
  parameter int COUNT_W = $clog2(DEPTH + 1),
  parameter int VC_ID_W = 1,
  parameter int VC_INDEX = 0
) (
  input  logic               clk,
  input  logic               rst_n,
  input  logic               enabled,
  input  logic               send,
  input  logic [0:0]         credit_in_valid,
  input  logic [VC_ID_W-1:0] credit_in_vc,
  output logic [COUNT_W-1:0] count
);
  logic matching_credit_return;

  // The physical output shares one credit-return channel across its VCs.
  assign matching_credit_return =
    credit_in_valid && (credit_in_vc == VC_INDEX[VC_ID_W-1:0]);

  // Credit-state update only. Safety and interface assumptions are checked in
  // the separate simulation-only block below.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      // Disabled ports start with no usable downstream capacity.
      count <= enabled ? DEPTH : '0;
    end else begin
      // Exact Core truth table: simultaneous send and return has no net change.
      case ({send, matching_credit_return})
        2'b10: count <= count - 1'b1;
        2'b01: count <= count + 1'b1;
        default: count <= count;
      endcase
    end
  end

`ifndef SYNTHESIS
  // Simulation-only credit invariants. These assertions observe the same
  // pre-edge count used by the state-update truth table.
  always_ff @(posedge clk) begin : credit_counter_assertions
    if (rst_n) begin
      assert (!(send && count == 0))
        else $fatal(1, "transmit without registered credit");

      assert (!(matching_credit_return && !send && count == DEPTH))
        else $fatal(1, "downstream credit overflow");

      assert (enabled || !(send || matching_credit_return))
        else $fatal(1, "credit event on disabled output");
    end
  end
`endif
endmodule
