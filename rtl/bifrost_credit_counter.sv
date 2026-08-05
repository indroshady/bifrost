`timescale 1ns/1ps

// Registered free-entry count for one downstream VC. Authorization is based on
// count before the edge, so credit_return never creates a zero-credit bypass.
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
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      count <= enabled ? DEPTH : '0;
    end else begin
      assert (!(send && count == 0))
        else $fatal(1, "transmit without registered credit");
      assert (!((credit_in_valid && (credit_in_vc == VC_INDEX[VC_ID_W-1:0])) &&
                !send && count == DEPTH))
        else $fatal(1, "downstream credit overflow");
      assert (enabled ||
              !(send ||
                (credit_in_valid && (credit_in_vc == VC_INDEX[VC_ID_W-1:0]))))
        else $fatal(1, "credit event on disabled output");

      // Exact Core truth table: simultaneous send and return has no net change.
      case ({send,
             credit_in_valid && (credit_in_vc == VC_INDEX[VC_ID_W-1:0])})
        2'b10: count <= count - 1'b1;
        2'b01: count <= count + 1'b1;
        default: count <= count;
      endcase
    end
  end
endmodule
