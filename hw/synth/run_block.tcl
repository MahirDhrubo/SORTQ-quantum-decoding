# Test 2c: one out-of-context run: synth_design -> opt_design -> place_design -> route_design, reports after route.
# Usage: vivado -mode batch -source run_block.tcl -tclargs <run> <period_ns> <threads> <outdir> [dcp 0/1]
# Sources: ../rtl (verified 2a RTL, packages first), rtl_2c (2c-only files), harness/h_<run>.sv (top h_<run>).
set run     [lindex $argv 0]
set period  [lindex $argv 1]
set threads [lindex $argv 2]
set outdir  [lindex $argv 3]
set dcp     [expr {[llength $argv] > 4 ? [lindex $argv 4] : 0}]
set part    xcvu19p-fsva3824-2-e
set here    [file dirname [file normalize [info script]]]
file mkdir $outdir
set_param general.maxThreads $threads
create_project -in_memory -part $part
set pk [lsort [glob $here/../rtl/*_pkg.sv]]
set rt [lsort [glob $here/../rtl/*.sv]]
foreach f $pk { read_verilog -sv $f }
foreach f $rt { if {[lsearch $pk $f] < 0} { read_verilog -sv $f } }
foreach f [lsort [glob $here/rtl_2c/*.sv]] { read_verilog -sv $f }
read_verilog -sv $here/harness/h_$run.sv
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
# one-line result (parsed by collect.py)
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
