`timescale 1ns/1ps

// Hand-written Core v0.2 five-port wormhole router.
//
// Input VCs buffer complete flits. A header first reserves one output VC, then
// switch arbitration forwards eligible flits while preserving that reservation
// until the packet tail transfers. The top level owns allocation, arbitration,
// packet reservations, and cycle integration; buffering, route decode, credit
// accounting, and datapath muxing remain in focused submodules.
module bifrost_router #(
  parameter int PORTS = bifrost_pkg::PORTS,
  parameter int FLIT_W = bifrost_pkg::FLIT_W,
  parameter int NUM_VCS = bifrost_pkg::NUM_VCS,
  parameter int VC_DEPTH = bifrost_pkg::VC_DEPTH,
  parameter int X_W = 1,
  parameter int Y_W = 1,
  parameter int ROUTER_X = 0,
  parameter int ROUTER_Y = 0,
  parameter int MESH_X = 2,
  parameter int MESH_Y = 2,
  parameter int PORT_ID_W = bifrost_pkg::PORT_ID_W,
  parameter int VC_ID_W = bifrost_pkg::VC_ID_W
) (
  input  logic                       clk,
  input  logic                       rst_n,
  input  logic [0:0]                 port_enable [PORTS],
  input  logic [0:0]                 rx_valid [PORTS],
  input  logic [FLIT_W-1:0]          rx_flit [PORTS],
  input  logic [VC_ID_W-1:0]         rx_vc [PORTS],
  output logic [0:0]                 tx_valid [PORTS],
  output logic [FLIT_W-1:0]          tx_flit [PORTS],
  output logic [VC_ID_W-1:0]         tx_vc [PORTS],
  output logic [0:0]                 credit_out_valid [PORTS],
  output logic [VC_ID_W-1:0]         credit_out_vc [PORTS],
  input  logic [0:0]                 credit_in_valid [PORTS],
  input  logic [VC_ID_W-1:0]         credit_in_vc [PORTS]
);
  import bifrost_pkg::*;

  localparam int OWNER_COUNT = PORTS * NUM_VCS;
  localparam int OWNER_W = $clog2(OWNER_COUNT);
  localparam int CREDIT_W = $clog2(VC_DEPTH + 1);

  // Ten independent input VCs hold received flits. Route decode is combinational
  // from each FIFO head and becomes meaningful whenever that FIFO is nonempty.
  logic [FLIT_W-1:0] fifo_head [PORTS][NUM_VCS];
  logic fifo_empty [PORTS][NUM_VCS];
  logic fifo_full [PORTS][NUM_VCS];
  logic fifo_dequeue [PORTS][NUM_VCS];
  logic [PORT_ID_W-1:0] decoded_route [PORTS][NUM_VCS];

  // Packet state is separate from FIFO occupancy so an active packet can retain
  // its route and output VC while its input FIFO is temporarily empty.
  logic route_valid [PORTS][NUM_VCS];
  logic [PORT_ID_W-1:0] route_cache [PORTS][NUM_VCS];
  logic [VC_ID_W-1:0] assigned_vc [PORTS][NUM_VCS];

  // One authoritative ownership entry and one independent credit counter exist
  // for every output VC.
  logic output_vc_owned [PORTS][NUM_VCS];
  logic [OWNER_W-1:0] output_vc_owner [PORTS][NUM_VCS];
  logic [CREDIT_W-1:0] credit_count [PORTS][NUM_VCS];
  logic send_for_vc [PORTS][NUM_VCS];

  // Round-robin histories advance only after the operation they arbitrate
  // succeeds. Failed requests therefore retain their relative priority.
  logic [OWNER_W-1:0] allocation_pointer [PORTS];
  logic [VC_ID_W-1:0] free_vc_pointer [PORTS];
  logic [OWNER_W-1:0] switch_pointer [PORTS];
  logic [PORT_ID_W-1:0] input_pointer [PORTS];

  logic allocation_valid [PORTS];
  logic [OWNER_W-1:0] allocation_owner [PORTS];
  logic [VC_ID_W-1:0] allocation_vc [PORTS];
  logic proposal_valid [PORTS];
  logic [OWNER_W-1:0] proposal_owner [PORTS];
  logic selected_valid [PORTS];
  logic [OWNER_W-1:0] selected_owner [PORTS];
  logic [VC_ID_W-1:0] selected_output_vc [PORTS];

  generate
    for (genvar input_port = 0; input_port < PORTS; input_port++) begin : g_input
      for (genvar input_vc = 0; input_vc < NUM_VCS; input_vc++) begin : g_vc
        logic [FLIT_W-1:0] selected_rx_flit;
        logic [FLIT_W-1:0] selected_head_flit;
        logic selected_dequeue;
        logic selected_empty;
        logic selected_full;

        assign selected_rx_flit = rx_flit[input_port];
        assign selected_dequeue = fifo_dequeue[input_port][input_vc];
        assign fifo_head[input_port][input_vc] = selected_head_flit;
        assign fifo_empty[input_port][input_vc] = selected_empty;
        assign fifo_full[input_port][input_vc] = selected_full;

        bifrost_input_vc #(
          .FLIT_W(FLIT_W),
          .DEPTH(VC_DEPTH),
          .VC_ID_W(VC_ID_W),
          .VC_INDEX(input_vc)
        ) u_fifo (
          .clk,
          .rst_n,
          .receive_valid(rx_valid[input_port]),
          .receive_vc(rx_vc[input_port]),
          .enqueue_flit(selected_rx_flit),
          .dequeue(selected_dequeue),
          .head_flit(selected_head_flit),
          .empty(selected_empty),
          .full(selected_full)
        );

        bifrost_route_decode #(
          .FLIT_W(FLIT_W),
          .X_W(X_W),
          .Y_W(Y_W),
          .ROUTER_X(ROUTER_X),
          .ROUTER_Y(ROUTER_Y),
          .PORT_ID_W(PORT_ID_W)
        ) u_route (
          .flit(selected_head_flit),
          .route(decoded_route[input_port][input_vc])
        );
      end
    end

    for (genvar output_port = 0; output_port < PORTS; output_port++) begin : g_output
      for (genvar output_vc = 0; output_vc < NUM_VCS; output_vc++) begin : g_vc
        assign send_for_vc[output_port][output_vc] =
          selected_valid[output_port] &&
          (selected_output_vc[output_port] == output_vc);

        bifrost_credit_counter #(
          .DEPTH(VC_DEPTH),
          .COUNT_W(CREDIT_W),
          .VC_ID_W(VC_ID_W),
          .VC_INDEX(output_vc)
        ) u_credit (
          .clk,
          .rst_n,
          .enabled(port_enable[output_port]),
          .send(send_for_vc[output_port][output_vc]),
          .credit_in_valid(credit_in_valid[output_port]),
          .credit_in_vc(credit_in_vc[output_port]),
          .count(credit_count[output_port][output_vc])
        );
      end

      assign tx_valid[output_port] = rst_n && selected_valid[output_port];
      assign tx_vc[output_port] =
        selected_valid[output_port] ? selected_output_vc[output_port] : '0;
    end

    for (genvar input_port = 0; input_port < PORTS; input_port++) begin : g_input_match
      logic [VC_ID_W-1:0] returned_vc;
      logic returned_valid;
      always_comb begin
        returned_vc = '0;
        returned_valid = 1'b0;
        for (integer input_vc = 0; input_vc < NUM_VCS; input_vc++) begin
          if (fifo_dequeue[input_port][input_vc]) begin
            returned_vc = input_vc[VC_ID_W-1:0];
            returned_valid = 1'b1;
          end
        end
      end
      assign credit_out_valid[input_port] = rst_n && returned_valid;
      assign credit_out_vc[input_port] = returned_vc;
    end
  endgenerate

  bifrost_crossbar #(
    .PORTS(PORTS),
    .NUM_VCS(NUM_VCS),
    .FLIT_W(FLIT_W),
    .OWNER_W(OWNER_W)
  ) u_crossbar (
    .input_flit(fifo_head),
    .selected_valid,
    .selected_owner,
    .output_flit(tx_flit)
  );

  // Full combinational match from registered state. Keeping the phases together
  // makes cycle ordering explicit and avoids delta-cycle coupling between
  // array-valued arbiter instances.
  always_comb begin : router_control
    integer output_port;
    integer input_port;
    integer input_vc;
    integer owner;
    integer offset;
    integer candidate;
    integer candidate_port;
    integer candidate_vc;
    integer chosen_vc;
    logic found;

    // Defaults describe a cycle with no allocation, proposal, transfer, or
    // dequeue. Every asserted event below therefore has one visible cause.
    for (output_port = 0; output_port < PORTS; output_port++) begin
      allocation_valid[output_port] = 1'b0;
      allocation_owner[output_port] = '0;
      allocation_vc[output_port] = '0;
      proposal_valid[output_port] = 1'b0;
      proposal_owner[output_port] = '0;
      selected_valid[output_port] = 1'b0;
      selected_owner[output_port] = '0;
      selected_output_vc[output_port] = '0;
    end
    for (input_port = 0; input_port < PORTS; input_port++) begin
      for (input_vc = 0; input_vc < NUM_VCS; input_vc++)
        fifo_dequeue[input_port][input_vc] = 1'b0;
    end

    // Phase 1: output-VC allocation. Each enabled output first chooses a free VC
    // and then chooses one buffered, unallocated header routed to that output.
    // The two searches use independent round-robin histories.
    for (output_port = 0; output_port < PORTS; output_port++) begin
      found = 1'b0;
      chosen_vc = 0;
      for (offset = 0; offset < NUM_VCS; offset++) begin
        candidate = (free_vc_pointer[output_port] + offset) % NUM_VCS;
        if (!found && !output_vc_owned[output_port][candidate]) begin
          found = 1'b1;
          chosen_vc = candidate;
        end
      end
      if (found && port_enable[output_port]) begin
        found = 1'b0;
        for (offset = 0; offset < OWNER_COUNT; offset++) begin
          owner = (allocation_pointer[output_port] + offset) % OWNER_COUNT;
          candidate_port = owner / NUM_VCS;
          candidate_vc = owner % NUM_VCS;
          if (!found &&
              !route_valid[candidate_port][candidate_vc] &&
              !fifo_empty[candidate_port][candidate_vc] &&
              fifo_head[candidate_port][candidate_vc][HEAD_BIT] &&
              decoded_route[candidate_port][candidate_vc] == output_port) begin
            found = 1'b1;
            allocation_valid[output_port] = 1'b1;
            allocation_owner[output_port] = owner[OWNER_W-1:0];
            allocation_vc[output_port] = chosen_vc[VC_ID_W-1:0];
          end
        end
      end
    end

    // Phase 2: switch proposals. Each output proposes at most one packet that
    // already owns an output VC, has a buffered flit, and has registered credit.
    // Same-cycle credit returns are intentionally not bypassed into eligibility.
    for (output_port = 0; output_port < PORTS; output_port++) begin
      found = 1'b0;
      if (port_enable[output_port]) begin
        for (offset = 0; offset < OWNER_COUNT; offset++) begin
          owner = (switch_pointer[output_port] + offset) % OWNER_COUNT;
          candidate_port = owner / NUM_VCS;
          candidate_vc = owner % NUM_VCS;
          if (!found &&
              route_valid[candidate_port][candidate_vc] &&
              route_cache[candidate_port][candidate_vc] == output_port &&
              !fifo_empty[candidate_port][candidate_vc] &&
              credit_count[output_port][assigned_vc[candidate_port][candidate_vc]] > 0) begin
            found = 1'b1;
            proposal_valid[output_port] = 1'b1;
            proposal_owner[output_port] = owner[OWNER_W-1:0];
          end
        end
      end
    end

    // Phase 3: input conflict resolution. Multiple outputs can propose flits from
    // different VCs on one physical input, but the input datapath can service
    // only one. Losing outputs do not choose a fallback requester this cycle.
    for (input_port = 0; input_port < PORTS; input_port++) begin
      found = 1'b0;
      for (offset = 0; offset < PORTS; offset++) begin
        output_port = (input_pointer[input_port] + offset) % PORTS;
        candidate_port = proposal_owner[output_port] / NUM_VCS;
        if (!found && proposal_valid[output_port] &&
            candidate_port == input_port) begin
          found = 1'b1;
          selected_valid[output_port] = 1'b1;
          selected_owner[output_port] = proposal_owner[output_port];
        end
      end
    end

    // Decode accepted owner IDs once to drive output VC sidebands and exactly
    // one FIFO dequeue. The crossbar module uses the same owner IDs for data.
    for (output_port = 0; output_port < PORTS; output_port++) begin
      if (selected_valid[output_port]) begin
        candidate_port = selected_owner[output_port] / NUM_VCS;
        candidate_vc = selected_owner[output_port] % NUM_VCS;
        selected_output_vc[output_port] =
          assigned_vc[candidate_port][candidate_vc];
        fifo_dequeue[candidate_port][candidate_vc] = 1'b1;
      end
    end
  end

  // Packet-level state and fairness history. FIFO occupancy and downstream
  // credits commit in their submodules on this same edge. Assertions are kept in
  // independent simulation-only blocks after the functional logic.
  always_ff @(posedge clk) begin : packet_state
    integer output_port;
    integer input_port;
    integer input_vc;
    integer owner;
    integer owner_port;
    integer owner_vc;

    if (!rst_n) begin
      for (input_port = 0; input_port < PORTS; input_port++) begin
        input_pointer[input_port] <= '0;
        for (input_vc = 0; input_vc < NUM_VCS; input_vc++) begin
          route_valid[input_port][input_vc] <= 1'b0;
          route_cache[input_port][input_vc] <= PORT_LOCAL;
          assigned_vc[input_port][input_vc] <= '0;
        end
      end
      for (output_port = 0; output_port < PORTS; output_port++) begin
        allocation_pointer[output_port] <= '0;
        free_vc_pointer[output_port] <= '0;
        switch_pointer[output_port] <= '0;
        for (input_vc = 0; input_vc < NUM_VCS; input_vc++) begin
          output_vc_owned[output_port][input_vc] <= 1'b0;
          output_vc_owner[output_port][input_vc] <= '0;
        end
      end
    end else begin
      for (output_port = 0; output_port < PORTS; output_port++) begin
        if (allocation_valid[output_port]) begin
          owner = allocation_owner[output_port];
          owner_port = owner / NUM_VCS;
          owner_vc = owner % NUM_VCS;
          output_vc_owned[output_port][allocation_vc[output_port]] <= 1'b1;
          output_vc_owner[output_port][allocation_vc[output_port]] <= owner;
          route_valid[owner_port][owner_vc] <= 1'b1;
          route_cache[owner_port][owner_vc] <= output_port[PORT_ID_W-1:0];
          assigned_vc[owner_port][owner_vc] <= allocation_vc[output_port];
          allocation_pointer[output_port] <=
            (owner == OWNER_COUNT-1) ? '0 : owner + 1'b1;
          free_vc_pointer[output_port] <=
            (allocation_vc[output_port] == NUM_VCS-1) ? '0
                                                     : allocation_vc[output_port] + 1'b1;
        end

        if (selected_valid[output_port]) begin
          owner = selected_owner[output_port];
          owner_port = owner / NUM_VCS;
          owner_vc = owner % NUM_VCS;
          switch_pointer[output_port] <=
            (owner == OWNER_COUNT-1) ? '0 : owner + 1'b1;
          input_pointer[owner_port] <=
            (output_port == PORTS-1) ? '0 : output_port + 1'b1;

          // HEAD+TAIL and ordinary tails take this same exact release path.
          if (fifo_head[owner_port][owner_vc][TAIL_BIT]) begin
            output_vc_owned[output_port][selected_output_vc[output_port]] <= 1'b0;
            route_valid[owner_port][owner_vc] <= 1'b0;
          end
        end
      end
    end
  end

`ifndef SYNTHESIS
  // Internal reservation invariants. These are intentionally separate from
  // packet_state so the state machine contains only functional assignments.
  always_ff @(posedge clk) begin : reservation_assertions
    integer output_port;

    if (rst_n) begin
      for (output_port = 0; output_port < PORTS; output_port++) begin
        if (allocation_valid[output_port]) begin
          assert (!output_vc_owned[output_port][allocation_vc[output_port]])
            else $fatal(1, "output VC allocated twice");
        end

        if (selected_valid[output_port]) begin
          assert (output_vc_owned[output_port][selected_output_vc[output_port]] &&
                  output_vc_owner[output_port][selected_output_vc[output_port]] ==
                    selected_owner[output_port])
            else $fatal(1, "transfer without matching output VC ownership");
        end
      end
    end
  end

  // External interface and packed-flit protocol checks. The Core contract
  // treats these conditions as integration errors; the RTL does not attempt
  // recovery after malformed traffic.
  always_ff @(posedge clk) begin : interface_assertions
    integer input_port;
    integer input_vc;
    integer output_port;

    if (!rst_n) begin
      for (input_port = 0; input_port < PORTS; input_port++) begin
        assert (!rx_valid[input_port] && !credit_in_valid[input_port])
          else $fatal(1, "flit and credit events are illegal during reset");
      end
    end else begin
      for (input_port = 0; input_port < PORTS; input_port++) begin
        if (rx_valid[input_port]) begin
          assert (port_enable[input_port])
            else $fatal(1, "arrival on disabled input port");
          for (input_vc = 0; input_vc < NUM_VCS; input_vc++) begin
            if (rx_vc[input_port] == input_vc)
              assert (!fifo_full[input_port][input_vc])
                else $fatal(1, "arrival to full input VC");
          end
          if (rx_flit[input_port][HEAD_BIT]) begin
            assert (rx_flit[input_port][QOS_MSB:QOS_LSB] == '0)
              else $fatal(1, "Core accepts only QoS class zero");
            assert (rx_flit[input_port][DEST_X_BIT] < MESH_X &&
                    rx_flit[input_port][DEST_Y_BIT] < MESH_Y &&
                    rx_flit[input_port][SOURCE_X_BIT] < MESH_X &&
                    rx_flit[input_port][SOURCE_Y_BIT] < MESH_Y)
              else $fatal(1, "header coordinate outside mesh");
          end
        end
      end
      for (output_port = 0; output_port < PORTS; output_port++) begin
        if (credit_in_valid[output_port])
          assert (port_enable[output_port])
            else $fatal(1, "credit return on disabled output port");
      end
    end
  end

  // Elaboration-time checks document the subset of parameterization implemented
  // by the Core v0.2 baseline.
  initial begin : parameter_assertions
    assert (PORTS == 5 && FLIT_W == 128 && NUM_VCS == 2)
      else $fatal(1, "Core v0.2 frozen interface parameters changed");
    assert (PORT_ID_W == 3 && VC_ID_W == 1)
      else $fatal(1, "Core v0.2 frozen sideband widths changed");
    assert (ROUTER_X >= 0 && ROUTER_X < MESH_X &&
            ROUTER_Y >= 0 && ROUTER_Y < MESH_Y)
      else $fatal(1, "router coordinates outside mesh");
  end
`endif
endmodule
