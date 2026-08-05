`timescale 1ns/1ps

// Readable 5x5 physical crossbar. The selected owner includes its input VC so
// the mux forwards the exact FIFO head chosen by the switch matcher.
module bifrost_crossbar #(
  parameter int PORTS = bifrost_pkg::PORTS,
  parameter int NUM_VCS = bifrost_pkg::NUM_VCS,
  parameter int FLIT_W = bifrost_pkg::FLIT_W,
  parameter int OWNER_W = $clog2(PORTS * NUM_VCS)
) (
  input  logic [FLIT_W-1:0] input_flit [PORTS][NUM_VCS],
  input  logic              selected_valid [PORTS],
  input  logic [OWNER_W-1:0] selected_owner [PORTS],
  output logic [FLIT_W-1:0] output_flit [PORTS]
);
  generate
    for (genvar output_port = 0; output_port < PORTS; output_port++) begin : g_output
      logic [FLIT_W-1:0] selected_flit;

      always_comb begin
        selected_flit = '0;
        if (selected_valid[output_port]) begin
          for (integer input_port = 0; input_port < PORTS; input_port++) begin
            for (integer input_vc = 0; input_vc < NUM_VCS; input_vc++) begin
              if (selected_owner[output_port] ==
                  input_port * NUM_VCS + input_vc)
                selected_flit = input_flit[input_port][input_vc];
            end
          end
        end
      end

      assign output_flit[output_port] = selected_flit;
    end
  endgenerate
endmodule
