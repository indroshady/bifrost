`timescale 1ns/1ps

// Pure deterministic XY decode for one buffered header. X is always resolved
// before Y, and increasing Y maps to North.
module bifrost_route_decode #(
  parameter int FLIT_W = bifrost_pkg::FLIT_W,
  parameter int X_W = 1,
  parameter int Y_W = 1,
  parameter int ROUTER_X = 0,
  parameter int ROUTER_Y = 0,
  parameter int PORT_ID_W = bifrost_pkg::PORT_ID_W
) (
  input  logic [FLIT_W-1:0] flit,
  output logic [PORT_ID_W-1:0] route
);
  import bifrost_pkg::*;

  always_comb begin
    if (flit[DEST_X_BIT] > ROUTER_X[X_W-1:0])
      route = PORT_EAST;
    else if (flit[DEST_X_BIT] < ROUTER_X[X_W-1:0])
      route = PORT_WEST;
    else if (flit[DEST_Y_BIT] > ROUTER_Y[Y_W-1:0])
      route = PORT_NORTH;
    else if (flit[DEST_Y_BIT] < ROUTER_Y[Y_W-1:0])
      route = PORT_SOUTH;
    else
      route = PORT_LOCAL;
  end
endmodule
