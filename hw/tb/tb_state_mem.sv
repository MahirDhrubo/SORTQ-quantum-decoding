// tb_state_mem.sv — state_mem against a reference model: 20,000 cycles of random arrivals, engine reads and
// write-backs, and frees; checks read data (with RD_LAT), head, count, arr_ready (full and write-priority).
`timescale 1ns/1ps
module tb_state_mem;
  parameter string STORAGE = "BRAM";
  parameter int RD_LAT = 1;
  localparam int DEPTH = 12, WIDTH = 40, AW = 4;
  logic clk = 0, rst = 1, arr_valid = 0, arr_ready, eng_re = 0, eng_we = 0, free = 0;
  logic [WIDTH-1:0] arr_data = '0, eng_rdata, eng_wdata = '0;
  logic [AW-1:0] head, eng_raddr = '0, eng_waddr = '0;
  logic [AW:0] count, free_n = '0;
  always #5 clk = ~clk;
  state_mem #(.DEPTH(DEPTH), .WIDTH(WIDTH), .STORAGE(STORAGE), .RD_LAT(RD_LAT)) dut (.*);

  logic [WIDTH-1:0] model [DEPTH];
  int m_head = 0, m_count = 0, nbad = 0, nreads = 0, nfull = 0, nprio = 0;
  logic [WIDTH-1:0] exp_rd; logic exp_v = 0;
  initial begin
    foreach (model[i]) model[i] = '0;
    repeat (2) @(negedge clk); rst = 0;
    // fill all slots once through the arrival port so reads are defined
    for (int i = 0; i < 20000; i++) begin
      arr_valid = ($urandom_range(0, 1) == 1); arr_data = {$urandom, $urandom};
      eng_we = ($urandom_range(0, 3) == 0); eng_waddr = AW'($urandom_range(0, DEPTH - 1)); eng_wdata = {$urandom, $urandom};
      eng_re = ($urandom_range(0, 1) == 1); eng_raddr = AW'($urandom_range(0, DEPTH - 1));
      free = (m_count > 0) && ($urandom_range(0, 4) == 0); free_n = (AW+1)'($urandom_range(1, (m_count > 0) ? m_count : 1));
      #1;
      // combinational checks before the edge
      if (arr_ready !== ((m_count < DEPTH) && !eng_we)) nbad++;
      if (m_count >= DEPTH) nfull++;
      if (eng_we && arr_valid) nprio++;
      if (RD_LAT == 0 && eng_re) begin nreads++; if (eng_rdata !== model[eng_raddr]) nbad++; end
      if (RD_LAT == 1) begin exp_v = eng_re; exp_rd = model[eng_raddr]; end
      @(posedge clk);
      // model update
      if (eng_we) model[eng_waddr] = eng_wdata;
      else if (arr_valid && m_count < DEPTH) begin model[m_head] = arr_data; m_head = (m_head + 1) % DEPTH; end
      m_count = m_count + ((!eng_we && arr_valid && m_count < DEPTH) ? 1 : 0) - (free ? int'(free_n) : 0);
      #1;
      if (RD_LAT == 1 && exp_v) begin nreads++; if (eng_rdata !== exp_rd) nbad++; end
      if (int'(head) != m_head || int'(count) != m_count) nbad++;
      @(negedge clk);
    end
    $display("tb_state_mem STORAGE=%s RD_LAT=%0d: 20000 cycles, reads checked %0d, cycles full %0d, write conflicts %0d, mismatches %0d",
             STORAGE, RD_LAT, nreads, nfull, nprio, nbad);
    $display("%s", (nbad == 0 && nreads > 5000) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
