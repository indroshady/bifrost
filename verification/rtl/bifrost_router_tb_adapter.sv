`timescale 1ns/1ps

// Verification-only shape adapter. The design-facing side preserves the frozen
// unpacked scalar arrays; the testbench-facing side packs one-bit event signals
// so masks and one-hot checks stay concise. No router behavior lives here.
module bifrost_router_tb_adapter #(
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
  input  logic                      clk,
  input  logic                      rst_n,
  input  logic [PORTS-1:0]          port_enable,
  input  logic [PORTS-1:0]          rx_valid,
  input  logic [FLIT_W-1:0]         rx_flit [PORTS],
  input  logic [VC_ID_W-1:0]        rx_vc [PORTS],
  output logic [PORTS-1:0]          tx_valid,
  output logic [FLIT_W-1:0]         tx_flit [PORTS],
  output logic [VC_ID_W-1:0]        tx_vc [PORTS],
  output logic [PORTS-1:0]          credit_out_valid,
  output logic [VC_ID_W-1:0]        credit_out_vc [PORTS],
  input  logic [PORTS-1:0]          credit_in_valid,
  input  logic [VC_ID_W-1:0]        credit_in_vc [PORTS]
);
  wire port_enable_u [PORTS];
  wire rx_valid_u [PORTS];
  wire tx_valid_u [PORTS];
  wire credit_out_valid_u [PORTS];
  wire credit_in_valid_u [PORTS];

  generate
    for (genvar port = 0; port < PORTS; port++) begin : g_port
      assign port_enable_u[port] = port_enable[port];
      assign rx_valid_u[port] = rx_valid[port];
      assign tx_valid[port] = tx_valid_u[port];
      assign credit_out_valid[port] = credit_out_valid_u[port];
      assign credit_in_valid_u[port] = credit_in_valid[port];
    end
  endgenerate

  bifrost_router #(
    .PORTS(PORTS),
    .FLIT_W(FLIT_W),
    .NUM_VCS(NUM_VCS),
    .VC_DEPTH(VC_DEPTH),
    .X_W(X_W),
    .Y_W(Y_W),
    .ROUTER_X(ROUTER_X),
    .ROUTER_Y(ROUTER_Y),
    .MESH_X(MESH_X),
    .MESH_Y(MESH_Y),
    .PORT_ID_W(PORT_ID_W),
    .VC_ID_W(VC_ID_W)
  ) u_router (
    .clk,
    .rst_n,
    .port_enable(port_enable_u),
    .rx_valid(rx_valid_u),
    .rx_flit,
    .rx_vc,
    .tx_valid(tx_valid_u),
    .tx_flit,
    .tx_vc,
    .credit_out_valid(credit_out_valid_u),
    .credit_out_vc,
    .credit_in_valid(credit_in_valid_u),
    .credit_in_vc
  );
endmodule
