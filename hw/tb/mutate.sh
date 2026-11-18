#!/bin/bash
# Mutation check: each mutant is one realistic bug injected into a copy of the RTL; its testbench must FAIL.
# Usage: ./mutate.sh   (writes logs/mutation.log);  ONLY="name1 name2" ./mutate.sh runs only those mutants.
cd "$(dirname "$0")"
run() {  # run <name> <tb> <file> <sed-expression> [tb params]
  local name=$1 tb=$2 f=$3 ex=$4; shift 4
  if [ -n "$ONLY" ] && [[ " $ONLY " != *" $name "* ]]; then return; fi
  local d=mut/$name; rm -rf $d; mkdir -p $d; cp ../rtl/*.sv $d/
  sed -i "$ex" $d/$f
  if cmp -s ../rtl/$f $d/$f; then echo "$name: MUTATION NOT APPLIED"; return; fi
  local ra="" bp=() x; for x in "$@"; do if [[ $x == +* ]]; then ra="$ra $x"; else bp+=("$x"); fi; done  # +X = run-time plusarg
  local out; out=$(RTL=$d OBJTAG=$name RUNARGS="${ra# }" ./run_tb.sh $tb "${bp[@]}" 2>&1 | grep -E "^PASS|^FAIL|BUILD FAILED" | tail -1)
  echo "$name ($tb): ${out:-no verdict} $( [ "$out" = FAIL ] && echo '-> caught' || echo '-> NOT CAUGHT')"
}
{
run cnu_min2      tb_cnu       cnu.sv       's/? m2_c : m1_c)/? m1_c : m1_c)/'
run cnu_parity    tb_cnu       cnu.sv       's/par_c = syn ^ ^(in_sign \& mask);/par_c = ^(in_sign \& mask);/'
run cnu_mask      tb_cnu       cnu.sv       's/(i < DEG \&\& mask\[i\]) ? in_mag\[i\]/(i < DEG) ? in_mag[i]/'
run vnu_round     tb_vnu       vnu.sv       's/rnd    = (num + PW.(1 << (GD - 1))) >>> GD;/rnd    = num >>> GD;/'
run vnu_gate      tb_vnu       vnu.sv       's/(mask\[e\] \&\& !(init \&\& late\[e\]))/(mask[e])/'
run vnu_hard      tb_vnu       vnu.sv       's/hard_c = (marg_c <= 0);/hard_c = (marg_c < 0);/'
run vnu_margsat   tb_vnu       vnu.sv       's/marg_c = MB.(sat(total, MARGMIN, MARGMAX));/marg_c = MB'"'"'(total);/'
run rot_dir       tb_rot2d     rot2d.sv     's/t\[((a + (1 << k)) % A)\*B + b\]/t[((a + A - (1 << k)) % A)*B + b]/'
run wiring_edge   tb_round_wiring round_wiring.sv '0,/assign cnu_in\[ck\]\[0\]\[4\] = v2c_o0\[ck\]\[3\]\[\([0-9]*\)\]/s//assign cnu_in[ck][0][4] = v2c_o0[ck][3][0]/'
run conv_mask     tb_conv_check conv_check.sv 's/assign terms\[k\] = emask\[i\]\[k\] \& hard/assign terms[k] = hard/'
run commit_rom    tb_commit    commit.sv    's/acc ^= h_m\[t\]\[p\] \& OBS_ROM\[t\]\[p\]\[b\];/acc ^= h_m[t][p] \& OBS_ROM[t][(p + 1) % NPOS][b];/'
run commit_tp     tb_commit    commit.sv    's/h_m\[t\] = types_present\[t\] ? hard\[t\] : .0;/h_m[t] = hard[t];/'
run commit_carry  tb_commit    commit.sv    's/if (BE_OFF\[k\] == 1) begin : g_on/if (BE_OFF[k] == 0) begin : g_on/'
run ctrl_wend     tb_ctrl      ctrl.sv      's/tw   = {1.b0, win_t} + (RW+1).(W - 1);/tw   = {1'"'"'b0, win_t} + (RW+1)'"'"'(W);/'
run gamma_thr     tb_gamma_src gamma_src.sv 's/187, 791/188, 791/'
run smem_wrap     tb_state_mem state_mem.sv 's/(head == AW.(DEPTH - 1)) ? .0 : head + 1.b1/(head == AW'"'"'(DEPTH)) ? '"'"'0 : head + 1'"'"'b1/'
run round_init    tb_round_step round_step.sv 's/= init ? {pr\[MW-1\], (pr\[MW-1\] ? N.(-pr) : N.(pr))} : v2c_o0_st/= v2c_o0_st/'
run round_prior_rd tb_round_step round_step.sv 's/prf\[round_idx - RW.(1)\]/prf[round_idx]/'
run round_late    tb_round_step round_step.sv 's/assign clate\[j\] = INIT_ZERO_CUR\[t\]\[j\];/assign clate[j] = 1'"'"'b0;/' -GVNU_PASSES=2
run round_pass_sel tb_round_step round_step.sv 's/assign sel = s_b;/assign sel = s_cnu;/' -GVNU_PASSES=2
run round_pass_prior tb_round_step round_step.sv 's/.prior(sel ? prior_prev_t\[t\] : prior_cur_t\[t\])/.prior(prior_cur_t[t])/' -GVNU_PASSES=2
run pf_adv_p2   tb_round_step_pf round_step_pf.sv 's/assign adv = a_new \&\& !start \&\& !((VNU_PASSES == 2) \&\& s_cnu);/assign adv = a_new \&\& !start;/' -GVNU_PASSES=2
run pf_prev_rd   tb_round_step_pf round_step_pf.sv 's/prf\[nxt_round_idx - RW.(1)\]/prf[nxt_round_idx]/'
run pf_sm        tb_round_step_pf round_step_pf.sv 's/a_cur_sm\[t\] <= to_sm(rd_cur\[t\]);/a_cur_sm[t] <= rd_cur[t];/'
run pf2_bfresh  tb_round_step_pf2 round_step_pf2.sv 's/assign mv_b   = adv_ok \&\& a2_new \&\& !b_fresh;/assign mv_b   = adv_ok \&\& a2_new;/'
run pf2_a2      tb_round_step_pf2 round_step_pf2.sv 's/assign mv_a2  = adv_ok \&\& a_new \&\& (!a2_new || mv_b);/assign mv_a2  = adv_ok \&\& a_new \&\& !a2_new;/'
run pf2_adv_p2  tb_round_step_pf2 round_step_pf2.sv 's/assign adv_ok = !start \&\& !((VNU_PASSES == 2) \&\& s_cnu);/assign adv_ok = !start;/' -GVNU_PASSES=2
run pf2_flush   tb_round_step_pf2 round_step_pf2.sv 's/a_new <= nxt_valid; a2_new <= 1.b0; b_fresh <= 1.b0;/a_new <= nxt_valid;/' +FLUSH
} 2>&1 | tee logs/mutation${ONLY:+_$(echo $ONLY | tr ' ' '+')}.log
