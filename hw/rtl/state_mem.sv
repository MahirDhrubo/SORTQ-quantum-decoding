// state_mem.sv — per-round state storage for DEPTH (= W) rounds as a ring buffer.
// One slot = one round, WIDTH bits (e.g. one field for all 72 positions of a round). Instantiate one per field
// (syndrome, priors, g8, marginals, memory, v2c / c2v per base edge ...).
//   arrival port : arr_valid / arr_data, written to slot `head` (= next round to arrive), head advances mod DEPTH.
//                  arr_ready = 0 when the buffer is full (DEPTH rounds held) or the engine writes this cycle.
//   engine port  : eng_re / eng_raddr -> eng_rdata after RD_LAT cycles; eng_we / eng_waddr / eng_wdata
//                  (engine write-back has priority over arrival; one write per cycle = simple dual port).
//   free         : release `free_n` oldest slots (after a commit of C rounds).
// STORAGE: "REG" (flip-flops), "LUTRAM" (distributed RAM) or "BRAM" (block RAM); sets the synthesis attribute.
// RD_LAT: 1 = registered read (required for BRAM); 0 = asynchronous read (REG / LUTRAM only).
module state_mem #(
  parameter int    DEPTH   = 12,
  parameter int    WIDTH   = 72,
  parameter string STORAGE = "BRAM",
  parameter int    RD_LAT  = 1,
  localparam int   AW      = (DEPTH > 1) ? $clog2(DEPTH) : 1
) (
  input  logic              clk,
  input  logic              rst,
  input  logic              arr_valid,
  input  logic [WIDTH-1:0]  arr_data,
  output logic              arr_ready,
  output logic [AW-1:0]     head,
  output logic [AW:0]       count,
  input  logic              eng_re,
  input  logic [AW-1:0]     eng_raddr,
  output logic [WIDTH-1:0]  eng_rdata,
  input  logic              eng_we,
  input  logic [AW-1:0]     eng_waddr,
  input  logic [WIDTH-1:0]  eng_wdata,
  input  logic              free,
  input  logic [AW:0]       free_n
);
  initial begin
    if (STORAGE != "REG" && STORAGE != "LUTRAM" && STORAGE != "BRAM") $fatal(1, "state_mem: bad STORAGE %s", STORAGE);
    if (STORAGE == "BRAM" && RD_LAT != 1) $fatal(1, "state_mem: BRAM needs RD_LAT = 1");
  end

  logic          we;
  logic [AW-1:0] waddr;
  logic [WIDTH-1:0] wdata;
  logic          arr_go;

  assign arr_ready = (count < (AW+1)'(DEPTH)) && !eng_we;
  assign arr_go    = arr_valid && arr_ready;
  assign we        = eng_we || arr_go;
  assign waddr     = eng_we ? eng_waddr : head;
  assign wdata     = eng_we ? eng_wdata : arr_data;

  if (STORAGE == "BRAM") begin : g_bram
    (* ram_style = "block" *) logic [WIDTH-1:0] mem [DEPTH];
    always_ff @(posedge clk) begin
      if (we) mem[waddr] <= wdata;
      if (eng_re) eng_rdata <= mem[eng_raddr];
    end
  end else if (STORAGE == "LUTRAM") begin : g_lutram
    (* ram_style = "distributed" *) logic [WIDTH-1:0] mem [DEPTH];
    always_ff @(posedge clk) if (we) mem[waddr] <= wdata;
    if (RD_LAT == 1) begin : g_sync
      always_ff @(posedge clk) if (eng_re) eng_rdata <= mem[eng_raddr];
    end else begin : g_async
      assign eng_rdata = mem[eng_raddr];
    end
  end else begin : g_reg
    (* ram_style = "registers" *) logic [WIDTH-1:0] mem [DEPTH];
    always_ff @(posedge clk) if (we) mem[waddr] <= wdata;
    if (RD_LAT == 1) begin : g_sync
      always_ff @(posedge clk) if (eng_re) eng_rdata <= mem[eng_raddr];
    end else begin : g_async
      assign eng_rdata = mem[eng_raddr];
    end
  end

  // ring pointers
  always_ff @(posedge clk) begin
    if (rst) begin
      head <= '0; count <= '0;
    end else begin
      if (arr_go) head <= (head == AW'(DEPTH - 1)) ? '0 : head + 1'b1;
      count <= count + (AW+1)'(arr_go) - (free ? free_n : '0);
    end
  end
endmodule
