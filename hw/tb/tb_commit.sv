// tb_commit.sv — commit unit against the 36-round matrices (vectors/commit_vectors.txt, gen_vectors_step3.py):
// absent types (boundary rounds) carry junk that types_present must mask; windows t = 0, 8, 24 commit homes [t, t+8) with a syndrome carry into round t+8; the last window (t = 32)
// commits homes 32..36 without carry. Random committed hard decisions (2%); expected logical frame = O * e and
// carry = H[round t+8 rows, committed cols] * e, both computed from the matrices.
`timescale 1ns/1ps
module tb_commit;
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
  logic clk = 0, clear = 0, in_valid = 0, last = 0, carry_en = 0, obs_valid, syn_corr_valid;
  logic [NTYPES-1:0][NPOS-1:0] hard = '0;
  logic [NTYPES-1:0] types_present = '1;
  logic [NOBS-1:0] obs, e_obs;
  logic [NPOS-1:0] syn_corr, e_sc;
  logic [NTYPES*NPOS-1:0] hf;
  logic [NTYPES-1:0] tp;
  always #5 clk = ~clk;
  commit dut (.*);

  int fd, t, nr, carry, n = 0, nbad_o = 0, nbad_s = 0, ncarry = 0, got_sc;
  logic [NPOS-1:0] sc_q;
  always @(posedge clk) if (syn_corr_valid) begin got_sc <= 1; sc_q <= syn_corr; end
  initial begin
    fd = $fopen("vectors/commit_vectors.txt", "r");
    if (fd == 0) begin $display("FAIL: no vectors"); $finish; end
    @(negedge clk);
    while ($fscanf(fd, "%d %d %d", t, nr, carry) == 3) begin
      clear = 1; @(negedge clk); clear = 0; got_sc = 0;
      for (int i = 0; i < nr; i++) begin
        void'($fscanf(fd, "%h %h", tp, hf));
        hard = hf; types_present = tp; in_valid = 1; last = (i == nr - 1); carry_en = carry[0];
        @(negedge clk);
      end
      in_valid = 0; last = 0; carry_en = 0;
      void'($fscanf(fd, "%h %h", e_obs, e_sc));
      repeat (3) @(negedge clk);
      if (obs !== e_obs) nbad_o++;
      if (carry) begin ncarry++; if (!got_sc || sc_q !== e_sc) nbad_s++; end
      else if (got_sc) nbad_s++;
      n++;
    end
    $display("tb_commit: vectors %0d (with carry %0d), logical-frame mismatches %0d, syndrome-carry mismatches %0d",
             n, ncarry, nbad_o, nbad_s);
    $display("%s", (n == 80 && nbad_o == 0 && nbad_s == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
