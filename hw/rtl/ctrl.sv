// ctrl.sv — controller for one window decode: iterations as round sweeps, relay legs, init flag, boundary masks.
//
// Sequence (ARITHMETIC.md sections 4-5): leg 0 (PRE_IT iterations, g8 = G0), then up to NLEGS legs of LEG_IT
// iterations, each starting with a new g8 draw and init = 1 in its first iteration. One iteration = round steps for
// the window rounds g = win_t .. min(win_t + W - 1, last_r), in order, one step every STEP_CYCLES cycles (the
// engine's round-step dependency latency), then a convergence request; stop on the first converged iteration.
//
// Masks for the step of check round g (window rows = rounds [win_t, win_t + W), window columns = errors homed in
// [win_t, win_t + W); global boundary: home round 0 has TP_FIRST types, home round last_r has TP_LAST types):
//   cnu_mask[k]            = home g - o_k inside the window and type_k present at that home round
//   vnu_mask_cur[t][j]     errors homed g    : slot j exists, type present, its check round g + o_j <= window end
//   vnu_mask_prev[t][j]    errors homed g - 1: same (only types with an offset-1 edge are updated in layer g)
//   prev_active            g - 1 is inside the window
// All step outputs are registered and duplicated NDUP times (fan-out control; each copy drives a slice of the
// engine). Copies are marked keep so synthesis does not merge them.
module ctrl
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
#(
  parameter int W           = 12,
  parameter int STEP_CYCLES = 4,
  parameter int PRE_IT      = 80,
  parameter int LEG_IT      = 60,
  parameter int NLEGS       = 300,
  parameter int NDUP        = 4,
  parameter int RW          = 8
) (
  input  logic                    clk,
  input  logic                    rst,
  input  logic                    start,
  input  logic [RW-1:0]           win_t,          // global round of the window start
  input  logic [RW-1:0]           last_r,         // final round R of the circuit
  input  logic                    conv_valid,
  input  logic                    conv,
  output logic                    busy,
  output logic                    done,
  output logic                    success,
  output logic [15:0]             iter_total,
  output logic [8:0]              leg,
  output logic                    gamma_start,    // pulse: leg 0 (g8 = G0)
  output logic                    gamma_next,     // pulse: new leg (draw g8)
  output logic                    iter_start,     // pulse: latch memory M(t-1) <- marginals
  output logic                    conv_req,       // pulse: all writes of the iteration are done
  (* keep = "true" *) output logic [NDUP-1:0]                         step_valid,
  (* keep = "true" *) output logic [NDUP-1:0]                         init,
  (* keep = "true" *) output logic [NDUP-1:0][RW-1:0]                 step_g,
  (* keep = "true" *) output logic [NDUP-1:0][NBASE-1:0]              cnu_mask,
  (* keep = "true" *) output logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0]  vnu_mask_cur,
  (* keep = "true" *) output logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0]  vnu_mask_prev,
  (* keep = "true" *) output logic [NDUP-1:0]                         prev_active
);
  typedef enum logic [1:0] {IDLE, STEP, CONV_WAIT, FIN} st_t;
  st_t st;
  logic [RW-1:0] i_win, nrounds, g_c;
  logic [$clog2(STEP_CYCLES + 1)-1:0] cyc;
  logic [15:0] it_leg;
  logic init_q;

  // types present at a home round
  function automatic logic [NTYPES-1:0] tp(input logic [RW:0] h, input logic [RW-1:0] r_last);
    if (h == '0) return TP_FIRST;
    else if (h == {1'b0, r_last}) return TP_LAST;
    else return '1;
  endfunction

  // has an offset-1 edge (from the base-edge table)
  function automatic logic has_o1(input int t);
    for (int k = 0; k < NBASE; k++) if (BE_TYPE[k] == t && BE_OFF[k] == 1) return 1'b1;
    return 1'b0;
  endfunction

  logic [NBASE-1:0]             cm_c;
  logic [NTYPES-1:0][DVMAX-1:0] vc_c, vp_c;
  logic                         pa_c;
  logic [RW:0]                  wend;             // last round inside the window (min(win_t + W - 1, last_r))

  always_comb begin
    logic [RW:0] h, g1, tw;
    logic [NTYPES-1:0] tp_h, tp_g, tp_gm1;   // function results in variables (Vivado: no select on a call)
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

  assign g_c = win_t + i_win;

  always_ff @(posedge clk) begin
    gamma_start <= 1'b0; gamma_next <= 1'b0; iter_start <= 1'b0; conv_req <= 1'b0;
    step_valid  <= '0;
    if (rst) begin
      st <= IDLE; busy <= 1'b0; done <= 1'b0; success <= 1'b0; iter_total <= '0; leg <= '0;
      i_win <= '0; cyc <= '0; it_leg <= '0; init_q <= 1'b0; nrounds <= '0;
    end else begin
      case (st)
        IDLE, FIN: if (start) begin
          st <= STEP; busy <= 1'b1; done <= 1'b0; success <= 1'b0; iter_total <= '0; leg <= '0;
          it_leg <= '0; init_q <= 1'b1; i_win <= '0; cyc <= '0;
          nrounds <= (({1'b0, win_t} + (RW+1)'(W - 1)) < {1'b0, last_r}) ? RW'(W) : (last_r - win_t + RW'(1));
          gamma_start <= 1'b1; iter_start <= 1'b1;
        end
        STEP: begin
          if (cyc == '0) begin
            for (int d = 0; d < NDUP; d++) begin
              step_valid[d] <= 1'b1; init[d] <= init_q; step_g[d] <= g_c; cnu_mask[d] <= cm_c;
              vnu_mask_cur[d] <= vc_c; vnu_mask_prev[d] <= vp_c; prev_active[d] <= pa_c;
            end
          end
          if (cyc == ($bits(cyc))'(STEP_CYCLES - 1)) begin
            cyc <= '0;
            if (i_win == nrounds - 1) begin st <= CONV_WAIT; conv_req <= 1'b1; i_win <= '0; end
            else i_win <= i_win + 1'b1;
          end else cyc <= cyc + 1'b1;
        end
        CONV_WAIT: if (conv_valid) begin
          iter_total <= iter_total + 1'b1;
          if (conv) begin st <= FIN; success <= 1'b1; busy <= 1'b0; done <= 1'b1; end
          else if (it_leg + 1 == ((leg == '0) ? 16'(PRE_IT) : 16'(LEG_IT))) begin
            if (leg == 9'(NLEGS)) begin st <= FIN; busy <= 1'b0; done <= 1'b1; end
            else begin
              leg <= leg + 1'b1; it_leg <= '0; init_q <= 1'b1; gamma_next <= 1'b1; iter_start <= 1'b1; st <= STEP;
            end
          end else begin
            it_leg <= it_leg + 1'b1; init_q <= 1'b0; iter_start <= 1'b1; st <= STEP;
          end
        end
        default: st <= IDLE;
      endcase
    end
  end
endmodule
