`timescale 1ns/1ps

package bifrost_pkg;
  // Core v0.2 fixes the externally visible widths and numeric encodings. RTL
  // modules repeat selected values as parameters for integration readability,
  // but simulation assertions reject configurations outside this baseline.
  parameter int PORTS = 5;
  parameter int FLIT_W = 128;
  parameter int NUM_VCS = 2;
  parameter int VC_DEPTH = 4;
  parameter int PORT_ID_W = 3;
  parameter int VC_ID_W = 1;

  typedef enum logic [PORT_ID_W-1:0] {
    PORT_LOCAL = 3'd0,
    PORT_NORTH = 3'd1,
    PORT_SOUTH = 3'd2,
    PORT_EAST  = 3'd3,
    PORT_WEST  = 3'd4
  } port_id_t;

  // Frozen packed-flit positions. Header-only fields span DEST_X_BIT through
  // QOS_LSB; body and tail flits must drive that range to zero. Keeping these
  // names centralized prevents RTL and testbench field layouts from drifting.
  localparam int HEAD_BIT = 127;
  localparam int TAIL_BIT = 126;
  localparam int DEST_X_BIT = 125;
  localparam int DEST_Y_BIT = 124;
  localparam int SOURCE_X_BIT = 123;
  localparam int SOURCE_Y_BIT = 122;
  localparam int PACKET_ID_MSB = 121;
  localparam int PACKET_ID_LSB = 106;
  localparam int QOS_MSB = 105;
  localparam int QOS_LSB = 104;
  localparam int PAYLOAD_MSB = 103;
  localparam int PAYLOAD_LSB = 0;
endpackage
