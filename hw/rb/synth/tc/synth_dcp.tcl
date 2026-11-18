# Test 2f timing closure: synthesize engine_top_rb once (same sources / options as run_block_rb.tcl) -> synth.dcp,
# so every implementation variant starts from the identical netlist (no RTL change).
set here [file dirname [file normalize [info script]]]
set R  $here/../../../rtl
set RB $here/../../rtl
set_param general.maxThreads 4
create_project -in_memory -part xcvu19p-fsva3824-2-e
foreach f [list $R/round_wiring_pkg.sv $R/engine_tables_pkg.sv $RB/rb_pkg.sv $R/round_wiring.sv $R/cnu.sv \
                $R/vnu_nosat.sv $R/gamma_src.sv $R/state_mem.sv $R/conv_check.sv $R/commit.sv $RB/vnu_post_rb.sv \
                $RB/cnu_merge_rb.sv $RB/round_step_rb.sv $RB/ctrl_rb.sv $RB/engine_top_rb.sv \
                $here/../harness/h_engine_top_rb.sv] { read_verilog -sv $f }
set t0 [clock seconds]
synth_design -top h_engine_top_rb -part xcvu19p-fsva3824-2-e -mode out_of_context -flatten_hierarchy rebuilt
write_checkpoint -force $here/synth.dcp
puts "SYNTH_DONE [expr {[clock seconds] - $t0}] s"
