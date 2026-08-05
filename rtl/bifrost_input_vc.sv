`timescale 1ns/1ps

// One independently buffered receive virtual channel.
//
// The FIFO stores complete flits and returns one upstream credit for each
// dequeue performed by the router. Packet-boundary tracking is intentionally
// independent of FIFO occupancy: receive_packet_active follows the source
// stream at enqueue time, so it remains valid even when the FIFO drains between
// two flits of the same packet.
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

  // read_ptr identifies the currently visible head entry. write_ptr identifies
  // the next entry accepted from the physical input.
  logic [FLIT_W-1:0] storage [DEPTH];
  logic [PTR_W-1:0] read_ptr;
  logic [PTR_W-1:0] write_ptr;
  logic [COUNT_W-1:0] count;

  // This state validates packet markers on the incoming stream; it does not
  // describe the packet currently at the FIFO head.
  logic receive_packet_active;

  // Storage data is intentionally not reset. count is the sole validity state,
  // so stale RAM contents are never consumed after reset.
  assign empty = (count == 0);
  assign full = (count == DEPTH);
  assign head_flit = storage[read_ptr];

  // FIFO and receive packet-state updates. Protocol enforcement lives in the
  // separate assertion block below so this block contains synthesizable state
  // transitions only.
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      read_ptr <= '0;
      write_ptr <= '0;
      count <= '0;
      receive_packet_active <= 1'b0;
    end else begin
      // Only the VC selected by receive_vc accepts the shared physical input.
      // A simultaneous enqueue and dequeue replaces one entry and leaves count
      // unchanged.
      if (receive_valid && (receive_vc == VC_INDEX[VC_ID_W-1:0])) begin
        storage[write_ptr] <= enqueue_flit;
        write_ptr <= (write_ptr == DEPTH-1) ? '0 : write_ptr + 1'b1;

        // A head opens a packet unless it is also a tail. A tail closes the
        // packet. Marker legality is checked independently below.
        if (!receive_packet_active) begin
          receive_packet_active <= !enqueue_flit[TAIL_BIT];
        end else if (enqueue_flit[TAIL_BIT]) begin
          receive_packet_active <= 1'b0;
        end
      end

      if (dequeue) begin
        read_ptr <= (read_ptr == DEPTH-1) ? '0 : read_ptr + 1'b1;
      end

      // Occupancy changes only when exactly one side of the FIFO transfers.
      case ({receive_valid && (receive_vc == VC_INDEX[VC_ID_W-1:0]), dequeue})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end

`ifndef SYNTHESIS
  // Simulation-only input protocol and FIFO safety checks. Keeping these checks
  // separate from the state-update block makes the hardware behavior readable
  // and allows synthesis flows to remove all assertion machinery by defining
  // SYNTHESIS.
  always_ff @(posedge clk) begin : input_vc_assertions
    if (rst_n) begin
      if (receive_valid && (receive_vc == VC_INDEX[VC_ID_W-1:0])) begin
        assert (!full)
          else $fatal(1, "input VC FIFO overflow");

        // An idle VC must receive a head. An active packet must receive a
        // body/tail flit rather than another head.
        assert ((!receive_packet_active && enqueue_flit[HEAD_BIT]) ||
                (receive_packet_active && !enqueue_flit[HEAD_BIT]))
          else $fatal(1,
                      "illegal packet marker sequence active=%b head=%b flit=%h",
                      receive_packet_active, enqueue_flit[HEAD_BIT], enqueue_flit);

        // Header-only routing and identity fields must not be repeated on body
        // or tail flits.
        if (!enqueue_flit[HEAD_BIT]) begin
          assert (enqueue_flit[DEST_X_BIT:QOS_LSB] == '0)
            else $fatal(1, "body/tail header-only fields must be zero");
        end
      end

      assert (!dequeue || !empty)
        else $fatal(1, "input VC FIFO underflow");
    end
  end
`endif
endmodule
