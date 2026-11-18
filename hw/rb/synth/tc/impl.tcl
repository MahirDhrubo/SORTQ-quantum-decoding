# Test 2f timing closure: implementation of synth.dcp with directives.
# Usage: vivado -mode batch -source impl.tcl -tclargs <period_ns> <place_directive> <outdir>
# Flow: opt_design; place_design -directive P; phys_opt_design -directive AggressiveExplore;
#       route_design -directive Explore; phys_opt_design (post-route). Reports as run_block_rb.tcl.
set period [lindex $argv 0]; set pdir [lindex $argv 1]; set outdir [lindex $argv 2]
set here [file dirname [file normalize [info script]]]
file mkdir $outdir
set_param general.maxThreads 4
open_checkpoint $here/synth.dcp
create_clock -name clk -period $period [get_ports clk]
set_input_delay  -clock clk 0 [get_ports sin]
set_output_delay -clock clk 0 [get_ports sout]
set t0 [clock seconds]
opt_design
place_design -directive $pdir
set t1 [clock seconds]
set wns_place [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
phys_opt_design -directive AggressiveExplore
set wns_popt [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
set t2 [clock seconds]
route_design -directive Explore
set wns_route [get_property SLACK [lindex [get_timing_paths -setup -max_paths 1] 0]]
set t3 [clock seconds]
phys_opt_design
set t4 [clock seconds]
report_utilization -file $outdir/util_route.rpt
report_utilization -hierarchical -hierarchical_depth 2 -file $outdir/util_route_hier.rpt
report_timing_summary -max_paths 10 -file $outdir/timing_summary.rpt
report_timing -max_paths 20 -nworst 1 -sort_by slack -file $outdir/timing_paths.rpt
report_design_analysis -logic_level_distribution -file $outdir/logic_levels.rpt
write_checkpoint -force $outdir/routed.dcp
set p [lindex [get_timing_paths -setup -max_paths 1 -nworst 1] 0]
set f [open $outdir/result.txt w]
puts $f "period $period"
puts $f "place_directive $pdir"
puts $f "wns [get_property SLACK $p]"
puts $f "wns_after_place $wns_place"
puts $f "wns_after_place_physopt $wns_popt"
puts $f "wns_after_route $wns_route"
puts $f "start [get_property STARTPOINT_PIN $p]"
puts $f "end [get_property ENDPOINT_PIN $p]"
puts $f "logic_levels [get_property LOGIC_LEVELS $p]"
puts $f "datapath_delay [get_property DATAPATH_DELAY $p]"
puts $f "logic_delay [get_property DATAPATH_LOGIC_DELAY $p]"
puts $f "net_delay [get_property DATAPATH_NET_DELAY $p]"
puts $f "route_status [llength [get_nets -hier -filter {ROUTE_STATUS == UNROUTED || ROUTE_STATUS == CONFLICTS}]]"
puts $f "t_opt_place_s [expr {$t1 - $t0}]"
puts $f "t_physopt_s [expr {$t2 - $t1}]"
puts $f "t_route_s [expr {$t3 - $t2}]"
puts $f "t_postroute_physopt_s [expr {$t4 - $t3}]"
close $f
puts "IMPL_DONE $pdir $period"
