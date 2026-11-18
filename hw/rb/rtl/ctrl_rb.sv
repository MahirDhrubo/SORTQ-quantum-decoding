// ctrl_rb.sv — Test 2f controller for the red-black round engine: one round step per cycle in the order
// window indices 0, 2, 4, ..., 1, 3, 5, ... (all even, then all odd), no stalls inside an iteration.
// Sequencing copied from ctrl_pf.sv (legs, init, overlapped convergence check, speculative iteration t + 1 inside a leg,
// stop on the first converged iteration, PEND_WAIT / CONV_WAIT); changes:
//   - STEP_CYCLES = 1 and the red-black step order (pos j -> window index i = j < NE ? 2j : 2(j - NE) + 1);
//   - every step carries its own flags: init, first (= first iteration of the decode: M(t-1) = L0), leg0 (g8 = G0),
//     pass (0 = even round), par (iteration parity: marginal / hard-decision bank); conv_par = parity of the
//     iteration whose check is requested by conv_req;
//   - prefill handshake: when the last step of a leg-end iteration is issued (and another leg can follow), pre_go
//     pulses; the engine pre-draws the next leg's g8 of the odd rounds (the even pass needs two home rounds per step).
//     The first step of the new leg is issued only when pre_busy is low (it always is: the conv wait is longer).
// Masks for the step of check round g: as ctrl_pf.
// No-forwarding condition: two steps that touch a common error are >= HAZ_DIST issue slots apart (rb_pkg, from H), for
// nrounds = W = 13; the engine's read-to-write latency must be < HAZ_DIST. Other window sizes are not supported here.
module ctrl_rb
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
#(
  parameter int W           = 13,
  parameter int PRE_IT      = 80,
  parameter int LEG_IT      = 60,
  parameter int NLEGS       = 300,
  parameter int NDUP        = 4,
  parameter int RW          = 8
) (
  input  logic                    clk,
  input  logic                    rst,
  input  logic                    start,
  input  logic [RW-1:0]           win_t,
  input  logic [RW-1:0]           last_r,
  input  logic                    conv_valid,
  input  logic                    conv,
  input  logic                    pre_busy,
  output logic                    busy,
  output logic                    done,
  output logic                    success,
  output logic [15:0]             iter_total,
  output logic [8:0]              leg,
  output logic                    gamma_next,     // pulse: new leg (lanes draw)
  output logic                    iter_start,     // pulse: an iteration starts (cycle accounting)
  output logic                    conv_req,       // pulse with the last step of an iteration
  output logic                    conv_par,       // parity of that iteration
  output logic                    pre_go,         // pulse: leg-end iteration issued, pre-draw the next leg's odd rounds
  (* keep = "true" *) output logic [NDUP-1:0]                         step_valid,
  (* keep = "true" *) output logic [NDUP-1:0]                         init,
  (* keep = "true" *) output logic [NDUP-1:0]                         first,
  (* keep = "true" *) output logic [NDUP-1:0]                         leg0,
  (* keep = "true" *) output logic [NDUP-1:0]                         pass,
  (* keep = "true" *) output logic [NDUP-1:0]                         par,
  (* keep = "true" *) output logic [NDUP-1:0][RW-1:0]                 step_g,
  (* keep = "true" *) output logic [NDUP-1:0][NBASE-1:0]              cnu_mask,
  (* keep = "true" *) output logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0]  vnu_mask_cur,
  (* keep = "true" *) output logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0]  vnu_mask_prev,
  (* keep = "true" *) output logic [NDUP-1:0]                         prev_active
);
  localparam int NSTEP_OK = rb_pkg::NSTEP;
