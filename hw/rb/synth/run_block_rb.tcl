# Test 2f: one out-of-context run of engine_top_rb, same flow and reports as Test 2c run_block.tcl
# (synth_design -flatten_hierarchy rebuilt -> opt_design -> place_design -> route_design; reports after route).
# Sources listed explicitly (verified 2a blocks unchanged + rb files), not globbed, so other sessions' files are not read.
# Usage: vivado -mode batch -source run_block_rb.tcl -tclargs <run> <period_ns> <threads> <outdir> [dcp 0/1]
set run     [lindex $argv 0]
set period  [lindex $argv 1]
set threads [lindex $argv 2]
set outdir  [lindex $argv 3]
set dcp     [expr {[llength $argv] > 4 ? [lindex $argv 4] : 0}]
set part    xcvu19p-fsva3824-2-e
set here    [file dirname [file normalize [info script]]]
set R  $here/../../rtl
set RB $here/../rtl
file mkdir $outdir
set_param general.maxThreads $threads
create_project -in_memory -part $part
foreach f [list $R/round_wiring_pkg.sv $R/engine_tables_pkg.sv $RB/rb_pkg.sv $R/round_wiring.sv $R/cnu.sv \
                $R/vnu_nosat.sv $R/gamma_src.sv $R/state_mem.sv $R/conv_check.sv $R/commit.sv $RB/vnu_post_rb.sv \
                $RB/cnu_merge_rb.sv $RB/round_step_rb.sv $RB/ctrl_rb.sv $RB/engine_top_rb.sv $here/harness/h_$run.sv] {
  read_verilog -sv $f
}
set t0 [clock seconds]
synth_design -top h_$run -part $part -mode out_of_context -flatten_hierarchy rebuilt
set t1 [clock seconds]
create_clock -name clk -period $period [get_ports clk]
set_input_delay  -clock clk 0 [get_ports sin]
set_output_delay -clock clk 0 [get_ports sout]
report_utilization -hierarchical -hierarchical_depth 4 -file $outdir/util_synth_hier.rpt
opt_design
place_design
set t2 [clock seconds]
route_design
set t3 [clock seconds]
report_utilization -file $outdir/util_route.rpt
report_utilization -hierarchical -hierarchical_depth 4 -file $outdir/util_route_hier.rpt
report_timing_summary -max_paths 10 -file $outdir/timing_summary.rpt
report_timing -max_paths 20 -nworst 1 -sort_by slack -file $outdir/timing_paths.rpt
report_design_analysis -logic_level_distribution -file $outdir/logic_levels.rpt
if {$dcp} { write_checkpoint -force $outdir/routed.dcp }
set p [lindex [get_timing_paths -setup -max_paths 1 -nworst 1] 0]
set wns [get_property SLACK $p]
set f [open $outdir/result.txt w]
puts $f "run $run"
puts $f "period $period"
puts $f "wns $wns"
puts $f "start [get_property STARTPOINT_PIN $p]"
puts $f "end [get_property ENDPOINT_PIN $p]"
puts $f "logic_levels [get_property LOGIC_LEVELS $p]"
puts $f "datapath_delay [get_property DATAPATH_DELAY $p]"
puts $f "logic_delay [get_property DATAPATH_LOGIC_DELAY $p]"
puts $f "net_delay [get_property DATAPATH_NET_DELAY $p]"
puts $f "route_status [llength [get_nets -hier -filter {ROUTE_STATUS == UNROUTED || ROUTE_STATUS == CONFLICTS}]]"
puts $f "t_synth_s [expr {$t1 - $t0}]"
puts $f "t_opt_place_s [expr {$t2 - $t1}]"
puts $f "t_route_s [expr {$t3 - $t2}]"
close $f
puts "RUN_DONE $run wns=$wns"
