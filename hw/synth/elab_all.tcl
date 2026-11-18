# Test 2c pre-flight: RTL elaboration (synth_design -rtl) of every harness; reports errors per run.
set here [file dirname [file normalize [info script]]]
set_param general.maxThreads 2
set runs {}
set fh [open $here/harness/runs.txt]; while {[gets $fh line] >= 0} { lappend runs [lindex $line 0] }; close $fh
if {[llength $argv] > 0} { set runs $argv }
foreach r $runs {
  create_project -in_memory -part xcvu19p-fsva3824-2-e
  set pk [lsort [glob $here/../rtl/*_pkg.sv]]
  foreach f $pk { read_verilog -sv $f }
  foreach f [lsort [glob $here/../rtl/*.sv]] { if {[lsearch $pk $f] < 0} { read_verilog -sv $f } }
  foreach f [lsort [glob $here/rtl_2c/*.sv]] { read_verilog -sv $f }
  read_verilog -sv $here/harness/h_$r.sv
  if {[catch {synth_design -rtl -top h_$r -part xcvu19p-fsva3824-2-e -mode out_of_context} e]} {
    puts "ELAB $r FAIL"
  } else { puts "ELAB $r OK" }
  close_project
}