`ifndef SYNTHESIS
  initial assert (W == NSTEP_OK) else $fatal(1, "ctrl_rb: only W = %0d is supported (hazard distance)", NSTEP_OK);
`endif
  typedef enum logic [2:0] {IDLE, STEP, CONV_WAIT, FIN, PEND_WAIT} st_t;
  st_t st;
  logic [RW-1:0] j_pos, i_win, nrounds, ne, g_c;
  logic [15:0] it_leg;
  logic init_q, par_q, pend;

  function automatic logic [NTYPES-1:0] tp(input logic [RW:0] h, input logic [RW-1:0] r_last);
    if (h == '0) return TP_FIRST;
    else if (h == {1'b0, r_last}) return TP_LAST;
    else return '1;
  endfunction
  function automatic logic has_o1(input int t);
    for (int k = 0; k < NBASE; k++) if (BE_TYPE[k] == t && BE_OFF[k] == 1) return 1'b1;
    return 1'b0;
  endfunction

  logic [NBASE-1:0]             cm_c;
  logic [NTYPES-1:0][DVMAX-1:0] vc_c, vp_c;
  logic                         pa_c;
  logic [RW:0]                  wend;
  always_comb begin
    logic [RW:0] h, g1, tw;
    logic [NTYPES-1:0] tp_h, tp_g, tp_gm1;
    tw   = {1'b0, win_t} + (RW+1)'(W - 1);
    wend = (tw < {1'b0, last_r}) ? tw : {1'b0, last_r};
    g1   = {1'b0, g_c};
    for (int k = 0; k < NBASE; k++) begin
      h = g1 - (RW+1)'(BE_OFF[k]);
      tp_h = tp(h, last_r);
      cm_c[k] = (g1 >= (RW+1)'(BE_OFF[k])) && (h >= {1'b0, win_t}) && tp_h[BE_TYPE[k]];
    end
    tp_g   = tp(g1, last_r);
    tp_gm1 = tp(g1 - 1, last_r);
    pa_c = (g_c > win_t);
    for (int t = 0; t < NTYPES; t++)
      for (int j = 0; j < DVMAX; j++) begin
        if (TS_EDGE[t][j] < 0) begin
          vc_c[t][j] = 1'b0; vp_c[t][j] = 1'b0;
        end else begin
          vc_c[t][j] = tp_g[t] && (g1 + (RW+1)'(BE_OFF[TS_EDGE[t][j]]) <= wend);
          vp_c[t][j] = pa_c && has_o1(t) && tp_gm1[t]
                       && (g1 - 1 + (RW+1)'(BE_OFF[TS_EDGE[t][j]]) <= wend);
        end
      end
  end

  assign i_win = (j_pos < ne) ? RW'(2 * j_pos) : RW'(2 * (j_pos - ne) + 1);
  assign g_c   = win_t + i_win;

  logic [15:0] leg_len;
  assign leg_len = (leg == '0) ? 16'(PRE_IT) : 16'(LEG_IT);

  always_ff @(posedge clk) begin
    logic do_end;
    do_end = 1'b0;
    gamma_next <= 1'b0; iter_start <= 1'b0; conv_req <= 1'b0; pre_go <= 1'b0;
    step_valid <= '0;
    if (rst) begin
      st <= IDLE; busy <= 1'b0; done <= 1'b0; success <= 1'b0; iter_total <= '0; leg <= '0;
      j_pos <= '0; it_leg <= '0; init_q <= 1'b0; nrounds <= '0; ne <= '0; pend <= 1'b0; par_q <= 1'b0;
      conv_par <= 1'b0;
    end else begin
      case (st)
        IDLE, FIN: if (start) begin
          logic [RW-1:0] nr;
          nr = (({1'b0, win_t} + (RW+1)'(W - 1)) < {1'b0, last_r}) ? RW'(W) : (last_r - win_t + RW'(1));
          st <= STEP; busy <= 1'b1; done <= 1'b0; success <= 1'b0; iter_total <= '0; leg <= '0;
          it_leg <= '0; init_q <= 1'b1; j_pos <= '0; pend <= 1'b0; par_q <= 1'b0;
          nrounds <= nr; ne <= (nr + RW'(1)) >> 1;
          iter_start <= 1'b1;
        end
        STEP: begin
          if (pend && conv_valid) begin
            iter_total <= iter_total + 1'b1; pend <= 1'b0;
          end
          if (pend && conv_valid && conv) begin
            st <= FIN; success <= 1'b1; busy <= 1'b0; done <= 1'b1;
          end else begin
            for (int d = 0; d < NDUP; d++) begin
              step_valid[d] <= 1'b1; init[d] <= init_q; first[d] <= init_q && (leg == '0); leg0[d] <= (leg == '0);
              pass[d] <= i_win[0]; par[d] <= par_q; step_g[d] <= g_c; cnu_mask[d] <= cm_c;
              vnu_mask_cur[d] <= vc_c; vnu_mask_prev[d] <= vp_c; prev_active[d] <= pa_c;
            end
            if (j_pos == nrounds - 1) begin
              j_pos <= '0;
              if (pend && !conv_valid) st <= PEND_WAIT;
              else do_end = 1'b1;
            end else j_pos <= j_pos + 1'b1;
          end
        end
        PEND_WAIT: if (conv_valid) begin
          iter_total <= iter_total + 1'b1; pend <= 1'b0;
          if (conv) begin st <= FIN; success <= 1'b1; busy <= 1'b0; done <= 1'b1; end
          else do_end = 1'b1;
        end
        CONV_WAIT: if (conv_valid) begin
          iter_total <= iter_total + 1'b1;
          if (conv) begin st <= FIN; success <= 1'b1; busy <= 1'b0; done <= 1'b1; end
          else if (it_leg + 1 == leg_len) begin
            if (leg == 9'(NLEGS)) begin st <= FIN; busy <= 1'b0; done <= 1'b1; end
            else begin
              leg <= leg + 1'b1; it_leg <= '0; init_q <= 1'b1; gamma_next <= 1'b1; iter_start <= 1'b1;
              par_q <= ~par_q; st <= STEP;
`ifndef SYNTHESIS
              if (pre_busy) $fatal(1, "ctrl_rb: new leg while the g8 prefill is still running");
`endif
            end
          end else begin
            it_leg <= it_leg + 1'b1; init_q <= 1'b0; iter_start <= 1'b1; par_q <= ~par_q; st <= STEP;
          end
        end
        default: st <= IDLE;
      endcase
      if (do_end) begin
        conv_req <= 1'b1; conv_par <= par_q;
        if (it_leg + 1 != leg_len) begin
          pend <= 1'b1; it_leg <= it_leg + 1'b1; init_q <= 1'b0; iter_start <= 1'b1; par_q <= ~par_q; st <= STEP;
        end else begin
          st <= CONV_WAIT;
          if (leg != 9'(NLEGS)) pre_go <= 1'b1;
        end
      end
    end
  end
endmodule
