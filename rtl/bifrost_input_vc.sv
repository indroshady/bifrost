`timescale 1ns/1ps

// One independently buffered receive VC. FIFO occupancy tracks stored flits,
// while receive_packet_active tracks packet boundaries across FIFO drain bubbles.
module bifrost_input_vc #(
  parameter int FLIT_W = 128,
  parameter int DEPTH = 4,
  parameter int VC_ID_W = 1,
  parameter int VC_INDEX = 0
) (
  input  logic              clk,
  input  logic              rst_n,
  input  logic [0:0]        receive_valid,
  input  logic [VC_ID_W-1:0] receive_vc,
  input  logic [FLIT_W-1:0] enqueue_flit,
  input  logic              dequeue,
  output logic [FLIT_W-1:0] head_flit,
  output logic              empty,
  output logic              full
);
  import bifrost_pkg::*;

  localparam int PTR_W = (DEPTH <= 1) ? 1 : $clog2(DEPTH);
  localparam int COUNT_W = $clog2(DEPTH + 1);

  logic [FLIT_W-1:0] storage [DEPTH];
  logic [PTR_W-1:0] read_ptr;
  logic [PTR_W-1:0] write_ptr;
  logic [COUNT_W-1:0] count;
  logic receive_packet_active;

  // Storage data is intentionally not reset. Empty/count is the validity state,
  // so reset behavior never depends on stale memory contents.
  assign empty = (count == 0);
  assign full = (count == DEPTH);
  assign head_flit = storage[read_ptr];

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      read_ptr <= '0;
      write_ptr <= '0;
      count <= '0;
      receive_packet_active <= 1'b0;
    end else begin
      // Decode the physical receive channel at the accepting clock edge. This
      // keeps the VC selection beside the state it controls and ensures a
      // simulator need not infer combinational sensitivity through an unpacked
      // top-level port array.
      if (receive_valid && (receive_vc == VC_INDEX[VC_ID_W-1:0])) begin
        assert (!full)
          else $fatal(1, "input VC FIFO overflow");
        // Validate the source stream at acceptance, independently of whether an
        // older flit from this VC also leaves on the same edge.
        if ((!receive_packet_active && !enqueue_flit[HEAD_BIT]) ||
            (receive_packet_active && enqueue_flit[HEAD_BIT]))
          $fatal(1, "illegal packet marker sequence active=%b head=%b flit=%h",
                 receive_packet_active, enqueue_flit[HEAD_BIT], enqueue_flit);
        if (!enqueue_flit[HEAD_BIT]) begin
          assert (enqueue_flit[DEST_X_BIT:QOS_LSB] == '0)
            else $fatal(1, "body/tail header-only fields must be zero");
        end

        storage[write_ptr] <= enqueue_flit;
        write_ptr <= (write_ptr == DEPTH-1) ? '0 : write_ptr + 1'b1;
        if (!receive_packet_active) begin
          receive_packet_active <= !enqueue_flit[TAIL_BIT];
        end else if (enqueue_flit[TAIL_BIT]) begin
          receive_packet_active <= 1'b0;
        end
      end

      if (dequeue) begin
        assert (!empty)
          else $fatal(1, "input VC FIFO underflow");
        read_ptr <= (read_ptr == DEPTH-1) ? '0 : read_ptr + 1'b1;
      end

      case ({receive_valid && (receive_vc == VC_INDEX[VC_ID_W-1:0]), dequeue})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end
endmodule
